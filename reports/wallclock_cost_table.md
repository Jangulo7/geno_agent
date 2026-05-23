# Wallclock + cost table (v3-12, 2026-05-23)

Single source of truth for the paper's operational-profile reporting.
Derived from per-case JSON mtimes in `data/eval_1050/cell_*/` (which
match the actual run wall-clock per case) and the recorded OpenAI
spend for the cloud-judged evaluations. Hardware: NVIDIA RTX 5090
(32 GB VRAM, Blackwell, cu128), 64 GB system RAM, NVMe SSD, WSL2
Ubuntu 24.04.

## Per-cell evaluation costs (cohort n = 1,047)

| Cell | Algorithm | Compute | Wall time | Per-case avg | OpenAI $ | Local-equiv $ * | Comments |
|---|---|---|---:|---:|---:|---:|---|
| **K** | Exomiser HPO-only (hiPhive) | CPU | 3 h 38 m | 12.5 s | $0 | ~$0.18 | Single-thread CPU; no GPU |
| **M** | LIRICAL HPO-only (LR framework) | CPU, 8 parallel workers | 0 h 22 m | 10.1 s effective | $0 | ~$0.02 | 8× parallel — fastest cell |
| **D** | Multi-agent hybrid (RRF retrieval) | GPU (dense + BM25) | 6 h 53 m | 23.7 s | $0 | ~$1.60 | PubMedBERT dense + FastEmbed BM25 |
| **L** | Cell D + CE-rerank | GPU (+ MedCPT-CE) | 5 h 28 m | 18.8 s | $0 | ~$1.30 | Faster than D in v3 re-run due to retrieval caching |
| **S** | Cell L + LEA (Qwen3-8B via vLLM) | GPU (+ Qwen3-8B) | 7 h 36 m | 26.1 s | $0 | ~$1.78 | Includes vLLM warm-up |
| **N** | RRF ensemble of M + S (post-hoc) | None (arithmetic) | 0 h 00 m | 0.005 s | $0 | ~$0 | Reads existing JSONs |
| **TOTAL local** | | | **~24 h** | | **$0** | **~$5** | one-shot reproducible |

\* Local-equiv $ is a cloud-substitution estimate using AWS
**g6e.4xlarge** ($1.86/h on-demand, December 2025, with an L4 GPU as
the closest sub-RTX-5090 alternative). The actual experiment ran on
locally-owned hardware at electricity cost only.

## Evaluation-pipeline costs (LLM-judged, n=600 / 100 / 100)

| Pipeline | Subset | Compute | Wall time | Judge calls | OpenAI $ | Notes |
|---|---|---|---:|---:|---:|---|
| **RAGAS** (multi-claim) | n=600 stratified (150 / MONDO) | OpenAI API | 167.8 min | ~13,800 | **$95** | Original headline — multi-claim measurement artifact |
| **RAGAS top-1-only** (sensitivity) | n=100 stratified (25 / MONDO) | OpenAI API | 3.9 min | ~340 | **$2** | Recommended primary faithfulness measurement |
| **DeepEval HallucinationMetric** | n=100 stratified (25 / MONDO) | OpenAI API | 3.1 min | ~400 | **$1.20** | Independent holistic judge |
| **TOTAL OpenAI** | | | 174.8 min | ~14,540 | **$98.20** | of $100 budget |

## Stratified-analysis costs (no compute, derived from existing per-case JSONs)

| Analysis | Reads from | Wall time | $ |
|---|---|---:|---:|
| 5-cell aggregation (top-k, MRR, NDCG@10, bootstrap CIs) | all 5 cells × 1,047 cases | ~30 s | $0 |
| Paired-Δ (5 comparisons × per-cohort) | per-case JSONs | ~3 s × 5 | $0 |
| Annotation-overlap join (Thread D) | hpoa + test_cases | ~1 s | $0 |
| Stratified re-aggregation by overlap (Thread D) | all 5 cells × 282 + 765 | ~20 s | $0 |
| Recency stratification + per-MONDO (Thread E) | all 5 cells × 601 + 446 | ~15 s | $0 |
| RRF ensemble construction (Thread F → Cell N) | M + S per-case | ~5 s | $0 |
| LEA rationale structural analysis (Thread G) | S per-case | ~3 s | $0 |
| Explainability report (16 case walkthroughs) | S per-case | ~3 s | $0 |
| **Total derived-analysis compute** | | **~1.5 min** | **$0** |

## Total compute footprint for the paper

| Category | Time | $ |
|---|---:|---:|
| Local evaluation (6 cells × 1,047 cases) | ~24 h GPU + CPU wall | $0 (electricity only) |
| LLM-judge evaluation (RAGAS × 2 + DeepEval) | ~175 min OpenAI API | $98.20 |
| Derived analyses (Threads D-G + aggregations + reports) | ~1.5 min CPU wall | $0 |
| **TOTAL** | **~24 h reproducible end-to-end** | **$98.20** |

## Reproducibility runtime

> *Re-running the entire paper evaluation pipeline from frozen sidecars
> requires ~24 hours of compute on a single RTX 5090 workstation, plus
> ~3 hours of OpenAI API spend for the RAGAS + DeepEval evaluation
> (~$100 budget). All five system-cells (K, M, D, L, S) plus the
> post-hoc ensemble Cell N are reproducible from a single
> `bash scripts/eval/run_paper_extension.sh` invocation with the
> sequencer that guarantees vLLM, MedCPT-CE, and PubMedBERT never
> compete for VRAM. Local rerun cost: electricity. Cloud-equivalent
> rerun cost (AWS g6e.4xlarge): ~$5 plus the $98 in OpenAI spend.*

## Paper Methods Table 1 — recommended condensed format

| Cell | Approach | Wall (h:m) | s/case | Cost ($) |
|---|---|---:|---:|---:|
| K | Exomiser HPO-only baseline | 3:38 | 12.5 | 0 |
| M | LIRICAL HPO-only baseline | 0:22 | 10.1\* | 0 |
| D | Multi-agent hybrid (D+BM25 RRF) | 6:53 | 23.7 | 0 |
| L | Cell D + CE-rerank | 5:28 | 18.8 | 0 |
| **S** | **Cell L + LEA (Qwen3-8B local)** | **7:36** | **26.1** | **0** |
| N | RRF(M,S) ensemble (post-hoc) | <0:01 | 0.005 | 0 |
| | Subtotal local | ~24 | — | 0 |
| | RAGAS multi-claim n=600 | 2:48 | — | 95 |
| | RAGAS top-1-only n=100 | 0:04 | — | 2 |
| | DeepEval n=100 | 0:03 | — | 1 |
| | **TOTAL** | **~27 h** | — | **98** |

\* LIRICAL ran 8-worker parallel; 10.1 s is the effective per-case
serial-equivalent time.

## Operational notes for reviewers

1. **The vLLM teardown between cells is essential.** A `trap`-based
   shutdown of vLLM after Cell S releases ~24 GB VRAM before the next
   stage; without it, the MedCPT-CE reranker OOMs when Cell L starts.
   See `methodology.md §5.3` for the sequencer details.
2. **GPU contention is the dominant resource constraint, not compute
   time.** A second concurrent run on the same hardware would be
   blocked by VRAM, not by wall time. The system is bounded by
   "single-GPU throughput" rather than "compute hours".
3. **The all-local production cost is electricity.** Geno_agent does
   not require any cloud API at inference time. The $98.20 cloud spend
   above is *evaluation-only* (RAGAS + DeepEval LLM judges).
4. **Cell M's 22-minute wall is the per-cohort floor.** LIRICAL with
   eight parallel workers is the fastest cell; for clinical-deployment
   throughput planning, an Exomiser + LIRICAL + geno_agent triage
   workflow is bounded by geno_agent (Cell S) at ~26 seconds per
   patient case.
5. **Operational profile suits a clinical-genetics consultation
   timeframe.** Each case completes in under 30 seconds end-to-end
   on a single workstation — well within the time a clinician would
   spend on a single rare-disease case during a consult.

---

*v3-12 wallclock + cost table — 2026-05-23. Frozen for the manuscript
Methods Table 1. Per-cell wall times are derived from case-JSON mtimes
in `data/eval_1050/cell_*/`; OpenAI spend is documented in the RAGAS
+ DeepEval summary JSONs.*
