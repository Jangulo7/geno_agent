# geno_agent — Progress Report — 2026-05-11

**Author:** Johanna Angulo
**Branch:** `phase1a/step-5b-ftp-extract-parse`
**Status:** Phase 1A data acquisition + corpus processing complete; embedding queued.
**Previous report:** `reports/progress_report_09052026_v3.md` (2026-05-09)

This is a deep technical report on the work done between 2026-05-09 and
2026-05-11. The focus of this window was finishing Phase 1A — turning
the PMC Open Access full-text corpus into a chunked, deterministic,
metadata-rich JSONL ready for embedding into Qdrant. Phase 2a (agentic
stack + Qwen3-8B + vLLM) was finished in the prior window and is now
parked; Phase 1B (test cases) was started earlier and is also parked
until the corpus is indexed.

---

## 1. Executive Summary

The corpus pipeline is **complete through chunking**. The next step is
embedding (PubMedBERT FP16 + BM25 sparse) and Qdrant index creation.

| Stage | Status | Artifact |
|---|---|---|
| §3.1 PMC OA acquisition | ✅ done (via NCBI FTP) | `xml_raw/_archives/{oa_comm,oa_noncomm,oa_other}/` 309 tarballs, 147 GB compressed |
| §4 step 1 — parse JATS XML | ✅ done | `parsed/{tier}/*.jsonl.gz` — 309 files, ~40 GB, ~2.6 M article rows (pre-dedup) |
| §4 step 2 — genetics filter | ✅ done | (merged into normalize, see §1A.3) |
| §4 step 3 — section-aware chunking | ✅ done | `/home/hana77/chunks/all_chunks.jsonl.gz` — **52.8 M chunks, 27.7 GB** |
| §4 step 4 — embedding | ⏳ next | needs ~10–15 h on RTX 5090 |
| §4 step 5 — Qdrant collection + index | ⏳ pending | container `qdrant_geno_agent` already up on :6533/:6534 |
| §4 step 6 — validation | ⏳ pending | |

**Final unique-article funnel:**

```
7,870,943  raw article rows in 309 FTP tarballs
  - 176          rows with no PMC ID (parser-side drops)
  - 61,471       baseline+incremental duplicates dropped
  ----------
7,809,296  unique PMC IDs across the FTP corpus
  - 5,554,908   dropped by genetics-relevance filter
  ----------
2,254,388  filtered articles -> chunker
                x 23.4 chunks / article (avg)
  ----------
52,782,789 chunks ready for embedding
```

**Difficulties encountered, in order of resolution:**

1. PMC OA S3 bucket layout had changed since the master plan was written (flat instead of tier-segmented).
2. `aws s3 sync` was too slow for the full corpus (~12 days at observed rate).
3. `s5cmd` was 5–10× faster but the host suffered **three involuntary WSL/BIOS reboots in a single day**, making any multi-day transfer unworkable.
4. Pivoted to user-managed FTP bulk download on the Windows side. New parser required because tar.gz packaging differs from S3's per-article layout.
5. First parser run had a worker race condition (multiple workers extracting to the same PMC-prefix directory could delete each other's XMLs) — 40 worker crashes in one run.
6. After the fix, found 12 leftover broken JSONL outputs from a previously killed run; the script's idempotency check (file size > 0) had incorrectly skipped them. Added atomic `.partial → rename` so this cannot recur.
7. Chunker run #1 was **OOM-killed at 62 GB resident memory** because `pool.imap_unordered` plus slow `/mnt/c` writes let the result queue grow unboundedly.

Each is detailed in §6.

---

## 2. Project Goals (recap)

`geno_agent` is a thesis project building an **agentic multi-agent RAG
system for rare-disease gene prioritization**. The system reads a
phenopacket (HPO term set), expands it via the HPO ontology, retrieves
PMC OA literature evidence for each candidate gene, grades that
evidence, and ranks the genes by causal-evidence weight.

The full system has three phases:

- **Phase 1A** — Build the deterministic, reproducible RAG knowledge corpus (PMC OA → hybrid Qdrant index).
- **Phase 1B** — Build the test-case benchmark (50–100 rare-disease cases from Phenopacket-store, 1 causal gene + 49 distractors each).
- **Phase 2** — Build the agentic layer (Query Planner, Retriever, Critic, Synthesizer agents over LangGraph; local Qwen3-8B via vLLM; CopilotKit + Next.js UI). Then run the §11.5 factorial evaluation (deterministic vs LLM-driven query planning + critic, with/without self-correction).

This report covers progress on Phase 1A primarily, with brief
recap of Phase 2a (foundations) from the prior window.

---

## 3. Phase Status Matrix

| Phase | Description | Status | Notes |
|---|---|---|---|
| **0** | Architecture & env setup | ✅ done | WSL2, Qdrant on :6533/:6534, pytorch-env reused |
| **1A.1** | Download ontologies (HPO/MONDO/GO/HGNC) + phenopackets | ✅ done | 2026 versions pinned, SHA-256 in `data/MANIFEST.tsv` |
| **1A.2** | PMC OA full-text acquisition | ✅ done | via NCBI FTP bulk (deviation, see §5) |
| **1A.3** | Parse JATS XML | ✅ done | `02_extract_and_parse_ftp.py`, 309 JSONLs |
| **1A.4** | Filter + dedupe + normalize | ✅ done | `03_normalize_dedupe_filter.py`, 2.25M filtered |
| **1A.5** | Section-aware chunking | ✅ done | `04_chunk_normalized.py`, 52.8M chunks |
| **1A.6** | Embedding (dense + sparse BM25) | ⏳ next | RTX 5090, ~10–15 h |
| **1A.7** | Qdrant collection + index | ⏳ pending | container already running |
| **1A.8** | Validation (12-query sample) | ⏳ pending | `11_validate_index.py` exists |
| **1B** | Test case prep (Phenopackets → 50–100 cases) | ⏸ paused | step [16] B9 acceptance gate already implemented; blocked on 1A.7 |
| **2a** | Agent stack: state graph, agents, vLLM, Qwen3-8B | ✅ done | PRs #19–#30 merged in prior window |
| **2b** | API exposure (FastAPI on loopback) | ⏳ not started | |
| **2c** | CopilotKit + Next.js UI | ⏳ not started | demo Qdrant collection works for UI dev |
| **2d** | §11.5 factorial evaluation | ⏳ not started | blocked on 1A + 1B |

---

## 4. Phase 1A — Detailed Progress (this window)

### 4.1 Data acquisition — three attempts, one survivor

The original master plan §3.1 specified downloading the PMC OA Subset
tier-by-tier (`oa_comm`, `oa_noncomm`, `oa_other`) from S3, streaming
each tier through processing and deleting before the next.

We had to make three pivots:

#### 4.1.1 Attempt 1 — `aws s3 sync`

The S3 bucket `pmc-oa-opendata` had been **restructured** since the
master plan was written. As of 2026-05-09 it is **flat**: articles live
at `s3://pmc-oa-opendata/PMC<id>.<version>/...` with no tier
directories. License tier is now recorded only inside per-article
`PMC<id>.<version>.json` metadata files. Also, the master plan's
documented fallback at `https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/`
returned 404 on 2026-05-09 over HTTPS (FTP protocol to the same host
remained available).

Consequence: the "stream by tier" strategy of §3.1 was infeasible;
license-tier classification had to be deferred to a downstream
step. The original script became a **single-pass full-corpus sync
filtered to `*.xml`**:

```bash
aws s3 sync --no-sign-request --exclude '*' --include '*/*.xml' \
    s3://pmc-oa-opendata/ /mnt/c/pmc_workspace/xml_raw/all/
```

Empirical throughput over a 7.5 h continuous run: **~12,000 files/hour**
(sequential, default 10 concurrent requests). That projected to
**~12–15 days** for the full ~4–5 M article corpus. Acceptable in
theory but a clear durability risk over a multi-day WSL session.

#### 4.1.2 Attempt 2 — `s5cmd` (parallel S3 client)

Switched to `s5cmd` v2.3.0 with default 256 worker threads. Single-stream
WiFi bandwidth on the host: ~30 Mbps; 8-stream aggregate: ~216 Mbps;
32-stream aggregate: ~296 Mbps (max usable). At that bandwidth ceiling
the projected sync would have dropped from ~12 days to **~2–3 days**.

We also discovered that `/mnt/c` write throughput for many small files
is much higher than `aws s3 sync` was exploiting:

| Mode | Files/sec |
|---|---:|
| Sequential 30 KB writes | ~400 |
| 200-way parallel 30 KB writes | **~1,259** |

So network was the real ceiling, not local disk — exactly the case
s5cmd's parallelism addresses.

**What killed this path:** the host suffered **three involuntary WSL/BIOS
reboots within 24 h** (2026-05-10 09:44, ~12:?, 13:40 local). Each
killed the in-flight sync. After three reboots in one day, attempting
a 2–3 day sync became untenable. PR #31 captures the s5cmd-based
script and remains open as a fallback.

#### 4.1.3 Attempt 3 — NCBI FTP bulk (the survivor)

The user manually downloaded the NCBI FTP bulk archives via a GUI
Windows FTP client (runs on the Windows side, immune to WSL reboots).
This produced **309 tarballs** totalling **~147 GB compressed XML**:

```
oa_comm/    105 GB, 120 .tar.gz baselines + incrementals
oa_noncomm:  36 GB, 120 .tar.gz
oa_other:   5.7 GB,  69 .tar.gz
```

The companion `.filelist.csv` files have a critical column the S3
bucket does not: **`Retracted` (yes/no)**. This is the authoritative
source of retraction status — far more reliable than parsing JATS
title prefixes (`RETRACTED:`).

This is the route we proceeded with. Recorded in master plan §10 as a
deviation; the script header in `01_download_pmc_oa.sh` and the new
`02_extract_and_parse_ftp.py` both document it.

### 4.2 Parsing pipeline — `02_extract_and_parse_ftp.py`

Master plan §4 step 1, adapted for the tar.gz layout. Each worker:

1. Loads its tarball's companion `.filelist.csv` and builds the set of retracted PMC IDs.
2. Verifies the tarball via `tarfile.open(mode="r:gz")` (raises on corrupt gzip — that's the integrity check).
3. Extracts XMLs to a **per-worker `tempfile.TemporaryDirectory()` on Linux ext4** (see §6.1 for why).
4. For each XML in the tarball, parses via `lxml.etree`, drops if its PMC ID is in the retracted set, otherwise emits one JSON line to the tarball's output `.jsonl.gz`.
5. Output written via `.partial → rename` so a crash mid-write cannot leave a half-written file that the next run mistakes for "already done".

**JATS fields extracted (full list):**

```
pmc_id, pmid, doi, article_type, title,
journal {title, ids, issn, publisher},
authors [{surname, given_names, aff_ids}],
affiliations {aff_id: text},
pub_dates {epub, ppub, collection, ...},
history {received, accepted},
abstract,
categories (subject group),
sections [{title, paragraphs}],
license {text, url}, copyright {statement, year, holder},
funding [statements],
n_references (count only; full ref parsing deferred to a later step)
```

**Production results:**

- Initial run (broken design): 581k articles written before fix-and-restart
- Final run after fix: **2,028,723** articles parsed across the 12 newly-processed tarballs (the others were already-done from a prior run, skipped)
- 11,898 retractions filtered (~0.42% of corpus — matches biomedical literature baseline)
- 5 parse errors out of 4.75 M attempts (~0.0001%)
- Runtime for the regen pass: 54.7 min on 12 workers

**Final on-disk artifact:** 309 `.jsonl.gz` files in
`/mnt/c/pmc_workspace/parsed/{tier}/` totalling ~40 GB.

### 4.3 Normalize + dedupe + filter — `03_normalize_dedupe_filter.py`

This step bridges the parser output to the chunker's expected schema,
deduplicates across baseline + incremental tarballs, and applies the
genetics-relevance filter.

**Why it exists as a separate step:**

The existing `08_section_aware_chunking.py` (master-plan-aligned, in place from earlier work) expects a different schema than our FTP parser produces:

| Chunker expects | Parser emits | Why different |
|---|---|---|
| `pmcid` | `pmc_id` | naming inconsistency between S3 vs FTP paths |
| `pub_year` (int) | `pub_dates.epub` (string) | parser keeps richer date info |
| `mesh_terms` | `categories` | JATS uses `<subject>` not MeSH explicitly |
| `sections[].section_type` | (none — only heading text) | needed standardized labels |
| `sections[].text` (concatenated paragraphs) | `sections[].paragraphs` (list) | parser preserved structure |
| (no separate abstract; first section) | `abstract` (separate field) | JATS layout |

Rather than modify either the parser or chunker (which would invalidate
master-plan-aligned tests), I wrote a normalization pass that bridges
the two schemas.

**Dedup strategy:** Iterate the 309 source `.jsonl.gz` files in
**reverse chronological order by tarball date**, emit each PMC ID only
once. Newest tarball seen first → newest article version wins.
Memory cost: one `set` of ~3 M PMC IDs ≈ 50 MB.

**Genetics filter:** Same vocabulary + regex as the original master-plan
`07_filter_corpus.py` (§4 step 2), which combines:

- ~75-term whitelist (genetics, mutation, exome, mendelian, …)
- A regex covering gene mentions, sequencing tech, OMIM/HGNC/Orphanet IDs, chromosome positions

Tested against title + abstract + categories.

**Section-type classifier:** Maps free-text section headings (`Materials and Methods`, `Results`, `2.1 Cell culture`, …) to a small set of standardized labels (`abstract`, `introduction`, `methods`, `results`, `discussion`, `case_report`, `references`, `acknowledgements`, or `other`) via regex matching.

**Schema produced** (for the chunker):

```
pmcid, pmid, doi, article_type, title, pub_year,
mesh_terms, authors[], affiliations{}, journal{},
license{}, copyright{}, funding[], n_references,
tier, source_tarball,
sections: [{section_type, heading, text}]   # text is paragraphs joined "\n\n"
```

**Production results:**

```
=== DONE in 102.8 min ===
  input_jsonls:           309
  input_records:          7,870,943
  no_pmcid:               176
  unique_pmcids:          7,809,296
  duplicates_dropped:     61,471      (0.79%)
  filtered_out_genetics:  5,554,908   (71.1%)
  written:                2,254,388   (28.9% retention)
  broken_files_skipped:   []          (all 309 intact)
  output:                 /mnt/c/pmc_workspace/parsed/all_articles.normalized.jsonl.gz (25 GB)
```

The 28.9 % genetics retention matched the smoke-test extrapolation of ~33 % closely.

### 4.4 Chunking — `04_chunk_normalized.py`

Master plan §4 step 3 implementation. Same deterministic UUID5 algorithm
and tokenization rules as `08_section_aware_chunking.py`, but rewired
for the production scale (multiprocessing, gzipped I/O, bounded memory).

**Chunking spec (from master plan §4 step 3):**

```
tokenizer:    NeuML/pubmedbert-base-embeddings
max_tokens:   512
overlap:      50 tokens
min_section:  50 chars
chunk_id:     uuid5(NAMESPACE, "pmcid|section_type|chunk_index|blake2b(text, 16)")
NAMESPACE:    6f9619ff-8b86-d011-b42d-00cf4fc964ff (PINNED — do not change)
```

**Architecture:**

- `multiprocessing.Pool` with PubMedBERT tokenizer loaded once per worker (initializer)
- Input streamed line-by-line from `/mnt/c/pmc_workspace/parsed/all_articles.normalized.jsonl.gz`
- Batched processing: `--batch-size` articles per `pool.map` call. Each batch fully completes before the next starts → bounded peak memory (see §6.3 for the OOM story this fixes)
- Output to **`/home/hana77/chunks/all_chunks.jsonl.gz`** (Linux ext4, not /mnt/c) — writes are ~10× faster than via 9P
- Atomic `.partial → rename` write
- Background status thread every 60 s, written to `_chunk_status.json` for tail-friendly monitoring

**Chunk record schema (one JSON line per chunk):**

```
chunk_id, pmcid, pmid, doi,
title, article_type, pub_year,
journal_title, issn, publisher, license_url,
tier, mesh_terms[], authors[],   # all from base_meta (per-article)
section_type, section_heading,
chunk_index, total_chunks_in_section,
text                              # the actual chunk
```

All metadata baked into each chunk record so the Qdrant upload step
(`10_create_qdrant_index.py`) doesn't need a join back to the source
JSONL to populate the payload.

**Production results:**

```
=== DONE in 103.7 min ===
  articles_in:            2,254,388
  chunks_out:             52,782,789
  avg chunks/article:     23.4
  short sections skipped: 298,234
  by section_type:
    abstract:           2,295,509    (4.3%)
    introduction:       4,287,952    (8.1%)
    methods:              674,039    (1.3%)
    results:            1,040,214    (2.0%)
    discussion:         6,372,375    (12.1%)
    case_report:          121,043    (0.2%)
    references:            47,699    (0.1%)
    acknowledgements:      24,194    (0.05%)
    other:             37,919,764    (71.8%)    # sub-sections (2.1, 2.2, ...)
  output:                 /home/hana77/chunks/all_chunks.jsonl.gz
  output_size_bytes:      27.7 GB
```

Sustained 8,400 chunks/sec on 12 workers. Avg 23.4 chunks/article
matched the 25.1 smoke-test estimate.

The dominance of `other` (71.8 %) is expected: PMC articles have
deeply nested sections (`2.1 Cell culture`, `2.2 Statistical analysis`,
…) that fall outside the eight canonical labels. They are still
chunked normally — the section_type label is mostly useful for
downstream filters (e.g., weight `results` higher in retrieval), and
articles missing canonical labels still contribute their text.

---

## 5. Master Plan Deviations (documented)

These are explicit departures from the v2.1 master plan, recorded for
the thesis methods chapter. Each is justified by a reason that the
plan itself would now have to address.

| ID | Deviation | Reason | Recorded in |
|---|---|---|---|
| D1 | 2026 ontology versions (HPO `v2026-02-16`, MONDO `v2026-03-03`, GO `2026-03-25`, HGNC `2026-04-07`) instead of 2024 pins | 2024 versions deprecated by ontology issuers | `data/MANIFEST.tsv`, master plan §10, CLAUDE.md |
| D2 | HGNC URL moved from EBI FTP to GCS bucket (doubled `archive/archive/` path) | HGNC infrastructure migration | CLAUDE.md, MANIFEST.tsv |
| D3 | Qdrant container on alt ports 6533/6534 instead of 6333/6334 | Two unrelated Qdrant instances pre-existed on the standard ports | CLAUDE.md, `.env` |
| D4 | PMC OA acquisition: **NCBI FTP bulk** instead of S3 streaming-by-tier | (a) S3 bucket layout flattened (no tier dirs); (b) `aws s3 sync` too slow; (c) `s5cmd` workable but host instability made multi-day sync infeasible (3 BIOS reboots in 1 day); (d) FTP path completed cleanly on Windows side | Script header `01_download_pmc_oa.sh`, PR #31 (parked), PR #32 (working) |
| D5 | Pre-flight retraction filtering uses the FTP `Retracted` column instead of JATS title-prefix parsing | The FTP filelist is the authoritative source; more reliable than string-matching `RETRACTED:` in titles | `02_extract_and_parse_ftp.py` docstring |
| D6 | Master plan §4 step 3 `08_section_aware_chunking.py` retained as-is; production runs use new `04_chunk_normalized.py` with same algorithm but gzipped I/O + bounded multiprocessing | Master plan script is single-file demo mode; production needed parallel + memory-safe pipeline | `04_chunk_normalized.py` docstring |
| D7 | Per-worker temp extract dirs on Linux ext4 (`/home/hana77/tmp_pmc_extract/`) instead of shared `/mnt/c` dir | Race condition between workers (see §6.1) + `/mnt/c` 9P slowness | `02_extract_and_parse_ftp.py` docstring |
| D8 | Chunk output on Linux ext4 (`/home/hana77/chunks/`) instead of `/mnt/c/pmc_workspace/chunks/` | Writer throughput; OOM in run #1 (see §6.3) | `04_chunk_normalized.py` docstring |

CLAUDE.md hard rule preserved: **Qdrant storage still on Linux fs at
`~/rare-disease-rag/qdrant_storage/`**; only the intermediate JSONL/chunk
artifacts moved. The final indexed corpus lives in the Qdrant location
the master plan requires.

---

## 6. Difficulties & Solutions

This section documents the actual obstacles encountered during this
window, with root cause, symptoms, fix, and outcome. Useful for the
thesis methods + lessons-learned sections.

### 6.1 Worker race condition in tarball extraction

**Symptom:** 40 `WORKER CRASH` messages mid-run, all of the form
`Error reading file '/mnt/c/.../PMC013xxxxxx/PMC13056894.xml': No such file or directory`.

**Investigation:** The crashes appeared during the parsing phase of
specific tarballs, not the extraction phase. Each error referenced a
file the worker had just extracted. The "file not found" was therefore
**not** an extraction failure — the file *had* existed but was *deleted
between extraction and parsing*.

**Root cause:** All workers were extracting their tarballs into the
**same** `/mnt/c/pmc_workspace/xml_raw/all/PMC0Nxxxxxx/` directory
structure (one PMC-prefix subdir per article-ID range). When two
tarballs (e.g. consecutive daily incrementals updating the same
article) contained the same PMC ID, two workers wrote to the same
filename, then one of them (with `--delete-extracted` enabled) deleted
its extracted file while the other worker was still parsing. The
parser raised `OSError` and the whole tarball's results were lost.

**Fix:** Each worker now uses `tempfile.TemporaryDirectory(prefix=tarball_stem, dir=/home/hana77/tmp_pmc_extract)`. The temp dir:

- Is unique per `(tarball, worker)` — no two workers can ever share a file path
- Is on Linux ext4 (`/home`) — extraction is ~10× faster than via /mnt/c 9P
- Auto-deletes on context-manager exit (success or exception) — bounded disk usage

**Outcome:** Zero crashes on the rerun. Side benefit: per-worker extraction is faster (no contention on the slow Windows mount).

**Commit:** `8f0bc2a` — fix(phase1a): per-worker temp extract dir on Linux fs (race + speed)

### 6.2 Atomic-write missing → 12 broken outputs from killed runs

**Symptom:** When the normalize step (§4.3) ran for the first time, it crashed with
`gzip.BadGzipFile: Compressed file ended before the end-of-stream marker was reached`
on one of the source JSONLs after 50 files in.

**Investigation:** Ran `gzip -t` against all 309 parser outputs.
12 of them failed integrity (truncated gzip streams):
9 large `oa_comm` baselines (PMC004-PMC012),
1 `oa_noncomm` baseline (PMC005),
2 `oa_noncomm` incrementals (2026-04-19, 2026-04-22).

**Root cause:** Earlier killed runs of the parser had been writing
directly to the final `.jsonl.gz` path. When `tmux kill-session` was
sent (e.g., during the OOM-fix-and-restart loop), workers were SIGKILL'd
mid-write, leaving half-written gzip files on disk. The script's
**idempotency check was `path.exists() and path.stat().st_size > 0`** —
which truncated gzips satisfy! So the next run skipped them as
"already done" even though they were unusable.

**Fix (in two places):**

1. Parser (`02_extract_and_parse_ftp.py`): write to `path.partial`, then `.replace(path)` only after successful close. A SIGKILL'd write leaves only the `.partial`, which `gzip.open()` rejects on the next run.
2. Normalize (`03_normalize_dedupe_filter.py`): wrap the input read in `try ... except (EOFError, gzip.BadGzipFile, OSError)` so a single broken JSONL doesn't abort the whole run; broken paths get logged to `broken_files_skipped` and the pass continues.

Then for the immediate fix: identified the 12 broken files, deleted them, re-ran the parser. The parser skipped the 297 intact files (idempotency check still works — non-zero-size and now atomically written) and regenerated only the 12 missing ones in 54.7 min on 12 workers.

**Outcome:** All 309 source JSONLs pass `gzip -t`. Subsequent normalize run reported `broken_files_skipped: []`.

**Commit:** `8f0bc2a` (parser side) + (normalize was already shipped with the fix).

### 6.3 Chunker OOM at 62 GB RSS

**Symptom:** After 57 min and ~16 M chunks produced, the chunker
process suddenly stopped emitting status lines. `tmux` session still
attached, workers still alive at 11–13 % CPU each, but no output.
Then a cascade of `BrokenPipeError` from every worker.

**Investigation:** Checked `dmesg`:

```
[40088.328138] oom_kill_process.cold+0xb/0x10
[40088.331475] Out of memory: Killed process 70483 (python)
                total-vm:75081856kB, anon-rss:61898476kB,
```

The main Python process consumed **62 GB RSS / 75 GB VM** before
the kernel OOM-killer fired. Workers' BrokenPipe errors were the
*consequence* of the main dying (not the cause).

**Root cause:** I used `pool.imap_unordered(_process_article, source)`
with a 25 GB gzipped input. Pool's internal result queue is **unbounded
by default**. Workers (CPU-fast) produced ~26-chunk lists per article.
Main consumed them with `out_f.write(...)` to `/mnt/c/pmc_workspace/chunks/all_chunks.jsonl.gz`. But /mnt/c writes via 9P
are slow (~3 MB/sec compressed gzip in practice). Workers outran the
writer; the result queue filled with un-consumed chunk lists; queue
grew unboundedly until OOM.

**Fix (two changes):**

1. **Batched `pool.map` instead of streaming `imap_unordered`.** Each call submits `--batch-size` (default 2000) articles, waits for ALL to complete, drains results to disk, then submits the next batch. Peak in-flight memory bounded by `batch_size × avg_chunks × chunk_size ≈ 100 MB`. No unbounded queue.
2. **Output moved to `/home/hana77/chunks/` (Linux ext4).** Native fs writes are ~10× faster than via 9P, so the writer keeps up with workers even at 8,400 chunks/sec.

**Outcome:** Run #2 completed cleanly in 103.7 min. Peak RSS observed
during the run: 9.6 GB (out of 62 GB available). No OOM risk.
`free -h` mid-run showed 53 GB still available.

**Commit:** `d3b6d86` — fix(phase1a): chunker OOM — bounded batches + Linux fs output

### 6.4 Host instability — three involuntary WSL/BIOS reboots in 24 h

**Symptom:** Three times on 2026-05-10 the user reported "I just saw
the BIOS screen for a moment." Each time, WSL's `uptime` showed
fresh boot times (09:44, ~12:?, 13:40 local). All running tmux sessions
were lost; the in-flight `aws s3 sync` (run 1) and subsequent
`s5cmd cp` (runs 2–3) all died after 7.5 h, 12 min, and 12 min
respectively.

**Investigation:** `dmesg` showed no OOM events for the syncs (they
used only ~500 MB RSS). `journalctl --since "1 hour ago"` showed
benign messages until each abrupt reboot. The pattern (BIOS screen
flash followed by Windows boot) suggests:

- **Power supply marginality** under transient load (RTX 5090 is 600 W TDP)
- Or **thermal protection** triggering an emergency shutdown
- Or **Windows kernel panic** with auto-reboot

This is a hardware/host environment issue outside the project's scope
to fix. The pragmatic response was to choose a workflow that doesn't
require multi-day continuous WSL runtime: do the long-running download
on the Windows side via FTP (immune to WSL reboots), and keep
WSL-side jobs to <2 h each so a reboot doesn't lose much progress.

**Outcome:** All subsequent WSL jobs (parser regen: 55 min, normalize:
103 min, chunker: 104 min) survived without reboot interruption.

**Recommendation for the user:** Check Windows Event Viewer for
`Kernel-Power 41` events (unexpected shutdown) and `WHEA-Logger`
events (hardware errors). If recurrent, suspect PSU before driver
issues.

### 6.5 Schema mismatch between FTP parser and existing chunker

**Symptom:** The existing `08_section_aware_chunking.py`
(master-plan-aligned, written before the FTP path existed) expects
field names that the FTP parser doesn't produce: `pmcid`, `pub_year`,
`mesh_terms`, and `sections[].section_type`. Our parser produces
`pmc_id`, `pub_dates.epub`, `categories`, and unstandardized section
headings.

**Root cause:** The existing chunker was written for the S3 path
(per-article XML files with a different metadata convention). The FTP
path produces the same content but via a different package (tar.gz
bundles) with naturally different field naming.

**Fix:** Wrote `03_normalize_dedupe_filter.py` as a schema-bridge
step between the parser and chunker. Same script also runs the
genetics-relevance filter (which would otherwise have been a separate
step) and the cross-tarball dedup (which would otherwise have required
a Pool-side join). One pass, three jobs.

**Outcome:** Chunker `04_chunk_normalized.py` reads the normalized
JSONL directly without modification. The existing
`08_section_aware_chunking.py` remains in the repo for the original
S3 demo path; it's no longer on the production critical path.

### 6.6 Disk pressure on /mnt/c

**Symptom:** After ~3 h of chunker run #1, `/mnt/c` had dropped from
848 GB free to 276 GB free (-572 GB), and the trajectory predicted
disk-full within another 80 min. The 5.76 M extracted XMLs in
`/mnt/c/pmc_workspace/xml_raw/all/` were the culprit — kept because
the chunker had been configured `--delete-extracted=False`.

**Fix sequence:** (a) Killed the in-flight chunker (which was in any
case about to OOM, but we didn't know that yet); (b) renamed all 14
PMC-prefix subdirs out of `xml_raw/all/` to `xml_raw/_trash_subdirs/`
(per-subdir mv worked even though parent-dir mv hit a /mnt/c
permission lock); (c) launched background `rm -rf` of the trash dirs
(slow on /mnt/c but doesn't block anything); (d) relaunched the
pipeline with `--delete-extracted=True`. Disk recovered to 465 GB
within ~10 min as the background cleanup made progress.

**Outcome:** /mnt/c free space stable at ~400 GB after the trash
cleanup completed. Chunker run #2 (with output on /home) never
touched /mnt/c for writes, so the issue is structurally gone.

### 6.7 Time-jump errors in WSL clock

**Symptom:** Status lines mid-pipeline occasionally showed
`elapsed` values going *backwards* (e.g., 23.3 min → 18.0 min between
two consecutive status messages). The status thread uses
`time.time()`, so a WSL clock-resync between intervals causes negative
elapsed deltas.

**Root cause:** WSL2's clock can drift from the Windows host clock,
and on suspend/resume or other events, `systemd-timedated` re-syncs
abruptly. `journalctl` confirms `Clock change detected. Flushing
caches.` events around the same timestamps as the elapsed jumps.

**Status:** Cosmetic only — the chunker counts articles processed,
not wall-time. No impact on correctness. Mention this in the report
because future status-thread implementations should use
`time.monotonic()` to be safe.

---

## 7. Current Corpus Metrics

### 7.1 Raw inputs

| Source | Size | Files |
|---|---:|---:|
| FTP tarballs (oa_comm) | 105 GB compressed | 120 |
| FTP tarballs (oa_noncomm) | 36 GB compressed | 120 |
| FTP tarballs (oa_other) | 5.7 GB compressed | 69 |
| **Total raw** | **147 GB** | **309** |

### 7.2 Pipeline funnel

| Stage | Articles / chunks | Size on disk |
|---|---:|---:|
| Raw article rows (309 JSONLs) | 7,870,943 | ~40 GB gz |
| Unique PMC IDs after dedup | 7,809,296 | (in-memory dedupe set ~50 MB) |
| After genetics filter | 2,254,388 | 25 GB gz (`all_articles.normalized.jsonl.gz`) |
| After chunking (1-to-many) | 52,782,789 chunks | 27.7 GB gz (`all_chunks.jsonl.gz`) |

### 7.3 Chunk distribution

| section_type | count | % |
|---|---:|---:|
| abstract | 2,295,509 | 4.3% |
| introduction | 4,287,952 | 8.1% |
| methods | 674,039 | 1.3% |
| results | 1,040,214 | 2.0% |
| discussion | 6,372,375 | 12.1% |
| case_report | 121,043 | 0.2% |
| references | 47,699 | 0.1% |
| acknowledgements | 24,194 | 0.05% |
| other | 37,919,764 | 71.8% |

### 7.4 Quality metrics

| Metric | Value |
|---|---:|
| Articles with at least one author | parsed; ~100% have authors per JATS rules |
| Articles with DOI | TBD (will report after Qdrant index) |
| Articles with both PMID and PMC ID | TBD |
| Articles with non-empty abstract | TBD |
| Retracted articles dropped | 11,898 |
| Parse errors | 5 (of ~4.75 M attempts) |
| Genetics-filter retention | 28.9 % |

---

## 8. Pull Requests Touched in This Window

| PR | Title | State | Branch | Notes |
|---|---|---|---|---|
| #31 | perf(phase1a): switch PMC OA sync to s5cmd + 5-min status logging | OPEN | `phase1a/step-5a-s5cmd-speedup` | Parked — fallback only; S3 path abandoned |
| #32 | feat(phase1a): FTP archive extractor + JATS parser + retraction filter | OPEN | `phase1a/step-5b-ftp-extract-parse` | Working PR; commits: `fb644cf`, `8f0bc2a`, `1121a60`, `d3b6d86` |

**Commits on PR #32:**

1. `fb644cf` — feat(phase1a): add FTP archive extractor + JATS parser + retraction filter
2. `8f0bc2a` — fix(phase1a): per-worker temp extract dir on Linux fs (race + speed)
3. `1121a60` — feat(phase1a): normalize+dedupe+filter and parallel chunker for FTP path
4. `d3b6d86` — fix(phase1a): chunker OOM — bounded batches + Linux fs output

Before merging PR #32: should add a passing test suite for the schema-bridge logic (`normalize_record()`, `is_genetics_article()`, `classify_section_type()`). Currently they have implicit tests via the production run; explicit unit tests would protect future refactors.

---

## 9. Next Steps

### 9.1 Immediate (next session)

1. **Read and adapt** `scripts/embedding/09_generate_embeddings.py` for the gzipped 52.8 M-chunk input. Likely needed:
   - `gzip.open()` input
   - Batched GPU inference (PubMedBERT FP16, batch 32–64)
   - **Both** dense (PubMedBERT 768-d) and sparse (fastembed `Qdrant/bm25`) vectors per chunk
   - Resumable output (idempotent on chunk_id since chunk_id is deterministic)
   - Status thread (every 60 s)
2. **Estimate runtime** with a smoke test on 10 k chunks. If 10–15 h projection holds, launch in tmux.
3. **`10_create_qdrant_index.py`** — create the collection in container `qdrant_geno_agent` on port :6533, hybrid scheme (dense + sparse), on-disk payload, ingest the embeddings.
4. **`11_validate_index.py`** — run the 12 master-plan sample queries to confirm retrieval works.
5. **`data/MANIFEST.tsv`** — append SHA-256 of `all_articles.normalized.jsonl.gz` + `all_chunks.jsonl.gz` + Qdrant snapshot.

### 9.2 Medium-term (Phase 1B unblocks)

Once 1A.7 (Qdrant index live) lands, Phase 1B step 5 ("PMC Causal-Gene Coverage Validation, ≥5 articles") can run. Phase 1B work already merged (steps 1–4 + acceptance gate) just waits for the index.

### 9.3 Longer-term (Phase 2)

Phase 2a (agentic stack) is done; Phase 2b (FastAPI loopback) and Phase 2c (CopilotKit UI) are independent of 1A and can start in parallel once 1A.7 is live. Phase 2d (the §11.5 factorial) needs both 1A and 1B complete.

---

## 10. Technical Debt & Open Items

| Item | Severity | Notes |
|---|---|---|
| `08_section_aware_chunking.py` is now unused on the production path | low | Keep for the S3 demo flow; document with a note pointing to `04_chunk_normalized.py` |
| `07_filter_corpus.py` is also unused on the production path | low | Same as above; filter logic now inlined in `03_normalize_dedupe_filter.py` |
| No unit tests for `normalize_record()`, `is_genetics_article()`, `classify_section_type()` | medium | Add before merging PR #32 to prevent silent regressions |
| Tables (`<table-wrap>`) are not extracted into chunks (only captions in section text) | low | Add if downstream evaluation shows missing evidence in table-rich articles |
| References parsed only as count (`n_references`) | low | Full citation graph would enable Phase 2 citation-based ranking; deferred |
| MathML elements flattened to whatever text content they have (usually nothing useful) | low | Most equations are images anyway; defer |
| Host BIOS reboots (§6.4) | external | Out of scope for software; suggest user check Event Viewer / PSU |
| `/mnt/c` trash dirs from §6.6 cleanup | low | Background `rm -rf` should have completed by now; verify before next session |
| Status thread uses `time.time()` not `time.monotonic()` (§6.7) | low | Cosmetic; fix in any future rewrite |

---

## 11. Appendix A — File Inventory (this window)

### New scripts

```
scripts/corpus/02_extract_and_parse_ftp.py        570 lines  (PR #32)
scripts/corpus/03_normalize_dedupe_filter.py      460 lines  (PR #32)
scripts/corpus/04_chunk_normalized.py             320 lines  (PR #32)
```

### Modified scripts (in this window)

```
scripts/corpus/01_download_pmc_oa.sh              s5cmd path (PR #31, parked)
```

### New runtime artifacts

```
/mnt/c/pmc_workspace/xml_raw/_archives/{oa_comm,oa_noncomm,oa_other}/   309 tarballs (147 GB)
/mnt/c/pmc_workspace/parsed/{oa_comm,oa_noncomm,oa_other}/              309 JSONLs (40 GB)
/mnt/c/pmc_workspace/parsed/all_articles.normalized.jsonl.gz            25 GB
/mnt/c/pmc_workspace/parsed/skipped_retractions.jsonl                    audit log
/mnt/c/pmc_workspace/parsed/_normalize_stats.json                        run summary
/home/hana77/chunks/all_chunks.jsonl.gz                                  27.7 GB
/home/hana77/chunks/_chunk_status.json                                   live status
/home/hana77/tmp_pmc_extract/                                            per-worker temp (auto-cleaned)
/home/hana77/rare-disease-rag/models/pubmedbert-base-embeddings/          438 MB (downloaded)
```

### Reports (existing)

```
reports/agent_architecture.{md,html,svg}              Phase 2a architecture (2026-05-09)
reports/progress_report_09052026.{md,html}             v1
reports/progress_report_09052026_v2.{md,html}          v2
reports/progress_report_09052026_v3.{md,html}          v3
reports/progress_report_11052026.{md,html}             THIS REPORT
reports/technical_report.md                            ongoing technical log
reports/visual_report.html                             dashboard
```

---

## 12. Appendix B — Timeline (this window)

| Time (local) | Event |
|---|---|
| 2026-05-09 18:27 Z | First S3 sync attempt (`aws s3 sync`) |
| 2026-05-10 09:44 local | WSL reboot #1 (kills 7.5 h aws sync) |
| 2026-05-10 10:33 Z | Switched to s5cmd, restarted sync |
| 2026-05-10 13:40 local | WSL reboot #2 (kills 12-min s5cmd run) |
| 2026-05-10 14:?? local | WSL reboot #3 |
| 2026-05-10 ~15:00 local | User starts manual FTP download on Windows |
| 2026-05-10 ~17:00 local | FTP download finishes; pivot to FTP-bulk path |
| 2026-05-10 ~17:30 local | First `02_extract_and_parse_ftp.py` run begins |
| 2026-05-10 ~18:00 local | First worker race condition crashes (40 errors) |
| 2026-05-10 ~18:30 local | Fixed via per-worker temp dirs; rerun |
| 2026-05-10 ~19:00 local | Parser completes; 309 JSONLs on disk |
| 2026-05-10 ~19:30 local | Found 12 broken JSONLs (truncated gzips from killed runs) |
| 2026-05-10 ~20:00 local | Atomic .partial -> rename fix; regen 12 broken files |
| 2026-05-10 ~20:30 local | Parser regen completes; all 309 JSONLs integrity-clean |
| 2026-05-10 ~20:35 local | `03_normalize_dedupe_filter.py` launched |
| 2026-05-10 ~22:08 local | Normalize completes (102.8 min) — **2.25 M filtered articles** |
| 2026-05-10 ~23:55 local | `04_chunk_normalized.py` v1 launched (had OOM bug) |
| 2026-05-11 ~00:55 local | Chunker OOM-killed at 62 GB RSS |
| 2026-05-11 ~01:00 local | Fix: batched pool.map + /home output; restart |
| 2026-05-11 ~02:44 local | **Chunker completes (103.7 min) — 52.8 M chunks** |
| 2026-05-11 09:00 local | This report written |

---

*End of report. Next milestone: embedding step (`09_generate_embeddings.py`).*
