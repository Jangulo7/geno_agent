"""Tests for src.agents.query_planner — the C3 Query Planner node.

Two tiers of tests:
  * Pure-function tests with hand-built tiny ontologies (fast, no I/O).
  * Real-HPO tests when the pinned `hp.obo` is on disk.
"""

from __future__ import annotations

from pathlib import Path

import pronto
import pytest

from src.agents.query_planner import (
    build_mesh_queries,
    plan_hpo_expansion,
    query_planner_node,
)
from src.agents.state import AgentState
from src.tools.hpo import load_hpo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HPO_OBO = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"


@pytest.fixture(scope="module")
def hpo() -> pronto.Ontology:
    """Module-scoped HPO fixture; skip the test class if the file is missing."""
    if not HPO_OBO.exists():
        pytest.skip(f"HPO obo not present: {HPO_OBO}")
    load_hpo.cache_clear()
    return load_hpo(HPO_OBO)


def _state(
    hpo_terms: list[str] | None = None,
    candidate_genes: list[str] | None = None,
) -> AgentState:
    return AgentState(
        case_id="test-case",
        hpo_terms=hpo_terms if hpo_terms is not None else ["HP:0001250"],
        candidate_genes=candidate_genes if candidate_genes is not None else ["BRCA1", "TP53"],
    )


class TestPlanHpoExpansion:
    """Pure expansion test on real HPO data."""

    def test_includes_self(self, hpo: pronto.Ontology) -> None:
        out = plan_hpo_expansion(_state(["HP:0001250"]), hpo, distance=2)
        assert "HP:0001250" in out

    def test_includes_known_ancestor(self, hpo: pronto.Ontology) -> None:
        """HP:0012638 (Abnormal nervous system physiology) is an ancestor of Seizure."""
        out = plan_hpo_expansion(_state(["HP:0001250"]), hpo, distance=2)
        assert "HP:0012638" in out

    def test_distance_zero_just_self(self, hpo: pronto.Ontology) -> None:
        out = plan_hpo_expansion(_state(["HP:0001250"]), hpo, distance=0)
        assert out == ["HP:0001250"]

    def test_dedup_when_terms_share_ancestors(self, hpo: pronto.Ontology) -> None:
        """Two HPO terms with overlapping ancestors must not produce duplicates."""
        out = plan_hpo_expansion(_state(["HP:0001250", "HP:0001250"]), hpo, distance=2)
        assert len(out) == len(set(out))


class TestBuildMeshQueries:
    """Per-gene query construction."""

    def test_one_query_per_candidate(self, hpo: pronto.Ontology) -> None:
        state = _state(
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1", "TP53", "FBN1"],
        )
        queries = build_mesh_queries(state, hpo)
        assert len(queries) == 3

    def test_query_starts_with_gene_symbol(self, hpo: pronto.Ontology) -> None:
        """Gene symbol must be first token — BM25 needs a strong lexical anchor."""
        state = _state(["HP:0001250"], ["BRCA1"])
        queries = build_mesh_queries(state, hpo)
        assert queries[0].startswith("BRCA1")

    def test_query_contains_hpo_label(self, hpo: pronto.Ontology) -> None:
        """HP:0001250's label is 'Seizure' — must appear in the query string."""
        state = _state(["HP:0001250"], ["BRCA1"])
        queries = build_mesh_queries(state, hpo)
        assert "Seizure" in queries[0]

    def test_uses_expanded_hpo_when_present(self, hpo: pronto.Ontology) -> None:
        """When ``state.expanded_hpo`` is populated, queries draw from it."""
        state = _state(["HP:0001250"], ["BRCA1"])
        # Manually inject a different expanded set
        state.expanded_hpo = ["HP:0012638"]  # Abnormal nervous system physiology
        queries = build_mesh_queries(state, hpo)
        # Now the label should be the EXPANDED ancestor, not Seizure
        assert "Abnormal nervous system physiology" in queries[0]
        assert "Seizure" not in queries[0]

    def test_max_labels_cap_honored(self, hpo: pronto.Ontology) -> None:
        """The per-query label cap reduces the query string length."""
        state = _state(
            ["HP:0001250", "HP:0001263", "HP:0002650"],
            ["BRCA1"],
        )
        capped = build_mesh_queries(state, hpo, max_labels_per_query=1)
        wide = build_mesh_queries(state, hpo, max_labels_per_query=5)
        assert len(capped[0]) < len(wide[0])

    def test_empty_candidate_genes_empty_output(self, hpo: pronto.Ontology) -> None:
        state = _state(["HP:0001250"], [])
        assert build_mesh_queries(state, hpo) == []

    def test_unknown_hpo_silently_dropped(self, hpo: pronto.Ontology) -> None:
        """Bogus HPO IDs are silently ignored — query is still well-formed."""
        state = _state(["HP:9999999", "HP:0001250"], ["BRCA1"])
        queries = build_mesh_queries(state, hpo)
        # Must contain BRCA1 and Seizure; must not contain the bogus ID
        assert "BRCA1" in queries[0]
        assert "Seizure" in queries[0]
        assert "HP:9999999" not in queries[0]


class TestQueryPlannerNode:
    """The full node mutates state with both expansion and queries."""

    def test_writes_expanded_hpo(self, hpo: pronto.Ontology) -> None:
        state = _state(["HP:0001250"], ["BRCA1"])
        out = query_planner_node(state, hpo, distance=2)
        assert out is state
        assert len(state.expanded_hpo) > 1
        assert "HP:0001250" in state.expanded_hpo

    def test_writes_mesh_queries(self, hpo: pronto.Ontology) -> None:
        state = _state(["HP:0001250"], ["BRCA1", "TP53"])
        query_planner_node(state, hpo)
        assert len(state.mesh_queries) == 2
        assert state.mesh_queries[0].startswith("BRCA1")
        assert state.mesh_queries[1].startswith("TP53")

    def test_idempotent_on_resolved_state(self, hpo: pronto.Ontology) -> None:
        """Running the node twice produces identical state."""
        s1 = _state(["HP:0001250"], ["BRCA1"])
        s2 = _state(["HP:0001250"], ["BRCA1"])
        query_planner_node(s1, hpo)
        query_planner_node(s2, hpo)
        assert s1.expanded_hpo == s2.expanded_hpo
        assert s1.mesh_queries == s2.mesh_queries

    def test_deterministic_output(self, hpo: pronto.Ontology) -> None:
        """Running the node twice on the same state is stable."""
        state = _state(["HP:0001250"], ["BRCA1"])
        query_planner_node(state, hpo)
        first_expansion = list(state.expanded_hpo)
        first_queries = list(state.mesh_queries)
        query_planner_node(state, hpo)
        assert state.expanded_hpo == first_expansion
        assert state.mesh_queries == first_queries
