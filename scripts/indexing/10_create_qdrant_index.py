"""Create the Qdrant collection schema for the PMC OA corpus.

Implements master plan §4 step 5. By default this script creates the empty
collection and exits — that is what §7 step [4] requires. The same script
is rerun with ``--upload`` after embeddings are produced (§7 step [5f]) to
push parquet shards into Qdrant; that path is stubbed but not implemented
in this PR.

Schema (per master plan §4 step 5 v2.1):
  * Dense vector ``"dense"``: 768-dim PubMedBERT, COSINE distance, on-disk,
    HNSW with m=16 / ef_construct=200 / full_scan_threshold=10000.
  * Sparse vector ``"bm25"``: native Qdrant BM25 with IDF modifier.
  * ``on_disk_payload=True`` (master plan v2.1 fix; the 2-5 M chunk corpus
    would otherwise OOM the host on payload alone).
  * Payload indices on ``section_type``, ``pmcid``, ``pub_year``.

Run from the project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/indexing/10_create_qdrant_index.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("create_qdrant_index")

QDRANT_HOST: Final[str] = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: Final[int] = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION_NAME: Final[str] = os.environ.get(
    "QDRANT_COLLECTION", "geno_agent_pmc_oa_v1"
)
EMBEDDING_DIM: Final[int] = int(os.environ.get("EMBEDDING_DIM", "768"))


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument(
        "--recreate",
        action="store_true",
        help="Drop the collection if it exists, then recreate from scratch.",
    )
    p.add_argument(
        "--upload",
        action="store_true",
        help="(Future) Upload parquet shards from $EMBEDDING_DIR after creation.",
    )
    return p.parse_args()


def connect() -> QdrantClient:
    """Open a Qdrant client to the configured host:port."""
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)
    logger.info(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
    return client


def collection_exists(client: QdrantClient, name: str) -> bool:
    """Return whether a collection with ``name`` is registered on the server."""
    return any(c.name == name for c in client.get_collections().collections)


def create_collection(client: QdrantClient, recreate: bool = False) -> None:
    """Create the project collection if it does not already exist.

    Args:
        client: Connected Qdrant client.
        recreate: If True and the collection exists, delete it first.
            Use with caution — drops all stored points and indices.

    Raises:
        qdrant_client.http.exceptions.UnexpectedResponse: On any server
            error during creation or index registration.
    """
    if collection_exists(client, COLLECTION_NAME):
        if recreate:
            logger.warning(f"Dropping existing collection '{COLLECTION_NAME}'")
            client.delete_collection(COLLECTION_NAME)
        else:
            logger.info(
                f"Collection '{COLLECTION_NAME}' already exists; skipping create. "
                f"Pass --recreate to drop and rebuild."
            )
            return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE,
                on_disk=True,
                hnsw_config=models.HnswConfigDiff(
                    m=16, ef_construct=200, full_scan_threshold=10000,
                ),
            ),
        },
        sparse_vectors_config={
            "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF),
        },
        on_disk_payload=True,
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000),
    )
    _create_payload_indices(client)
    logger.info(
        f"Created collection '{COLLECTION_NAME}' "
        f"(dense {EMBEDDING_DIM}d HNSW + BM25 sparse, on_disk_payload=True)"
    )


def _create_payload_indices(client: QdrantClient) -> None:
    """Register the three payload field indices used for retrieval filtering."""
    field_specs: tuple[tuple[str, models.PayloadSchemaType], ...] = (
        ("section_type", models.PayloadSchemaType.KEYWORD),
        ("pmcid", models.PayloadSchemaType.KEYWORD),
        ("pub_year", models.PayloadSchemaType.INTEGER),
    )
    for field_name, field_schema in field_specs:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field_name,
            field_schema=field_schema,
        )
        logger.info(f"  payload index: {field_name} ({field_schema.name})")


def verify_collection(client: QdrantClient) -> None:
    """Read back the collection config and log a summary of what was created.

    Raises:
        AssertionError: If the dense vector dim or BM25 sparse modifier do
            not match the master plan §4 step 5 spec.
    """
    info = client.get_collection(COLLECTION_NAME)
    cfg = info.config.params
    dense = cfg.vectors["dense"]
    bm25 = cfg.sparse_vectors["bm25"]

    assert dense.size == EMBEDDING_DIM, (
        f"dense vector size {dense.size} != {EMBEDDING_DIM}"
    )
    assert dense.distance == models.Distance.COSINE, (
        f"dense distance {dense.distance} != COSINE"
    )
    assert bm25.modifier == models.Modifier.IDF, (
        f"BM25 modifier {bm25.modifier} != IDF"
    )

    points = client.count(collection_name=COLLECTION_NAME, exact=True).count
    logger.info("=== Collection summary ===")
    logger.info(f"  name:         {COLLECTION_NAME}")
    logger.info(f"  status:       {info.status}")
    logger.info(f"  dense:        size={dense.size}, distance={dense.distance.name}, "
                f"on_disk={dense.on_disk}")
    logger.info(f"  sparse(bm25): modifier={bm25.modifier.name}")
    logger.info(f"  on_disk_payload: {cfg.on_disk_payload}")
    logger.info(f"  points:       {points}")


def main() -> int:
    """Entry point — create or verify the collection, optionally upload."""
    args = parse_args()
    client = connect()
    create_collection(client, recreate=args.recreate)
    verify_collection(client)
    if args.upload:
        logger.error(
            "--upload is reserved for §7 step [5f] and is not yet implemented; "
            "exiting after collection verification."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
