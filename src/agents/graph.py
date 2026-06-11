"""LangGraph state graph wiring (master plan §11.1, C7a).

Composes the four Phase 2a agents (Query Planner, Retriever, Critic,
Synthesizer) into a single :class:`langgraph.graph.StateGraph` with
the conditional self-correction loop that routes from Critic back to
the Retriever when (a) iteration budget remains AND (b) too many
low-confidence grades were produced.

This module wires the **deterministic** Phase 2a agents. The same wiring
serves the LLM-prompted variants (C7b/C7c) once they exist — the swap-in
points are inside ``build_mesh_queries`` and ``grade_chunk``, not at the
graph level.

Graph topology::

    START → query_planner → retriever → critic → ┬→ retriever_loop → critic
                                                  └→ synthesizer → END

The ``retriever_loop`` node is a thin wrapper around ``retriever_node``
that increments ``state.iteration`` on entry. Keeping the increment out
of the conditional edge function keeps that function pure (no side
effects) — the routing decision is a pure function of state.
"""

from __future__ import annotations

import logging
from typing import Final, Literal

import pronto
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.critic import critic_node
from src.agents.query_planner import query_planner_node
from src.agents.retriever import retriever_node
from src.agents.state import AgentState
from src.agents.synthesizer import synthesizer_node
from src.tools.hgnc import HgncIndex
from src.tools.qdrant_search import RetrievalMode, SearchConfig

logger = logging.getLogger(__name__)

DEFAULT_LOW_CONF_THRESHOLD: Final[int] = 5
DEFAULT_RETRIEVER_TOP_K: Final[int] = 10


def critic_router(
    state: AgentState, low_conf_threshold: int = DEFAULT_LOW_CONF_THRESHOLD
) -> Literal["retriever_loop", "synthesizer"]:
    """Pure routing function — decide whether to loop back or finish.

    The decision is a pure function of the state: no side effects, no
    state mutation. The actual iteration-counter increment happens in
    ``_make_retriever_loop_node`` below, on entry to the loop body.

    Args:
        state: Agent state populated by the Critic.
        low_conf_threshold: How many low-confidence grades trigger a re-loop.

    Returns:
        ``"retriever_loop"`` to route back through the retriever (and then
        back to the critic), or ``"synthesizer"`` to finalize the ranking.
    """
    if state.remaining_iterations() > 0 and state.n_low_confidence_grades() > low_conf_threshold:
        return "retriever_loop"
    return "synthesizer"


def build_graph(
    *,
    hpo_ontology: pronto.Ontology,
    search_cfg: SearchConfig,
    hgnc_index: HgncIndex,
    retriever_top_k: int = DEFAULT_RETRIEVER_TOP_K,
    retriever_mode: RetrievalMode = "hybrid",
    use_gene_filter: bool = False,
    low_conf_threshold: int = DEFAULT_LOW_CONF_THRESHOLD,
    use_llm_planner: bool = False,
    use_llm_critic: bool = False,
    use_lea_synthesiser: bool = False,
) -> CompiledStateGraph:
    """Build and compile the four-agent LangGraph state graph.

    Each LangGraph node is a closure that captures its dependencies —
    LangGraph nodes themselves only see the state. This keeps the
    dependency injection out of the state object.

    Args:
        hpo_ontology: Loaded HPO ontology (Query Planner + Critic).
        search_cfg: Qdrant + dense + BM25 search config (Retriever).
        hgnc_index: HGNC index (Critic).
        retriever_top_k: Per-gene chunk budget (default 10).
        retriever_mode: ``"dense"`` / ``"bm25"`` / ``"hybrid"``.
        use_gene_filter: Forward gene as Qdrant payload-text filter.
        low_conf_threshold: Critic loop trigger threshold.

    Returns:
        Compiled :class:`CompiledStateGraph` ready to ``.invoke(state)``.
    """
    graph: StateGraph = StateGraph(AgentState)

    # Node wrappers (closures capture deps; nodes only see state).
    # LLM variants are imported lazily so we don't pay the cost when not used.
    if use_llm_planner:
        from src.agents.query_planner_llm import query_planner_node_llm

        def _planner(state: AgentState) -> AgentState:
            return query_planner_node_llm(state, hpo_ontology)
    else:

        def _planner(state: AgentState) -> AgentState:
            return query_planner_node(state, hpo_ontology)

    def _retriever(state: AgentState) -> AgentState:
        return retriever_node(
            state,
            search_cfg,
            top_k=retriever_top_k,
            mode=retriever_mode,
            use_gene_filter=use_gene_filter,
        )

    if use_llm_critic:
        from src.agents.critic_llm import critic_node_llm

        def _critic(state: AgentState) -> AgentState:
            return critic_node_llm(state, hpo_ontology, hgnc_index)
    else:

        def _critic(state: AgentState) -> AgentState:
            return critic_node(state, hpo_ontology, hgnc_index)

    if use_lea_synthesiser:
        from src.agents.synthesizer_lea import lea_synthesizer_node

        def _synthesizer(state: AgentState) -> AgentState:
            return lea_synthesizer_node(state, hpo_ontology)
    else:

        def _synthesizer(state: AgentState) -> AgentState:
            return synthesizer_node(state)

    def _retriever_loop(state: AgentState) -> AgentState:
        """Loop-body retriever: increments iteration before re-fetching."""
        state.iteration += 1
        logger.info(
            "Self-correction loop iteration %d/%d (%d low-confidence grades triggered re-entry)",
            state.iteration,
            state.max_iterations,
            state.n_low_confidence_grades(),
        )
        return _retriever(state)

    # Register nodes
    graph.add_node("query_planner", _planner)
    graph.add_node("retriever", _retriever)
    graph.add_node("critic", _critic)
    graph.add_node("retriever_loop", _retriever_loop)
    graph.add_node("synthesizer", _synthesizer)

    # Linear edges
    graph.set_entry_point("query_planner")
    graph.add_edge("query_planner", "retriever")
    graph.add_edge("retriever", "critic")
    graph.add_edge("retriever_loop", "critic")  # loop body returns to critic
    graph.add_edge("synthesizer", END)

    # Conditional self-correction edge
    graph.add_conditional_edges(
        "critic",
        lambda s: critic_router(s, low_conf_threshold=low_conf_threshold),
        {
            "retriever_loop": "retriever_loop",
            "synthesizer": "synthesizer",
        },
    )

    compiled = graph.compile()
    logger.info(
        "geno_agent graph compiled: 5 nodes, "
        "linear default + Critic→Retriever loop (max %d iterations)",
        AgentState(case_id="", hpo_terms=[], candidate_genes=[]).max_iterations,
    )
    return compiled


def run_graph(
    initial_state: AgentState,
    *,
    hpo_ontology: pronto.Ontology,
    search_cfg: SearchConfig,
    hgnc_index: HgncIndex,
    **kwargs,
) -> AgentState:
    """Convenience wrapper: build, invoke, return the final state.

    Most callers will want this — the graph itself is reusable across
    cases, but a one-shot invocation is the common pattern.

    Args:
        initial_state: AgentState with case_id, hpo_terms, candidate_genes set.
        hpo_ontology, search_cfg, hgnc_index: Forwarded to :func:`build_graph`.
        **kwargs: Forwarded to :func:`build_graph` (top_k, mode, etc.).

    Returns:
        The final :class:`AgentState` after the graph has run to completion.
    """
    compiled = build_graph(
        hpo_ontology=hpo_ontology,
        search_cfg=search_cfg,
        hgnc_index=hgnc_index,
        **kwargs,
    )
    final = compiled.invoke(initial_state)
    # LangGraph may return a dict-like; ensure it's an AgentState for callers.
    if isinstance(final, AgentState):
        return final
    # Fall back to dataclass reconstruction if LangGraph normalized to dict.
    return AgentState(**final)
