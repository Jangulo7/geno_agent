"""Tests for deterministic UUID5 chunk-ID derivation.

The chunk-ID function is the load-bearing piece of the project's
reproducibility contract (master plan §4.1.3 / fix #2). Identical inputs
must produce identical UUIDs across runs, machines, and Python versions —
or the entire Qdrant index becomes unstable.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_chunker_module():
    """Load the numbered script ``08_section_aware_chunking.py`` by file path."""
    path = PROJECT_ROOT / "scripts" / "corpus" / "08_section_aware_chunking.py"
    spec = importlib.util.spec_from_file_location("chunker_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["chunker_module"] = module
    spec.loader.exec_module(module)
    return module


class TestDeterministicChunkId:
    """``deterministic_chunk_id`` must be byte-stable across runs."""

    def test_pinned_namespace_unchanged(self) -> None:
        """The namespace UUID is a project-wide invariant — DO NOT CHANGE."""
        chunker = _load_chunker_module()
        assert uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff") == chunker.CHUNK_NAMESPACE

    def test_same_inputs_same_id(self) -> None:
        """Two calls with identical inputs return identical UUIDs."""
        chunker = _load_chunker_module()
        a = chunker.deterministic_chunk_id("PMC123", "introduction", 0, "Lorem ipsum.")
        b = chunker.deterministic_chunk_id("PMC123", "introduction", 0, "Lorem ipsum.")
        assert a == b

    def test_different_pmcid_different_id(self) -> None:
        chunker = _load_chunker_module()
        a = chunker.deterministic_chunk_id("PMC123", "introduction", 0, "x")
        b = chunker.deterministic_chunk_id("PMC456", "introduction", 0, "x")
        assert a != b

    def test_different_section_type_different_id(self) -> None:
        chunker = _load_chunker_module()
        a = chunker.deterministic_chunk_id("PMC123", "introduction", 0, "x")
        b = chunker.deterministic_chunk_id("PMC123", "methods", 0, "x")
        assert a != b

    def test_different_chunk_index_different_id(self) -> None:
        chunker = _load_chunker_module()
        a = chunker.deterministic_chunk_id("PMC123", "introduction", 0, "x")
        b = chunker.deterministic_chunk_id("PMC123", "introduction", 1, "x")
        assert a != b

    def test_different_text_different_id(self) -> None:
        chunker = _load_chunker_module()
        a = chunker.deterministic_chunk_id("PMC123", "introduction", 0, "alpha")
        b = chunker.deterministic_chunk_id("PMC123", "introduction", 0, "beta")
        assert a != b

    def test_returns_valid_uuid_string(self) -> None:
        """Output is a hyphenated UUID string parseable by ``uuid.UUID``."""
        chunker = _load_chunker_module()
        out = chunker.deterministic_chunk_id("PMC1", "intro", 0, "x")
        # Must round-trip through UUID()
        parsed = uuid.UUID(out)
        assert str(parsed) == out


class TestClassifySection:
    """``classify_section`` maps headings to standardized section types."""

    def test_explicit_sec_type_wins(self) -> None:
        """When ``sec-type`` attribute is set, it takes priority over heading."""

        # Need the parser module not the chunker for classify_section
        path = PROJECT_ROOT / "scripts" / "corpus" / "06_parse_jats_xml.py"
        spec = importlib.util.spec_from_file_location("parser_module", path)
        assert spec is not None and spec.loader is not None
        parser = importlib.util.module_from_spec(spec)
        sys.modules["parser_module"] = parser
        spec.loader.exec_module(parser)

        assert parser.classify_section("Some Title", "intro") == "introduction"
        assert parser.classify_section("Some Title", "methods") == "methods"
        assert parser.classify_section("Some Title", "results") == "results"
        assert parser.classify_section("Some Title", "discussion") == "discussion"
        assert parser.classify_section("Some Title", "conclusion") == "conclusion"

    def test_heading_regex_fallback(self) -> None:

        path = PROJECT_ROOT / "scripts" / "corpus" / "06_parse_jats_xml.py"
        spec = importlib.util.spec_from_file_location("parser_module2", path)
        assert spec is not None and spec.loader is not None
        parser = importlib.util.module_from_spec(spec)
        sys.modules["parser_module2"] = parser
        spec.loader.exec_module(parser)

        # No sec-type → regex on heading text
        assert parser.classify_section("Introduction", None) == "introduction"
        assert parser.classify_section("Background", "") == "introduction"
        assert parser.classify_section("Materials and Methods", "") == "methods"
        assert parser.classify_section("Results", "") == "results"
        assert parser.classify_section("Case Report", "") == "case"
        assert parser.classify_section("Discussion", "") == "discussion"
        assert parser.classify_section("Conclusions", "") == "conclusion"

    def test_unmatched_falls_back_to_other(self) -> None:
        path = PROJECT_ROOT / "scripts" / "corpus" / "06_parse_jats_xml.py"
        spec = importlib.util.spec_from_file_location("parser_module3", path)
        assert spec is not None and spec.loader is not None
        parser = importlib.util.module_from_spec(spec)
        sys.modules["parser_module3"] = parser
        spec.loader.exec_module(parser)

        assert parser.classify_section("Author Contributions", "") == "other"
        assert parser.classify_section("Acknowledgements", "") == "other"
