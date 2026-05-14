# geno_agent — LLM-Augmented Factorial (Cells E + F) — 2026-05-14

**Author:** Johanna Angulo
**Branch:** `phase2d/factorial-llm-augmented`
**Status:** Two new factorial cells (E, F) with LLM-augmented Query Planner. LLM-Critic cells G/H/I/J deferred (compute infeasible in single session).
**Continuation of:** `reports/progress_report_13052026_factorial_results.md`.

---

## Headline result

The LLM Query Planner's contribution is **conditional on retrieval mode**:
strong gain over deterministic when retrieval is dense-only, ~neutral when
retrieval is already hybrid.

| Cell | Architecture × Retrieval | Top-1 | MRR | NDCG@10 |
|------|--------------------------|------:|----:|--------:|
| A | single-agent · dense | 0.053 | 0.126 | 0.114 |
| B | single-agent · hybrid | 0.173 | 0.229 | 0.227 |
| C | multi-agent · dense | 0.133 | 0.194 | 0.193 |
| D | multi-agent · hybrid | 0.627 | 0.670 | 0.678 |
| **E** | **multi-agent + LLM-Planner · dense** | **0.293** | **0.352** | **0.350** |
| **F** | **multi-agent + LLM-Planner · hybrid** | **0.587** | **0.640** | **0.647** |

(Full 95 % CIs in `data/eval/_results_summary.md`.)

## Two contrasts isolate the LLM-Planner effect

| Comparison | What it asks | Top-1 delta |
|---|---|---|
| **E vs C** (dense retrieval, LLM Planner added) | Does the LLM Planner help when retrieval is dense-only? | **+16.0 pp** (0.133 → 0.293) |
| **F vs D** (hybrid retrieval, LLM Planner added) | Does the LLM Planner help when retrieval is already hybrid? | **−4.0 pp** (0.627 → 0.587) |

**Interpretation:** when BM25 already provides a strong lexical anchor via the gene symbol (hybrid retrieval, Cell D), the deterministic query `"<GENE_SYMBOL> <hpo labels>"` is already near-optimal. Adding LLM expansion dilutes the BM25 anchor without offering significant new semantic signal. With dense-only retrieval, the deterministic query is much weaker (no lexical anchor at all, just semantic), so the LLM's gene-aware reformulation provides a meaningful lift.

## What this tells us for the thesis

1. **The multi-agent architecture matters most under hybrid retrieval.** Cells A/B vs C/D shows multi-agent only really helps when retrieval is hybrid (A→C: +8 pp, B→D: +45.4 pp). This was the result we already had.
2. **The LLM Planner is a *substitute* for hybrid retrieval, not a complement.** Cells E vs F: E is a hybrid-free workaround that closes some of the gap (0.293 top-1), but the proper hybrid solution (D, 0.627) is still ~2× better than LLM-Planner-over-dense (E, 0.293).
3. **In our specific architecture, the LLM Planner adds little once hybrid retrieval is present** (F ≈ D within CI overlap). The interaction effect is well-documented and ablation-clean.

## By MONDO category (Cell F vs D)

| Category | n | D (top-1) | F (top-1) | Δ |
|---|--:|---:|---:|---:|
| neurological | 18 | 0.778 | 0.667 | −11.1 pp |
| developmental | 19 | 0.737 | 0.684 | −5.3 pp |
| metabolic | 19 | 0.526 | 0.421 | −10.5 pp |
| immunological | 19 | 0.474 | 0.579 | **+10.5 pp** |

Interesting: immunological is the **only** category where the LLM Planner helps over Cell D. Hypothesis: immunology terms have noisy overlap (CD19/CD20/IL-2/etc. recurring across genes), so a deterministic gene-anchored query fails more often; LLM reformulation distinguishes the candidate gene more reliably.

## Pipeline timing

```
Cell E (LLM Planner · dense):   70.8 min
Cell F (LLM Planner · hybrid):  76.8 min
Total wall-clock:              147.6 min  (2 h 28 min, 75 cases × 2 cells = 150 runs)
```

vLLM serving Qwen3-8B on RTX 5090: ~104 tok/s sustained. Per-case time
varies from 22 sec (cached prompts, simple cases) up to 264 sec (Qwen3
self-correction loop triggered 3 iterations on a hard case).

## Why LLM-Critic cells (G/H/I/J) are deferred

The LLM Critic grades **500 chunks per case** (top-10 chunks × 50 genes). Even with batched (10 chunks/LLM call) and thinking disabled (`/no_think`), one case takes **~13 minutes** wall — entirely dominated by prompt setup and JSON generation across 50 batched calls.

Extrapolated cost for all 4 LLM-Critic cells (G/H/I/J) × 75 cases:

```
13 min/case × 75 cases × 4 cells = ~65 hours of compute
```

This exceeds single-session feasibility. Pragmatic options for follow-up work:

- **Restrict to a smaller test set** (e.g., 20-case subset) for the Critic ablation — ~17 hours, overnight feasible.
- **Use a smaller LLM** (e.g., Qwen3-4B or Llama-3.2-3B) — likely 3-5× faster, enabling the full 75-case ablation in ~13 hours.
- **Reduce retriever_top_k to 3 for Critic-only cells** — 3× fewer LLM calls, ~20 hours total. Note this breaks comparability with Cell D's top_k=10.
- **Use the vLLM `--enable-prefix-caching`** flag to reuse the system prompt across batches; can give 5-10× speedup. This was not in our startup script and is the most promising fix.

For this session, we ship the Planner ablation (E + F) which is the cleaner of the two contributions to isolate, and note Critic as future work.

## Files produced

```
scripts/eval/run_factorial.py                 (extended for cells E-J)
scripts/eval/aggregate_metrics.py              (CELLS dict updated; LLM cells admitted)
src/agents/query_planner_llm.py                (new, /no_think system prompt)
src/agents/critic_llm.py                       (new, batched grader + /no_think)
src/agents/graph.py                            (use_llm_planner / use_llm_critic args)
data/eval/cell_E_multi_llmplanner_dense/        (75 JSONs, gitignored)
data/eval/cell_F_multi_llmplanner_hybrid/       (75 JSONs, gitignored)
data/eval/_results_summary.md                   (overall table, A-F)
data/eval/_results_summary.json                 (programmatic dump)
data/eval/_results_table.csv                    (CSV with CIs)
data/eval/_results_by_category.csv              (per-category CSV)
```

## Acceptance vs master plan §11.5 / §11.6

| Item | Status |
|---|---|
| 4 cells of the 2×2 deterministic factorial | ✅ Done (PR #34 merged earlier) |
| 2 LLM-Planner cells (E, F) | ✅ Done (this report) |
| 4 LLM-Critic cells (G, H, I, J) | ⏸ Deferred (compute budget) |
| Cell K — Exomiser baseline | ⏸ Deferred (Java + ~50 GB external data setup) |
| Top-1 / Top-5 / Top-10 / MRR / NDCG@10 | ✅ Done for all 6 active cells |
| Paired bootstrap 95 % CIs (1000 resamples) | ✅ Done |
| Per-MONDO-category breakdown | ✅ Done |
| LaTeX-ready table emitted | ✅ Done |

---

*Next: commit + PR for cells E + F; consider Exomiser cell next session.*
