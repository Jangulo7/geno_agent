"""WP5 --- design-weighted (Horvitz-Thompson) estimates for the eligible pool.

The cohort is a *disproportionate* stratified sample: the four MONDO strata were
drawn at rates from 77% (immunological) down to 8% (neurological) of their
eligible pools. An unweighted cohort mean therefore estimates a quantity defined
by the sampling design, not by the eligible population. P1 releases the inclusion
probabilities precisely so that a design-based estimate can be computed.

This matters substantively here: the eligible pool is 67% neurological
(3,144/4,670), and the overlap-absent neurological result is a near three-way tie,
so the design-weighted margin is expected to be materially smaller than the
unweighted one.

Reports, for every system and every subset, the Horvitz-Thompson weighted top-1
alongside the unweighted and the equal-weight (25% per stratum) figure the
manuscript currently uses, each with a publication-clustered bootstrap CI, plus
the design-weighted paired deltas for the primary contrasts.

Outputs ``reports/p2_revision/wp5_design_weighted.json``. Seed 42.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CATEGORIES,
    CELL_NAMES,
    DESIGN,
    SEED,
    cluster_bootstrap,
    design_weights,
    load_ranks,
    subset,
    write_json,
)

N_BOOT = 10_000
# Estimates are stored at 6 dp, not 3 or 4. render_supp_tables.py formats them
# with ":.3f", so storing at 4 dp rounds twice: a true 0.775549 lands on the
# 4-dp half-boundary 0.7755, and the second round resolves it by float
# representation rather than by value (0.7755 -> 0.775, 0.1915 -> 0.192). Six
# places keep the render the only rounding step.
PRECISION = 6
SYSTEMS = ["K", "M", "D", "L", "S", "N", "O"]
SUBSETS = ["full", "overlap_present", "overlap_absent"]
PRIMARY = [("S", "K"), ("S", "M"), ("S", "O"), ("M", "K")]

W = design_weights()


def top1(cell: str) -> dict[str, int]:
    return {cid: int(r is not None and r <= 1) for cid, r in load_ranks(cell).items()}


def ht_mean(cases, hits) -> float:
    """Horvitz-Thompson weighted mean: sum(w_i y_i) / sum(w_i), w = 1/pi."""
    if not cases:
        return float("nan")
    num = sum(W[c.category] * hits[c.case_id] for c in cases)
    den = sum(W[c.category] for c in cases)
    return float(num / den) if den else float("nan")


def equal_weight_mean(cases, hits) -> float:
    """Equal 25% per stratum --- the manuscript's current sensitivity analysis."""
    parts = []
    for cat in CATEGORIES:
        vals = [hits[c.case_id] for c in cases if c.category == cat]
        if vals:
            parts.append(float(np.mean(vals)))
    return float(np.mean(parts)) if parts else float("nan")


def unweighted_mean(cases, hits) -> float:
    if not cases:
        return float("nan")
    return float(np.mean([hits[c.case_id] for c in cases]))


def main() -> None:
    weights_table = {
        cat: {
            "eligible_pool": DESIGN[cat]["eligible"],
            "analytic_cohort": DESIGN[cat]["analytic"],
            "inclusion_probability": round(DESIGN[cat]["analytic"] / DESIGN[cat]["eligible"], 4),
            "design_weight": round(W[cat], 3),
        }
        for cat in CATEGORIES
    }
    eligible_total = sum(DESIGN[c]["eligible"] for c in CATEGORIES)
    eligible_share = {c: round(DESIGN[c]["eligible"] / eligible_total, 4) for c in CATEGORIES}

    estimates = []
    for cell in SYSTEMS:
        hits = top1(cell)
        for sub in SUBSETS:
            cases = subset(sub)
            comp = {cat: sum(1 for c in cases if c.category == cat) for cat in CATEGORIES}
            ht, lo, hi = cluster_bootstrap(
                cases, lambda cs, _h=hits: ht_mean(cs, _h), n_boot=N_BOOT, seed=SEED
            )
            uw, ulo, uhi = cluster_bootstrap(
                cases,
                lambda cs, _h=hits: unweighted_mean(cs, _h),
                n_boot=N_BOOT,
                seed=SEED,
            )
            estimates.append(
                {
                    "cell": cell,
                    "name": CELL_NAMES[cell],
                    "subset": sub,
                    "n_cases": len(cases),
                    "composition": comp,
                    "unweighted_top1": round(uw, PRECISION),
                    "unweighted_ci95_cluster": [round(ulo, PRECISION), round(uhi, PRECISION)],
                    "equal_weight_top1": round(equal_weight_mean(cases, hits), PRECISION),
                    "design_weighted_top1": round(ht, PRECISION),
                    "design_weighted_ci95_cluster": [round(lo, PRECISION), round(hi, PRECISION)],
                }
            )

    deltas = []
    for a, b in PRIMARY:
        ha, hb = top1(a), top1(b)
        for sub in SUBSETS:
            cases = subset(sub)

            def d_ht(cs, _a=ha, _b=hb):
                return ht_mean(cs, _a) - ht_mean(cs, _b)

            def d_uw(cs, _a=ha, _b=hb):
                return unweighted_mean(cs, _a) - unweighted_mean(cs, _b)

            pt, lo, hi = cluster_bootstrap(cases, d_ht, n_boot=N_BOOT, seed=SEED)
            upt, ulo, uhi = cluster_bootstrap(cases, d_uw, n_boot=N_BOOT, seed=SEED)
            deltas.append(
                {
                    "label": f"{a} vs {b}",
                    "subset": sub,
                    "n_cases": len(cases),
                    "unweighted_delta": round(upt, PRECISION),
                    "unweighted_ci95_cluster": [round(ulo, PRECISION), round(uhi, PRECISION)],
                    "design_weighted_delta": round(pt, PRECISION),
                    "design_weighted_ci95_cluster": [round(lo, PRECISION), round(hi, PRECISION)],
                    "design_weighted_ci_excludes_zero": bool(lo > 0 or hi < 0),
                }
            )

    payload = {
        "work_package": "WP5",
        "description": (
            "Horvitz-Thompson design-weighted top-1 for the eligible pool, using "
            "P1's released inclusion probabilities, with publication-clustered "
            "bootstrap CIs. The unweighted figure describes the sampled cohort; "
            "the weighted figure describes the eligible population."
        ),
        "seed": SEED,
        "n_bootstrap": N_BOOT,
        "bootstrap_unit": "source publication (PMID)",
        "weights": weights_table,
        "eligible_pool_composition": eligible_share,
        "estimates": estimates,
        "paired_deltas": deltas,
    }
    p = write_json("wp5_design_weighted.json", payload)
    print(f"wrote {p}")

    print("\neligible-pool composition:", eligible_share)
    print("\n--- top-1: unweighted / equal-weight / design-weighted ---")
    for e in estimates:
        if e["subset"] != "overlap_absent":
            continue
        print(
            f"  {e['cell']} {e['name']:<24} unw {e['unweighted_top1']:.3f}  "
            f"eq {e['equal_weight_top1']:.3f}  HT {e['design_weighted_top1']:.3f} "
            f"CI {e['design_weighted_ci95_cluster']}"
        )
    print("\n--- design-weighted paired deltas ---")
    for d in deltas:
        print(
            f"  {d['label']:<8} {d['subset']:<16} unw {d['unweighted_delta']:+.4f}  "
            f"HT {d['design_weighted_delta']:+.4f} CI {d['design_weighted_ci95_cluster']}"
            f"  excl0={d['design_weighted_ci_excludes_zero']}"
        )


if __name__ == "__main__":
    main()
