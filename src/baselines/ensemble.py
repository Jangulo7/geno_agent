"""Ensemble of two gene-ranking systems via Reciprocal Rank Fusion.

Combines the ranked outputs of two cells (e.g. Cell D — multi-agent
literature RAG — and Cell K — Exomiser HPO-only) into a single ranked
list. Used to produce Cell P (D + K ensemble), the "cheapest big win"
identified in the 2026-05-15 design discussion: D and K have
complementary category strengths (D wins on immunological, K wins on
developmental and metabolic), so a rank-fused combination is expected
to outperform either alone.

Reciprocal Rank Fusion (RRF, Cormack et al. 2009) is the standard
score-free ensemble in IR. For each item, the fused score is
``sum_i 1 / (k + rank_i)`` across input systems. The constant ``k=60``
is the canonical default; it dampens the contribution of high ranks
without rewarding spurious top-1 picks.

RRF is preferred to score-weighted averaging here because the two
systems' confidence scores live on incomparable scales:

  * Cell D's ``aggregate_confidence`` is a sum of LLM-graded chunk
    relevance scores (typically 0-1, but case-dependent).
  * Cell K's ``aggregate_confidence`` is Exomiser's hiPhive phenotype
    score (also 0-1, but with very different distributional shape).

Normalising scores per case before linear combination is possible but
adds tuning knobs that RRF avoids. See the milestone report for the
rationale and any future score-fusion experiments.
"""

from __future__ import annotations

from typing import Final

# Standard RRF damping constant from the TREC literature.
RRF_K: Final[int] = 60


def rrf_score(rank: int, k: int = RRF_K) -> float:
    """Reciprocal Rank Fusion score for a single item from a single system.

    Args:
        rank: 1-based rank in the source system (lower = better).
        k: Damping constant; ``k=60`` is the canonical default and
            essentially never tuned in the literature.

    Returns:
        ``1 / (k + rank)`` — a positive float that decreases monotonically
        with rank.
    """
    if rank < 1:
        raise ValueError(f"rank must be >= 1, got {rank}")
    return 1.0 / (k + rank)


def ensemble_two_cells(
    case_a: list[dict],
    case_b: list[dict],
    *,
    k: int = RRF_K,
    weight_a: float = 1.0,
    weight_b: float = 1.0,
) -> list[dict]:
    """Fuse two cell payloads into a single weighted-RRF payload.

    The input payloads must be in the standard cell JSON shape:
    ``[{symbol, is_causal, aggregate_confidence, supporting_chunks,
    final_rank}, ...]``. Both payloads should cover the same set of
    candidate genes (one Phase 1B test case).

    The fused score for each gene is
    ``weight_a / (k + rank_a) + weight_b / (k + rank_b)``.
    Equal weights gives standard RRF (Cormack et al. 2009). Unequal
    weights bias the ensemble toward the stronger system; needed
    here because Cell K (Exomiser HPO-only, 0.773 overall top-1) is
    substantially stronger than Cell D (0.627), and a 50/50 RRF
    dilutes K's wins.

    Args:
        case_a: Payload from one cell (e.g. Cell D).
        case_b: Payload from the other cell (e.g. Cell K).
        k: RRF damping constant.
        weight_a: Weight on system A. Default 1.
        weight_b: Weight on system B. Default 1. Set > 1 to bias
            toward system B (e.g. when B is the stronger system).

    Returns:
        New payload in the same shape, with ``aggregate_confidence``
        set to the weighted-RRF score and ``final_rank`` re-assigned
        from the fused ranking.
    """
    rank_a = {entry["symbol"]: entry["final_rank"] for entry in case_a}
    rank_b = {entry["symbol"]: entry["final_rank"] for entry in case_b}
    causal = {e["symbol"] for e in case_a if e.get("is_causal")} | {
        e["symbol"] for e in case_b if e.get("is_causal")
    }
    fallback_rank = max(len(case_a), len(case_b)) + 1

    symbols = sorted(set(rank_a) | set(rank_b))
    scored: list[tuple[str, float]] = []
    for symbol in symbols:
        ra = rank_a.get(symbol, fallback_rank)
        rb = rank_b.get(symbol, fallback_rank)
        score = weight_a * rrf_score(ra, k) + weight_b * rrf_score(rb, k)
        scored.append((symbol, score))

    # Sort by score descending, then by symbol for determinism on ties.
    scored.sort(key=lambda x: (-x[1], x[0]))

    return [
        {
            "symbol": symbol,
            "is_causal": symbol in causal,
            "aggregate_confidence": score,
            "supporting_chunks": [],
            "final_rank": rank,
        }
        for rank, (symbol, score) in enumerate(scored, start=1)
    ]
