"""Upload embedded parquet shards to Qdrant — FTP-bulk corpus path.

Master plan §4 step 5 + §7 step [5f] adapted for the 264-shard /
52.8 M-chunk corpus produced by ``scripts/embedding/05_embed_chunks.py``.

Behavior:

  * Idempotent collection setup. Calls
    ``scripts/indexing/10_create_qdrant_index.create_collection()``
    so the schema (dense 768-d cosine HNSW + BM25 sparse with IDF
    modifier, on_disk_payload=True, payload indices on section_type /
    pmcid / pub_year) stays canonical.

  * Reads our actual parquet schema. The 22-column shards from
    ``05_embed_chunks.py`` already carry pre-computed BM25 sparse
    vectors (``bm25_indices`` int32 list + ``bm25_values`` float32
    list per row). We use those directly — no second pass through
    fastembed at upload time, which would have wasted the 2.4 h of
    CPU the embedder spent computing them.

  * Rich payload. Each Qdrant point's payload carries every field
    the agent UI may want to display: pmcid, pmid, doi, title,
    journal_title, issn, publisher, license_url, tier, pub_year,
    article_type, mesh_terms, authors, section_type, section_heading,
    chunk_index, total_chunks_in_section, text.

  * Parallel upserts. ``client.upload_points(parallel=N)`` uses an
    internal thread pool and a bounded queue, so the main process
    streams shards while Qdrant does the heavy lifting.

  * Resumable. ``_upload_progress.json`` records the highest shard
    index fully uploaded. On restart, the script skips past it.
    Qdrant upserts are idempotent on point ID anyway (our chunk_id
    is a deterministic UUID5), so a re-upload is correct even if
    the progress file is lost.

  * Status reporting. Background thread prints
    ``[STATUS HH:MM:SSZ] shards=A/B points=N rate=R/sec elapsed=Tmin``
    every ``--status-interval`` seconds (default 60).

Usage::

    python scripts/indexing/06_upload_to_qdrant.py [--create]
        [--embedding-dir PATH] [--parallel N]
        [--batch-size N] [--status-interval SECONDS]
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Final

import numpy as np
import pyarrow.parquet as pq
from qdrant_client import QdrantClient, models

# ---------------------------------------------------------------- defaults
INPUT_DIR: Final[Path] = Path("/home/hana77/embeddings")
QDRANT_HOST: Final[str] = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: Final[int] = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION_NAME: Final[str] = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
BATCH_SIZE: Final[int] = int(os.environ.get("UPLOAD_BATCH_SIZE", "256"))
PARALLEL_WORKERS: Final[int] = 4
STATUS_INTERVAL_SEC: Final[int] = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("qdrant_upload")


# ---------------------------------------------------------------- reuse 10_'s collection setup
def _load_create_collection_module():
    """Import the existing script (file starts with a digit so dotted imports fail)."""
    path = Path(__file__).parent / "10_create_qdrant_index.py"
    spec = importlib.util.spec_from_file_location("_create_qdrant_index", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- status thread
class Stats:
    """Lock-protected counters shared between main + status thread."""

    def __init__(self) -> None:
        self.start_ts = time.monotonic()
        self.last_print_ts = self.start_ts
        self.last_print_points = 0
        self.shards_done = 0
        self.shards_total = 0
        self.points_uploaded = 0
        self.done = False
        self.lock = threading.Lock()


def status_reporter(stats: Stats, status_path: Path, interval: int) -> None:
    """Print one status line every ``interval`` seconds."""
    while True:
        time.sleep(interval)
        with stats.lock:
            if stats.done:
                break
            now = time.monotonic()
            elapsed = now - stats.start_ts
            interval_elapsed = max(now - stats.last_print_ts, 1e-6)
            interval_points = stats.points_uploaded - stats.last_print_points
            rate_overall = stats.points_uploaded / elapsed if elapsed > 0 else 0.0
            rate_recent = interval_points / interval_elapsed
            stats.last_print_ts = now
            stats.last_print_points = stats.points_uploaded

            line = (
                f"[STATUS {time.strftime('%H:%M:%SZ', time.gmtime(time.time()))}] "
                f"shards={stats.shards_done}/{stats.shards_total} "
                f"points={stats.points_uploaded:,} "
                f"rate_overall={rate_overall:.0f}/sec "
                f"rate_recent={rate_recent:.0f}/sec "
                f"elapsed={elapsed / 60:.1f}min"
            )
            print(line, flush=True)

            with contextlib.suppress(OSError):
                status_path.write_text(
                    json.dumps(
                        {
                            "shards_done": stats.shards_done,
                            "shards_total": stats.shards_total,
                            "points_uploaded": stats.points_uploaded,
                            "rate_overall_per_sec": rate_overall,
                            "rate_recent_per_sec": rate_recent,
                            "elapsed_min": elapsed / 60,
                        },
                        indent=2,
                    )
                )


# ---------------------------------------------------------------- progress checkpoint
def load_progress(path: Path) -> int:
    """Return last fully-uploaded shard index, or -1 if no checkpoint."""
    try:
        return int(json.loads(path.read_text())["last_shard_done"])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return -1


def save_progress(path: Path, last_shard_done: int) -> None:
    """Persist the highest shard index that has been fully upserted."""
    with contextlib.suppress(OSError):
        path.write_text(json.dumps({"last_shard_done": last_shard_done}))


# ---------------------------------------------------------------- shard upload
def _row_to_point(row: dict) -> models.PointStruct:
    """Convert one parquet row (as pydict slice) to a Qdrant PointStruct."""
    dense_vec = np.frombuffer(row["dense_embedding"], dtype=np.float32).tolist()
    return models.PointStruct(
        id=row["chunk_id"],
        vector={
            "dense": dense_vec,
            "bm25": models.SparseVector(
                indices=row["bm25_indices"],
                values=row["bm25_values"],
            ),
        },
        payload={
            "chunk_id": row["chunk_id"],
            "pmcid": row.get("pmcid"),
            "pmid": row.get("pmid"),
            "doi": row.get("doi"),
            "title": row.get("title", ""),
            "article_type": row.get("article_type"),
            "pub_year": row.get("pub_year"),
            "journal_title": row.get("journal_title"),
            "issn": row.get("issn"),
            "publisher": row.get("publisher"),
            "license_url": row.get("license_url"),
            "tier": row.get("tier"),
            "mesh_terms": row.get("mesh_terms") or [],
            "authors": row.get("authors") or [],
            "section_type": row.get("section_type"),
            "section_heading": row.get("section_heading"),
            "chunk_index": row.get("chunk_index", 0),
            "total_chunks_in_section": row.get("total_chunks_in_section", 1),
            "text": row.get("text", ""),
        },
    )


def upload_shard(
    client: QdrantClient,
    parquet_path: Path,
    batch_size: int,
    parallel: int,
) -> int:
    """Stream one parquet shard to Qdrant. Returns the number of points uploaded."""
    table = pq.read_table(parquet_path)
    n_rows = table.num_rows

    def _gen_points():
        for start in range(0, n_rows, batch_size):
            end = min(start + batch_size, n_rows)
            sub = table.slice(start, end - start).to_pylist()
            for row in sub:
                yield _row_to_point(row)

    client.upload_points(
        collection_name=COLLECTION_NAME,
        points=_gen_points(),
        batch_size=batch_size,
        parallel=parallel,
        wait=True,
    )
    return n_rows


# ---------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--embedding-dir", type=Path, default=INPUT_DIR)
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create the collection if it doesn't exist (idempotent — no-op if it does).",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="DROP and recreate the collection before uploading. Destructive.",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--parallel",
        type=int,
        default=PARALLEL_WORKERS,
        help="Qdrant client upload thread pool size (default 4).",
    )
    parser.add_argument("--status-interval", type=int, default=STATUS_INTERVAL_SEC)
    parser.add_argument(
        "--limit-shards",
        type=int,
        default=None,
        help="Process at most N shards (debug/smoke).",
    )
    args = parser.parse_args()

    if not args.embedding_dir.is_dir():
        log.error("Embedding dir not found: %s", args.embedding_dir)
        return 1

    parquet_files = sorted(args.embedding_dir.glob("shard_*.parquet"))
    if not parquet_files:
        log.error("No shard_*.parquet under %s", args.embedding_dir)
        return 1

    progress_path = args.embedding_dir / "_upload_progress.json"
    status_path = args.embedding_dir / "_upload_status.json"
    last_done = load_progress(progress_path)

    log.info("Qdrant:       %s:%d / %s", QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME)
    log.info("Shards found: %d", len(parquet_files))
    log.info("Batch size:   %d", args.batch_size)
    log.info("Parallel:     %d", args.parallel)
    log.info("Resume from:  shard_%04d (last done = %d)", last_done + 1, last_done)

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=600)

    if args.create or args.recreate:
        create_mod = _load_create_collection_module()
        create_mod.create_collection(client, recreate=args.recreate)
    elif not any(c.name == COLLECTION_NAME for c in client.get_collections().collections):
        log.error("Collection '%s' does not exist. Re-run with --create.", COLLECTION_NAME)
        return 1

    stats = Stats()
    stats.shards_total = len(parquet_files)
    stats.shards_done = last_done + 1  # already-done shards count as done
    reporter = threading.Thread(
        target=status_reporter,
        args=(stats, status_path, args.status_interval),
        daemon=True,
    )
    reporter.start()

    processed_this_run = 0
    try:
        for idx, parquet_path in enumerate(parquet_files):
            if idx <= last_done:
                continue
            if args.limit_shards is not None and processed_this_run >= args.limit_shards:
                break

            t0 = time.monotonic()
            n = upload_shard(client, parquet_path, args.batch_size, args.parallel)
            dt = time.monotonic() - t0
            with stats.lock:
                stats.shards_done = idx + 1
                stats.points_uploaded += n
            save_progress(progress_path, idx)
            log.info(
                "  %s: %d points in %.1fs (%.0f pts/sec)",
                parquet_path.name,
                n,
                dt,
                n / max(dt, 1e-6),
            )
            processed_this_run += 1
    finally:
        with stats.lock:
            stats.done = True
        reporter.join(timeout=2)

    # Final verification
    create_mod = _load_create_collection_module()
    create_mod.verify_collection(client)

    elapsed = time.monotonic() - stats.start_ts
    print()
    print(f"=== DONE in {elapsed / 60:.1f} min ===")
    print(f"  shards processed this run: {processed_this_run}")
    print(f"  shards total on disk:      {stats.shards_done}/{stats.shards_total}")
    print(f"  points uploaded this run:  {stats.points_uploaded:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
