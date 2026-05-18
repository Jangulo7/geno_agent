"""Agent state schema (master plan §11.1).

Defines the dataclasses that flow through the LangGraph state graph
``query_planner → retriever → critic → (loop or synthesizer) → END``.

Every dataclass is plain-Python: no Pydantic, no LangGraph dependency.
This keeps the schema testable in isolation and importable without
spinning up the full agent stack.

The fields are deliberately conservative — additions are easy, removals
break Phase 2c rendering, so changes here are deliberate and reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EvidenceType = Literal[
    "case_report",
    "functional",
    "association",
    "review",
    "unknown",
]


@dataclass(slots=True)
class RetrievedChunk:
    """One chunk pulled by the Retriever from the Qdrant index.

    All three score fields are optional because the same dataclass is
    populated by dense-only, BM25-only, and hybrid (RRF) retrieval. When
    a mode does not produce a particular score, the field is left ``None``.

    Attributes:
        chunk_id: UUID5 of the chunk (master plan §4 step 3).
        pmcid: Source PMC accession (e.g. ``"PMC10258773"``).
        text: Detokenized chunk text.
        section_type: Standardized section label
            (``introduction|methods|results|case|discussion|conclusion|other``).
        score_dense: Cosine similarity from the dense vector channel.
        score_bm25: BM25 score from the sparse vector channel.
        score_rrf: Reciprocal-rank-fusion score in hybrid mode.
    """

    chunk_id: str
    pmcid: str
    text: str
    section_type: str
    score_dense: float | None = None
    score_bm25: float | None = None
    score_rrf: float | None = None


@dataclass(slots=True)
class CriticGrade:
    """Critic agent's grade for a single retrieved chunk.

    Attributes:
        chunk_id: ID of the chunk being graded (matches ``RetrievedChunk.chunk_id``).
        gene_mention_valid: True if the chunk text mentions an HGNC-recognized
            symbol (or recognized alias) for the candidate gene under review.
        relevance: Ordinal grade 1-5 capturing phenotype-gene association strength
            in this chunk. ``1`` = irrelevant, ``5`` = strong direct evidence.
        evidence_type: Type of evidence (case report / functional / association /
            review / unknown).
        rationale: Short Critic justification, intended for UI rendering and audit.
    """

    chunk_id: str
    gene_mention_valid: bool
    relevance: int
    evidence_type: EvidenceType
    rationale: str


@dataclass(slots=True)
class GeneCandidate:
    """A single gene in the final ranked output.

    Attributes:
        symbol: HGNC gene symbol.
        is_causal: Ground-truth flag for Phase 1B / evaluation. ``False`` in
            production usage where ground truth is unknown.
        aggregate_confidence: Synthesizer's per-gene confidence in [0, 1].
        supporting_chunks: ``chunk_id``s of the chunks that drove the rank.
        final_rank: 1-based rank in the final output (1 = top).
    """

    symbol: str
    is_causal: bool
    aggregate_confidence: float
    supporting_chunks: list[str]
    final_rank: int


@dataclass(slots=True)
class AgentState:
    """Single state object that flows through the LangGraph graph.

    Per master plan §11.1: nodes mutate this state in place (or return a
    partial-update dict that LangGraph merges in). The conditional edge from
    ``critic`` consults ``iteration < max_iterations`` to decide whether
    to re-enter the Retriever for another pass.

    Attributes:
        case_id: Phase 1B case identifier.
        hpo_terms: Patient HPO term IDs (input).
        candidate_genes: 50-gene candidate list (input).
        expanded_hpo: Output of Query Planner — superset of HPO terms.
        mesh_queries: Query Planner's MeSH-style query strings.
        retrieved: Per-gene list of retrieved chunks (Retriever output).
        grades: Per-gene list of Critic grades.
        ranked: Synthesizer's final ranked output.
        iteration: Counter incremented each time the Critic-loop re-enters
            the Retriever. Capped at ``max_iterations``.
        max_iterations: Loop budget (default 3 per master plan §11.1).
    """

    case_id: str
    hpo_terms: list[str]
    candidate_genes: list[str]
    expanded_hpo: list[str] = field(default_factory=list)
    mesh_queries: list[str] = field(default_factory=list)
    retrieved: dict[str, list[RetrievedChunk]] = field(default_factory=dict)
    grades: dict[str, list[CriticGrade]] = field(default_factory=dict)
    ranked: list[GeneCandidate] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 3
    # Optional debug/eval payload populated by lea_synthesizer_node when
    # response logging is enabled (paper extension v3, Thread C). Consumed by
    # scripts/eval/rerank_inside_d.py --responses-dir to emit per-case
    # sidecars for RAGAS / DeepEval. Stays None for non-LEA cells.
    lea_log: dict | None = None

    def remaining_iterations(self) -> int:
        """Return how many more Retriever→Critic loops are budgeted."""
        return max(0, self.max_iterations - self.iteration)

    def n_low_confidence_grades(self, threshold: int = 2) -> int:
        """Count Critic grades whose ``relevance`` is at or below ``threshold``.

        The conditional edge in the LangGraph (master plan §11.1) re-enters
        the Retriever when this count exceeds a heuristic (currently 5).
        Centralizing the predicate here lets the graph builder stay terse.
        """
        return sum(1 for grades in self.grades.values() for g in grades if g.relevance <= threshold)
