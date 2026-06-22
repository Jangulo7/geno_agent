# geno_agent — Project status & resumption plan

**Date:** 2026-05-09 (Saturday)
**Author:** Johanna Angulo (johanna.angulo@gmail.com)
**Snapshot of:** `main` @ commit `3308a0f`
**Reference:** [`MASTER_PROJECT_v2.1.md`](../MASTER_PROJECT_v2.1.md)

---

## 1. Where the project is right now

| Phase | Status | Evidence |
|---|---|---|
| **Phase 1A — Acquisition (§3)** | ✅ Complete | `data/MANIFEST.tsv` (8 ontology artifacts SHA-256-hashed) |
| **Phase 1A — Pipeline scripts (§4)** | ✅ Complete (demo path) | 7 scripts in `scripts/{corpus,embedding,indexing}/`, end-to-end demo at `reports/visual_report.html` |
| **Phase 1A — Production corpus build (§7 step 5 production)** | ❌ Not started | No PMC OA tier downloaded; demo uses 100 articles via NCBI esearch instead of `aws s3 sync` |
| **Phase 1B — Test case preparation (§6)** | ❌ Not started | Blocked on full Phase 1A corpus per `CLAUDE.md` hard rule |
| **Phase 2 — Agent layer** | ❌ Not started | Out of scope for Phase 1; no LangGraph code in `src/` |

A working **end-to-end Phase 1A pipeline** runs in 44 seconds on the 100-article demo sample (RTX 5090, cu128 nightly torch). All 12 rare-disease probe queries return relevant top-1 hits across dense, BM25, and hybrid (RRF) modes. Reproducibility is verified: deterministic UUID5 chunk IDs, pinned 2026 ontologies, `qdrant/qdrant:v1.14.1` server, `pyproject.toml` with all 19 deps frozen to exact installed versions.

What is **missing for the full thesis** is the production corpus (the 150 GB / 5–9 day machine run that turns the same scripts into a 2–5 M chunk index), the Phase 1B 50–100 case benchmark on top of that index, and the Phase 2 agentic layer.

---

## 2. Master plan §7 checklist — completion status

| #   | Step | Status | Notes |
|---|---|---|---|
| [1] | Project structure | ✅ | All required dirs present (`~/rare-disease-rag/{qdrant_storage,models,logs}`, `/mnt/c/pmc_workspace/`, `data/`, `src/`, `scripts/`, `tests/`, `config/`, `logs/`) |
| [2] | Python env + Qdrant + `seed.py` | ✅ | Reuses `/home/hana77/pytorch-env/` per project memory; Qdrant container `qdrant_geno_agent` running on `:6533/:6534`, image v1.14.1 |
| [3] | Ontology download + verification | ✅ | HPO/MONDO/GO/HGNC + companion files all hashed and verified |
| [4] | Empty Qdrant collection | ✅ | `geno_agent_pmc_oa_v1` — dense 768d HNSW + BM25 IDF + payload indices |
| [5a] | Download PMC OA tiers | 🟡 Partial | Demo sample (100 articles, 12.8 MB) downloaded via NCBI esearch+efetch. Production AWS S3 sync of `oa_comm`+`oa_noncomm`+`oa_other` not started |
| [5b] | Parse JATS XML | ✅ Script ready | Validated on 100 articles → 559 sections |
| [5c] | Filter for genetics | ✅ Script ready | Validated on 100 articles → 89 retained (89 %) |
| [5d] | Section-aware chunking (UUID5) | ✅ Script ready | Validated on 89 articles → 1,625 chunks (avg 18.3) |
| [5e] | PubMedBERT embedding | ✅ Script ready | Validated on 1,625 chunks at **351 chunks/s** on RTX 5090 |
| [5f] | Upload to Qdrant (dense + BM25) | ✅ Script ready | Validated; collection at 1,625 points, status green |
| [6]  | Validate index | ✅ | 12 probes × {dense, bm25, hybrid} all return relevant top-1 |
| [7]  | Acquisition manifest | 🟡 Partial | `data/MANIFEST.tsv` covers ontologies; will need re-run after PMC OA / phenopacket downloads |
| [8]  | Phenopacket-store v0.1.19 download | ❌ | Phase 1B; deferred per `CLAUDE.md` hard rule |
| [9]  | Phenopacket ingest | ❌ | Phase 1B |
| [10] | Inclusion/exclusion filter | ❌ | Phase 1B |
| [11] | MONDO categorization | ❌ | Phase 1B |
| [12] | Stratified random sampling (seed=42) | ❌ | Phase 1B |
| [13] | PMC coverage validation (≥5 articles per causal gene) | ❌ | Phase 1B; **requires full corpus index** |
| [14] | Candidate gene-list builder (1 + 49 distractors from HGNC) | ❌ | Phase 1B |
| [15] | Finalize canonical `test_cases.jsonl` | ❌ | Phase 1B |
| [16] | Acceptance gate | ❌ | Phase 1B |

**Numerical summary:** 11 of 16 master-plan checklist items are complete or partially complete; 5 are blocked on the production corpus build.

---

## 3. What was delivered between 2026-05-08 and 2026-05-09

Twelve commits over two days (six PRs, all merged to `main`):

| Commit | Description |
|---|---|
| `c79689c` | Ontology MANIFEST.tsv + path-alias gitignore |
| `5408d65` | Thesis-level README expansion |
| `436539a` | `pyproject.toml` (19 deps pinned) + `scripts/utils/seed.py` |
| `14c59f9` | `12_verify_ontologies.py` (HPO/MONDO/GO/HGNC validator) |
| `3fdd140` | `10_create_qdrant_index.py` collection schema + Qdrant v1.14.1 bump |
| `8627b1b` | `01_demo_fetch_pmc.py` + `06_parse_jats_xml.py` |
| `e779a0f` | `07_filter_corpus.py` + `08_section_aware_chunking.py` |
| `c553d14` | `09_generate_embeddings.py` + `10..--upload` + `11_validate_index.py` |
| `3308a0f` | TFM demo report bundle (HTML, MD, charts, run logs, stats JSON, orchestrator) |

Repository: <https://github.com/Jangulo7/geno_agent>

---

## 4. What remains, by track

### Track A — Production corpus build (Phase 1A finish line)

Same scripts already validated, run on the full 150 GB PMC OA. Master plan §7 estimate: 5–9 days wall-clock.

| Sub-step | Action | Estimated time |
|---|---|---|
| Write `01_download_pmc_oa.sh` | Adapt master plan §3.1 shell script for AWS `--no-sign-request` sync, tier-by-tier | ~1 hour |
| Run `5a` for tier `oa_comm` | `aws s3 sync` ~40–50 GB | 2–4 hours |
| Run `5b` parse | lxml on tier | 1.5–3 hours |
| Run `5c` filter | hard-asserted [100K, 600K] retention | 10–20 min |
| Run `5d` chunk | UUID5 deterministic | 1–2 hours |
| Run `5e` embed | RTX 5090 sustained | 8–16 hours |
| Run `5f` upload | Qdrant batched upsert | 1–2 hours |
| Repeat for `oa_noncomm`, `oa_other` | Tier-by-tier streaming per master plan §7 | 2 × the above |
| Final `11_validate_index.py` | Probe queries | 5 min |
| Re-run manifest | Append PMC OA SHA-256 to `MANIFEST.tsv` | 5 min |

**Total wall-clock per master plan §7: 5–9 days**, dominated by ~24–48 GPU-hours of embedding across the three tiers. **Must run on a workstation that stays awake.** Disk requirement: ~500 GB peak Linux + ~200 GB peak Windows.

### Track B — Phase 1B test case preparation

Blocked on Track A completion (step [13] PMC coverage validation queries the full Qdrant index). Once unblocked: 1–2 days of engineering + ~1 hour of Phenopacket processing.

Eight scripts to write per master plan §6:

```
scripts/cases/04_download_phenopacket_store.sh   ([8])  ~50 MB tarball
scripts/cases/13_load_phenopackets.py            ([9])  6,668 JSON files → JSONL
scripts/cases/14_apply_inclusion_exclusion.py    ([10]) ≥3 HPO terms, single-gene pathogenic, no chromosomal/mito
scripts/cases/15_categorize_by_mondo.py          ([11]) 4 disease categories (neuro/metabolic/immuno/dev)
scripts/cases/16_stratified_sample.py            ([12]) seed=42, target 75 cases (configurable)
scripts/cases/17_validate_pmc_coverage.py        ([13]) ≥5 PMC articles per causal gene; replace if not
scripts/cases/18_build_candidate_lists.py        ([14]) 1 causal + 49 HGNC distractors (per-case derived seed)
scripts/cases/19_finalize_test_cases.py          ([15]) canonical test_cases.jsonl + manifest
scripts/cases/20_validate_test_cases.py          ([16]) acceptance gate
```

### Track C — Phase 2 agent layer

Not yet specified in `MASTER_PROJECT_v2.1.md` (Phase 1 only). Expected scope per `README.md`:

- LangGraph state graph orchestrating four agents:
  - **Query Planner**: HPO term expansion, MeSH query construction
  - **Retriever**: hybrid Qdrant search with section-type filters
  - **Critic**: relevance grading, gene-mention validation against HGNC
  - **Synthesizer**: re-ranked candidate list with cited justifications
- Reasoning model: Qwen3-8B (per README; ~8B params, fits in 32 GB VRAM)
- Evaluation harness: 2×2+1 factorial (single-agent vs multi-agent × dense-only vs hybrid + Exomiser baseline)

**Not blocked on Track A** — agent code can be developed against the demo corpus (1,625 chunks) while Track A's machine time runs in parallel. Quantitative evaluation is blocked on Track B.

---

## 5. Recommended resumption order

Two reasonable strategies depending on how much hands-on time vs machine time you want:

### Option 1 — Strict sequential (lowest risk, longest calendar)

1. **Today/tomorrow:** write `01_download_pmc_oa.sh` (~1 h).
2. **Next 5–9 days:** run Track A end-to-end on a workstation that stays awake. Periodic checks but mostly machine time.
3. **Day 10–11:** Track B (Phase 1B) — 1–2 days of engineering on the now-populated index.
4. **Day 12+:** Track C (Phase 2) agent development.

### Option 2 — Parallel (recommended if calendar matters)

1. **Today/tomorrow:** write `01_download_pmc_oa.sh`, kick off the download tonight.
2. **Tomorrow morning:** while download/parse runs unattended, start Track C agent code against the existing 1,625-chunk demo collection. Develop Query Planner + Retriever + Critic + Synthesizer end-to-end on the small substrate; iterate on prompts and grading rubrics.
3. **Day 5–7:** Track A finishes. Run Track B (Phase 1B) on the now-populated production index.
4. **Day 7–10:** Connect the agent layer (built in step 2) to the production corpus. Run quantitative evaluation against Phase 1B benchmark and Exomiser baseline.

**My recommendation: Option 2.** The agentic prompts and grading logic are the highest-uncertainty work — the sooner you start iterating on them, the more cycles you get. The full corpus is just a scale-up of identical retrieval semantics.

---

## 6. Open risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PMC OA `aws s3 sync` interruption mid-download (network, host sleep) | Medium | High (re-download wastes hours) | `aws s3 sync` is resumable by default; run inside `tmux`/`screen`; disable host sleep for the duration |
| Filter §4.2.2 retention falls outside [100K, 600K] band on the full corpus | Low | High (hard abort by `--strict`) | Run on `oa_comm` first, inspect retention before chaining the other two tiers |
| Embedding OOM on a section/article with anomalously long text | Low | Medium | Tokenizer enforces 512-token chunks at chunking time; embedder receives uniform-length inputs |
| Qdrant index corruption from forced container kill mid-upsert | Low | High (re-build the tier) | Use `docker compose down` not `kill`; HNSW is incrementally consistent on graceful shutdown |
| Phenopacket-store v0.1.19 release URL changes / 404 | Low | Medium | Pinned URL recorded in script; if 404, fall back to git tag tarball |
| `pytorch-env` torch nightly is replaced by user's other ML work | Low | Medium | `pyproject.toml` records exact versions; if drift detected, `pip install -r requirements.lock.txt` to re-pin |
| Rate-limit / NCBI E-utilities ban during demo re-runs | Very low | Low | Demo path uses `time.sleep(0.34)` (3 req/s, no API key); production uses S3 not NCBI |

---

## 7. Concrete next actions (pickable now)

| Priority | Action | Owner | Estimated |
|---|---|---|---|
| P0 | Write `scripts/corpus/01_download_pmc_oa.sh` (production AWS sync) | engineering | ~1 hour |
| P0 | Decide: Option 1 sequential vs Option 2 parallel | user | ~10 min |
| P1 | Kick off `01_download_pmc_oa.sh` for tier `oa_comm` (background, ~3 h) | machine | ~2–4 hours |
| P1 | Scaffold `src/agents/` with LangGraph state graph skeleton | engineering | ~half day |
| P2 | Add Qdrant payload index on `mesh_terms` (currently unindexed; needed for Critic agent's MeSH-filtered queries) | engineering | ~30 min |
| P2 | Write Phase 1B script `13_load_phenopackets.py` (no Qdrant dependency) | engineering | ~1 hour |
| P3 | Add `requirements.lock.txt` snapshot via `pip freeze > requirements.lock.txt` | engineering | ~5 min |

---

## 8. Resource & infrastructure status

| Resource | Status | Notes |
|---|---|---|
| Workstation (RTX 5090 / 64 GB RAM / WSL2) | ✅ Available | cu128 nightly torch validated end-to-end |
| Linux disk (~700 GB) | ✅ Available | `~/rare-disease-rag/qdrant_storage/` empty (needs ~300–500 GB for full index) |
| Windows scratch (`/mnt/c/`) | ✅ Available | Currently 18 MB used (demo); needs ~200 GB peak per tier |
| Qdrant container | ✅ Running | `qdrant_geno_agent` v1.14.1 on `:6533/:6534`, status green, 1,625 demo points |
| GitHub auth | ✅ Working | `gh auth setup-git` configured, `gh` token persistent |
| PubMedBERT model weights | ✅ Cached | `~/.cache/huggingface/` populated from demo run |
| Qdrant BM25 model weights | ✅ Cached | `~/.cache/fastembed/` populated |

**No new dependencies need to be installed** to resume any of Track A, B, or C.

---

## 9. Citation & where things live

- Source: <https://github.com/Jangulo7/geno_agent>
- Master plan (full spec): [`MASTER_PROJECT_v2.1.md`](../MASTER_PROJECT_v2.1.md)
- Demo report (this snapshot's predecessor): [`reports/visual_report.html`](visual_report.html) · [`reports/technical_report.md`](technical_report.md)
- Pipeline orchestrator: [`scripts/demo/run_pipeline.sh`](../scripts/demo/run_pipeline.sh)
- Acquisition manifest: [`data/MANIFEST.tsv`](../data/MANIFEST.tsv)

---

*Snapshot taken 2026-05-09; regenerate this report after any major milestone (production corpus complete, Phase 1B finalized, first agent prototype) so the project always has a current status anchor.*
