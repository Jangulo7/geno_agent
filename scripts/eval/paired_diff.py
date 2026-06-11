"""Paired per-case Δ between two cells with paired-bootstrap 95 % CI and McNemar.

For two cells (A, B) over the same cohort, computes for each metric:
  - Mean Δ = mean(metric_A[case] - metric_B[case])
  - 95 % CI by paired bootstrap (1000 resamples, seed 42) over per-case diffs
  - Exact McNemar p-value on (A beats B) vs (B beats A) discordant pairs for
    binary metrics (top-1, top-5, top-10)
  - "★" flag if 95 % CI excludes 0

Run::

    PYTHONPATH=. python scripts/eval/paired_diff.py \\
        --eval-root data/eval_1050 \\
        --test-cases data/test_cases_1050/test_cases.jsonl \\
        --a S --b K
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval.aggregate_metrics import (  # noqa: E402
    CELLS,
    causal_rank_from_payload,
    ndcg_at_10,
    reciprocal_rank,
    top_k_hit,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paired_diff")

BOOTSTRAP_N: Final[int] = 1000
RANDOM_SEED: Final[int] = 42


def load_cell_metrics(cell_dir: Path, cases_meta: dict[str, dict]) -> dict[str, dict[str, float]]:
    """Return ``{case_id: {top1, top5, top10, mrr, ndcg10, category}}`` for a cell."""
    out: dict[str, dict[str, float]] = {}
    for path in sorted(cell_dir.glob("*.json")):
        case_id = path.stem
        meta = cases_meta.get(case_id)
        if meta is None:
            continue
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            log.warning("Bad JSON: %s", path)
            continue
        rank = causal_rank_from_payload(payload)
        out[case_id] = {
            "top1": float(top_k_hit(rank, 1)),
            "top5": float(top_k_hit(rank, 5)),
            "top10": float(top_k_hit(rank, 10)),
            "mrr": reciprocal_rank(rank),
            "ndcg10": ndcg_at_10(rank),
            "category": meta.get("category", "unknown"),
        }
    return out


def paired_bootstrap_diff(
    diffs: list[float], n_resamples: int = BOOTSTRAP_N, seed: int = RANDOM_SEED, alpha: float = 0.05
) -> tuple[float, float, float]:
    """Return (mean Δ, ci_lo, ci_hi) by bootstrapping the mean of per-case diffs."""
    n = len(diffs)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = sum(diffs) / n
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += diffs[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[max(0, math.floor(alpha / 2 * n_resamples))]
    hi = means[min(n_resamples - 1, math.ceil((1 - alpha / 2) * n_resamples) - 1)]
    return point, lo, hi


def mcnemar_exact_p(a_wins: int, b_wins: int) -> float:
    """Exact two-sided McNemar p-value on discordant pairs (binomial(0.5))."""
    n = a_wins + b_wins
    if n == 0:
        return 1.0
    k = min(a_wins, b_wins)
    # Two-sided: 2 * P(X <= k) under Binom(n, 0.5), capped at 1
    cdf = 0.0
    for i in range(k + 1):
        cdf += math.comb(n, i) * (0.5**n)
    return min(1.0, 2.0 * cdf)


def compare(
    a_metrics: dict[str, dict[str, float]],
    b_metrics: dict[str, dict[str, float]],
    category_filter: str | None = None,
) -> dict:
    """Return paired comparison dict for A vs B."""
    common = sorted(set(a_metrics) & set(b_metrics))
    if category_filter:
        common = [c for c in common if a_metrics[c]["category"] == category_filter]
    n = len(common)
    out: dict = {"n": n, "category": category_filter or "__all__", "metrics": {}}
    for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
        diffs = [a_metrics[c][metric] - b_metrics[c][metric] for c in common]
        point, lo, hi = paired_bootstrap_diff(diffs)
        sig = lo > 0 or hi < 0
        d = {
            "point": round(point, 4),
            "ci_lo": round(lo, 4),
            "ci_hi": round(hi, 4),
            "significant": sig,
        }
        if metric in ("top1", "top5", "top10"):
            a_wins = sum(1 for c in common if a_metrics[c][metric] > b_metrics[c][metric])
            b_wins = sum(1 for c in common if a_metrics[c][metric] < b_metrics[c][metric])
            d["a_wins"] = a_wins
            d["b_wins"] = b_wins
            d["mcnemar_p"] = round(mcnemar_exact_p(a_wins, b_wins), 5)
        out["metrics"][metric] = d
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--test-cases", type=Path, required=True)
    parser.add_argument("--a", required=True, help="First cell ID (e.g. S)")
    parser.add_argument("--b", required=True, help="Second cell ID (e.g. K)")
    parser.add_argument(
        "--by-category", action="store_true", help="Also report per-MONDO breakdown"
    )
    parser.add_argument("--out-json", type=Path, default=None)
    args = parser.parse_args()

    cases_meta: dict[str, dict] = {}
    with args.test_cases.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            c = json.loads(line)
            cases_meta[c["case_id"]] = c

    a_dir = args.eval_root / CELLS[args.a]["dir"]
    b_dir = args.eval_root / CELLS[args.b]["dir"]
    a = load_cell_metrics(a_dir, cases_meta)
    b = load_cell_metrics(b_dir, cases_meta)
    log.info("Cell %s: %d cases | Cell %s: %d cases", args.a, len(a), args.b, len(b))

    results: dict = {"a": args.a, "b": args.b, "comparisons": []}
    results["comparisons"].append(compare(a, b))

    categories: list[str] = []
    if args.by_category:
        categories = sorted({m["category"] for m in a.values()})
        for cat in categories:
            results["comparisons"].append(compare(a, b, category_filter=cat))

    # ---- print human-readable
    for comp in results["comparisons"]:
        cat = comp["category"]
        n = comp["n"]
        print(f"\n=== {args.a} vs {args.b} | {cat} | n={n} ===")
        print(
            f"  {'metric':<8} {'Δ':>8} {'95% CI':>22} {'sig':>4}  {'A>B':>5} {'B>A':>5} {'McNemar p':>11}"
        )
        for metric, d in comp["metrics"].items():
            sig = "★" if d.get("significant") else ""
            ci = f"[{d['ci_lo']:+.4f}, {d['ci_hi']:+.4f}]"
            extra = ""
            if "a_wins" in d:
                extra = f"  {d['a_wins']:>5d} {d['b_wins']:>5d} {d['mcnemar_p']:>11.5f}"
            print(f"  {metric:<8} {d['point']:+.4f} {ci:>22}   {sig:>2}{extra}")

    if args.out_json:
        args.out_json.write_text(json.dumps(results, indent=2))
        log.info("Wrote %s", args.out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
