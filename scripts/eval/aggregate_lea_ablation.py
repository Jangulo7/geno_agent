"""Cross-LLM aggregation for the LEA ablation (Q1-B).

Loads per-case results for the production Qwen3-8B (from cell_S_responses)
plus each ablation model (cell_S_ablation_<slug>/), restricted to the
same n=300 stratified cohort, and computes:

  * Per-model top-1, top-5, MRR, NDCG@10 with paired-bootstrap 95 % CIs
  * Paired Δ vs Qwen3-8B production (with exact McNemar) per ablation model
  * Per-MONDO category breakdown
  * Stratified by Thread D's annotation-overlap flag
  * A summary table ready to drop into the paper Methods Table 2

Outputs:
  data/eval_1050/_results_lea_ablation.json
  data/eval_1050/_results_lea_ablation.md

Run::

    PYTHONPATH=. python scripts/eval/aggregate_lea_ablation.py
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval.aggregate_metrics import (  # noqa: E402
    ndcg_at_10,
    reciprocal_rank,
    top_k_hit,
)
from scripts.eval.paired_diff import (  # noqa: E402
    mcnemar_exact_p,
    paired_bootstrap_diff,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ablation_agg")

DEFAULT_PROD_DIR: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_S_responses"
DEFAULT_ABLATION_ROOT: Final[Path] = PROJECT_ROOT / "data" / "eval_1050"
DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
DEFAULT_OUT_JSON: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "_results_lea_ablation.json"
DEFAULT_OUT_MD: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "_results_lea_ablation.md"


def load_production_metrics(prod_dir: Path, case_ids: set[str]) -> dict[str, dict[str, float]]:
    """Return per-case metrics for Cell S production (Qwen3-8B) on case_ids."""
    out: dict[str, dict[str, float]] = {}
    for case_id in case_ids:
        path = prod_dir / f"{case_id}.json"
        if not path.exists():
            continue
        sc = json.loads(path.read_text())
        causal = sc.get("causal_gene")
        parsed = (sc.get("lea_log") or {}).get("lea_response_parsed") or []
        rank = None
        if isinstance(parsed, list):
            for i, e in enumerate(parsed, 1):
                if isinstance(e, dict) and e.get("gene") == causal:
                    rank = i
                    break
        out[case_id] = {
            "rank": rank,
            "top1": float(top_k_hit(rank, 1)),
            "top5": float(top_k_hit(rank, 5)),
            "top10": float(top_k_hit(rank, 10)),
            "mrr": reciprocal_rank(rank),
            "ndcg10": ndcg_at_10(rank),
            "category": sc.get("category", "unknown"),
        }
    return out


def load_ablation_metrics(ablation_dir: Path) -> dict[str, dict[str, float]]:
    """Per-case metrics for one ablation-model directory."""
    out: dict[str, dict[str, float]] = {}
    for path in sorted(ablation_dir.glob("*.json")):
        rec = json.loads(path.read_text())
        rank = rec.get("causal_rank")  # may be None if causal not in returned ranking
        out[path.stem] = {
            "rank": rank,
            "top1": float(top_k_hit(rank, 1)),
            "top5": float(top_k_hit(rank, 5)),
            "top10": float(top_k_hit(rank, 10)),
            "mrr": reciprocal_rank(rank),
            "ndcg10": ndcg_at_10(rank),
            "category": rec.get("category", "unknown"),
            "had_error": bool(rec.get("error") or rec.get("parse_error")),
            "tokens_in": rec.get("tokens_in", 0),
            "tokens_out": rec.get("tokens_out", 0),
            "latency_s": rec.get("latency_s", 0.0),
            "cost_usd": rec.get("cost_usd", 0.0) or 0.0,
        }
    return out


def per_cell_bootstrap(
    values: dict[str, dict], case_ids: list[str], n_resamples: int = 1000, seed: int = 42
) -> dict[str, tuple]:
    """Single-cell bootstrap CI for each metric."""
    import random

    out: dict[str, tuple] = {}
    if not case_ids:
        return dict.fromkeys(("top1", "top5", "top10", "mrr", "ndcg10"), (0.0, 0.0, 0.0))
    rng = random.Random(seed)
    for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
        vec = [values[c][metric] for c in case_ids if c in values]
        if not vec:
            out[metric] = (0.0, 0.0, 0.0)
            continue
        n = len(vec)
        point = sum(vec) / n
        means = []
        for _ in range(n_resamples):
            s = 0.0
            for _ in range(n):
                s += vec[rng.randrange(n)]
            means.append(s / n)
        means.sort()
        lo = means[max(0, math.floor(0.025 * n_resamples))]
        hi = means[min(n_resamples - 1, math.ceil(0.975 * n_resamples) - 1)]
        out[metric] = (round(point, 4), round(lo, 4), round(hi, 4))
    return out


def paired_compare(a_vals: dict, b_vals: dict, case_ids: list[str]) -> dict:
    """Paired Δ A - B + bootstrap CI + McNemar on top-1."""
    common = [c for c in case_ids if c in a_vals and c in b_vals]
    out = {"n": len(common), "metrics": {}}
    for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
        diffs = [a_vals[c][metric] - b_vals[c][metric] for c in common]
        point, lo, hi = paired_bootstrap_diff(diffs)
        d = {
            "point": round(point, 4),
            "ci_lo": round(lo, 4),
            "ci_hi": round(hi, 4),
            "significant": lo > 0 or hi < 0,
        }
        if metric in ("top1", "top5", "top10"):
            a_wins = sum(1 for c in common if a_vals[c][metric] > b_vals[c][metric])
            b_wins = sum(1 for c in common if a_vals[c][metric] < b_vals[c][metric])
            d.update(
                {
                    "a_wins": a_wins,
                    "b_wins": b_wins,
                    "mcnemar_p": round(mcnemar_exact_p(a_wins, b_wins), 5),
                }
            )
        out["metrics"][metric] = d
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prod-dir", type=Path, default=DEFAULT_PROD_DIR)
    parser.add_argument("--ablation-root", type=Path, default=DEFAULT_ABLATION_ROOT)
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = parser.parse_args()

    # Discover ablation DIRECTORIES (the glob also matches the summary JSON).
    ablation_dirs = sorted(d for d in args.ablation_root.glob("cell_S_ablation_*") if d.is_dir())
    if not ablation_dirs:
        log.error("No ablation dirs found in %s", args.ablation_root)
        return 1
    log.info("Ablation dirs: %s", [d.name for d in ablation_dirs])

    # Use the FIRST ablation dir's case ids as the canonical n-cohort
    cohort_case_ids: set[str] = {p.stem for p in ablation_dirs[0].glob("*.json")}
    log.info("Cohort size: %d (from %s)", len(cohort_case_ids), ablation_dirs[0].name)

    # Sanity: all ablation dirs should have the same case_ids
    for d in ablation_dirs[1:]:
        d_ids = {p.stem for p in d.glob("*.json")}
        missing = cohort_case_ids - d_ids
        extra = d_ids - cohort_case_ids
        if missing or extra:
            log.warning(
                "Cohort mismatch in %s: missing=%d extra=%d", d.name, len(missing), len(extra)
            )

    # Build per-model metrics dict
    models: dict[str, dict[str, dict]] = {}
    models["qwen3-8b (production)"] = load_production_metrics(args.prod_dir, cohort_case_ids)
    for d in ablation_dirs:
        slug = d.name.replace("cell_S_ablation_", "")
        models[slug] = load_ablation_metrics(d)
        log.info("Model %s: %d cases loaded", slug, len(models[slug]))

    # Load overlap flag
    overlap_records = json.loads(args.overlap.read_text())["records"]
    overlap_of: dict[str, int] = {r["case_id"]: r["overlap"] for r in overlap_records}
    category_of: dict[str, str] = {r["case_id"]: r["category"] for r in overlap_records}

    # Subsets
    all_ids = sorted(cohort_case_ids)
    overlap_absent = [c for c in all_ids if overlap_of.get(c) == 0]
    overlap_present = [c for c in all_ids if overlap_of.get(c) == 1]
    cats = sorted({category_of.get(c, "unknown") for c in all_ids})
    cat_ids = {c: [cid for cid in all_ids if category_of.get(cid) == c] for c in cats}

    subsets = {
        "__all__": all_ids,
        "overlap_present": overlap_present,
        "overlap_absent": overlap_absent,
    }
    for c in cats:
        subsets[f"cat_{c}"] = cat_ids[c]

    # Per-model bootstrap on each subset
    per_cell: dict[str, dict[str, dict]] = {}
    for subset, ids in subsets.items():
        per_cell[subset] = {}
        for model in models:
            per_cell[subset][model] = per_cell_bootstrap(models[model], ids)

    # Paired Δ vs production
    paired: dict[str, dict[str, dict]] = {}
    prod_key = "qwen3-8b (production)"
    for subset, ids in subsets.items():
        if not subset.startswith("__") and not subset.startswith("overlap"):
            continue
        paired[subset] = {}
        for model in models:
            if model == prod_key:
                continue
            paired[subset][f"{model}_vs_prod"] = paired_compare(
                models[model], models[prod_key], ids
            )

    # Per-model cost + latency summary
    cost_summary: dict[str, dict] = {}
    for model in models:
        if model == prod_key:
            continue  # no API cost for local production
        vals = models[model].values()
        total_cost = sum(v.get("cost_usd", 0) for v in vals)
        n_err = sum(1 for v in vals if v.get("had_error"))
        avg_lat = (sum(v.get("latency_s", 0) for v in vals) / len(vals)) if vals else 0
        cost_summary[model] = {
            "total_cost_usd": round(total_cost, 4),
            "mean_latency_s": round(avg_lat, 2),
            "n_with_parse_or_api_error": n_err,
        }

    # Write JSON
    payload = {
        "cohort_size": len(all_ids),
        "subsets": {k: len(v) for k, v in subsets.items()},
        "models": list(models.keys()),
        "per_cell": per_cell,
        "paired_vs_production": paired,
        "cost_summary": cost_summary,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2))
    log.info("Wrote %s", args.out_json)

    # Write markdown
    lines: list[str] = []
    lines.append(f"# LEA ablation — cross-LLM comparison (n = {len(all_ids)})")
    lines.append("")
    lines.append(
        f"Cohort: n = {len(all_ids)} stratified (subset of the full n = 1,047 evaluation). "
        f"overlap_absent = {len(overlap_absent)}, overlap_present = {len(overlap_present)}."
    )
    lines.append("")
    lines.append(
        "Production = Qwen3-8B run on the same cases (extracted from "
        "data/eval_1050/cell_S_responses/). Ablation models replayed the "
        "saved LEA prompts via OpenRouter — same retrieval, same rerank, "
        "same chunks; only the LLM backend differs."
    )
    lines.append("")

    def fmt(p, lo, hi):
        return f"{p:.3f} [{lo:.3f}, {hi:.3f}]"

    for subset_name in ("__all__", "overlap_absent", "overlap_present"):
        n_sub = len(subsets[subset_name])
        lines.append(f"## {subset_name} (n = {n_sub})")
        lines.append("")
        lines.append("| Model | top-1 | top-5 | top-10 | MRR | NDCG@10 |")
        lines.append("|---|---|---|---|---|---|")
        for model in models:
            mp = per_cell[subset_name].get(model, {})
            if not mp:
                continue
            lines.append(
                f"| {model} | "
                f"{fmt(*mp['top1'])} | "
                f"{fmt(*mp['top5'])} | "
                f"{fmt(*mp['top10'])} | "
                f"{fmt(*mp['mrr'])} | "
                f"{fmt(*mp['ndcg10'])} |"
            )
        lines.append("")
        if paired.get(subset_name):
            lines.append("### Paired Δ vs Qwen3-8B production")
            lines.append("")
            lines.append("| Model | Δ top-1 | 95 % CI | A>B | B>A | McNemar p | sig |")
            lines.append("|---|---:|---|---:|---:|---:|:-:|")
            for cmp_key, comp in paired[subset_name].items():
                m = comp["metrics"]["top1"]
                sig = "★" if m["significant"] else ""
                ci = f"[{m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}]"
                aw = m.get("a_wins", "")
                bw = m.get("b_wins", "")
                mp = f"{m['mcnemar_p']:.5f}" if "mcnemar_p" in m else ""
                model_name = cmp_key.replace("_vs_prod", "")
                lines.append(
                    f"| {model_name} | {m['point']:+.4f} | {ci} | {aw} | {bw} | {mp} | {sig} |"
                )
            lines.append("")

    # Per-MONDO category for the __all__ cohort
    lines.append("## Per-MONDO breakdown — top-1 (point estimate only)")
    lines.append("")
    lines.append("| Model | " + " | ".join(f"{c} n={len(cat_ids[c])}" for c in cats) + " |")
    lines.append("|---|" + "|".join("---" for _ in cats) + "|")
    for model in models:
        row = [model]
        for c in cats:
            mp = per_cell.get(f"cat_{c}", {}).get(model, {})
            row.append(f"{mp.get('top1', (0, 0, 0))[0]:.3f}" if mp else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    if cost_summary:
        lines.append("## Cost + latency per ablation model (n cohort)")
        lines.append("")
        lines.append("| Model | Total $ | Mean latency (s) | API/parse errors |")
        lines.append("|---|---:|---:|---:|")
        for model, s in cost_summary.items():
            lines.append(
                f"| {model} | {s['total_cost_usd']} | {s['mean_latency_s']} | "
                f"{s['n_with_parse_or_api_error']} |"
            )
        lines.append("")

    args.out_md.write_text("\n".join(lines))
    log.info("Wrote %s", args.out_md)

    # Console summary
    print("\n=== LEA ablation — top-1 by subset ===")
    for subset_name in ("__all__", "overlap_absent", "overlap_present"):
        n_sub = len(subsets[subset_name])
        print(f"\n  {subset_name} (n={n_sub}):")
        for model in models:
            mp = per_cell[subset_name].get(model, {})
            if not mp:
                continue
            p, lo, hi = mp["top1"]
            print(f"    {model:50s}  top-1 = {p:.3f}  [{lo:.3f}, {hi:.3f}]")

    print("\n=== Paired Δ vs production on __all__ ===")
    if "__all__" in paired:
        for cmp_key, comp in paired["__all__"].items():
            m = comp["metrics"]["top1"]
            sig = "★" if m["significant"] else " "
            model_name = cmp_key.replace("_vs_prod", "")
            print(
                f"  {model_name:50s}  Δ={m['point']:+.4f}  CI=[{m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}]  "
                f"McNemar p={m.get('mcnemar_p', float('nan')):.5f}  {sig}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
