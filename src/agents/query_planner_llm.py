"""LLM-prompted Query Planner variant (master plan §11.1, C7c).

Replaces ``src.agents.query_planner.build_mesh_queries`` with a
Qwen3-8B-prompted version that produces one focused PubMed-style
query string per candidate gene. Interface-compatible: same
``(state, ontology, *, max_labels_per_query) -> list[str]`` signature,
same per-gene ordering aligned with ``state.candidate_genes``.

Design notes:
  * **Thinking mode OFF** for this agent. Query construction is mostly
    surface-form synthesis (gene symbol + a few HPO labels + maybe a
    disease association). The Critic — not the Planner — is where
    deeper reasoning matters, so we save tokens here.
  * **Hard token budget** on the response (``max_tokens=512``) so a
    chatty model can't blow through context for 50 genes per case.
  * **JSON-structured response**: the model returns a single JSON
    array of strings of length ``len(candidate_genes)``. We validate
    length and string type. Any failure -> fall back to the
    deterministic ``build_mesh_queries`` for that case. The fallback
    is logged so failures are visible in audit, not silent.
  * **Determinism**: ``temperature=0.0``. The vLLM server still has
    its own non-determinism (kernel order across batches) so two
    runs may produce near-identical but not byte-identical queries.
    This is accepted and noted in thesis methods.
"""

from __future__ import annotations

import logging
from typing import Final

import pronto

from src.agents.query_planner import (
    DEFAULT_MAX_LABELS_PER_QUERY,
)
from src.agents.query_planner import (
    build_mesh_queries as _deterministic_build_mesh_queries,
)
from src.agents.state import AgentState
from src.tools.llm import LlmConfig, generate_json

logger = logging.getLogger(__name__)

# How many of the patient's HPO labels we surface to the model. Keeping
# this small (rather than dumping all expanded_hpo) avoids prompt
# bloat — the master plan's expanded HPO set can be 30-50 terms wide.
_PROMPT_HPO_CAP: Final[int] = 12

# Per-gene max tokens in the response. With 50 genes per case, the
# total response is ~50 * 30 ≈ 1500 tokens. Generous; vLLM's 8192-token
# max-model-len comfortably handles it.
_MAX_OUTPUT_TOKENS: Final[int] = 2048


SYSTEM_PROMPT: Final[str] = (
    "/no_think\n"
    "You build short, focused PubMed-style search queries for rare-disease gene "
    "prioritization. For each candidate gene, write ONE query string that combines "
    "the gene symbol with the most relevant phenotype terms for retrieving "
    "literature evidence of a gene-phenotype association. "
    "Output a single JSON array of strings, same length and order as the input genes. "
    "No prose, no markdown, no code fences, no extra fields. Just the JSON array."
)


def _resolve_labels(hpo_ids: list[str], ontology: pronto.Ontology) -> list[str]:
    """Map HPO term IDs to their canonical labels (skipping unknowns)."""
    out: list[str] = []
    for tid in hpo_ids:
        term = ontology.get(tid)
        if term is not None and term.name:
            out.append(term.name)
    return out


def _build_prompt(genes: list[str], hpo_labels: list[str]) -> str:
    """Compose the user-side message for the model."""
    labels_str = ", ".join(hpo_labels[:_PROMPT_HPO_CAP]) or "(no HPO labels)"
    genes_str = ", ".join(genes)
    return (
        f"Patient HPO phenotypes: {labels_str}\n\n"
        f"Candidate genes ({len(genes)}): {genes_str}\n\n"
        "Return a JSON array of exactly "
        f"{len(genes)} strings — one PubMed-style query per gene, "
        "in the same order. Each query should contain the gene symbol "
        "plus the most discriminating phenotype words for that gene's "
        "known disease associations."
    )


def build_mesh_queries_llm(
    state: AgentState,
    ontology: pronto.Ontology,
    *,
    max_labels_per_query: int = DEFAULT_MAX_LABELS_PER_QUERY,
    llm_cfg: LlmConfig | None = None,
) -> list[str]:
    """LLM-prompted replacement for ``build_mesh_queries``.

    Falls back to the deterministic version on any LLM / parsing failure.
    The deterministic fallback uses ``max_labels_per_query`` as in the
    deterministic path so the interface is fully drop-in.

    Args:
        state: Agent state with ``state.candidate_genes`` populated.
            ``state.expanded_hpo`` is preferred when set; otherwise
            ``state.hpo_terms`` is used.
        ontology: Loaded HPO ontology (for label lookup).
        max_labels_per_query: Passed through to the deterministic
            fallback. Ignored by the LLM path (the model decides its
            own label set per gene).
        llm_cfg: Optional LLM server config. Defaults to local vLLM.

    Returns:
        list[str] of length ``len(state.candidate_genes)``. Ordering
        matches ``state.candidate_genes``.
    """
    genes = list(state.candidate_genes)
    if not genes:
        return []

    source_hpo = state.expanded_hpo or state.hpo_terms
    hpo_labels = _resolve_labels(source_hpo, ontology)

    user_prompt = _build_prompt(genes, hpo_labels)
    try:
        parsed, _resp = generate_json(
            user_prompt,
            cfg=llm_cfg,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:
        logger.warning(
            "LLM Planner failed (%s); falling back to deterministic for %d genes",
            e.__class__.__name__,
            len(genes),
        )
        return _deterministic_build_mesh_queries(
            state, ontology, max_labels_per_query=max_labels_per_query
        )

    # Structural validation — the model promised a list of strings of the right length.
    if not isinstance(parsed, list) or len(parsed) != len(genes):
        logger.warning(
            "LLM Planner returned malformed response (type=%s, len=%s, expected %d); falling back",
            type(parsed).__name__,
            len(parsed) if hasattr(parsed, "__len__") else "?",
            len(genes),
        )
        return _deterministic_build_mesh_queries(
            state, ontology, max_labels_per_query=max_labels_per_query
        )

    # Coerce each entry to a string; if a slot is empty, fall back per-gene to
    # the deterministic style for that single gene.
    out: list[str] = []
    n_fallback = 0
    det_queries = _deterministic_build_mesh_queries(
        state, ontology, max_labels_per_query=max_labels_per_query
    )
    for i, (_gene, query) in enumerate(zip(genes, parsed, strict=True)):
        if isinstance(query, str) and query.strip():
            out.append(query.strip())
        else:
            out.append(det_queries[i])
            n_fallback += 1

    if n_fallback:
        logger.info(
            "LLM Planner: %d/%d genes used deterministic fallback (malformed entries)",
            n_fallback,
            len(genes),
        )
    return out


def query_planner_node_llm(
    state: AgentState,
    ontology: pronto.Ontology,
    *,
    distance: int = 2,
    max_labels_per_query: int = DEFAULT_MAX_LABELS_PER_QUERY,
    llm_cfg: LlmConfig | None = None,
) -> AgentState:
    """LangGraph node: LLM Planner version of ``query_planner_node``.

    Mirrors the deterministic node's behaviour: populate
    ``state.expanded_hpo`` (still deterministic — HPO graph traversal
    is well-defined and we don't gain by LLM-ing it) and
    ``state.mesh_queries`` (LLM-prompted).
    """
    from src.agents.query_planner import plan_hpo_expansion

    state.expanded_hpo = plan_hpo_expansion(state, ontology, distance=distance)
    state.mesh_queries = build_mesh_queries_llm(
        state, ontology, max_labels_per_query=max_labels_per_query, llm_cfg=llm_cfg
    )
    logger.info(
        "Query Planner (LLM): %d HPO terms -> %d expanded, %d queries built",
        len(state.hpo_terms),
        len(state.expanded_hpo),
        len(state.mesh_queries),
    )
    return state
