"""Case-clustering statistics for the released cohort (P1 resource paper).

The 1,047 benchmark cases are curated from a much smaller number of source
publications, so cases are clustered within publications and the
``annotation_overlap`` flag --- being a property of the (PMID, disease) pair ---
varies across far fewer independent units than cases. This script quantifies
that clustering for the full cohort and for every stratum the paper recommends
analysing, so the Usage Notes can state the effective sample size instead of
implying that per-case metrics are independent observations.

Inputs (all pinned, released files):

- ``data/test_cases_1050/test_cases.jsonl``
- ``data/test_cases_1050/annotation_overlap.json``
- ``data/test_cases_1050/pmid_dates.json``

Output: ``release/cohort/clustering_stats.json``

The source PMID is parsed from ``case_id``, whose Phenopacket Store convention
encodes the source publication as a ``PMID_<digits>_...`` filename stem, so the
clustering variable requires no additional file.

Run from project root: ``python scripts/eval/compute_clustering_stats.py``
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
COHORT_DIR: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050"
CASES_PATH: Final[Path] = COHORT_DIR / "test_cases.jsonl"
OVERLAP_PATH: Final[Path] = COHORT_DIR / "annotation_overlap.json"
DATES_PATH: Final[Path] = COHORT_DIR / "pmid_dates.json"
OUT_PATH: Final[Path] = PROJECT_ROOT / "release" / "cohort" / "clustering_stats.json"

RECENCY_BOUNDARY: Final[int] = 2020
CATEGORIES: Final[tuple[str, ...]] = (
    "developmental",
    "immunological",
    "metabolic",
    "neurological",
)

_PMID_RE: Final[re.Pattern[str]] = re.compile(r"PMID_(\d+)")


def pmid_of(case_id: str) -> str:
    """Extract the source PMID encoded in a ``case_id``.

    Args:
        case_id: Cohort case identifier, ``"{GENE}:{phenopacket_id}"`` where the
            phenopacket id carries a ``PMID_<digits>_...`` stem.

    Returns:
        The PMID as a digit string.

    Raises:
        ValueError: If the case_id carries no PMID stem, which would mean the
            clustering variable is not recoverable and the analysis is invalid.
    """
    m = _PMID_RE.search(case_id)
    if m is None:
        raise ValueError(f"no PMID stem in case_id: {case_id!r}")
    return m.group(1)


def summarise(pmids: list[str]) -> dict[str, float | int]:
    """Summarise the clustering of a set of cases by their source PMIDs.

    Args:
        pmids: One PMID per case (repeats expected --- that is the clustering).

    Returns:
        Mapping with case count, unique-PMID count, and the median, mean and
        max number of cases contributed by a single publication.
    """
    if not pmids:
        return {
            "n_cases": 0,
            "n_unique_pmids": 0,
            "median_cases_per_pmid": 0,
            "mean_cases_per_pmid": 0.0,
            "max_cases_per_pmid": 0,
        }
    counts = Counter(pmids)
    per_pmid = sorted(counts.values())
    return {
        "n_cases": len(pmids),
        "n_unique_pmids": len(counts),
        "median_cases_per_pmid": statistics.median(per_pmid),
        "mean_cases_per_pmid": round(len(pmids) / len(counts), 4),
        "max_cases_per_pmid": max(per_pmid),
    }


def main() -> int:
    """Compute clustering statistics for every stratum and write the JSON."""
    cases = [json.loads(line) for line in CASES_PATH.read_text().splitlines() if line]
    overlap = {r["case_id"]: r["overlap"] for r in json.loads(OVERLAP_PATH.read_text())["records"]}
    dates = json.loads(DATES_PATH.read_text())["dates"]

    for c in cases:
        c["_pmid"] = pmid_of(c["case_id"])
        c["_overlap"] = overlap[c["case_id"]]
        c["_year"] = int(dates[c["_pmid"]][:4])

    strata: dict[str, list[dict]] = {"full_cohort": cases}
    for cat in CATEGORIES:
        strata[f"category_{cat}"] = [c for c in cases if c["category"] == cat]
    strata["overlap_present"] = [c for c in cases if c["_overlap"] == 1]
    strata["overlap_absent"] = [c for c in cases if c["_overlap"] == 0]
    strata["pre_2020"] = [c for c in cases if c["_year"] < RECENCY_BOUNDARY]
    strata["post_2020"] = [c for c in cases if c["_year"] >= RECENCY_BOUNDARY]
    strata["post_2020_x_overlap_absent"] = [
        c for c in cases if c["_year"] >= RECENCY_BOUNDARY and c["_overlap"] == 0
    ]

    out = {
        "meta": {
            "source_cohort": str(CASES_PATH.relative_to(PROJECT_ROOT)),
            "phenopacket_store_version": "0.1.26",
            "hpoa_version": "v2026-02-16",
            "recency_boundary": f"{RECENCY_BOUNDARY}-01-01",
            "clustering_variable": "source PMID parsed from case_id",
            "note": (
                "Cases sharing a source publication are not independent: they "
                "share a source, frequently a causal gene, and by construction "
                "an annotation-overlap flag."
            ),
        },
        "strata": {k: summarise([c["_pmid"] for c in v]) for k, v in strata.items()},
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")

    for name, stats in out["strata"].items():
        print(
            f"{name:<32} n={stats['n_cases']:>5}  "
            f"pmids={stats['n_unique_pmids']:>4}  "
            f"median={stats['median_cases_per_pmid']}  "
            f"max={stats['max_cases_per_pmid']}"
        )
    print(f"\nwrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
