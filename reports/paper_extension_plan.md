# Paper Extension Plan — n=500 Validation

**Author:** Johanna Angulo Quintero
**Date:** 2026-05-16
**Branch:** `paper/n500-validation`
**Master plan:** extends `MASTER_PROJECT_v2.1.md` §11.5 / §11.8

---

## 1. Motivation

The thesis run (PR #36, n=75) established the headline result:

- **Cell S** (CE-rerank + LEA + hybrid) = **top-1 = 0.787 [0.680, 0.880]**
- **Cell K** (Exomiser HPO-only) = **top-1 = 0.773 [0.680, 0.853]**
- Δ = +1.3 pp, but bootstrap CIs heavily overlap → conservative claim is *statistical
  parity*, point-estimate ranking favours geno_agent.

For a **paper submission**, the n=75 sample is statistically modest. CIs of ±~0.10 around
top-1 ≈ 0.7 are wide enough that the "+1.3 pp" point-estimate gap could easily be sampling
noise. To upgrade the claim from "parity" to "decisive win", we need a larger sample. This
plan executes a **4-cell focused validation at n=500** — a 6.7 × increase that should tighten
CIs to roughly ±0.04 and either confirm or refute the thesis claim with statistical force.

## 2. Goal

> **Validate (or refute) the thesis claim — Cell S beats Exomiser HPO-only on top-1 — at
> n=500 with paired-bootstrap 95 % CIs, using only the cells that the n=75 factorial
> identified as load-bearing.**

Sub-goals:

1. Re-run the **4 cells that matter for the headline claim** at n=500: K (baseline),
   D (deterministic best), L (rerank), S (rerank + LEA).
2. Compute paired-bootstrap CIs at n=500. Expected CI half-width: ~0.04 vs ~0.10 at n=75.
3. Verify per-MONDO category trends (S wins on immunological, neurological; ties on
   developmental; loses on metabolic) hold with ~125 cases per category instead of ~19.
4. Produce a paper-extension report and PR.

## 3. Scope — what's IN and what's OUT

### Cells to run (4 total)

| Cell | Configuration | Purpose | Resource |
|---|---|---|---|
| **K** | Exomiser HPO-only | External baseline anchor (the gold standard) | CPU |
| **D** | multi-agent · hybrid (deterministic) | Inside-system baseline; verifies +10.7 pp rerank lift extrapolates | GPU (Qdrant) |
| **L** | D + cross-encoder rerank · hybrid | Single biggest contributor; standalone effect of rerank | GPU (CE + Qdrant) |
| **S** | rerank + LEA · hybrid | The thesis result; confirms beating K at scale | GPU (CE + Qdrant + vLLM) |

### Cells deliberately skipped (and why)

| Cell | Reason |
|---|---|
| A, B, C | Single-agent / dense baselines; main effects (retrieval +49 pp, architecture +45 pp under hybrid) well-characterised at n=75 — won't change qualitatively at scale |
| E, F, G, H, I, J | LLM augmentation cells were null/negative on top-1 at n=75 with bootstrap CIs that already include zero. Re-running at n=500 just confirms "still null" with tighter CIs. Not load-bearing for the paper claim. |
| P | D + K naive ensemble; plateaus at K alone. Extracted lesson: rank-fusion cannot exploit complementarity. Paper text can cite n=75 result. |
| Q | LEA · dense alone; catastrophic regression confirmed at n=75 (top-1 = 0.213). Not informative to repeat. |
| R | LEA · hybrid alone; marginal lift (+1.3 pp at n=75). Cited as ablation; not re-run at scale. |

The 4-cell scope reduces work from 16 × 500 = 8 000 evaluations to 4 × 500 = 2 000
evaluations, a 4 × reduction, while preserving the entire thesis-relevant claim chain.

## 4. Methodology

### 4.1 Test case generation

A new test set will be drawn from the same Phenopacket Store snapshot:

| Parameter | n=75 (thesis) | n=500 (paper) |
|---|---|---|
| Source | Phenopacket Store v0.1.19 | same |
| HPO ontology | hp.obo v2026-02-16 | same |
| MONDO ontology | v2026-03-03 | same |
| HGNC snapshot | 2026-04-07 | same |
| Stratification | 19+19+19+18 | **125+125+125+125** |
| `SAMPLE_TARGET_SIZE` | 75 | **500** |
| `RANDOM_SEED` | 42 | **4242** (different seed → different sample) |
| Output | `data/test_cases/test_cases.jsonl` | `data/test_cases_500/test_cases.jsonl` |
| Eligible pool | 2 971 | same (already computed in stages 1-3) |

**Why a different seed.** Using `seed=42` would produce a strict superset of the 75 thesis
cases plus 425 new ones, but per-case paired statistics across the two samples would still
be confounded. A fresh seed (4242) gives an **independent random sample** — methodologically
cleaner for replication / validation framing.

The Phase 1B pipeline (Stages 4-6) accepts `SAMPLE_TARGET_SIZE` and `RANDOM_SEED` as env
vars; only Stage 4 (sampling), Stage 5 (PMC validation), and Stage 6 (distractor draw) need
to re-run. Stages 1-3 are reused from the n=75 run.

PMC coverage validation expectation: at n=75 we had 100 % first-try pass rate. At n=500
with fresh sampling, expect 95-98 % first-try; 10-25 cases may need replacement.

### 4.2 Evaluation infrastructure

All cells share the same infrastructure as the n=75 thesis run:

- **Qdrant index** `geno_agent_pmc_oa_v1` (52.78 M chunks, unchanged)
- **vLLM serving Qwen3-8B** at `localhost:8001`, `--max-model-len 32768`
- **MedCPT-Cross-Encoder** loaded fresh per cell (cached locally after first download)
- **Exomiser CLI 14.0.2** with phenotype-only data (already in place)
- **Determinism**: `PYTHONHASHSEED=42` (eval seed unchanged), bootstrap seed=42

### 4.3 Output isolation

To preserve the n=75 thesis results untouched, all paper-extension outputs go to a separate
directory tree:

```
data/test_cases_500/                                      # new test cases
data/eval_500/cell_K_exomiser_hpo_only/                  # new cell results
data/eval_500/cell_D_multi_hybrid/
data/eval_500/cell_L_rerank_inside_d/
data/eval_500/cell_S_rerank_inside_plus_lea/
data/eval_500/_results_summary.{md,json}                 # new aggregate
```

This avoids any risk of overwriting the n=75 thesis evaluation artefacts.

### 4.4 Time and resource budget

Per-cell time at n=500 (extrapolated from n=75 timings; per-case wall ≈ unchanged):

| Cell | s/case (n=75) | n=500 wall | Resource |
|---|---|---|---|
| K | ~9 s | ~1.3 h | CPU (parallel with GPU cells) |
| D | ~30 s | ~4.2 h | GPU (Qdrant + deterministic) |
| L | ~21 s | ~2.9 h | GPU (CE + Qdrant) |
| S | ~28 s | ~3.9 h | GPU (CE + vLLM) |

**Sequencing:**

```
T+0:00     Generate test_cases_500.jsonl                           (~30 min)
T+0:30     Launch Cell K (CPU) || start Cell D (GPU)               parallel
T+1:50     Cell K done; Cell D continues
T+4:42     Cell D done → start Cell L
T+7:36     Cell L done → start Cell S
T+11:30    Cell S done
T+11:30    Run aggregator + bootstrap CIs                          (~15 min)
T+11:45    Generate per-MONDO breakdown, side-by-side n=75 vs n=500 (~15 min)
T+12:00    Update reports                                            (~2 h)
T+14:00    Commit + open PR
```

**Total wall time: ~14 hours (overnight, single working day).**
**Active human attention: ~2-4 hours** (kick-off + monitoring + report writing).

## 5. Acceptance criteria

The paper extension is **successful** if all of the following are true:

- [ ] `data/test_cases_500/test_cases.jsonl` produced with 500 cases, 5-gate validation passed
- [ ] All 4 cells produce 500/500 case JSONs (no unrecovered errors)
- [ ] `data/eval_500/_results_summary.json` includes K, D, L, S with 1 000-resample
      bootstrap CIs
- [ ] Per-MONDO category breakdown (K vs S) regenerated at ~125 cases/category
- [ ] Cell S top-1 95% CI **does not include** Cell K top-1 (the strong claim) **OR**
      The paper writes "statistical parity confirmed at n=500" honestly if CIs still
      overlap
- [ ] Paper-extension report (`reports/paper_extension_results.md` + `.html`) drafted
      with side-by-side n=75 vs n=500 comparison
- [ ] PR opened against `main` (or against the merged thesis PR base)

## 6. Risk register and mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| n=500 sampling produces fewer than 500 PMC-validated cases | medium | Stage 5 has automatic replacement logic (drew 75/75 first try at n=75). At n=500 we expect 10-25 replacements; pipeline handles up to 50 % attrition before failing. |
| GPU contention if vLLM or Qdrant restart needed mid-run | low | Established the start-vLLM workflow this session; auto-launch monitor pattern works. Dockerised Qdrant restart is sub-minute. |
| Cell S still ties K (CIs overlap at n=500) | medium | This is the actual hypothesis test. If CIs overlap at n=500, the honest claim is "statistical parity" — *still a meaningful contribution* (literature-RAG with no curation matches a curated-DB baseline). Frame the paper accordingly. |
| Cell S loses to K at n=500 (effect was sampling artifact) | low | Per-MONDO breakdown showing 3-of-4 categorical wins at n=75 makes overall regression unlikely. If it happens, paper becomes about the categorical complementarity rather than the overall win. |
| Per-case wall time grows due to Qdrant index pressure at scale | low | Qdrant has handled 52.7 M points cleanly; 500 vs 75 query batches is well within capacity. |

## 7. Deliverables

After execution:

1. **`data/test_cases_500/`** — new test case set with manifest + sha256
2. **`data/eval_500/`** — per-case JSONs for K, D, L, S
3. **`data/eval_500/_results_summary.{md,json,csv}`** — aggregator output
4. **`reports/paper_extension_results.md`** — paper-style extension report with:
   - Side-by-side n=75 vs n=500 comparison table
   - Updated bootstrap CIs
   - Per-MONDO breakdown at scale
   - Discussion of any divergence between scales
5. **`reports/paper_extension_results.html`** — visual variant (white background)
6. **PR** `paper/n500-validation` → `main` (after thesis PR #36 merges)

## 8. Plan execution checklist

- [ ] **Step 1:** Branch `paper/n500-validation` created (already done)
- [ ] **Step 2:** Add `--test-cases` flag to `run_cell_k.py` and `rerank_inside_d.py`
- [ ] **Step 3:** Generate `test_cases_500.jsonl` via Phase 1B Stages 4-6 with
      `SAMPLE_TARGET_SIZE=500 RANDOM_SEED=4242`
- [ ] **Step 4:** Validate the new test set (5-gate validation)
- [ ] **Step 5:** Launch Cell K (CPU, parallel) + chained tmux for D → L → S
- [ ] **Step 6:** Set up monitor for "all 4 cells done" event
- [ ] **Step 7:** Aggregate + per-MONDO breakdown
- [ ] **Step 8:** Write paper extension report (md + html)
- [ ] **Step 9:** Commit + push + open PR

The plan is now in execution. Subsequent commits on this branch implement the steps above.
