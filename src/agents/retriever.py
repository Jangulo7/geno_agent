"""Retriever agent (master plan §11.1).

The second node in the LangGraph state graph. Given the Query Planner's
per-gene query strings, fetches the top-K most relevant chunks per gene
from the Qdrant index and writes them to ``state.retrieved``.

Design notes:
  * Retrieval is **per-gene**, not per-HPO-term. The Query Planner already
    folded HPO context into each gene's query; the Retriever runs one
    hybrid search per gene, which keeps the LangGraph node fast (50 small
    Qdrant calls vs 50 x N_HPO calls).
  * The default mode is ``"hybrid"`` (dense + BM25 + RRF). Single-mode
    runs are exposed for the §11.5 evaluation factorial (cells A and C
    use ``"dense"``, B and D use ``"hybrid"``).
  * The optional ``gene_filter`` argument forwards the gene symbol as a
    Qdrant payload-text filter, so retrieved chunks must mention the gene.
    Disabled by default; enable when the Critic agent needs gene-grounded
    evidence.

The node mutates ``state.retrieved`` in place and returns the same state.
"""

from __future__ import annotations

import logging

from src.agents.state import AgentState, RetrievedChunk
from src.tools.qdrant_search import RetrievalMode, SearchConfig, hybrid_search

logger = logging.getLogger(__name__)

DEFAULT_TOP_K: int = 10
DEFAULT_MODE: RetrievalMode = "hybrid"


def retrieve_for_gene(
    cfg: SearchConfig,
    query: str,
    *,
    gene: str,
    top_k: int = DEFAULT_TOP_K,
    mode: RetrievalMode = DEFAULT_MODE,
    use_gene_filter: bool = False,
) -> list[RetrievedChunk]:
    """Run a single hybrid search for one gene's query.

    Pure wrapper around :func:`src.tools.qdrant_search.hybrid_search` —
    factored out so unit tests can monkeypatch this function instead of
    mocking the whole Qdrant client.

    Args:
        cfg: Connected Qdrant search configuration.
        query: The gene-specific query string (from the Query Planner).
        gene: The HGNC gene symbol this query is for. Used both as the
            ``gene_filter`` (when enabled) and for log context.
        top_k: Number of chunks to return.
        mode: ``"dense"`` / ``"bm25"`` / ``"hybrid"`` (default).
        use_gene_filter: If True, restrict hits to chunks whose payload
            text mentions ``gene``. Default False — broad retrieval.

    Returns:
        List of :class:`RetrievedChunk`, ordered by descending score.
    """
    return hybrid_search(
        cfg,
        query,
        top_k=top_k,
        mode=mode,
        gene_filter=gene if use_gene_filter else None,
    )


def retriever_node(
    state: AgentState,
    cfg: SearchConfig,
    *,
    top_k: int = DEFAULT_TOP_K,
    mode: RetrievalMode = DEFAULT_MODE,
    use_gene_filter: bool = False,
) -> AgentState:
    """LangGraph-compatible node: populate ``state.retrieved`` for every candidate.

    Iterates over ``state.candidate_genes`` and ``state.mesh_queries`` in
    lockstep — both are built in the same order by the Query Planner.
    If the lengths disagree (e.g., the Planner was skipped), the node
    falls back to a generic query of just the gene symbol.

    Args:
        state: Incoming agent state (must already have ``candidate_genes``
            populated; ``mesh_queries`` strongly recommended).
        cfg: Qdrant + dense + BM25 search configuration.
        top_k: Per-gene chunk budget.
        mode: Retrieval mode.
        use_gene_filter: Forward gene as a payload-text filter.

    Returns:
        The same state, with ``state.retrieved`` filled in.
    """
    n_genes = len(state.candidate_genes)
    n_queries = len(state.mesh_queries)
    if n_queries != n_genes:
        logger.warning(
            "Retriever: %d candidate_genes but %d mesh_queries — "
            "falling back to gene-symbol-only queries for the mismatch",
            n_genes,
            n_queries,
        )

    n_total_chunks = 0
    for i, gene in enumerate(state.candidate_genes):
        # Use the Planner's query when present; otherwise use just the gene symbol.
        query = state.mesh_queries[i] if i < n_queries else gene
        chunks = retrieve_for_gene(
            cfg,
            query,
            gene=gene,
            top_k=top_k,
            mode=mode,
            use_gene_filter=use_gene_filter,
        )
        state.retrieved[gene] = chunks
        n_total_chunks += len(chunks)

    logger.info(
        "Retriever (%s, top_k=%d, gene_filter=%s): %d genes -> %d total chunks",
        mode,
        top_k,
        use_gene_filter,
        n_genes,
        n_total_chunks,
    )
    return state
