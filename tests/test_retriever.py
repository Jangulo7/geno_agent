"""Tests for src.agents.retriever — the C4 Retriever node.

Two tiers:
  * Unit tests with monkeypatched ``hybrid_search`` (fast, no I/O).
  * Integration tests against the live Qdrant demo collection
    (gracefully skipped when Docker/Qdrant is unreachable).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Generator

import pytest
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from src.agents import retriever as retriever_module
from src.agents.retriever import retrieve_for_gene, retriever_node
from src.agents.state import AgentState, RetrievedChunk
from src.tools.qdrant_search import SearchConfig

# ---------------------------------------------------------------- unit tests


def _state(genes: list[str], queries: list[str] | None = None) -> AgentState:
    return AgentState(
        case_id="test-case",
        hpo_terms=["HP:0001250"],
        candidate_genes=genes,
        mesh_queries=queries if queries is not None else [],
    )


def _fake_chunks(gene: str, n: int) -> list[RetrievedChunk]:
    """Build n fake chunks for ``gene`` with deterministic IDs and scores."""
    return [
        RetrievedChunk(
            chunk_id=f"{gene}-chunk-{i}",
            pmcid=f"PMC{i:04d}",
            text=f"Text mentioning {gene} at index {i}",
            section_type="results",
            score_rrf=1.0 / (i + 1),
        )
        for i in range(n)
    ]


@pytest.fixture
def mock_search(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[int], list[tuple[str, str, int, str, bool]]]:
    """Monkeypatch ``hybrid_search`` and return a recorder of call args.

    Returns a list-like recorder so each test can assert on the calls made.
    Each call gets recorded as ``(query, gene_filter_or_None, top_k, mode, used_gene_filter)``.
    """
    calls: list[tuple[str, str | None, int, str, bool]] = []

    def fake(cfg: SearchConfig, query: str, *, top_k: int, mode: str, gene_filter: str | None):
        calls.append((query, gene_filter, top_k, mode, gene_filter is not None))
        # Derive the gene from the query string's first token (matches Planner output).
        gene = query.split()[0] if query else "UNKNOWN"
        return _fake_chunks(gene, n=min(top_k, 3))

    monkeypatch.setattr(retriever_module, "hybrid_search", fake)
    return calls  # type: ignore[return-value]


class TestRetrieveForGene:
    def test_calls_hybrid_search_with_args(self, mock_search) -> None:
        chunks = retrieve_for_gene(
            cfg=None,  # type: ignore[arg-type] — mock doesn't read it
            query="BRCA1 breast cancer",
            gene="BRCA1",
            top_k=5,
            mode="hybrid",
            use_gene_filter=False,
        )
        assert len(chunks) == 3  # mock returns min(top_k, 3)
        assert mock_search[0] == ("BRCA1 breast cancer", None, 5, "hybrid", False)

    def test_passes_gene_filter_when_enabled(self, mock_search) -> None:
        retrieve_for_gene(
            cfg=None,  # type: ignore[arg-type]
            query="TP53 tumor",
            gene="TP53",
            top_k=10,
            use_gene_filter=True,
        )
        assert mock_search[0][1] == "TP53"  # gene_filter forwarded
        assert mock_search[0][4] is True  # used_gene_filter flag


class TestRetrieverNode:
    def test_populates_state_retrieved_keyed_by_gene(self, mock_search) -> None:
        state = _state(
            genes=["BRCA1", "TP53", "FBN1"],
            queries=["BRCA1 q", "TP53 q", "FBN1 q"],
        )
        retriever_node(state, cfg=None, top_k=5)  # type: ignore[arg-type]
        assert set(state.retrieved.keys()) == {"BRCA1", "TP53", "FBN1"}
        for gene in state.candidate_genes:
            assert all(isinstance(c, RetrievedChunk) for c in state.retrieved[gene])

    def test_one_search_call_per_gene(self, mock_search) -> None:
        state = _state(genes=["A", "B", "C"], queries=["A q", "B q", "C q"])
        retriever_node(state, cfg=None, top_k=3)  # type: ignore[arg-type]
        assert len(mock_search) == 3

    def test_falls_back_to_gene_symbol_when_queries_missing(self, mock_search) -> None:
        """If mesh_queries is shorter than candidate_genes, use bare symbol for the rest."""
        state = _state(genes=["BRCA1", "TP53"], queries=["BRCA1 with HPO"])
        retriever_node(state, cfg=None, top_k=3)  # type: ignore[arg-type]
        # First call uses the planner query; second falls back to the symbol
        assert mock_search[0][0] == "BRCA1 with HPO"
        assert mock_search[1][0] == "TP53"

    def test_empty_candidate_genes_no_calls(self, mock_search) -> None:
        state = _state(genes=[], queries=[])
        retriever_node(state, cfg=None, top_k=5)  # type: ignore[arg-type]
        assert state.retrieved == {}
        assert len(mock_search) == 0

    def test_top_k_forwarded(self, mock_search) -> None:
        state = _state(genes=["BRCA1"], queries=["BRCA1 q"])
        retriever_node(state, cfg=None, top_k=42)  # type: ignore[arg-type]
        assert mock_search[0][2] == 42

    def test_mode_forwarded(self, mock_search) -> None:
        state = _state(genes=["BRCA1"], queries=["BRCA1 q"])
        retriever_node(state, cfg=None, top_k=5, mode="dense")  # type: ignore[arg-type]
        assert mock_search[0][3] == "dense"

    def test_gene_filter_off_by_default(self, mock_search) -> None:
        state = _state(genes=["BRCA1"], queries=["BRCA1 q"])
        retriever_node(state, cfg=None)  # type: ignore[arg-type]
        assert mock_search[0][4] is False

    def test_returns_same_state_object(self, mock_search) -> None:
        state = _state(genes=["BRCA1"], queries=["BRCA1 q"])
        out = retriever_node(state, cfg=None)  # type: ignore[arg-type]
        assert out is state


# ---------------------------------------------------------------- integration

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL_NAME = os.environ.get("EMBED_MODEL_NAME", "NeuML/pubmedbert-base-embeddings")


def _qdrant_alive() -> bool:
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
        n = client.count(collection_name=COLLECTION, exact=True).count
        return n > 0
    except Exception:  # intentionally broad — fixture must skip, not error
        return False


@pytest.fixture(scope="module")
def live_cfg() -> Generator[SearchConfig, None, None]:
    if not _qdrant_alive():
        pytest.skip(
            f"Qdrant collection {COLLECTION!r} unreachable at "
            f"{QDRANT_HOST}:{QDRANT_PORT} — run the demo pipeline first."
        )
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60)
    dense = SentenceTransformer(DENSE_MODEL_NAME)
    bm25 = SparseTextEmbedding(model_name="Qdrant/bm25")
    yield SearchConfig(
        client=client, collection_name=COLLECTION, dense_model=dense, bm25_model=bm25
    )


@pytest.mark.integration
class TestLiveRetrieverNode:
    """Integration: exercise the Retriever against the demo Qdrant collection."""

    def test_demo_corpus_produces_chunks(self, live_cfg: SearchConfig) -> None:
        state = AgentState(
            case_id="live-test",
            hpo_terms=["HP:0001250"],
            candidate_genes=["BRCA1", "FBN1"],
            mesh_queries=["BRCA1 breast cancer", "FBN1 Marfan syndrome"],
        )
        retriever_node(state, live_cfg, top_k=5)
        assert "BRCA1" in state.retrieved
        assert "FBN1" in state.retrieved
        # The demo collection covers Marfan but not breast cancer; FBN1 should
        # produce real hits, BRCA1 may be empty or weakly relevant — either is OK.
        assert len(state.retrieved["FBN1"]) > 0

    def test_chunks_are_well_formed(self, live_cfg: SearchConfig) -> None:
        state = AgentState(
            case_id="live-test-2",
            hpo_terms=["HP:0001250"],
            candidate_genes=["FBN1"],
            mesh_queries=["FBN1 Marfan syndrome aortic aneurysm"],
        )
        retriever_node(state, live_cfg, top_k=3, mode="hybrid")
        for c in state.retrieved["FBN1"]:
            assert c.chunk_id  # non-empty
            assert c.pmcid.startswith("PMC")
            assert c.score_rrf is not None  # hybrid mode populates RRF
