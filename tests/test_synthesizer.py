"""Tests for src.agents.synthesizer — the C6 Synthesizer node.

Unit tests with hand-built CriticGrade lists covering:
  * chunk_contribution math for each evidence type and mention status
  * aggregate_gene_score top-K selection, empty input, normalization
  * rank_genes sort order, ranks, tie-break stability, missing genes
  * synthesizer_node end-to-end on the AgentState
"""

from __future__ import annotations

from src.agents.state import AgentState, CriticGrade, EvidenceType
from src.agents.synthesizer import (
    EVIDENCE_WEIGHTS,
    NO_MENTION_MULTIPLIER,
    aggregate_gene_score,
    chunk_contribution,
    rank_genes,
    synthesizer_node,
)


def _grade(
    *,
    chunk_id: str = "c-1",
    relevance: int = 3,
    evidence_type: EvidenceType = "case_report",
    gene_mention_valid: bool = True,
    rationale: str = "test",
) -> CriticGrade:
    """Build a CriticGrade with sensible defaults."""
    return CriticGrade(
        chunk_id=chunk_id,
        gene_mention_valid=gene_mention_valid,
        relevance=relevance,
        evidence_type=evidence_type,
        rationale=rationale,
    )


# ----------------------------------------------- chunk_contribution


class TestChunkContribution:
    def test_max_score_case_report_mentioned(self) -> None:
        g = _grade(relevance=5, evidence_type="case_report", gene_mention_valid=True)
        assert chunk_contribution(g) == 5.0

    def test_max_score_functional_mentioned(self) -> None:
        g = _grade(relevance=5, evidence_type="functional", gene_mention_valid=True)
        assert chunk_contribution(g) == 5.0  # weight 1.0

    def test_association_weight(self) -> None:
        g = _grade(relevance=5, evidence_type="association", gene_mention_valid=True)
        assert chunk_contribution(g) == 5.0 * EVIDENCE_WEIGHTS["association"]

    def test_review_weight(self) -> None:
        g = _grade(relevance=5, evidence_type="review", gene_mention_valid=True)
        assert chunk_contribution(g) == 5.0 * EVIDENCE_WEIGHTS["review"]

    def test_unknown_weight(self) -> None:
        g = _grade(relevance=5, evidence_type="unknown", gene_mention_valid=True)
        assert chunk_contribution(g) == 5.0 * EVIDENCE_WEIGHTS["unknown"]

    def test_no_mention_downweights(self) -> None:
        """Same chunk without mention gets multiplied by NO_MENTION_MULTIPLIER."""
        with_mention = _grade(relevance=5, evidence_type="case_report", gene_mention_valid=True)
        without = _grade(relevance=5, evidence_type="case_report", gene_mention_valid=False)
        assert chunk_contribution(without) == 5.0 * NO_MENTION_MULTIPLIER
        assert chunk_contribution(without) < chunk_contribution(with_mention)

    def test_low_relevance_low_score(self) -> None:
        g = _grade(relevance=1, evidence_type="case_report", gene_mention_valid=True)
        assert chunk_contribution(g) == 1.0


# ----------------------------------------------- aggregate_gene_score


class TestAggregateGeneScore:
    def test_empty_grades(self) -> None:
        score, supporting = aggregate_gene_score([])
        assert score == 0.0
        assert supporting == []

    def test_max_score_three_perfect_chunks(self) -> None:
        """Three perfect chunks → confidence == 1.0."""
        grades = [
            _grade(
                chunk_id=f"c-{i}", relevance=5, evidence_type="case_report", gene_mention_valid=True
            )
            for i in range(3)
        ]
        score, supporting = aggregate_gene_score(grades, top_k=3)
        assert score == 1.0
        assert len(supporting) == 3

    def test_top_k_selection(self) -> None:
        """Only the top-K contributions count toward the score."""
        grades = [
            _grade(chunk_id="hi-1", relevance=5, evidence_type="case_report"),
            _grade(chunk_id="hi-2", relevance=5, evidence_type="case_report"),
            _grade(chunk_id="hi-3", relevance=5, evidence_type="case_report"),
            _grade(chunk_id="lo-1", relevance=1, evidence_type="unknown"),
            _grade(chunk_id="lo-2", relevance=1, evidence_type="unknown"),
        ]
        score, supporting = aggregate_gene_score(grades, top_k=3)
        assert score == 1.0
        # Supporting list contains only the top-3 (high-relevance) chunks
        assert set(supporting) == {"hi-1", "hi-2", "hi-3"}

    def test_supporting_chunks_in_descending_contribution_order(self) -> None:
        grades = [
            _grade(chunk_id="medium", relevance=3, evidence_type="case_report"),
            _grade(chunk_id="best", relevance=5, evidence_type="case_report"),
            _grade(chunk_id="worst", relevance=1, evidence_type="unknown"),
        ]
        _, supporting = aggregate_gene_score(grades, top_k=3)
        assert supporting == ["best", "medium", "worst"]

    def test_clamped_to_unit_interval(self) -> None:
        """Even pathological inputs cannot exceed 1.0."""
        # 10 perfect chunks but top-K is still 3
        grades = [
            _grade(chunk_id=f"c-{i}", relevance=5, evidence_type="case_report") for i in range(10)
        ]
        score, _ = aggregate_gene_score(grades, top_k=3)
        assert 0.0 <= score <= 1.0

    def test_no_mention_drops_score(self) -> None:
        """Same relevance/evidence but no gene mention → lower score."""
        with_mention = [
            _grade(
                chunk_id=f"c-{i}", relevance=5, evidence_type="case_report", gene_mention_valid=True
            )
            for i in range(3)
        ]
        without = [
            _grade(
                chunk_id=f"c-{i}",
                relevance=5,
                evidence_type="case_report",
                gene_mention_valid=False,
            )
            for i in range(3)
        ]
        s1, _ = aggregate_gene_score(with_mention)
        s2, _ = aggregate_gene_score(without)
        assert s2 < s1


# ----------------------------------------------- rank_genes


class TestRankGenes:
    def test_basic_ordering(self) -> None:
        state = AgentState(case_id="c", hpo_terms=[], candidate_genes=["LO", "HI"])
        state.grades = {
            "LO": [_grade(relevance=1, evidence_type="unknown", gene_mention_valid=False)],
            "HI": [_grade(relevance=5, evidence_type="case_report", gene_mention_valid=True)],
        }
        ranked = rank_genes(state)
        assert ranked[0].symbol == "HI"
        assert ranked[1].symbol == "LO"

    def test_ranks_are_one_based_dense(self) -> None:
        state = AgentState(
            case_id="c",
            hpo_terms=[],
            candidate_genes=["A", "B", "C", "D"],
        )
        state.grades = {
            "A": [_grade(relevance=4)],
            "B": [_grade(relevance=2)],
            "C": [_grade(relevance=5)],
            "D": [_grade(relevance=3)],
        }
        ranked = rank_genes(state)
        ranks = [c.final_rank for c in ranked]
        assert ranks == [1, 2, 3, 4]

    def test_genes_without_grades_score_zero(self) -> None:
        state = AgentState(case_id="c", hpo_terms=[], candidate_genes=["LO", "MISSING"])
        state.grades = {
            "LO": [_grade(relevance=2, evidence_type="unknown", gene_mention_valid=True)],
        }
        ranked = rank_genes(state)
        # MISSING gene gets score 0 and lands last
        assert ranked[-1].symbol == "MISSING"
        assert ranked[-1].aggregate_confidence == 0.0
        assert ranked[-1].supporting_chunks == []

    def test_tie_break_preserves_input_order(self) -> None:
        """Equal scores → original candidate_genes order is preserved (stable sort)."""
        state = AgentState(case_id="c", hpo_terms=[], candidate_genes=["FIRST", "SECOND", "THIRD"])
        state.grades = {
            g: [_grade(relevance=3, evidence_type="case_report", gene_mention_valid=True)]
            for g in state.candidate_genes
        }
        ranked = rank_genes(state)
        # All have identical scores; ranks reflect original order
        assert [c.symbol for c in ranked] == ["FIRST", "SECOND", "THIRD"]
        assert [c.final_rank for c in ranked] == [1, 2, 3]

    def test_supporting_chunks_attached(self) -> None:
        state = AgentState(case_id="c", hpo_terms=[], candidate_genes=["X"])
        state.grades = {
            "X": [
                _grade(chunk_id="cid-1", relevance=5, evidence_type="case_report"),
                _grade(chunk_id="cid-2", relevance=3, evidence_type="functional"),
            ]
        }
        ranked = rank_genes(state)
        assert ranked[0].supporting_chunks == ["cid-1", "cid-2"]


# ----------------------------------------------- synthesizer_node


class TestSynthesizerNode:
    def test_writes_state_ranked(self) -> None:
        state = AgentState(case_id="c", hpo_terms=[], candidate_genes=["A", "B"])
        state.grades = {
            "A": [_grade(relevance=2)],
            "B": [_grade(relevance=5)],
        }
        out = synthesizer_node(state)
        assert out is state
        assert len(state.ranked) == 2
        assert state.ranked[0].symbol == "B"
        assert state.ranked[0].final_rank == 1

    def test_empty_candidates_empty_ranking(self) -> None:
        state = AgentState(case_id="c", hpo_terms=[], candidate_genes=[])
        synthesizer_node(state)
        assert state.ranked == []

    def test_idempotent(self) -> None:
        """Two calls produce the same final ranking."""
        state1 = AgentState(case_id="c", hpo_terms=[], candidate_genes=["A", "B"])
        state2 = AgentState(case_id="c", hpo_terms=[], candidate_genes=["A", "B"])
        for s in (state1, state2):
            s.grades = {
                "A": [_grade(relevance=4, evidence_type="case_report")],
                "B": [_grade(relevance=2, evidence_type="unknown")],
            }
        synthesizer_node(state1)
        synthesizer_node(state2)
        assert [c.symbol for c in state1.ranked] == [c.symbol for c in state2.ranked]
        assert [c.final_rank for c in state1.ranked] == [c.final_rank for c in state2.ranked]
        assert [c.aggregate_confidence for c in state1.ranked] == [
            c.aggregate_confidence for c in state2.ranked
        ]
