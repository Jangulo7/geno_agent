"""Qdrant hybrid search wrapper used by the Retriever agent.

The Retriever agent (master plan §11.1) needs a single function:
"given a query string and an optional gene filter, return the top-K
chunks". This module provides that function in three flavors — dense,
BM25, hybrid — sharing a single signature so the agent code can switch
modes via a parameter rather than a different call.

All three return :class:`RetrievedChunk` instances (master plan §11.1
state schema), making the agent code Qdrant-agnostic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from src.agents.state import RetrievedChunk

logger = logging.getLogger(__name__)

RetrievalMode = Literal["dense", "bm25", "hybrid"]


@dataclass(slots=True, frozen=True)
class SearchConfig:
    """Static configuration for the search wrapper.

    Bundling these in a config dataclass means the agent code passes a
    single object instead of 4 keyword arguments to every search call.

    Attributes:
        client: Connected Qdrant client.
        collection_name: Target Qdrant collection (e.g. ``"geno_agent_pmc_oa_v1"``).
        dense_model: Loaded :class:`SentenceTransformer` for query encoding.
        bm25_model: Loaded :class:`SparseTextEmbedding` for sparse query encoding.
    """

    client: QdrantClient
    collection_name: str
    dense_model: SentenceTransformer
    bm25_model: SparseTextEmbedding


def _hit_to_chunk(hit: models.ScoredPoint, mode: RetrievalMode) -> RetrievedChunk:
    """Convert a Qdrant ScoredPoint into a :class:`RetrievedChunk`.

    The conversion places the raw score in the appropriate
    score field based on retrieval mode, leaving the others ``None``.
    """
    p = hit.payload or {}
    return RetrievedChunk(
        chunk_id=str(hit.id),
        pmcid=p.get("pmcid", ""),
        text=p.get("text", ""),
        section_type=p.get("section_type", "other"),
        score_dense=hit.score if mode == "dense" else None,
        score_bm25=hit.score if mode == "bm25" else None,
        score_rrf=hit.score if mode == "hybrid" else None,
    )


def _build_filter(gene_filter: str | None) -> models.Filter | None:
    """Build a Qdrant payload filter restricting hits to chunks mentioning ``gene_filter``.

    Args:
        gene_filter: HGNC symbol to require in the chunk text. ``None`` to
            disable filtering. Uses substring match via ``MatchText``.

    Returns:
        Qdrant ``Filter`` object or ``None``.
    """
    if not gene_filter:
        return None
    return models.Filter(
        must=[models.FieldCondition(key="text", match=models.MatchText(text=gene_filter))]
    )


def hybrid_search(
    cfg: SearchConfig,
    query: str,
    *,
    top_k: int = 10,
    mode: RetrievalMode = "hybrid",
    gene_filter: str | None = None,
) -> list[RetrievedChunk]:
    """Run a Qdrant query in ``dense``, ``bm25``, or ``hybrid`` mode.

    Hybrid uses Reciprocal Rank Fusion over a dense and a sparse prefetch.
    BM25 query embeddings use ``query_embed`` (TF-only) — the IDF is
    applied server-side via the collection's ``Modifier.IDF`` setting
    (master plan §4 step 5 line 1111).

    Args:
        cfg: :class:`SearchConfig` (client, collection, dense and BM25 models).
        query: Free-text query to encode.
        top_k: Number of results to return.
        mode: ``"dense"``, ``"bm25"``, or ``"hybrid"`` (default).
        gene_filter: Optional HGNC symbol that must appear in the chunk text.

    Returns:
        List of :class:`RetrievedChunk` ordered by descending score.
    """
    qdrant_filter = _build_filter(gene_filter)

    if mode == "dense":
        return _dense_search(cfg, query, top_k, qdrant_filter)
    if mode == "bm25":
        return _bm25_search(cfg, query, top_k, qdrant_filter)
    return _hybrid_search(cfg, query, top_k, qdrant_filter)


def _dense_search(
    cfg: SearchConfig, query: str, top_k: int, qf: models.Filter | None
) -> list[RetrievedChunk]:
    """Dense-only search via PubMedBERT-encoded query."""
    vec = cfg.dense_model.encode(query, normalize_embeddings=True).tolist()
    res = cfg.client.query_points(
        collection_name=cfg.collection_name,
        query=vec,
        using="dense",
        with_payload=True,
        limit=top_k,
        query_filter=qf,
    )
    return [_hit_to_chunk(h, "dense") for h in res.points]


def _bm25_search(
    cfg: SearchConfig, query: str, top_k: int, qf: models.Filter | None
) -> list[RetrievedChunk]:
    """BM25 sparse search via ``query_embed`` (TF-only on the query side)."""
    sparse = next(iter(cfg.bm25_model.query_embed([query])))
    res = cfg.client.query_points(
        collection_name=cfg.collection_name,
        query=models.SparseVector(
            indices=sparse.indices.tolist(),
            values=sparse.values.tolist(),
        ),
        using="bm25",
        with_payload=True,
        limit=top_k,
        query_filter=qf,
    )
    return [_hit_to_chunk(h, "bm25") for h in res.points]


def _hybrid_search(
    cfg: SearchConfig, query: str, top_k: int, qf: models.Filter | None
) -> list[RetrievedChunk]:
    """Hybrid search via Qdrant's ``FusionQuery(Fusion.RRF)``."""
    dense_vec = cfg.dense_model.encode(query, normalize_embeddings=True).tolist()
    sparse = next(iter(cfg.bm25_model.query_embed([query])))
    res = cfg.client.query_points(
        collection_name=cfg.collection_name,
        prefetch=[
            models.Prefetch(query=dense_vec, using="dense", limit=top_k * 4),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse.indices.tolist(),
                    values=sparse.values.tolist(),
                ),
                using="bm25",
                limit=top_k * 4,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=top_k,
        query_filter=qf,
    )
    return [_hit_to_chunk(h, "hybrid") for h in res.points]
