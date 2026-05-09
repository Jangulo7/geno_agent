"""Tests for src.agents.graph — the C7a LangGraph wiring.

Two tiers:
  * Pure routing tests for ``critic_router`` (no graph compile, no I/O).
  * Compiled-graph tests with monkeypatched ``hybrid_search`` (no Qdrant).

The graph topology and the conditional self-correction loop are exercised
end-to-end with deterministic agents — no LLM needed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pronto
import pytest

from src.agents import retriever as retriever_module
from src.agents.graph import build_graph, critic_router, run_graph
from src.agents.state import AgentState, CriticGrade, RetrievedChunk
from src.tools.hgnc import HgncEntry, HgncIndex, load_hgnc
from src.tools.hpo import load_hpo
from src.tools.qdrant_search import SearchConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HPO_OBO = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"
HGNC_TSV = PROJECT_ROOT / "data" / "HGNC" / "hgnc_complete_set_2026-04-07.txt"


# ---------------------------------------------------------------- routing


class TestCriticRouter:
    """Pure routing function — no side effects, no I/O."""

    def test_no_grades_routes_to_synthesizer(self) -> None:
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=["X"])
        assert critic_router(s) == "synthesizer"

    def test_high_confidence_routes_to_synthesizer(self) -> None:
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=["X"])
        # 5 high-relevance grades; none are low-confidence
        s.grades = {
            "X": [
                CriticGrade(
                    chunk_id=f"c-{i}",
                    gene_mention_valid=True,
                    relevance=5,
                    evidence_type="case_report",
                    rationale="",
                )
                for i in range(5)
            ]
        }
        assert critic_router(s) == "synthesizer"

    def test_many_low_conf_with_budget_routes_to_loop(self) -> None:
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=["X"])
        s.grades = {
            "X": [
                CriticGrade(
                    chunk_id=f"c-{i}",
                    gene_mention_valid=False,
                    relevance=1,
                    evidence_type="unknown",
                    rationale="",
                )
                for i in range(10)  # 10 low-confidence > threshold of 5
            ]
        }
        # iteration=0 → remaining=3 → enters loop
        assert critic_router(s) == "retriever_loop"

    def test_budget_exhausted_routes_to_synthesizer(self) -> None:
        """Even with many low-confidence grades, exhausted budget ends the loop."""
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=["X"])
        s.iteration = s.max_iterations  # remaining = 0
        s.grades = {
            "X": [
                CriticGrade(
                    chunk_id=f"c-{i}",
                    gene_mention_valid=False,
                    relevance=1,
                    evidence_type="unknown",
                    rationale="",
                )
                for i in range(10)
            ]
        }
        assert critic_router(s) == "synthesizer"

    def test_threshold_param_is_honored(self) -> None:
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=["X"])
        s.grades = {
            "X": [
                CriticGrade(
                    chunk_id=f"c-{i}",
                    gene_mention_valid=False,
                    relevance=1,
                    evidence_type="unknown",
                    rationale="",
                )
                for i in range(3)  # only 3 low-confidence
            ]
        }
        # Default threshold=5 → don't loop
        assert critic_router(s) == "synthesizer"
        # Lower threshold=2 → loop
        assert critic_router(s, low_conf_threshold=2) == "retriever_loop"


# ---------------------------------------------------------------- compiled graph


@pytest.fixture(scope="module")
def hpo() -> pronto.Ontology:
    if not HPO_OBO.exists():
        pytest.skip(f"HPO obo not present: {HPO_OBO}")
    load_hpo.cache_clear()
    return load_hpo(HPO_OBO)


@pytest.fixture(scope="module")
def hgnc_real() -> HgncIndex:
    if not HGNC_TSV.exists():
        pytest.skip(f"HGNC TSV not present: {HGNC_TSV}")
    load_hgnc.cache_clear()
    return load_hgnc(HGNC_TSV)


def _fake_chunks_factory(n_high_per_gene: int) -> Callable:
    """Build a fake hybrid_search that returns ``n_high_per_gene`` strong chunks per gene."""

    def fake(cfg: SearchConfig, query: str, *, top_k: int, mode: str, gene_filter: str | None):
        # Derive gene from the first token of the query (matches Planner output).
        gene = query.split()[0] if query else "UNKNOWN"
        chunks: list[RetrievedChunk] = []
        # Half strong (relevance trigger via mention + co-occurrence), half weak.
        for i in range(n_high_per_gene):
            chunks.append(
                RetrievedChunk(
                    chunk_id=f"{gene}-strong-{i}",
                    pmcid=f"PMC{i:04d}",
                    text=f"{gene} mutation associated with Seizure in patient.",
                    section_type="case",
                    score_rrf=0.9 - i * 0.05,
                )
            )
        for i in range(top_k - n_high_per_gene):
            chunks.append(
                RetrievedChunk(
                    chunk_id=f"{gene}-weak-{i}",
                    pmcid=f"PMC{1000 + i:04d}",
                    text=f"Generic unrelated text {i}.",
                    section_type="other",
                    score_rrf=0.1 - i * 0.01,
                )
            )
        return chunks

    return fake


@pytest.fixture
def fake_search_cfg() -> SearchConfig:
    """A SearchConfig with non-None placeholders. The actual search is mocked."""
    return SearchConfig(
        client=None,  # type: ignore[arg-type]
        collection_name="test",
        dense_model=None,  # type: ignore[arg-type]
        bm25_model=None,  # type: ignore[arg-type]
    )


class TestBuildAndRunGraph:
    """End-to-end graph compilation + invocation with mocked retrieval."""

    def test_graph_compiles(
        self, hpo: pronto.Ontology, hgnc_real: HgncIndex, fake_search_cfg: SearchConfig
    ) -> None:
        compiled = build_graph(
            hpo_ontology=hpo,
            search_cfg=fake_search_cfg,
            hgnc_index=hgnc_real,
        )
        assert compiled is not None

    def test_linear_flow_high_confidence(
        self,
        hpo: pronto.Ontology,
        hgnc_real: HgncIndex,
        fake_search_cfg: SearchConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When grades are mostly high-confidence, no loop happens."""
        monkeypatch.setattr(retriever_module, "hybrid_search", _fake_chunks_factory(8))
        state = AgentState(
            case_id="test-1",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1", "TP53"],
        )
        final = run_graph(
            state,
            hpo_ontology=hpo,
            search_cfg=fake_search_cfg,
            hgnc_index=hgnc_real,
            retriever_top_k=10,
        )
        # No loop happened
        assert final.iteration == 0
        # Synthesizer ran
        assert len(final.ranked) == 2
        assert all(c.final_rank in (1, 2) for c in final.ranked)

    def test_loop_triggers_when_low_confidence(
        self,
        hpo: pronto.Ontology,
        fake_search_cfg: SearchConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When most grades are low-confidence, the loop fires."""

        # All chunks → bare gene mentions, no HPO co-occurrence → forces low scores.
        def low_grade_search(cfg, query, *, top_k, mode, gene_filter):
            return [
                RetrievedChunk(
                    chunk_id=f"c-{i}",
                    pmcid=f"PMC{i:04d}",
                    text="Generic text.",
                    section_type="other",
                    score_rrf=0.1,
                )
                for i in range(top_k)
            ]

        monkeypatch.setattr(retriever_module, "hybrid_search", low_grade_search)

        # Mini HGNC so canonicalize works for "BRCA1"
        mini_hgnc = HgncIndex(
            by_symbol={
                "BRCA1": HgncEntry(
                    hgnc_id="HGNC:1100",
                    symbol="BRCA1",
                    name="BRCA1",
                    locus_group="protein-coding gene",
                )
            },
            alias_to_symbol={},
        )

        state = AgentState(
            case_id="test-loop",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1"],
        )
        final = run_graph(
            state,
            hpo_ontology=hpo,
            search_cfg=fake_search_cfg,
            hgnc_index=mini_hgnc,
            retriever_top_k=10,
        )
        # Loop ran at least once (state.iteration incremented)
        assert final.iteration >= 1
        # Loop terminated by max_iterations
        assert final.iteration <= final.max_iterations
        # Synthesizer eventually ran
        assert len(final.ranked) == 1

    def test_loop_terminates_at_max_iterations(
        self,
        hpo: pronto.Ontology,
        fake_search_cfg: SearchConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No matter how many low-confidence grades, loop stops at max_iterations."""

        def perpetually_bad_search(cfg, query, *, top_k, mode, gene_filter):
            return [
                RetrievedChunk(
                    chunk_id=f"c-{i}",
                    pmcid=f"PMC{i:04d}",
                    text="Generic.",
                    section_type="other",
                    score_rrf=0.0,
                )
                for i in range(top_k)
            ]

        monkeypatch.setattr(retriever_module, "hybrid_search", perpetually_bad_search)

        mini_hgnc = HgncIndex(
            by_symbol={
                "BRCA1": HgncEntry(
                    hgnc_id="HGNC:1100",
                    symbol="BRCA1",
                    name="BRCA1",
                    locus_group="protein-coding gene",
                )
            },
            alias_to_symbol={},
        )
        state = AgentState(
            case_id="test-budget",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1"],
            max_iterations=2,  # Tighter budget for test
        )
        final = run_graph(
            state,
            hpo_ontology=hpo,
            search_cfg=fake_search_cfg,
            hgnc_index=mini_hgnc,
            retriever_top_k=5,
        )
        # Iteration counter cannot exceed max_iterations
        assert final.iteration <= 2

    def test_returns_agent_state(
        self,
        hpo: pronto.Ontology,
        hgnc_real: HgncIndex,
        fake_search_cfg: SearchConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run_graph normalizes LangGraph's output to an AgentState."""
        monkeypatch.setattr(retriever_module, "hybrid_search", _fake_chunks_factory(8))
        state = AgentState(
            case_id="t",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1"],
        )
        final = run_graph(
            state,
            hpo_ontology=hpo,
            search_cfg=fake_search_cfg,
            hgnc_index=hgnc_real,
        )
        assert isinstance(final, AgentState)
