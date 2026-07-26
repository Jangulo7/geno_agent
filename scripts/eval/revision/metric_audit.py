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

SUBSETS = [
    "full",
    "overlap_present",
    "overlap_absent",
    "pre2020",
    "post2020",
    "post2020_overlap_absent",
]
CELLS = ["K", "M", "D", "L", "S", "N", "O"]

# Values the current manuscript states, keyed by a stable identifier.
# (cohort, subset, cell, metric, claimed)
CLAIMED = [
    ("standard", "full", "K", "top1", 0.691),
    ("standard", "full", "K", "top5", 0.821),
    ("standard", "full", "K", "top10", 0.859),
    ("standard", "full", "K", "mrr", 0.754),
    ("standard", "full", "K", "ndcg10", 0.775),
    ("standard", "full", "M", "top1", 0.924),
    ("standard", "full", "M", "top5", 0.989),
    ("standard", "full", "M", "top10", 0.999),
    ("standard", "full", "M", "mrr", 0.953),
    ("standard", "full", "M", "ndcg10", 0.964),
    ("standard", "full", "D", "top1", 0.460),
    ("standard", "full", "D", "top5", 0.581),
    ("standard", "full", "D", "top10", 0.628),
    ("standard", "full", "D", "mrr", 0.529),
    ("standard", "full", "D", "ndcg10", 0.542),
    ("standard", "full", "L", "top1", 0.698),
    ("standard", "full", "L", "top5", 0.791),
    ("standard", "full", "L", "top10", 0.814),
    ("standard", "full", "L", "mrr", 0.745),
    ("standard", "full", "L", "ndcg10", 0.756),
    ("standard", "full", "S", "top1", 0.726),
    ("standard", "full", "S", "top5", 0.798),
    ("standard", "full", "S", "top10", 0.817),
    ("standard", "full", "S", "mrr", 0.766),
    ("standard", "full", "S", "ndcg10", 0.773),
    ("standard", "full", "N", "top1", 0.775),
    ("standard", "full", "N", "top5", 0.856),
    ("standard", "full", "N", "top10", 0.903),
    ("standard", "full", "N", "mrr", 0.819),
    ("standard", "full", "N", "ndcg10", 0.834),
    ("standard", "full", "O", "top1", 0.511),
    ("standard", "full", "O", "top5", 0.626),
    ("standard", "full", "O", "top10", 0.697),
    ("standard", "full", "O", "mrr", 0.575),
    ("standard", "full", "O", "ndcg10", 0.594),
    # overlap-absent ("fair") cohort
    ("standard", "overlap_absent", "S", "top1", 0.858),
    ("standard", "overlap_absent", "S", "top5", 0.933),
    ("standard", "overlap_absent", "S", "top10", 0.940),
    ("standard", "overlap_absent", "L", "top1", 0.823),
    ("standard", "overlap_absent", "K", "top1", 0.780),
    ("standard", "overlap_absent", "M", "top1", 0.777),
    ("standard", "overlap_absent", "M", "top5", 0.965),
    ("standard", "overlap_absent", "M", "top10", 1.000),
    ("standard", "overlap_absent", "O", "top1", 0.667),
    ("standard", "overlap_present", "M", "top1", 0.978),
    ("standard", "overlap_present", "O", "top1", 0.454),
    # recency
    ("standard", "pre2020", "K", "top1", 0.847),
    ("standard", "post2020", "K", "top1", 0.480),
    ("standard", "pre2020", "S", "top1", 0.839),
    ("standard", "post2020", "S", "top1", 0.574),
    ("standard", "pre2020", "M", "top1", 0.915),
    ("standard", "post2020", "M", "top1", 0.935),
    ("standard", "post2020_overlap_absent", "S", "top1", 0.852),
    ("standard", "post2020_overlap_absent", "L", "top1", 0.823),
    ("standard", "post2020_overlap_absent", "K", "top1", 0.818),
    ("standard", "post2020_overlap_absent", "M", "top1", 0.773),
    # hard cohort
    ("hard", "full", "K", "top1", 0.258),
    ("hard", "full", "M", "top1", 0.642),
    ("hard", "full", "D", "top1", 0.139),
    ("hard", "full", "L", "top1", 0.229),
    ("hard", "full", "S", "top1", 0.303),
    ("hard", "full", "N", "top1", 0.425),
    ("hard", "overlap_absent", "K", "top1", 0.238),
    ("hard", "overlap_absent", "M", "top1", 0.284),
    ("hard", "overlap_absent", "D", "top1", 0.110),
    ("hard", "overlap_absent", "L", "top1", 0.291),
    ("hard", "overlap_absent", "S", "top1", 0.390),
    ("hard", "overlap_absent", "N", "top1", 0.316),
    ("hard", "overlap_absent", "S", "top5", 0.670),
    ("hard", "overlap_absent", "S", "top10", 0.812),
    ("hard", "overlap_absent", "L", "top10", 0.798),
    ("hard", "overlap_absent", "S", "mrr", 0.523),
    ("hard", "overlap_present", "M", "top1", 0.774),
    ("hard", "overlap_present", "S", "top1", 0.271),
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
                    row[k] = round(m[k], 4)
                # counts alongside proportions (WP7-C)
                for k, cut in (("top1", 1), ("top5", 5), ("top10", 10)):
                    row[f"{k}_count"] = sum(
                        1 for i in ids if (ranks.get(i) is not None and ranks[i] <= cut)
                    )
                rows.append(row)
    return rows


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
        # 3-dp display tolerance: anything above half a unit in the last displayed
        # digit is a genuine discrepancy, not rounding.
        status = "OK" if diff <= 0.0005 else ("ROUNDING" if diff <= 0.001 else "MISMATCH")
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
                cell_txt = "{:.3f} ({}/{})".format(r["top1"], r["top1_count"], r["n_cases"])
                line += f"{cell_txt:>26}"
        print(line)


if __name__ == "__main__":
    main()
