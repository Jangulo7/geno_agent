"""Query Planner agent (master plan §11.1).

The Query Planner is the first node in the LangGraph state graph. Given
a patient's HPO terms and a 50-gene candidate list, it produces:

  * ``expanded_hpo`` — the HPO terms broadened by parent-term traversal
    (default distance 2) for higher retrieval recall.
  * ``mesh_queries`` — one MeSH-style query string per candidate gene,
    suitable for ``hybrid_search`` against the PMC OA Qdrant index.

This module ships a **deterministic, no-LLM implementation** sufficient
for offline evaluation and the demo path. An LLM-driven variant
(prompted Qwen3-8B over vLLM) can be wired in later by replacing
``build_mesh_queries`` — the function-level interface stays stable.

Design: the LangGraph node is a thin wrapper around two pure functions
(``plan_hpo_expansion``, ``build_mesh_queries``). Pure functions are
unit-testable in isolation; the node mutates state.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import pronto

from src.agents.state import AgentState
from src.tools.hpo import expand_many, lookup_term

logger = logging.getLogger(__name__)

# Cap how many HPO labels we splice into each per-gene query string.
# More terms hurts BM25 specificity without adding much dense signal.
DEFAULT_MAX_LABELS_PER_QUERY: int = 5


def plan_hpo_expansion(
    state: AgentState, ontology: pronto.Ontology, distance: int = 2
) -> list[str]:
    """Expand the patient's HPO terms by walking up to ``distance`` parents.

    Args:
        state: Current agent state. Reads ``state.hpo_terms``.
        ontology: Loaded HPO ontology.
        distance: Max parent-edge distance (default 2 per master plan §11.1).

    Returns:
        Deduplicated list of HPO IDs ordered by traversal:
        for each input term, the term itself comes first, then each
        ancestor in BFS order, then the next input term.
    """
    return expand_many(state.hpo_terms, ontology, distance=distance)


def _resolve_labels(hpo_ids: Iterable[str], ontology: pronto.Ontology) -> list[str]:
    """Look up each HPO ID's display name and return non-empty labels.

    Used to produce human-readable query strings — gene symbols are
    already English, but HPO IDs need to be resolved to their text labels
    for BM25 to match against article text.
    """
    labels: list[str] = []
    for hpo_id in hpo_ids:
        term = lookup_term(hpo_id, ontology)
        if term is not None and term.name:
            labels.append(term.name)
    return labels


def build_mesh_queries(
    state: AgentState,
    ontology: pronto.Ontology,
    *,
    max_labels_per_query: int = DEFAULT_MAX_LABELS_PER_QUERY,
) -> list[str]:
    """Build one MeSH-style query string per candidate gene.

    Each query combines the gene's HGNC symbol with the patient's most
    informative HPO labels (capped at ``max_labels_per_query``). The
    result is intended for hybrid Qdrant search: the gene symbol gives
    BM25 a strong lexical anchor, while the HPO labels broaden the
    dense channel via PubMedBERT semantic matching.

    Args:
        state: Current agent state. Reads ``state.candidate_genes``,
            ``state.hpo_terms``, and (preferred when populated)
            ``state.expanded_hpo``.
        ontology: Loaded HPO ontology, used to resolve labels.
        max_labels_per_query: Cap on HPO labels appended per query.

    Returns:
        List of length ``len(state.candidate_genes)``. Order matches
        the candidate-genes order. Each string is safe to pass directly
        to :func:`src.tools.qdrant_search.hybrid_search`.
    """
    # Prefer expanded_hpo if the planner already ran; fall back to the raw
    # patient HPO terms otherwise. This keeps the function callable on its
    # own (e.g., from tests) without forcing prior expansion.
    source_hpo = state.expanded_hpo or state.hpo_terms
    labels = _resolve_labels(source_hpo, ontology)[:max_labels_per_query]
    label_phrase = " ".join(labels)

    queries: list[str] = []
    for gene in state.candidate_genes:
        # Gene symbol first → BM25 anchor; HPO labels after → dense context.
        query = f"{gene} {label_phrase}".strip()
        queries.append(query)
    return queries


def query_planner_node(
    state: AgentState,
    ontology: pronto.Ontology,
    *,
    distance: int = 2,
    max_labels_per_query: int = DEFAULT_MAX_LABELS_PER_QUERY,
) -> AgentState:
    """LangGraph-compatible node: mutate state with planner outputs and return.

    Order of operations:
      1. Expand HPO terms (writes ``state.expanded_hpo``).
      2. Build per-gene MeSH queries (writes ``state.mesh_queries``).

    Args:
        state: Incoming agent state. ``state.hpo_terms`` and
            ``state.candidate_genes`` must be set.
        ontology: Loaded HPO ontology.
        distance: HPO expansion distance (default 2).
        max_labels_per_query: HPO label cap per query string.

    Returns:
        The same ``state`` object, mutated in place. Returning the state
        rather than a partial-update dict keeps the call site uniform
        whether or not LangGraph is involved.
    """
    state.expanded_hpo = plan_hpo_expansion(state, ontology, distance=distance)
    state.mesh_queries = build_mesh_queries(
        state, ontology, max_labels_per_query=max_labels_per_query
    )
    logger.info(
        "Query Planner: %d HPO terms -> %d expanded, %d queries built "
        "(%d genes x avg %d labels/query)",
        len(state.hpo_terms),
        len(state.expanded_hpo),
        len(state.mesh_queries),
        len(state.candidate_genes),
        max_labels_per_query,
    )
    return state
