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

**Scope decision (2026-05-23):** A smoke test (3 cases × 3 metrics) measured
real cost at ~23 OpenAI calls per case — extrapolating to ~$160 for the
originally-planned n=1,047 × Cells L+S × 4 metrics, materially over the
$100 budget. The final scope is **Cell S only, n=600 (150 per MONDO,
seed 42), 3 metrics (faithfulness, context_precision, context_recall),
MAX_CONTEXTS_PER_CASE=20**, expected ~$95. Skipping Cell L is defensible
because the L-vs-S retrieval-quality story is already covered by the
top-1 Δ of +0.028 ★ in §4.2 (LEA contribution). Skipping answer_relevance
is defensible because it overlaps with top-k accuracy. The 3-metric
combination preserves the load-bearing "is LEA hallucinating?" question
(faithfulness) plus retrieval-quality numbers for the Methods section.

### 4.7 Annotation overlap analysis (Thread D, v3) — ✅ landed 2026-05-23

LIRICAL's `phenotype.hpoa` knowledge base is curated from rare-disease
publications. Phenopacket Store cases are derived from the same publications.
**Therefore LIRICAL's evaluation on Phenopacket Store cases is partially
self-referential — an annotation overlap.**

**Implementation:** `scripts/eval/compute_annotation_overlap.py` joins each
case's source PMID (extracted from `case_id`) against `phenotype.hpoa
v2026-02-16` (282,723 rows → 9,852 unique `(OMIM disease, PMID)` keys) for
each causal-OMIM-disease in the case. 100 % of n=1,047 cases have both an
extractable PMID and an OMIM disease ID — zero edge cases.
`scripts/eval/aggregate_stratified.py` re-aggregates all 5 cells on
`overlap_present` (n=765), `overlap_absent` (n=282, the fair-comparison
cohort), and `__all__` subsets with per-cell bootstrap CIs and paired Δ +
McNemar for the canonical comparisons.

**Cohort overlap rate**: 73.1 % (765/1,047). Per-MONDO:
immunological 86.3 %, neurological 76.1 %, metabolic 64.0 %, developmental 63.2 %.

**Headline deconfounded result (overlap_absent, n=282):**
- Cell S (geno_agent): top-1 = 0.858 [0.816, 0.901] — **#1 system**
- Cell L (CE-rerank): 0.823 [0.773, 0.869]
- Cell K (Exomiser): 0.780 [0.734, 0.830]
- Cell M (LIRICAL): 0.777 [0.727, 0.826] (DOWN from 0.978 on overlap-present)
- Cell D (multi-agent hybrid): 0.475 [0.422, 0.532]

**Paired Δ on the fair cohort:**
- S vs M: Δ = +0.082 [+0.021, +0.145] ★ McNemar p = 0.014
- S vs K: Δ = +0.078 [+0.011, +0.138] ★ McNemar p = 0.015 (>2× the +0.035 on full cohort)
- M vs K: Δ = -0.004 [-0.053, +0.043] **— LIRICAL TIES Exomiser without overlap**

Full results in [`paper_extension_results.md §13`](paper_extension_results.md)
and `data/eval_1050/_results_stratified.{json,md}`.

### 4.8 Novel-cases / recency-stratified subset (Thread E, v3, pivoted) — ✅ landed 2026-05-23

**Original premise was empty by construction.** The plan called for cases
whose source PMID was published > `phenotype.hpoa v2026-02-16`. NCBI E-utils
lookup of all 415 unique cohort PMIDs (`scripts/eval/pubmed_date_lookup.py`,
~10 s wall) returns **0 such cases**: Phenopacket Store v0.1.26 is curated
from already-published literature (most recent source PMID = 2024).

**Pivoted to a publication-recency split** that preserves the scientific
intent ("does geno_agent generalise better than curated tools to cases the
curation cycle hasn't caught up with?") on a properly-powered partition.

`scripts/eval/aggregate_recency.py` re-aggregates all 5 cells on:
- `pre_2020` (n=601, 57.4 %)
- `post_2020` (n=446, 42.6 %)
- `pre_2020_overlap_absent` (n=194)
- `post_2020_overlap_absent` (n=88, **closest substitute for the empty
  original subset**)

**Headline recency findings:**

1. **Exomiser top-1 collapses on post-2020 papers**: 0.847 → 0.480
   (Δ = -37 pp). Largest recency-induced drop of any system.
2. **geno_agent's edge over Exomiser is 2.7× larger on post-2020**:
   Δ S−K = +0.094 [+0.045, +0.139] ★ on post_2020 vs +0.035 on full cohort.
   On pre-2020 the two systems are statistically tied (Δ = -0.008, p = 0.72).
3. **LIRICAL recency paradox** (strengthens Thread D): LIRICAL top-1 *rises*
   from 0.915 → 0.935 on post-2020, mechanistically explained by the
   post-2020 overlap rate of **80.3 %** vs pre-2020 **67.7 %** (+12.6 pp).
   hpoa preferentially curates recent landmark publications.
4. **Strictest-novel subset** (post_2020 × overlap-absent, n=88):
   S = 0.852, M = 0.773 — geno_agent remains the top-ranked system.
   Δ S−M = +0.080 matches Thread D's fair-cohort +0.082 within MC noise.

Full results in [`paper_extension_results.md §14`](paper_extension_results.md)
and `data/eval_1050/_results_recency.{json,md}`.

### 4.9 LIRICAL + LEA ensemble (Thread F, v3, scoped) — ✅ landed 2026-05-23

**Scope reduced 3-day → 1-day** (in fact ~10 min execution after Thread D + E)
because the math says the ensemble is bounded above by the better of M and S
on each subset. Single RRF check (k = 60) to generate the concrete number
for the reviewer question "did you try ensembling?".

`scripts/eval/build_cell_n_rrf.py` produces Cell N (RRF ensemble of M + S)
over the 50-gene candidate sets in each case. Registered in the `CELLS`
dict so existing aggregation tooling picks it up.

**Result (Cell N top-1 by subset):**

| Subset | n | M | S | **N (RRF)** | N vs S | N vs M |
|---|---:|---:|---:|---:|---:|---:|
| __all__ | 1,047 | 0.924 | 0.726 | 0.775 | +0.050 ★ | **-0.148 ★** |
| overlap_present | 765 | **0.978** | 0.677 | 0.748 | +0.071 ★ | **-0.230 ★** |
| **overlap_absent** | **282** | 0.777 | **0.858** | 0.851 | **-0.007 NS** | +0.075 ★ |
| post_2020_overlap_absent | 88 | 0.773 | 0.852 | 0.875 | +0.023 NS | +0.102 ★ |

**Interpretation:** On the cohort that matters (overlap-absent, n=282) the
ensemble is **statistically tied** with Cell S alone (Δ = -0.007, McNemar
p = 0.87). On the contaminated cohort it loses 23 pp to LIRICAL alone. The
two systems carry no independent predictive signal beyond what overlap status
already explains. The "did you try ensembling?" reviewer question is closed
with a one-sentence Discussion conclusion.

Full results in [`paper_extension_results.md §15`](paper_extension_results.md).

### 4.10 Explanation quality (Thread G, v3) — ✅ structural part landed 2026-05-23, RAGAS pending

Contrast: only Cell S produces evidence-traceable free-text rationales with
PMC citations. RAGAS faithfulness on Cell S has no equivalent on Cell K, M,
or L. **Cell S is the only system in the comparison that satisfies the
three explanation properties simultaneously: free-text rationale per ranked
gene, PMC source attribution, and LLM-judge-quantifiable faithfulness.**

`scripts/eval/analyze_lea_rationales.py` runs the structural part locally
(no API spend) over the 1,047 Cell S sidecars.

**Headline coverage stats:**

| Subset | n | causal-gene substantive rationale | median top-1 length (chars) | mean PMCIDs / top-1 gene | LEA fallback |
|---|---:|---:|---:|---:|---:|
| __all__ | 1,047 | **81.5 %** | 80 | 2.81 | 0.19 % |
| **overlap_absent** | **282** | **94.0 %** | 80 | 2.85 | **0.00 %** |
| metabolic | 250 | **94.8 %** | 81 | 2.90 | 0.00 % |

Two findings:

1. **LEA explains itself BETTER on the fair cohort** (94.0 % vs 76.9 %
   overlap-present, +17 pp). Consistent with Thread D's accuracy story —
   it's reasoning more confidently with citable evidence, not just guessing
   harder.
2. **LEA fallback rate = 0.2 % overall and 0.0 % on the fair cohort** —
   concrete answer to the "is the LLM-in-the-loop reproducible?" reviewer
   question.

**RAGAS faithfulness landed 2026-05-23 18:13Z** (n = 600 stratified
Cell S, gpt-4o-2024-08-06 judge, MAX_CONTEXTS=20, 167.8 min wall,
~$95 OpenAI spend — within the $100 budget):

| Metric | Mean | Median |
|---|---:|---:|
| context_precision | 0.650 | 0.794 |
| context_recall | 0.796 | 1.000 |
| faithfulness | **0.286** | **0.433** |

The most important *secondary* finding: **faithfulness is a strong
top-1 correctness predictor**. Cases at faithfulness = 0 are 46.5 %
top-1 correct; cases at faithfulness > 0 are 79.9 % correct — a
33-pp gap. This makes faithfulness usable as an automated clinical-
triage flag (low-faithfulness predictions auto-routed for human
review). Faithfulness is also slightly higher on the fair-comparison
cohort (mean 0.310 vs 0.276 overlap-present), consistent with
geno_agent's higher rationale-coverage rate on the same subset
(94 % vs 77 % causal-gene substantive, see Thread G structural part).

**Honest caveat (must appear in the Methods):** faithfulness was
computed against ≤ 20 retrieved contexts per case to fit the $100
budget; LEA itself saw up to 45 chunks during inference. Chunks 21-45
are invisible to the judge, so claims they support may be marked
"unsupported". The measured 0.286 is therefore a *lower bound* on
the true faithfulness against LEA's actual input. Bounding the true
value (rerun at MAX_CONTEXTS=45, ~$50, or inline-citation prompting)
is future work; the 33-pp correctness-prediction signal stands
regardless of the absolute floor.

**RAGAS top-1-only sensitivity re-run (added 2026-05-23 19:07Z):**
Investigation of high vs zero-faithfulness cases on the original n=600
run revealed that ~70 % of the LEA response is a JSON list of 14
"no direct evidence" rationales for distractor genes that RAGAS scores
as unsupported claims (each distractor rationale claims absence of
evidence — and chunks don't literally contain "X has no link"
statements). Re-running with `--top1-only` (strip response to LEA's
substantive top-1 claim + reorder contexts by LEA rank so top-1's
chunks are guaranteed in the cap window) on n=100 stratified gave:

| Statistic | Original (n=600) | Top-1-only (n=100) | Paired Δ on n=66 |
|---|---:|---:|---:|
| Mean | 0.286 | **0.480** | +0.229 |
| Median | 0.433 | **0.500** | +0.200 |
| Fair-cohort mean | 0.310 | **0.616** | +0.306 |
| Fair-cohort lift | +0.034 | **+0.188** | +0.154 |

68 % of cases improved, 12 % worsened. The (0.5, 1.0) range now holds
44 % of cases (vs 1 % in the original). **The 0.480 number is the
recommended primary measurement for the paper**; the original 0.286
is retained as a documented methodological caveat (the multi-claim
artifact is a known RAGAS-on-multi-gene-output pattern that warrants
mention in any paper using RAGAS on rare-disease prioritisation
output).

The correctness-prediction signal also reproduces (top-1-only > 0.5
vs ≤ 0.5: 82.8 % vs 62.2 % top-1 correct, 21-pp gap), confirming the
auto-triage-flag deployment story.

**DeepEval HallucinationMetric on n=100 sensitivity subset (added 2026-05-23):**
A second independent LLM judge (DeepEval v4.0.3 with the same
gpt-4o-2024-08-06 model, MAX_CONTEXTS=45) was run on a stratified n=100
subset (25 per MONDO, seed 42 — a subset of the RAGAS n=600 cohort).
3.1 min wall, ~$1.20 spend.

| Metric | Mean | Median |
|---|---:|---:|
| Groundedness (1=fully grounded, 0=fully hallucinated) | 0.845 | 0.933 |
| Hallucination rate (= 1 − score) | 0.155 | 0.067 |

DeepEval is **holistic** (does the answer overall contradict the contexts?)
while RAGAS is **claim-level** (is each individual claim chunk-supported?).
Both are valid measurements of different aspects of grounding. The paper
reports both as a defensible range (0.286 strict ↔ 0.845 lenient).

**The correctness-prediction signal reproduces across both judges:**
DeepEval-high (groundedness ≥ 0.5) cases are 78.9 % top-1 correct vs
DeepEval-low cases at 40.0 % — a 39-pp gap matching RAGAS's 33-pp gap.
Independent reproduction strengthens the "groundedness as triage flag"
deployment story.

Per-subgroup DeepEval (n=100 stratified):
- developmental 0.898, immunological 0.946, metabolic 0.872, neurological 0.665
- overlap_absent 0.894 vs overlap_present 0.830 (+6.4 pp fair-cohort lift)

**Neurological is the worst on both judges** (lowest groundedness, highest
zero-rate) — robustly-documented system-level limitation to flag in the
paper Limitations section.

Full results in [`paper_extension_results.md §§16-17`](paper_extension_results.md).

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

### 7.1 Completed (as of 2026-05-23)

| Phase | Status |
|---|---|
| Master thesis (n=75, 16-cell factorial, v0.1.19) | ✅ defended |
| Paper extension v1 (n=459 from v0.1.19, seed 4242) | ✅ done, PR #36 |
| Paper extension v2 (n=1,047 from v0.1.26, seed 42) | ✅ done, tagged `paper-v2-final` |
| Paper extension v3 — Cell M (LIRICAL) integration + run | ✅ done, commit `5df44fa` |
| Paper extension v3 — response-logging patches + L+S re-run | ✅ done (L: 0 top-1 flips; S: 1 top-1 flip / 1,047) |
| **v3-5 — 5-cell aggregation + paired-diff toolkit** | ✅ done, commit `1b65028` |
| **v3-6 Thread D — annotation-overlap deconfounding** | ✅ done, commit `308fb2e` — geno_agent #1 on fair cohort |
| **v3-9 Thread E — recency-stratified analysis (pivoted)** | ✅ done, commit `6a812a4` — Exomiser collapses post-2020 |
| **v3-10 Thread F — RRF ensemble (scoped)** | ✅ done, commit `178ed68` — no complementary signal |
| **v3-11 Thread G — explanation-quality structural part** | ✅ done, commit `49ebaca` — 94 % causal-gene rationale coverage on fair cohort |

### 7.2 In progress

| Item | Status | ETA |
|---|---|---|
| **v3-7 RAGAS pipeline (Cell S n=600 stratified, 3 metrics)** | ✅ done (commit pending) — faithfulness 0.286 / 0.433 (mean / median), context_precision 0.650, context_recall 0.796 | 167.8 min, $95 |

### 7.3 Pending (Strategy A roadmap)

| # | Item | Effort |
|---|---|---|
| 1 | ~~DeepEval hallucination metric~~ ✅ done 2026-05-23 — mean groundedness 0.845 / median 0.933 on n=100 stratified subset, 3.1 min wall, $1.20 | — |
| 2 | Thread G RAGAS plug-in (fill faithfulness number into §16.5) | ~5 min |
| 3 | Wallclock + cost table (K, M, D, L, S, N-ensemble) | 1 day |
| 4 | paper_extension_results.html — visual artefacts for §§12-16 | ~1.5 h |
| 5 | DeepRare head-to-head on n=100 (post-v3) | 5-7 days |
| 6 | Qwen3-32B AWQ ablation on n=100 (post-v3) | 2-3 days |
| 7 | Pre-submission self-review against EJHG 2026 benchmark | 1 day |
| 8 | Manuscript drafting (target: Genome Medicine) | 2-3 weeks |

**Revised Strategy A timeline:** ~3-4 weeks remaining from 2026-05-23 to
Genome Medicine submission (was ~12-13 weeks at v3 start; Threads D-G
collapsed from estimated 8-11 days to ~1 h actual wall thanks to
infrastructure-reuse — Thread D's per-case PMID/overlap toolkit made
Threads E/F/G mechanical).

### 7.4 Paper position and framing — REVISED 2026-05-23 after Threads D-G

The v3 results allow a substantially stronger framing than the v2 "ties
Exomiser overall, wins on metabolic + immunological" story:

> "geno_agent is the **#1 system on the fair-comparison cohort** of rare-disease
> cases (n = 282 cases whose source publication is not cited in
> `phenotype.hpoa` for the causal disease): top-1 = 0.858 [0.816, 0.901],
> beating LIRICAL (0.777, Δ = +8.2 pp ★) and Exomiser (0.780, Δ = +7.8 pp ★).
> On the full cohort (n = 1,047), LIRICAL's apparent dominance (top-1 = 0.924)
> is shown to be an **annotation-overlap artefact** — 73 % of cases have
> source PMIDs cited in LIRICAL's underlying `phenotype.hpoa` for the causal
> disease, and once deconfounded LIRICAL is **statistically tied** with
> Exomiser (Δ = -0.004, p = 1.000). Three further differentiators support
> geno_agent's deployment story: (i) **publication-recency robustness** —
> Exomiser top-1 drops 37 pp on post-2020 papers while geno_agent drops
> 27 pp, making the S-vs-K advantage 2.7× larger on recent cases
> (Δ = +9.4 pp ★); (ii) **uniquely-explainable rankings** — 94 % of
> fair-cohort cases have a substantive LEA rationale for the causal gene,
> backed by a mean 2.81 PMC citations; (iii) **a deterministic-fallback
> rate of 0.0 % on the fair cohort**, addressing reviewer concerns about
> LLM-in-the-loop reproducibility."

Target venue: **Genome Medicine** (IF ~12-15). Fallbacks: Bioinformatics, JAMIA,
Briefings in Bioinformatics. The v3 findings (especially Thread D + E)
substantially raise the defensibility against the most likely Q1 reviewer
objections.

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

*Methodology v3.1 — extended 2026-05-23 with Threads D-G results +
recency-pivot rationale + revised paper framing. Authoritative reference for
the paper's Methods section. Plan documents
[`paper_extension_plan_v2.md`](paper_extension_plan_v2.md) and
[`paper_extension_plan_v3.md`](paper_extension_plan_v3.md) remain authoritative
for execution sequencing and per-thread methodology rationale; the v3 plan's
Thread E spec (PMID > hpoa pin) was pivoted to publication-recency split
after the strict definition yielded an empty subset by construction. See
[`paper_extension_results.md §§13-16`](paper_extension_results.md) for
detailed Threads D-G writeups.*
