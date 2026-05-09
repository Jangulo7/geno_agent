"""Tests for Phase 1B parsing helpers (phenopacket extraction).

Smoke-tests the schema-tolerant extractors in
``scripts/cases/13_load_phenopackets.py``. We construct minimal phenopacket
dicts by hand to avoid the slow file I/O of the real 6,668-record corpus.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_loader_module():
    """Load the numbered script ``13_load_phenopackets.py`` by file path."""
    path = PROJECT_ROOT / "scripts" / "cases" / "13_load_phenopackets.py"
    spec = importlib.util.spec_from_file_location("phenopacket_loader_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["phenopacket_loader_module"] = module
    spec.loader.exec_module(module)
    return module


class TestExtractHpoTerms:
    """``extract_hpo_terms`` keeps only observed (non-excluded) HPO IDs, dedupes."""

    def test_simple_observed(self) -> None:
        loader = _load_loader_module()
        pp = {
            "phenotypicFeatures": [
                {"type": {"id": "HP:0001250", "label": "Seizure"}},
                {"type": {"id": "HP:0001263", "label": "Global delay"}},
            ]
        }
        assert loader.extract_hpo_terms(pp) == ["HP:0001250", "HP:0001263"]

    def test_excluded_dropped(self) -> None:
        loader = _load_loader_module()
        pp = {
            "phenotypicFeatures": [
                {"type": {"id": "HP:0001250"}},
                {"type": {"id": "HP:9999999"}, "excluded": True},
            ]
        }
        assert loader.extract_hpo_terms(pp) == ["HP:0001250"]

    def test_dedup_preserves_order(self) -> None:
        loader = _load_loader_module()
        pp = {
            "phenotypicFeatures": [
                {"type": {"id": "HP:0001250"}},
                {"type": {"id": "HP:0001263"}},
                {"type": {"id": "HP:0001250"}},
            ]
        }
        assert loader.extract_hpo_terms(pp) == ["HP:0001250", "HP:0001263"]

    def test_non_hp_dropped(self) -> None:
        loader = _load_loader_module()
        pp = {
            "phenotypicFeatures": [
                {"type": {"id": "HP:0001250"}},
                {"type": {"id": "MONDO:0007947"}},  # not an HP id
            ]
        }
        assert loader.extract_hpo_terms(pp) == ["HP:0001250"]

    def test_missing_key_returns_empty(self) -> None:
        loader = _load_loader_module()
        assert loader.extract_hpo_terms({}) == []


class TestExtractDiseases:
    """``extract_diseases`` filters out excluded entries."""

    def test_simple(self) -> None:
        loader = _load_loader_module()
        pp = {"diseases": [{"term": {"id": "OMIM:154700", "label": "Marfan syndrome"}}]}
        assert loader.extract_diseases(pp) == [{"id": "OMIM:154700", "label": "Marfan syndrome"}]

    def test_excluded_dropped(self) -> None:
        loader = _load_loader_module()
        pp = {
            "diseases": [
                {"term": {"id": "OMIM:154700", "label": "Marfan"}},
                {"term": {"id": "OMIM:999999", "label": "Other"}, "excluded": True},
            ]
        }
        assert loader.extract_diseases(pp) == [{"id": "OMIM:154700", "label": "Marfan"}]


class TestExtractInterpretations:
    """``extract_interpretations`` walks the v2 nested structure."""

    def test_full_path(self) -> None:
        loader = _load_loader_module()
        pp = {
            "interpretations": [
                {
                    "diagnosis": {
                        "genomicInterpretations": [
                            {
                                "interpretationStatus": "CAUSATIVE",
                                "variantInterpretation": {
                                    "variationDescriptor": {
                                        "label": "c.4577C>T",
                                        "geneContext": {
                                            "symbol": "FBN1",
                                            "valueId": "HGNC:3603",
                                        },
                                    }
                                },
                            }
                        ]
                    }
                }
            ]
        }
        out = loader.extract_interpretations(pp)
        assert len(out) == 1
        assert out[0]["gene_symbol"] == "FBN1"
        assert out[0]["hgnc_id"] == "HGNC:3603"
        assert out[0]["variant"] == "c.4577C>T"
        assert out[0]["ascertained"] is True

    def test_missing_status_treated_as_ascertained(self) -> None:
        """Phenopackets often omit the status field — treat as ascertained per master plan §6 step 1."""
        loader = _load_loader_module()
        pp = {
            "interpretations": [
                {
                    "diagnosis": {
                        "genomicInterpretations": [
                            {
                                "variantInterpretation": {
                                    "variationDescriptor": {"geneContext": {"symbol": "BRCA1"}}
                                }
                            }
                        ]
                    }
                }
            ]
        }
        out = loader.extract_interpretations(pp)
        assert len(out) == 1
        assert out[0]["gene_symbol"] == "BRCA1"
        assert out[0]["ascertained"] is True

    def test_missing_symbol_drops_record(self) -> None:
        loader = _load_loader_module()
        pp = {
            "interpretations": [
                {
                    "diagnosis": {
                        "genomicInterpretations": [
                            {"variantInterpretation": {"variationDescriptor": {"geneContext": {}}}}
                        ]
                    }
                }
            ]
        }
        assert loader.extract_interpretations(pp) == []

    def test_no_interpretations(self) -> None:
        loader = _load_loader_module()
        assert loader.extract_interpretations({}) == []
