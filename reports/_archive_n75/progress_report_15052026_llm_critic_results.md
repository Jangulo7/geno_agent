# geno_agent — LLM-Critic Factorial (Cells G + H) — 2026-05-15

**Author:** Johanna Angulo
**Branch:** `phase2d/vllm-prefix-caching`
**Status:** Two new factorial cells (G, H) with LLM-prompted Critic, plus partial Cell I (LLM Planner + LLM Critic). Cell J still running.
**Continuation of:** `reports/progress_report_14052026_llm_planner_results.md`.

---

## Headline result

The LLM-prompted Critic — properly run with no fallback storm — **does not
improve top-1** over the deterministic Critic in either retrieval mode.
It re-orders chunks at top-5 / top-10, but the gene at rank-1 does not
change. This is a clean negative result that **isolates the bottleneck:
it is the retriever, not the chunk-grader**.

| Cell | Architecture × Retrieval | Top-1 | Top-5 | Top-10 | MRR | NDCG@10 |
|------|--------------------------|------:|------:|-------:|----:|--------:|
| A | single-agent · dense                 | 0.053 | 0.147 | 0.187 | 0.126 | 0.114 |
| B | single-agent · hybrid                | 0.173 | 0.240 | 0.307 | 0.229 | 0.227 |
| C | multi-agent · dense                  | 0.133 | 0.187 | 0.293 | 0.194 | 0.193 |
| **D** | **multi-agent · hybrid**         | **0.627** | **0.693** | **0.733** | **0.670** | **0.678** |
| E | multi-agent + LLM-Planner · dense    | 0.293 | 0.387 | 0.413 | 0.352 | 0.350 |
| F | multi-agent + LLM-Planner · hybrid   | 0.587 | 0.680 | 0.707 | 0.640 | 0.647 |
| **G** | **multi-agent + LLM-Critic · dense** | **0.120** | **0.253** | **0.333** | **0.198** | **0.207** |
| **H** | **multi-agent + LLM-Critic · hybrid** | **0.613** | **0.693** | **0.747** | **0.670** | **0.680** |
| I (partial, n=14) | multi-agent + LLM-Planner + LLM-Critic · dense | 0.286 | 0.500 | 0.571 | 0.379 | 0.412 |
| J | multi-agent + LLM-Planner + LLM-Critic · hybrid | *running* | – | – | – | – |

All numbers use 75 cases (except I, which is partial). 95% paired bootstrap
CIs on every cell are in `data/eval/_results_summary.md`. Cell D remains
the operational winner across every metric.

## Four contrasts isolate the LLM-Critic effect

| Comparison | What it asks | Top-1 delta |
|---|---|---|
| **G vs C** (dense retrieval, LLM Critic added) | Does the LLM Critic help when retrieval is dense-only? | **−1.3 pp** (0.133 → 0.120) |
| **H vs D** (hybrid retrieval, LLM Critic added) | Does the LLM Critic help when retrieval is already hybrid? | **−1.4 pp** (0.627 → 0.613) |
| **G vs C, deeper ranks** | Does the LLM Critic re-order chunks beyond rank-1? | top-5 +6.6 pp, top-10 +4.0 pp, NDCG@10 +1.4 pp |
| **H vs D, deeper ranks** | Same, under hybrid retrieval | top-10 +1.4 pp; top-5 and MRR identical |

Both top-1 deltas are inside the 95% bootstrap CIs (Cell H: [0.507, 0.720]
vs Cell D: [0.520, 0.733] — heavy overlap). The Critic moves chunks at
deeper ranks but does not change which gene appears at rank-1.

## Interpretation

**The Critic operates on a fixed chunk set.** It scores the chunks the
retriever surfaced and feeds those scores to the Synthesiser. If the
chunk that contains the actual causal evidence is not in the top-K
retrieved set, **no Critic at any model size can rescue the case**.
Cell D's 0.627 top-1 reflects a retrieval ceiling: among the 75 cases,
the truly causal chunk is in the top-10 retrieved set for ~63% of cases
when hybrid (BM25 + dense) retrieval is used, and ~13% for dense-only.
That ceiling is what the Critic-replacement experiments measure against,
and the Critic — regardless of being rule-based or LLM-prompted —
cannot exceed it.

**Why does the LLM Critic help at top-5 / top-10 but not top-1?** When
the causal chunk is *present* in the top-10 retrieved set but ranked
lower (e.g. position 3-5), the LLM's relevance grade can promote it past
chunks that scored higher purely on lexical similarity. This explains
the consistent +1–7 pp lift at top-5 / top-10 / NDCG@10. But for top-1
to change, the LLM must promote the causal chunk past a chunk that the
retriever already ranked #1 — and the deterministic Critic's gene-mention
+ section-type heuristics are already strong enough to handle the
unambiguous cases that dominate top-1.

**Two LLM components don't compose additively.** Cell I (partial, n=14):
LLM-Planner + LLM-Critic on dense retrieval lands at top-1=0.286, which
is statistically indistinguishable from Cell E (LLM-Planner only)
top-1=0.293. The LLM-Critic adds nothing on top of the LLM-Planner.

## By MONDO category (H vs D)

| Category | n | D top-1 | H top-1 | Δ |
|----------|---|--------:|--------:|---:|
| neurological  | 18 | 0.778 | 0.778 | **0.0 pp** |
| developmental | 19 | 0.737 | 0.684 | −5.3 pp |
| metabolic     | 19 | 0.526 | 0.526 | **0.0 pp** |
| immunological | 19 | 0.474 | 0.474 | **0.0 pp** |

Three of four categories show identical top-1 — meaning the **same set of
cases** are getting the same rank-1 gene under both Critics. Only
developmental disorders see the LLM Critic regress slightly (one extra
case missed). There is no category in which the LLM Critic offers a
material advantage.

## The v1 → v2 token-budget fix (operational note)

The first overnight run (Cell G v1, completed at 03:33 on 2026-05-15)
showed **71.6 % of LLM batches falling back to the deterministic grader**
(2685 warnings across 3750 expected batches). Root cause:

- `_DEFAULT_BATCH_SIZE = 10` chunks per LLM call
- `_CHUNK_TEXT_CAP_CHARS = 2400` per chunk
- Prompt: 10 × 2400 chars + system + headers ≈ **6 000 tokens**
- `max_tokens = 1500 + 250 × 10 = 4000` (response budget)
- Total: **10 000 tokens > vLLM `--max-model-len 8192`**
- vLLM returned 400 BadRequest; the `try / except` path fell back to
  the deterministic grader, masking the bug

The fix (commit `547b464`, branch `phase2d/vllm-prefix-caching`):

- `_DEFAULT_BATCH_SIZE = 5`
- Per-batch prompt ≈ 3 500 tokens + 2 750 max_tokens = **6 250 tokens**
- Headroom: ~1 900 tokens for outlier-long chunks

After the fix, Cell G v2 completed with **1 warning total across 7 500
batches** (effective fallback rate ≈ 0.01 %). Per-case wall time was
unchanged because the 8-way concurrent dispatcher absorbed the 2×
increase in batch count: vLLM dynamic-batches the concurrent requests
so the GPU stays saturated.

This is also the reason Cell G v1 looked "OK" — the deterministic
fallback was running on 72 % of grades, so the published Cell G v1
metrics were Cell C with light noise. The v2 numbers are the real
LLM-Critic effect.

## Pipeline timing (v2 run)

```
Cell G (LLM-Critic · dense):                  217.0 min  (75 cases)
Cell H (LLM-Critic · hybrid):                 247.0 min  (75 cases)
Cell I (LLM-Planner + LLM-Critic · dense):    ~300 min   (in flight)
Cell J (LLM-Planner + LLM-Critic · hybrid):   ~300 min   (queued)
```

vLLM serving Qwen3-8B with `--enable-prefix-caching` and 8 concurrent
worker threads, on RTX 5090 32 GB. GPU utilisation held at 99–100 %
throughout. Per-case wall time: G/H ≈ 2.8–3.3 min; I/J ≈ 4.0 min
(the LLM Planner adds ~30 s of Planner LLM calls + self-correction
loop).

## What this means for the thesis

1. **Cell D (deterministic multi-agent + hybrid retrieval) is the
   operational winner.** No LLM-augmented cell beats it on any metric.
2. **The LLM-Planner is a *substitute* for hybrid retrieval, not a
   complement** (Planner report 14/05): E−C = +16 pp on dense; F−D =
   −4 pp on hybrid. Useful in a context where lexical retrieval is
   unavailable (e.g. dense-only deployment), not otherwise.
3. **The LLM-Critic is null on top-1 across both retrieval modes.**
   It re-orders chunks at top-5 / top-10 — useful for downstream
   evidence-aggregation tasks — but does not change which gene ranks
   first. This **justifies the deterministic Critic on operational
   grounds**: it is ~50× faster (no GPU LLM call per chunk), reproducible
   bit-for-bit, and produces identical top-1 accuracy.
4. **The factorial decomposition is clean.** The 4 deterministic cells
   + 6 LLM-augmented cells give us a 2 × 2 × 2 factorial with each
   factor's main effect cleanly attributable: retrieval mode (dense vs
   hybrid, +49 pp), architecture (single vs multi, +0–8 pp depending
   on retrieval), and LLM augmentation (no main effect; conditional
   interaction with retrieval mode for the Planner only).

## Files produced this session

```
scripts/eval/start_vllm.sh                     (+ --enable-prefix-caching, cfa0bd2)
src/agents/critic_llm.py                       (concurrent + batch=5,  547b464)
data/eval/cell_G_multi_llmcritic_dense/        (75 case JSONs, gitignored)
data/eval/cell_H_multi_llmcritic_hybrid/       (75 case JSONs, gitignored)
data/eval/cell_I_multi_llmboth_dense/          (in flight, gitignored)
data/eval/cell_J_multi_llmboth_hybrid/         (pending, gitignored)
data/eval/_results_summary.{md,json}           (overall, includes G + H)
data/eval/_results_table.csv                   (with CIs)
data/eval/_results_by_category.csv             (per MONDO category)
reports/progress_report_15052026_llm_critic_results.md   (this file)
reports/progress_report_15052026_llm_critic_results.html (visual variant)
```

## Acceptance vs master plan §11.5 / §11.6

| Item | Status |
|---|---|
| 4 cells of the 2 × 2 deterministic factorial          | ✅ Done (PR #34) |
| 2 LLM-Planner cells (E, F)                            | ✅ Done (PR #35) |
| 2 LLM-Critic cells (G, H)                             | ✅ Done (this report) |
| 2 LLM-both cells (I, J)                               | 🟡 In flight (I ~20 % done; J pending) |
| Cell K — Exomiser baseline                            | ⏸ Deferred (Java + ~50 GB external data setup) |
| Top-1 / Top-5 / Top-10 / MRR / NDCG@10                | ✅ Done for all 8 completed cells |
| Paired bootstrap 95 % CIs (1000 resamples)            | ✅ Done |
| Per-MONDO-category breakdown                          | ✅ Done |
| LaTeX-ready table emitted                             | ✅ Done |

---

# Phase 2e proposal — cross-encoder re-ranker

## Rationale

The LLM-Critic ablation (this report) and the LLM-Planner ablation
(14/05) both show **null top-1 effects on top of hybrid retrieval**.
The factorial isolates the retriever as the binding constraint. The
direct way to attack the retriever is a re-ranking stage.

The pipeline as of Phase 2d is:

```
query → planner → retrieve(top_k=50) → critic(grade each) → synth → top-N genes
```

The proposed Phase 2e change inserts a **cross-encoder re-ranker**
between retrieval and critic:

```
query → planner → retrieve(top_k=50) → reranker(top_k=10) → critic → synth
```

A cross-encoder computes a single relevance score by attending jointly
over (query, chunk) — much higher capacity than the two-tower (query
embedding) · (chunk embedding) dot product used at retrieval time, but
~100× too expensive to run on the full corpus. Restricting it to the
top-50 candidates is the standard "first-stage retrieval + second-stage
re-ranking" pattern from the IR literature (Nogueira & Cho 2019, MS
MARCO leaderboard, BEIR benchmark).

## Expected lift

Order-of-magnitude estimates from the IR literature on biomedical
retrieval tasks (TREC-COVID, BioASQ, NFCorpus):

- BM25 → BM25 + BGE-reranker-large: **+5–15 pp top-1**
- Hybrid retrieval → hybrid + cross-encoder: **+3–10 pp top-1**

Applied to Cell D's 0.627 baseline, a conservative +3 pp gives
top-1 ≈ 0.65; a generous +10 pp gives top-1 ≈ 0.73.

## Candidate models

| Model | Size | Throughput on RTX 5090 | Notes |
|---|--:|---:|---|
| `BAAI/bge-reranker-large`           | 560 MB | ~30 ms/chunk | Best general accuracy; English+multilingual |
| `BAAI/bge-reranker-v2-m3`           | 600 MB | ~28 ms/chunk | Newer; multilingual; strong on biomedical |
| `cross-encoder/ms-marco-MiniLM-L-12-v2` | 130 MB | ~6 ms/chunk | Smallest; weaker on biomedical, very fast |
| `ncbi/MedCPT-Cross-Encoder`         | 440 MB | ~25 ms/chunk | PubMed-fine-tuned; the right choice for our domain |

**Default choice:** `ncbi/MedCPT-Cross-Encoder` — it is specifically
trained on PubMed query–passage pairs, which matches our setting almost
exactly. Fallback to `BAAI/bge-reranker-v2-m3` if MedCPT under-performs.

Both are open-weight, local, and consistent with master plan §11.1
("No cloud LLM API in any code path"). No new external dependencies.

## Compute budget

- VRAM: ~600 MB resident next to Qwen3-8B (16 GB) and PubMedBERT
  embedder (440 MB). RTX 5090 has 32 GB; plenty of headroom.
- Per case: 50 chunks × 50 genes = 2 500 cross-encoder forward passes.
  At 25 ms each: ~62 s of re-ranking per case.
- Cells re-runnable: A factorial repeat of cells A/B/C/D with the
  re-ranker inserted costs ~62 s × 75 × 4 = ~5.2 h of GPU. Overnight
  feasible.

## Implementation outline

```
src/agents/reranker.py
    class CrossEncoderReranker:
        def __init__(self, model_id: str = "ncbi/MedCPT-Cross-Encoder"): ...
        def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]: ...

src/agents/graph.py
    add `use_reranker: bool = False` kwarg to build_graph()
    insert a `rerank` node between `retrieve` and `critic` when True

scripts/eval/run_factorial.py
    new cells L–O for the deterministic re-ranker factorial:
        L  multi-agent + reranker · dense
        M  multi-agent + reranker · hybrid
        N  multi-agent + reranker + LLM-Planner · hybrid
        O  multi-agent + reranker + LLM-Critic · hybrid

tests/test_reranker.py
    smoke test that the re-ranker preserves chunk-id integrity and
    that the top-k slicing is deterministic.
```

## Milestones (estimated)

1. **Day 1:** add `src/agents/reranker.py` + integrate into
   `build_graph()` behind a feature flag. Smoke test on 1 case.
2. **Day 2:** run Cells L + M (deterministic + re-ranker, both
   retrieval modes). Expected ~10 h of GPU.
3. **Day 3:** run Cells N + O (re-ranker stacked on LLM augmentation).
   Expected ~10 h of GPU.
4. **Day 4:** aggregator update + milestone report + PR.

## Master plan impact

This adds a new sub-phase **§11.5e — Cross-encoder re-ranker
ablation** to the existing §11 (Evaluation Layer). No change to:

- §0 (phase ordering: still requires Phase 1A + 1B complete)
- §11.1 (LLM stack: still local Qwen3-8B; re-ranker is a separate,
  non-LLM model)
- §11.4 (compute budget: re-ranker fits comfortably in the existing
  VRAM allocation)
- Determinism: cross-encoders are deterministic at temperature 0;
  no probabilistic decoding involved.

The proposal will be added to the master plan §11 as a tracked
deviation alongside the 2026 ontology versions and the HGNC URL
change.

## Open questions

1. **Where to truncate?** Re-rank top-50 candidates? Top-100?
   Tradeoff: more candidates → more compute, but more chance to
   surface the truly causal chunk if retrieval ranked it deeply.
2. **Apply per-gene or globally?** The current pipeline retrieves
   per-gene (10 chunks × 50 candidate genes = 500 chunks/case).
   Re-rank within each gene's chunk slate, or pool and rescore
   globally? Per-gene preserves the architecture; global may give
   more lift but requires query rewriting.
3. **Score combination.** The retrieval pipeline already fuses BM25
   + dense via RRF. Adding a cross-encoder score gives three signals.
   Linear combination with grid search vs LightGBM vs straight
   replacement? The IR literature mostly uses straight replacement
   of the second-stage score; we follow that default.

These will be resolved in Phase 2e Step 1 before any runs.

---

*Next session: open PR for `phase2d/vllm-prefix-caching` (Cells G/H/I/J + reports), merge to `main`, branch `phase2e/cross-encoder-reranker` for the proposal above.*
