"""Integration tests for src.tools.qdrant_search.

These hit a live Qdrant collection (the 1,625-chunk demo populated by
the original Phase 1A demo run). They are skipped automatically if
Qdrant is unreachable or the collection is empty.

Tests are marked ``@pytest.mark.integration`` so they can be excluded
in CI via ``pytest -m 'not integration'``.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from src.agents.state import RetrievedChunk
from src.tools.qdrant_search import SearchConfig, hybrid_search

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL_NAME = os.environ.get("EMBED_MODEL_NAME", "NeuML/pubmedbert-base-embeddings")


def _qdrant_alive() -> bool:
    """Return True iff the configured Qdrant collection has at least 1 point.

    Catches any exception type — these tests must skip gracefully when
    Qdrant or Docker is unavailable, not error-out the test suite.
    """
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
        n = client.count(collection_name=COLLECTION, exact=True).count
        return n > 0
    except Exception:  # intentionally broad — fixture must skip, not error
        return False


pytestmark = [pytest.mark.integration]


@pytest.fixture(scope="module")
def cfg() -> Generator[SearchConfig, None, None]:
    if not _qdrant_alive():
        pytest.skip(
            f"Qdrant collection {COLLECTION!r} unreachable or empty at "
            f"{QDRANT_HOST}:{QDRANT_PORT} — start the demo pipeline first."
        )
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60)
    dense = SentenceTransformer(DENSE_MODEL_NAME)
    bm25 = SparseTextEmbedding(model_name="Qdrant/bm25")
    yield SearchConfig(
        client=client, collection_name=COLLECTION, dense_model=dense, bm25_model=bm25
    )


class TestHybridSearch:
    def test_dense_returns_chunks(self, cfg: SearchConfig) -> None:
        out = hybrid_search(cfg, "BRCA1 mutation breast cancer", top_k=5, mode="dense")
        assert len(out) > 0
        assert all(isinstance(c, RetrievedChunk) for c in out)
        # In dense mode only score_dense is set
        for c in out:
            assert c.score_dense is not None
            assert c.score_bm25 is None
            assert c.score_rrf is None

    def test_bm25_returns_chunks(self, cfg: SearchConfig) -> None:
        out = hybrid_search(cfg, "BRCA1 mutation breast cancer", top_k=5, mode="bm25")
        assert len(out) > 0
        for c in out:
            assert c.score_bm25 is not None
            assert c.score_dense is None
            assert c.score_rrf is None

    def test_hybrid_returns_rrf_score(self, cfg: SearchConfig) -> None:
        out = hybrid_search(cfg, "common variable immunodeficiency", top_k=5, mode="hybrid")
        assert len(out) > 0
        for c in out:
            assert c.score_rrf is not None
            assert c.score_dense is None
            assert c.score_bm25 is None

    def test_top_k_honored(self, cfg: SearchConfig) -> None:
        out = hybrid_search(cfg, "Marfan syndrome FBN1", top_k=3)
        assert len(out) <= 3

    def test_results_ordered_by_score(self, cfg: SearchConfig) -> None:
        out = hybrid_search(cfg, "phenylketonuria", top_k=5, mode="hybrid")
        scores = [c.score_rrf for c in out]
        assert scores == sorted(scores, reverse=True), "results should be score-descending"

    def test_payload_fields_populated(self, cfg: SearchConfig) -> None:
        out = hybrid_search(cfg, "DiGeorge syndrome", top_k=3)
        for c in out:
            assert c.chunk_id  # non-empty UUID5
            assert c.pmcid.startswith("PMC")
            assert c.text  # non-empty
            assert c.section_type in {
                "introduction",
                "methods",
                "results",
                "case",
                "discussion",
                "conclusion",
                "other",
            }

    def test_gene_filter_narrows_results(self, cfg: SearchConfig) -> None:
        """When a gene_filter is supplied, every hit's text should mention it."""
        out = hybrid_search(cfg, "muscular dystrophy", top_k=5, gene_filter="DMD")
        # MatchText is case-insensitive token-level — all hits should mention DMD
        # in their text payload (the filter is what enforces this server-side).
        for c in out:
            assert "dmd" in c.text.lower() or "DMD" in c.text
