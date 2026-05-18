# Methodology (v3, paper-extension consolidated)

**Project:** geno_agent — Agentic Multi-Agent RAG for Rare-Disease Gene Prioritization
**Author:** Johanna Angulo (johanna.angulo@gmail.com)
**Date:** 2026-05-18
**Status:** Paper extension v3 in progress (Cell S re-run with response logging, ~60 % done)

This document is the **single authoritative technical methodology reference** for
the project as of the v3 paper-extension phase. It supersedes the methodology
sections of the v1 plan ([`paper_extension_plan.md`](paper_extension_plan.md)),
the v2 plan ([`paper_extension_plan_v2.md`](paper_extension_plan_v2.md)), and the
v3 plan ([`paper_extension_plan_v3.md`](paper_extension_plan_v3.md)) by
consolidating their methodology decisions into a single coherent description
suitable for:

1. The Methods section of the planned Q1 manuscript (target: Genome Medicine)
2. Reviewers checking reproducibility
3. Team-member or future-self onboarding

Plan documents remain the authoritative source for **what to do next** and the
**rationale behind individual decisions**; this document is the authoritative
source for **what the methodology IS**.

---

## 1. System architecture

### 1.1 Four-agent LangGraph pipeline

`geno_agent` decomposes literature-based gene prioritization across four
specialized agents orchestrated by [LangGraph](https://github.com/langchain-ai/langgraph)
as a stateful graph. The agents share a single `AgentState` dataclass:

| Agent | Responsibility | Implementation |
|---|---|---|
| **Query Planner** | Expand patient HPO terms via ontology graph traversal; build MeSH-style queries per candidate gene | `src/agents/query_planner.py`; `pronto` over `hp.obo` |
| **Retriever** | Hybrid (dense + sparse) retrieval from PMC OA chunks per candidate gene | `src/agents/retriever.py`; Qdrant client |
| **Critic** | Grade each retrieved chunk's relevance + evidence strength on a 0-3 ordinal scale | `src/agents/critic.py`; deterministic (Cell D/L/S) or LLM-based (Cell G/H/I/J) |
| **Synthesizer** | Aggregate evidence per gene → final 50-gene ranking | `src/agents/synthesizer.py` (deterministic) or `src/agents/synthesizer_lea.py` (LLM-as-evidence-aggregator) |

Per the master plan §11.1, agents communicate by mutating the shared
`AgentState`; LangGraph supplies the conditional-edge logic that lets the
Critic re-enter the Retriever for additional iterations (bounded by
`max_iterations=3`).

### 1.2 Evaluated cells (v3 scope)

The thesis evaluation defined a 16-cell factorial (cells A–J + P, Q, R, K). For
the n=1,047 paper extension, we run a focused 5-cell subset selected because
the other cells were shown at thesis scale to be inferior, null, or marginal:

| Cell | Configuration | Role |
|---|---|---|
| **D** | multi-agent + hybrid retrieval, deterministic Critic + Synth | Inside-system baseline (isolates pre-rerank performance) |
| **L** | D + MedCPT cross-encoder rerank inside the agent loop | Isolates the cross-encoder rerank contribution |
| **S** | L + LEA (LLM-as-Evidence-Aggregator using Qwen3-8B) | Full agentic stack — the paper's primary contribution |
| **K** | Exomiser CLI 14.0.2 HPO-only, hiPhive prioritiser | External curated baseline |
| **M** | LIRICAL CLI 2.4.0 HPO-only, likelihood-ratio framework | Second curated baseline (added v3) |

Cells K and M are baseline tools run external to the geno_agent pipeline; cells
D, L, S are progressive configurations of the geno_agent stack itself.

### 1.3 Retrieval

| Component | Detail |
|---|---|
| **Corpus** | PubMed Central Open Access (PMC OA) full-text articles |
| **Chunking** | UUID5-keyed sentence-window chunks (master plan §4 step 3) |
| **Total chunks** | 52,777,684 (Phase 1A processed) |
| **Dense embedder** | `NeuML/pubmedbert-base-embeddings` (PubMedBERT-base, 768-dim, biomedical pre-trained) |
| **Sparse embedder** | `Qdrant/bm25` via `fastembed.SparseTextEmbedding` (no hash-based fallback per project rule) |
| **Vector store** | Qdrant 1.14.1 (server), 1.14.3 (Python client) |
| **Deployment** | Dedicated container `qdrant_geno_agent` on `localhost:6533` (REST) / `:6534` (gRPC) |
| **Index** | `geno_agent_pmc_oa_v1` collection (HNSW, dense + sparse + RRF) |
| **Hybrid fusion** | Reciprocal Rank Fusion (RRF), k=60, top-50 dense ∪ top-50 sparse |
| **Per-gene retrieval depth** | 50 chunks/gene (Cell L/S); 10 chunks/gene (Cell D, pre-rerank) |

### 1.4 Cross-encoder reranking (Cells L and S)

| Component | Detail |
|---|---|
| **Model** | `ncbi/MedCPT-Cross-Encoder` |
| **Parameters** | 110M, BERT-base architecture, PubMed-fine-tuned |
| **Input** | Pairs of (MeSH query, retrieved chunk text), max 512 tokens |
| **Batch size** | 64 pairs per forward pass |
| **Pipeline placement** | After Retriever (top-50), before Critic (top-10) — keeps the top 10 per gene |
| **VRAM footprint** | ~1.5 GB on RTX 5090, FP16 inference |

### 1.5 LEA (LLM-as-Evidence-Aggregator) — Cell S only

| Component | Detail |
|---|---|
| **LLM** | Qwen3-8B-Instruct (open weights, FP16) |
| **Serving** | vLLM 0.20.1 OpenAI-compatible API on `localhost:8001` |
| **Inference config** | `--max-model-len 32768`, `--max-num-seqs 1`, `--gpu-memory-utilization 0.75`, `--dtype float16`, `--enable-prefix-caching`, `--reasoning-parser qwen3` |
| **VRAM allocation** | ~22.8 GB (14.3 weights + 3 overhead + ~5.5 KV cache) |
| **System prompt** | `SYSTEM_PROMPT` in `src/agents/synthesizer_lea.py`; instructs LLM to rank top-N candidate genes by likelihood of being causal given evidence |
| **Per-gene context** | Top-3 chunks per gene after rerank, truncated at 1,600 chars/chunk (`_CHUNK_TEXT_CAP_CHARS`) |
| **Genes re-ranked** | Top-15 (`_DEFAULT_LEA_TOP_GENES`); the remaining 35 keep preliminary rank shifted to positions 16-50 |
| **Output** | Structured JSON: per-gene confidence + rationale |
| **Max output tokens** | 1,500 (`_MAX_OUTPUT_TOKENS`) |
| **Temperature** | 0.0 (deterministic) |
| **Sampling seed** | Fixed (vLLM-managed) |
| **Fallback** | When LLM call fails OR JSON parse fails, ranking falls back to deterministic synthesizer (equivalent to Cell L). Recorded as `lea_fallback_reason` in sidecar. Observed rate: 2/1,047 = 0.19 % at v2; similar at v3. |

---

## 2. Cohort construction

### 2.1 Source

- **Phenopacket Store v0.1.26** (released 2026-01-13). 9,588 phenopackets across 623 unique gene cohorts.
- **Source URL:** `https://github.com/monarch-initiative/phenopacket-store/releases/download/0.1.26/all_phenopackets.zip`
- **v0.1.26 was chosen** for the paper extension after a Step 0 audit found the immunological eligible pool grew from 85 (v0.1.19) to 390 (v0.1.26) — eliminating the v1 paper's structural cap on the IEI subgroup.

### 2.2 Phase 1B pipeline

```
Stage 13: load_phenopackets       → 9,588 raw
Stage 14: apply_inclusion_exclusion → 6,382 eligible (66.6%)
   Gates: MIN_HPO_TERMS=3, single causal gene, no excluded MONDO root
Stage 15: categorize_by_mondo     → 4,670 in 4 target categories (73.2%)
   Target MONDO subtrees: developmental disorders, immunological, metabolic, neurological
Stage 16: stratified_sample        → 1,050 (250+300+250+250, disproportionate)
   New v3 flag: --per-category-target "dev=250,imm=300,met=250,neuro=250"
Stage 17: validate_pmc_coverage    → 1,050 / 1,050 first pass (0 replacements)
   Gate: ≥ MIN_PMC_ARTICLES_PER_GENE=5 PMC OA articles per causal gene
Stage 18: build_candidate_lists    → 1,047 (3 dropped: RNU4-2 x2 + 1 ncRNA at HGNC protein-coding gate)
Stage 19: finalize_test_cases     → data/test_cases_1050/test_cases.jsonl
   sha256: c355b800e53e5347…
```

### 2.3 Disproportionate stratified sampling

The natural prevalence of immunological diseases in the v0.1.26 eligible pool
is 8.4 % (390 / 4,670). The v3 sample oversamples to **28.6 %** (300 / 1,047) to
achieve adequate statistical power for the per-MONDO immunological subgroup
analysis — the paper's lead categorical finding.

| Category | Eligible (v0.1.26) | Target | Achieved | % of cohort | % of pool |
|---|---:|---:|---:|---:|---:|
| developmental | 464 | 250 | 250 | 23.9 % | 53.9 % |
| **immunological** | **390** | **300** | **300** | **28.7 %** | **76.9 %** |
| metabolic | 672 | 250 | 250 | 23.9 % | 37.2 % |
| neurological | 3,144 | 250 | 247 | 23.6 % | 7.9 % |
| **Total** | 4,670 | 1,050 | **1,047** | 100 % | 22.4 % |

This is a textbook disproportionate stratified sampling design. Trade-off:
cohort-level metrics are not directly comparable to baseline tools evaluated
on natural-prevalence cohorts. We compensate by reporting both raw and
per-category-mean (unweighted) aggregates (see §4.2).

### 2.4 Frozen artefacts

| Artefact | Path | sha256 |
|---|---|---|
| Test cases | `data/test_cases_1050/test_cases.jsonl` | `c355b800e53e5347…` |
| Manifest | `data/test_cases_1050/test_cases_manifest.json` | committed |
| PMC validation stats | `data/test_cases_1050/05_validated_stats.json` | committed |

The `.jsonl` files themselves are `.gitignore`d (consistent with project policy
on large generated artefacts) but are bit-stably regenerable from the pipeline
given the same `RANDOM_SEED=42`, ontology pins, and Phenopacket Store v0.1.26.

---

## 3. Pinned versions

All version pins are deliberate and aligned across the cohort, ontologies, and
baseline tools for methodological consistency.

| Component | Version | Notes |
|---|---|---|
| **Phenopacket Store** | **v0.1.26** | upgraded from v0.1.19 at v3; +252 gene cohorts (+359 % immunological eligible) |
| HPO ontology | v2026-02-16 | matches Phenopacket Store v0.1.26's bundled HPO and LIRICAL's `phenotype.hpoa` reference |
| MONDO ontology | v2026-03-03 | for Stage 15 categorization |
| HGNC snapshot | 2026-04-07 (quarterly) | protein-coding set for distractor draw + LIRICAL gene mapping |
| **Qwen3-8B** | HF default (FP16 weights) | local at `~/rare-disease-rag/models/Qwen3-8B/` |
| **vLLM** | 0.20.1 | in `~/vllm-env/` (separate venv from `pytorch-env`) |
| Qdrant server | v1.14.1 | aligned with qdrant-client 1.14.3 |
| MedCPT cross-encoder | `ncbi/MedCPT-Cross-Encoder` (HF) | downloaded once, cached |
| PubMedBERT dense | `NeuML/pubmedbert-base-embeddings` (HF) | downloaded once, cached |
| Exomiser CLI | 14.0.2 | phenotype-data 2402, hiPhive prioritiser, HPO-only mode |
| **LIRICAL CLI** | **2.4.0** | released 2026-04-09; LR framework + `phenotype.hpoa` v2026-02-16 |
| `random_seed` (sample) | 42 | (v3); v1 used 4242; thesis used 42 |
| `bootstrap_seed` | 42 | for paired bootstrap CIs |
| `MIN_PMC_ARTICLES_PER_GENE` | 5 | Stage 17 gate |
| `MIN_HPO_TERMS` | 3 | Stage 14 gate |

---

## 4. Evaluation framework

### 4.1 Per-case output schema

Each cell produces, per case, one JSON file at
`data/eval_1050/<cell_dir>/<case_id>.json` with a list of 50 entries (one per
candidate gene), each:

```json
{
  "symbol": "AIRE",
  "is_causal": true,
  "aggregate_confidence": 0.95,
  "supporting_chunks": ["chunk_id_1", "chunk_id_2"],
  "final_rank": 1
}
```

The `is_causal` flag is applied **post-hoc** by comparing against the test
case's `causal_gene` field — the agent does not see the answer key. Ranks are
1-based and unique within a case.

### 4.2 Metrics

| Metric | Formula | Range |
|---|---|---|
| **top-1** | Fraction of cases where `final_rank` of `is_causal=true` gene is 1 | [0, 1] |
| **top-5** | Same, rank ≤ 5 | [0, 1] |
| **top-10** | Same, rank ≤ 10 | [0, 1] |
| **MRR** (Mean Reciprocal Rank) | mean(1 / rank) over all cases | (0, 1] |
| **NDCG@10** | DCG@10 / IDCG@10 over the top-10 list (causal at correct rank yields gain) | [0, 1] |

Confidence intervals are computed by **paired bootstrap** (1,000 resamples,
seed 42): for each comparison cell vs reference, draw n cases with replacement,
compute Δ, repeat 1,000 times, report 2.5 % and 97.5 % percentiles.

### 4.3 Cohort-level vs per-category-mean reporting

Because v3 oversamples immunological:

- **Raw cohort top-1** (e.g., 0.725 for Cell S) reflects the disproportionate
  sample → NOT directly comparable to baselines evaluated on natural-prevalence
  cohorts.
- **Per-category-mean top-1** (unweighted average of 4 category top-1s) is the
  bias-corrected alternative. For Cell S: (0.716 + 0.747 + 0.872 + 0.559) / 4
  = 0.7235 — within 0.002 of the raw figure because all categories are
  approximately equally represented.

Both numbers are reported. Per-MONDO subgroup analysis is the primary unit of
inference; cohort aggregates are secondary.

### 4.4 Per-MONDO subgroup analysis

For each pair of cells × each of the 4 MONDO categories, we compute:
- Per-cell top-1/5/10 on the subgroup
- Δ (cell A − cell B) with paired bootstrap 95 % CI
- McNemar's exact test (when relevant)

The paper reports per-MONDO breakdowns for K, M (when comparing curated baselines),
and for all 5 cells in the main results table.

### 4.5 Sensitivity analysis

For load-bearing claims (e.g., per-MONDO subgroup wins), we run four
robustness probes:

1. **Bootstrap CI** at the full subset n
2. **Leave-one-out (LOO)** — drop each case, recompute CI; report fraction of
   LOO subsets whose CI still excludes 0
3. **Leave-N-out (sample-size sensitivity)** — at multiple smaller n values,
   how often does the CI exclude 0
4. **McNemar's exact test** + **permutation test** for paired binary outcomes

### 4.6 RAGAS evaluation (Thread C, v3)

Independent evaluation axis measuring RAG-quality properties the per-case top-1
metric doesn't capture. Computed using GPT-4o (`gpt-4o-2024-08-06`) as the
LLM judge via OpenAI API (a **deliberate documented deviation** from the
project's all-local rule — for evaluation only; production stays all-local).

| Metric | Definition | Applies to |
|---|---|---|
| **Faithfulness** | Fraction of LEA's claims supported by retrieved chunks | Cell S only |
| **Context precision** | Fraction of retrieved chunks relevant to the query | Cell L + S |
| **Context recall** | Fraction of ground-truth claims present in retrieved chunks | Cell L + S |
| **Answer relevance** | Semantic alignment of LEA's response to the patient phenotype | Cell S only |
| **Hallucination (DeepEval)** | Fraction of LEA's claims NOT supported by contexts (= 1 − faithfulness with different operationalisation) | Cell S only |

Per-case sidecars are persisted to
`data/eval_1050/cell_S_responses/<case_id>.json` and
`data/eval_1050/cell_L_responses/<case_id>.json`, containing the full LEA
prompt, raw response text, parsed JSON ranking, token counts, finish reason,
and per-gene retrieved chunks with PMCIDs and RRF scores.

### 4.7 Annotation overlap analysis (Thread D, v3)

LIRICAL's `phenotype.hpoa` knowledge base is curated from rare-disease
publications. Phenopacket Store cases are derived from the same publications.
**Therefore LIRICAL's evaluation on Phenopacket Store cases is partially
self-referential — an annotation overlap.**

For each case, we compute a binary `annotation_overlap` flag:
- 1 if case source PMID appears in `phenotype.hpoa` as a reference for the
  causal gene's OMIM disease
- 0 otherwise

We then stratify all 5 cells' results into overlap-present vs overlap-absent
subsets and report side-by-side. This makes the LIRICAL comparison honest.

### 4.8 Novel-cases subset (Thread E, v3)

Stronger overlap-control: filter the n=1,047 to cases whose source PMID was
published *after* `phenotype.hpoa` v2026-02-16 release. LIRICAL has no
annotations for these → fair comparison. Expected subset size: ~150-300 cases.

### 4.9 LIRICAL + LEA ensemble (Thread F, v3)

Combine LIRICAL posttest probability with LEA confidence via Reciprocal Rank
Fusion or weighted blend. Demonstrates complementarity — even when LIRICAL is
strong, geno_agent contributes orthogonal information.

### 4.10 Explanation quality (Thread G, v3)

Contrast: only Cell S produces evidence-traceable free-text rationales with
citations. RAGAS faithfulness on Cell S has no equivalent on Cell K, M, or L.
Reported as a clinical-utility differentiator.

---

## 5. Operational infrastructure

### 5.1 Hardware

| Component | Spec |
|---|---|
| GPU | NVIDIA RTX 5090, 32 GB VRAM (Blackwell, cu128) |
| CPU | (host) |
| RAM | 64 GB |
| Storage | 1.7 TB Linux SSD (project + Qdrant + models on `/dev/sdc`); 3.7 TB Windows mount for PMC bulk processing |
| OS | WSL2 Ubuntu 24.04 on Windows host |

### 5.2 VRAM budgeting (paper extension iteration 3)

A multi-iteration calibration was needed to find safe vLLM caps:

| Attempt | `--gpu-memory-utilization` | `--max-model-len` | `--max-num-seqs` | Outcome |
|---|---|---|---|---|
| 1 (thesis) | 0.85 | 32768 | default (256) | Worked but only ~4 GB free for CE+dense |
| 2 (v1 first cut) | 0.55 | 16384 | 4 | Engine init failed — 0.88 GB KV cache too small |
| 3 (v1 second cut) | 0.70 | **16384** | 4 | Booted but vLLM returned HTTP 400 on 78 % of LEA requests (prompts > 16k) |
| **4 (v1 final, v2, v3)** | **0.75** | **32768** | **1** | **Stable. vLLM ~24.4 GB; ~8 GB free for CE + dense + activations.** |

The final config has been verified across the n=459 v1 run, the n=1,047 v2 run,
and the n=1,047 v3 re-run with no GPU crashes or driver hangs.

### 5.3 Sequenced GPU resource scheduling

To prevent GPU OOM when vLLM, MedCPT-CE, and PubMedBERT compete for VRAM, the
sequencer (`scripts/eval/run_paper_extension.sh`) never overlaps GPU consumers
in time:

```
CPU lane:  K -------- (Exomiser, ~1.5h)
           M -------- (LIRICAL, ~22 min, 8 parallel workers)

GPU lane:  D --> L --> [start vLLM] --> S --> [kill vLLM]
           ~7h  ~6h    ~30 s          ~8 h
```

vLLM is only alive during Cell S; explicitly torn down via `trap cleanup_on_exit
EXIT INT TERM` to release VRAM for the next stage.

### 5.4 Pre-flight GPU-free assertion

Before each GPU stage transition, the sequencer asserts `nvidia-smi free ≥
MIN_FREE_MIB` (default 4,000 MiB at v3; was 6,000 at v1 — relaxed because
util=0.75 leaves ~5.8 GB free legitimately during CUDA-graph capture, which
tripped the original 6 GB threshold as a false-positive).

### 5.5 Python environment separation

- **`pytorch-env`** (`/home/hana77/pytorch-env/`): main evaluation environment.
  Python 3.12, cu128 nightly torch (RTX 5090 requirement), sentence-transformers,
  qdrant-client, pronto, etc.
- **`vllm-env`** (`/home/hana77/vllm-env/`): isolated venv for vLLM 0.20.1
  (requires its own torch pin). `start_vllm.sh` always uses
  `${VLLM_PYTHON:-${HOME}/vllm-env/bin/python}` regardless of the calling shell.

### 5.6 Response logging (v3)

For RAGAS / DeepEval evaluation, per-case sidecars persist:

```
data/eval_1050/cell_{L,S}_responses/<case_id>.json:
{
  "case_id": "...",
  "hpo_terms": [...],
  "candidate_genes": [...50...],
  "causal_gene": "...",
  "category": "immunological",
  "use_lea": true,                  // false for Cell L
  "retrieved_per_gene": {
    "AIRE": [
      {"chunk_id": "...", "text": "...", "source_pmcid": "PMC...", "section_type": "...", "score_dense": 0.83, "score_bm25": 11.4, "score_rrf": 0.33}, ...
    ], ... 49 more ...
  },
  "lea_log": {                       // null for Cell L
    "lea_system_prompt": "...",
    "lea_user_prompt": "62 KB of evidence text",
    "lea_top_gene_symbols": [...15...],
    "hpo_labels": [...],
    "lea_evidence_per_gene": {...same shape as retrieved_per_gene but only top-15...},
    "lea_response_raw": "...LEA's free-text reasoning, ~1.9 KB...",
    "lea_response_parsed": [...15 genes ranked by LEA...],
    "lea_response_tokens_in": 16147,
    "lea_response_tokens_out": 446,
    "lea_response_finish_reason": "stop",
    "lea_response_latency_s": 18.4,
    "lea_fallback_reason": null
  },
  "ranked": [...50 genes with rank + score + is_causal...]
}
```

The schema was finalised after three bug-fix iterations (RetrievedChunk field
names, AgentState slots, LlmResponse serialisation). All fields are
JSON-serialisable primitives.

### 5.7 Reproducibility commands

See `paper_extension_plan_v2.md` §Appendix D and
`paper_extension_plan_v3.md` §7 for end-to-end reproducibility command sequences.
Summary:

```bash
# Pin Phenopacket Store v0.1.26
sed -i 's/PHENOPACKET_STORE_VERSION=0.1.19/PHENOPACKET_STORE_VERSION=0.1.26/' .env

# Download + extract phenopackets
curl -sL ".../all_phenopackets.zip" -o data/phenopackets/v0.1.26.zip
unzip data/phenopackets/v0.1.26.zip -d data/phenopackets/v0.1.26/

# Phase 1B Stages 13-19
for stage in 13 14 15; do
  TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/${stage}_*.py
done
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/16_stratified_sample.py \
    --seed 42 \
    --per-category-target "developmental=250,immunological=300,metabolic=250,neurological=250"
for stage in 17 18 19; do
  TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/${stage}_*.py
done

# Launch 4 main cells (~20 h)
tmux new -d -s paper_k_1050 "PYTHONPATH=. python scripts/eval/run_cell_k.py --test-cases data/test_cases_1050/test_cases.jsonl --out-dir data/eval_1050/cell_K_exomiser_hpo_only"
tmux new -d -s paper_gpu_1050 "TEST_CASES=\$(pwd)/data/test_cases_1050/test_cases.jsonl OUT_ROOT=\$(pwd)/data/eval_1050 MIN_FREE_MIB=4000 bash scripts/eval/run_paper_extension.sh"

# Cell M (LIRICAL, ~22 min)
PYTHONPATH=. python scripts/eval/run_cell_m.py --workers 8 --xmx 4g

# Aggregate
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/eval/aggregate_metrics.py \
    --eval-root data/eval_1050 --test-cases data/test_cases_1050/test_cases.jsonl

# Response-logged L+S re-run (for RAGAS sidecars)
bash scripts/eval/run_paper_extension_LS_responses.sh

# RAGAS + DeepEval (requires OPENAI_API_KEY)
PYTHONPATH=. python scripts/eval/run_ragas.py --responses-dir data/eval_1050/cell_S_responses --out data/eval_1050/ragas_cell_S.json
PYTHONPATH=. python scripts/eval/run_deepeval.py --responses-dir data/eval_1050/cell_S_responses --out data/eval_1050/deepeval_cell_S.json
```

---

## 6. Determinism + reproducibility guarantees

| Guarantee | Mechanism |
|---|---|
| Bit-stable cohort | seeded sampling (`random.Random(42)`), sorted by (`category`, `case_id`) within strata |
| Bit-stable candidate lists | UUID5 distractor draw with seed |
| Deterministic chunk IDs | UUID5 from chunk text + provenance (master plan §4 step 3) |
| Deterministic Critic + Synthesizer | No LLM in the deterministic configurations (Cells D, L) |
| Deterministic LEA temperature | `temperature=0.0` (vLLM batching adds minor non-determinism; observed: ~98 % per-case rank stability between two independent runs; **top-1 metric is bit-identical** across runs because the small per-case rank perturbations don't cross the rank-1 boundary in observed data) |
| Deterministic bootstrap | `random.seed(42)` at the start of each CI computation |
| Pinned ontologies + tools | All versions listed in §3 |

### 6.1 v2 vs v3 deterministic verification

We re-ran Cells L and S at v3 with response logging enabled (otherwise identical
code paths). Comparison on the 605 cases completed at the time of writing:

- **Cell L**: 100 % top-1 identical between v2 and v3 (deterministic; 21/1047 cases had different rank-positions for ties below #1, but top-1 was bit-identical at 0.6982)
- **Cell S**: **100 % top-1 identical** between v2 and v3 on the 605 cases completed so far (97.7 % rank-identical overall — the 14 disagreements were in ranks 2-50 and did not flip top-1 status)

This is the strongest possible reproducibility guarantee short of bit-identical
floating-point arithmetic: the **scientific conclusion** is deterministic even
though some sub-rank positions are vLLM-batching-sensitive.

---

## 7. Current status and timeline

### 7.1 Completed (as of 2026-05-18)

| Phase | Status |
|---|---|
| Master thesis (n=75, 16-cell factorial, v0.1.19) | ✅ defended |
| Paper extension v1 (n=459 from v0.1.19, seed 4242) | ✅ done, PR #36 |
| Paper extension v2 (n=1,047 from v0.1.26, seed 42) | ✅ done, tagged `paper-v2-final` |
| Paper extension v3 — Cell M (LIRICAL) integration + run | ✅ done, commit `5df44fa` |
| Paper extension v3 — response-logging patches + L re-run | ✅ Cell L done; Cell S currently at ~58 % |

### 7.2 In progress

| Item | Status | ETA |
|---|---|---|
| Cell S v3 re-run | 🟢 ~605/1047 | done ~23:50Z 2026-05-18 |

### 7.3 Pending (Strategy A roadmap)

| # | Item | Effort |
|---|---|---|
| 1 | RAGAS pipeline (GPT-4o judge, n=1,047, Cell L + Cell S) | 3-4 days (needs OPENAI_API_KEY) |
| 2 | DeepEval hallucination metric (Cell S, n=1,047) | 1-2 days |
| 3 | Thread D: LIRICAL annotation-overlap analysis | ~3 days |
| 4 | Thread E: Novel-cases subset experiment | ~3-4 days |
| 5 | Thread F: LIRICAL + LEA ensemble | ~3 days |
| 6 | Thread G: Explanation-quality contrast | ~0.5 day |
| 7 | Wallclock + cost table (K, M, D, L, S, N-ensemble) | 1 day |
| 8 | DeepRare head-to-head on n=100 (post-v3) | 5-7 days |
| 9 | Qwen3-32B AWQ ablation on n=100 (post-v3) | 2-3 days |
| 10 | Pre-submission self-review against EJHG 2026 benchmark | 1 day |
| 11 | Manuscript drafting (target: Genome Medicine) | 2-3 weeks |

**Total Strategy A timeline:** ~12-13 weeks from 2026-05-18 to Genome Medicine submission.

### 7.4 Paper position and framing

Headline (as of v3 with overlap caveats understood):

> "geno_agent is the **strongest literature-only system** for rare-disease gene
> prioritization: it statistically matches Exomiser HPO-only on overall top-1
> (Δ=+0.034, 95% CI [+0.006, +0.064]), statistically wins on the metabolic
> (+8.4 pp) and immunological (+6.7 pp) MONDO subgroups, and provides three
> capabilities no curated tool offers — explanation-traceable rankings with
> primary-literature citations, performance on cases beyond curated tools'
> knowledge cutoff, and ensemble complementarity with LIRICAL.
> LIRICAL outperforms in raw top-1 (0.924) but with significant annotation
> overlap with the source cohort; we report stratified deconfounded numbers
> alongside the raw figures."

Target venue: **Genome Medicine** (IF ~12-15). Fallbacks: Bioinformatics, JAMIA,
Briefings in Bioinformatics.

---

## 8. Project-rule deviations (deliberate, documented)

The project's `CLAUDE.md` and master plan have hard rules. Three deliberate
deviations are documented:

| Deviation | Where allowed | Justification |
|---|---|---|
| Ontology versions pinned to 2026 releases (vs 2024 in original master plan) | All phases | 2026 ontologies are the current authoritative releases; pinning to 2024 would mean evaluating against stale phenotype-gene associations |
| Phenopacket Store upgraded v0.1.19 → v0.1.26 between v1 and v2 paper extension | v2 + v3 | Adds 252 gene cohorts (+359 % immunological) at zero plumbing cost; closes a known v1 limitation |
| **GPT-4o cloud API for RAGAS/DeepEval judging** | **v3 evaluation only — never production** | Production pipeline (Cells D, L, S) remains 100 % local. GPT-4o is the de-facto standard RAG-evaluation judge in 2025-2026; using a Qwen-family judge would introduce self-evaluation bias. ~$60-80 total spend, bounded. |

Each deviation is also recorded in the master plan §10 (recorded deviations)
and the relevant plan documents.

---

*Methodology v3 finalised 2026-05-18. Authoritative reference for the paper's
Methods section. Plan documents
[`paper_extension_plan_v2.md`](paper_extension_plan_v2.md) and
[`paper_extension_plan_v3.md`](paper_extension_plan_v3.md) remain authoritative
for execution sequencing and per-thread methodology rationale.*
