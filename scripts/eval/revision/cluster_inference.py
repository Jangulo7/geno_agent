"""WP4 --- publication-clustered inference for every interval and paired test.

The n=1,047 cases derive from 415 publications (mean 2.5, max 42 per paper).
Cases from one publication share a source, frequently a causal gene, and by
construction the annotation-overlap flag, so case-level bootstrap intervals and
case-level McNemar tests understate variance. P1's Usage Notes recommend
clustering on source PMID; this script implements that recommendation and
reports the case-level result alongside it for transparency.

Two cluster-robust devices are used:

  * a **cluster bootstrap** (resample the 415 publications with replacement,
    retain all their cases; 10,000 resamples, seed 42) for every point estimate
    and every paired delta that currently carries a CI; and

  * a **cluster-level permutation test** on the paired discordance indicator, in
    place of case-level McNemar. Under the null the sign of a discordance is
    exchangeable, but discordances within a publication are not independent, so
    signs are flipped a whole publication at a time.

**Provenance of the clustering variable.** ``source_pmid`` comes from the curated
``annotation_overlap.json`` layer (via ``_common.load_cases``), **not** from parsing
the ``case_id``. For this cohort the two agree on all 1,047 cases (both yield 415
publications), because every id carries an explicit ``PMID_<digits>`` stem first --
including the 35 ``STXBP1:PMID_35190816_STX_<subject>_...`` cases, whose second
number is an internal subject identifier rather than a PMID. Do not generalise the
id-parsing shortcut to another cohort without checking its identifier convention: a
sibling cohort whose ids read ``STX_<subject>`` with no PMID stem would split that
single publication into hundreds of pseudo-independent clusters, which is precisely
the error this module exists to prevent. Prefer the curated field.

Outputs ``reports/p2_revision/wp4_cluster_inference.json`` and
``reports/p2_revision/wp4_unique_pmids.json``.

Re-analysis over saved per-case artefacts only. Seed 42.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CELL_NAMES,
    SEED,
    Case,
    case_bootstrap,
    cluster_bootstrap,
    load_cases,
    load_ranks,
    subset,
    write_json,
)

# 6 dp, not 4: renderers format these at 3 dp, and a 4-dp store puts the S-vs-O
# overlap-absent delta (54/282 = 0.191489) on the half-boundary 0.1915, where the
# display round resolves it to +0.192 instead of the +0.191 the paper reports.
PRECISION = 6

N_BOOT = 10_000
N_PERM = 10_000

# Every contrast the manuscript reports with a CI or a p-value.
CONTRASTS = [
    # (cohort, subset, system_a, system_b, family)
    ("standard", "overlap_absent", "S", "K", "primary"),
    ("standard", "overlap_absent", "S", "M", "primary"),
    ("standard", "overlap_absent", "S", "L", "mechanistic"),
    ("standard", "overlap_absent", "S", "O", "mechanistic"),
    ("standard", "overlap_absent", "M", "K", "descriptive"),
    ("standard", "overlap_absent", "S", "N", "descriptive"),
    ("standard", "full", "S", "K", "supportive"),
    ("standard", "full", "S", "O", "mechanistic"),
    ("standard", "full", "L", "D", "mechanistic"),
    ("standard", "full", "S", "L", "mechanistic"),
    ("standard", "post2020", "S", "K", "supportive"),
    ("standard", "pre2020", "S", "K", "descriptive"),
    ("standard", "post2020_overlap_absent", "S", "M", "qualitative_probe"),
    ("hard", "overlap_absent", "S", "K", "supportive_hard"),
    ("hard", "overlap_absent", "S", "M", "supportive_hard"),
]

POINT_CELLS = ["K", "M", "D", "L", "S", "N", "O"]
POINT_SUBSETS = [
    "full",
    "overlap_present",
    "overlap_absent",
    "pre2020",
    "post2020",
    "post2020_overlap_absent",
]


def top1_map(cell: str, cohort: str) -> dict[str, int]:
    return {cid: int(r is not None and r <= 1) for cid, r in load_ranks(cell, cohort).items()}


# --------------------------------------------------------------------------
# Cluster-level permutation test on the paired discordance indicator
# --------------------------------------------------------------------------


def cluster_permutation_paired(
    cases: list[Case],
    hits_a: dict[str, int],
    hits_b: dict[str, int],
    n_perm: int = N_PERM,
    seed: int = SEED,
) -> dict:
    """Two-sided cluster-robust paired test for a difference in top-1 rates.

    Per case d_i = a_i - b_i in {-1, 0, +1}. The observed statistic is the mean
    of d over cases. Under the null of exchangeable outcomes within a case, the
    sign of d is free; because cases within a publication are dependent, the sign
    is flipped for a whole publication at a time.
    """
    rng = np.random.default_rng(seed)
    ids = [c.case_id for c in cases]
    d = np.array([hits_a[i] - hits_b[i] for i in ids], dtype=float)
    obs = float(d.mean())

    pmids = np.array([c.source_pmid for c in cases])
    uniq, inverse = np.unique(pmids, return_inverse=True)
    n_clusters = len(uniq)

    count = 0
    for _ in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=n_clusters)
        if abs(float((d * signs[inverse]).mean())) >= abs(obs) - 1e-15:
            count += 1
    p = (count + 1) / (n_perm + 1)

    n_disc_a = int((d > 0).sum())
    n_disc_b = int((d < 0).sum())
    return {
        "delta": round(obs, PRECISION),
        "n_discordant_a_wins": n_disc_a,
        "n_discordant_b_wins": n_disc_b,
        "n_clusters": int(n_clusters),
        "p_cluster_permutation": round(p, 5),
        "n_permutations": n_perm,
    }


def mcnemar_exact(hits_a: dict[str, int], hits_b: dict[str, int], ids) -> dict:
    """Case-level exact McNemar, i.e. what the original analysis reported."""
    b = sum(1 for i in ids if hits_a[i] == 1 and hits_b[i] == 0)
    c = sum(1 for i in ids if hits_a[i] == 0 and hits_b[i] == 1)
    p = 1.0 if b + c == 0 else float(min(1.0, 2 * stats.binom.cdf(min(b, c), b + c, 0.5)))
    return {"b": b, "c": c, "p_mcnemar_exact_case_level": round(p, 6)}


def run_contrast(cohort: str, sub: str, a: str, b: str, family: str) -> dict:
    cases = subset(sub)
    ids = [c.case_id for c in cases]
    ha, hb = top1_map(a, cohort), top1_map(b, cohort)

    def delta(cs):
        if not cs:
            return np.nan
        return float(np.mean([ha[c.case_id] - hb[c.case_id] for c in cs]))

    d_pt, d_lo, d_hi = cluster_bootstrap(cases, delta, n_boot=N_BOOT, seed=SEED)
    _, dc_lo, dc_hi = case_bootstrap(cases, delta, n_boot=N_BOOT, seed=SEED)

    perm = cluster_permutation_paired(cases, ha, hb)
    mcn = mcnemar_exact(ha, hb, ids)

    return {
        "cohort": cohort,
        "subset": sub,
        "family": family,
        "system_a": a,
        "system_b": b,
        "label": f"{a} vs {b}",
        "n_cases": len(cases),
        "n_publications": len({c.source_pmid for c in cases}),
        "top1_a": round(float(np.mean([ha[i] for i in ids])), PRECISION),
        "top1_b": round(float(np.mean([hb[i] for i in ids])), PRECISION),
        "n_correct_a": int(sum(ha[i] for i in ids)),
        "n_correct_b": int(sum(hb[i] for i in ids)),
        "delta": round(d_pt, PRECISION),
        "ci95_cluster_bootstrap": [round(d_lo, PRECISION), round(d_hi, PRECISION)],
        "ci95_case_bootstrap": [round(dc_lo, PRECISION), round(dc_hi, PRECISION)],
        **mcn,
        "p_cluster_permutation": perm["p_cluster_permutation"],
        "n_discordant_a_wins": perm["n_discordant_a_wins"],
        "n_discordant_b_wins": perm["n_discordant_b_wins"],
        "significant_case_level_0.05": mcn["p_mcnemar_exact_case_level"] < 0.05,
        "significant_cluster_0.05": perm["p_cluster_permutation"] < 0.05,
    }


def point_estimates() -> list[dict]:
    out = []
    for cohort in ("standard", "hard"):
        for cell in POINT_CELLS:
            try:
                hits = top1_map(cell, cohort)
            except FileNotFoundError:
                continue  # Cell O was never run on the hard cohort
            for sub in POINT_SUBSETS:
                cases = subset(sub)

                def stat(cs, _h=hits):
                    return float(np.mean([_h[c.case_id] for c in cs])) if cs else np.nan

                pt, lo, hi = cluster_bootstrap(cases, stat, n_boot=N_BOOT, seed=SEED)
                _, clo, chi = case_bootstrap(cases, stat, n_boot=N_BOOT, seed=SEED)
                out.append(
                    {
                        "cohort": cohort,
                        "cell": cell,
                        "name": CELL_NAMES[cell],
                        "subset": sub,
                        "n_cases": len(cases),
                        "n_publications": len({c.source_pmid for c in cases}),
                        "top1": round(pt, PRECISION),
                        "n_correct": int(sum(hits[c.case_id] for c in cases)),
                        "ci95_cluster_bootstrap": [round(lo, PRECISION), round(hi, PRECISION)],
                        "ci95_case_bootstrap": [round(clo, PRECISION), round(chi, PRECISION)],
                    }
                )
    return out


def unique_pmids() -> dict:
    """WP4-B --- unique publications behind every analysis cell."""
    cases = load_cases()
    out = {}
    for sub in POINT_SUBSETS:
        cs = subset(sub)
        by = {}
        for c in cs:
            by.setdefault(c.source_pmid, 0)
            by[c.source_pmid] += 1
        counts = sorted(by.values(), reverse=True)
        out[sub] = {
            "n_cases": len(cs),
            "n_publications": len(by),
            "mean_cases_per_publication": round(len(cs) / len(by), 3) if by else None,
            "median_cases_per_publication": int(np.median(counts)) if counts else None,
            "max_cases_from_one_publication": counts[0] if counts else None,
            "largest_publication_share": (round(counts[0] / len(cs), 3) if counts else None),
        }
    out["_meta"] = {
        "cohort_n": len(cases),
        "note": (
            "The crossed post-2020 x overlap-absent cell is the smallest and most "
            "strongly clustered unit in the resource and should be read as a "
            "qualitative probe, not a powered comparison (P1 Usage Notes)."
        ),
    }
    return out


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adj, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        val = min(1.0, (m - i) * p)
        running = max(running, val)
        adj[k] = round(running, 5)
    return adj


def benjamini_hochberg(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adj, prev = {}, 1.0
    for i in range(m - 1, -1, -1):
        k, p = items[i]
        val = min(prev, p * m / (i + 1))
        adj[k] = round(val, 5)
        prev = val
    return adj


def main() -> None:
    contrasts = [run_contrast(*c) for c in CONTRASTS]

    # Multiplicity: the primary family is the two overlap-absent curated-baseline
    # contrasts specified in the analysis plan before the stratification was run.
    # The hard-cohort contrasts are a separately corrected supportive family.
    fams: dict[str, dict[str, float]] = {}
    for c in contrasts:
        if c["family"] in ("primary", "supportive", "supportive_hard"):
            fams.setdefault(c["family"], {})[f"{c['cohort']}/{c['subset']}/{c['label']}"] = c[
                "p_cluster_permutation"
            ]

    correction = {}
    for fam, ps in fams.items():
        correction[fam] = {
            "tests": ps,
            "holm_adjusted": holm(ps),
            "benjamini_hochberg_adjusted": benjamini_hochberg(ps),
            "basis": "cluster-permutation p-values",
        }

    payload = {
        "work_package": "WP4",
        "description": (
            "Publication-clustered intervals and paired tests for every contrast "
            "the manuscript reports, with the case-level result retained alongside."
        ),
        "seed": SEED,
        "n_bootstrap": N_BOOT,
        "n_permutations": N_PERM,
        "clustering_variable": (
            "source PMID from the curated annotation_overlap.json 'source_pmid' field "
            "(via _common.load_cases), NOT parsed from the case_id"
        ),
        "rationale": (
            "P1 Usage Notes, 'Clustered cases': 1,047 cases from 415 publications; "
            "confidence intervals and significance tests should cluster on source PMID."
        ),
        "families": {
            "primary": (
                "Top-1 superiority of Cell S over Exomiser (K) and over LIRICAL (M) "
                "on the overlap-absent subset --- the two contrasts fixed in the "
                "version-controlled analysis plan (paper_extension_plan_v3.md "
                "section 3b, commit 8ebf6f4, 2026-05-17) before the overlap flag was "
                "computed (commit 308fb2e, 2026-05-23)."
            ),
            "supportive": "Full-cohort and post-2020 S-vs-Exomiser, corrected separately.",
            "supportive_hard": (
                "Hard-cohort overlap-absent S-vs-K and S-vs-M. The hard variant was "
                "built on 2026-06-28 (commit 8b8f76a), after the primary family was "
                "fixed, so it is a supportive family corrected separately."
            ),
        },
        "contrasts": contrasts,
        "multiplicity": correction,
        "point_estimates": point_estimates(),
    }
    p = write_json("wp4_cluster_inference.json", payload)
    print(f"wrote {p}")
    write_json("wp4_unique_pmids.json", unique_pmids())

    print(
        "\n{:<38} {:>6} {:>6} {:>8} {:>22} {:>10} {:>10}".format(
            "contrast", "n", "npub", "delta", "cluster CI", "p_case", "p_cluster"
        )
    )
    for c in contrasts:
        print(
            "{:<38} {:>6} {:>6} {:>+8.4f} {:>22} {:>10.4g} {:>10.4g}".format(
                f"{c['cohort']}/{c['subset']}/{c['label']}",
                c["n_cases"],
                c["n_publications"],
                c["delta"],
                f"[{c['ci95_cluster_bootstrap'][0]:+.3f},{c['ci95_cluster_bootstrap'][1]:+.3f}]",
                c["p_mcnemar_exact_case_level"],
                c["p_cluster_permutation"],
            )
        )

    print("\n--- multiplicity (cluster p-values) ---")
    for fam, d in correction.items():
        print(f"  [{fam}]")
        for k, v in d["holm_adjusted"].items():
            print(f"    {k:<44} raw={d['tests'][k]:.4g}  holm={v:.4g}")


if __name__ == "__main__":
    main()
