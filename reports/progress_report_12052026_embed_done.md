# geno_agent — Embedding Milestone — 2026-05-12

**Author:** Johanna Angulo
**Branch:** `phase1a/step-5b-ftp-extract-parse`
**Status:** Phase 1A.6 complete. 264 parquet shards (140 GB) on disk.
**Continuation of:** `reports/progress_report_11052026.md` (Phase 1A through chunking).

This is a focused milestone note. The full technical narrative lives
in the previous report.

---

## What just finished

```
=== DONE in 1279.1 min (21 h 19 min) ===
  shards_written:        264 / 264   ✅
  chunks_emitted_total:  52,782,789  ← exact match with chunker
  dense_time_min:        1096.2     (85.7 %)
  sparse_time_min:        144.3     (11.3 %)
  write_time_min:          23.2     ( 1.8 %)
  output_dir:            /home/hana77/embeddings/
```

Zero errors across 21 hours. 0 OOM events. 0 GPU memory issues. The
batched + Linux-fs design from `04_chunk_normalized.py` carried over
cleanly — the embedder also wrote to `/home` (140 GB total) rather
than `/mnt/c`, and used the same atomic `.partial → rename` shard
write pattern.

## Per-shard math

```
263 full shards    x  200,000 chunks = 52,600,000
1 final shard      x  182,789 chunks =    182,789
                                       ----------
                                       52,782,789  ✓  matches chunker exactly
```

## Output schema (22 columns per parquet row)

```
chunk_id, pmcid, pmid, doi, title, article_type, pub_year,
journal_title, issn, publisher, license_url, tier,
mesh_terms[], authors[],
section_type, section_heading,
chunk_index, total_chunks_in_section, text,
dense_embedding   (binary, 768 × float32 = 3072 bytes/row,
                   mean-pooled, L2-normalized),
bm25_indices[]    (int32 list — Qdrant token-hash IDs),
bm25_values[]     (float32 list — BM25 IDF weights)
```

This is the Qdrant payload + vector data, ready to upload.

## Throughput observations

- **Dense bottleneck** as expected: 86 % of total time was GPU inference at ~823 chunks/sec sustained (vs the ~1500 chunks/sec smoke-test extrapolation).
- **Sparse cost is small**: BM25 indexing is ~5000 chunks/sec single-threaded on CPU.
- **Write cost is trivial** on Linux ext4: 1.8 % of total. Validates the §6.3 fix of moving chunker output off `/mnt/c`.
- **No crashes, no OOM, no resume needed**: the bounded-batch design from the chunker survived the 21-hour run unchanged.

## Next step

Phase 1A.7 — create the Qdrant hybrid collection and upload all 264
shards. Container `qdrant_geno_agent` on `:6533/:6534` is already up
and has been since 2026-05-10. Existing skeleton script:
`scripts/indexing/10_create_qdrant_index.py` (~10 KB) needs adapting
for parquet shard input. Estimated upload time: **1.5–3 hours** at
typical Qdrant batch upsert rates.

After 1A.7:
- 1A.8 validation (`11_validate_index.py`, 12 sample queries)
- Update `data/MANIFEST.tsv` with SHA-256 of the chunked + embedded artifacts
- Unblock Phase 1B step 5 (causal-gene PMC coverage validation)

## Final stats snapshot

Persisted at `reports/embed_stats_2026-05-12.json`:

```json
{
  "elapsed_min": 1279.12,
  "shards_written_this_run": 264,
  "shards_total_on_disk": 264,
  "chunks_emitted_total": 52782789,
  "chunks_processed_this_run": 52782789,
  "dense_time_min": 1096.19,
  "sparse_time_min": 144.35,
  "write_time_min": 23.22,
  "output_dir": "/home/hana77/embeddings"
}
```

---

*End of milestone note.*
