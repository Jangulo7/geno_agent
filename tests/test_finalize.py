"""Tests for Phase 1B finalize step (B8 / scripts/cases/19_finalize_test_cases.py).

Covers the canonical schema projection, deterministic JSONL ordering by
``case_id``, and SHA-256 stability.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_finalize_module():
    """Load ``19_finalize_test_cases.py`` by file path."""
    path = PROJECT_ROOT / "scripts" / "cases" / "19_finalize_test_cases.py"
    spec = importlib.util.spec_from_file_location("finalize_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["finalize_module"] = module
    spec.loader.exec_module(module)
    return module


def _sample_b7_record(case_id: str = "ABC:case-001", causal: str = "BRCA1") -> dict:
    """Construct a minimal B7-shaped record for projection tests."""
    return {
        "case_id": case_id,
        "source_path": f"data/phenopackets/v0.1.19/0.1.19/ABC/{case_id}.json",
        "subject_id": "Patient X",
        "category": "neurological",
        "category_resolution": "priority-first; matched=[neurological]",
        "hpo_terms": ["HP:0001250", "HP:0001263"],
        "diseases": [{"id": "OMIM:154700", "label": "Marfan syndrome"}],
        "interpretations": [{"gene_symbol": causal, "hgnc_id": "HGNC:3603", "ascertained": True}],
        "causal_gene": causal,
        "mondo_ids": ["MONDO:0007947"],
        "candidate_genes": [causal] + [f"GENE{i:04d}" for i in range(49)],
        "n_candidates": 50,
        "causal_gene_index_in_candidates": 0,
    }


class TestProjectToCanonical:
    """``project_to_canonical`` keeps only the canonical schema fields."""

    def test_returns_canonical_keys_only(self) -> None:
        finalize = _load_finalize_module()
        out = finalize.project_to_canonical(_sample_b7_record())
        assert set(out.keys()) == set(finalize.CANONICAL_FIELDS)

    def test_renames_source_path_to_source_phenopacket(self) -> None:
        finalize = _load_finalize_module()
        out = finalize.project_to_canonical(_sample_b7_record())
        assert out["source_phenopacket"].endswith(".json")
        assert "source_path" not in out

    def test_drops_intermediate_fields(self) -> None:
        """Intermediate fields like mondo_ids, interpretations, subject_id are dropped."""
        finalize = _load_finalize_module()
        out = finalize.project_to_canonical(_sample_b7_record())
        for dropped in (
            "mondo_ids",
            "interpretations",
            "subject_id",
            "category_resolution",
            "n_candidates",
        ):
            assert dropped not in out

    def test_pmc_count_none_when_b6_not_run(self) -> None:
        """When the input lacks pmc_article_count, output sets it to None."""
        finalize = _load_finalize_module()
        rec = _sample_b7_record()
        rec.pop("pmc_article_count", None)
        out = finalize.project_to_canonical(rec)
        assert out["pmc_article_count"] is None

    def test_pmc_count_preserved_when_present(self) -> None:
        """When B6 set pmc_article_count, it carries through unchanged."""
        finalize = _load_finalize_module()
        rec = _sample_b7_record()
        rec["pmc_article_count"] = 12
        out = finalize.project_to_canonical(rec)
        assert out["pmc_article_count"] == 12


class TestWriteCanonicalJsonl:
    """``write_canonical_jsonl`` produces a deterministic, sorted, hashed file."""

    def test_sorted_by_case_id(self, tmp_path: Path) -> None:
        finalize = _load_finalize_module()
        recs = [
            _sample_b7_record("z-case"),
            _sample_b7_record("a-case"),
            _sample_b7_record("m-case"),
        ]
        canonical = [finalize.project_to_canonical(r) for r in recs]
        out = tmp_path / "out.jsonl"
        finalize.write_canonical_jsonl(canonical, out)

        lines = out.read_text(encoding="utf-8").splitlines()
        ids = [json.loads(line)["case_id"] for line in lines]
        assert ids == ["a-case", "m-case", "z-case"]

    def test_sha256_stable_across_runs(self, tmp_path: Path) -> None:
        """Same input → same output → same SHA-256."""
        finalize = _load_finalize_module()
        recs = [
            finalize.project_to_canonical(_sample_b7_record("c1")),
            finalize.project_to_canonical(_sample_b7_record("c2")),
        ]
        out1 = tmp_path / "a.jsonl"
        out2 = tmp_path / "b.jsonl"
        sha1 = finalize.write_canonical_jsonl(recs, out1)
        sha2 = finalize.write_canonical_jsonl(recs, out2)
        assert sha1 == sha2
        # And the SHA matches a fresh hashlib over the file
        assert sha1 == hashlib.sha256(out1.read_bytes()).hexdigest()


class TestBuildManifest:
    """``build_manifest`` produces a complete provenance record."""

    def test_required_fields(self, tmp_path: Path) -> None:
        finalize = _load_finalize_module()
        recs = [finalize.project_to_canonical(_sample_b7_record(f"c{i}")) for i in range(5)]
        out = tmp_path / "out.jsonl"
        sha = finalize.write_canonical_jsonl(recs, out)
        manifest = finalize.build_manifest(recs, out, sha)
        for required in (
            "created_at_utc",
            "n_cases",
            "category_distribution",
            "sha256",
            "bytes",
            "random_seed",
            "pmc_coverage_validated",
        ):
            assert required in manifest

    def test_pmc_coverage_false_when_b6_skipped(self, tmp_path: Path) -> None:
        """When records have pmc_article_count=None, coverage flag is False."""
        finalize = _load_finalize_module()
        recs = [finalize.project_to_canonical(_sample_b7_record(f"c{i}")) for i in range(3)]
        # _sample_b7_record doesn't set pmc_article_count → None after projection
        out = tmp_path / "out.jsonl"
        sha = finalize.write_canonical_jsonl(recs, out)
        manifest = finalize.build_manifest(recs, out, sha)
        assert manifest["pmc_coverage_validated"] is False
        assert manifest["n_cases_with_pmc_coverage"] == 0

    def test_pmc_coverage_true_when_all_validated(self, tmp_path: Path) -> None:
        finalize = _load_finalize_module()
        recs = []
        for i in range(3):
            r = _sample_b7_record(f"c{i}")
            r["pmc_article_count"] = 10
            recs.append(finalize.project_to_canonical(r))
        out = tmp_path / "out.jsonl"
        sha = finalize.write_canonical_jsonl(recs, out)
        manifest = finalize.build_manifest(recs, out, sha)
        assert manifest["pmc_coverage_validated"] is True
        assert manifest["n_cases_with_pmc_coverage"] == 3
