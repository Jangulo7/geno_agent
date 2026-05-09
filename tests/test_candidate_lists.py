"""Tests for the candidate-list builder (B7 / scripts/cases/18_build_candidate_lists.py).

Covers:
  * ``per_case_seed`` is deterministic per (case_id, global_seed).
  * Different case_ids produce different seeds.
  * ``build_candidate_list`` produces a list of size ``1 + n_distractors``.
  * The causal gene is always in the output.
  * The recorded ``causal_index`` truly points to the causal gene.
  * Re-running with the same case_id reproduces the same list bit-for-bit.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_builder_module():
    """Load ``18_build_candidate_lists.py`` by file path."""
    path = PROJECT_ROOT / "scripts" / "cases" / "18_build_candidate_lists.py"
    spec = importlib.util.spec_from_file_location("candidate_builder_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_builder_module"] = module
    spec.loader.exec_module(module)
    return module


# Sample HGNC-like pool — sorted, no duplicates, includes a few known genes
SAMPLE_POOL = sorted(
    {f"GENE{i:04d}" for i in range(500)} | {"BRCA1", "TP53", "TTN", "FBN1", "ABCA4"}
)


class TestPerCaseSeed:
    """Per-case derived seed must be deterministic and case-distinct."""

    def test_deterministic(self) -> None:
        builder = _load_builder_module()
        a = builder.per_case_seed("case-001")
        b = builder.per_case_seed("case-001")
        assert a == b

    def test_different_case_id_different_seed(self) -> None:
        builder = _load_builder_module()
        assert builder.per_case_seed("case-001") != builder.per_case_seed("case-002")

    def test_different_global_seed_different_seed(self) -> None:
        builder = _load_builder_module()
        a = builder.per_case_seed("case-001", global_seed=42)
        b = builder.per_case_seed("case-001", global_seed=43)
        assert a != b

    def test_returns_int_within_64_bits(self) -> None:
        builder = _load_builder_module()
        s = builder.per_case_seed("any-case-id")
        assert isinstance(s, int)
        assert 0 <= s < 2**64


class TestBuildCandidateList:
    """The 50-gene candidate list must contain the causal gene and N distractors."""

    def test_size_is_n_plus_one(self) -> None:
        builder = _load_builder_module()
        cands, _ = builder.build_candidate_list("BRCA1", "case-001", SAMPLE_POOL, 49)
        assert len(cands) == 50

    def test_causal_present(self) -> None:
        builder = _load_builder_module()
        cands, idx = builder.build_candidate_list("BRCA1", "case-001", SAMPLE_POOL, 49)
        assert "BRCA1" in cands
        assert cands[idx] == "BRCA1"

    def test_no_duplicates(self) -> None:
        builder = _load_builder_module()
        cands, _ = builder.build_candidate_list("TP53", "case-002", SAMPLE_POOL, 49)
        assert len(set(cands)) == len(cands)

    def test_causal_excluded_from_distractor_pool(self) -> None:
        """The causal gene must not be drawn as a distractor (only added once)."""
        builder = _load_builder_module()
        cands, _ = builder.build_candidate_list("FBN1", "case-003", SAMPLE_POOL, 49)
        # FBN1 should appear exactly once
        assert cands.count("FBN1") == 1

    def test_reproducible_same_case_id(self) -> None:
        """Same (causal, case_id, pool, n) → same list, byte-identical."""
        builder = _load_builder_module()
        a, _ = builder.build_candidate_list("BRCA1", "case-001", SAMPLE_POOL, 49)
        b, _ = builder.build_candidate_list("BRCA1", "case-001", SAMPLE_POOL, 49)
        assert a == b

    def test_different_case_id_different_list(self) -> None:
        """Two cases with the same causal gene get different distractors."""
        builder = _load_builder_module()
        a, _ = builder.build_candidate_list("BRCA1", "case-A", SAMPLE_POOL, 49)
        b, _ = builder.build_candidate_list("BRCA1", "case-B", SAMPLE_POOL, 49)
        assert a != b
        # but both contain BRCA1
        assert "BRCA1" in a and "BRCA1" in b

    def test_smaller_n_distractors(self) -> None:
        """Argument honored — not hardcoded to 49."""
        builder = _load_builder_module()
        cands, _ = builder.build_candidate_list("BRCA1", "case-001", SAMPLE_POOL, 9)
        assert len(cands) == 10
        assert "BRCA1" in cands

    def test_causal_index_points_to_causal(self) -> None:
        """Recorded index must actually point to the causal gene."""
        builder = _load_builder_module()
        cands, idx = builder.build_candidate_list("TTN", "case-007", SAMPLE_POOL, 49)
        assert cands[idx] == "TTN"
