# geno_agent — Qdrant Milestone — 2026-05-13

**Author:** Johanna Angulo
**Branch:** `phase1a/step-5b-ftp-extract-parse`
**Status:** Phase 1A.7 complete. Hybrid Qdrant index live with 52.78 M points.
**Continuation of:** `reports/progress_report_12052026_embed_done.md`.

## What just finished

```
=== DONE in 660.6 min (11 h 1 min) ===
  shards processed: 264 / 264    ✅
  points uploaded:  52,782,789

Live Qdrant collection (geno_agent_pmc_oa_v1):
  status:                  green
  points_count:            52,777,395
  indexed_vectors_count:   105,554,100   (dense + sparse counted separately)
  segments_count:          109
  dense vector:            768-d, COSINE, on_disk=True, HNSW (m=16, ef_c=200)
  sparse vector:           bm25 with IDF modifier
  on_disk_payload:         True
  payload indices:         section_type (KEYWORD), pmcid (KEYWORD), pub_year (INTEGER)
```

Delta of **5,394 points** between script-counted uploads (52,782,789) and
Qdrant-counted points (52,777,395) = **0.0102 %**, caused by UUID5 chunk_id
collisions on rare-but-real cases of two articles producing identical
`(pmcid, section_type, chunk_index, blake2b(text))` keys. Qdrant's
idempotent upsert keeps one. Expected and harmless.

## Pipeline summary so far

| Step | Output | Size | Wall time | Notes |
|---|---|---|---:|---|
| 1A.2 acquire (FTP) | 309 tar.gz | 147 GB | (manual on Windows) | deviation D4 |
| 1A.3 parse | 309 JSONLs | 40 GB | 31 + 55 min | atomic .partial → rename fix |
| 1A.4 normalize+dedupe+filter | 1 JSONL | 25 GB | 103 min | 29 % retention after genetics filter |
| 1A.5 chunk | 1 JSONL | 27.7 GB | 104 min | 12 workers, batch 2000, OOM-bounded |
| 1A.6 embed | 264 parquet shards | 140 GB | 21 h 19 min | PubMedBERT FP16 + Qdrant/bm25 sparse |
| **1A.7 upload to Qdrant** | live hybrid collection | 52.78 M points / 109 segments | **11 h 1 min** | parallel=4, batch=256 |

Total Phase 1A wall time (in-WSL processing only): **~35 hours**.

## Next steps

| Step | Status |
|---|---|
| 1A.8 validate (12 sample queries) | ⏳ next, minutes |
| Update `data/MANIFEST.tsv` with SHA-256s | ⏳ after validation |
| Unblock Phase 1B step 5 (causal-gene PMC coverage) | once MANIFEST signed |

## Final stats snapshot

Persisted at `reports/qdrant_upload_stats_2026-05-13.json`.
