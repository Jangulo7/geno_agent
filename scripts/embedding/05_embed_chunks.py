"""Generate dense (PubMedBERT) + sparse (BM25) embeddings for all chunks.

Master plan §4 step 4 / §7 step [5e] adapted for the FTP-bulk path.

Reads the single gzipped JSONL produced by ``04_chunk_normalized.py``
(~52.8 M chunks, ~28 GB), emits one parquet shard per
``--shard-size`` chunks (default 200 000). Each parquet row carries
the full chunk metadata + both embeddings::

    Dense:  PubMedBERT 768-d FP32 (mean-pooled, L2-normalized),
            stored as ``dense_embedding`` binary column.
    Sparse: fastembed Qdrant/bm25 indices + values, stored as
            ``bm25_indices`` (list[int32]) and ``bm25_values``
            (list[float32]). Both lists, same length per row.

CONTRIBUTING.md hard rule: BM25 must be ``fastembed.SparseTextEmbedding("Qdrant/bm25")``
— no hash-based fallback. Honoured.

Inputs::

    /home/hana77/chunks/all_chunks.jsonl.gz

Outputs::

    /home/hana77/embeddings/shard_0000.parquet
    /home/hana77/embeddings/shard_0001.parquet
    ...
    /home/hana77/embeddings/_embed_status.json
    /home/hana77/embeddings/_embed_stats.json   (final summary)

Resumability: shards are written ``shard_NNNN.parquet.partial`` then
atomically renamed; on restart, the first incomplete shard index is
detected and the input is fast-forwarded past the first
``done_shards * shard_size`` chunks.

Usage::

    python scripts/embedding/05_embed_chunks.py [--workers N]
        [--input PATH] [--output-dir PATH]
        [--shard-size N] [--dense-batch-size N]
        [--device cuda|cpu] [--status-interval SECONDS]
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Final

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from fastembed import SparseTextEmbedding
from sentence_transformers import SentenceTransformer

# Deterministic seeding — match every other pipeline entrypoint (08/09/10/11):
# fixes numpy/torch/cudnn to seed 42 so bulk embedding is reproducible on the
# pinned hardware. Called at import so it precedes any model load or encode.
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.utils.seed import apply_seeds  # noqa: E402

apply_seeds()

# ---------------------------------------------------------------- defaults
INPUT_PATH: Final[Path] = Path("/home/hana77/chunks/all_chunks.jsonl.gz")
OUTPUT_DIR: Final[Path] = Path("/home/hana77/embeddings")
DENSE_MODEL_PATH: Final[str] = os.environ.get(
    "EMBED_MODEL_NAME",
    "/home/hana77/rare-disease-rag/models/pubmedbert-base-embeddings",
)
SPARSE_MODEL_NAME: Final[str] = "Qdrant/bm25"  # CONTRIBUTING.md hard rule
EXPECTED_DIM: Final[int] = 768
SHARD_SIZE: Final[int] = 200_000
DENSE_BATCH_SIZE: Final[int] = 128
STATUS_INTERVAL_SEC: Final[int] = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("embedder")


# ---------------------------------------------------------------- status thread
class Stats:
    """Lock-protected counters shared between main + status thread."""

    def __init__(self) -> None:
        self.start_ts = time.monotonic()
        self.last_print_ts = self.start_ts
        self.last_print_chunks = 0
        self.shards_done = 0
        self.shards_total: int | None = None
        self.chunks_emitted = 0
        self.dense_time_sec = 0.0
        self.sparse_time_sec = 0.0
        self.write_time_sec = 0.0
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
            interval_chunks = stats.chunks_emitted - stats.last_print_chunks
            rate_overall = stats.chunks_emitted / elapsed if elapsed > 0 else 0.0
            rate_recent = interval_chunks / interval_elapsed
            stats.last_print_ts = now
            stats.last_print_chunks = stats.chunks_emitted

            shards_part = (
                f"{stats.shards_done}/{stats.shards_total}"
                if stats.shards_total
                else str(stats.shards_done)
            )
            line = (
                f"[STATUS {time.strftime('%H:%M:%SZ', time.gmtime(time.time()))}] "
                f"shards={shards_part} "
                f"chunks={stats.chunks_emitted:,} "
                f"rate_overall={rate_overall:.0f}/sec "
                f"rate_recent={rate_recent:.0f}/sec "
                f"dense={stats.dense_time_sec / 60:.1f}min "
                f"sparse={stats.sparse_time_sec / 60:.1f}min "
                f"write={stats.write_time_sec / 60:.1f}min "
                f"elapsed={elapsed / 60:.1f}min"
            )
            print(line, flush=True)

            with contextlib.suppress(OSError):
                status_path.write_text(
                    json.dumps(
                        {
                            "shards_done": stats.shards_done,
                            "shards_total": stats.shards_total,
                            "chunks_emitted": stats.chunks_emitted,
                            "rate_overall_per_sec": rate_overall,
                            "rate_recent_per_sec": rate_recent,
                            "dense_min": stats.dense_time_sec / 60,
                            "sparse_min": stats.sparse_time_sec / 60,
                            "write_min": stats.write_time_sec / 60,
                            "elapsed_min": elapsed / 60,
                        },
                        indent=2,
                    )
                )


# ---------------------------------------------------------------- shard writing
def shard_path(output_dir: Path, idx: int) -> Path:
    """Return the canonical shard parquet path for index ``idx``."""
    return output_dir / f"shard_{idx:04d}.parquet"


def find_resume_index(output_dir: Path) -> int:
    """Count contiguous shard_NNNN.parquet files starting at 0; return next index."""
    i = 0
    while shard_path(output_dir, i).exists() and shard_path(output_dir, i).stat().st_size > 0:
        i += 1
    return i


def write_shard(
    records: list[dict],
    dense_embs: np.ndarray,
    sparse_indices: list[list[int]],
    sparse_values: list[list[float]],
    out_path: Path,
) -> None:
    """Persist one shard parquet atomically.

    Dense embeddings are stored as ``binary`` (raw float32 bytes) — Qdrant's
    Python client can decode them directly and it keeps parquet rows compact.
    """
    columns = {
        "chunk_id": [r["chunk_id"] for r in records],
        "pmcid": [r.get("pmcid") for r in records],
        "pmid": [r.get("pmid") for r in records],
        "doi": [r.get("doi") for r in records],
        "title": [r.get("title", "") for r in records],
        "article_type": [r.get("article_type") for r in records],
        "pub_year": [r.get("pub_year") for r in records],
        "journal_title": [r.get("journal_title") for r in records],
        "issn": [r.get("issn") for r in records],
        "publisher": [r.get("publisher") for r in records],
        "license_url": [r.get("license_url") for r in records],
        "tier": [r.get("tier") for r in records],
        "mesh_terms": [r.get("mesh_terms") or [] for r in records],
        "authors": [r.get("authors") or [] for r in records],
        "section_type": [r["section_type"] for r in records],
        "section_heading": [r.get("section_heading") for r in records],
        "chunk_index": [r.get("chunk_index", 0) for r in records],
        "total_chunks_in_section": [r.get("total_chunks_in_section", 1) for r in records],
        "text": [r["text"] for r in records],
        "dense_embedding": [dense_embs[i].tobytes() for i in range(len(records))],
        "bm25_indices": sparse_indices,
        "bm25_values": sparse_values,
    }
    table = pa.Table.from_pydict(columns)
    partial = out_path.with_suffix(out_path.suffix + ".partial")
    pq.write_table(table, partial, compression="zstd")
    partial.replace(out_path)


# ---------------------------------------------------------------- main
def stream_chunks(input_path: Path, skip: int):
    """Yield parsed chunk dicts from the gzipped JSONL, skipping the first ``skip`` lines."""
    with gzip.open(input_path, mode="rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < skip:
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--shard-size",
        type=int,
        default=SHARD_SIZE,
        help="Chunks per parquet shard (default 200k).",
    )
    parser.add_argument(
        "--dense-batch-size",
        type=int,
        default=DENSE_BATCH_SIZE,
        help="GPU batch size for PubMedBERT (default 128). FP16 fits in <2 GB VRAM.",
    )
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Inference device for dense embeddings.",
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        default=True,
        help="Use FP16 inference on GPU (default: on for cuda).",
    )
    parser.add_argument(
        "--no-fp16",
        action="store_false",
        dest="fp16",
        help="Disable FP16 (FP32 dense, slower).",
    )
    parser.add_argument(
        "--status-interval",
        type=int,
        default=STATUS_INTERVAL_SEC,
        help="Status print interval in seconds (default 60).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N chunks (debug/smoke).",
    )
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input not found: %s", args.input)
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    status_path = args.output_dir / "_embed_status.json"
    stats_path = args.output_dir / "_embed_stats.json"

    log.info("Input:       %s", args.input)
    log.info("Output dir:  %s", args.output_dir)
    log.info("Shard size:  %d chunks", args.shard_size)
    log.info("Dense model: %s", DENSE_MODEL_PATH)
    log.info("Sparse:      %s (CONTRIBUTING.md hard rule — no fallback)", SPARSE_MODEL_NAME)
    log.info(
        "Device:      %s%s", args.device, " (FP16)" if args.fp16 and args.device == "cuda" else ""
    )

    # Resume
    resume_idx = find_resume_index(args.output_dir)
    skip_lines = resume_idx * args.shard_size
    if resume_idx > 0:
        log.info(
            "Resume: found %d complete shards on disk, skipping %d chunks", resume_idx, skip_lines
        )
    else:
        log.info("Resume: no existing shards, starting fresh")

    # Load models
    log.info("Loading dense model...")
    dense_model = SentenceTransformer(DENSE_MODEL_PATH, device=args.device)
    if args.fp16 and args.device == "cuda":
        dense_model = dense_model.half()
    dim = dense_model.get_sentence_embedding_dimension()
    log.info("  dim=%d", dim)
    if dim != EXPECTED_DIM:
        log.error("Dense dim %d != expected %d; aborting.", dim, EXPECTED_DIM)
        return 1

    log.info("Loading sparse model (downloads vocab files on first use)...")
    sparse_model = SparseTextEmbedding(SPARSE_MODEL_NAME)
    log.info("Sparse model ready.")

    # Stats + status thread
    stats = Stats()
    stats.shards_done = resume_idx
    stats.chunks_emitted = skip_lines
    reporter = threading.Thread(
        target=status_reporter,
        args=(stats, status_path, args.status_interval),
        daemon=True,
    )
    reporter.start()

    # Main loop
    buffer: list[dict] = []
    next_shard_idx = resume_idx
    chunks_processed_this_run = 0

    try:
        for record in stream_chunks(args.input, skip_lines):
            buffer.append(record)
            chunks_processed_this_run += 1
            if args.limit is not None and chunks_processed_this_run >= args.limit:
                break

            if len(buffer) >= args.shard_size:
                _flush_shard(
                    buffer,
                    next_shard_idx,
                    args.output_dir,
                    dense_model,
                    sparse_model,
                    args.dense_batch_size,
                    stats,
                )
                next_shard_idx += 1
                buffer = []

        if buffer:
            _flush_shard(
                buffer,
                next_shard_idx,
                args.output_dir,
                dense_model,
                sparse_model,
                args.dense_batch_size,
                stats,
            )
            next_shard_idx += 1
            buffer = []

    finally:
        with stats.lock:
            stats.done = True
        reporter.join(timeout=2)

    elapsed = time.monotonic() - stats.start_ts
    summary = {
        "elapsed_min": elapsed / 60,
        "shards_written_this_run": next_shard_idx - resume_idx,
        "shards_total_on_disk": next_shard_idx,
        "chunks_emitted_total": stats.chunks_emitted,
        "chunks_processed_this_run": chunks_processed_this_run,
        "dense_time_min": stats.dense_time_sec / 60,
        "sparse_time_min": stats.sparse_time_sec / 60,
        "write_time_min": stats.write_time_sec / 60,
        "output_dir": str(args.output_dir),
    }
    stats_path.write_text(json.dumps(summary, indent=2))

    print()
    print(f"=== DONE in {elapsed / 60:.1f} min ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


def _flush_shard(
    buffer: list[dict],
    shard_idx: int,
    output_dir: Path,
    dense_model: SentenceTransformer,
    sparse_model: SparseTextEmbedding,
    dense_batch_size: int,
    stats: Stats,
) -> None:
    """Compute dense + sparse embeddings for one shard and write parquet."""
    texts = [r["text"] for r in buffer]

    # Dense (GPU)
    t0 = time.monotonic()
    dense_embs = dense_model.encode(
        texts,
        batch_size=dense_batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype(np.float32, copy=False)
    dense_dt = time.monotonic() - t0

    # Sparse (CPU, BM25)
    t1 = time.monotonic()
    sparse_indices: list[list[int]] = []
    sparse_values: list[list[float]] = []
    for emb in sparse_model.embed(texts):
        sparse_indices.append(emb.indices.astype(np.int32).tolist())
        sparse_values.append(emb.values.astype(np.float32).tolist())
    sparse_dt = time.monotonic() - t1

    # Write
    t2 = time.monotonic()
    out_path = shard_path(output_dir, shard_idx)
    write_shard(buffer, dense_embs, sparse_indices, sparse_values, out_path)
    write_dt = time.monotonic() - t2

    with stats.lock:
        stats.shards_done += 1
        stats.chunks_emitted += len(buffer)
        stats.dense_time_sec += dense_dt
        stats.sparse_time_sec += sparse_dt
        stats.write_time_sec += write_dt


if __name__ == "__main__":
    sys.exit(main())
