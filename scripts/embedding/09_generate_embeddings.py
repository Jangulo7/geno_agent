"""Generate 768-dim PubMedBERT embeddings for chunked corpus.

Implements master plan §4 step 4. Reads the chunked JSONL produced by
``08_section_aware_chunking.py`` and writes parquet shards containing the
full chunk metadata plus a binary ``embedding`` column (np.float32 bytes,
mean-pooled and L2-normalized for cosine similarity).

Model: ``NeuML/pubmedbert-base-embeddings`` (768-dim) via
``sentence-transformers``. Inference runs on CUDA when available
(RTX 5090 / cu128 nightly per pytorch-env), falls back to CPU otherwise.

Run from project root::

    python scripts/embedding/09_generate_embeddings.py \\
        --input  /mnt/c/pmc_workspace/chunks/demo.jsonl \\
        --output /mnt/c/pmc_workspace/embeddings/demo.parquet
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Final

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("embedder")

MODEL_NAME: Final[str] = os.environ.get("EMBED_MODEL_NAME", "NeuML/pubmedbert-base-embeddings")
EMBEDDING_DIM: Final[int] = int(os.environ.get("EMBEDDING_DIM", "768"))
BATCH_SIZE: Final[int] = int(os.environ.get("EMBED_BATCH_SIZE", "32"))


def parse_args() -> argparse.Namespace:
    """CLI argument parsing."""
    workspace = os.environ.get("PMC_WORKSPACE", "/mnt/c/pmc_workspace")
    p = argparse.ArgumentParser(description="PubMedBERT embedding generator.")
    p.add_argument("--input", type=Path, default=Path(workspace) / "chunks" / "demo.jsonl")
    p.add_argument("--output", type=Path, default=Path(workspace) / "embeddings" / "demo.parquet")
    p.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Inference device (default: cuda if available).",
    )
    return p.parse_args()


def load_chunks(path: Path) -> list[dict]:
    """Read every JSON line from ``path`` and return as a list of dicts."""
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def embed_texts(model: SentenceTransformer, texts: list[str], batch_size: int) -> np.ndarray:
    """Run mean-pooled, L2-normalized embeddings for ``texts``.

    Returns:
        ``np.ndarray`` shape ``(len(texts), EMBEDDING_DIM)``, dtype float32.
    """
    arr = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return arr.astype(np.float32, copy=False)


def write_parquet(records: list[dict], embs: np.ndarray, out_path: Path) -> None:
    """Persist chunk metadata + binary embedding column as a parquet file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    columns = {
        "chunk_id": [r["chunk_id"] for r in records],
        "pmcid": [r["pmcid"] for r in records],
        "title": [r.get("title", "") for r in records],
        "section_type": [r["section_type"] for r in records],
        "section_heading": [r.get("section_heading", "") for r in records],
        "pub_year": [r.get("pub_year") for r in records],
        "mesh_terms": [json.dumps(r.get("mesh_terms", [])) for r in records],
        "chunk_index": [r["chunk_index"] for r in records],
        "text": [r["text"] for r in records],
        "embedding": [embs[i].tobytes() for i in range(len(records))],
    }
    table = pa.Table.from_pydict(columns)
    pq.write_table(table, out_path, compression="zstd")


def main() -> int:
    """Read chunks, embed with PubMedBERT, write parquet."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        return 1

    logger.info(f"Loading chunks from {args.input}")
    records = load_chunks(args.input)
    logger.info(f"  {len(records):,} chunks loaded")

    logger.info(f"Loading model: {MODEL_NAME} on {args.device}")
    model = SentenceTransformer(MODEL_NAME, device=args.device)
    logger.info(f"  embedding dim: {model.get_sentence_embedding_dimension()}")

    if model.get_sentence_embedding_dimension() != EMBEDDING_DIM:
        logger.error(
            f"Model dim {model.get_sentence_embedding_dimension()} "
            f"!= expected {EMBEDDING_DIM}; aborting."
        )
        return 1

    texts = [r["text"] for r in records]
    t0 = time.time()
    embs = embed_texts(model, texts, BATCH_SIZE)
    dt = time.time() - t0
    logger.info(
        f"Encoded {len(texts):,} chunks in {dt:.1f}s "
        f"({len(texts) / dt:.0f} chunks/s); shape {embs.shape}"
    )

    write_parquet(records, embs, args.output)
    size_mb = args.output.stat().st_size / 1024 / 1024
    logger.info("=== Embedding summary ===")
    logger.info(f"  records:    {len(records):,}")
    logger.info(f"  embedding:  {embs.shape}, dtype={embs.dtype}")
    logger.info(f"  output:     {args.output}  ({size_mb:.1f} MB, zstd)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
