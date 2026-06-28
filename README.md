# geno_agent

**An Agentic-Workflow RAG System for Gene Prioritization in Rare Mendelian Disease**

> **Doctoral first paper** (Universidad Europea de Madrid; n=1,047; target:
> *Genome Medicine*). An end-to-end agentic-workflow RAG system for
> literature-based causal gene prioritisation in rare Mendelian disease.
>
> **Headline (n=1,047, deconfounded).** On the *fair-comparison cohort* — cases
> whose source publication is **not** cited by `phenotype.hpoa` for the causal
> gene — geno_agent (Cell S) is the **top-ranked system** (top-1 **0.858**),
> significantly beating Exomiser (+0.078, p=0.015) and LIRICAL (+0.082, p=0.014);
> both survive Holm multiple-comparison correction. A **leave-one-paper-out**
> robustness check confirms this does **not** depend on retrieving each case's own
> source paper (fair-cohort top-1 unchanged, 0.858 → 0.858, McNemar p=1.0).
> geno_agent is the strongest **literature-only** rare-disease gene-prioritisation
> system (no curated phenotype-gene tables); **production inference runs entirely
> on local hardware** — only the optional RAGAS/DeepEval evaluation judges (used
> for measurement, not prioritisation) require an external OpenAI-compatible LLM
> endpoint (GPT-4o in this study).
>
> **Latest update (2026-06-11).** Full n=1,047 evaluation complete
> (annotation-overlap deconfounding, publication-recency stratification,
> three-LLM-family ablation, RAGAS + DeepEval). Added a **leave-one-paper-out**
> robustness analysis, **Holm / Benjamini-Hochberg** multiplicity correction, and
> **stratum-weighted** sensitivity. Manuscript Q1 draft hardened (PR #37, merged).

---

## Overview

`geno_agent` is an agentic-workflow retrieval-augmented generation (RAG) system that automates literature-based evidence synthesis for the most labor-intensive step of the rare-disease diagnostic pipeline: deciding which candidate gene most plausibly causes a patient's phenotype.

Given a patient's phenotypic profile (encoded as [Human Phenotype Ontology](https://hpo.jax.org) terms) and a list of candidate genes from upstream variant calling, the system automatically retrieves full-text articles from PubMed Central Open Access (PMC OA), critically evaluates the relevance and strength of the recovered evidence, and synthesizes a re-ranked candidate list with cited justifications.

Unlike monolithic RAG systems that perform a single retrieve-and-generate pass, `geno_agent` is an **agentic workflow composed of four role-specialized agents** — **Query Planner**, **Retriever**, **Critic**, and **Synthesizer** — orchestrated as a stateful graph in [LangGraph](https://github.com/langchain-ai/langgraph). This decomposition enables iterative query refinement, explicit relevance grading, and a critic-driven self-correction loop that single-pass architectures cannot support.

**Terminology.** Throughout, we use *agent* to denote a **role-specialized component** — a node in the LangGraph state graph that consumes and updates shared workflow state. The system as a whole is an **agentic workflow**: orchestration with predefined routing plus a critic-driven self-correction loop. It is *not* an autonomous multi-agent system in which each agent decides its own control flow and chooses tools at run time — fixing the topology and decoding (temperature 0, seeded) keeps inference reproducible and the evaluation valid, a prerequisite for clinical benchmarking. The "single-agent vs. multi-agent" factor below refers to the number of role-specialized agents (one vs. four), not to agent autonomy.

## Why this matters

Rare diseases affect an estimated [300 million people worldwide](https://doi.org/10.1038/s41431-019-0508-0) — between 3.5% and 8% of the global population. Despite the maturation of next-generation sequencing, roughly **half of all exome and genome sequencing cases remain without a molecular diagnosis** ([Clark et al., 2018](https://doi.org/10.1038/s41525-018-0053-8)). A substantial fraction of these undiagnosed cases is not due to undetectable variants but to the limits of current bioinformatic tools when interpreting **variants of uncertain significance** (VUS), particularly in patients with atypical or previously undescribed phenotypes.

Phenotype-driven prioritization tools such as [Exomiser](https://exomiser.readthedocs.io) (Smedley et al., 2015) work well when the causal gene is already well annotated in curated phenotype databases. They cannot surface novel or emerging gene–phenotype associations that exist *only* in unstructured literature — which is precisely where the most diagnostically valuable case reports, functional studies, and phenotype-expansion papers live. PubMed indexes over a million new articles per year, and the PMC Open Access subset alone contains more than four million full-text articles. No human curator can keep pace.

This project asks whether an agentic-workflow RAG architecture, deployed on local hardware and grounded in the published literature, can meaningfully assist this synthesis step for clinical genetics teams.

## What this project contributes

To our knowledge, this is the first end-to-end validated agentic-workflow RAG system designed and evaluated specifically for **causal gene prioritization in rare Mendelian disease via literature evidence synthesis**. Specifically, the project contributes:

1. **An open, reproducible architecture** — four role-specialized agents (Query Planner / Retriever / Critic / Synthesizer) coordinated as a LangGraph agentic workflow, with all components, prompts, and configuration released under an open license.
2. **A rigorous 2×2+1 factorial evaluation design** that isolates the contribution of the multi-agent architecture from the contribution of hybrid retrieval. The 2×2 factor crosses *single-agent vs. multi-agent* with *dense-only vs. hybrid (dense + BM25)* retrieval; Exomiser is included as an external phenotype-driven baseline, providing a direct quantitative comparison against an established gold standard.
3. **Local, consumer-GPU deployment** — the system runs end-to-end on a single workstation (NVIDIA RTX 5090, 32 GB VRAM) using [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) as the reasoning model and [PubMedBERT](https://huggingface.co/microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext) for biomedical embeddings. No external API dependencies *at inference time*, no per-call cost, no data leaving the workstation — important for both reproducibility and any future extension to protected clinical data. (The optional RAGAS/DeepEval evaluation judges are the sole component that calls an external OpenAI-compatible LLM endpoint — GPT-4o in this study — used only to *measure* rationale quality, never for gene prioritisation.)
4. **A standardized benchmark pipeline** built on the [GA4GH Phenopacket Store](https://github.com/monarch-initiative/phenopacket-store) (v0.1.26 for the paper; v0.1.19 for the earlier cohort), with deterministic case selection (stratified across neurological, metabolic, immunological, and developmental categories) and seeded distractor sampling, so that any reported result can be regenerated bit-for-bit.

Where this work *is not* claiming novelty: RAG itself ([Lewis et al., 2020](https://arxiv.org/abs/2005.11401)), multi-agent LLM systems generally, hybrid dense+sparse retrieval, and the use of PubMed/PMC as a corpus are all established techniques. The contribution is the application of these techniques, in this combination, to this clinical problem, with rigorous evaluation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUT                                       │
│   • HPO phenotype terms (patient profile)                           │
│   • Candidate gene list (1 causal + 49 distractor genes)            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  ① Query Planner Agent         │
              │  Expands HPO terms via         │
              │  ontology graph traversal,     │
              │  generates targeted queries    │
              └────────────────┬───────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  ② Retriever Agent             │
              │  Hybrid search over Qdrant     │
              │  (PubMedBERT dense + BM25)     │
              │  with RRF fusion               │
              └────────────────┬───────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐         ┌──────────────┐
              │  ③ Critic Agent                │ ◄──────►│  Refinement  │
              │  Grades chunk relevance,       │         │  loop        │
              │  detects insufficient evidence │         │  (≤ N iters) │
              └────────────────┬───────────────┘         └──────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  ④ Synthesizer Agent           │
              │  Generates per-gene evidence   │
              │  summary with citations,       │
              │  produces re-ranked list       │
              └────────────────┬───────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         OUTPUT                                      │
│   • Re-ranked candidate gene list                                   │
│   • Per-gene evidence summary with PMC citations                    │
│   • Confidence / faithfulness signals                               │
└─────────────────────────────────────────────────────────────────────┘
```

### Knowledge base

The retrieval corpus is a filtered subset of PMC Open Access full-text articles enriched for rare-disease and clinical genetics content. Articles are parsed from JATS XML, segmented section-aware (Methods, Results, etc.) into 512-token chunks with 50-token overlap, embedded with PubMedBERT (768-dim), and indexed in [Qdrant](https://qdrant.tech) with both dense HNSW and BM25 sparse vectors for hybrid retrieval.

Ontologies (HPO, MONDO, GO, HGNC) are accessed at runtime as structured graph and tabular resources via `pronto` and `pandas` — they are deliberately *not* embedded into the vector index, since their value lies in their graph structure and exact lookups, not in semantic similarity.

## Evaluation design

An earlier 16-cell factorial (architecture × retrieval × Critic
type × Synthesizer type) over an n=75 cohort (cells A–J + P, Q, R, K)
established the design. This study scales the most informative cells to
n=1,047 and adds a second curated baseline:

| Cell | Configuration | Role |
|---|---|---|
| **D** | Multi-agent + hybrid retrieval (deterministic) | Inside-system baseline; isolates pre-rerank performance |
| **L** | D + MedCPT cross-encoder rerank inside the agent loop | Isolates rerank contribution |
| **S** | L + LEA (LLM-as-Evidence-Aggregator, Qwen3-8B) | Full agentic stack — primary contribution |
| **K** | Exomiser CLI 14.0.2 HPO-only, hiPhive prioritiser | External curated baseline |
| **M** | LIRICAL CLI 2.4.0 HPO-only (likelihood-ratio framework) | Second curated baseline (added v3) |

Test cases (n=1,047) are sampled from GA4GH Phenopacket Store **v0.1.26**
using disproportionate stratified sampling (250 dev + **300 imm** + 250 met +
247 neuro; immunological oversampled for subgroup statistical power). The
earlier n=75 and n=459 (paper-v1) cohorts remain in the repo for the audit
trail.

**Headline results at n=1,047 (v2 final, tagged `paper-v2-final`):**

| Cell | top-1 | top-5 | top-10 | MRR | Notes |
|---|---:|---:|---:|---:|---|
| K (Exomiser HPO-only) | 0.691 | 0.821 | 0.859 | 0.754 | curated baseline |
| M (LIRICAL HPO-only) | 0.924 | 0.989 | 0.999 | 0.953 | likely annotation overlap; see v3 Thread D |
| D (multi+hybrid) | 0.460 | 0.581 | 0.628 | 0.529 | inside-system baseline |
| L (D + CE-rerank) | 0.698 | 0.791 | 0.814 | 0.745 | +23.8 pp rerank contribution |
| **S (L + LEA)** | **0.725** | 0.798 | 0.816 | **0.766** | **+3.4 pp over K (★ paired bootstrap)** |

**Metrics:** top-1 / top-5 / top-10 (Recall@k), MRR, NDCG@10. Paired
bootstrap 95 % CIs (1,000 resamples, seed 42). Sensitivity probes
(leave-one-out, leave-N-out, permutation, McNemar) on load-bearing claims.

### Deconfounding & robustness (n=1,047, complete)

- **Annotation-overlap deconfounding.** A per-case flag marks whether the source
  publication is cited by `phenotype.hpoa` for the causal gene's OMIM disease
  (cohort overlap rate 73.1 %). On the **fair cohort (overlap-absent, n=282)**,
  geno_agent is #1 (top-1 **0.858**) vs Exomiser 0.780 (**+0.078 ★**) and LIRICAL
  0.777 (**+0.082 ★**); LIRICAL's apparent overall 0.924 collapses to a tie with
  Exomiser, quantifying its training-data exposure.
- **Leave-one-paper-out (LOPO).** Excluding each case's own source publication
  from retrieval leaves the fair cohort **completely unchanged** (0.858 → 0.858,
  McNemar p=1.0); the small full-cohort effect (−0.015) is confined to the
  overlap-present subset. geno_agent's signal is distributed across the
  literature, not concentrated in the source case report.
- **Publication-recency stratification.** Exomiser top-1 collapses 0.847 → 0.480
  on post-2020 source papers; geno_agent's edge over Exomiser is 2.7× larger on
  recent cases.
- **LLM-family ablation.** Replaying the LEA prompts across Qwen3-32B, Claude
  Sonnet 4.6, and DeepSeek-V3 converges within 2.4 pp on the fair cohort — the
  headline is robust to model family.
- **Statistical rigor.** Primary fair-cohort comparisons survive Holm correction
  (adjusted p=0.028); the geno_agent–Exomiser advantage is invariant to stratum
  weighting (+0.034 equal-weighted vs +0.035 unweighted).
- **RAG quality (GPT-4o judge).** RAGAS faithfulness (rank-1 / top-1-only
  sensitivity) **0.480** — the multi-claim full-response measurement is **0.286**,
  reported as a conservative lower bound — and DeepEval groundedness **0.845**;
  both predict top-1 correctness with a 33–39 pp gap, supporting a low-grounding
  clinical-triage flag.

## Project status

| Phase | Description | Status |
|---|---|---|
| 1A (scripts) | PMC OA pipeline scripts validated | ✅ Complete |
| 1A (production) | 52.78 M chunks indexed in Qdrant `geno_agent_pmc_oa_v1` | ✅ Complete |
| 1B (test set v1) | n=75 earlier cohort (v0.1.19, seed 42) | ✅ Complete |
| 1B (test set v2) | n=459 paper v1 (v0.1.19, seed 4242) | ✅ Complete |
| **1B (test set v3)** | **n=1,047 paper extension (v0.1.26, seed 42, disproportionate 250+300+250+250)** | ✅ Complete |
| 2a | LangGraph 4-agent state graph + Qwen3-8B/vLLM | ✅ Complete |
| 2c | CopilotKit React UI | ⏳ Deferred to post-paper |
| Eval (earlier n=75) | 16-cell factorial at n=75 | ✅ Complete |
| **Eval (paper v2)** | **5 cells × n=1,047, bootstrap CIs, per-MONDO breakdown, LIRICAL** | ✅ Complete |
| **Eval (paper v3)** | **LEA logging + RAGAS + DeepEval + annotation-overlap + recency + LLM-family ablation** | ✅ Complete |
| **Robustness** | **Leave-one-paper-out + Holm/BH multiplicity correction + stratum-weighted sensitivity** | ✅ Complete (2026-06-11) |
| **Manuscript** | **Q1 draft (*Genome Medicine*): Methods + Results + Discussion + 50 refs + TRIPOD-LLM** | 🟢 Prose complete; pending UE ethics letter + co-author list |

Reports: the consolidated methodology, execution plans, result write-ups, and
manuscript drafts are maintained as **local working documents and kept private until
publication**. The published methodology, results, and benchmark are available
through the Figshare deposits (see [Data and software availability](#data-and-software-availability));
`reports/` retains the rendered **figures, tables, and pipeline logs**.

### Phase 2 UI — CopilotKit

The interactive demo will be served through a [CopilotKit](https://copilotkit.ai)-based React UI sourced from the user's fork at [`github.com/Jangulo7/agent_UI`](https://github.com/Jangulo7/agent_UI) (upstream `CopilotKit/CopilotKit`). CopilotKit ships first-class LangGraph integration via the AG-UI protocol; geno_agent's four agents stream their state into a chat + generative-UI surface so a clinician-style user can:

- Pick HPO phenotype terms with autocomplete sourced from the local `hp.obo`
- Paste / edit a candidate gene list (validated against HGNC)
- Watch the Query Planner expand HPO terms, the Retriever pull chunks from Qdrant, the Critic grade them, and the Synthesizer re-rank — live, with citations
- Click into individual `<GeneCandidateCard>` tiles to see the supporting passages with PMC links

Full design in master plan §11.

## Reproducibility

This project is built reproducibility-first. Every external dataset is pinned to a specific dated release, with SHA-256 hashes recorded in `data/MANIFEST.tsv`:

| Resource | Pinned version |
|---|---|
| Human Phenotype Ontology (HPO) | `v2026-02-16` |
| Mondo Disease Ontology (MONDO) | `v2026-03-03` |
| Gene Ontology (GO)             | `2026-03-25` |
| HGNC complete set              | `2026-04-07` quarterly |
| **Phenopacket Store**           | **`v0.1.26`** (this study; earlier cohort used `v0.1.19`) |
| MedCPT Cross-Encoder           | `ncbi/MedCPT-Cross-Encoder` (HuggingFace, cached) |
| PubMedBERT dense embedder      | `NeuML/pubmedbert-base-embeddings` (HuggingFace, cached) |
| Qdrant server / client         | `v1.14.1` / `1.14.3` |
| Qwen3-8B Instruct              | HuggingFace default, FP16 weights, local `~/rare-disease-rag/models/` |
| vLLM                            | `0.20.1` (dedicated venv `~/vllm-env/`) |
| Exomiser CLI                    | `14.0.2` (phenotype data `2402`) |
| **LIRICAL CLI** (paper v3)      | **`2.4.0`** |

In addition:
- All chunk identifiers are deterministic UUIDv5 hashes of content, not random UUIDs
- Random seeding is fixed and documented (`PYTHONHASHSEED=42`, explicit `torch` / `numpy` / `random` seeds in embedding generation; `RANDOM_SEED=42` in `.env` for cohort sampling)
- Qdrant runs in Docker at a pinned image version (`qdrant/qdrant:v1.14.1`)
- Dependencies are pinned in `pyproject.toml` with exact versions
- Distractor gene sampling uses a per-case derived seed (`blake2b(global_seed, case_id)`), so individual cases can be regenerated without disturbing others
- All cohort sample sizes (n=75, n=459, n=1,047) regenerable from `RANDOM_SEED` + pinned ontology versions + Phenopacket Store version
- vLLM at `temperature=0.0` is mostly deterministic (~98 % per-case rank stability between runs; **top-1 metric is bit-identical** across two independent v2 and v3 runs)

The full reproducibility specification is documented in
[`MASTER_PROJECT_v2.2.md`](MASTER_PROJECT_v2.2.md) §4.1.3 and consolidated in the
project's methodology document (kept local until publication).

## Data and software availability

The release artifacts are archived on Figshare (project "GenoAgent") with persistent DOIs:

| Item | Figshare type | License | DOI |
|---|---|---|---|
| **Benchmark cohort (n=1,047)** — `test_cases.jsonl` + provenance stages + manifest | Dataset | CC BY 4.0 | [`10.6084/m9.figshare.32814449`](https://doi.org/10.6084/m9.figshare.32814449) |
| **Methods / shared foundation** — corpus/index build recipe, ontology pins, cohort construction | Software | AGPL-3.0 | [`10.6084/m9.figshare.32814491`](https://doi.org/10.6084/m9.figshare.32814491) |
| **GenoAgent system** — agents, evaluation harness, per-cell results, manuscript artifacts | Software | AGPL-3.0 | [`10.6084/m9.figshare.32814497`](https://doi.org/10.6084/m9.figshare.32814497) |

The 323 GB Qdrant index and the raw LLM response dumps are **recipe-only** (mixed-licence verbatim PMC OA text): they are not deposited but regenerate bit-for-bit from public inputs via the methods item (index fingerprint `52,777,395` chunks; SHA-256 in `data/MANIFEST.tsv`). Upstream resources — Phenopacket Store v0.1.26, ontologies, Exomiser/LIRICAL, and the Qwen3-8B / PubMedBERT / MedCPT models — are referenced by pinned version (see [Reproducibility](#reproducibility)), not redistributed.

## Repository layout

```
geno_agent/
├── MASTER_PROJECT_v2.2.md            # Authoritative project spec (Phases 1A, 1B, 2, 3)
├── pyproject.toml                     # Pinned Python dependencies
├── docker-compose.yml                 # Qdrant v1.14.1 on :6533/:6534
├── .env.example                       # Template; copy to .env and fill in
├── scripts/
│   ├── corpus/                        # PMC OA fetch / parse / filter / chunk (Phase 1A §4)
│   ├── ontology/                      # Ontology download + verify (§3, §5)
│   ├── embedding/                     # PubMedBERT embedding (§4 step 4)
│   ├── indexing/                      # Qdrant create + validate (§4 steps 5-6)
│   ├── cases/                         # Phenopacket pipeline (Phase 1B §6)
│   │                                  # Stage 16 patched with --per-category-target (v3)
│   │                                  # Stage 17 patched to honour TEST_CASES_DIR (v3)
│   └── eval/                          # Phase 2 + Phase 3 evaluation
│       ├── run_factorial.py           # 16-cell factorial driver (earlier n=75 run)
│       ├── run_cell_k.py              # Cell K (Exomiser HPO-only)
│       ├── run_cell_m.py              # Cell M (LIRICAL HPO-only, v3, 8-worker pool)
│       ├── rerank_inside_d.py         # Cell L / S driver (CE-rerank-inside-D + optional LEA)
│       ├── run_paper_extension.sh     # Sequenced D → L → vLLM → S launcher
│       ├── run_paper_extension_LS_responses.sh  # v3 re-run with --responses-dir
│       ├── start_vllm.sh              # vLLM 0.20.1 with v3 VRAM caps
│       ├── aggregate_metrics.py       # Per-case → overall + per-MONDO bootstrap CIs
│       ├── run_ragas.py               # RAGAS faithfulness/precision/recall/relevance (GPT-4o)
│       ├── run_deepeval.py            # DeepEval hallucination (GPT-4o)
│       ├── run_lopo.py                # Leave-one-paper-out retrieval (source-paper exclusion)
│       ├── aggregate_lopo.py          # LOPO stratified + fair-cohort cross-tabs
│       ├── multiplicity_correction.py # Holm / Benjamini-Hochberg on primary comparisons
│       └── weighted_overall.py        # Stratum-weighted overall sensitivity
├── src/
│   ├── agents/                        # LangGraph state + 4 agent nodes + synthesizer_lea
│   ├── baselines/                     # exomiser_runner.py + lirical_runner.py (v3)
│   ├── api/                           # FastAPI (Phase 2b, deferred)
│   └── tools/                         # Qdrant search, HGNC, LLM wrapper
├── frontend/                          # Phase 2c CopilotKit React UI (deferred to post-paper)
├── tests/                             # Unit + integration
├── config/                            # Prompt templates, agent configs
├── reports/                           # All planning + results documents
│   ├── methodology.md                 # v3 consolidated technical methodology (authoritative)
│   ├── research_status_2026-06-22_n1047.md  # consolidated n=1,047 status + gap analysis
│   ├── paper_extension_plan_v2.md     # v2 plan (n=1,047, v0.1.26)
│   ├── paper_extension_plan_v3.md     # v3 plan (LIRICAL + RAGAS + Threads D-G)
│   ├── paper_extension_results.md     # v2 final results (each above also has a .html)
│   ├── tables/                        # supplementary tables (e.g. multiplicity correction)
│   └── _archive_n75/           # superseded n=75-era reports + v1 plan (n=460)
└── data/                              # Manifests + ontologies (large files .gitignored)
    ├── test_cases/                    # n=75 earlier cohort (v0.1.19)
    ├── test_cases_500/                # n=459 paper v1 cohort (v0.1.19, seed 4242)
    ├── test_cases_1050/               # n=1,047 paper v2/v3 cohort (v0.1.26, seed 42)
    ├── eval/                          # n=75 earlier results (16 cells)
    ├── eval_500/                      # n=459 v1 results (4 cells K/D/L/S)
    ├── eval_1050/                     # n=1,047 v2/v3 results (5 cells K/D/L/S/M + sidecars)
    └── eval_1050_lopo_full/           # leave-one-paper-out results (summaries; per-case sidecars gitignored)
```

Persistent heavy artifacts (Qdrant index, Qwen3-8B weights, raw corpus, logs) live outside the repository under `~/rare-disease-rag/` to keep the git history clean. The `frontend/` directory will hold a standalone Next.js + CopilotKit project; the upstream CopilotKit framework lives at the user's fork [`github.com/Jangulo7/agent_UI`](https://github.com/Jangulo7/agent_UI) and is consumed via npm rather than vendored.

## Quick start

> The Phase 1A/1B pipeline and the full n=1,047 evaluation are complete and reproducible. The steps below set up the infrastructure; per-cell evaluation drivers live in `scripts/eval/`, and the consolidated methodology is kept as a local document (private until publication).

```bash
# 1. Clone and enter
git clone https://github.com/Jangulo7/geno_agent.git
cd geno_agent

# 2. Configure environment
cp .env.example .env
# Edit .env to match your local paths and ports

# 3. Bring up local Qdrant (uses bind-mount to ~/rare-disease-rag/qdrant_storage/)
mkdir -p ~/rare-disease-rag/qdrant_storage
docker compose up -d
curl http://localhost:6533/healthz   # expect: healthz check passed

# 4. Set up Python environment (recommend uv)
uv venv
source .venv/bin/activate
uv pip install -e .
```

Detailed Phase 1A and 1B execution instructions are in
[`MASTER_PROJECT_v2.2.md`](MASTER_PROJECT_v2.2.md). The full paper-extension
methodology and per-version execution plans are kept as local working documents
(private until publication).

## Hardware

The reference deployment targets a single workstation:
- NVIDIA RTX 5090 (32 GB VRAM)
- 64 GB system RAM
- ~700 GB Linux storage for Qdrant index and models
- WSL2 Ubuntu 24.04 on Windows host

The architecture should run on any GPU with ≥24 GB VRAM and is GPU-required for the embedding pipeline; the agent layer can run CPU-only on smaller-context models if VRAM is tight.

## Citation

A peer-reviewed manuscript derived from this work is in preparation for
submission to *Genome Medicine* (fallbacks: *Bioinformatics*, *JAMIA*,
*Briefings in Bioinformatics*). In the interim, please cite this repository:

```bibtex
@misc{angulo2026geno_agent,
  author       = {Angulo, Johanna},
  title        = {geno\_agent: An Agentic-Workflow RAG System for
                  Gene Prioritization in Rare Mendelian Disease},
  year         = {2026},
  howpublished = {\url{https://github.com/Jangulo7/geno_agent}},
  note         = {Doctoral first paper (Universidad Europea de Madrid; n=1,047; target: Genome Medicine).}
}
```

Headline finding to cite (n=1,047, deconfounded):

> On the fair-comparison cohort (overlap-absent, n=282) of Phenopacket Store v0.1.26, geno_agent (multi-agent + MedCPT cross-encoder rerank + Qwen3-8B LEA) is the top-ranked system (top-1 0.858), significantly exceeding Exomiser HPO-only (+0.078, p=0.015) and LIRICAL HPO-only (+0.082, p=0.014) — both surviving Holm multiplicity correction. LIRICAL's apparent overall top-1 (0.924) is largely an annotation-overlap artefact (it ties Exomiser once overlap is removed). A leave-one-paper-out analysis confirms geno_agent's advantage does not depend on retrieving each case's own source publication (fair-cohort top-1 unchanged, 0.858 → 0.858). On the full cohort, Cell S also exceeds Exomiser HPO-only (Δ = +0.034, 95 % CI [+0.006, +0.064]).

## License

The code in this repository is released under the **GNU Affero General Public License v3.0 (AGPL-3.0)** (see [`LICENSE`](LICENSE)). Note that the redistributable artifacts have their own licenses — PMC OA articles retain their original publisher licenses, ontologies (HPO, MONDO, GO) are CC BY 4.0, and HGNC data is publicly available without restriction. Pinned versions and SHA-256 hashes for every external dataset are recorded in `data/MANIFEST.tsv`.

## Acknowledgments

This is doctoral research at Universidad Europea de Madrid,
supervised by [advisor name to be added]. It builds on the open ecosystem of biomedical NLP
and bioinformatics — particularly the Monarch Initiative (Phenopacket Store,
HPO, MONDO), the [LIRICAL](https://github.com/TheJacksonLaboratory/LIRICAL) and
[Exomiser](https://exomiser.readthedocs.io/) teams, the
[NCBI MedCPT](https://github.com/ncbi/MedCPT) authors, the
[Qwen team](https://huggingface.co/Qwen), and the maintainers of PMC Open Access
and Qdrant — without which a project of this scope would not be possible from a
single workstation.

## Contact

Issues and pull requests are welcome via GitHub. For research correspondence: [email to be added].
