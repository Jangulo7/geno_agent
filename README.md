# geno_agent

**An Agentic-Workflow RAG System for Gene Prioritization in Rare Mendelian Disease**

> **Doctoral first paper** (Universidad Europea de Madrid; n=1,047). An
> end-to-end agentic-workflow RAG system for literature-based causal gene
> prioritisation in rare Mendelian disease.
>
> **Headline (n=1,047, overlap-absent subset).** The cohort's cases derive from only
> 415 source publications, so all inference clusters on source publication (a
> publication-level bootstrap and a cluster-level permutation test). Under that
> inference, on the *overlap-absent subset* — cases whose source publication is
> **not** cited by `phenotype.hpoa` for the causal gene — geno_agent (Cell S) has
> the highest top-1 (**0.858** vs Exomiser 0.780 and LIRICAL 0.777) but the margins
> are **not statistically significant** (p=0.45 and 0.41): 20 of the 22 net
> discordances against Exomiser come from a single publication. geno_agent is
> therefore reported as **matching**, not beating, the curated baselines at rank 1.
>
> **What does survive clustered inference:** the contribution of retrieval and the
> agentic workflow over the identical backbone LLM (**+0.191**, p<0.001); the
> advantage over Exomiser on post-2020 source publications (**+0.094**,
> Holm p=0.002); and the hard-cohort margin over Exomiser (**+0.153**,
> Holm p=0.002). A **leave-one-paper-out** check confirms none of this depends on
> retrieving each case's own source paper (overlap-absent top-1 unchanged,
> 0.858 → 0.858, McNemar p=1.0).
>
> **The main result is the instrument, not the system.** 73.1% of
> cases have their source publication cited by `phenotype.hpoa`, and removing that
> overlap erases LIRICAL's 23-point lead over Exomiser entirely (0.924 → 0.777;
> tied with Exomiser, p=1.000). Every system with no exposure to `phenotype.hpoa`
> scores *higher* on the overlap-absent subset while LIRICAL alone scores lower —
> a system × overlap interaction of **+0.382** (p≈1e-27) that survives clustering,
> standardisation for disease composition, and adjustment for annotation density.
>
> geno_agent is a **literature-only** rare-disease gene-prioritisation system (no
> curated phenotype-gene tables); **production inference runs entirely on local
> hardware** — only the optional RAGAS evaluation judge (used for measurement, not
> prioritisation) requires an external OpenAI-compatible LLM endpoint (GPT-4o).
>
> **Latest update (2026-07-26).** Re-analysed the saved per-case artefacts with
> publication-clustered inference, design weighting, and an annotation-density
> adjustment; added a prompt-sensitivity replay. Nothing was re-run — the
> artefacts are unchanged. See
> [Verifying the reported numbers](#verifying-the-reported-numbers). Earlier
> (2026-07-01): the **difficulty × leakage 2×2** — a case-paired *hard* cohort with
> 49 phenotype-similar distractors (HPO Resnik best-match-average) crossed with the
> annotation-overlap axis. Earlier (2026-06-11): full n=1,047 evaluation —
> annotation-overlap flagging, publication-recency stratification,
> three-LLM-family ablation, **leave-one-paper-out**, and **Holm /
> Benjamini–Hochberg** multiplicity correction.

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
3. **Local, consumer-GPU deployment** — the system runs end-to-end on a single workstation (NVIDIA RTX 5090, 32 GB VRAM) using [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) as the reasoning model and [PubMedBERT](https://huggingface.co/microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext) for biomedical embeddings. No external API dependencies *at inference time*, no per-call cost, no data leaving the workstation — important for both reproducibility and any future extension to protected clinical data. (The optional RAGAS evaluation judge is the sole component that calls an external OpenAI-compatible LLM endpoint — GPT-4o in this study — used only to *measure* rationale quality, never for gene prioritisation.)
4. **A standardized, difficulty-controlled benchmark** built on the [GA4GH Phenopacket Store](https://github.com/monarch-initiative/phenopacket-store) (v0.1.26 for the paper; v0.1.19 for the earlier cohort), with deterministic stratified case selection (neurological, metabolic, immunological, developmental) and **two case-paired distractor variants** — *standard* (49 uniformly-random HGNC protein-coding genes) and *hard* (49 phenotypically most-similar genes by HPO Resnik best-match-average). Crossed with a per-case annotation-overlap (leakage) flag, these form a **difficulty × leakage 2×2**. The benchmark itself is fully seeded — every case, distractor list, and stratification label regenerates bit-for-bit from public inputs; the LLM-dependent evaluation results reproduce to within vLLM's near-deterministic decoding (~98% per-case rank stability, with the **top-1 metric bit-identical** across independent runs — see [Reproducibility](#reproducibility) for the exact determinism contract).

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
| **O** | LLM-only, no retrieval (same Qwen3-8B backend, no agents/retrieval) | Control — isolates the joint value of retrieval + the agentic workflow |

Test cases (n=1,047) are sampled from GA4GH Phenopacket Store **v0.1.26**
using disproportionate stratified sampling (250 dev + **300 imm** + 250 met +
247 neuro; immunological oversampled for subgroup statistical power). The
earlier n=75 and n=459 (paper-v1) cohorts remain in the repo for the audit
trail.

**Distractor-difficulty variants.** Each case carries a fixed 50-gene candidate
list (1 causal + 49 distractors), built in two **case-paired** variants that differ
*only* in the distractors: a **standard** cohort with 49 uniformly-random HGNC
protein-coding genes (genome-wide separability) and a **hard** cohort with the 49
phenotypically most-similar genes by HPO Resnik best-match-average
(differential-diagnosis stress test). Crossing distractor difficulty with the
annotation-overlap (leakage) axis yields a **difficulty × leakage 2×2**; the fair
(overlap-absent, n=282) split is the identical case set in both variants, so
difficulty is varied orthogonally to leakage.

**Headline results at n=1,047 (v2 final, tagged `paper-v2-final`):**

| Cell | top-1 | top-5 | top-10 | MRR | Notes |
|---|---:|---:|---:|---:|---|
| K (Exomiser HPO-only) | 0.691 | 0.821 | 0.859 | 0.754 | curated baseline |
| M (LIRICAL HPO-only) | 0.924 | 0.989 | 0.999 | 0.953 | likely annotation overlap; see v3 Thread D |
| D (multi+hybrid) | 0.460 | 0.581 | 0.628 | 0.529 | inside-system baseline |
| L (D + CE-rerank) | 0.698 | 0.791 | 0.814 | 0.745 | +23.8 pp rerank contribution |
| **S (L + LEA)** | **0.725** | 0.798 | 0.816 | **0.766** | **+3.4 pp over K (★ paired bootstrap)** |
| O (LLM-only, no retrieval) | 0.511 | 0.626 | 0.697 | 0.575 | control: −0.215 vs S (McNemar p<0.001) |

**Metrics:** top-1 / top-5 / top-10 (Recall@k), MRR, NDCG@10. Paired
bootstrap 95 % CIs (1,000 resamples, seed 42). Sensitivity probes
(leave-one-out, leave-N-out, permutation, McNemar) on load-bearing claims.

### Curation-overlap analysis & robustness (n=1,047, complete)

- **Annotation-overlap flag.** A per-case flag marks whether the source
  publication is cited by `phenotype.hpoa` for the causal gene's OMIM disease
  (cohort overlap rate 73.1 %). On the **fair cohort (overlap-absent, n=282)**,
  geno_agent is #1 (top-1 **0.858**) vs Exomiser 0.780 (**+0.078 ★**) and LIRICAL
  0.777 (**+0.082 ★**); LIRICAL's apparent overall 0.924 collapses to a tie with
  Exomiser, quantifying its training-data exposure.
- **LLM-only ablation (retrieval + workflow value).** An LLM-only control
  (Cell O; the same Qwen3-8B backend with no retrieval and no agents) reaches
  top-1 **0.511 overall / 0.667 fair** — a non-trivial parametric baseline, but
  geno_agent adds **+0.215 overall / +0.191 fair** (McNemar p<0.001), isolating
  the joint contribution of retrieval and the agentic workflow. Unlike the curated
  tools, the LLM-only score *rises* on the fair cohort (0.454 → 0.667): parametric
  knowledge is orthogonal to `phenotype.hpoa` citation, independently corroborating
  that the fair split removes a curated-tool confound rather than a difficulty
  effect. (Grammar-constrained decoding was evaluated and rejected — at
  temperature 0 it distorted the backbone; Cell O uses free-form generation with a
  tolerant JSON/regex parser.)
- **Leave-one-paper-out (LOPO).** Excluding each case's own source publication
  from retrieval leaves the fair cohort **completely unchanged** (0.858 → 0.858,
  McNemar p=1.0); the small full-cohort effect (−0.015) is confined to the
  overlap-present subset. geno_agent's signal is distributed across the
  literature, not concentrated in the source case report.
- **Distractor-difficulty stress test (hard cohort).** Replacing the 49 random
  distractors with the 49 phenotype-similar genes (Resnik BMA) drops every system,
  but on the fair cohort geno_agent **remains #1 (top-1 0.390)** and its margin
  *widens*: **+0.152** vs Exomiser (McNemar p=1×10⁻⁵) and **+0.106** vs LIRICAL
  (p=0.0021), both surviving Holm correction. LIRICAL collapses full→fair
  (0.642 → 0.284) while geno_agent *improves* (0.303 → 0.390); retrieval stays
  strong (fair top-10 **0.812**), so the residual difficulty is rank-1
  discrimination among phenotype-confusable genes. The GPT-4o judge localises this:
  top-1 rationale faithfulness holds (0.507 vs 0.480) while full-response
  faithfulness falls (0.286 → 0.211) and retrieved-context precision drops
  sharply (0.650 → 0.308), i.e. the hard regime stresses grounded
  discrimination, not retrieval recall.
- **Publication-recency stratification.** Exomiser top-1 collapses 0.847 → 0.480
  on post-2020 source papers; geno_agent's edge over Exomiser is 2.7× larger on
  recent cases.
- **LLM-family ablation.** Replaying the LEA prompts across three frontier LLMs
  spanning three independent model families converges within 2.4 pp on the fair
  cohort — the headline is robust to model family.
- **Statistical rigor.** Inference clusters on source publication: the 1,047
  cases come from 415 papers, so case-level intervals understate variance. Under
  publication-clustered inference geno_agent **matches** rather than exceeds the
  curated baselines on the overlap-absent subset (p=0.45 and 0.41), and the
  design-weighted margins shrink further. What survives clustering is the
  retrieval-and-scaffold contribution over the identical backbone (+0.191), the
  post-2020 advantage over Exomiser (+0.094) and the hard-cohort margin over
  Exomiser (+0.153). See [Verifying the reported numbers](#verifying-the-reported-numbers).
- **RAG quality (GPT-4o judge).** RAGAS faithfulness on the committed rank-1
  rationale is **0.480** (95% CI 0.424–0.533); the multi-claim full-response
  measurement is **0.286**, reported as a conservative lower bound because it
  scores deliberate "no direct evidence" abstentions as unsupported claims.
  Faithfulness predicts top-1 correctness with an AUROC of **0.73**, which is
  moderate discrimination — enough to motivate prospective evaluation of a
  triage flag, not enough to specify a deployable operating point.

## Project status

| Phase | Description | Status |
|---|---|---|
| 1A (scripts) | PMC OA pipeline scripts validated | ✅ Complete |
| 1A (production) | 52.78 M chunks indexed in Qdrant `geno_agent_pmc_oa_v1` | ✅ Complete |
| 1B (test set v1) | n=75 earlier cohort (v0.1.19, seed 42) | ✅ Complete |
| 1B (test set v2) | n=459 paper v1 (v0.1.19, seed 4242) | ✅ Complete |
| **1B (test set v3)** | **n=1,047 paper extension (v0.1.26, seed 42, disproportionate 250+300+250+250)** | ✅ Complete |
| 2a | LangGraph 4-agent state graph + Qwen3-8B/vLLM | ✅ Complete |
| Eval (earlier n=75) | 16-cell factorial at n=75 | ✅ Complete |
| **Eval (paper v2)** | **5 cells × n=1,047, bootstrap CIs, per-MONDO breakdown, LIRICAL** | ✅ Complete |
| **Eval (paper v3)** | **LEA logging + RAGAS + annotation-overlap + recency + LLM-family ablation** | ✅ Complete |
| **Robustness** | **Leave-one-paper-out + Holm/BH multiplicity correction + stratum-weighted sensitivity** | ✅ Complete (2026-06-11) |
| **Difficulty × leakage 2×2** | **Hard (phenotype-similar distractor) cohort + hard-cohort RAGAS** | ✅ Complete (2026-07-01) |

Reports: the consolidated methodology, execution plans, and result write-ups are
maintained as **local working documents and kept private until publication** — the
README is the single explanatory document in the repo. The published results and
benchmark are available through the Figshare deposits (see
[Data and software availability](#data-and-software-availability)); `reports/`
retains the rendered **figures, tables, and method descriptors**.

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
| PubMedBERT dense embedder      | `NeuML/pubmedbert-base-embeddings` @ `b79526d6ef3645e0df4530322e266f24c829f5ef` |
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

The full reproducibility specification is kept in the project's local methodology
document (private until publication); the pinned versions and SHA-256 hashes below,
together with `data/MANIFEST.tsv`, are the reproducibility-critical subset.

### Verifying the reported numbers

Every number in the evaluation write-up is produced by a committed script under
`scripts/eval/revision/` and written to a machine-readable file under
`reports/p2_revision/`, so a reader can check any figure without re-running the
pipeline. All are deterministic at seed 42 and read only saved per-case
artefacts — none re-runs model inference, except the prompt-sensitivity replay.

| Script | Produces | What it establishes |
|---|---|---|
| `provenance_checks.py` | `wp1a_coverage_check.json`, `wp1d_baseline_versions.json`, `wp9b_tie_handling.json` | The retrieval index never gated cohort membership; LIRICAL read the same pinned `phenotype.hpoa` the overlap flag is computed against; how each baseline breaks rank ties |
| `interaction_test.py` | `wp3_did.json` | Per-system overlap shift, the system × overlap interaction, and directly standardised estimates |
| `cluster_inference.py` | `wp4_cluster_inference.json`, `wp4_unique_pmids.json` | Publication-clustered intervals and paired tests for every reported contrast, with the case-level result alongside |
| `design_weighted.py` | `wp5_design_weighted.json` | Horvitz–Thompson estimates for the eligible population using the released inclusion probabilities |
| `annotation_density.py` | `wp6_annotation_density.json`, `wp6_case_density.csv` | Whether curation depth, rather than annotation exposure, explains the overlap effect |
| `metric_audit.py` | `wp7_full_stratum_table.csv`, `wp7_metric_audit.{csv,json}` | All cells × metrics × subsets for both candidate-list variants, and a diff of every previously reported value |
| `judge_provenance.py` | `wp8_judge_provenance.json` | Judge-run provenance with intervals, triage operating characteristics, and as-run vs error-excluded ablation estimates |
| `prompt_sensitivity.py` | `wp8d_prompt_sensitivity.json`, `data/eval_1050/prompt_sensitivity/` | Sensitivity of the result to prompt wording, replaying cached retrieval so only the LEA stage re-runs |
| `cutoff_asymmetry.py` | `wp9c_cutoff_asymmetry.json`, `wp9c_pmcid_dates.json` | How much retrieved evidence postdates the curated tools' annotation release |
| `render_supp_tables.py` | Supplementary Tables S2, S3 | Multiplicity correction and design-weighted estimates, as standalone documents |
| `consistency_check.py` | — | Cross-checks cohort counts, pinned versions and DOIs against the companion resource paper; verifies no orphan or stale claims and that references are complete and sequential |
| `latex_lint.py` | — | Structural checks on a `.tex` without compiling it |

Two properties of the evaluation are worth knowing before reusing this cohort:

- **Cases are clustered within source publications.** The 1,047 cases derive from
  415 publications (mean 2.5, max 42), and the overlap-absent subset carries 282
  cases from only 93. Intervals and tests must cluster on source PMID — a
  publication-level bootstrap rather than resampling cases — or they will be too
  narrow. `cluster_inference.py` reports both so the difference is visible.
- **The cohort is a disproportionate stratified sample.** Unweighted pooled
  metrics describe the sampled cohort, not the eligible population, which is
  ~67 % neurological. Use the released inclusion probabilities for a
  population-level estimate; `design_weighted.py` does this.

```bash
PY=/path/to/python
$PY scripts/eval/revision/provenance_checks.py
$PY scripts/eval/revision/interaction_test.py
$PY scripts/eval/revision/cluster_inference.py     # ~70 s (10k cluster resamples)
$PY scripts/eval/revision/design_weighted.py
$PY scripts/eval/revision/annotation_density.py
$PY scripts/eval/revision/metric_audit.py
$PY scripts/eval/revision/judge_provenance.py
$PY scripts/eval/revision/cutoff_asymmetry.py      # needs network (NCBI E-utilities)
```

## Data and software availability

The release artifacts are archived on Figshare (project "GenoAgent") with persistent DOIs:

| Item | Figshare type | License | DOI |
|---|---|---|---|
| **Benchmark cohort — standard (n=1,047)** — random distractors; `test_cases.jsonl` + provenance + manifest | Dataset | CC BY 4.0 | [`10.6084/m9.figshare.32814449`](https://doi.org/10.6084/m9.figshare.32814449) |
| **Benchmark cohort — hard (n=1,047)** — phenotype-similar (Resnik BMA) distractors; case-paired with the standard set | Dataset | CC BY 4.0 | [`10.6084/m9.figshare.32816468`](https://doi.org/10.6084/m9.figshare.32816468) |
| **Methods / shared foundation** — corpus/index build recipe, ontology pins, cohort construction | Software | AGPL-3.0 | [`10.6084/m9.figshare.32814491`](https://doi.org/10.6084/m9.figshare.32814491) |
| **GenoAgent system** — agents, evaluation harness, per-cell results, figures + tables | Software | AGPL-3.0 | [`10.6084/m9.figshare.32814497`](https://doi.org/10.6084/m9.figshare.32814497) |

The 323 GB Qdrant index and the raw LLM response dumps are **recipe-only** (mixed-licence verbatim PMC OA text): they are not deposited but regenerate from public inputs via the methods item. What regenerates is the indexed **content** — which chunks exist, under which content-addressed identifiers — verifiable against the chunk-set fingerprint below. The Qdrant collection itself is *not* byte-identical across builds: HNSW graph construction depends on insertion order and concurrency, and dense vectors are computed in FP16 on GPU, so two builds from identical inputs are content-equivalent rather than binary-identical. Upstream resources — Phenopacket Store v0.1.26, ontologies, Exomiser/LIRICAL, and the Qwen3-8B / PubMedBERT / MedCPT models — are referenced by pinned version (see [Reproducibility](#reproducibility)), not redistributed.

### Index fingerprint and substrate validation

The retrieval index is released as a build recipe, so it needs a way to be
*checked*. `release/index_fingerprint/` carries that (all values also in
`data/MANIFEST.tsv`):

| Quantity | Value |
|---|---|
| Distinct `chunk_id` values | **52,777,395** (= Qdrant `points_count`) |
| SHA-256 over the sorted, deduplicated `chunk_id` list | `70759656…aa39ea` |
| Per-PMCID chunk-count manifest (`chunk_counts_by_pmcid.tsv`, 2,249,438 rows) | `639eae12…8a1769` |

Recompute with `scripts/corpus/compute_chunk_fingerprint.sh`. Two steps are
load-bearing and a rebuild will not match without them: `LC_ALL=C` byte ordering,
and **deduplication** — `chunk_id` is a content-addressed UUID5, so a resumed
build can re-emit a record an earlier pass already wrote, and that record upserts
onto the same point. The released build emitted 52,782,789 records containing
5,394 such duplicates; the distinct count matching `points_count` exactly is what
confirms the upserts were idempotent.

Two index-level characterisations (`retrieval_substrate_validation.json`, from
`scripts/eval/validate_retrieval_substrate.py`) establish that the substrate
retrieves something useful — properties of the corpus and retrieval configuration
alone, with no ranker, LLM or prioritisation tool involved:

- **Source-article recall.** Of the 415 unique source publications behind the
  cohort, only **130 (31.3 %)** are in the index — 174 have no PMC record at all.
  Among the 345 cases whose source article *is* indexed, a single unrefined query
  recovers it in the top-100 chunks for 35.7 % (gene symbol) to 37.4 % (HPO
  labels) of cases.
- **Symbol grounding.** A mean of 18.6 % of the top-100 chunks returned for a gene
  symbol contain that symbol under a case-sensitive word-boundary match; no gene
  among the 100 sampled returned zero literal matches.

Cohort-level analysis caveats are quantified in `release/cohort/`: the 1,047 cases
derive from only **415 unique publications** (`clustering_stats.json`), so
per-case metrics are not independent observations and intervals should cluster on
source PMID; and the four strata were sampled at inclusion probabilities from
0.769 down to 0.0786, so unweighted pooling estimates a design-defined quantity.

## Repository layout

```
geno_agent/
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
│       ├── run_cell_o.py              # Cell O (LLM-only, no-retrieval control)
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
│   └── tools/                         # Qdrant search, HGNC, LLM wrapper
├── tests/                             # Unit + integration
├── config/                            # Prompt templates, agent configs
├── reports/                           # Tracked: method descriptors, figures, tables
│   ├── dataset-development-method.md  # cohort + distractor-variant construction
│   ├── annotation-overlap-method.md   # leakage-flag computation
│   ├── architecture/                  # geno_agent_architecture.md
│   ├── figures/                       # publication figures (regenerated from committed data via `scripts/`)
│   └── tables/                        # supplementary tables (e.g. multiplicity correction)
└── data/                              # Manifests + ontologies (large files .gitignored)
    ├── test_cases/                    # n=75 earlier cohort (v0.1.19)
    ├── test_cases_500/                # n=459 paper v1 cohort (v0.1.19, seed 4242)
    ├── test_cases_1050/               # n=1,047 paper v2/v3 cohort (v0.1.26, seed 42)
    ├── eval/                          # n=75 earlier results (16 cells)
    ├── eval_500/                      # n=459 v1 results (4 cells K/D/L/S)
    ├── eval_1050/                     # n=1,047 v2/v3 results (5 cells K/D/L/S/M + sidecars)
    └── eval_1050_lopo_full/           # leave-one-paper-out results (summaries; per-case sidecars gitignored)
```

Persistent heavy artifacts (Qdrant index, Qwen3-8B weights, raw corpus, logs) live outside the repository under `~/rare-disease-rag/` to keep the git history clean.

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

The full paper-extension methodology and per-version execution plans are kept as
local working documents (private until publication); the reproducible pipeline is
the `scripts/` drivers plus the pinned versions above.

## Hardware

The reference deployment targets a single workstation:
- NVIDIA RTX 5090 (32 GB VRAM)
- 64 GB system RAM
- ~700 GB Linux storage for Qdrant index and models
- WSL2 Ubuntu 24.04 on Windows host

The architecture should run on any GPU with ≥24 GB VRAM and is GPU-required for the embedding pipeline; the agent layer can run CPU-only on smaller-context models if VRAM is tight.

## Citation

This work is being prepared for peer-reviewed publication. In the interim,
please cite this repository:

```bibtex
@misc{angulo2026geno_agent,
  author       = {Angulo, Johanna},
  title        = {geno\_agent: An Agentic-Workflow RAG System for
                  Gene Prioritization in Rare Mendelian Disease},
  year         = {2026},
  howpublished = {\url{https://github.com/Jangulo7/geno_agent}},
  note         = {Doctoral first paper (Universidad Europea de Madrid; n=1,047).}
}
```

Headline finding to cite (n=1,047, overlap-absent subset):

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
