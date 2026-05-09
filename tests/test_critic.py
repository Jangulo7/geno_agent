"""Tests for src.agents.critic — the C5 Critic node.

Pure-Python unit tests covering each grading function with hand-built
chunks. Only the ``critic_node`` test loads real HPO + HGNC; the rest
use small fake objects to keep tests fast and isolated.
"""

from __future__ import annotations

from pathlib import Path

import pronto
import pytest

from src.agents.critic import (
    classify_evidence_type,
    critic_node,
    grade_chunk,
    grade_gene_mention,
    grade_relevance,
)
from src.agents.state import AgentState, RetrievedChunk
from src.tools.hgnc import HgncIndex, load_hgnc
from src.tools.hpo import load_hpo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HPO_OBO = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"
HGNC_TSV = PROJECT_ROOT / "data" / "HGNC" / "hgnc_complete_set_2026-04-07.txt"


# ----------------------------------------------- shared HGNC helper


def _hgnc(symbol: str, aliases: list[str] | None = None) -> HgncIndex:
    """Build a tiny HGNC index containing one canonical symbol + aliases."""
    from src.tools.hgnc import HgncEntry  # local import to avoid heavy load

    by_symbol = {
        symbol: HgncEntry(
            hgnc_id=f"HGNC:{symbol}",
            symbol=symbol,
            name=f"{symbol} test name",
            locus_group="protein-coding gene",
        )
    }
    alias_map = dict.fromkeys(aliases or [], symbol)
    return HgncIndex(by_symbol=by_symbol, alias_to_symbol=alias_map)


def _chunk(text: str, section: str = "results") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="test-chunk",
        pmcid="PMC0001",
        text=text,
        section_type=section,
        score_rrf=0.5,
    )


# ----------------------------------------------- gene mention tests


class TestGradeGeneMention:
    def test_canonical_match(self) -> None:
        idx = _hgnc("BRCA1")
        c = _chunk("Patient carries a BRCA1 missense variant.")
        assert grade_gene_mention(c, "BRCA1", idx) is True

    def test_alias_match(self) -> None:
        idx = _hgnc("ERBB2", aliases=["HER2", "NEU"])
        c = _chunk("HER2 amplification was observed.")
        assert grade_gene_mention(c, "ERBB2", idx) is True

    def test_case_insensitive(self) -> None:
        idx = _hgnc("BRCA1")
        c = _chunk("the brca1 protein binds...")
        assert grade_gene_mention(c, "BRCA1", idx) is True

    def test_word_boundary_no_substring(self) -> None:
        """``BRCA1`` should NOT match within an unrelated longer token."""
        idx = _hgnc("BRCA1")
        c = _chunk("This is gibberishBRCA1plusmore text.")
        assert grade_gene_mention(c, "BRCA1", idx) is False

    def test_unknown_gene_returns_false(self) -> None:
        idx = _hgnc("BRCA1")
        c = _chunk("BRCA1 is mentioned here.")
        assert grade_gene_mention(c, "ZZZ_NOT_A_GENE", idx) is False

    def test_no_mention_returns_false(self) -> None:
        idx = _hgnc("BRCA1")
        c = _chunk("This chunk talks about something else entirely.")
        assert grade_gene_mention(c, "BRCA1", idx) is False


# ----------------------------------------------- relevance tests


class TestGradeRelevance:
    def test_5_gene_plus_two_near_labels(self) -> None:
        """Gene + ≥2 HPO labels in a near-window co-occurrence -> 5."""
        c = _chunk("BRCA1 mutation cause Seizure and Global delay symptoms.")
        # gene_in_chunk=True simulated; both labels present + within 200 chars
        score = grade_relevance(c, gene_in_chunk=True, hpo_labels=["Seizure", "Global delay"])
        assert score == 5

    def test_4_gene_plus_one_label(self) -> None:
        c = _chunk("BRCA1 mutation associated with disease. " + "x" * 500 + " Seizure.")
        score = grade_relevance(c, gene_in_chunk=True, hpo_labels=["Seizure"])
        assert score == 4

    def test_3_gene_only_no_labels(self) -> None:
        c = _chunk("BRCA1 mutation only.")
        score = grade_relevance(c, gene_in_chunk=True, hpo_labels=["Seizure"])
        assert score == 3

    def test_2_labels_no_gene(self) -> None:
        c = _chunk("Patient presented with Seizure and Global delay.")
        score = grade_relevance(c, gene_in_chunk=False, hpo_labels=["Seizure"])
        assert score == 2

    def test_1_neither(self) -> None:
        c = _chunk("Generic biochemistry text without clinical content.")
        score = grade_relevance(c, gene_in_chunk=False, hpo_labels=["Seizure"])
        assert score == 1


# ----------------------------------------------- evidence type tests


class TestClassifyEvidenceType:
    def test_case_section_wins(self) -> None:
        c = _chunk("Patient is 5 years old.", section="case")
        assert classify_evidence_type(c) == "case_report"

    def test_functional_keyword(self) -> None:
        c = _chunk("Luciferase reporter assay confirmed transactivation.", section="results")
        assert classify_evidence_type(c) == "functional"

    def test_knockout_classified_functional(self) -> None:
        c = _chunk("Knock-out mice showed embryonic lethality.", section="methods")
        assert classify_evidence_type(c) == "functional"

    def test_association_keyword(self) -> None:
        c = _chunk("Case-control study with OR=2.5 and p<0.001.", section="results")
        assert classify_evidence_type(c) == "association"

    def test_review_in_introduction(self) -> None:
        c = _chunk(
            "Previously reported clinical cases are summarized below.", section="introduction"
        )
        assert classify_evidence_type(c) == "review"

    def test_case_keyword_fallback(self) -> None:
        c = _chunk("The proband presented at age 10 with seizures.", section="discussion")
        assert classify_evidence_type(c) == "case_report"

    def test_unknown_default(self) -> None:
        c = _chunk("Generic text with no specific cues at all.", section="other")
        assert classify_evidence_type(c) == "unknown"


# ----------------------------------------------- combined grade_chunk


class TestGradeChunk:
    def test_full_grade_with_strong_evidence(self) -> None:
        idx = _hgnc("BRCA1")
        c = _chunk(
            "We report a patient with BRCA1 mutation presenting with "
            "Seizure and Global delay. Previously reported cases described.",
            section="case",
        )
        grade = grade_chunk(c, "BRCA1", ["Seizure", "Global delay"], idx)
        assert grade.gene_mention_valid is True
        assert grade.relevance >= 4
        assert grade.evidence_type == "case_report"
        assert "BRCA1 mentioned" in grade.rationale
        assert "Seizure" in grade.rationale or "HPO" in grade.rationale

    def test_full_grade_with_no_evidence(self) -> None:
        idx = _hgnc("BRCA1")
        c = _chunk("Generic text about cell biology.", section="other")
        grade = grade_chunk(c, "BRCA1", ["Seizure"], idx)
        assert grade.gene_mention_valid is False
        assert grade.relevance == 1
        assert grade.evidence_type == "unknown"
        assert "NOT mentioned" in grade.rationale


# ----------------------------------------------- critic_node integration


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


class TestCriticNode:
    def test_populates_state_grades(self, hpo: pronto.Ontology, hgnc_real: HgncIndex) -> None:
        state = AgentState(
            case_id="test",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1"],
        )
        state.retrieved = {
            "BRCA1": [
                _chunk("BRCA1 mutation associated with Seizure in this patient.", "case"),
                _chunk("Generic unrelated chunk.", "other"),
            ]
        }
        critic_node(state, hpo, hgnc_real)
        assert "BRCA1" in state.grades
        assert len(state.grades["BRCA1"]) == 2
        # First chunk should grade higher than the second
        assert state.grades["BRCA1"][0].relevance > state.grades["BRCA1"][1].relevance

    def test_chunk_ids_match(self, hpo: pronto.Ontology, hgnc_real: HgncIndex) -> None:
        """Each grade.chunk_id must equal the chunk_id it was built for."""
        state = AgentState(
            case_id="test",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1"],
        )
        chunks = [
            RetrievedChunk(chunk_id="cid-1", pmcid="P1", text="BRCA1 mention", section_type="r"),
            RetrievedChunk(chunk_id="cid-2", pmcid="P2", text="other", section_type="r"),
        ]
        state.retrieved = {"BRCA1": chunks}
        critic_node(state, hpo, hgnc_real)
        assert state.grades["BRCA1"][0].chunk_id == "cid-1"
        assert state.grades["BRCA1"][1].chunk_id == "cid-2"

    def test_returns_same_state_object(self, hpo: pronto.Ontology, hgnc_real: HgncIndex) -> None:
        state = AgentState(case_id="test", hpo_terms=[], candidate_genes=[])
        out = critic_node(state, hpo, hgnc_real)
        assert out is state

    def test_empty_retrieved_no_grades(self, hpo: pronto.Ontology, hgnc_real: HgncIndex) -> None:
        state = AgentState(case_id="test", hpo_terms=["HP:0001250"], candidate_genes=["BRCA1"])
        # No retrieved entry for BRCA1
        critic_node(state, hpo, hgnc_real)
        assert state.grades == {}
