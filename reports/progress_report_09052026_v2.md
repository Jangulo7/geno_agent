# geno_agent — Project status v2

**Date:** 2026-05-09 (Saturday, ~21:00 local)
**Author:** Johanna Angulo (johanna.angulo@gmail.com)
**Snapshot of:** `main` @ `eb110e6`
**Reference:** [`MASTER_PROJECT_v2.1.md`](../MASTER_PROJECT_v2.1.md)
**Supersedes:** [`progress_report_09052026.md`](progress_report_09052026.md) (v1, this morning)

---

## 1. Headline change since v1 (this morning)

| Track | v1 status (this morning) | v2 status (now) |
|---|---|---|
| Phase 1A scripts | ✅ 100 % (demo path) | ✅ 100 % (demo) + ✅ production wrapper ready |
| Phase 1A corpus | ⏳ 10 % (demo only) | ⏳ **about to start** (full build kicked off after this report) |
| Phase 1B test cases | ⏳ 0 % | ⏳ **56 % — 5 of 9 scripts written, 75 cases sampled** |
| Phase 2 plan | ✅ Locked in master plan §11 | ✅ same |
| Phase 2 implementation | ⏳ 0 % | ⏳ 0 % (Phase 2c UI requires Qwen3-8B + agents first) |

**Net delta:** in ~5 hours (2026-05-09 16:00 → 21:00) the project went from "demo only + Phase 1B blocked" to "Phase 1B 5/9 scripts done, 75 deterministic test cases drawn, production download wrapper ready". The only Phase 1B step that is hard-blocked is **B6** (PMC coverage validation, needs the production index).

---

## 2. What was delivered this afternoon (PRs #10 → #15)

| PR  | Commit  | Description |
|---|---|---|
| [#10](https://github.com/Jangulo7/geno_agent/pull/10) | `95fd7c7` | A1 — production PMC OA download wrapper (`scripts/corpus/01_download_pmc_oa.sh`); master plan §10 records the bucket-layout deviation (flat layout, no tier prefixes) |
| [#11](https://github.com/Jangulo7/geno_agent/pull/11) | `810a92a` | B1 — Phenopacket-Store v0.1.19 download (6,668 JSONs, 11.6 MB zip in MANIFEST) |
| [#12](https://github.com/Jangulo7/geno_agent/pull/12) | `9d0178b` | B2 — phenopacket ingest → JSONL (3,941 records/s; 97.9 % have HPO terms; avg 8.1 HPO/case) |
| [#13](https://github.com/Jangulo7/geno_agent/pull/13) | `972ea2f` | B3 — inclusion/exclusion filter w/ MONDO exclusions (3,878 / 6,668 eligible, 58.2 %) |
| [#14](https://github.com/Jangulo7/geno_agent/pull/14) | `9b75ee6` | B4 — MONDO disease categorization w/ priority resolution (2,971 categorized; neuro 2,231 / metabolic 350 / immuno 85 / dev 305) |
| [#15](https://github.com/Jangulo7/geno_agent/pull/15) | `eb110e6` | B5 — stratified random sampling, seed=42 (75 cases drawn, 18/19/19/19 split) |

All six PRs merged via rebase to `main`.

---

## 3. Phase 1B: 5 of 9 scripts done

| Step | Script | Status | Output |
|---|---|---|---|
| [8] | `04_download_phenopacket_store.sh` | ✅ done | `data/phenopackets/v0.1.19/` (6,668 JSONs) |
| [9] | `13_load_phenopackets.py` | ✅ done | `01_all_phenopackets.jsonl` (6,668 records) |
| [10] | `14_apply_inclusion_exclusion.py` | ✅ done | `02_eligible.jsonl` (3,878 records) |
| [11] | `15_categorize_by_mondo.py` | ✅ done | `03_categorized.jsonl` (2,971 records) |
| [12] | `16_stratified_sample.py` | ✅ done | `04_sampled.jsonl` (75 records) |
| [13] | `17_validate_pmc_coverage.py` | ⏳ **hard-blocked on production corpus** | `05_validated.jsonl` |
| [14] | `18_build_candidate_lists.py` | ⏳ pending (no Qdrant dep) | `06_with_candidates.jsonl` |
| [15] | `19_finalize_test_cases.py` | ⏳ pending (no Qdrant dep) | `test_cases.jsonl` (canonical) |
| [16] | `20_validate_test_cases.py` | ⏳ pending (no Qdrant dep) | acceptance gate |

Steps [14]–[16] can be implemented and tested locally on the current 75-case sample without waiting for the production corpus.

---

## 4. The 75-case test sample

Drawn deterministically with `random.Random(42)`. Distribution:

| Category | Sampled | Available pool | Headroom factor |
|---|---|---|---|
| neurological | 18 | 2,231 | 124× |
| metabolic | 19 | 350 | 18× |
| immunological | 19 | 85 | 4.5× |
| developmental | 19 | 305 | 16× |
| **Total** | **75** | 2,971 | — |

Sample file: `data/test_cases/04_sampled.jsonl` (gitignored; reproducible byte-for-byte from the script + manifested phenopackets zip).

---

## 5. Disk space audit (verified 2026-05-09 21:00)

| Filesystem | Total | Used | **Available** | What lives here |
|---|---|---|---|---|
| Linux `/dev/sdc` | 1.7 TB | 763 GB | **870 GB** | Qdrant index, models, code, ontologies |
| Windows `/mnt/c/` | 3.7 TB | 2.5 TB | **1.2 TB** | PMC OA XML download + intermediates |

### Projected usage after full Phase 1A + 2

| Filesystem | Required peak | Headroom |
|---|---|---|
| Linux | ~516 GB (300–500 Qdrant + 16 Qwen3 + small) | ~354 GB ✓ |
| Windows | ~215 GB (150 XML + ~30 embeddings + ~25 intermediates) | ~985 GB ✓ |

Both filesystems comfortably fit the master plan §7 worst-case estimates with significant slack. **No disk-space risk to the full build.**

---

## 6. Updated master plan §7 checklist

| #   | Step | Status |
|---|---|---|
| [1] | Project structure | ✅ |
| [2] | Python env + Qdrant + `seed.py` | ✅ |
| [3] | Ontologies + verification | ✅ |
| [4] | Empty Qdrant collection | ✅ |
| [5a] | Production PMC OA download | 🔄 **starting now** (script ready since PR #10) |
| [5b] | Parse JATS XML | ✅ Script ready (validated on demo) |
| [5c] | Filter genetics | ✅ Script ready |
| [5d] | UUID5 chunking | ✅ Script ready |
| [5e] | PubMedBERT embedding | ✅ Script ready (351 chunks/s on RTX 5090) |
| [5f] | Qdrant upload | ✅ Script ready |
| [6] | Validate index | ✅ Script ready |
| [7] | Acquisition manifest | 🟡 Will be appended after [5a]/[8] artifacts land |
| [8] | Phenopacket-store download | ✅ |
| [9] | Phenopacket ingest | ✅ |
| [10] | Inclusion/exclusion filter | ✅ |
| [11] | MONDO categorization | ✅ |
| [12] | Stratified sampling | ✅ |
| [13] | PMC coverage validation | ⏳ Blocked on [5a]–[6] production run |
| [14] | Candidate gene-list builder | ⏳ Pending (no Qdrant dep) |
| [15] | Finalize `test_cases.jsonl` | ⏳ Pending |
| [16] | Acceptance gate | ⏳ Pending |
| [17]–[27] | Phase 2 (agents + UI + eval) | ⏳ Plan in §11; implementation pending |

**14 of 27 steps complete or partial; 13 remaining.**

---

## 7. What's about to happen

After this report is committed, the production PMC OA full-corpus download is being kicked off in the background via:

```bash
nohup bash scripts/corpus/01_download_pmc_oa.sh > logs/download_pmc_oa.stdout 2>&1 &
disown
```

The download runs for an estimated **5–9 days wall-clock** (4–8 h transfer, 24–48 h embedding once the pipeline gets there, replicated across 3 conceptual tiers — though our flat sync collapses that to a single pass). It writes to `/mnt/c/pmc_workspace/xml_raw/all/` and logs to `logs/download_pmc_oa.log`.

The download survives terminal disconnects via `nohup`. Monitor progress with:

```bash
tail -f logs/download_pmc_oa.log     # live log
du -sh /mnt/c/pmc_workspace/xml_raw/  # disk growth
ps -p $(pgrep -f 01_download_pmc_oa)  # process check
```

To stop early:

```bash
pkill -f 01_download_pmc_oa.sh        # graceful (sync resumes on rerun)
```

---

## 8. Recommended next actions in priority order

| P | Action | Track | Time | Why |
|---|---|---|---|---|
| **P0** | Wait for production corpus to populate (passive, machine-only) | A | ~5–9 days | Unblocks B6, B7 PMC coverage and Phase 2 evaluation |
| **P1** | Implement Phase 1B B7 (`18_build_candidate_lists.py`) | B | ~1 hour | No Qdrant dep; can run on current 75-case sample with HGNC distractors |
| **P1** | Implement Phase 1B B8 (`19_finalize_test_cases.py`) | B | ~30 min | Pure aggregation |
| **P1** | Implement Phase 1B B9 (`20_validate_test_cases.py`) | B | ~30 min | Acceptance gate |
| P2 | Scaffold Phase 2a `src/agents/state.py` + tools (C1–C2) | C | ~half day | Develop against demo collection while corpus builds |
| P2 | Download Qwen3-8B weights to `~/rare-disease-rag/models/` | C | ~5–15 min download | Required for any agent prompt iteration |
| P2 | `pip install vllm` into pytorch-env | C | ~5 min | LLM serving; ~2 GB |
| P3 | Add Qdrant payload index on `mesh_terms` | A | ~30 min | Currently unindexed; needed for Critic agent's MeSH-filtered queries |

---

## 9. Risks & mitigations (updated)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| S3 sync fails mid-download (network, host sleep) | Medium | High | Running under `nohup`; sync is resumable (rerun picks up where it left off) |
| Filter retention falls outside [100K, 600K] band on full corpus | Low | High | Run `--strict` only after first inspection; otherwise process partial output to validate |
| Embedding OOM on long inputs | Low | Medium | Tokenizer enforces 512-token chunks; embedder receives uniform-length tensors |
| Qdrant index corruption from forced kill | Low | High | Use `docker compose down` not `kill`; HNSW is incrementally consistent on graceful shutdown |
| Disk fills mid-build | **Very low** (verified 870 GB Linux + 1.2 TB Windows free) | High | Monitor with `du -sh /mnt/c/pmc_workspace/`; intermediates can be deleted after each pipeline stage |
| `pytorch-env` torch nightly updated by user's other ML work | Low | Medium | `pyproject.toml` records exact versions; `pip install -r requirements.lock.txt` to re-pin |

---

## 10. Citation & where things live

- Source: <https://github.com/Jangulo7/geno_agent>
- Master plan (full spec, Phases 1A/1B/2): [`MASTER_PROJECT_v2.1.md`](../MASTER_PROJECT_v2.1.md)
- Demo report: [`reports/visual_report.html`](visual_report.html) · [`reports/technical_report.md`](technical_report.md)
- Previous progress snapshot (v1): [`reports/progress_report_09052026.html`](progress_report_09052026.html)
- Pipeline orchestrator (demo): [`scripts/demo/run_pipeline.sh`](../scripts/demo/run_pipeline.sh)
- Production download wrapper: [`scripts/corpus/01_download_pmc_oa.sh`](../scripts/corpus/01_download_pmc_oa.sh)
- Acquisition manifest: [`data/MANIFEST.tsv`](../data/MANIFEST.tsv)

---

*Snapshot taken 2026-05-09 21:00 local. Next regeneration recommended after the production corpus build completes (estimated 2026-05-14 — 2026-05-18) so the report reflects the populated Qdrant index and unblocks Phase 1B step [13].*
