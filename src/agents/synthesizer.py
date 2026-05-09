"""Synthesizer agent (master plan §11.1).

The fourth and final node in the LangGraph state graph. Aggregates the
Critic's per-chunk grades into a per-gene confidence score, ranks the
50 candidate genes, and produces the structured output the UI renders.

This is **pure aggregation** — no LLM, no external tools. The math is
deterministic and explainable: each chunk contributes
``relevance * evidence_weight * gene_mention_multiplier`` to its gene's
score; the top-K contributions per gene are summed and normalized to [0, 1].

The deterministic implementation produces useful rankings for offline
evaluation. An LLM-driven variant could replace ``aggregate_gene_score``
with a prompted re-ranker if needed; the :class:`GeneCandidate` schema
and node interface stay stable.
"""

from __future__ import annotations

import logging

from src.agents.state import AgentState, CriticGrade, EvidenceType, GeneCandidate

logger = logging.getLogger(__name__)

# Per-evidence-type weight applied to each chunk's contribution.
# Higher = stronger evidence type for causal-gene reasoning.
EVIDENCE_WEIGHTS: dict[EvidenceType, float] = {
    "case_report": 1.0,
    "functional": 1.0,
    "association": 0.8,
    "review": 0.6,
    "unknown": 0.5,
}

# Multiplier when the chunk does NOT mention the gene at all.
# We keep some signal (the chunk is still topically relevant via the
# query), but down-weight heavily because direct mention is the strongest
# proxy for gene-grounded evidence.
NO_MENTION_MULTIPLIER: float = 0.3

# Number of top contributions to sum per gene (the "top-K" in the aggregation).
DEFAULT_TOP_K_CHUNKS: int = 3

# Maximum possible per-chunk contribution (relevance=5 * evidence=1.0 * mention=1.0).
_MAX_PER_CHUNK_CONTRIBUTION: float = 5.0


def chunk_contribution(grade: CriticGrade) -> float:
    """Compute the score contribution of one Critic grade.

    contribution = ``relevance * evidence_weight * mention_multiplier``

    where ``mention_multiplier`` is 1.0 if the chunk mentions the gene
    canonically and ``NO_MENTION_MULTIPLIER`` (0.3) otherwise.
    """
    mention_mult = 1.0 if grade.gene_mention_valid else NO_MENTION_MULTIPLIER
    evidence_w = EVIDENCE_WEIGHTS.get(grade.evidence_type, EVIDENCE_WEIGHTS["unknown"])
    return float(grade.relevance) * evidence_w * mention_mult


def aggregate_gene_score(
    grades: list[CriticGrade], top_k: int = DEFAULT_TOP_K_CHUNKS
) -> tuple[float, list[str]]:
    """Aggregate per-chunk grades into a single (score, supporting_chunks) pair.

    The score is the sum of the top-``top_k`` contributions divided by
    ``top_k * MAX_PER_CHUNK_CONTRIBUTION``, clamped to ``[0, 1]``. This
    gives a meaningful confidence in the unit interval — 1.0 means
    "every supporting chunk gave maximum-relevance, gene-mentioned,
    case-report or functional evidence".

    Args:
        grades: Critic grades for one gene's retrieved chunks.
        top_k: How many top-contributing chunks to sum (default 3).

    Returns:
        Tuple ``(confidence, supporting_chunks)``:
          * ``confidence`` — float in ``[0, 1]``.
          * ``supporting_chunks`` — chunk_ids of the top-``top_k``
            contributors, ordered by descending contribution.
    """
    if not grades:
        return 0.0, []

    # Sort by contribution descending, take top-K.
    scored = [(chunk_contribution(g), g) for g in grades]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:top_k]

    total = sum(c for c, _ in top)
    max_possible = max(top_k, 1) * _MAX_PER_CHUNK_CONTRIBUTION
    confidence = max(0.0, min(1.0, total / max_possible))

    supporting = [g.chunk_id for _, g in top]
    return confidence, supporting


def rank_genes(
    state: AgentState, *, top_k_chunks: int = DEFAULT_TOP_K_CHUNKS
) -> list[GeneCandidate]:
    """Compute a sorted ranking of all candidate genes.

    Iterates over ``state.candidate_genes`` (which preserves the input
    order from Phase 1B), aggregates each gene's grades, and returns
    a list sorted by descending confidence with ``final_rank`` assigned.

    Args:
        state: Agent state with ``candidate_genes`` and ``grades`` populated.
        top_k_chunks: Per-gene aggregation top-K.

    Returns:
        List of :class:`GeneCandidate`, length ``len(state.candidate_genes)``,
        sorted by descending ``aggregate_confidence``. Tie-break: original
        candidate-list order (stable sort).
    """
    candidates: list[GeneCandidate] = []
    for gene in state.candidate_genes:
        grades = state.grades.get(gene, [])
        confidence, supporting = aggregate_gene_score(grades, top_k=top_k_chunks)
        candidates.append(
            GeneCandidate(
                symbol=gene,
                is_causal=False,  # set by evaluation harness when ground truth is known
                aggregate_confidence=confidence,
                supporting_chunks=supporting,
                final_rank=0,  # set after sort below
            )
        )

    # Sort descending by confidence; stable sort preserves input order for ties.
    candidates.sort(key=lambda c: c.aggregate_confidence, reverse=True)

    # Assign final_rank: 1-based, top scorer gets rank 1.
    for rank, c in enumerate(candidates, start=1):
        c.final_rank = rank

    return candidates


def synthesizer_node(state: AgentState, *, top_k_chunks: int = DEFAULT_TOP_K_CHUNKS) -> AgentState:
    """LangGraph node: compute the final ranked candidate list.

    Reads ``state.candidate_genes`` and ``state.grades``; writes
    ``state.ranked``. No external dependencies beyond state.

    Args:
        state: Agent state populated by Critic.
        top_k_chunks: Per-gene aggregation top-K.

    Returns:
        Same state, with ``state.ranked`` populated.
    """
    state.ranked = rank_genes(state, top_k_chunks=top_k_chunks)

    if state.ranked:
        top = state.ranked[0]
        bottom = state.ranked[-1]
        logger.info(
            "Synthesizer: ranked %d genes; top=%s (conf=%.3f), bottom=%s (conf=%.3f)",
            len(state.ranked),
            top.symbol,
            top.aggregate_confidence,
            bottom.symbol,
            bottom.aggregate_confidence,
        )
    else:
        logger.info("Synthesizer: no candidate genes to rank")
    return state
