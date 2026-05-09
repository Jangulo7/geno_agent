"""Tests for src.agents.state — Phase 2a state schema (master plan §11.1)."""

from __future__ import annotations

from src.agents.state import (
    AgentState,
    CriticGrade,
    GeneCandidate,
    RetrievedChunk,
)


class TestRetrievedChunk:
    def test_minimal_construction(self) -> None:
        chunk = RetrievedChunk(
            chunk_id="uuid-1",
            pmcid="PMC123",
            text="hello",
            section_type="introduction",
        )
        assert chunk.chunk_id == "uuid-1"
        assert chunk.score_dense is None
        assert chunk.score_bm25 is None
        assert chunk.score_rrf is None

    def test_score_fields_independent(self) -> None:
        """A chunk from hybrid mode populates only score_rrf."""
        chunk = RetrievedChunk(
            chunk_id="x",
            pmcid="PMC1",
            text="t",
            section_type="results",
            score_rrf=0.83,
        )
        assert chunk.score_rrf == 0.83
        assert chunk.score_dense is None
        assert chunk.score_bm25 is None


class TestCriticGrade:
    def test_construction(self) -> None:
        grade = CriticGrade(
            chunk_id="uuid-1",
            gene_mention_valid=True,
            relevance=4,
            evidence_type="case_report",
            rationale="Patient with FBN1 mutation, classic Marfan presentation.",
        )
        assert grade.relevance == 4
        assert grade.evidence_type == "case_report"

    def test_evidence_type_literal_accepts_known(self) -> None:
        """All literal values are constructible."""
        for et in ("case_report", "functional", "association", "review", "unknown"):
            g = CriticGrade(
                chunk_id="x", gene_mention_valid=True, relevance=3, evidence_type=et, rationale="r"
            )  # type: ignore[arg-type]
            assert g.evidence_type == et


class TestGeneCandidate:
    def test_construction(self) -> None:
        gc = GeneCandidate(
            symbol="BRCA1",
            is_causal=True,
            aggregate_confidence=0.87,
            supporting_chunks=["c1", "c2", "c3"],
            final_rank=1,
        )
        assert gc.symbol == "BRCA1"
        assert len(gc.supporting_chunks) == 3
        assert gc.final_rank == 1


class TestAgentState:
    def test_required_fields(self) -> None:
        s = AgentState(
            case_id="c-001",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1", "TP53"],
        )
        assert s.case_id == "c-001"
        assert s.iteration == 0
        assert s.max_iterations == 3

    def test_default_collections_independent(self) -> None:
        """Default-factory ensures each instance gets its own list/dict."""
        a = AgentState(case_id="a", hpo_terms=[], candidate_genes=[])
        b = AgentState(case_id="b", hpo_terms=[], candidate_genes=[])
        a.expanded_hpo.append("HP:1")
        a.retrieved["BRCA1"] = []
        assert b.expanded_hpo == []
        assert b.retrieved == {}

    def test_remaining_iterations(self) -> None:
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=[])
        assert s.remaining_iterations() == 3
        s.iteration = 2
        assert s.remaining_iterations() == 1
        s.iteration = 5
        assert s.remaining_iterations() == 0  # clamped to 0, not negative

    def test_n_low_confidence_grades(self) -> None:
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=[])
        s.grades = {
            "BRCA1": [
                CriticGrade(
                    chunk_id=f"c{i}",
                    gene_mention_valid=True,
                    relevance=r,
                    evidence_type="case_report",
                    rationale="",
                )
                for i, r in enumerate([5, 4, 2, 1, 5])
            ],
            "TP53": [
                CriticGrade(
                    chunk_id=f"d{i}",
                    gene_mention_valid=True,
                    relevance=r,
                    evidence_type="functional",
                    rationale="",
                )
                for i, r in enumerate([1, 1, 3])
            ],
        }
        # threshold default 2: count grades with relevance <= 2
        # BRCA1: relevances [5,4,2,1,5] → 2 below-threshold (relevance 2 and 1)
        # TP53:  relevances [1,1,3]     → 2 below-threshold (relevance 1 twice)
        assert s.n_low_confidence_grades() == 4

    def test_n_low_confidence_with_custom_threshold(self) -> None:
        s = AgentState(case_id="c", hpo_terms=[], candidate_genes=[])
        s.grades = {
            "BRCA1": [
                CriticGrade(
                    chunk_id=f"c{i}",
                    gene_mention_valid=True,
                    relevance=r,
                    evidence_type="case_report",
                    rationale="",
                )
                for i, r in enumerate([5, 4, 3, 2, 1])
            ]
        }
        assert s.n_low_confidence_grades(threshold=3) == 3
        assert s.n_low_confidence_grades(threshold=5) == 5
