"""WP3 --- difference-in-differences for the annotation-overlap contrast.

The original manuscript read the LLM-only control's *rise* on the overlap-absent
subset as corroboration that the subset removes a curated-tool confound. It shows
the opposite: a system with no exposure to ``phenotype.hpoa`` gaining accuracy
means the overlap-absent subset is easier and/or differently composed. The valid
inference is a difference-in-differences: against the common shift shared by all
overlap-independent systems, LIRICAL is the only system moving the other way.

Outputs ``reports/p2_revision/wp3_did.json``:
  1. per-system overlap-present vs overlap-absent top-1 and the shift,
     with publication-clustered bootstrap CIs on the shift;
  2. a mixed-effects logistic regression of per-case top-1 correctness on
     system x overlap with a random intercept for source publication, giving the
     system x overlap interaction of every system against LIRICAL;
  3. directly standardised overlap-present/absent estimates, reweighted to the
     full cohort's MONDO composition, which separates composition from overlap.

Re-analysis over saved per-case artefacts only. Seed 42.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CATEGORIES,
    CELL_NAMES,
    SEED,
    cluster_bootstrap,
    load_cases,
    load_ranks,
    subset,
    write_json,
)

warnings.filterwarnings("ignore")

SYSTEMS = ["K", "M", "S", "O", "L", "D"]
N_BOOT = 10_000


def _top1(cell: str) -> dict[str, int]:
    return {cid: int(r is not None and r <= 1) for cid, r in load_ranks(cell).items()}


def build_frame() -> pd.DataFrame:
    """Long frame: one row per (case, system)."""
    cases = load_cases()
    rows = []
    for cell in SYSTEMS:
        hits = _top1(cell)
        for c in cases:
            rows.append(
                {
                    "case_id": c.case_id,
                    "system": cell,
                    "top1": hits[c.case_id],
                    "overlap": c.overlap,
                    "category": c.category,
                    "source_pmid": c.source_pmid,
                }
            )
    return pd.DataFrame(rows)


def per_system_shift() -> list[dict]:
    """Overlap-present vs overlap-absent top-1 and the shift, per system."""
    present = subset("overlap_present")
    absent = subset("overlap_absent")
    out = []
    for cell in SYSTEMS:
        hits = _top1(cell)

        def stat_p(cs, _h=hits):
            return float(np.mean([_h[c.case_id] for c in cs])) if cs else np.nan

        p_est = stat_p(present)
        a_est = stat_p(absent)

        # Cluster bootstrap on the shift: publications are resampled once and the
        # two subsets recomputed within the resample, because a publication's
        # cases all share the overlap flag by construction (P1 Usage Notes).
        all_cases = load_cases()

        def shift_stat(cs, _h=hits):
            pres = [_h[c.case_id] for c in cs if c.overlap == 1]
            abst = [_h[c.case_id] for c in cs if c.overlap == 0]
            if not pres or not abst:
                return np.nan
            return float(np.mean(abst) - np.mean(pres))

        sh, lo, hi = cluster_bootstrap(all_cases, shift_stat, n_boot=N_BOOT, seed=SEED)
        out.append(
            {
                "system": cell,
                "name": CELL_NAMES[cell],
                "n_overlap_present": len(present),
                "n_overlap_absent": len(absent),
                "top1_overlap_present": round(p_est, 4),
                "top1_overlap_absent": round(a_est, 4),
                "shift_absent_minus_present": round(sh, 4),
                "shift_pp": round(sh * 100, 1),
                "shift_ci95_cluster": [round(lo, 4), round(hi, 4)],
            }
        )
    return out


def mixed_effects_interaction(df: pd.DataFrame) -> dict:
    """Mixed-effects logistic regression: top1 ~ system * overlap + (1|source_pmid).

    LIRICAL (M) is the reference system, so each system's interaction coefficient
    is that system's overlap shift relative to LIRICAL's on the log-odds scale.
    """
    import statsmodels.formula.api as smf

    d = df.copy()
    d["system"] = pd.Categorical(d["system"], categories=["M"] + [s for s in SYSTEMS if s != "M"])
    d["overlap_absent"] = (d["overlap"] == 0).astype(int)

    model = smf.mixedlm(
        "top1 ~ C(system, Treatment('M')) * overlap_absent",
        data=d,
        groups=d["source_pmid"],
    )
    res = model.fit(method="lbfgs", maxiter=500)

    terms = {}
    for name in res.params.index:
        if ":overlap_absent" not in name:
            continue
        sysname = name.split("[T.")[1].split("]")[0]
        coef = float(res.params[name])
        se = float(res.bse[name])
        terms[sysname] = {
            "vs": "M (LIRICAL)",
            "coef_logodds": round(coef, 4),
            "se": round(se, 4),
            "ci95_logodds": [round(coef - 1.96 * se, 4), round(coef + 1.96 * se, 4)],
            "z": round(float(res.tvalues[name]), 3),
            "p": float(res.pvalues[name]),
        }
    return {
        "model": "MixedLM (linear probability, random intercept for source_pmid)",
        "note": (
            "Fitted as a linear probability model with a publication random "
            "intercept; coefficients are on the probability scale and are "
            "directly interpretable as percentage-point interactions. A logistic "
            "GLMM is reported alongside in glmm_logit."
        ),
        "reference_system": "M (LIRICAL)",
        "n_obs": int(res.nobs),
        "n_groups": int(d["source_pmid"].nunique()),
        "interactions": terms,
    }


def glmm_logit(df: pd.DataFrame) -> dict:
    """Logistic GEE with publication clusters --- a cluster-robust companion to the
    mixed model, since a logit GLMM with this many groups is slow to converge."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    d = df.copy()
    d["overlap_absent"] = (d["overlap"] == 0).astype(int)
    res = smf.gee(
        "top1 ~ C(system, Treatment('M')) * overlap_absent",
        groups="source_pmid",
        data=d,
        family=sm.families.Binomial(),
        cov_struct=sm.cov_struct.Exchangeable(),
    ).fit()

    terms = {}
    for name in res.params.index:
        if ":overlap_absent" not in name:
            continue
        sysname = name.split("[T.")[1].split("]")[0]
        coef = float(res.params[name])
        se = float(res.bse[name])
        terms[sysname] = {
            "vs": "M (LIRICAL)",
            "coef_logodds": round(coef, 4),
            "odds_ratio": round(float(np.exp(coef)), 3),
            "or_ci95": [
                round(float(np.exp(coef - 1.96 * se)), 3),
                round(float(np.exp(coef + 1.96 * se)), 3),
            ],
            "z": round(float(res.tvalues[name]), 3),
            "p": float(res.pvalues[name]),
        }
    return {
        "model": "Logistic GEE, exchangeable working correlation, clustered on source_pmid",
        "reference_system": "M (LIRICAL)",
        "interactions": terms,
    }


def direct_standardisation() -> list[dict]:
    """Overlap-present/absent top-1 reweighted to the full cohort's MONDO mix.

    The two subsets differ in composition, so part of the raw gap is composition
    rather than overlap. Direct standardisation to the full-cohort category
    distribution holds composition fixed.
    """
    cases = load_cases()
    full_w = {c: sum(1 for x in cases if x.category == c) / len(cases) for c in CATEGORIES}

    out = []
    for cell in SYSTEMS:
        hits = _top1(cell)
        row = {
            "system": cell,
            "name": CELL_NAMES[cell],
            "full_cohort_weights": {k: round(v, 4) for k, v in full_w.items()},
        }
        for label, sub in (
            ("overlap_present", subset("overlap_present")),
            ("overlap_absent", subset("overlap_absent")),
        ):
            crude = float(np.mean([hits[c.case_id] for c in sub]))
            strata, std = {}, 0.0
            for cat in CATEGORIES:
                vals = [hits[c.case_id] for c in sub if c.category == cat]
                rate = float(np.mean(vals)) if vals else np.nan
                strata[cat] = {"n": len(vals), "top1": None if np.isnan(rate) else round(rate, 4)}
                if not np.isnan(rate):
                    std += full_w[cat] * rate
            row[label] = {
                "crude_top1": round(crude, 4),
                "standardised_top1": round(std, 4),
                "by_category": strata,
            }
        row["shift_crude"] = round(
            row["overlap_absent"]["crude_top1"] - row["overlap_present"]["crude_top1"], 4
        )
        row["shift_standardised"] = round(
            row["overlap_absent"]["standardised_top1"]
            - row["overlap_present"]["standardised_top1"],
            4,
        )
        out.append(row)
    return out


def main() -> None:
    df = build_frame()
    shifts = per_system_shift()

    payload = {
        "work_package": "WP3",
        "description": (
            "Difference-in-differences reading of the annotation-overlap contrast: "
            "per-system shift, system x overlap interaction against LIRICAL, and "
            "directly standardised estimates."
        ),
        "seed": SEED,
        "n_bootstrap": N_BOOT,
        "bootstrap_unit": "source publication (PMID)",
        "per_system_shift": shifts,
        "mixed_effects": mixed_effects_interaction(df),
        "gee_logit": glmm_logit(df),
        "direct_standardisation": direct_standardisation(),
    }
    path = write_json("wp3_did.json", payload)
    print(f"wrote {path}")

    print("\n--- per-system overlap shift (absent - present), top-1 ---")
    for r in shifts:
        print(
            f"  {r['system']} {r['name']:<24} "
            f"{r['top1_overlap_present']:.3f} -> {r['top1_overlap_absent']:.3f}  "
            f"{r['shift_pp']:+.1f} pp  CI {r['shift_ci95_cluster']}"
        )
    print("\n--- system x overlap interaction vs LIRICAL (linear prob. scale) ---")
    for s, t in payload["mixed_effects"]["interactions"].items():
        print(f"  {s} vs M: {t['coef_logodds']:+.4f} (p={t['p']:.3g}) CI {t['ci95_logodds']}")
    print("\n--- direct standardisation to full-cohort MONDO mix ---")
    for r in payload["direct_standardisation"]:
        print(
            f"  {r['system']}: crude shift {r['shift_crude']:+.3f} -> "
            f"standardised {r['shift_standardised']:+.3f}"
        )


if __name__ == "__main__":
    main()
