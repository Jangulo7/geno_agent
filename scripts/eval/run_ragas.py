"""RAGAS evaluation pipeline for Cell L (retrieval) and Cell S (LEA).

Computes RAG-quality metrics over the per-case sidecar JSONs produced by
``scripts/eval/rerank_inside_d.py --responses-dir <dir>``. Uses GPT-4o
(``gpt-4o-2024-08-06``) as the LLM judge via the OpenAI API.

Metrics computed
================

For Cell L (retrieval only — no LLM answer):
  * **context_precision** — fraction of retrieved chunks that are
    relevant to the patient phenotype query.
  * **context_recall** — fraction of the ground-truth's relevant claims
    present in the retrieved chunks.

For Cell S (LEA — has free-text LLM response):
  * **faithfulness** — fraction of LEA's claims supported by the
    retrieved chunks.
  * **answer_relevance** — semantic alignment of LEA's response to the
    patient phenotype query.
  * context_precision, context_recall (same as Cell L).

Project-rule deviation
======================

``CLAUDE.md`` mandates "No cloud LLM API in any code path." Using
GPT-4o as a RAGAS judge is a deliberate deviation **for evaluation
only**; the production pipeline (Cells D, L, S) remains all-local.
Documented in paper_extension_plan_v3.md §3.5.

Usage
=====

Pre-flight::

    export OPENAI_API_KEY=sk-...
    pip install ragas langchain-openai

Cell L (retrieval-only metrics, n=1,047, ~3-4 h API)::

    PYTHONPATH=. python scripts/eval/run_ragas.py \\
        --responses-dir data/eval_1050/cell_L_responses \\
        --out data/eval_1050/ragas_cell_L.json \\
        --metrics context_precision,context_recall

Cell S (full metrics, n=1,047, ~5-6 h API)::

    PYTHONPATH=. python scripts/eval/run_ragas.py \\
        --responses-dir data/eval_1050/cell_S_responses \\
        --out data/eval_1050/ragas_cell_S.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Final

logger = logging.getLogger("ragas_eval")

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

# All available metrics — keep the names matching RAGAS exactly.
ALL_METRICS: Final[list[str]] = [
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_relevance",
]
# Cell-L cannot compute LLM-answer-dependent metrics.
RETRIEVAL_ONLY: Final[set[str]] = {"context_precision", "context_recall"}

# Token budget: per RAGAS docs, faithfulness + answer_relevance generate
# several sub-questions per case. Cap context length conservatively to
# stay within GPT-4o's 128k context.
MAX_CONTEXTS_PER_CASE: Final[int] = 20  # ~50 % cost vs 45; covers top-5 genes x 3 chunks +
# top-5 genes x 1 chunk → enough for paper Methods.
# See plan v3 §3.6 (budget capped at $100, 2026-05-23).
MAX_CHARS_PER_CONTEXT: Final[int] = 1500  # ~375 tokens


def _build_question(sidecar: dict) -> str:
    """Build a patient-phenotype query string from HPO labels.

    Args:
        sidecar: One sidecar JSON dict from rerank_inside_d.py.

    Returns:
        Free-text question describing the patient, formulated as a
        gene-prioritisation prompt to give the LLM judge the right
        framing for relevance/faithfulness judgements.
    """
    # Prefer LEA's resolved labels; fall back to raw HPO IDs.
    lea_log = sidecar.get("lea_log") or {}
    hpo_labels = lea_log.get("hpo_labels") or sidecar.get("hpo_terms", [])
    hpo_str = ", ".join(hpo_labels)
    return (
        f"A rare-disease patient presents with the following phenotypic features: "
        f"{hpo_str}. Which gene from the candidate list is most likely causal "
        f"for this patient's disease, based on the published medical literature?"
    )


def _build_contexts(sidecar: dict) -> list[str]:
    """Build the retrieved-context list for RAGAS.

    Strategy: prefer the LEA evidence (top-15 genes x top-3 chunks)
    since that's what the LLM actually saw. Fall back to the full
    retrieved set (Cell L sidecars have no LEA log).

    Args:
        sidecar: Sidecar JSON dict.

    Returns:
        List of context strings, ordered by gene-then-chunk. Total
        capped at ``MAX_CONTEXTS_PER_CASE`` items, each truncated
        to ``MAX_CHARS_PER_CONTEXT`` characters.
    """
    lea_log = sidecar.get("lea_log") or {}
    evidence = lea_log.get("lea_evidence_per_gene")
    if not evidence:
        # Cell L fallback: use the full per-gene retrieval (cap aggressively).
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


def _build_answer(sidecar: dict) -> str | None:
    """Build the LLM-answer string for RAGAS.

    For Cell S, this is LEA's raw text response (the reasoning the LLM
    produced). For Cell L (no LEA), returns None — only retrieval
    metrics apply.

    Args:
        sidecar: Sidecar JSON dict.

    Returns:
        Answer text or ``None`` if no LEA response is available
        (Cell L, or Cell S fallback cases).
    """
    lea_log = sidecar.get("lea_log") or {}
    raw = lea_log.get("lea_response_raw")
    if not raw:
        return None
    # Cap to avoid blowing up the judge context window. LEA's typical
    # response is ~1-2k chars; cap at 5k to be safe.
    return raw[:5000]


def _build_reference(sidecar: dict) -> str:
    """Build the ground-truth reference string for context_recall.

    Args:
        sidecar: Sidecar JSON dict.

    Returns:
        Reference text describing the true causal gene (used by RAGAS
        to compute context_recall as "fraction of reference's claims
        present in retrieved contexts").
    """
    causal = sidecar.get("causal_gene", "")
    category = sidecar.get("category") or "rare disease"
    return (
        f"The causal gene for this patient's {category} disease is {causal}. "
        f"The retrieved evidence should contain phenotype-gene associations "
        f"linking {causal} to the patient's HPO features."
    )


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


def _build_sample(sidecar: dict, metric_names: list[str]):
    """Build a RAGAS SingleTurnSample from one sidecar.

    Args:
        sidecar: One sidecar JSON.
        metric_names: Which metrics will be computed (controls what
            fields must be populated).

    Returns:
        ragas.SingleTurnSample or None if required fields missing.
    """
    from ragas import SingleTurnSample

    contexts = _build_contexts(sidecar)
    if not contexts:
        return None  # cannot evaluate without contexts

    question = _build_question(sidecar)
    reference = _build_reference(sidecar)

    fields: dict = {
        "user_input": question,
        "retrieved_contexts": contexts,
        "reference": reference,
    }

    # Faithfulness + answer_relevance need a free-text answer.
    needs_answer = any(m in {"faithfulness", "answer_relevance"} for m in metric_names)
    if needs_answer:
        answer = _build_answer(sidecar)
        if answer is None:
            # Cell L: no answer. If only retrieval metrics requested, OK.
            # If faithfulness/answer_relevance requested but no answer,
            # skip this case for those metrics.
            return None
        fields["response"] = answer

    return SingleTurnSample(**fields)


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--responses-dir",
        type=Path,
        required=True,
        help="Sidecar JSON directory produced by rerank_inside_d.py --responses-dir.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON path for per-case scores + aggregate.",
    )
    parser.add_argument(
        "--metrics",
        type=str,
        default=",".join(ALL_METRICS),
        help=f"Comma-separated metric names. Default: all ({ALL_METRICS}).",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="gpt-4o-2024-08-06",
        help="OpenAI model name for the LLM judge (default: gpt-4o-2024-08-06).",
    )
    parser.add_argument(
        "--judge-temperature",
        type=float,
        default=0.0,
        help="Judge LLM temperature (default 0.0 for deterministic scoring).",
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
        help="Concurrent judge API calls (default 8; respects OpenAI tier limits).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY env var not set. Set it before running.")
        return 2

    requested = [m.strip() for m in args.metrics.split(",") if m.strip()]
    unknown = [m for m in requested if m not in ALL_METRICS]
    if unknown:
        logger.error("Unknown metrics: %s. Valid: %s", unknown, ALL_METRICS)
        return 2

    # langchain-community 0.4.x moved the Vertex AI integration into a
    # separate langchain-google-vertexai package, but ragas 0.2-0.4.x still
    # imports ChatVertexAI from the old path. We shim a no-op replacement
    # so the import succeeds — we don't use Vertex AI anywhere (GPT-4o judge).
    import types as _types

    _vertex_shim = _types.ModuleType("langchain_community.chat_models.vertexai")

    class _ChatVertexAIShim:
        """No-op placeholder so ragas can import the symbol."""

    _vertex_shim.ChatVertexAI = _ChatVertexAIShim
    sys.modules["langchain_community.chat_models.vertexai"] = _vertex_shim

    # Import RAGAS lazily so the script can be inspected without the dep.
    try:
        from langchain_openai import ChatOpenAI
        from ragas import EvaluationDataset, evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
    except ImportError as e:
        logger.error(
            "RAGAS dependencies missing. Install with: pip install ragas langchain-openai. (%s)",
            e,
        )
        return 2

    metric_map = {
        "faithfulness": Faithfulness,
        "context_precision": ContextPrecision,
        "context_recall": ContextRecall,
        "answer_relevance": AnswerRelevancy,
    }

    logger.info("=== RAGAS evaluation ===")
    logger.info("  responses dir: %s", args.responses_dir)
    logger.info("  output:        %s", args.out)
    logger.info("  metrics:       %s", requested)
    logger.info("  judge model:   %s @ temperature=%s", args.judge_model, args.judge_temperature)

    sidecars = _load_sidecars(args.responses_dir, args.limit)
    logger.info("  sidecars:      %d", len(sidecars))
    if not sidecars:
        logger.error("No sidecars found in %s", args.responses_dir)
        return 1

    # Optional: stratified sub-sample by MONDO category (seed 42).
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
            sampled_cat = rng.sample(pool, n_take)
            sampled.extend(sampled_cat)
            logger.info("  stratified: %s -> %d sampled (from %d)", cat, n_take, len(pool))
        sidecars = sampled
        logger.info("  sidecars after stratified sample: %d", len(sidecars))

    # Build samples; track which cases are skipped (no answer + non-retrieval metric).
    samples = []
    case_ids = []
    skipped = []
    for sc in sidecars:
        sample = _build_sample(sc, requested)
        if sample is None:
            skipped.append(sc.get("case_id", "?"))
            continue
        samples.append(sample)
        case_ids.append(sc.get("case_id", "?"))
    logger.info("  evaluable:     %d (%d skipped — no answer/contexts)", len(samples), len(skipped))

    dataset = EvaluationDataset(samples=samples)
    judge_llm = LangchainLLMWrapper(
        ChatOpenAI(model=args.judge_model, temperature=args.judge_temperature)
    )
    metrics = [metric_map[m](llm=judge_llm) for m in requested]

    from ragas.run_config import RunConfig

    run_config = RunConfig(max_workers=args.max_concurrency, timeout=120)
    logger.info(
        "Calling RAGAS evaluate (n=%d x %d metrics, max_workers=%d)...",
        len(samples),
        len(metrics),
        args.max_concurrency,
    )
    t0 = time.time()
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=judge_llm,
        raise_exceptions=False,
        run_config=run_config,
    )
    dt = time.time() - t0
    logger.info("RAGAS evaluate completed in %.1f min", dt / 60.0)

    # Serialize per-case + aggregate to JSON.
    df = result.to_pandas()
    per_case_records = []
    for i, cid in enumerate(case_ids):
        row = df.iloc[i].to_dict() if i < len(df) else {}
        per_case_records.append(
            {
                "case_id": cid,
                **{k: (None if (isinstance(v, float) and (v != v)) else v) for k, v in row.items()},
            }
        )
    aggregate = {
        m.name: float(df[m.name].dropna().mean()) if m.name in df else None for m in metrics
    }

    out_payload = {
        "judge_model": args.judge_model,
        "judge_temperature": args.judge_temperature,
        "metrics": requested,
        "n_cases_total": len(sidecars),
        "n_cases_evaluated": len(samples),
        "n_cases_skipped": len(skipped),
        "skipped_case_ids": skipped[:20],
        "elapsed_seconds": dt,
        "aggregate_mean": aggregate,
        "per_case": per_case_records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_payload, indent=2))

    logger.info("=== Aggregate scores ===")
    for k, v in aggregate.items():
        logger.info("  %s: %.3f", k, v if v is not None else float("nan"))
    logger.info("Output: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
