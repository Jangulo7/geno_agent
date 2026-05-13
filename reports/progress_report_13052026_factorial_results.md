# geno_agent — §11.5 Factorial Results — 2026-05-13

**Author:** Johanna Angulo
**Branch:** `phase2d/factorial-2x2`
**Status:** §11.5 2×2 factorial complete on 75 Phase 1B test cases. Cell E (Exomiser baseline) deferred.

---

## Headline result

The multi-agent + hybrid-retrieval combination (Cell D) **dominates** both single-factor variants.

| Cell | Architecture × Retrieval | Top-1 | Top-5 | Top-10 | MRR | NDCG@10 |
|------|--------------------------|------:|------:|-------:|----:|--------:|
| A | single-agent · dense | 0.053 | 0.147 | 0.187 | 0.126 | 0.114 |
| B | single-agent · hybrid | 0.173 | 0.240 | 0.307 | 0.229 | 0.227 |
| C | multi-agent · dense | 0.133 | 0.187 | 0.293 | 0.194 | 0.193 |
| **D** | **multi-agent · hybrid** | **0.627** | **0.693** | **0.733** | **0.670** | **0.678** |

(All metrics with 1000-resample paired bootstrap 95 % CI in `_results_summary.md`.)

## Interpretation

The factorial isolates two contributions:

1. **Hybrid retrieval over dense-only** (A → B and C → D, holding architecture constant):
   - A → B: +12.0 pp top-1 (5.3 % → 17.3 %)
   - C → D: **+49.4 pp top-1** (13.3 % → 62.7 %)

2. **Multi-agent over single-agent** (A → C and B → D, holding retrieval constant):
   - A → C: +8.0 pp top-1 (5.3 % → 13.3 %)
   - B → D: **+45.4 pp top-1** (17.3 % → 62.7 %)

The dramatic gap between the "isolated" effect (A→B, A→C: ~10 pp each) and the "in-combination" effect (B→D, C→D: ~45-50 pp each) is the **synergistic interaction**: the multi-agent self-correction loop and the BM25 sparse vector channel each unlock value that the other depends on. Neither factor alone explains the full system's performance.

## By MONDO category

| Category | n | Cell A | Cell B | Cell C | Cell D |
|---|--:|------:|------:|------:|------:|
| neurological | 18 | 0.000 | 0.222 | 0.111 | **0.778** |
| developmental | 19 | 0.105 | 0.210 | 0.316 | **0.737** |
| metabolic | 19 | 0.000 | 0.158 | 0.105 | **0.526** |
| immunological | 19 | 0.105 | 0.105 | 0.000 | **0.474** |

Cell D works best on neurological + developmental (gene-disease associations are typically well-described in PMC). Hardest category is immunological — disease-protein names overlap noisily across many genes (immunology vocabulary like *CD19*, *CD20*, *TNF* recurs across cases that aren't about those genes).

## Why this matters

- All four cells are **fully deterministic** — no LLM in the loop. The numbers above are a floor on what an LLM-augmented variant (Phase 2a C7b/C7c) can achieve on top.
- The retrieval ceiling (Cell B's 17.3 % top-1) shows that pure retrieval is not enough — the multi-agent self-correction loop adds 45+ pp on top.
- The architecture-only contribution (Cell C's 13.3 %) shows that the agents alone (without BM25) cannot extract enough signal from dense-only retrieval — they need the lexical channel to find the right chunks first.

## Pipeline timing

```
Cell A (single-agent, dense):     8.5 min
Cell B (single-agent, hybrid):   10.5 min
Cell C (multi-agent, dense):     23.2 min
Cell D (multi-agent, hybrid):    28.4 min
Total:                           70.7 min wall (75 cases × 4 cells = 300 runs)
```

Zero crashes, zero errors. Multi-agent cells are 2–3× slower than single-agent because of (a) per-gene retrieval (50 queries × case) and (b) Critic loop (up to 3 iterations).

## Acceptance vs master plan §11.5

- [x] All 4 cells of the 2×2 factorial run on all Phase 1B cases (75)
- [x] Top-1 / Top-5 / Top-10 / MRR / NDCG@10 computed per cell
- [x] Paired bootstrap 95 % CI (1000 resamples) per cell per metric
- [x] LaTeX-ready table emitted (`_results_summary.md`)
- [x] Per-MONDO-category breakdown
- [ ] **Cell E (Exomiser baseline)** — deferred. Requires Java + Exomiser CLI + ~50 GB ClinVar/gnomAD/UK10K data. Out of scope for this PR.

## Files produced

```
data/eval/cell_A_single_dense/{case_id}.json     (75 files)
data/eval/cell_B_single_hybrid/{case_id}.json    (75)
data/eval/cell_C_multi_dense/{case_id}.json      (75)
data/eval/cell_D_multi_hybrid/{case_id}.json     (75)
data/eval/_results_summary.md                     (LaTeX-ready table)
data/eval/_results_summary.json                   (programmatic dump)
data/eval/_results_table.csv                      (overall, with CIs)
data/eval/_results_by_category.csv                (per-category, with CIs)
```

The per-case JSONs are gitignored (per repo policy — reproducible from
``run_factorial.py``). The summary tables are committed.

## Next steps

1. (Optional) Add Cell E (Exomiser) for a literature-free baseline. ~1 day of installation + run time. **Not blocking** — the 4-cell factorial already isolates the two architectural choices the thesis is testing.
2. (Optional) Add LLM-prompted Query Planner + Critic variants once vLLM is reliably warm. Same 2×2 design rerun → 16-cell super-factorial. Probably another 4–8 h of compute.
3. Decide on Phase 2b (FastAPI) and Phase 2c (CopilotKit UI) — needed if you want a deployed demo for the thesis defence; not needed for the empirical chapter.

---

*Generated by `scripts/eval/aggregate_metrics.py` from per-case outputs in `data/eval/`.*
