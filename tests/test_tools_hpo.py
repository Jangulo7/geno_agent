"""Tests for src.tools.hpo — HPO ontology helpers (master plan §11.1)."""

from __future__ import annotations

from pathlib import Path

import pronto
import pytest

from src.tools.hpo import expand_many, hpo_expand, load_hpo, lookup_term

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HPO_OBO = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"


@pytest.fixture(scope="module")
def hpo() -> pronto.Ontology:
    """Module-scoped HPO fixture — loaded once per pytest run."""
    if not HPO_OBO.exists():
        pytest.skip(f"HPO obo not present: {HPO_OBO}")
    load_hpo.cache_clear()
    return load_hpo(HPO_OBO)


class TestLoadHpo:
    def test_load_returns_ontology(self, hpo: pronto.Ontology) -> None:
        # data-version stamp confirms we got the pinned 2026-02-16 release
        assert "2026-02-16" in (hpo.metadata.data_version or "")

    def test_known_term_present(self, hpo: pronto.Ontology) -> None:
        seizure = hpo.get("HP:0001250")
        assert seizure is not None
        assert "seizure" in (seizure.name or "").lower()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        load_hpo.cache_clear()
        with pytest.raises(FileNotFoundError):
            load_hpo(tmp_path / "missing.obo")


class TestLookupTerm:
    def test_returns_slim_record(self, hpo: pronto.Ontology) -> None:
        t = lookup_term("HP:0001250", hpo)
        assert t is not None
        assert t.id == "HP:0001250"
        assert "seizure" in t.name.lower()
        # parents must be HP-prefixed strings
        for p in t.parents:
            assert p.startswith("HP:")

    def test_unknown_returns_none(self, hpo: pronto.Ontology) -> None:
        assert lookup_term("HP:9999999", hpo) is None


class TestHpoExpand:
    def test_includes_self(self, hpo: pronto.Ontology) -> None:
        out = hpo_expand("HP:0001250", hpo, distance=2)
        assert "HP:0001250" in out

    def test_walks_to_parents(self, hpo: pronto.Ontology) -> None:
        """Distance=2 should pull in at least the immediate parent of Seizure."""
        out = hpo_expand("HP:0001250", hpo, distance=2)
        # HP:0012638 (Abnormal nervous system physiology) is a known ancestor
        assert "HP:0012638" in out

    def test_distance_zero_just_self(self, hpo: pronto.Ontology) -> None:
        out = hpo_expand("HP:0001250", hpo, distance=0)
        assert out == ["HP:0001250"]

    def test_unknown_returns_empty(self, hpo: pronto.Ontology) -> None:
        assert hpo_expand("HP:9999999", hpo, distance=2) == []

    def test_only_hp_prefixed_results(self, hpo: pronto.Ontology) -> None:
        """Pronto sometimes surfaces non-HP ancestors (BFO etc.); we filter."""
        out = hpo_expand("HP:0001250", hpo, distance=4)
        for hp_id in out:
            assert hp_id.startswith("HP:"), f"non-HP id leaked: {hp_id}"


class TestExpandMany:
    def test_dedup_across_inputs(self, hpo: pronto.Ontology) -> None:
        """Two terms with overlapping ancestors should not produce duplicates."""
        out = expand_many(["HP:0001250", "HP:0001250"], hpo, distance=2)
        assert len(out) == len(set(out))

    def test_first_seen_order(self, hpo: pronto.Ontology) -> None:
        """First input term + its ancestors come before later inputs' ancestors."""
        out = expand_many(["HP:0001250", "HP:0001263"], hpo, distance=1)
        assert out.index("HP:0001250") < out.index("HP:0001263")

    def test_empty_input_empty_output(self, hpo: pronto.Ontology) -> None:
        assert expand_many([], hpo) == []
