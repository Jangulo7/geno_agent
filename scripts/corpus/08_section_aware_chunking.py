"""Section-aware semantic chunking with deterministic UUID5 chunk IDs.

Implements master plan §4 step 3 (v2.1). Reads the filtered JSONL produced
by ``07_filter_corpus.py`` and emits one JSON line per chunk. Chunks never
span section boundaries, are token-bounded by the PubMedBERT tokenizer,
and carry a deterministic chunk_id derived as::

    chunk_id = uuid.uuid5(
        CHUNK_NAMESPACE,
        f"{pmcid}|{section_type}|{chunk_index}|blake2b(chunk_text)"
    )

The fixed namespace UUID is pinned in the master plan and MUST NOT change —
mutating it invalidates every existing Qdrant point ID.

Run from project root::

    python scripts/corpus/08_section_aware_chunking.py \\
        --input  /mnt/c/pmc_workspace/filtered/demo.jsonl \\
        --output /mnt/c/pmc_workspace/chunks/demo.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from tqdm import tqdm
from transformers import AutoTokenizer, PreTrainedTokenizerBase

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("chunker")

TOKENIZER_NAME: Final[str] = os.environ.get(
    "EMBED_MODEL_NAME", "NeuML/pubmedbert-base-embeddings"
)
MAX_TOKENS: Final[int] = int(os.environ.get("CHUNK_MAX_TOKENS", "512"))
OVERLAP_TOKENS: Final[int] = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "50"))
MIN_SECTION_CHARS: Final[int] = 50

# DO NOT CHANGE — pinned in master plan §4 step 3 line 897.
CHUNK_NAMESPACE: Final[uuid.UUID] = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")


def deterministic_chunk_id(
    pmcid: str, section_type: str, chunk_index: int, chunk_text: str
) -> str:
    """Generate a deterministic UUID5 for a chunk.

    Args:
        pmcid: PMC accession (e.g. ``PMC10258773``).
        section_type: Standardized section label.
        chunk_index: Zero-based chunk index within the section.
        chunk_text: Detokenized chunk text.

    Returns:
        UUID5 string. Identical inputs always produce the identical UUID
        across processes, machines, and Python versions — required for
        Qdrant idempotent upserts and replay-stable manifest hashing.
    """
    text_digest = hashlib.blake2b(
        chunk_text.encode("utf-8"), digest_size=16
    ).hexdigest()
    key = f"{pmcid}|{section_type}|{chunk_index}|{text_digest}"
    return str(uuid.uuid5(CHUNK_NAMESPACE, key))


def chunk_section_text(
    text: str, tokenizer: PreTrainedTokenizerBase,
    max_tokens: int = MAX_TOKENS, overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Split ``text`` into overlapping token-bounded chunks.

    Args:
        text: Section body text.
        tokenizer: HuggingFace tokenizer instance.
        max_tokens: Maximum tokens per chunk (excluding special tokens).
        overlap_tokens: Number of overlapping tokens between consecutive chunks.

    Returns:
        List of detokenized chunk strings. Returns ``[text]`` if the section
        fits in one chunk.
    """
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= max_tokens:
        return [text]

    chunks: list[str] = []
    stride = max_tokens - overlap_tokens
    for start in range(0, len(token_ids), stride):
        end = min(start + max_tokens, len(token_ids))
        chunk_text = tokenizer.decode(
            token_ids[start:end], skip_special_tokens=True
        ).strip()
        if chunk_text:
            chunks.append(chunk_text)
        if end >= len(token_ids):
            break
    return chunks


def process_article(
    article: dict, tokenizer: PreTrainedTokenizerBase
) -> list[dict]:
    """Chunk every section of one article and return chunk records."""
    out: list[dict] = []
    pmcid = article["pmcid"]
    for section in article.get("sections", []):
        section_type = section.get("section_type", "other")
        heading = section.get("heading", "")
        text = section.get("text", "")
        if not text or len(text.strip()) < MIN_SECTION_CHARS:
            continue
        text_chunks = chunk_section_text(text, tokenizer)
        for i, chunk_text in enumerate(text_chunks):
            out.append({
                "chunk_id": deterministic_chunk_id(pmcid, section_type, i, chunk_text),
                "pmcid": pmcid,
                "title": article.get("title", ""),
                "section_type": section_type,
                "section_heading": heading,
                "pub_year": article.get("pub_year"),
                "mesh_terms": article.get("mesh_terms", []),
                "chunk_index": i,
                "total_chunks_in_section": len(text_chunks),
                "text": chunk_text,
            })
    return out


def parse_args() -> argparse.Namespace:
    """CLI argument parsing."""
    workspace = os.environ.get("PMC_WORKSPACE", "/mnt/c/pmc_workspace")
    p = argparse.ArgumentParser(description="Section-aware deterministic chunker.")
    p.add_argument("--input", type=Path,
                   default=Path(workspace) / "filtered" / "demo.jsonl")
    p.add_argument("--output", type=Path,
                   default=Path(workspace) / "chunks" / "demo.jsonl")
    return p.parse_args()


def main() -> int:
    """Read input JSONL, chunk, write output JSONL."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading tokenizer: {TOKENIZER_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    logger.info(
        f"Tokenizer loaded; vocab={tokenizer.vocab_size}, "
        f"max_tokens={MAX_TOKENS}, overlap={OVERLAP_TOKENS}"
    )

    n_articles = sum(1 for _ in args.input.open("r", encoding="utf-8"))
    n_chunks = n_skipped_secs = 0
    section_type_counts: dict[str, int] = {}

    with args.input.open("r", encoding="utf-8") as fin, \
         args.output.open("w", encoding="utf-8") as fout:
        for line in tqdm(fin, total=n_articles, desc="chunking"):
            article = json.loads(line)
            chunks = process_article(article, tokenizer)
            n_skipped_secs += sum(
                1 for s in article.get("sections", [])
                if not s.get("text") or len(s["text"].strip()) < MIN_SECTION_CHARS
            )
            for c in chunks:
                fout.write(json.dumps(c, ensure_ascii=False) + "\n")
                section_type_counts[c["section_type"]] = (
                    section_type_counts.get(c["section_type"], 0) + 1
                )
            n_chunks += len(chunks)

    logger.info("=== Chunking summary ===")
    logger.info(f"  articles in:        {n_articles}")
    logger.info(f"  chunks out:         {n_chunks}")
    logger.info(f"  avg chunks/article: {n_chunks / max(n_articles, 1):.1f}")
    logger.info(f"  short sections skipped: {n_skipped_secs}")
    logger.info(f"  by section_type:    {dict(sorted(section_type_counts.items()))}")
    logger.info(f"  output:             {args.output}")
    return 0 if n_chunks else 1


if __name__ == "__main__":
    raise SystemExit(main())
