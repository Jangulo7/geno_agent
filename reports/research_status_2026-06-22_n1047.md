# Research Status Report — geno_agent (n = 1,047 Q1 paper)

**Date:** 2026-06-22 · **Last updated:** 2026-06-27 (post-merge of PRs #42/#43)
**Scope:** Doctoral first paper (Universidad Europea, Madrid) — *not* the n = 75 AI
master's thesis (Universidad Alfonso X). Target journal: *Genome Medicine*.
**Purpose:** Consolidated, verified status of the **n = 1,047** research; concordance
check of `MASTER_PROJECT_v2.2.md` and `README.md` against what is actually in the
repo; inventory of stale n = 75–era reports that should not be mistaken for current.

All numbers below were read directly from the on-disk result artifacts
(`data/eval_1050/`, `data/eval_1050_lopo_full/`, `reports/tables/`) on 2026-06-22,
not copied from prose.

---

## 1. Bottom line

The research is **substantially complete and internally consistent**. The full
n = 1,047 factorial, both curated baselines (Exomiser + LIRICAL), the four
deconfounding/robustness threads, RAGAS + DeepEval, leave-one-paper-out, and
multiplicity correction have all run and their artifacts are present on disk. The
manuscript Q1 draft prose is complete.

**The user's premise needs one correction:** the `README.md` is **not** a stale
n = 75 thesis document. It was already rewritten for n = 1,047 in PRs #38/#39/#40
(merged) and its headline, results table, status table, and reproducibility table
all reflect the current n = 1,047 study. The genuinely stale material is in the
`reports/` directory — a layer of n = 75 thesis-era progress reports and summaries
that still sit alongside the current ones (see §6).

**What remains** is administrative/editorial, not experimental: UE ethics letter and
co-author/advisor names. The n = 1,047 artifact-tracking gap flagged in earlier
revisions is now **closed** — the roster rankings, LOPO summaries, diagnostic
script, and archived material were committed and merged to `main` via PRs #42 and
#43 on 2026-06-27, with the 1.9 GB of raw response dumps and earlier-cohort data
deliberately gitignored (see §7).

---

## 2. Verified headline results (n = 1,047)

Source: `data/eval_1050/_results_summary.md`, `_results_stratified.md`,
`data/eval_1050_lopo_full/_lopo_full_results_cell_S.md`,
`reports/tables/supp_table_multiplicity.md`.

### Overall, all 1,047 cases (top-1 point, 95 % bootstrap CI)

| Cell | System | top-1 | top-5 | top-10 | MRR | NDCG@10 |
|---|---|---:|---:|---:|---:|---:|
| D | multi-agent + hybrid (inside baseline) | 0.460 | 0.581 | 0.628 | 0.529 | 0.542 |
| K | Exomiser HPO-only (curated baseline) | 0.691 | 0.821 | 0.859 | 0.754 | 0.775 |
| L | D + MedCPT CE-rerank | 0.698 | 0.791 | 0.814 | 0.745 | 0.756 |
| M | LIRICAL HPO-only (curated baseline) | 0.924 | 0.989 | 0.999 | 0.953 | 0.964 |
| N | RRF ensemble M + S (Thread F) | 0.775 | 0.856 | 0.903 | 0.819 | 0.834 |
| **S** | **multi-agent + CE-rerank + LEA (full system)** | **0.726** | 0.798 | 0.817 | **0.766** | 0.773 |

- **Full cohort:** S beats Exomiser on top-1 by **+0.035** (95 % CI [+0.007, +0.066],
  McNemar p = 0.0187 ★). S does **not** beat LIRICAL on the full cohort
  (−0.213) — but that gap is an annotation-overlap artifact (next point).

### Fair cohort — overlap-absent, n = 282 (the canonical headline)

The per-case `annotation_overlap` flag marks whether the source publication is cited
by `phenotype.hpoa` for the causal gene's OMIM disease. Cohort overlap rate = 73.1 %
(765 present / 282 absent). On the fair (overlap-absent) cohort:

| System | top-1 | Δ vs S | McNemar p |
|---|---:|---:|---:|
| **geno_agent S** | **0.858** | — | — |
| Exomiser K | 0.780 | −0.078 ★ | 0.0154 |
| LIRICAL M | 0.777 | −0.082 ★ | 0.0140 |

→ **geno_agent is the #1 system on the fair cohort.** LIRICAL's apparent 0.924
overall collapses to a tie with Exomiser once annotation overlap is removed —
quantifying its training-data exposure. This is the result the paper leads with.

### Robustness / deconfounding (all complete)

- **Leave-one-paper-out (full n = 1,047, `_lopo_full_results_cell_S.md`):**
  removing each case's own source publication from retrieval leaves the **fair
  cohort completely unchanged** (0.858 → 0.858, McNemar p = 1.0; 0 discordant pairs).
  Full-cohort effect is a tiny −0.015, confined to the overlap-present subset.
  Source-paper-in-retrieval leak rate is only 11.7 % overall. → geno_agent's signal
  is distributed across the literature, not parasitic on the case's own report.
- **Multiplicity correction (`supp_table_multiplicity.md`):** both primary
  fair-cohort comparisons survive **Holm** correction (adjusted p = 0.028 each);
  recency and full-cohort supportive comparisons also survive.
- **Recency stratification:** Exomiser top-1 collapses 0.847 → 0.480 on post-2020
  source papers; geno_agent's edge widens (post-2020 S vs K survives Holm,
  adjusted p = 0.00014).
- **LLM-family ablation:** LEA replayed on Qwen3-32B, Claude Sonnet 4.6, DeepSeek-V3
  converges within 2.4 pp on the fair cohort → headline robust to model family.
- **Stratum-weighted sensitivity:** +0.034 equal-weighted vs +0.035 unweighted
  (S vs K advantage invariant to category weighting).

### RAG / rationale quality (GPT-4o judge, measurement only)

- **RAGAS faithfulness:** rank-1/top-1-only sensitivity (n = 100) **0.479**; the
  conservative multi-claim full-response measure (n = 600) **0.286** (reported as a
  lower bound). Context precision 0.650.
- **DeepEval groundedness (n = 100):** **0.845** (hallucination rate 0.155).
- Both predict top-1 correctness with a 33–39 pp gap → supports a low-grounding
  clinical-triage flag.

---

## 3. Phase / deliverable status (verified against artifacts)

| Area | Status | Evidence on disk |
|---|---|---|
| Phase 1A corpus (52,777,395 chunks, Qdrant `geno_agent_pmc_oa_v1`) | ✅ Complete | manuscript cites exact count; index outside repo |
| Phase 1B cohort v3 (n = 1,047, PPS v0.1.26, seed 42, 250+300+250+247) | ✅ Complete | `data/test_cases_1050/test_cases.jsonl` + manifest |
| Phase 2a LangGraph 4-agent + Qwen3-8B/vLLM | ✅ Complete | `src/agents/`, `scripts/eval/start_vllm.sh` |
| Cell D / L / S / K / M / N drivers + results | ✅ Complete | `data/eval_1050/cell_*`, 1,974 files tracked |
| Annotation-overlap deconfounding (Thread D) | ✅ Complete | `_results_stratified.{md,json}`, `compute_annotation_overlap.py` |
| Recency stratification (Thread E) | ✅ Complete | `_results_recency.{md,json}`, `aggregate_recency.py` |
| RRF ensemble (Thread F, Cell N) | ✅ Complete | `cell_N_rrf_m_s/`, `build_cell_n_rrf.py` |
| Explainability contrast (Thread G) | ✅ Complete | `thread_g_rationale_stats.json`, `explainability_report.md` |
| RAGAS + DeepEval (Thread C) | ✅ Complete | `ragas_cell_S_*`, `deepeval_cell_S_n100.json` |
| Leave-one-paper-out (pilot n=100 + full n=1,047) | ✅ Complete | `data/eval_1050_lopo_full/_lopo_full_results_cell_S.md` |
| Holm / BH multiplicity correction | ✅ Complete | `reports/tables/supp_table_multiplicity.md`, `multiplicity_correction.py` |
| Stratum-weighted sensitivity | ✅ Complete | `weighted_overall.py` |
| LLM-family ablation | ✅ Complete | `cell_S_ablation_*`, `cell_S_ablation_summary.json` |
| Manuscript Q1 draft (Methods+Results+Discussion+refs+TRIPOD-LLM) | 🟢 Prose complete | `reports/manuscript_q1_draft.md` |
| UE ethics letter + co-author/advisor list | 🔴 Pending | placeholders in README & draft |
| Phase 2c CopilotKit UI | ⏳ Deferred post-paper | `frontend/` scaffold only |

---

## 4. Master plan ↔ repo concordance

`MASTER_PROJECT_v2.2.md` is **already aligned** with the n = 1,047 study — it is not
a thesis-only spec. Its §0 changelog states v2.2 "reflects the post-thesis
paper-extension phase: evaluation scaled from n=75 to n=1,047, two new baselines
(LIRICAL Cell M alongside Exomiser Cell K)…". Verified matches:

| Item | Master plan | Repo reality | Match |
|---|---|---|---|
| Cohort size | n = 1,047 (250+300+250+247) | same | ✅ |
| Phenopacket Store | v0.1.26 | `data/phenopackets/v0.1.26/` | ✅ |
| Baselines | Exomiser (K) + LIRICAL (M) | both run, 1,047 cases each | ✅ |
| MedCPT rerank, LEA (Cell S) | §11.8 / Cell S | implemented + run | ✅ |
| RAGAS, DeepEval | Threads C/G documented | run | ✅ |
| Annotation overlap, recency, LOPO | Threads D/E/H documented | run | ✅ |
| LLM-family ablation | Q1-B documented | run | ✅ |
| Ontology pins (2026) | §10 | files in `data/` | ✅ |

**Gaps in the master plan — RESOLVED 2026-06-22:**

1. ✅ **Holm / Benjamini-Hochberg multiplicity correction** — now documented in
   §11.5 (with `multiplicity_correction.py`, `weighted_overall.py`, and
   `supp_table_multiplicity`) and recorded as a §10 deviation. Previously the plan
   discussed only per-comparison McNemar p / bootstrap CIs.
2. ✅ **Cell N (RRF ensemble of M + S, Thread F)** — the executed cell roster
   (D/K/L/M/N/S) is now stated explicitly via a §11.8 disambiguation note + §10
   deviation entry. This also fixed a latent **naming collision**: §11.8 originally
   defined "Cell N" as a reranker+LLM-Planner variant that was never run.
3. Earlier drift risk flagged in older notes — manuscript citing "287k articles /
   4.2 M chunks" — was **already fixed**: the draft cites the exact 52,777,395
   chunk count. No action.

With these edits, the master plan and repo are concordant.

---

## 5. README accuracy

`README.md` is current for n = 1,047. Spot-checks all pass:

- Headline (fair-cohort top-1 0.858; +0.078 vs Exomiser; +0.082 vs LIRICAL;
  Holm-surviving; LOPO 0.858→0.858) — **matches the artifacts exactly**.
- Results table (D/K/L/M/S) and the deconfounding bullets — match.
- Status table marks paper v2/v3, robustness, manuscript states correctly.
- Reproducibility table pins (PPS v0.1.26, LIRICAL 2.4.0, Qdrant v1.14.1, etc.) — match.

Minor residual nits (optional):
- README's repo-layout block lists `eval_1050_lopo_full/` (correct — it exists) but
  the prose also references the LOPO pilot dir `data/eval_1050_lopo/`; both exist, so
  no contradiction.
- Two `[to be added]` placeholders (advisor name, contact email) remain — expected
  pre-submission.

**Conclusion:** no n = 75/n = 1,047 mismatch in the README itself. If a stale README
was seen, it was likely the GitHub web view on an older commit or a cached copy.

---

## 6. Stale n = 75 reports still in `reports/` (the real cleanup target)

> **Done (2026-06-22):** the 27 files below were moved to
> `reports/_archive_n75/` (tracked files via `git mv`; the two untracked
> `progress_report_15052026_end_of_day.*` via plain `mv`). All inbound links in
> `README.md` and `MASTER_PROJECT_v2.2.md` were repointed to the archive path.

These do **not** mention n = 1,047 and are thesis-era or early-pipeline artifacts.
They are kept for the audit trail but subordinated so the current paper material is
not diluted:

**Thesis-era / superseded (archived → `reports/_archive_n75/`):**
- `thesis_final_report.md` (+ `.html`) — n = 75 final report
- `research_summary_15052026.md`, `research_summary_15052026_technical.md` — n = 75
- `progress_report_09052026{,_v2,_v3}.md`, `progress_report_11052026.md`,
  `progress_report_12052026_embed_done.md`, `progress_report_13052026_*.md`,
  `progress_report_14052026_llm_planner_results.md`,
  `progress_report_15052026_{end_of_day,llm_critic_results}.md` — daily logs, n = 75
- `paper_extension_plan.md` (v1, n = 460 superseded by v2/v3)
- `technical_report.md`, `validation_results_2026-05-13.md` — early pipeline
- `agent_architecture.md`, `methodology_test_case_selection.md` — version-agnostic;
  verify before archiving (architecture doc may still be cited).

**Current n = 1,047 paper material (keep, authoritative):**
- `methodology.md` — consolidated authoritative methodology
- `paper_extension_plan_v2.md`, `paper_extension_plan_v3.md` — execution plans
- `paper_extension_results.md` (+ `.html`) — v2 final results
- `manuscript_q1_draft.md`, `manuscript_methods_draft.md` (+ `_apa` variants)
- `explainability_report.md`, `deeprare_comparability_analysis.md`,
  `tripod_llm_compliance.md`, `wallclock_cost_table.md`
- `expert_review_2026-06-10.md` — most recent review
- `reports/tables/supp_table_multiplicity.md` — multiplicity supplement
- **this file** — `research_status_2026-06-22_n1047.md`

**Local-only (deliberately NOT tracked):**
- `cover_letter_genome_medicine.md` — the *Genome Medicine* submission cover letter.
  It carries personal contact details (name, affiliation, email, phone), so it is
  gitignored and kept only as a local working copy. It was briefly tracked (committed
  in PR #43) and was untracked again on 2026-06-27; the bytes remain in git history
  on the private repo (see §7 for the optional history-scrub note).

> ✅ **Resolved (2026-06-27):** the two previously-untracked thesis-era reports
> (`progress_report_15052026_end_of_day.{md,html}`) are now committed under
> `reports/_archive_n75/` (merged via PR #42). Nothing is left dangling.

---

## 7. Git hygiene — RESOLVED (2026-06-27)

The artifact-tracking gap is closed. The working tree is **clean** and `main` carries
a deterministic, intentional set of files. Two PRs landed on 2026-06-27:

- **PR #42** (`docs/archive-thesis-reports`) — archived the n = 75 reports to
  `reports/_archive_n75/`, added this status report, and patched the master plan
  (multiplicity correction + Cell N roster).
- **PR #43** (`chore/track-eval-roster`) — committed the n = 1,047 roster and
  housekeeping, with an explicit gitignore policy.

**Now tracked (committed):**
- `data/eval_1050/cell_{D,K,L,M,S}/` per-case ranking JSONs (mirroring the already-
  tracked `cell_N`) + `data/eval_1050_lopo/` summaries
- `scripts/eval/rerank_diagnostic.py`
- `demos/_archive/streamlit_thesis_presentation_v1_2026-05-24.py`

**Deliberately gitignored (heavy/derived/private — outside git by policy):**
- `data/eval_1050/cell_{S,L}_responses/` — 1.9 GB raw LLM response dumps
  (regenerable from the committed rankings)
- `data/eval_1050/*_backup_*/` — pre-v2 aggregation snapshots
- `data/eval/cell_*/`, `data/eval_500/`, `data/test_cases/` — earlier-cohort
  (n = 75 / n = 500) artifacts, superseded by n = 1,047
- `*Zone.Identifier` — Windows mark-of-the-web sidecars (one stray file removed)
- `reports/cover_letter_genome_medicine.md` — private submission letter (local only)

> **Optional history scrub.** `cover_letter_genome_medicine.md` was committed in
> PR #43 before being untracked, so its bytes (incl. personal contact details)
> persist in `main`'s history. The repo is **private**, so exposure is contained.
> If a full purge is wanted (e.g. before any future public release), rewrite history
> with `git filter-repo --path reports/cover_letter_genome_medicine.md --invert-paths`
> and force-push — a separate, coordinated operation, not done here.

---

## 8. Remaining work to submission

| # | Item | Type | Owner action |
|---|---|---|---|
| 1 | UE ethics/IRB exemption letter | Admin | obtain; template at `ue_irb_exemption_request_template.md` |
| 2 | Co-author + advisor names + contact email (README, draft, cover letter) | Admin | fill placeholders (needs author input) |
| 3 | ✅ Patch master plan §11.5/§10/§11.8 with multiplicity correction + Cell N roster | Doc | **DONE 2026-06-22** |
| 4 | ✅ Archive stale n = 75 reports → `reports/_archive_n75/` | Cleanup | **DONE** — merged via PR #42 (2026-06-27) |
| 5 | ✅ Commit/ignore the untracked n = 1,047 artifacts consistently | Git | **DONE** — merged via PR #43 (2026-06-27); roster tracked, heavy/older data + private docs gitignored |
| 6 | ✅ Remove private cover letter from repo (local-only) | Privacy | **DONE 2026-06-27** — untracked + gitignored; history-scrub optional (§7) |
| 7 | Final manuscript pass (figures, ref formatting, journal template) | Editorial | per the (local) cover-letter checklist |

No further *experiments* are required for the primary submission. Optional
strengtheners noted in the v3 plan (DeepRare head-to-head; Qwen3-32B AWQ ablation)
remain explicitly deferred.

---

*Prepared from on-disk artifacts in `data/eval_1050*/`, `reports/tables/`, and git
state as of 2026-06-22; §1/§6/§7/§8 revised 2026-06-27 to reflect the merge of PRs
#42/#43 and the removal of the private cover letter. Every metric in §2 was read from
result files, not prose.*
