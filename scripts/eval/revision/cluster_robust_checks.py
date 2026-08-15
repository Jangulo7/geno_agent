"""Publication-level parametric and rank tests for the primary-family contrasts.

The cluster permutation test in `cluster_inference.py` is the manuscript's
inferential statement. Supplementary Table S2 also cites two corroborating
cluster-robust procedures on the same publication-level rates -- a paired t-test
and a Wilcoxon signed-rank test -- and those two numbers previously existed only
as prose in `render_supp_tables.py`, computed once and never persisted. This
script computes them from the per-case artefacts and writes them to
`reports/p2_revision/wp4b_cluster_robust_checks.json`, so every number in that
sentence has a machine-readable source like the rest of the supplement.

Both tests treat the source publication as the unit: each publication contributes
its top-1 rate under each system, and the paired comparison runs over those rates.
Deterministic -- no resampling, hence no seed.

Usage:
    python scripts/eval/revision/cluster_robust_checks.py
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from _common import CELL_NAMES, load_ranks, subset, write_json
from scipy import stats

CONTRASTS = (("S", "K"), ("S", "M"))
SUBSET = "overlap_absent"


def publication_rates(cell: str, cases) -> tuple[list[str], np.ndarray]:
    """Top-1 rate per source publication for one system."""
    ranks = load_ranks(cell)
    hits: dict[str, list[int]] = defaultdict(list)
    for c in cases:
        r = ranks.get(c.case_id)
        hits[c.source_pmid].append(1 if r == 1 else 0)
    pubs = sorted(hits)
    return pubs, np.array([float(np.mean(hits[p])) for p in pubs])


def main() -> None:
    cases = subset(SUBSET)
    results = []
    for a, b in CONTRASTS:
        pubs, ra = publication_rates(a, cases)
        _, rb = publication_rates(b, cases)
        diff = ra - rb
        t = stats.ttest_rel(ra, rb)
        discordant = int(np.count_nonzero(diff))
        w = stats.wilcoxon(ra, rb) if discordant else None
        results.append(
            {
                "contrast": f"{a} vs {b}",
                "comparator": CELL_NAMES[b],
                "subset": SUBSET,
                "n_cases": len(cases),
                "n_publications": len(pubs),
                "publication_mean_rate_a": round(float(ra.mean()), 4),
                "publication_mean_rate_b": round(float(rb.mean()), 4),
                "publication_mean_difference": round(float(diff.mean()), 4),
                "n_publications_discordant": discordant,
                "paired_t_statistic": round(float(t.statistic), 4),
                "paired_t_p": round(float(t.pvalue), 4),
                "wilcoxon_statistic": round(float(w.statistic), 1) if w else None,
                "wilcoxon_p": round(float(w.pvalue), 4) if w else None,
            }
        )
        print(
            f"{a} vs {b} ({SUBSET}): {len(pubs)} publications, "
            f"mean rate {ra.mean():.4f} vs {rb.mean():.4f}, "
            f"paired t p={t.pvalue:.4f}" + (f", Wilcoxon p={w.pvalue:.4f}" if w else "")
        )

    path = write_json(
        "wp4b_cluster_robust_checks.json",
        {
            "work_package": "WP4b",
            "description": (
                "Publication-level paired t-test and Wilcoxon signed-rank test for the "
                "primary-family contrasts on the overlap-absent subset. The unit is the "
                "source publication: each contributes its top-1 rate under each system. "
                "Corroborates the cluster permutation test in wp4_cluster_inference.json."
            ),
            "unit": "source publication (PMID)",
            "results": results,
        },
    )
    print(f"wrote {path.relative_to(path.parents[2])}")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
