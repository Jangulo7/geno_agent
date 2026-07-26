"""A1 --- the zero-density stratum: the cleanest exposure test in the dataset.

Among the 765 overlap-present cases, 173 have an ``annotation_density`` of zero:
after excluding rows citing the case's own source publication, ``phenotype.hpoa``
holds *no* annotation for that disease at all. For those cases LIRICAL's entire
knowledge of the disease derives from the case's own source paper. No
overlap-absent case has this property, by construction.

That partition is a far sharper instrument than the binary overlap flag. If
exposure drives LIRICAL's advantage, LIRICAL should be flat across the
zero-density / positive-density boundary while every system that does not read
``phenotype.hpoa`` should fall, because zero-density diseases are intrinsically
obscure and carry little literature of any kind.

Reports, per system:
  * top-1 on stratum Z (density = 0), stratum P (density > 0) and the
    overlap-absent subset, each with publication-clustered bootstrap CIs;
  * the Z - P gradient with a clustered CI and a cluster-level permutation test;
  * the difference between each system's gradient and LIRICAL's.

Interpretation caveat, stated in the output and carried into the manuscript:
Z and P differ in disease obscurity as well as in exposure. That is precisely
what makes the contrast informative --- LIRICAL's flatness across a gradient
that flattens every other system is the signal --- but the strata are not
exchangeable and the comparison is not a randomised one.

Outputs ``reports/p2_revision/wp_a1_zero_density.json``. Seed 42.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CELL_NAMES,
    OUT_DIR,
    SEED,
    cluster_bootstrap,
    load_cases,
    load_ranks,
    subset,
    write_json,
)

N_BOOT = 10_000
N_PERM = 10_000
SYSTEMS = ["M", "K", "S", "O", "L", "D"]


def density_map() -> dict[str, int]:
    path = OUT_DIR / "wp6_case_density.csv"
    if not path.exists():
        raise SystemExit("run annotation_density.py first (needs wp6_case_density.csv)")
    return {r["case_id"]: int(r["annotation_density"]) for r in csv.DictReader(path.open())}


def top1(cell: str) -> dict[str, int]:
    return {cid: int(r is not None and r <= 1) for cid, r in load_ranks(cell).items()}


def cluster_permutation_gradient(
    zp_cases, hits, dens, n_perm: int = N_PERM, seed: int = SEED
) -> float:
    """Two-sided cluster-robust test that the Z - P gradient is zero.

    Stratum membership is a property of the case, so the label cannot simply be
    shuffled across cases without breaking the publication structure. Instead the
    Z/P label is permuted a whole publication at a time among publications that
    are internally homogeneous in stratum, which preserves clustering while
    breaking the association between stratum and outcome.
    """
    rng = np.random.default_rng(seed)
    by_pub: dict[str, list] = {}
    for c in zp_cases:
        by_pub.setdefault(c.source_pmid, []).append(c)

    pubs, labels, means = [], [], []
    for pmid, cs in by_pub.items():
        labs = {dens[c.case_id] == 0 for c in cs}
        if len(labs) != 1:
            continue  # mixed publication: contributes to neither arm cleanly
        pubs.append(pmid)
        labels.append(labs.pop())
        means.append(float(np.mean([hits[c.case_id] for c in cs])))

    labels = np.array(labels)
    means = np.array(means)
    if labels.sum() == 0 or (~labels).sum() == 0:
        return float("nan")

    obs = means[labels].mean() - means[~labels].mean()
    count = 0
    for _ in range(n_perm):
        perm = rng.permutation(labels)
        if abs(means[perm].mean() - means[~perm].mean()) >= abs(obs) - 1e-12:
            count += 1
    return (count + 1) / (n_perm + 1)


def main() -> None:
    dens = density_map()
    cases = load_cases()
    Z = [c for c in cases if c.overlap == 1 and dens[c.case_id] == 0]
    P = [c for c in cases if c.overlap == 1 and dens[c.case_id] > 0]
    A = subset("overlap_absent")

    strata = {
        "Z_zero_density": {"cases": Z, "desc": "overlap-present, annotation_density == 0"},
        "P_positive_density": {"cases": P, "desc": "overlap-present, annotation_density > 0"},
        "overlap_absent": {"cases": A, "desc": "overlap-absent subset"},
    }
    meta = {
        k: {
            "n_cases": len(v["cases"]),
            "n_publications": len({c.source_pmid for c in v["cases"]}),
            "description": v["desc"],
        }
        for k, v in strata.items()
    }

    rows = []
    for cell in SYSTEMS:
        hits = top1(cell)
        entry = {"cell": cell, "name": CELL_NAMES[cell], "strata": {}}
        for key, v in strata.items():
            cs = v["cases"]

            def stat(x, _h=hits):
                return float(np.mean([_h[c.case_id] for c in x])) if x else np.nan

            pt, lo, hi = cluster_bootstrap(cs, stat, n_boot=N_BOOT, seed=SEED)
            entry["strata"][key] = {
                "top1": round(pt, 4),
                "n_correct": int(sum(hits[c.case_id] for c in cs)),
                "n_cases": len(cs),
                "ci95_cluster": [round(lo, 4), round(hi, 4)],
            }

        zp = Z + P

        def grad(x, _h=hits):
            z = [_h[c.case_id] for c in x if dens[c.case_id] == 0]
            p = [_h[c.case_id] for c in x if dens[c.case_id] > 0]
            return float(np.mean(z) - np.mean(p)) if z and p else np.nan

        g, glo, ghi = cluster_bootstrap(zp, grad, n_boot=N_BOOT, seed=SEED)
        entry["gradient_Z_minus_P"] = {
            "estimate": round(g, 4),
            "ci95_cluster": [round(glo, 4), round(ghi, 4)],
            "ci_excludes_zero": bool(glo > 0 or ghi < 0),
            "p_cluster_permutation": round(cluster_permutation_gradient(zp, hits, dens), 5),
        }
        rows.append(entry)

    # Each system's gradient relative to LIRICAL's: the quantity that isolates
    # exposure from the general obscurity of zero-density diseases.
    lir = next(r for r in rows if r["cell"] == "M")["gradient_Z_minus_P"]["estimate"]
    for r in rows:
        r["gradient_vs_LIRICAL"] = round(r["gradient_Z_minus_P"]["estimate"] - lir, 4)

    payload = {
        "work_package": "A1",
        "description": (
            "Zero-density stratum. Among overlap-present cases, those whose disease "
            "has no phenotype.hpoa annotation from any source other than the case's "
            "own publication isolate maximal exposure with minimal independent "
            "curation."
        ),
        "seed": SEED,
        "n_bootstrap": N_BOOT,
        "n_permutations": N_PERM,
        "strata": meta,
        "systems": rows,
        "interpretation_caveat": (
            "Zero-density diseases are intrinsically obscure, so stratum Z is harder "
            "for any system relying on independent literature; Z and P are not "
            "exchangeable. The informative quantity is therefore not any single "
            "system's gradient but LIRICAL's flatness across a boundary that every "
            "overlap-independent system falls across."
        ),
    }
    p = write_json("wp_a1_zero_density.json", payload)
    print(f"wrote {p}\n")

    for k, v in meta.items():
        print(f"  {k:<20} n={v['n_cases']:>4}  publications={v['n_publications']:>4}")
    print(f"\n  {'system':<26}{'Z':>10}{'P':>10}{'absent':>10}{'Z-P':>10}{'p':>10}")
    for r in rows:
        s = r["strata"]
        g = r["gradient_Z_minus_P"]
        print(
            f"  {r['name']:<26}{s['Z_zero_density']['top1']:>10.3f}"
            f"{s['P_positive_density']['top1']:>10.3f}"
            f"{s['overlap_absent']['top1']:>10.3f}"
            f"{g['estimate']:>+10.3f}{g['p_cluster_permutation']:>10.4g}"
        )


if __name__ == "__main__":
    main()
