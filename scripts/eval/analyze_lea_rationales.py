"""Thread G — local analysis of LEA rationale quality.

The plan v3 spec for Thread G (§3c.5) is a 4-system contrast table where
the only quantitative cell that requires GPT-4o is the RAGAS faithfulness
score on Cell S. Everything else can be computed locally from the existing
Cell S sidecars:

  * coverage         fraction of top-ranked genes with a non-empty rationale
  * substantiveness  fraction with > 30 chars AND not a generic fallback
                     ("No direct evidence ...", "No information ...")
  * length           median chars per rationale (top-1 vs lower-ranked)
  * citation density mean PMCIDs in the LEA evidence underlying each top gene

For the comparison table:

| System  | Output format            | Free-text rationale? | Chunk citations? |
|---------|--------------------------|----------------------|-------------------|
| K       | gene + hiPhive score     | No                   | No                |
| M       | OMIM disease + post.prob | No                   | No                |
| L       | gene + score             | No                   | partial (chunks)  |
| S       | gene + rationale         | **Yes** (n=X covered)| **Yes** (PMCIDs)  |

Run::

    PYTHONPATH=. python scripts/eval/analyze_lea_rationales.py
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("thread_g")

DEFAULT_RESPONSES: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_S_responses"
DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
DEFAULT_OUT: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "thread_g_rationale_stats.json"

# Phrases LEA emits when it has no real signal for a gene. Anything matching
# one of these is counted as "non-substantive" — these are formulaic
# fallbacks, not actual reasoning.
GENERIC_FALLBACK_PATTERNS: Final[list[re.Pattern]] = [
    re.compile(r"no direct evidence", re.I),
    re.compile(r"no information", re.I),
    re.compile(r"no specific evidence", re.I),
    re.compile(r"no published evidence", re.I),
    re.compile(r"no relevant", re.I),
    re.compile(r"not linked", re.I),
    re.compile(r"unlikely candidate", re.I),
]
SUBSTANTIVENESS_MIN_CHARS: Final[int] = 30


def is_substantive(rationale: str) -> bool:
    """Return True iff the rationale is non-generic and ≥ 30 chars."""
    if not rationale or len(rationale) < SUBSTANTIVENESS_MIN_CHARS:
        return False
    return not any(p.search(rationale) for p in GENERIC_FALLBACK_PATTERNS)


def analyze_case(sidecar: dict) -> dict:
    """Return per-case rationale stats."""
    lea = sidecar.get("lea_log") or {}
    parsed = lea.get("lea_response_parsed") or []
    if not isinstance(parsed, list):
        parsed = []
    evidence = lea.get("lea_evidence_per_gene") or {}

    n_ranked = len(parsed)
    rationales = [(p.get("gene", ""), p.get("rationale", "") or "") for p in parsed]
    n_with_rationale = sum(1 for _, r in rationales if r.strip())
    n_substantive = sum(1 for _, r in rationales if is_substantive(r))

    # Top-1 specific
    top1_gene = parsed[0].get("gene", "") if parsed else ""
    top1_rationale = parsed[0].get("rationale", "") if parsed else ""
    top1_substantive = is_substantive(top1_rationale)
    top1_len = len(top1_rationale)

    # Length distribution
    lengths = [len(r) for _, r in rationales if r]

    # Causal-gene-specific
    causal_gene = sidecar.get("causal_gene") or ""
    causal_rationale = next((r for g, r in rationales if g == causal_gene), "")
    causal_substantive = is_substantive(causal_rationale)
    causal_len = len(causal_rationale)

    # Citation density: PMCIDs cited in the LEA evidence underlying each ranked gene
    # (this is the structural evidence trail; the rationale itself is short and
    # rarely contains literal PMCID strings)
    pmcids_per_gene: dict[str, set[str]] = defaultdict(set)
    for gene, chunks in evidence.items():
        for ch in chunks or []:
            pmcid = (ch or {}).get("source_pmcid") if isinstance(ch, dict) else None
            if pmcid:
                pmcids_per_gene[gene].add(pmcid)
    top1_pmcids = len(pmcids_per_gene.get(top1_gene, set()))
    causal_pmcids = len(pmcids_per_gene.get(causal_gene, set()))
    pmcid_counts = [len(s) for s in pmcids_per_gene.values()]

    # Fallback flag (LEA bypassed the LLM and used a deterministic baseline)
    fallback = lea.get("lea_fallback_reason") not in (None, "", "ok")

    return {
        "case_id": sidecar.get("case_id"),
        "category": sidecar.get("category"),
        "n_ranked": n_ranked,
        "n_with_rationale": n_with_rationale,
        "n_substantive": n_substantive,
        "frac_substantive": n_substantive / n_ranked if n_ranked else 0.0,
        "top1_gene": top1_gene,
        "top1_substantive": top1_substantive,
        "top1_len": top1_len,
        "top1_pmcid_count": top1_pmcids,
        "causal_gene": causal_gene,
        "causal_in_ranking": any(g == causal_gene for g, _ in rationales),
        "causal_substantive": causal_substantive,
        "causal_len": causal_len,
        "causal_pmcid_count": causal_pmcids,
        "median_rationale_len": statistics.median(lengths) if lengths else 0,
        "median_pmcid_per_gene": statistics.median(pmcid_counts) if pmcid_counts else 0,
        "lea_fallback": fallback,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses-dir", type=Path, default=DEFAULT_RESPONSES)
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    # Load overlap for stratified reporting
    overlap = {r["case_id"]: r["overlap"] for r in json.loads(args.overlap.read_text())["records"]}

    records: list[dict] = []
    for path in sorted(args.responses_dir.glob("*.json")):
        try:
            sc = json.loads(path.read_text())
        except json.JSONDecodeError:
            log.warning("Bad JSON: %s", path)
            continue
        rec = analyze_case(sc)
        rec["overlap"] = overlap.get(rec["case_id"])
        records.append(rec)
    log.info("Analysed %d cases", len(records))

    # ---- aggregates
    def agg(subset: list[dict], label: str) -> dict:
        if not subset:
            return {"label": label, "n": 0}
        n = len(subset)
        return {
            "label": label,
            "n": n,
            "frac_lea_fallback": sum(r["lea_fallback"] for r in subset) / n,
            "frac_any_rationale_on_top1": sum(bool(r["top1_len"]) for r in subset) / n,
            "frac_top1_substantive": sum(r["top1_substantive"] for r in subset) / n,
            "frac_causal_in_ranking": sum(r["causal_in_ranking"] for r in subset) / n,
            "frac_causal_substantive": sum(r["causal_substantive"] for r in subset) / n,
            "mean_top1_len": statistics.mean(r["top1_len"] for r in subset),
            "median_top1_len": statistics.median(r["top1_len"] for r in subset),
            "mean_causal_len": statistics.mean(r["causal_len"] for r in subset),
            "mean_pmcid_per_top1": statistics.mean(r["top1_pmcid_count"] for r in subset),
            "mean_pmcid_per_causal": statistics.mean(r["causal_pmcid_count"] for r in subset),
            "frac_top1_has_pmcid": sum(r["top1_pmcid_count"] > 0 for r in subset) / n,
            "frac_causal_has_pmcid": sum(r["causal_pmcid_count"] > 0 for r in subset) / n,
            "mean_n_substantive_per_case": statistics.mean(r["n_substantive"] for r in subset),
            "mean_frac_substantive": statistics.mean(r["frac_substantive"] for r in subset),
        }

    by_cat: dict[str, list[dict]] = defaultdict(list)
    by_overlap: dict[int | None, list[dict]] = defaultdict(list)
    for r in records:
        by_cat[r["category"]].append(r)
        by_overlap[r["overlap"]].append(r)

    summary = {
        "__all__": agg(records, "all"),
        "overlap_present": agg(by_overlap.get(1, []), "overlap_present"),
        "overlap_absent": agg(by_overlap.get(0, []), "overlap_absent"),
        **{f"cat_{k}": agg(v, k) for k, v in sorted(by_cat.items())},
    }

    # ---- write
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "records": records}, indent=2))
    log.info("Wrote %s", args.out)

    # ---- console summary
    print("\n=== LEA rationale quality (Thread G) ===\n")
    print(
        f"  {'subset':<22s} {'n':>5s} {'frc_subst':>10s} {'top1_len':>9s} "
        f"{'top1_PMCs':>10s} {'caus_subst':>11s} {'fallback':>9s}"
    )
    for key in (
        "__all__",
        "overlap_present",
        "overlap_absent",
        "cat_developmental",
        "cat_immunological",
        "cat_metabolic",
        "cat_neurological",
    ):
        s = summary.get(key)
        if not s or s.get("n", 0) == 0:
            continue
        print(
            f"  {key:<22s} {s['n']:>5d} "
            f"{s['mean_frac_substantive']:>10.3f} "
            f"{s['median_top1_len']:>9.0f} "
            f"{s['mean_pmcid_per_top1']:>10.2f} "
            f"{s['frac_causal_substantive']:>11.3f} "
            f"{s['frac_lea_fallback']:>9.3f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
