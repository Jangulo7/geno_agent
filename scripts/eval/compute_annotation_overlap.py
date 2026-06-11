"""Per-case LIRICAL annotation-overlap flag (Thread D, paper extension v3).

For each case in ``data/test_cases_1050/test_cases.jsonl`` we determine whether
the case's source PMID is referenced by ``phenotype.hpoa`` for any of the
causal-OMIM-disease's HPO annotations. If yes, LIRICAL's likelihood-ratio
computation for that case is partly recalling memorised training data instead
of predicting from the patient's clinical phenotype — this is the well-known
annotation-overlap confound (Smedley 2015; EJHG 2026).

The output ``annotation_overlap.json`` is a per-case record::

    {
        "case_id": "AAGAB:PMID_24573067_CASE_REPORT",
        "source_pmid": "PMID:24573067",
        "omim_ids": ["OMIM:148600"],
        "overlap": 1,
        "matching_rows": 7,
        "matching_hpo_ids": ["HP:0007530", "HP:0045059", ...],
    }

Acceptance criteria (plan v3 §3b.8):
- per-case binary flag produced ✓ (this script)
- summary stats: cohort overlap rate, per-MONDO breakdown, per-cell rank-1 split

Run::

    PYTHONPATH=. python scripts/eval/compute_annotation_overlap.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("overlap")

DEFAULT_TEST_CASES: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl"
DEFAULT_HPOA: Final[Path] = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "phenotype.hpoa"
DEFAULT_OUT: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"


def build_hpoa_index(hpoa_path: Path) -> dict[tuple[str, str], list[str]]:
    """Return ``{(disease_id, reference): [hpo_id, ...]}`` from phenotype.hpoa.

    Both keys are kept as the canonical form they appear in the file
    (e.g. ``"OMIM:148600"``, ``"PMID:24573067"``).
    """
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    header: list[str] | None = None
    n_data_rows = 0
    with hpoa_path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("#"):
                continue
            cols = line.split("\t")
            if header is None:
                header = cols
                continue
            if len(cols) < len(header):
                continue
            row = dict(zip(header, cols, strict=False))
            disease_id = row.get("database_id", "").strip()
            reference = row.get("reference", "").strip()
            hpo_id = row.get("hpo_id", "").strip()
            if not disease_id or not reference or not hpo_id:
                continue
            # reference may itself be semicolon-delimited (e.g. "PMID:1;PMID:2")
            for ref in reference.split(";"):
                ref = ref.strip()
                if not ref.startswith("PMID:"):
                    continue
                index[(disease_id, ref)].append(hpo_id)
            n_data_rows += 1
    log.info(
        "Loaded %d rows from %s -> %d (disease, PMID) keys",
        n_data_rows,
        hpoa_path.name,
        len(index),
    )
    return index


def extract_source_pmid(case: dict) -> str | None:
    """Return canonical ``PMID:<digits>`` from the case_id prefix."""
    case_id = case.get("case_id", "")
    parts = case_id.split(":", 1)
    if len(parts) != 2:
        return None
    suffix = parts[1]
    # suffix like "PMID_24573067_CASE_REPORT" -> PMID:24573067
    tokens = suffix.split("_")
    if len(tokens) >= 2 and tokens[0] == "PMID" and tokens[1].isdigit():
        return f"PMID:{tokens[1]}"
    return None


def overlap_for_case(case: dict, hpoa_index: dict[tuple[str, str], list[str]]) -> dict:
    """Return overlap record for a single case."""
    pmid = extract_source_pmid(case)
    omim_ids = [d["id"] for d in case.get("diseases", []) if d.get("id", "").startswith("OMIM:")]
    matching_hpo_ids: list[str] = []
    matching_rows = 0
    if pmid is not None:
        for omim in omim_ids:
            hits = hpoa_index.get((omim, pmid), [])
            matching_rows += len(hits)
            matching_hpo_ids.extend(hits)
    return {
        "case_id": case["case_id"],
        "source_pmid": pmid,
        "omim_ids": omim_ids,
        "category": case.get("category", "unknown"),
        "overlap": 1 if matching_rows > 0 else 0,
        "matching_rows": matching_rows,
        "matching_hpo_ids": sorted(set(matching_hpo_ids)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-cases", type=Path, default=DEFAULT_TEST_CASES)
    parser.add_argument("--hpoa", type=Path, default=DEFAULT_HPOA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    hpoa = build_hpoa_index(args.hpoa)

    cases: list[dict] = []
    with args.test_cases.open() as fh:
        for line in fh:
            if line.strip():
                cases.append(json.loads(line))
    log.info("Loaded %d cases from %s", len(cases), args.test_cases)

    records = [overlap_for_case(c, hpoa) for c in cases]

    # ---- summary
    n = len(records)
    n_overlap = sum(r["overlap"] for r in records)
    n_no_pmid = sum(1 for r in records if r["source_pmid"] is None)
    n_no_omim = sum(1 for r in records if not r["omim_ids"])

    print(f"\n=== Cohort overlap summary (n={n}) ===")
    print(f"  overlap-present:  {n_overlap:4d} ({100 * n_overlap / n:5.1f}%)")
    print(f"  overlap-absent:   {n - n_overlap:4d} ({100 * (n - n_overlap) / n:5.1f}%)")
    print(f"  cases with no extractable source PMID: {n_no_pmid}")
    print(f"  cases with no OMIM disease id:         {n_no_omim}")

    by_cat: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        by_cat[r["category"]]["total"] += 1
        by_cat[r["category"]]["overlap"] += r["overlap"]

    print("\n=== Per-MONDO overlap rate ===")
    print(f"  {'category':<16s} {'n':>5s} {'overlap':>9s} {'rate':>7s}")
    for cat in sorted(by_cat):
        c = by_cat[cat]
        rate = 100 * c["overlap"] / c["total"]
        print(f"  {cat:<16s} {c['total']:>5d} {c['overlap']:>9d} {rate:>6.1f}%")

    # ---- write
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "meta": {
                    "n": n,
                    "n_overlap": n_overlap,
                    "n_no_pmid": n_no_pmid,
                    "n_no_omim": n_no_omim,
                    "hpoa_source": str(args.hpoa),
                    "test_cases_source": str(args.test_cases),
                },
                "records": records,
            },
            indent=2,
        )
    )
    log.info("Wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
