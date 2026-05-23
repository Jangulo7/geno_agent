"""LLM ablation: replay the LEA prompt against 3 frontier models via OpenRouter.

For each case in a stratified subset, takes the saved Cell S LEA prompts
(`lea_system_prompt`, `lea_user_prompt` — captured during the Cell S re-run)
and re-sends them to ablation LLMs via the OpenRouter API. Records each
model's parsed JSON ranking, top-1 prediction, token counts, latency, and
estimated $ cost. Same retrieval / reranking / LEA prompt as the production
Qwen3-8B run — only the LLM backend changes.

Goal: prove the paper's headline result (Cell S top-1 = 0.726 / 0.858 fair
cohort) is robust across LLM families, not an artifact of Qwen3-8B
specifically.

Models (passed via --models comma-separated):
  qwen/qwen3-32b-instruct       Qwen 32B, same family as production, larger
  anthropic/claude-sonnet-4.6   Cross-family frontier (Anthropic)
  deepseek/deepseek-chat        Cross-family 671B MoE (DeepSeek-V3)

Output: per-case JSON files at data/eval_1050/cell_S_ablation_<model_slug>/
plus a single aggregate JSON for cross-model comparison.

Run::

    PYTHONPATH=. python scripts/eval/run_lea_ablation.py \\
        --responses-dir data/eval_1050/cell_S_responses \\
        --test-cases data/test_cases_1050/test_cases.jsonl \\
        --stratified-n-per-cat 75 \\
        --models "qwen/qwen3-32b-instruct,anthropic/claude-sonnet-4.5,deepseek/deepseek-chat" \\
        --max-concurrency 4
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Final

from openai import APIConnectionError, APITimeoutError, OpenAI

logger = logging.getLogger("lea_ablation")

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"
DEFAULT_MAX_TOKENS: Final[int] = 4096  # LEA needs ~400-800 for 15-gene JSON;
# bumped from 2048 to 4096 after Qwen3-32B truncated mid-response in initial
# smoke (some models pad with whitespace / metadata)
DEFAULT_TEMPERATURE: Final[float] = 0.0

# Pricing per 1M tokens (USD), early 2026 from OpenRouter price page.
# Used to estimate per-case + per-model cost.
PRICING: Final[dict[str, tuple[float, float]]] = {
    # input, output (verified from OpenRouter /v1/models endpoint 2026-05-23)
    "qwen/qwen3-32b": (0.08, 0.28),
    "qwen/qwen3-32b-instruct": (0.08, 0.28),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
    "deepseek/deepseek-chat": (0.32, 0.89),
    "deepseek/deepseek-chat-v3-0324": (0.20, 0.77),
    "deepseek/deepseek-chat-v3.1": (0.21, 0.79),
    "deepseek/deepseek-v3.2": (0.25, 0.38),
    "google/gemini-2.5-pro": (1.25, 5.00),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Rough USD estimate for a single call."""
    if model not in PRICING:
        return 0.0
    in_rate, out_rate = PRICING[model]
    return (tokens_in * in_rate + tokens_out * out_rate) / 1_000_000


def slug_for(model: str) -> str:
    """Make a filesystem-safe slug from an OpenRouter model identifier."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", model)


def load_sidecar(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Bad sidecar %s: %s", path, e)
        return None


def select_cases(
    responses_dir: Path, test_cases_path: Path, n_per_cat: int, seed: int = 42
) -> list[Path]:
    """Stratified sample of sidecar paths."""
    cat_of: dict[str, str] = {}
    with test_cases_path.open() as fh:
        for line in fh:
            if line.strip():
                c = json.loads(line)
                cat_of[c["case_id"]] = c.get("category", "unknown")

    by_cat: dict[str, list[Path]] = {}
    for p in sorted(responses_dir.glob("*.json")):
        cat = cat_of.get(p.stem, "unknown")
        by_cat.setdefault(cat, []).append(p)

    rng = random.Random(seed)
    selected: list[Path] = []
    for cat in sorted(by_cat):
        pool = by_cat[cat]
        n_take = min(n_per_cat, len(pool))
        selected.extend(rng.sample(pool, n_take))
        logger.info("  stratified: %s -> %d sampled (from %d)", cat, n_take, len(pool))
    return selected


def call_one(
    client: OpenAI,
    model: str,
    sys_prompt: str,
    user_prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    use_json_mode: bool = True,
) -> dict:
    """Single OpenRouter call. Returns dict with raw + parsed + metadata.

    Tolerant to common LLM JSON sins: markdown fences, leading text.
    """
    t0 = time.time()
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if use_json_mode:
        # OpenRouter passes response_format through to providers that support it.
        kwargs["response_format"] = {"type": "json_object"}

    try:
        completion = client.chat.completions.create(**kwargs)
    except (APIConnectionError, APITimeoutError) as e:
        return {"error": f"connection:{e}", "latency_s": time.time() - t0}
    except Exception as e:
        # Some providers reject json_object; retry without it.
        if use_json_mode and "response_format" in str(e).lower():
            kwargs.pop("response_format", None)
            try:
                completion = client.chat.completions.create(**kwargs)
            except Exception as e2:
                return {"error": f"call:{type(e2).__name__}:{e2}", "latency_s": time.time() - t0}
        else:
            return {"error": f"call:{type(e).__name__}:{e}", "latency_s": time.time() - t0}

    latency = time.time() - t0
    choice = completion.choices[0]
    text = (choice.message.content or "").strip()
    usage = getattr(completion, "usage", None)
    tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
    tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0

    # Tolerant JSON parsing — handle every shape we've observed across
    # Qwen3-32B, Sonnet 4.6, DeepSeek-V3:
    #   (1) [{"gene":...,"confidence":...,"rationale":...}, ...]   ← spec
    #   (2) {"ranking":[...]} / {"genes":[...]}                     ← wrapped
    #   (3) {"GENE1":{"gene":"GENE1","confidence":...}, ...}        ← Qwen-32B dict
    #   (4) {"GENE1":0.95, "GENE2":0.85, ...}                       ← Qwen-32B compact
    #   (5) {"gene":"GENE1","confidence":...,"rationale":...}        ← Qwen-32B single
    cleaned = text
    for fence in ("```json", "```"):
        if cleaned.startswith(fence):
            cleaned = cleaned[len(fence) :].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[: -len("```")].strip()

    parsed = None
    parse_error = None
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as e:
        parse_error = str(e)
        m = re.search(r"\[\s*\{.*?\}\s*\]", cleaned, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError as e2:
                parse_error = f"{parse_error}; fallback: {e2}"
                obj = None
        else:
            obj = None

    # If we have a JSON object, normalise it to the spec list-of-dicts shape.
    if obj is not None:
        # Detect self-error responses ({"error":"..."} or {"message":"..."})
        if (
            isinstance(obj, dict)
            and set(obj.keys()) & {"error", "message"}
            and not any(isinstance(v, dict) for v in obj.values())
        ):
            parse_error = f"model_self_error:{json.dumps(obj)[:200]}"
            parsed = None
        # Shape (1): list of dicts → spec, use as-is
        elif isinstance(obj, list):
            parsed = obj
        # Shape (2): wrapped list under a known key
        elif isinstance(obj, dict) and any(
            isinstance(obj.get(k), list)
            for k in ("ranking", "genes", "results", "ranked", "output")
        ):
            for k in ("ranking", "genes", "results", "ranked", "output"):
                if isinstance(obj.get(k), list):
                    parsed = obj[k]
                    break
        # Shape (3): dict keyed by gene with full entries as values
        elif isinstance(obj, dict) and all(
            isinstance(v, dict) and ("gene" in v or "confidence" in v) for v in obj.values()
        ):
            # Sort by confidence descending if present, else preserve dict order
            entries = []
            for k, v in obj.items():
                e = dict(v)
                e.setdefault("gene", k)
                entries.append(e)
            entries.sort(key=lambda e: -float(e.get("confidence", 0) or 0))
            parsed = entries
        # Shape (4): dict keyed by gene with numeric confidence values
        elif isinstance(obj, dict) and all(isinstance(v, (int, float)) for v in obj.values()):
            entries = [{"gene": k, "confidence": float(v), "rationale": ""} for k, v in obj.items()]
            entries.sort(key=lambda e: -e["confidence"])
            parsed = entries
        # Shape (5): single object — treat as 1-gene ranking
        elif isinstance(obj, dict) and "gene" in obj:
            parsed = [obj]
        else:
            parse_error = (
                (parse_error or "")
                + f"; unknown_shape:{type(obj).__name__}:"
                + ",".join(list(obj.keys())[:5])
                if isinstance(obj, dict)
                else ""
            )

    return {
        "raw_text": text,
        "parsed": parsed,
        "parse_error": parse_error,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "finish_reason": choice.finish_reason,
        "latency_s": latency,
        "cost_usd": estimate_cost(model, tokens_in, tokens_out),
    }


def evaluate_case(sidecar_path: Path, sidecar: dict, model: str, client: OpenAI) -> dict:
    """Run one model on one case (replay LEA prompt). Return per-case record."""
    case_id = sidecar.get("case_id")
    causal = sidecar.get("causal_gene")
    category = sidecar.get("category")
    lea = sidecar.get("lea_log") or {}
    sys_prompt = lea.get("lea_system_prompt") or ""
    user_prompt = lea.get("lea_user_prompt") or ""

    # Original Qwen3-8B's top-1 for paired comparison
    orig_parsed = lea.get("lea_response_parsed") or []
    orig_top1 = (
        orig_parsed[0].get("gene") if (isinstance(orig_parsed, list) and orig_parsed) else None
    )

    if not sys_prompt or not user_prompt:
        return {
            "case_id": case_id,
            "model": model,
            "error": "missing_lea_prompt",
            "top1": None,
            "causal": causal,
            "top1_correct": False,
        }

    result = call_one(client, model, sys_prompt, user_prompt)
    parsed = result.get("parsed")
    top1 = None
    causal_rank = None
    if isinstance(parsed, list) and parsed:
        # Each entry should be {"gene":...,"confidence":...,"rationale":...}
        top1 = parsed[0].get("gene") if isinstance(parsed[0], dict) else None
        for i, e in enumerate(parsed, 1):
            if isinstance(e, dict) and e.get("gene") == causal:
                causal_rank = i
                break

    return {
        "case_id": case_id,
        "category": category,
        "model": model,
        "causal_gene": causal,
        "orig_qwen3_8b_top1": orig_top1,
        "orig_qwen3_8b_correct": (orig_top1 == causal) and bool(causal),
        "top1": top1,
        "top1_correct": (top1 == causal) and bool(causal),
        "causal_rank": causal_rank,
        "tokens_in": result.get("tokens_in"),
        "tokens_out": result.get("tokens_out"),
        "finish_reason": result.get("finish_reason"),
        "latency_s": result.get("latency_s"),
        "cost_usd": result.get("cost_usd"),
        "parse_error": result.get("parse_error"),
        "error": result.get("error"),
        "raw_text": (result.get("raw_text") or "")[:5000],  # cap for sidecar size
        "parsed_top5": [
            e.get("gene") if isinstance(e, dict) else None
            for e in (parsed[:5] if isinstance(parsed, list) else [])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses-dir", type=Path, required=True)
    parser.add_argument("--test-cases", type=Path, required=True)
    parser.add_argument("--stratified-n-per-cat", type=int, default=75)
    parser.add_argument("--models", required=True, help="Comma-separated OpenRouter model slugs.")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval_1050",
        help="Per-model results go to <out-root>/cell_S_ablation_<slug>/.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval_1050" / "cell_S_ablation_summary.json",
    )
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument(
        "--limit", type=int, default=None, help="Smoke mode: run only first N cases."
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    api_key = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPEN_ROUTER_API env var not set.")
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    logger.info("Models to evaluate: %s", models)

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key, timeout=120.0)

    # Select cases
    selected = select_cases(
        args.responses_dir, args.test_cases, args.stratified_n_per_cat, seed=args.seed
    )
    if args.limit:
        selected = selected[: args.limit]
    logger.info("Cases selected: %d", len(selected))

    # Load all sidecars once
    sidecars = [(p, load_sidecar(p)) for p in selected]
    sidecars = [(p, sc) for p, sc in sidecars if sc is not None]

    # Per-model results
    model_summaries = {}
    for model in models:
        logger.info("=== Model: %s ===", model)
        slug = slug_for(model)
        out_dir = args.out_root / f"cell_S_ablation_{slug}"
        out_dir.mkdir(parents=True, exist_ok=True)

        results: list[dict] = []
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as pool:
            futures = {
                pool.submit(evaluate_case, p, sc, model, client): (p, sc) for p, sc in sidecars
            }
            for done, fut in enumerate(as_completed(futures), start=1):
                _p, sc = futures[fut]
                try:
                    rec = fut.result()
                except Exception as e:
                    rec = {
                        "case_id": sc.get("case_id"),
                        "model": model,
                        "error": f"future:{type(e).__name__}:{e}",
                    }
                results.append(rec)
                (out_dir / f"{sc['case_id']}.json").write_text(json.dumps(rec, indent=2))
                if done % 25 == 0 or done == len(sidecars):
                    n_correct = sum(1 for r in results if r.get("top1_correct"))
                    n_err = sum(1 for r in results if r.get("error"))
                    cum_cost = sum(r.get("cost_usd") or 0 for r in results)
                    logger.info(
                        "  [%d/%d] top-1 so far: %d (%.1f%%) | errors: %d | est cost: $%.2f",
                        done,
                        len(sidecars),
                        n_correct,
                        100 * n_correct / done,
                        n_err,
                        cum_cost,
                    )
        dt = time.time() - t0

        # Per-model aggregate
        scored = [r for r in results if r.get("top1") is not None]
        n_correct = sum(1 for r in scored if r.get("top1_correct"))
        n_correct_orig = sum(1 for r in results if r.get("orig_qwen3_8b_correct"))
        cum_cost = sum(r.get("cost_usd") or 0 for r in results)
        agg = {
            "model": model,
            "n_total": len(sidecars),
            "n_scored": len(scored),
            "n_skipped": len(results) - len(scored),
            "top1_correct_count": n_correct,
            "top1_accuracy": n_correct / len(scored) if scored else 0.0,
            "orig_qwen3_8b_top1_accuracy_on_same_subset": n_correct_orig / len(sidecars),
            "elapsed_seconds": dt,
            "elapsed_minutes": round(dt / 60, 1),
            "total_cost_usd": cum_cost,
            "mean_latency_s": (sum(r.get("latency_s") or 0 for r in scored) / len(scored))
            if scored
            else 0.0,
        }
        model_summaries[model] = agg
        logger.info(
            "  done in %.1f min | top-1 = %.4f (%d/%d) | cost $%.2f",
            dt / 60,
            agg["top1_accuracy"],
            n_correct,
            len(scored),
            cum_cost,
        )

    # Combined summary
    summary_payload = {
        "stratified_n_per_cat": args.stratified_n_per_cat,
        "n_cases_total": len(sidecars),
        "seed": args.seed,
        "models": list(model_summaries.keys()),
        "per_model": model_summaries,
        "total_cost_usd": sum(m["total_cost_usd"] for m in model_summaries.values()),
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary_payload, indent=2))
    logger.info("=== COMBINED SUMMARY ===")
    for model, agg in model_summaries.items():
        logger.info(
            "  %s  top-1=%.4f  n=%d  cost=$%.2f",
            model,
            agg["top1_accuracy"],
            agg["n_scored"],
            agg["total_cost_usd"],
        )
    logger.info("Total cost: $%.2f", summary_payload["total_cost_usd"])
    logger.info("Summary: %s", args.summary_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
