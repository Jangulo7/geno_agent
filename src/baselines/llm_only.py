"""LLM-only (no-retrieval) baseline — Cell O.

A control that isolates the joint contribution of retrieval **and** the agentic
workflow. It asks the *same* locally-served Qwen3-8B that Cell S uses to rank a
case's candidate genes using ONLY the model's parametric knowledge — no PMC
retrieval, no Critic grading, no evidence chunks. Every other input is identical
to the other cells (the patient's HPO phenotypes + the 50-gene candidate list),
and the output matches the schema consumed by ``scripts/eval/aggregate_metrics.py``::

    [{"symbol", "is_causal", "aggregate_confidence", "supporting_chunks": [],
      "final_rank"}, ...]

Design (mirrors the LEA synthesiser for a fair paired comparison):
  * ``temperature=0.0`` + a ``/no_think`` prompt prefix (deterministic decoding).
  * The prompt gives the LLM the same HPO *labels* Cell S's LEA sees, and the
    candidate genes in their per-case seed-shuffled order.
  * Any LLM/parse failure falls back to the **input candidate order**. Because
    that order is per-case seed-shuffled (``18_build_candidate_lists.py``), the
    fallback carries no positional signal about the causal gene — it degrades to
    chance rather than leaking the answer. Fallbacks are logged, never silent.

No new dependencies: reuses ``src.tools.llm`` (the openai->vLLM client) exactly
as Cell S does, so running this baseline needs only the vLLM server already used
for the headline system.
"""

from __future__ import annotations

import json
import logging
from typing import Final

from src.tools.llm import LlmConfig, generate_json

logger = logging.getLogger(__name__)

# Cap HPO labels fed into the prompt (matches the LEA synthesiser's _PROMPT_HPO_CAP).
_PROMPT_HPO_CAP: Final[int] = 12

# 50 candidate genes each with a short rationale; /no_think means no thinking
# tokens, so ~4k output tokens is generous headroom against truncation.
_MAX_OUTPUT_TOKENS: Final[int] = 4096

SYSTEM_PROMPT: Final[str] = (
    "/no_think\n"
    "You are a clinical genomics expert ranking candidate causal genes for a "
    "patient. You are given the patient's HPO phenotypes and a list of candidate "
    "genes. Using ONLY your own knowledge of gene-disease associations (NO external "
    "evidence is provided), rank the genes by how likely each is the single causal "
    "gene for this phenotype profile.\n\n"
    "Output a single JSON ARRAY, ordered by descending confidence. Each element "
    "must have exactly these keys:\n"
    '  "gene" (string): the HGNC gene symbol exactly as provided.\n'
    '  "confidence" (float 0.0-1.0): your belief this gene is the causal one.\n'
    '  "rationale" (string, <=180 chars): one-sentence justification.\n\n'
    "Only one gene is causal. Confidence values should reflect that -- the top "
    "entry should be substantially higher than the rest. Include EVERY input gene "
    "exactly once. Output only the JSON array, no markdown, no prose."
)


def _build_prompt(hpo_labels: list[str], candidate_genes: list[str]) -> str:
    """Compose the user prompt: phenotypes + candidate genes, no evidence."""
    labels_str = ", ".join(hpo_labels[:_PROMPT_HPO_CAP]) or "(no HPO labels)"
    return "\n".join(
        [
            "Patient HPO phenotypes:",
            labels_str,
            "",
            f"Candidate genes to rank ({len(candidate_genes)}):",
            ", ".join(candidate_genes),
            "",
            "Rank ALL candidate genes above by confidence (highest first), using "
            "only your own knowledge. Return JSON only.",
        ]
    )


def _parse_response(parsed: object, valid_genes: set[str]) -> dict[str, float] | None:
    """Validate the LLM's JSON array -> ``{gene: confidence}``.

    Returns ``None`` if the response is malformed (caller falls back to input
    order). Unknown / duplicate genes are ignored; first occurrence wins.
    """
    if not isinstance(parsed, list):
        return None
    out: dict[str, float] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        gene = entry.get("gene")
        if not isinstance(gene, str) or gene not in valid_genes or gene in out:
            continue
        try:
            conf = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        out[gene] = max(0.0, min(1.0, conf))
    return out or None


def _payload_from_order(
    ordered_genes: list[str],
    causal_gene: str,
    confidences: dict[str, float],
) -> list[dict]:
    """Build the aggregator-format payload from a ranked gene ordering."""
    return [
        {
            "symbol": gene,
            "is_causal": gene == causal_gene,
            "aggregate_confidence": round(confidences.get(gene, 0.0), 4),
            "supporting_chunks": [],
            "final_rank": rank,
        }
        for rank, gene in enumerate(ordered_genes, start=1)
    ]


def rank_llm_only(
    case: dict,
    *,
    hpo_labels: list[str],
    llm_cfg: LlmConfig | None = None,
) -> list[dict]:
    """Rank a case's candidate genes with the LLM alone (no retrieval).

    Args:
        case: A test case with ``candidate_genes`` (50 symbols, seed-shuffled)
            and ``causal_gene``.
        hpo_labels: Patient HPO display names (resolved by the caller from the
            HPO ontology, exactly as Cell S's LEA does).
        llm_cfg: Optional LLM server config; defaults to the local vLLM.

    Returns:
        A ranked payload list in ``aggregate_metrics`` schema. On any LLM or
        parse failure, genes are returned in their input (seed-shuffled) order.
    """
    candidate_genes: list[str] = list(case["candidate_genes"])
    causal_gene: str = case["causal_gene"]
    valid = set(candidate_genes)
    case_id = case.get("case_id", "?")

    try:
        parsed, _resp = generate_json(
            _build_prompt(hpo_labels, candidate_genes),
            cfg=llm_cfg,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
    except json.JSONDecodeError as e:
        logger.warning("Cell O %s: invalid JSON, falling back to input order (%s)", case_id, e)
        return _payload_from_order(candidate_genes, causal_gene, {})
    except Exception as e:  # LLM connection/timeout/etc. — never crash the run
        logger.warning(
            "Cell O %s: LLM call failed (%s), falling back to input order",
            case_id,
            type(e).__name__,
        )
        return _payload_from_order(candidate_genes, causal_gene, {})

    confidences = _parse_response(parsed, valid)
    if confidences is None:
        logger.warning("Cell O %s: unparseable ranking, falling back to input order", case_id)
        return _payload_from_order(candidate_genes, causal_gene, {})

    # Rank all candidates: LLM-scored genes by descending confidence, ties and
    # unscored genes broken by original (seed-shuffled) input order — a stable,
    # signal-free tiebreak.
    input_index = {g: i for i, g in enumerate(candidate_genes)}
    ordered = sorted(
        candidate_genes,
        key=lambda g: (-confidences.get(g, 0.0), input_index[g]),
    )
    n_scored = len(confidences)
    if n_scored < len(candidate_genes):
        logger.info(
            "Cell O %s: LLM scored %d/%d genes; rest kept in input order",
            case_id,
            n_scored,
            len(candidate_genes),
        )
    return _payload_from_order(ordered, causal_gene, confidences)
