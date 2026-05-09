"""Validate the populated Qdrant index with probe gene-phenotype queries.

Implements master plan §4 step 6 / §7 step [6]. Runs a small set of probe
queries against the populated ``geno_agent_pmc_oa_v1`` collection in three
retrieval modes — dense-only, BM25-only, and hybrid (RRF fusion) — and
prints the top-K hits for each. The script is the smoke test that
unblocks Phase 1B; it does not score retrieval quality formally.

Critical v2.1 detail (master plan §4 step 5 line 1111): BM25 query
embeddings MUST use ``SparseTextEmbedding.query_embed()`` (TF only),
not ``.embed()`` (TF + IDF). Indexing and querying are asymmetric —
the IDF half lives on the document side and is multiplied in by the
server's ``Modifier.IDF`` setting.

Run from project root::

    python scripts/indexing/11_validate_index.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_index")

QDRANT_HOST: Final[str] = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: Final[int] = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION: Final[str] = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL: Final[str] = os.environ.get("EMBED_MODEL_NAME", "NeuML/pubmedbert-base-embeddings")
BM25_MODEL: Final[str] = "Qdrant/bm25"
TOP_K: Final[int] = 5

PROBES: Final[tuple[str, ...]] = (
    # Neurological
    "Huntington disease CAG repeat expansion",
    "Rett syndrome MECP2 X-linked",
    "Charcot-Marie-Tooth peripheral neuropathy PMP22",
    # Metabolic
    "phenylketonuria PAH enzyme deficiency",
    "Fabry disease alpha-galactosidase A GLA",
    "Niemann-Pick lysosomal storage NPC1",
    # Immunological
    "common variable immunodeficiency B cell",
    "severe combined immunodeficiency SCID T cell",
    "agammaglobulinemia BTK X-linked",
    # Developmental / connective-tissue
    "Marfan syndrome FBN1 fibrillin aortic",
    "Noonan syndrome RAS-MAPK PTPN11",
    "DiGeorge syndrome 22q11 deletion thymus",
)


def parse_args() -> argparse.Namespace:
    """CLI argument parsing."""
    p = argparse.ArgumentParser(description="Probe Qdrant index with hybrid queries.")
    p.add_argument("--collection", default=COLLECTION)
    p.add_argument("--top-k", type=int, default=TOP_K)
    return p.parse_args()


def _format_hit(hit: models.ScoredPoint, max_chars: int = 140) -> str:
    """Render one Qdrant hit as a one-line summary."""
    p = hit.payload or {}
    snippet = (p.get("text", "") or "").replace("\n", " ")[:max_chars]
    return (
        f"  [{hit.score:.3f}] {p.get('pmcid', '?'):14s} "
        f"{p.get('section_type', '?'):12s} | {snippet}…"
    )


def probe_dense(
    client: QdrantClient, model: SentenceTransformer, collection: str, query: str, k: int
) -> list[models.ScoredPoint]:
    """Run a dense-vector query."""
    vec = model.encode(query, normalize_embeddings=True).tolist()
    return client.query_points(
        collection_name=collection,
        query=vec,
        using="dense",
        with_payload=True,
        limit=k,
    ).points


def probe_bm25(
    client: QdrantClient, bm25: SparseTextEmbedding, collection: str, query: str, k: int
) -> list[models.ScoredPoint]:
    """Run a BM25 sparse query — uses .query_embed (TF only)."""
    sparse = next(iter(bm25.query_embed([query])))
    return client.query_points(
        collection_name=collection,
        query=models.SparseVector(
            indices=sparse.indices.tolist(),
            values=sparse.values.tolist(),
        ),
        using="bm25",
        with_payload=True,
        limit=k,
    ).points


def probe_hybrid(
    client: QdrantClient,
    model: SentenceTransformer,
    bm25: SparseTextEmbedding,
    collection: str,
    query: str,
    k: int,
) -> list[models.ScoredPoint]:
    """Run hybrid retrieval with reciprocal rank fusion."""
    dense_vec = model.encode(query, normalize_embeddings=True).tolist()
    sparse = next(iter(bm25.query_embed([query])))
    res = client.query_points(
        collection_name=collection,
        prefetch=[
            models.Prefetch(query=dense_vec, using="dense", limit=k * 4),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse.indices.tolist(),
                    values=sparse.values.tolist(),
                ),
                using="bm25",
                limit=k * 4,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=k,
    )
    return res.points


def main() -> int:
    """Run probes in dense / BM25 / hybrid modes and print top-K each."""
    args = parse_args()
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)
    info = client.get_collection(args.collection)
    points = client.count(collection_name=args.collection, exact=True).count
    logger.info(f"Collection '{args.collection}' status={info.status}, points={points:,}")
    if points == 0:
        logger.error("Collection is empty; run --upload first.")
        return 1

    logger.info(f"Loading dense model: {DENSE_MODEL}")
    dense = SentenceTransformer(DENSE_MODEL)
    logger.info(f"Loading sparse model: {BM25_MODEL}")
    bm25 = SparseTextEmbedding(model_name=BM25_MODEL)

    for query in PROBES:
        logger.info(f"\n==== Probe: {query!r} ====")
        # Default-arg trick (q=query) prevents lambda late-binding to the loop var.
        for label, fn in (
            ("dense ", lambda q=query: probe_dense(client, dense, args.collection, q, args.top_k)),
            ("bm25  ", lambda q=query: probe_bm25(client, bm25, args.collection, q, args.top_k)),
            (
                "hybrid",
                lambda q=query: probe_hybrid(client, dense, bm25, args.collection, q, args.top_k),
            ),
        ):
            hits = fn()
            logger.info(f"-- {label} (top {args.top_k}) --")
            for h in hits:
                logger.info(_format_hit(h))

    logger.info("=== Validation complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
