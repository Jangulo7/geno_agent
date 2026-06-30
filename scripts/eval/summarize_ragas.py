"""Slim a raw RAGAS output JSON into a committable summary.

``run_ragas.py`` writes a large per-case JSON (``ragas_cell_S_n600.json``,
~19 MB) that embeds the retrieved PMC chunk text for every case. That raw
file is **gitignored** (verbatim PMC text is license-mixed and bulky). This
script derives the small, committable ``*_summary.json`` that carries the
aggregate statistics plus per-case *scores only* (case_id + metric values, no
context text) — the artifact the manuscript-render code reads.

Schema matches the standard-cohort summary
(``data/eval_1050/ragas_cell_S_n600_summary.json``) so both difficulty variants
are summarised by identical code.

Usage::

    PYTHONPATH=. python scripts/eval/summarize_ragas.py \\
        --raw data/eval_hard/ragas_cell_S_n600.json \\
        --out data/eval_hard/ragas_cell_S_n600_summary.json \\
        --subset "Cell S, n=600 stratified (150 per MONDO category, seed 42)" \\
        --estimated-cost-usd 95
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

# Mirrors run_ragas.MAX_CONTEXTS_PER_CASE; recorded for provenance only.
DEFAULT_MAX_CONTEXTS: int = 20


def _is_null(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _bucket(v: float) -> str:
    """Bin a 0-1 score into the standard-cohort distribution buckets."""
    if v == 0.0:
        return "0.00"
    if v == 1.0:
        return "1.00"
    if v <= 0.1:
        return "(0,0.1]"
    if v <= 0.25:
        return "(0.1,0.25]"
    if v <= 0.5:
        return "(0.25,0.5]"
    if v <= 0.75:
        return "(0.5,0.75]"
    return "(0.75,1.0)"


def summarize(
    raw: dict, *, subset: str, source: str, cost: float | None, max_contexts: int
) -> dict:
    metrics: list[str] = raw["metrics"]
    per_case: list[dict] = raw["per_case"]

    aggregate: dict[str, dict] = {}
    for m in metrics:
        vals = [r.get(m) for r in per_case]
        scored = [float(v) for v in vals if not _is_null(v)]
        n_null = sum(1 for v in vals if _is_null(v))
        buckets: dict[str, int] = {}
        if n_null:
            buckets["null"] = n_null
        for v in scored:
            b = _bucket(v)
            buckets[b] = buckets.get(b, 0) + 1
        aggregate[m] = {
            "n_scored": len(scored),
            "n_null": n_null,
            "mean": (statistics.fmean(scored) if scored else None),
            "median": (statistics.median(scored) if scored else None),
            "min": (min(scored) if scored else None),
            "max": (max(scored) if scored else None),
            "distribution_buckets": buckets,
        }

    per_case_scores = [
        {
            "case_id": r.get("case_id"),
            **{m: (None if _is_null(r.get(m)) else r.get(m)) for m in metrics},
        }
        for r in per_case
    ]

    elapsed = raw.get("elapsed_seconds")
    meta = {
        "judge_model": raw.get("judge_model"),
        "judge_temperature": raw.get("judge_temperature"),
        "metrics": metrics,
        "n_cases_total": raw.get("n_cases_total"),
        "n_cases_evaluated": raw.get("n_cases_evaluated"),
        "n_cases_skipped": raw.get("n_cases_skipped"),
        "elapsed_seconds": elapsed,
        "elapsed_minutes": (round(elapsed / 60.0, 1) if elapsed else None),
        "estimated_cost_usd": cost,
        "source": source,
        "subset": subset,
        "max_contexts_per_case": max_contexts,
    }
    return {"meta": meta, "aggregate": aggregate, "per_case_scores": per_case_scores}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", type=Path, required=True, help="Raw ragas JSON from run_ragas.py.")
    p.add_argument("--out", type=Path, required=True, help="Output summary JSON path.")
    p.add_argument(
        "--subset", type=str, default="", help="Human description of the sampled subset."
    )
    p.add_argument(
        "--source",
        type=str,
        default="",
        help="Provenance note for the raw file (default: the --raw path).",
    )
    p.add_argument("--estimated-cost-usd", type=float, default=None, help="Approx. judge API cost.")
    p.add_argument("--max-contexts", type=int, default=DEFAULT_MAX_CONTEXTS)
    args = p.parse_args()

    raw = json.loads(args.raw.read_text())
    source = args.source or f"{args.raw} (full, gitignored)"
    summary = summarize(
        raw,
        subset=args.subset,
        source=source,
        cost=args.estimated_cost_usd,
        max_contexts=args.max_contexts,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2))

    print(f"Wrote {args.out}")
    for m, a in summary["aggregate"].items():
        mean = a["mean"]
        print(
            f"  {m}: mean={mean:.4f} n_scored={a['n_scored']} n_null={a['n_null']}"
            if mean is not None
            else f"  {m}: all null"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
