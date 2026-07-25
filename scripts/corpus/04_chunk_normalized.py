"""Bulk parallel chunker for the normalized FTP-bulk output.

Master plan §4 step 3 / §7 step [5d] applied to the FTP-bulk path.

Reads the single gzipped JSONL produced by ``03_normalize_dedupe_filter.py``
and emits one JSON line per chunk to a gzipped output. Same deterministic
UUID5 chunk IDs and tokenization rules as ``08_section_aware_chunking.py``,
but adds:

  * gzip-native I/O (input + output both ``.jsonl.gz``)
  * ``multiprocessing.Pool`` so the CPU-bound PubMedBERT tokenization
    saturates all cores
  * background status thread every ``--status-interval`` seconds (default 60)
  * atomic ``.partial -> rename`` write so a crash mid-stream never
    leaves a half-written ``.jsonl.gz`` the next run mistakes as done

The chunk record carries the ``08`` fields plus every metadata field
useful for downstream Qdrant payload (DOI, authors, journal, license,
tier) — this avoids a join against the source JSONL at upload time.

Usage::

    python scripts/corpus/04_chunk_normalized.py [--workers N]
        [--input PATH] [--output PATH] [--status-interval SECONDS]
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import logging
import multiprocessing as mp
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Final

from transformers import AutoTokenizer, PreTrainedTokenizerBase

# ---------------------------------------------------------------- defaults
INPUT_PATH: Final[Path] = Path("/mnt/c/pmc_workspace/parsed/all_articles.normalized.jsonl.gz")
# Output on Linux ext4 (not /mnt/c via 9P) — writer ~10x faster, keeps result
# queue from accumulating and tripping OOM (62 GB main process killed in run #1).
OUTPUT_PATH: Final[Path] = Path("/home/hana77/chunks/all_chunks.jsonl.gz")
# Public, revision-pinned tokenizer. The production build loaded these weights
# from a bare local path, which carries no revision and cannot be reproduced by
# anyone else; that copy is byte-identical to the Hugging Face snapshot below, so
# pinning the public revision is what makes the chunk set regenerable off this
# machine. EMBED_MODEL_NAME still overrides for an offline/local copy.
TOKENIZER_NAME: Final[str] = os.environ.get("EMBED_MODEL_NAME", "NeuML/pubmedbert-base-embeddings")
TOKENIZER_REVISION: Final[str] = os.environ.get(
    "EMBED_MODEL_REVISION", "b79526d6ef3645e0df4530322e266f24c829f5ef"
)
MAX_TOKENS: Final[int] = int(os.environ.get("CHUNK_MAX_TOKENS", "512"))
OVERLAP_TOKENS: Final[int] = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "50"))
MIN_SECTION_CHARS: Final[int] = 50
STATUS_INTERVAL_SEC: Final[int] = 60

# DO NOT CHANGE — pinned in master plan §4 step 3.
CHUNK_NAMESPACE: Final[uuid.UUID] = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("chunker")


# ---------------------------------------------------------------- chunk ID
def deterministic_chunk_id(pmcid: str, section_type: str, chunk_index: int, chunk_text: str) -> str:
    """UUID5 chunk ID; identical inputs always yield the same ID."""
    digest = hashlib.blake2b(chunk_text.encode("utf-8"), digest_size=16).hexdigest()
    key = f"{pmcid}|{section_type}|{chunk_index}|{digest}"
    return str(uuid.uuid5(CHUNK_NAMESPACE, key))


def chunk_section_text(
    text: str,
    tokenizer: PreTrainedTokenizerBase,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Token-bounded sliding-window chunking via the PubMedBERT tokenizer."""
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= max_tokens:
        return [text]

    chunks: list[str] = []
    stride = max_tokens - overlap_tokens
    for start in range(0, len(token_ids), stride):
        end = min(start + max_tokens, len(token_ids))
        decoded = tokenizer.decode(token_ids[start:end], skip_special_tokens=True).strip()
        if decoded:
            chunks.append(decoded)
        if end >= len(token_ids):
            break
    return chunks


# ---------------------------------------------------------------- worker
# Tokenizer is loaded once per worker process via initializer (avoids the
# ~3 s cold-load penalty on every article and keeps the worker stateless
# enough that the Pool can recycle freely).
_TOKENIZER: PreTrainedTokenizerBase | None = None


def _worker_init(tokenizer_name: str, revision: str | None = None) -> None:
    global _TOKENIZER
    # A local path carries no revision, so only pass one for a hub identifier.
    kwargs = {} if Path(tokenizer_name).exists() else {"revision": revision}
    _TOKENIZER = AutoTokenizer.from_pretrained(tokenizer_name, **kwargs)


def _process_article(article_json: str) -> tuple[list[dict], int]:
    """Chunk one article; returns (chunks, n_short_sections_skipped)."""
    assert _TOKENIZER is not None, "tokenizer not initialized in worker"
    try:
        article = json.loads(article_json)
    except json.JSONDecodeError:
        return [], 0

    pmcid = article.get("pmcid")
    if not pmcid:
        return [], 0

    out: list[dict] = []
    skipped = 0

    # Extract reusable per-article metadata once
    journal = article.get("journal") or {}
    license_info = article.get("license") or {}
    base_meta = {
        "pmcid": pmcid,
        "pmid": article.get("pmid"),
        "doi": article.get("doi"),
        "title": article.get("title", ""),
        "article_type": article.get("article_type"),
        "pub_year": article.get("pub_year"),
        "journal_title": journal.get("title"),
        "issn": (journal.get("issn") or {}).get("epub") or (journal.get("issn") or {}).get("ppub"),
        "publisher": journal.get("publisher"),
        "license_url": license_info.get("url"),
        "tier": article.get("tier"),
        "mesh_terms": article.get("mesh_terms") or [],
        "authors": [
            f"{a.get('surname', '')}, {a.get('given_names', '')}".strip(", ")
            for a in (article.get("authors") or [])
        ],
    }

    for section in article.get("sections") or []:
        section_type = section.get("section_type", "other")
        heading = section.get("heading") or ""
        text = section.get("text", "") or ""
        if len(text.strip()) < MIN_SECTION_CHARS:
            skipped += 1
            continue
        text_chunks = chunk_section_text(text, _TOKENIZER)
        n = len(text_chunks)
        for i, chunk_text in enumerate(text_chunks):
            record = {
                **base_meta,
                "chunk_id": deterministic_chunk_id(pmcid, section_type, i, chunk_text),
                "section_type": section_type,
                "section_heading": heading,
                "chunk_index": i,
                "total_chunks_in_section": n,
                "text": chunk_text,
            }
            out.append(record)
    return out, skipped


# ---------------------------------------------------------------- status thread
class Stats:
    """Lock-protected counters shared between main + status thread."""

    def __init__(self) -> None:
        self.start_ts = time.time()
        self.last_print_ts = self.start_ts
        self.last_print_chunks = 0
        self.articles_in = 0
        self.chunks_out = 0
        self.short_sections_skipped = 0
        self.section_type_counts: dict[str, int] = {}
        self.done = False
        self.lock = threading.Lock()


def status_reporter(stats: Stats, status_path: Path, interval: int) -> None:
    """Print one status line every `interval` seconds."""
    while True:
        time.sleep(interval)
        with stats.lock:
            if stats.done:
                break
            now = time.time()
            elapsed = now - stats.start_ts
            interval_elapsed = max(now - stats.last_print_ts, 1e-6)
            interval_chunks = stats.chunks_out - stats.last_print_chunks
            rate_overall = stats.chunks_out / elapsed if elapsed > 0 else 0.0
            rate_recent = interval_chunks / interval_elapsed
            stats.last_print_ts = now
            stats.last_print_chunks = stats.chunks_out

            line = (
                f"[STATUS {time.strftime('%H:%M:%SZ', time.gmtime(now))}] "
                f"articles={stats.articles_in} "
                f"chunks={stats.chunks_out} "
                f"short_skipped={stats.short_sections_skipped} "
                f"rate_overall={rate_overall:.0f}/sec "
                f"rate_recent={rate_recent:.0f}/sec "
                f"elapsed={elapsed / 60:.1f}min"
            )
            print(line, flush=True)

            with contextlib.suppress(OSError):
                status_path.write_text(
                    json.dumps(
                        {
                            "ts": now,
                            "articles_in": stats.articles_in,
                            "chunks_out": stats.chunks_out,
                            "short_sections_skipped": stats.short_sections_skipped,
                            "rate_overall_per_sec": rate_overall,
                            "rate_recent_per_sec": rate_recent,
                            "elapsed_min": elapsed / 60,
                            "section_type_counts": dict(stats.section_type_counts),
                        },
                        indent=2,
                    )
                )


# ---------------------------------------------------------------- main
def stream_lines(input_path: Path):
    """Yield raw JSON lines from the gzipped input."""
    with gzip.open(input_path, mode="rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line:
                yield line


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--workers",
        type=int,
        default=max((os.cpu_count() or 2) // 2, 1),
        help="Worker processes (default: half of CPU count)",
    )
    parser.add_argument(
        "--status-interval",
        type=int,
        default=STATUS_INTERVAL_SEC,
        help="Status print interval in seconds (default 60)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Articles per pool.map batch (default 2000). Bounds peak memory; "
        "lower if you have less RAM.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N articles (debug/smoke).",
    )
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input not found: %s", args.input)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    status_path = args.output.parent / "_chunk_status.json"

    log.info("Tokenizer: %s @ %s", TOKENIZER_NAME, TOKENIZER_REVISION)
    log.info("Input:     %s", args.input)
    log.info("Output:    %s", args.output)
    log.info("Workers:   %d", args.workers)
    log.info(
        "Chunk params: max_tokens=%d, overlap=%d, min_section_chars=%d",
        MAX_TOKENS,
        OVERLAP_TOKENS,
        MIN_SECTION_CHARS,
    )

    stats = Stats()
    reporter = threading.Thread(
        target=status_reporter,
        args=(stats, status_path, args.status_interval),
        daemon=True,
    )
    reporter.start()

    partial_path = args.output.with_suffix(args.output.suffix + ".partial")
    partial_path.unlink(missing_ok=True)

    try:
        with (
            gzip.open(partial_path, mode="wt", encoding="utf-8") as out_f,
            mp.Pool(
                processes=args.workers,
                initializer=_worker_init,
                initargs=(TOKENIZER_NAME, TOKENIZER_REVISION),
            ) as pool,
        ):
            line_iter = stream_lines(args.input)
            if args.limit is not None:
                # bound the iterator
                def _bounded():
                    for i, line in enumerate(line_iter):
                        if i >= args.limit:
                            break
                        yield line

                source = _bounded()
            else:
                source = line_iter

            # Batched pool.map — bounded peak memory.
            # Each pool.map call submits batch_size articles and returns when
            # ALL workers have finished. The result list lives only as long
            # as the inner for-loop. Versus imap_unordered, this gives up
            # the "workers stay busy while writer flushes" overlap, but the
            # write to /home is fast enough that the gap is negligible
            # (and it avoids the 62 GB OOM kill we hit with imap_unordered).
            batch: list[str] = []

            def _flush(batch_lines: list[str]) -> None:
                if not batch_lines:
                    return
                results = pool.map(_process_article, batch_lines)
                # Stream results to disk + update stats
                local_chunks = 0
                local_skipped = 0
                for chunks, skipped in results:
                    local_skipped += skipped
                    if not chunks:
                        continue
                    local_chunks += len(chunks)
                    out_lines = [
                        json.dumps(c, ensure_ascii=False, separators=(",", ":")) for c in chunks
                    ]
                    out_f.write("\n".join(out_lines))
                    out_f.write("\n")
                with stats.lock:
                    stats.articles_in += len(batch_lines)
                    stats.chunks_out += local_chunks
                    stats.short_sections_skipped += local_skipped
                    for chunks, _ in results:
                        for c in chunks:
                            st = c["section_type"]
                            stats.section_type_counts[st] = stats.section_type_counts.get(st, 0) + 1

            for line in source:
                batch.append(line)
                if len(batch) >= args.batch_size:
                    _flush(batch)
                    batch = []
            _flush(batch)

        # Atomic publish
        partial_path.replace(args.output)
    except Exception:
        with contextlib.suppress(OSError):
            partial_path.unlink()
        raise
    finally:
        with stats.lock:
            stats.done = True
        reporter.join(timeout=2)

    elapsed = time.time() - stats.start_ts
    print()
    print(f"=== DONE in {elapsed / 60:.1f} min ===")
    print(f"  articles_in:            {stats.articles_in}")
    print(f"  chunks_out:             {stats.chunks_out}")
    print(f"  avg chunks/article:     {stats.chunks_out / max(stats.articles_in, 1):.1f}")
    print(f"  short sections skipped: {stats.short_sections_skipped}")
    print(f"  by section_type:        {dict(sorted(stats.section_type_counts.items()))}")
    print(f"  output:                 {args.output}")
    print(f"  output_size_bytes:      {args.output.stat().st_size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
