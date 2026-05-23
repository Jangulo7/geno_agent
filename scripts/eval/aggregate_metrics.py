"""Aggregate per-case factorial results into the §11.5 results table.

Master plan §11.5 metrics:
  - Top-1, Top-5, Top-10 accuracy
  - Mean Reciprocal Rank (MRR)
  - NDCG@10 (binary relevance, gain = is_causal)
  - Paired bootstrap 95 % CI (1000 resamples) over cases per cell

Inputs:
  data/eval/cell_{A,B,C,D}_*/[case_id].json
    Per-case ranked lists from ``run_factorial.py``.
  data/test_cases/test_cases.jsonl
    Source-of-truth labels (causal_gene, MONDO category).

Outputs:
  data/eval/_results_table.csv       — one row per cell, plus point estimate + CI per metric
  data/eval/_results_by_category.csv — same, broken down by MONDO category
  data/eval/_results_summary.md      — LaTeX-ready markdown table
  data/eval/_results_summary.json    — programmatic dump (point estimates only)

Run::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/eval/aggregate_metrics.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("aggregate")

EVAL_ROOT: Final[Path] = PROJECT_ROOT / "data" / "eval"
TEST_CASES: Final[Path] = PROJECT_ROOT / "data" / "test_cases" / "test_cases.jsonl"
BOOTSTRAP_N: Final[int] = 1000
RANDOM_SEED: Final[int] = 42

CELLS: Final[dict[str, dict]] = {
    "A": {"dir": "cell_A_single_dense", "label": "single-agent - dense"},
    "B": {"dir": "cell_B_single_hybrid", "label": "single-agent - hybrid"},
    "C": {"dir": "cell_C_multi_dense", "label": "multi-agent - dense"},
    "D": {"dir": "cell_D_multi_hybrid", "label": "multi-agent - hybrid"},
    "E": {"dir": "cell_E_multi_llmplanner_dense", "label": "multi-agent LLM-Planner - dense"},
    "F": {"dir": "cell_F_multi_llmplanner_hybrid", "label": "multi-agent LLM-Planner - hybrid"},
    "G": {"dir": "cell_G_multi_llmcritic_dense", "label": "multi-agent LLM-Critic - dense"},
    "H": {"dir": "cell_H_multi_llmcritic_hybrid", "label": "multi-agent LLM-Critic - hybrid"},
    "I": {"dir": "cell_I_multi_llmboth_dense", "label": "multi-agent LLM-both - dense"},
    "J": {"dir": "cell_J_multi_llmboth_hybrid", "label": "multi-agent LLM-both - hybrid"},
    "K": {"dir": "cell_K_exomiser_hpo_only", "label": "Exomiser HPO-only (baseline)"},
    "L": {"dir": "cell_L_rerank_inside_d", "label": "multi-agent + CE-rerank-inside · hybrid"},
    "M": {"dir": "cell_M_lirical_hpo_only", "label": "LIRICAL HPO-only (baseline)"},
    "N": {"dir": "cell_N_rrf_m_s", "label": "RRF ensemble of M + S (Thread F)"},
    "Q": {"dir": "cell_Q_multi_lea_dense", "label": "multi-agent + LEA - dense"},
    "R": {"dir": "cell_R_multi_lea_hybrid", "label": "multi-agent + LEA - hybrid"},
    "S": {
        "dir": "cell_S_rerank_inside_plus_lea",
        "label": "multi-agent + CE-rerank + LEA - hybrid",
    },
    "P": {"dir": "cell_P_ensemble_d_k", "label": "Ensemble D + K (RRF)"},
}


# ---------------------------------------------------------------- metric helpers
def causal_rank_from_payload(payload: list[dict]) -> int | None:
    """Return the 1-based rank of the causal gene, or None if no causal flag."""
    for entry in payload:
        if entry.get("is_causal"):
            return entry.get("final_rank")
    return None


def top_k_hit(rank: int | None, k: int) -> int:
    """1 if rank ≤ k else 0; rank=None counted as miss."""
    return 1 if rank is not None and rank <= k else 0


def reciprocal_rank(rank: int | None) -> float:
    """1/rank if rank is set, else 0."""
    return 1.0 / rank if rank is not None and rank > 0 else 0.0


def ndcg_at_10(rank: int | None) -> float:
    """Binary-relevance NDCG@10 for a single ranked list.

    Only the causal gene contributes (binary gain). Ideal DCG is
    ``1 / log2(2) = 1.0`` (causal at rank 1). Observed DCG is
    ``1 / log2(rank + 1)`` if rank ≤ 10 else 0.
    """
    if rank is None or rank > 10:
        return 0.0
    return 1.0 / math.log2(rank + 1)


# ---------------------------------------------------------------- bootstrap
def paired_bootstrap_ci(
    values: list[float],
    *,
    n_resamples: int = BOOTSTRAP_N,
    seed: int = RANDOM_SEED,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Return (point estimate = mean, ci_lo, ci_hi) by paired-bootstrap mean.

    Args:
        values: Per-case metric values (e.g. [0,1,1,0,...] for top-1).
        n_resamples: Number of bootstrap resamples (default 1000).
        seed: Bootstrap RNG seed.
        alpha: CI alpha; 0.05 -> 95 % CI.
    """
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = sum(values) / n
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        sample_sum = 0.0
        for _ in range(n):
            sample_sum += values[rng.randrange(n)]
        means.append(sample_sum / n)
    means.sort()
    lo_idx = math.floor(alpha / 2 * n_resamples)
    hi_idx = math.ceil((1 - alpha / 2) * n_resamples) - 1
    lo_idx = max(0, min(lo_idx, n_resamples - 1))
    hi_idx = max(0, min(hi_idx, n_resamples - 1))
    return point, means[lo_idx], means[hi_idx]


# ---------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=Path, default=EVAL_ROOT)
    parser.add_argument("--test-cases", type=Path, default=TEST_CASES)
    parser.add_argument(
        "--bootstrap-n",
        type=int,
        default=BOOTSTRAP_N,
        help="Number of paired bootstrap resamples (default 1000).",
    )
    args = parser.parse_args()

    # Build case_id -> category map
    cases_meta = {}
    with args.test_cases.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            c = json.loads(line)
            cases_meta[c["case_id"]] = c

    # Collect per-cell, per-case metrics
    cell_metrics: dict[str, dict[str, dict[str, list[float]]]] = {}
    cell_per_case: dict[str, dict[str, dict]] = {}

    for cell_id, meta in CELLS.items():
        cell_dir = args.eval_root / meta["dir"]
        if not cell_dir.is_dir():
            log.debug("Cell %s dir missing: %s (skipping)", cell_id, cell_dir)
            continue
        # metrics["top1"][category] = list of 0/1
        by_metric: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        per_case: dict[str, dict] = {}
        for json_path in sorted(cell_dir.glob("*.json")):
            case_id = json_path.stem
            case_meta = cases_meta.get(case_id)
            if not case_meta:
                log.warning("No metadata for %s; skipping", case_id)
                continue
            try:
                payload = json.loads(json_path.read_text())
            except json.JSONDecodeError:
                log.warning("Bad JSON in %s; skipping", json_path)
                continue
            rank = causal_rank_from_payload(payload)
            category = case_meta.get("category", "unknown")
            metrics_this_case = {
                "top1": top_k_hit(rank, 1),
                "top5": top_k_hit(rank, 5),
                "top10": top_k_hit(rank, 10),
                "mrr": reciprocal_rank(rank),
                "ndcg10": ndcg_at_10(rank),
                "causal_rank": rank,
            }
            for m, v in metrics_this_case.items():
                if m == "causal_rank":
                    continue
                by_metric[m]["__all__"].append(v)
                by_metric[m][category].append(v)
            per_case[case_id] = {
                "rank": rank,
                "category": category,
                **{k: v for k, v in metrics_this_case.items() if k != "causal_rank"},
            }
        cell_metrics[cell_id] = by_metric
        cell_per_case[cell_id] = per_case
        log.info("Cell %s: %d cases", cell_id, len(per_case))

    # ----- emit CSVs + summary -----
    args.eval_root.mkdir(parents=True, exist_ok=True)

    # Overall results table
    overall_rows: list[dict] = []
    metric_names = ("top1", "top5", "top10", "mrr", "ndcg10")
    for cell_id, meta in CELLS.items():
        m = cell_metrics.get(cell_id, {})
        if not m:
            continue
        n_cases = len(m["top1"]["__all__"])
        row = {"cell": cell_id, "label": meta["label"], "n_cases": n_cases}
        for metric in metric_names:
            values = m[metric]["__all__"]
            point, lo, hi = paired_bootstrap_ci(values, n_resamples=args.bootstrap_n)
            row[f"{metric}_point"] = round(point, 4)
            row[f"{metric}_ci_lo"] = round(lo, 4)
            row[f"{metric}_ci_hi"] = round(hi, 4)
        overall_rows.append(row)

    overall_csv = args.eval_root / "_results_table.csv"
    if overall_rows:
        with overall_csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(overall_rows[0].keys()))
            writer.writeheader()
            writer.writerows(overall_rows)
        log.info("Wrote %s", overall_csv)

    # Per-category breakdown
    category_rows: list[dict] = []
    for cell_id, meta in CELLS.items():
        m = cell_metrics.get(cell_id, {})
        if not m:
            continue
        all_cats = sorted(set(m["top1"].keys()) - {"__all__"})
        for cat in all_cats:
            n_cases = len(m["top1"][cat])
            row = {"cell": cell_id, "label": meta["label"], "category": cat, "n_cases": n_cases}
            for metric in metric_names:
                values = m[metric][cat]
                point, lo, hi = paired_bootstrap_ci(values, n_resamples=args.bootstrap_n)
                row[f"{metric}_point"] = round(point, 4)
                row[f"{metric}_ci_lo"] = round(lo, 4)
                row[f"{metric}_ci_hi"] = round(hi, 4)
            category_rows.append(row)
    by_cat_csv = args.eval_root / "_results_by_category.csv"
    if category_rows:
        with by_cat_csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(category_rows[0].keys()))
            writer.writeheader()
            writer.writerows(category_rows)
        log.info("Wrote %s", by_cat_csv)

    # LaTeX-ready markdown summary
    summary_md = args.eval_root / "_results_summary.md"
    cases_per_cell = overall_rows[0]["n_cases"] if overall_rows else 0
    n_cells = len(overall_rows)
    lines: list[str] = []
    lines.append("# §11.5 Factorial Evaluation — Results")
    lines.append("")
    lines.append(
        f"{n_cells} cells x {cases_per_cell} cases per cell. "
        f"Bootstrap N = {args.bootstrap_n}, 95 % CI. Cells A-D deterministic; "
        "cells E-J use Qwen3-8B via local vLLM (thinking-off, batched, "
        "deterministic temperature=0)."
    )
    lines.append("")
    lines.append("## Overall (point estimate - 95 % CI)")
    lines.append("")
    lines.append("| Cell | Architecture x Retrieval | Top-1 | Top-5 | Top-10 | MRR | NDCG@10 |")
    lines.append("|------|--------------------------|------:|------:|-------:|----:|--------:|")
    for row in overall_rows:
        lines.append(
            f"| {row['cell']} | {row['label']} | "
            f"{row['top1_point']:.3f} ({row['top1_ci_lo']:.3f}-{row['top1_ci_hi']:.3f}) | "
            f"{row['top5_point']:.3f} ({row['top5_ci_lo']:.3f}-{row['top5_ci_hi']:.3f}) | "
            f"{row['top10_point']:.3f} ({row['top10_ci_lo']:.3f}-{row['top10_ci_hi']:.3f}) | "
            f"{row['mrr_point']:.3f} ({row['mrr_ci_lo']:.3f}-{row['mrr_ci_hi']:.3f}) | "
            f"{row['ndcg10_point']:.3f} ({row['ndcg10_ci_lo']:.3f}-{row['ndcg10_ci_hi']:.3f}) |"
        )
    lines.append("")
    if category_rows:
        lines.append("## By MONDO category")
        lines.append("")
        for cat in sorted({r["category"] for r in category_rows}):
            lines.append(f"### {cat}")
            lines.append("")
            lines.append("| Cell | n | Top-1 | Top-5 | Top-10 | MRR | NDCG@10 |")
            lines.append("|------|--:|------:|------:|-------:|----:|--------:|")
            for row in category_rows:
                if row["category"] != cat:
                    continue
                lines.append(
                    f"| {row['cell']} | {row['n_cases']} | "
                    f"{row['top1_point']:.3f} | "
                    f"{row['top5_point']:.3f} | "
                    f"{row['top10_point']:.3f} | "
                    f"{row['mrr_point']:.3f} | "
                    f"{row['ndcg10_point']:.3f} |"
                )
            lines.append("")
    summary_md.write_text("\n".join(lines))
    log.info("Wrote %s", summary_md)

    # JSON dump for programmatic access
    summary_json = args.eval_root / "_results_summary.json"
    summary_json.write_text(
        json.dumps(
            {"overall": overall_rows, "by_category": category_rows},
            indent=2,
        )
    )
    log.info("Wrote %s", summary_json)

    print()
    print("=== Results summary ===")
    for row in overall_rows:
        print(
            f"  {row['cell']} ({row['label']:<30s}) "
            f"top1={row['top1_point']:.3f} "
            f"top5={row['top5_point']:.3f} "
            f"top10={row['top10_point']:.3f} "
            f"MRR={row['mrr_point']:.3f} "
            f"NDCG@10={row['ndcg10_point']:.3f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
