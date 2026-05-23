"""DeepEval hallucination metric for Cell S (LEA).

Computes the hallucination rate of LEA's free-text responses by
comparing each response to its retrieved contexts via GPT-4o judge.

DeepEval ``HallucinationMetric`` definition (from
https://docs.confident-ai.com/docs/metrics-hallucination):

    A score of 1 means the actual_output contains no hallucination —
    every claim is supported by the contexts. A score of 0 means
    every claim is hallucinated.

We report the *complement* (1 - score) as the hallucination *rate*
plus the raw score for compatibility.

Project-rule deviation
======================

``CLAUDE.md`` mandates "No cloud LLM API in any code path." Using
GPT-4o as a DeepEval judge is a deliberate deviation **for evaluation
only**; the production pipeline (Cells D, L, S) remains all-local.
Documented in paper_extension_plan_v3.md §3.5.

Usage
=====

Pre-flight::

    export OPENAI_API_KEY=sk-...
    pip install deepeval

Cell S (n=1,047, ~2-3 h API)::

    PYTHONPATH=. python scripts/eval/run_deepeval.py \\
        --responses-dir data/eval_1050/cell_S_responses \\
        --out data/eval_1050/deepeval_cell_S.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

logger = logging.getLogger("deepeval_eval")

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

MAX_CONTEXTS_PER_CASE: Final[int] = 45
MAX_CHARS_PER_CONTEXT: Final[int] = 1500


def _build_contexts(sidecar: dict) -> list[str]:
    """Build retrieved-context list (mirrors run_ragas._build_contexts)."""
    lea_log = sidecar.get("lea_log") or {}
    evidence = lea_log.get("lea_evidence_per_gene")
    if not evidence:
        evidence = sidecar.get("retrieved_per_gene", {})

    contexts: list[str] = []
    for gene, chunks in evidence.items():
        for ch in chunks:
            text = (ch.get("text") or "").strip()
            if not text:
                continue
            text = text[:MAX_CHARS_PER_CONTEXT]
            pmid = ch.get("source_pmcid")
            prefix = f"[gene={gene}"
            if pmid:
                prefix += f" PMCID={pmid}"
            prefix += "] "
            contexts.append(prefix + text)
            if len(contexts) >= MAX_CONTEXTS_PER_CASE:
                return contexts
    return contexts


def _build_input(sidecar: dict) -> str:
    """Build the patient query string."""
    lea_log = sidecar.get("lea_log") or {}
    hpo_labels = lea_log.get("hpo_labels") or sidecar.get("hpo_terms", [])
    hpo_str = ", ".join(hpo_labels)
    return (
        f"A rare-disease patient presents with: {hpo_str}. "
        f"Which gene from the candidate list is most likely causal?"
    )


def _build_actual_output(sidecar: dict) -> str | None:
    """Get LEA's raw response text (the model's reasoning)."""
    lea_log = sidecar.get("lea_log") or {}
    raw = lea_log.get("lea_response_raw")
    if not raw:
        return None
    return raw[:5000]


def _load_sidecars(responses_dir: Path, limit: int | None) -> list[dict]:
    """Read all sidecar JSONs from a responses directory."""
    sidecars: list[dict] = []
    for p in sorted(responses_dir.glob("*.json")):
        try:
            sidecars.append(json.loads(p.read_text()))
        except json.JSONDecodeError as e:
            logger.warning("Skipping malformed sidecar %s: %s", p, e)
        if limit and len(sidecars) >= limit:
            break
    return sidecars


def _evaluate_one(sidecar: dict, judge_model: str):
    """Run HallucinationMetric on one case.

    Returns:
        Dict with case_id, hallucination_score (0=all hallucinated,
        1=fully grounded), hallucination_rate (= 1 - score), reason.
    """
    from deepeval.metrics import HallucinationMetric
    from deepeval.test_case import LLMTestCase

    case_id = sidecar.get("case_id", "?")
    contexts = _build_contexts(sidecar)
    actual_output = _build_actual_output(sidecar)
    user_input = _build_input(sidecar)

    if not contexts or not actual_output:
        return {
            "case_id": case_id,
            "hallucination_score": None,
            "hallucination_rate": None,
            "reason": "missing_contexts_or_output",
        }

    test_case = LLMTestCase(
        input=user_input,
        actual_output=actual_output,
        context=contexts,
    )

    metric = HallucinationMetric(threshold=0.5, model=judge_model, include_reason=True)
    try:
        metric.measure(test_case)
        return {
            "case_id": case_id,
            "hallucination_score": float(metric.score) if metric.score is not None else None,
            "hallucination_rate": (1.0 - float(metric.score)) if metric.score is not None else None,
            "reason": getattr(metric, "reason", None),
        }
    except Exception as e:
        return {
            "case_id": case_id,
            "hallucination_score": None,
            "hallucination_rate": None,
            "reason": f"error:{type(e).__name__}:{str(e)[:200]}",
        }


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--responses-dir",
        type=Path,
        required=True,
        help="Sidecar JSON directory from rerank_inside_d.py --responses-dir.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON path for per-case + aggregate hallucination scores.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="gpt-4o-2024-08-06",
        help="OpenAI model name (default: gpt-4o-2024-08-06).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N sidecars (smoke/debug).",
    )
    parser.add_argument(
        "--stratified-n-per-cat",
        type=int,
        default=None,
        help="Sample N cases per MONDO category (seed 42). Requires --test-cases.",
    )
    parser.add_argument(
        "--test-cases",
        type=Path,
        default=None,
        help="test_cases.jsonl for per-case category labels (needed by --stratified-n-per-cat).",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=8,
        help="Concurrent judge API calls (default 8).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY env var not set. Set it before running.")
        return 2

    try:
        import deepeval  # noqa: F401  - import to detect availability
    except ImportError:
        logger.error("DeepEval missing. Install with: pip install deepeval")
        return 2

    logger.info("=== DeepEval hallucination ===")
    logger.info("  responses dir: %s", args.responses_dir)
    logger.info("  output:        %s", args.out)
    logger.info("  judge model:   %s", args.judge_model)

    sidecars = _load_sidecars(args.responses_dir, args.limit)
    logger.info("  sidecars:      %d", len(sidecars))
    if not sidecars:
        logger.error("No sidecars found in %s", args.responses_dir)
        return 1

    # Optional stratified sub-sample by MONDO category (seed 42).
    if args.stratified_n_per_cat is not None:
        if args.test_cases is None:
            logger.error("--stratified-n-per-cat requires --test-cases.")
            return 2
        import random
        from collections import defaultdict

        cat_of: dict[str, str] = {}
        with args.test_cases.open() as fh:
            for line in fh:
                if line.strip():
                    c = json.loads(line)
                    cat_of[c["case_id"]] = c.get("category", "unknown")
        by_cat: dict[str, list] = defaultdict(list)
        for sc in sidecars:
            by_cat[cat_of.get(sc.get("case_id"), "unknown")].append(sc)
        rng = random.Random(42)
        sampled: list[dict] = []
        for cat in sorted(by_cat):
            pool = by_cat[cat]
            n_take = min(args.stratified_n_per_cat, len(pool))
            sampled.extend(rng.sample(pool, n_take))
            logger.info("  stratified: %s -> %d sampled (from %d)", cat, n_take, len(pool))
        sidecars = sampled
        logger.info("  sidecars after stratified sample: %d", len(sidecars))

    results: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.max_concurrency) as pool:
        # `executor.map` preserves input order, easy to log progress.
        for i, res in enumerate(
            pool.map(lambda sc: _evaluate_one(sc, args.judge_model), sidecars),
            start=1,
        ):
            results.append(res)
            if i % 25 == 0:
                logger.info(
                    "  [%d/%d] %s score=%s",
                    i,
                    len(sidecars),
                    res["case_id"],
                    None
                    if res["hallucination_score"] is None
                    else f"{res['hallucination_score']:.3f}",
                )
    dt = time.time() - t0
    logger.info("DeepEval done in %.1f min", dt / 60.0)

    scored = [r for r in results if r["hallucination_score"] is not None]
    if scored:
        mean_score = sum(r["hallucination_score"] for r in scored) / len(scored)
        mean_rate = 1.0 - mean_score
    else:
        mean_score, mean_rate = None, None

    out_payload = {
        "judge_model": args.judge_model,
        "n_cases_total": len(sidecars),
        "n_cases_scored": len(scored),
        "n_cases_skipped": len(results) - len(scored),
        "elapsed_seconds": dt,
        "aggregate_mean_hallucination_score": mean_score,
        "aggregate_mean_hallucination_rate": mean_rate,
        "per_case": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_payload, indent=2))

    logger.info("=== Aggregate ===")
    logger.info("  scored cases:         %d / %d", len(scored), len(sidecars))
    if mean_score is not None:
        logger.info("  mean groundedness:    %.3f", mean_score)
        logger.info("  mean halluc. rate:    %.3f", mean_rate)
    logger.info("Output: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
