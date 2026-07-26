"""WP6 --- does annotation density explain the overlap effect?

A case is flagged overlap-present precisely when its disease is well enough
curated for its source paper to have been read into ``phenotype.hpoa``. So
overlap-present is confounded with *richly annotated disease*, and LIRICAL
performing better on richly annotated diseases is partly expected competence
rather than exposure to the benchmark case itself. This is the strongest
available objection to reading the whole overlap gap as leakage, and it is
testable from the pinned annotation file.

For each case we count the ``phenotype.hpoa`` v2026-02-16 annotation rows for its
OMIM disease(s) **excluding every row whose reference field cites the case's own
source PMID**. Excluding the case's own paper is what makes the covariate a
measure of curation depth independent of the exposure being tested.

Then, per system:
  (a) a mixed-effects model of per-case top-1 on overlap status adjusted for
      log annotation density, with a random intercept for source publication; and
  (b) a density-stratified (quintile) comparison as a non-parametric check that
      does not assume a functional form.

Either outcome is publishable: if LIRICAL's drop persists after adjustment,
exposure is implicated; if it attenuates substantially, curation depth explains
part of it and the manuscript says so.

Outputs ``reports/p2_revision/wp6_annotation_density.json``. Seed 42.
"""

from __future__ import annotations

import csv
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CELL_NAMES,
    REPO,
    SEED,
    load_cases,
    load_ranks,
    write_json,
)

warnings.filterwarnings("ignore")

HPOA = REPO / "data" / "Human_Phenotype_Ontology" / "phenotype.hpoa"
SYSTEMS = ["M", "K", "S", "O"]
N_QUINTILES = 5


def parse_hpoa() -> tuple[dict[str, list[set[str]]], str]:
    """disease_id -> list of per-row reference PMID sets, plus the file version."""
    rows: dict[str, list[set[str]]] = defaultdict(list)
    version = "unknown"
    with HPOA.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                if line.startswith("#version:"):
                    version = line.split(":", 1)[1].strip()
                continue
            break
        fh.seek(0)
        reader = csv.DictReader((ln for ln in fh if not ln.startswith("#")), delimiter="\t")
        for rec in reader:
            did = (rec.get("database_id") or "").strip()
            if not did:
                continue
            refs = {
                r.strip().removeprefix("PMID:")
                for r in (rec.get("reference") or "").split(";")
                if r.strip().startswith("PMID:")
            }
            rows[did].append(refs)
    return rows, version


def build_density() -> tuple[pd.DataFrame, str]:
    hpoa, version = parse_hpoa()
    cases = load_cases()

    recs = []
    for c in cases:
        total = 0
        own = 0
        for did in c.omim_ids:
            for refs in hpoa.get(did, []):
                total += 1
                if c.source_pmid in refs:
                    own += 1
        recs.append(
            {
                "case_id": c.case_id,
                "category": c.category,
                "source_pmid": c.source_pmid,
                "overlap": c.overlap,
                "rows_total": total,
                "rows_own_pmid": own,
                # annotation_density excludes the case's own source publication
                "annotation_density": total - own,
            }
        )
    df = pd.DataFrame(recs)
    df["log_density"] = np.log1p(df["annotation_density"])
    return df, version


def density_by_stratum(df: pd.DataFrame) -> dict:
    out = {}
    for label, mask in (
        ("overlap_present", df["overlap"] == 1),
        ("overlap_absent", df["overlap"] == 0),
    ):
        d = df.loc[mask, "annotation_density"]
        out[label] = {
            "n": len(d),
            "mean": round(float(d.mean()), 2),
            "median": float(d.median()),
            "q25": float(d.quantile(0.25)),
            "q75": float(d.quantile(0.75)),
            "zero_density_cases": int((d == 0).sum()),
        }
    from scipy import stats

    u = stats.mannwhitneyu(
        df.loc[df["overlap"] == 1, "annotation_density"],
        df.loc[df["overlap"] == 0, "annotation_density"],
        alternative="two-sided",
    )
    out["mann_whitney_u"] = {"U": float(u.statistic), "p": float(u.pvalue)}
    return out


def adjusted_models(df: pd.DataFrame) -> list[dict]:
    """top1 ~ overlap_absent [+ log_density], clustered on source_pmid.

    Fitted as a linear-probability GEE with an exchangeable working correlation
    and cluster-robust standard errors. A mixed model was tried first but is
    numerically degenerate for LIRICAL, whose overlap-present rate is 0.978, so
    within-publication variance is near zero and the random-intercept variance sits
    on the boundary. GEE is stable in that regime and its coefficients remain
    directly interpretable as percentage points.
    """
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    def fit(formula, d):
        return smf.gee(
            formula,
            groups="source_pmid",
            data=d,
            family=sm.families.Gaussian(),
            cov_struct=sm.cov_struct.Exchangeable(),
        ).fit()

    results = []
    for cell in SYSTEMS:
        hits = {cid: int(r is not None and r <= 1) for cid, r in load_ranks(cell).items()}
        d = df.copy()
        d["top1"] = d["case_id"].map(hits)
        d["overlap_absent"] = (d["overlap"] == 0).astype(int)

        crude = fit("top1 ~ overlap_absent", d)
        adj = fit("top1 ~ overlap_absent + log_density", d)

        c_coef = float(crude.params["overlap_absent"])
        a_coef = float(adj.params["overlap_absent"])
        attenuation = round(100 * (1 - a_coef / c_coef), 1) if abs(c_coef) > 1e-9 else None
        results.append(
            {
                "cell": cell,
                "name": CELL_NAMES[cell],
                "model": "linear-probability GEE, exchangeable, clustered on source_pmid",
                "crude_overlap_effect": round(c_coef, 4),
                "crude_se": round(float(crude.bse["overlap_absent"]), 4),
                "crude_p": float(crude.pvalues["overlap_absent"]),
                "adjusted_overlap_effect": round(a_coef, 4),
                "adjusted_se": round(float(adj.bse["overlap_absent"]), 4),
                "adjusted_p": float(adj.pvalues["overlap_absent"]),
                "log_density_coef": round(float(adj.params["log_density"]), 4),
                "log_density_p": float(adj.pvalues["log_density"]),
                "percent_attenuation": attenuation,
            }
        )
    return results


def adjusted_interaction(df: pd.DataFrame) -> dict:
    """Does the system x overlap interaction survive adjustment for density?

    This is the quantity the manuscript actually rests on: not whether each system
    shifts, but whether LIRICAL shifts *differently* from systems that never read
    ``phenotype.hpoa``. Annotation density is a property of the case, not of the
    system, so it cannot by itself produce a system-specific interaction --- but
    the check is worth reporting explicitly because a reviewer will ask.
    """
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    rows = []
    for cell in SYSTEMS:
        hits = {cid: int(r is not None and r <= 1) for cid, r in load_ranks(cell).items()}
        d = df.copy()
        d["system"] = cell
        d["top1"] = d["case_id"].map(hits)
        rows.append(d)
    long = pd.concat(rows, ignore_index=True)
    long["overlap_absent"] = (long["overlap"] == 0).astype(int)

    def fit(formula):
        return smf.gee(
            formula,
            groups="source_pmid",
            data=long,
            family=sm.families.Gaussian(),
            cov_struct=sm.cov_struct.Exchangeable(),
        ).fit()

    crude = fit("top1 ~ C(system, Treatment('M')) * overlap_absent")
    adj = fit(
        "top1 ~ C(system, Treatment('M')) * overlap_absent "
        "+ log_density + C(system, Treatment('M')):log_density"
    )

    def terms(res):
        out = {}
        for name in res.params.index:
            if ":overlap_absent" not in name:
                continue
            s = name.split("[T.")[1].split("]")[0]
            coef, se = float(res.params[name]), float(res.bse[name])
            out[s] = {
                "coef": round(coef, 4),
                "se": round(se, 4),
                "ci95": [round(coef - 1.96 * se, 4), round(coef + 1.96 * se, 4)],
                "p": float(res.pvalues[name]),
            }
        return out

    return {
        "model": "linear-probability GEE, clustered on source_pmid",
        "reference_system": "M (LIRICAL)",
        "note": (
            "Coefficients are the system's overlap shift relative to LIRICAL's, in "
            "percentage points. 'adjusted' additionally controls annotation density "
            "and lets its slope differ by system."
        ),
        "crude_interaction": terms(crude),
        "density_adjusted_interaction": terms(adj),
    }


def density_stratified(df: pd.DataFrame) -> list[dict]:
    """Non-parametric check: overlap effect within annotation-density quintiles."""
    d = df.copy()
    # Quintiles of density among cases that have any annotation at all; rank-based
    # so ties do not collapse the bins.
    d["quintile"] = pd.qcut(d["annotation_density"].rank(method="first"), N_QUINTILES, labels=False)

    out = []
    for cell in SYSTEMS:
        hits = {cid: int(r is not None and r <= 1) for cid, r in load_ranks(cell).items()}
        d["top1"] = d["case_id"].map(hits)
        bins, diffs, weights = [], [], []
        for q in range(N_QUINTILES):
            sub = d[d["quintile"] == q]
            pres = sub[sub["overlap"] == 1]["top1"]
            abst = sub[sub["overlap"] == 0]["top1"]
            rec = {
                "quintile": q + 1,
                "density_range": [
                    float(sub["annotation_density"].min()),
                    float(sub["annotation_density"].max()),
                ],
                "n_present": len(pres),
                "n_absent": len(abst),
                "top1_present": round(float(pres.mean()), 4) if len(pres) else None,
                "top1_absent": round(float(abst.mean()), 4) if len(abst) else None,
            }
            if len(pres) and len(abst):
                diff = float(abst.mean() - pres.mean())
                rec["shift_absent_minus_present"] = round(diff, 4)
                diffs.append(diff)
                weights.append(len(sub))
            bins.append(rec)
        pooled = round(float(np.average(diffs, weights=weights)), 4) if diffs else None
        crude = None
        if len(d):
            crude = round(
                float(d[d["overlap"] == 0]["top1"].mean() - d[d["overlap"] == 1]["top1"].mean()),
                4,
            )
        out.append(
            {
                "cell": cell,
                "name": CELL_NAMES[cell],
                "crude_shift": crude,
                "density_stratified_shift": pooled,
                "bins": bins,
            }
        )
    return out


def main() -> None:
    df, version = build_density()
    payload = {
        "work_package": "WP6",
        "description": (
            "Annotation density as a competing explanation for the overlap effect. "
            "Density counts phenotype.hpoa rows for the case's OMIM disease(s), "
            "excluding rows citing the case's own source PMID."
        ),
        "seed": SEED,
        "hpoa_file": str(HPOA.relative_to(REPO)),
        "hpoa_version": version,
        "n_cases": len(df),
        "density_by_overlap_stratum": density_by_stratum(df),
        "adjusted_models": adjusted_models(df),
        "adjusted_interaction": adjusted_interaction(df),
        "density_stratified": density_stratified(df),
    }
    p = write_json("wp6_annotation_density.json", payload)
    print(f"wrote {p}  (hpoa version {version})")

    df.to_csv(REPO / "reports" / "p2_revision" / "wp6_case_density.csv", index=False)

    ds = payload["density_by_overlap_stratum"]
    print("\n--- annotation density by overlap stratum (own paper excluded) ---")
    for k in ("overlap_present", "overlap_absent"):
        v = ds[k]
        print(
            f"  {k:<17} n={v['n']:>4}  mean={v['mean']:>8.2f}  median={v['median']:>6}"
            f"  IQR[{v['q25']},{v['q75']}]  zero-density={v['zero_density_cases']}"
        )
    print(f"  Mann-Whitney U p = {ds['mann_whitney_u']['p']:.3g}")

    print("\n--- overlap effect before vs after adjusting for log density ---")
    for r in payload["adjusted_models"]:
        print(
            f"  {r['cell']} {r['name']:<24} crude {r['crude_overlap_effect']:+.4f} "
            f"(p={r['crude_p']:.3g}) -> adjusted {r['adjusted_overlap_effect']:+.4f} "
            f"(p={r['adjusted_p']:.3g})  attenuation {r['percent_attenuation']}%"
        )

    ai = payload["adjusted_interaction"]
    print("\n--- system x overlap interaction vs LIRICAL: crude -> density-adjusted ---")
    for s in ai["crude_interaction"]:
        c, a = ai["crude_interaction"][s], ai["density_adjusted_interaction"][s]
        print(f"  {s} vs M: {c['coef']:+.4f} (p={c['p']:.3g}) -> {a['coef']:+.4f} (p={a['p']:.3g})")

    print("\n--- density-stratified (quintile) check ---")
    for r in payload["density_stratified"]:
        print(
            f"  {r['cell']} {r['name']:<24} crude {r['crude_shift']:+.4f} -> "
            f"stratified {r['density_stratified_shift']}"
        )


if __name__ == "__main__":
    main()
