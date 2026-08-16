"""WP7 --- the missing centrepiece table, plus an audit of every headline number.

The paper's contribution is a stratification, yet no table gave all cells x all
metrics x {full, overlap-present, overlap-absent}. This builds it for both
candidate-list variants from the saved per-case ranks, with counts alongside
proportions so that every delta in the manuscript is verifiable by subtraction.

It also re-derives the values the manuscript currently claims and diffs them, so
that stale or inconsistent figures are caught rather than carried forward.

Outputs:
  reports/p2_revision/wp7_full_stratum_table.csv   -- the centrepiece table
  reports/p2_revision/wp7_metric_audit.csv         -- claimed vs recomputed
  reports/p2_revision/wp7_metric_audit.json

Seed 42.
"""

from __future__ import annotations

import csv
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CELL_NAMES,
    OUT_DIR,
    SEED,
    available_cells,
    load_ranks,
    metrics_for,
    subset,
    write_json,
)

# Metrics are stored at 6 dp. At 4 dp a true 0.657516 lands on the half-boundary
# 0.6575 and the 3-dp display round resolves it by float representation rather
# than by value, so the table prints 0.657 where 0.658 is correct.
PRECISION = 6

SUBSETS = [
    "full",
    "overlap_present",
    "overlap_absent",
    "pre2020",
    "post2020",
    "post2020_overlap_absent",
]
# R included: Table 1 prints a Cell R row in both blocks, and load_ranks reads
# cell_R_resnik like any other cell. Leaving it out meant the audit could not
# see a printed row -- which is how Cell R's full-cohort 0.925 survived.
CELLS = ["K", "M", "D", "L", "S", "N", "O", "R"]

# Every value the manuscript prints, keyed by a stable identifier.
# (cohort, subset, cell, metric, claimed)
#
# The Table 1 block below is the COMPLETE grid -- every cell of both candidate-list
# blocks, primary and secondary. Partial coverage is what let two defects through:
# Cell R's full-cohort top-1 (0.925 for 0.926) and six of the seven overlap-absent
# MRR values, both in rows no entry pointed at. Regenerate with
# gen_claimed_from_table1.py if Table 1 changes; it parses the printed table, so
# the check stays a comparison against the manuscript rather than against itself.
CLAIMED = [
    # --- Table 1, standard cohort ---
    ("standard", "full", "K", "top1", 0.691),
    ("standard", "overlap_present", "K", "top1", 0.658),
    ("standard", "overlap_absent", "K", "top1", 0.780),
    ("standard", "overlap_absent", "K", "top5", 0.926),
    ("standard", "overlap_absent", "K", "top10", 0.926),
    ("standard", "overlap_absent", "K", "mrr", 0.846),
    ("standard", "full", "M", "top1", 0.924),
    ("standard", "overlap_present", "M", "top1", 0.978),
    ("standard", "overlap_absent", "M", "top1", 0.777),
    ("standard", "overlap_absent", "M", "top5", 0.965),
    ("standard", "overlap_absent", "M", "top10", 1.000),
    ("standard", "overlap_absent", "M", "mrr", 0.861),
    ("standard", "full", "D", "top1", 0.460),
    ("standard", "overlap_present", "D", "top1", 0.455),
    ("standard", "overlap_absent", "D", "top1", 0.475),
    ("standard", "overlap_absent", "D", "top5", 0.635),
    ("standard", "overlap_absent", "D", "top10", 0.677),
    ("standard", "overlap_absent", "D", "mrr", 0.559),
    ("standard", "full", "L", "top1", 0.698),
    ("standard", "overlap_present", "L", "top1", 0.652),
    ("standard", "overlap_absent", "L", "top1", 0.823),
    ("standard", "overlap_absent", "L", "top5", 0.922),
    ("standard", "overlap_absent", "L", "top10", 0.940),
    ("standard", "overlap_absent", "L", "mrr", 0.870),
    ("standard", "full", "S", "top1", 0.726),
    ("standard", "overlap_present", "S", "top1", 0.677),
    ("standard", "overlap_absent", "S", "top1", 0.858),
    ("standard", "overlap_absent", "S", "top5", 0.933),
    ("standard", "overlap_absent", "S", "top10", 0.940),
    ("standard", "overlap_absent", "S", "mrr", 0.896),
    ("standard", "full", "N", "top1", 0.776),
    ("standard", "overlap_present", "N", "top1", 0.748),
    ("standard", "overlap_absent", "N", "top1", 0.851),
    ("standard", "overlap_absent", "N", "top5", 0.954),
    ("standard", "overlap_absent", "N", "top10", 0.972),
    ("standard", "overlap_absent", "N", "mrr", 0.900),
    ("standard", "full", "O", "top1", 0.511),
    ("standard", "overlap_present", "O", "top1", 0.454),
    ("standard", "overlap_absent", "O", "top1", 0.667),
    ("standard", "overlap_absent", "O", "top5", 0.770),
    ("standard", "overlap_absent", "O", "top10", 0.784),
    ("standard", "overlap_absent", "O", "mrr", 0.718),
    ("standard", "full", "R", "top1", 0.926),
    ("standard", "overlap_present", "R", "top1", 0.973),
    ("standard", "overlap_absent", "R", "top1", 0.798),
    ("standard", "overlap_absent", "R", "top5", 1.000),
    ("standard", "overlap_absent", "R", "top10", 1.000),
    ("standard", "overlap_absent", "R", "mrr", 0.892),
    # --- Table 1, hard cohort ---
    ("hard", "full", "K", "top1", 0.258),
    ("hard", "overlap_present", "K", "top1", 0.265),
    ("hard", "overlap_absent", "K", "top1", 0.238),
    ("hard", "overlap_absent", "K", "top5", 0.482),
    ("hard", "overlap_absent", "K", "top10", 0.518),
    ("hard", "overlap_absent", "K", "mrr", 0.352),
    ("hard", "full", "M", "top1", 0.642),
    ("hard", "overlap_present", "M", "top1", 0.774),
    ("hard", "overlap_absent", "M", "top1", 0.284),
    ("hard", "overlap_absent", "M", "top5", 0.426),
    ("hard", "overlap_absent", "M", "top10", 0.496),
    ("hard", "overlap_absent", "M", "mrr", 0.364),
    ("hard", "full", "D", "top1", 0.138),
    ("hard", "overlap_present", "D", "top1", 0.149),
    ("hard", "overlap_absent", "D", "top1", 0.110),
    ("hard", "overlap_absent", "D", "top5", 0.383),
    ("hard", "overlap_absent", "D", "top10", 0.535),
    ("hard", "overlap_absent", "D", "mrr", 0.246),
    ("hard", "full", "L", "top1", 0.229),
    ("hard", "overlap_present", "L", "top1", 0.207),
    ("hard", "overlap_absent", "L", "top1", 0.291),
    ("hard", "overlap_absent", "L", "top5", 0.631),
    ("hard", "overlap_absent", "L", "top10", 0.798),
    ("hard", "overlap_absent", "L", "mrr", 0.446),
    ("hard", "full", "S", "top1", 0.303),
    ("hard", "overlap_present", "S", "top1", 0.271),
    ("hard", "overlap_absent", "S", "top1", 0.390),
    ("hard", "overlap_absent", "S", "top5", 0.670),
    ("hard", "overlap_absent", "S", "top10", 0.812),
    ("hard", "overlap_absent", "S", "mrr", 0.523),
    ("hard", "full", "N", "top1", 0.425),
    ("hard", "overlap_present", "N", "top1", 0.465),
    ("hard", "overlap_absent", "N", "top1", 0.316),
    ("hard", "overlap_absent", "N", "top5", 0.521),
    ("hard", "overlap_absent", "N", "top10", 0.645),
    ("hard", "overlap_absent", "N", "mrr", 0.424),
    ("hard", "full", "R", "top1", 0.572),
    ("hard", "overlap_present", "R", "top1", 0.693),
    ("hard", "overlap_absent", "R", "top1", 0.245),
    ("hard", "overlap_absent", "R", "top5", 0.436),
    ("hard", "overlap_absent", "R", "top10", 0.486),
    ("hard", "overlap_absent", "R", "mrr", 0.342),
    # --- Full-cohort secondary metrics, quoted in Discussion 5.2 but printed in
    # no table; they map to reports/p2_revision/wp7_metric_audit.csv ---
    ("standard", "full", "K", "top5", 0.821),
    ("standard", "full", "K", "top10", 0.859),
    ("standard", "full", "K", "mrr", 0.754),
    ("standard", "full", "K", "ndcg10", 0.775),
    ("standard", "full", "M", "top5", 0.989),
    ("standard", "full", "M", "top10", 0.999),
    ("standard", "full", "M", "mrr", 0.953),
    ("standard", "full", "M", "ndcg10", 0.964),
    ("standard", "full", "D", "top5", 0.581),
    ("standard", "full", "D", "top10", 0.628),
    ("standard", "full", "D", "mrr", 0.53),
    ("standard", "full", "D", "ndcg10", 0.542),
    ("standard", "full", "L", "top5", 0.791),
    ("standard", "full", "L", "top10", 0.814),
    ("standard", "full", "L", "mrr", 0.745),
    ("standard", "full", "L", "ndcg10", 0.756),
    ("standard", "full", "S", "top5", 0.798),
    ("standard", "full", "S", "top10", 0.817),
    ("standard", "full", "S", "mrr", 0.766),
    ("standard", "full", "S", "ndcg10", 0.773),
    ("standard", "full", "N", "top5", 0.856),
    ("standard", "full", "N", "top10", 0.903),
    ("standard", "full", "N", "mrr", 0.819),
    ("standard", "full", "N", "ndcg10", 0.834),
    ("standard", "full", "O", "top5", 0.626),
    ("standard", "full", "O", "top10", 0.697),
    ("standard", "full", "O", "mrr", 0.575),
    ("standard", "full", "O", "ndcg10", 0.594),
    # --- Recency split and the crossed post-2020 x overlap-absent cell ---
    ("standard", "pre2020", "K", "top1", 0.847),
    ("standard", "post2020", "K", "top1", 0.48),
    ("standard", "pre2020", "S", "top1", 0.839),
    ("standard", "post2020", "S", "top1", 0.574),
    ("standard", "pre2020", "M", "top1", 0.915),
    ("standard", "post2020", "M", "top1", 0.935),
    ("standard", "post2020_overlap_absent", "S", "top1", 0.852),
    ("standard", "post2020_overlap_absent", "L", "top1", 0.818),
    ("standard", "post2020_overlap_absent", "K", "top1", 0.818),
    ("standard", "post2020_overlap_absent", "M", "top1", 0.773),
]

METRICS = ["top1", "top5", "top10", "mrr", "ndcg10"]


def build_table() -> list[dict]:
    rows = []
    for cohort in ("standard", "hard"):
        cells = [c for c in CELLS if c in available_cells(cohort)]
        for cell in cells:
            ranks = load_ranks(cell, cohort)
            for sub in SUBSETS:
                cases = subset(sub)
                ids = [c.case_id for c in cases]
                m = metrics_for(ranks, ids)
                n = len(ids)
                row = {
                    "cohort": cohort,
                    "cell": cell,
                    "system": CELL_NAMES[cell],
                    "subset": sub,
                    "n_cases": n,
                    "n_publications": len({c.source_pmid for c in cases}),
                }
                for k in METRICS:
                    row[k] = round(m[k], PRECISION)
                # counts alongside proportions (WP7-C)
                for k, cut in (("top1", 1), ("top5", 5), ("top10", 10)):
                    row[f"{k}_count"] = sum(
                        1 for i in ids if (ranks.get(i) is not None and ranks[i] <= cut)
                    )
                rows.append(row)
    return rows


def display_3dp(x: float) -> str:
    """The 3-dp string the manuscript should print, rounded half-up by value.

    ``f"{x:.3f}"`` rounds half-to-even *and* resolves the half by the float's
    binary representation, so 0.6575 renders 0.657. Decimal decides by value.

    ``float(x)`` first: metrics arrive as numpy scalars, whose ``repr`` is
    ``np.float64(0.658)`` and not parseable by Decimal.
    """
    x = float(x)
    if x != x:  # NaN -- empty subset
        return "nan"
    return str(Decimal(str(x)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def audit(rows: list[dict]) -> list[dict]:
    index = {(r["cohort"], r["subset"], r["cell"]): r for r in rows}
    out = []
    for cohort, sub, cell, metric, claimed in CLAIMED:
        r = index.get((cohort, sub, cell))
        if r is None:
            out.append(
                {
                    "cohort": cohort,
                    "subset": sub,
                    "cell": cell,
                    "metric": metric,
                    "claimed": claimed,
                    "recomputed": None,
                    "abs_diff": None,
                    "status": "NO_ARTEFACT",
                }
            )
            continue
        got = r[metric]
        diff = abs(got - claimed)
        # The manuscript prints 3 dp, so the only correct claim is the recomputed
        # value rounded half-up to 3 dp -- compared as an exact string, not under a
        # tolerance. A +/- 0.0005 window admits both sides of a half-boundary and
        # so passes exactly the values it should catch: 0.775549 printed as 0.775
        # sits 0.0005 away and used to audit "OK" while 0.776 is correct.
        expected = display_3dp(got)
        status = (
            "OK" if f"{claimed:.3f}" == expected else ("ROUNDING" if diff <= 0.001 else "MISMATCH")
        )
        out.append(
            {
                "cohort": cohort,
                "subset": sub,
                "cell": cell,
                "metric": metric,
                "claimed": claimed,
                "recomputed": got,
                "abs_diff": round(diff, 5),
                "status": status,
                "n_cases": r["n_cases"],
                "count": r.get(f"{metric}_count"),
            }
        )
    return out


def main() -> None:
    rows = build_table()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tbl = OUT_DIR / "wp7_full_stratum_table.csv"
    with tbl.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {tbl}  ({len(rows)} rows)")

    aud = audit(rows)
    apath = OUT_DIR / "wp7_metric_audit.csv"
    with apath.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(aud[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(aud)
    print(f"wrote {apath}  ({len(aud)} checked)")

    bad = [a for a in aud if a["status"] not in ("OK",)]
    write_json(
        "wp7_metric_audit.json",
        {
            "work_package": "WP7",
            "seed": SEED,
            "n_claims_checked": len(aud),
            "n_ok": sum(1 for a in aud if a["status"] == "OK"),
            "n_rounding": sum(1 for a in aud if a["status"] == "ROUNDING"),
            "n_mismatch": sum(1 for a in aud if a["status"] == "MISMATCH"),
            "discrepancies": bad,
        },
    )

    print(
        f"\n{len(aud)} claims checked: "
        f"{sum(1 for a in aud if a['status'] == 'OK')} exact, "
        f"{sum(1 for a in aud if a['status'] == 'ROUNDING')} rounding, "
        f"{sum(1 for a in aud if a['status'] == 'MISMATCH')} mismatched"
    )
    if bad:
        print("\n--- discrepancies ---")
        for a in bad:
            print(
                f"  [{a['status']:<9}] {a['cohort']}/{a['subset']}/{a['cell']}/"
                f"{a['metric']}: claimed {a['claimed']} vs recomputed {a['recomputed']}"
            )

    print("\n--- centrepiece: standard cohort, all cells x subsets (top-1) ---")
    print(
        f"{'cell':<4}{'system':<26}"
        + "".join(f"{s:>26}" for s in ("full", "overlap_present", "overlap_absent"))
    )
    for cell in CELLS:
        line = f"{cell:<4}{CELL_NAMES[cell]:<26}"
        for s in ("full", "overlap_present", "overlap_absent"):
            r = next(
                (
                    x
                    for x in rows
                    if x["cohort"] == "standard" and x["cell"] == cell and x["subset"] == s
                ),
                None,
            )
            if r is None:
                line += " " * 26
            else:
                cell_txt = "{} ({}/{})".format(
                    display_3dp(r["top1"]), r["top1_count"], r["n_cases"]
                )
                line += f"{cell_txt:>26}"
        print(line)


if __name__ == "__main__":
    main()
