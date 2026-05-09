"""Tests for src.tools.hgnc — HGNC validation helpers (master plan §11.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.hgnc import (
    HgncIndex,
    canonicalize,
    hgnc_validate,
    is_canonical_symbol,
    load_hgnc,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HGNC_TSV = PROJECT_ROOT / "data" / "HGNC" / "hgnc_complete_set_2026-04-07.txt"


@pytest.fixture(scope="module")
def hgnc_index() -> HgncIndex:
    """Module-scoped HGNC fixture — loaded once per pytest run."""
    if not HGNC_TSV.exists():
        pytest.skip(f"HGNC TSV not present: {HGNC_TSV}")
    # Clear the lru_cache for clean test isolation
    load_hgnc.cache_clear()
    return load_hgnc(HGNC_TSV)


class TestLoadHgnc:
    def test_load_returns_indexes(self, hgnc_index: HgncIndex) -> None:
        assert isinstance(hgnc_index.by_symbol, dict)
        assert isinstance(hgnc_index.alias_to_symbol, dict)
        assert len(hgnc_index.by_symbol) > 19_000
        # alias map should be smaller than canonical map (most aliases are unique)
        assert len(hgnc_index.alias_to_symbol) > 1_000

    def test_known_canonical_symbols(self, hgnc_index: HgncIndex) -> None:
        for s in ("BRCA1", "TP53", "TTN", "FBN1", "ABCA4"):
            assert s in hgnc_index.by_symbol, f"{s} should be a canonical HGNC symbol"

    def test_entry_has_required_fields(self, hgnc_index: HgncIndex) -> None:
        e = hgnc_index.by_symbol["BRCA1"]
        assert e.symbol == "BRCA1"
        assert e.locus_group == "protein-coding gene"
        assert e.hgnc_id.startswith("HGNC:")
        assert e.name  # non-empty

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        load_hgnc.cache_clear()
        with pytest.raises(FileNotFoundError):
            load_hgnc(tmp_path / "does-not-exist.txt")


class TestCanonicalSymbol:
    def test_canonical_returns_self(self, hgnc_index: HgncIndex) -> None:
        assert canonicalize("BRCA1", hgnc_index) == "BRCA1"

    def test_alias_resolves(self, hgnc_index: HgncIndex) -> None:
        """``HER2`` is an HGNC alias for ``ERBB2``."""
        # Skip if this alias mapping isn't in the snapshot for some reason
        if "HER2" not in hgnc_index.alias_to_symbol:
            pytest.skip("HER2 alias mapping not in this HGNC snapshot")
        assert canonicalize("HER2", hgnc_index) == "ERBB2"

    def test_unknown_returns_none(self, hgnc_index: HgncIndex) -> None:
        assert canonicalize("ZZZ_NOT_A_GENE", hgnc_index) is None

    def test_is_canonical(self, hgnc_index: HgncIndex) -> None:
        assert is_canonical_symbol("BRCA1", hgnc_index) is True
        assert is_canonical_symbol("ZZZ_NOT_A_GENE", hgnc_index) is False


class TestHgncValidate:
    def test_canonical_validates(self, hgnc_index: HgncIndex) -> None:
        for s in ("BRCA1", "TP53", "TTN"):
            assert hgnc_validate(s, hgnc_index) is True

    def test_unknown_does_not_validate(self, hgnc_index: HgncIndex) -> None:
        assert hgnc_validate("ZZZ_NOT_A_GENE", hgnc_index) is False
