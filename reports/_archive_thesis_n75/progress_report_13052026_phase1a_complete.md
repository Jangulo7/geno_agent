# geno_agent — Project Status — 2026-05-13 (Phase 1A complete)

**Author:** Johanna Angulo
**Branch:** `main` (PR #32 merged as `13b093d`)
**Status:** Phase 1A end-to-end **COMPLETE**. Phase 1B step 5 next.

This is a project-wide status snapshot taken right after the PR #32
merge that closes Phase 1A. The previous milestone notes
(`progress_report_11052026.md`, `…_12052026_embed_done.md`,
`…_13052026_qdrant_done.md`, `validation_results_2026-05-13.md`)
remain as the deep technical trail for each individual step.

---

## 1. Executive summary

The RAG knowledge corpus is live in Qdrant. **52,777,395 hybrid
points** (dense PubMedBERT 768-d + sparse Qdrant/bm25) from 2.25 M
genetics-filtered PMC OA articles are queryable on
`localhost:6533/geno_agent_pmc_oa_v1` with COSINE distance + BM25 IDF
fusion. The 12-query smoke test passes 12/12 across all three
retrieval modes. The agent stack from Phase 2a (LangGraph + Qwen3-8B
+ vLLM + 4 agents) already runs against this. The §11.5 factorial
evaluation just needs the Phase 1B test-case slate completed.

**Phase 1A wall-clock summary** (in-WSL processing only):

| Stage | Output | Wall time |
|---|---|---:|
| Parse + filter retractions | 309 JSONLs / 40 GB | 1 h 25 min |
| Normalize + dedupe + genetics filter | 1 JSONL / 25 GB / 2.25 M articles | 1 h 43 min |
| Section-aware chunking | 1 JSONL / 27.7 GB / 52.8 M chunks | 1 h 44 min |
| Embedding (dense + sparse BM25) | 264 parquet shards / 140 GB | 21 h 19 min |
| Qdrant hybrid upload | 109 segments / 52.78 M points | 11 h 1 min |
| Validation (12 probes × 3 modes) | report | ~2 min |
| **Total Phase 1A WSL processing** | | **~37 hours** |

(Excludes the ~1-day Windows-side FTP download done by the user.)

## 2. Phase status matrix

| Phase | Description | Status |
|---|---|---|
| 0 | Architecture & env | ✅ Done |
| 1A.1 | Ontologies + HGNC + Phenopackets (2026 pins) | ✅ Done |
| 1A.2 | PMC OA acquisition (FTP bulk, 309 tarballs / 147 GB) | ✅ Done |
| 1A.3 | Parse JATS | ✅ Done |
| 1A.4 | Normalize + dedupe + genetics filter | ✅ Done |
| 1A.5 | Section-aware chunking | ✅ Done |
| 1A.6 | Embedding (PubMedBERT FP16 + BM25 sparse) | ✅ Done |
| 1A.7 | Qdrant hybrid collection + index | ✅ Done |
| 1A.8 | Validation (12/12 probes PASS) | ✅ Done |
| 1A — MANIFEST signed | SHA-256 of normalized + chunks + Qdrant fingerprint | ✅ Done |
| **1B.1–1B.4** | Phenopacket ingest → categorize → stratified sample | ✅ Done (prior window) |
| **1B.5** | **PMC causal-gene coverage validation (≥5 articles/gene)** | ⏳ **Next** |
| 1B.6 | Build candidate gene lists (1 causal + 49 distractors) | ✅ Done (prior window) |
| 1B.7 | Persist canonical `test_cases.jsonl` | ✅ Done (prior window) |
| 1B.8 | Final acceptance gate (5 checks) | ✅ Done (prior window) |
| 2a | Agent stack (LangGraph + 4 agents + Qwen3-8B + vLLM) | ✅ Done (PRs #21–#30) |
| 2b | FastAPI loopback for the agent stack | ⏳ Not started |
| 2c | CopilotKit + Next.js UI | ⏳ Not started |
| 2d | §11.5 factorial evaluation (2×2+1 conditions) | ⏳ Blocked on 1B.5 |

**Note on 1B.5 ordering:** Phase 1B was driven end-to-end on a demo
corpus earlier (steps B1–B9 merged), but step 5 was deferred because
it requires a live production Qdrant index — which only landed today.
The pipeline is now ready to run step 5, which may invalidate-and-replace
some of the currently-sampled cases if their causal gene has <5
articles in the index.

## 3. Live corpus + index state

```
collection:     geno_agent_pmc_oa_v1
container:      qdrant_geno_agent (qdrant/qdrant:v1.14.1)
host:           localhost:6533 (REST), localhost:6534 (gRPC)
status:         green
points:         52,777,395
segments:       109
dense vector:   768-d, COSINE, on_disk=True, HNSW(m=16, ef_c=200)
sparse vector:  bm25, IDF modifier (server-side IDF, TF on query)
on_disk_payload: True
payload index:  section_type (KEYWORD), pmcid (KEYWORD), pub_year (INTEGER)
```

## 4. Per-step artifact inventory

```
/mnt/c/pmc_workspace/xml_raw/_archives/{oa_comm,oa_noncomm,oa_other}/
    309 tarballs + filelists (147 GB)
/mnt/c/pmc_workspace/parsed/{tier}/*.jsonl.gz
    309 JSONLs, ~40 GB
/mnt/c/pmc_workspace/parsed/all_articles.normalized.jsonl.gz
    25 GB, sha256 796136c0537e…
/home/hana77/chunks/all_chunks.jsonl.gz
    27.7 GB, sha256 da59cd55a3f0…
/home/hana77/embeddings/shard_NNNN.parquet
    264 shards, 140 GB total
~/rare-disease-rag/qdrant_storage/   (Qdrant bind mount)
    52.78 M-point hybrid index, fingerprint c6e53665…
```

## 5. PRs merged (cumulative across both windows)

| PR | Title |
|---|---|
| #21 | feat(phase2a): agent state schema + HPO/HGNC/Qdrant tool modules (C1+C2) |
| #22 | feat(phase2a): Query Planner agent — HPO expansion (C3) |
| #23 | feat(phase2a): Retriever agent — per-gene hybrid search wrapper (C4) |
| #24 | feat(phase2a): Critic agent — chunk grading (C5) |
| #25 | feat(phase2a): Synthesizer agent — per-gene aggregation (C6) |
| #26 | feat(phase1b): test-case scripts B1–B9 acceptance gate |
| #27 | docs(report): agentic architecture report |
| #28 | feat(phase2a): LangGraph state graph wiring with self-correction (C7a) |
| #29 | Phase 2a [C7b]: LLM client + Qwen3-8B + vLLM scripts |
| #30 | fix(phase2a): pass --reasoning-parser qwen3 to vLLM startup |
| **#32** | **feat(phase1a): FTP archive extractor → JATS parser → normalize → chunk → embed → upload → validate** (this window) |

(PR #31, the s5cmd S3-sync path, remains open as a parked fallback —
not needed since the FTP path completed.)

## 6. Difficulties resolved in the Phase 1A window (capsule)

For full technical detail see `progress_report_11052026.md` §6.

1. **PMC OA S3 bucket flattened** (no tier dirs) — deviation D4, switched to NCBI FTP bulk archives.
2. **`aws s3 sync` too slow** (~12 days projected) — tried `s5cmd` for 5–10× speedup.
3. **3 BIOS-screen reboots in 24 h** — pivoted away from multi-day WSL syncs entirely; FTP runs on Windows side.
4. **Worker race condition** in tarball extraction (40 crashes) — fixed with per-worker `tempfile.TemporaryDirectory()` on Linux ext4.
5. **12 truncated JSONLs** from killed runs surviving the idempotency check — fixed with atomic `.partial → rename`.
6. **Chunker OOM at 62 GB RSS** (unbounded `pool.imap_unordered` result queue + slow `/mnt/c` writes) — fixed with batched `pool.map` + output to `/home` ext4.
7. **Schema mismatch** between FTP parser and existing master-plan chunker — wrote `03_normalize_dedupe_filter.py` as the bridge step.
8. **Disk pressure on /mnt/c** during extraction (572 GB consumed in 3 h) — moved tooling to /home; auto-cleanup via TemporaryDirectory.

## 7. What unblocks now

| Phase | What | Blocker |
|---|---|---|
| **1B.5** | PMC causal-gene coverage validation | unblocked — running today |
| **2b/2c** | FastAPI + CopilotKit UI | unblocked (independent) |
| **2d** | §11.5 factorial evaluation | needs 1B.5 to land cleanly |

## 8. Next session plan (in order)

1. **Write `scripts/cases/17_validate_pmc_coverage.py`** (missing — master plan §6 step 5 has the spec; needs adapting for our port 6533 + collection name).
2. **Run it** against the live index. Per-case hybrid query for the causal gene symbol, count distinct PMCIDs in top-100, reject + replace from same category if <5.
3. **Re-run the final acceptance gate** (`20_validate_test_cases.py`) on the post-replacement test set.
4. **Update `data/MANIFEST.tsv`** with SHA-256 of the new `05_validated.jsonl`.
5. **Open PR for 1B.5** (small focused PR on a `phase1b/step-5-pmc-coverage` branch).

After 1B.5 lands:
- Phase 1B is fully complete — the §11.5 factorial is unblocked.
- Decide whether to proceed to Phase 2b (FastAPI), Phase 2c (UI), or Phase 2d (factorial evaluation) next.

## 9. Open items / technical debt

- Tables (`<table-wrap>`) are not extracted into chunks — only captions in section text. Add if downstream evaluation shows missing evidence in table-rich articles.
- References parsed only as count (`n_references`). Full citation graph deferred.
- MathML elements flattened to text. Most equations are images anyway.
- `08_section_aware_chunking.py` and `07_filter_corpus.py` (master-plan demo scripts) are kept in the repo but unused on the production path. Annotated as such.
- No unit tests for the new pipeline helpers (`normalize_record`, `is_genetics_article`, `classify_section_type`, `parse_jats`, `_row_to_point`). Worth adding before any future refactor.
- Host BIOS reboots (§6.4 in the 11052026 report). External, recommend user check Windows Event Viewer `Kernel-Power 41` / `WHEA-Logger`.

---

*End of project status snapshot. Next milestone note will document 1B.5.*
