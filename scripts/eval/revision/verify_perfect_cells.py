"""I1 --- independent re-derivation of the ``1.000`` cells in main.tex Table 1.

Three cells in the centrepiece table are exactly 1.000 on the overlap-absent
subset of the standard cohort: LIRICAL (M) top-10, and the Resnik BMA similarity
floor (R) at top-5 and top-10. Perfect scores attract reviewer scrutiny, so this
script re-derives them straight from the per-case artefacts rather than from any
previously written summary, and reports explicit numerators and denominators.

It deliberately does NOT reuse ``_common.metrics_for``: the ranks are read out of
the raw ``data/eval_1050/cell_*/<case_id>.json`` files here, so an error in the
shared metric code cannot hide behind itself. The only shared input is the
overlap-absent case list (from the P1 overlap flag), which is re-derived below
from ``annotation_overlap.json`` directly.

It also records tie diagnostics: a top-k of 1.000 is only meaningful if the
causal gene's placement is not an artefact of how score ties were broken.

Output: reports/p2_revision/i1_perfect_cells.json
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COHORT_DIR = REPO / "data" / "test_cases_1050"
EVAL_STD = REPO / "data" / "eval_1050"
OUT = REPO / "reports" / "p2_revision" / "i1_perfect_cells.json"

CELL_DIRS = {
    "K": "cell_K_exomiser_hpo_only",
    "M": "cell_M_lirical_hpo_only",
    "S": "cell_S_rerank_inside_plus_lea",
    "R": "cell_R_resnik",
}

# (cell, metric, value printed in main.tex Table 1, overlap-absent secondary block)
CLAIMED = [
    ("M", "top5", 0.965),
    ("M", "top10", 1.000),
    ("R", "top5", 1.000),
    ("R", "top10", 1.000),
    ("R", "top1", 0.798),
    # neighbouring non-perfect cells, as controls on the same code path
    ("S", "top5", 0.933),
    ("S", "top10", 0.940),
    ("K", "top10", 0.926),
]


def overlap_absent_ids() -> list[str]:
    doc = json.loads((COHORT_DIR / "annotation_overlap.json").read_text())
    return sorted(r["case_id"] for r in doc["records"] if int(r["overlap"]) == 0)


def read_case(cell: str, case_id: str) -> dict:
    """Rank of the causal gene plus tie diagnostics for one case."""
    path = EVAL_STD / CELL_DIRS[cell] / f"{case_id}.json"
    if not path.exists():
        return {"present": False}
    payload = json.loads(path.read_text())
    causal = [e for e in payload if e.get("is_causal")]
    if len(causal) != 1:
        return {"present": True, "n_causal_entries": len(causal), "rank": None}
    entry = causal[0]
    score = entry.get("aggregate_confidence")
    # How many candidates share the causal gene's score? A tie block of size t
    # means the causal gene could have landed anywhere in a t-wide rank window.
    tied = sum(1 for e in payload if e.get("aggregate_confidence") == score)
    ranks_in_tie = [e["final_rank"] for e in payload if e.get("aggregate_confidence") == score]
    return {
        "present": True,
        "n_causal_entries": 1,
        "rank": int(entry["final_rank"]),
        "n_candidates": len(payload),
        "score": score,
        "tie_block": tied,
        "tie_block_worst_rank": max(ranks_in_tie) if ranks_in_tie else None,
    }


def main() -> None:
    ids = overlap_absent_ids()
    n = len(ids)
    per_cell: dict[str, dict] = {}

    for cell in CELL_DIRS:
        rows = {cid: read_case(cell, cid) for cid in ids}
        missing = [c for c, r in rows.items() if not r.get("present")]
        no_causal = [c for c, r in rows.items() if r.get("present") and r.get("rank") is None]
        ranks = {c: r["rank"] for c, r in rows.items() if r.get("rank") is not None}
        counts = {f"top{k}": sum(1 for v in ranks.values() if v <= k) for k in (1, 5, 10)}
        # Worst-case placement if every score tie had been broken against the
        # causal gene: does the perfect top-k survive an adversarial tie rule?
        worst = {
            f"top{k}": sum(
                1
                for c, r in rows.items()
                if r.get("rank") is not None and (r["tie_block_worst_rank"] or r["rank"]) <= k
            )
            for k in (1, 5, 10)
        }
        per_cell[cell] = {
            "n_cases_overlap_absent": n,
            "artefacts_present": n - len(missing),
            "missing_artefacts": missing,
            "artefacts_without_causal_entry": no_causal,
            "candidate_list_sizes": dict(
                Counter(r["n_candidates"] for r in rows.values() if r.get("n_candidates"))
            ),
            "counts": counts,
            "rates": {k: round(v / n, 4) for k, v in counts.items()},
            "as_fraction": {k: f"{v}/{n}" for k, v in counts.items()},
            "worst_rank_in_causal_tie_block": {
                "counts": worst,
                "rates": {k: round(v / n, 4) for k, v in worst.items()},
                "note": "counts if every score tie were broken against the causal gene",
            },
            "cases_with_tied_causal_score": sum(
                1 for r in rows.values() if (r.get("tie_block") or 0) > 1
            ),
            "max_causal_rank": max(ranks.values()) if ranks else None,
            "rank_gt10_cases": sorted(c for c, v in ranks.items() if v > 10),
        }

    audit = []
    for cell, metric, claimed in CLAIMED:
        rec = per_cell[cell]
        got = rec["rates"][metric]
        audit.append(
            {
                "cell": cell,
                "metric": metric,
                "claimed_in_table1": claimed,
                "recomputed": got,
                "as_fraction": rec["as_fraction"][metric],
                "abs_diff": round(abs(got - claimed), 4),
                "status": "OK" if abs(got - claimed) <= 0.0006 else "MISMATCH",
            }
        )

    payload = {
        "item": "I1",
        "question": "Are the 1.000 cells in main.tex Table 1 real, and what is the denominator?",
        "subset": "standard cohort, overlap-absent (P1 annotation-overlap flag == 0)",
        "n_cases": n,
        "source": "per-case artefacts under data/eval_1050/<cell>/<case_id>.json",
        "audit": audit,
        "per_cell": per_cell,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"overlap-absent cases: {n}")
    for row in audit:
        print(
            f"  {row['cell']} {row['metric']:6s} claimed={row['claimed_in_table1']:.3f} "
            f"recomputed={row['recomputed']:.4f} ({row['as_fraction']}) {row['status']}"
        )
    print()
    for cell, rec in per_cell.items():
        print(
            f"  {cell}: artefacts {rec['artefacts_present']}/{n}, "
            f"list sizes {rec['candidate_list_sizes']}, "
            f"max causal rank {rec['max_causal_rank']}, "
            f"tied-score cases {rec['cases_with_tied_causal_score']}, "
            f"worst-tie top10 {rec['worst_rank_in_causal_tie_block']['rates']['top10']}"
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
