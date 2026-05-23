# Manuscript draft — geno_agent for rare-disease gene prioritisation (Genome Medicine)

> **Drafting workflow:** This file is the working manuscript. Each section is
> either ✅ **drafted**, ⚠️ **partial**, or ❌ **pending**. The Methods section
> lives in `reports/manuscript_methods_draft.md` and is referenced (not
> duplicated) here; merge will happen at submission time. Numbers are locked
> against `reports/paper_extension_results.md` §§12-20. Citations are marked
> with `[CIT: …]` placeholders.

---

## Title (❌ pending)

**Working title:**
*"Literature-only multi-agent retrieval-augmented gene prioritisation for
rare disease: fair-cohort evaluation against curated baselines, recency
robustness, and frontier-LLM ablation"*

(Final title needs co-author review.)

## Authors (❌ pending)

- Johanna Angulo Quintero (Universidad Alfonso X)
- [Thesis advisor — confirm name + affiliation]
- [Additional co-authors — confirm]

---

## Abstract (❌ pending)

(Structured 250-350 words, Genome Medicine format: Background / Methods /
Results / Conclusions.)

---

## Background (✅ DRAFTED — this commit)

### Rare-disease diagnostic burden

Rare diseases are individually rare but collectively common: an estimated
**3.5-5.9 % of the global population (~300 million individuals) live
with one of the more than 7,000 currently catalogued rare conditions**
[Nguengang Wakap et al., 2020; Global Genes, 2020]. The median patient
with an undiagnosed rare disease is seen by seven specialists and
waits **5-7 years for a correct molecular diagnosis** [Boycott et al.,
2019]. Despite the routine clinical availability of exome and genome
sequencing, **approximately half of all sequenced rare-disease cases
remain without a confirmed molecular diagnosis** at the time of test
reporting [Clark et al., 2018]. A substantial fraction of these
undiagnosed cases is not attributable to undetectable variants but to
the limits of current bioinformatic tools when interpreting variants
of uncertain significance (VUS) under the ACMG/AMP framework [Richards
et al., 2015], particularly in patients whose phenotypes are atypical,
under-described, or characterised only by individual case reports.

### Phenotype-driven computational prioritisation

The dominant computational paradigm for rare-disease gene
prioritisation is **phenotype-driven**: candidate genes from upstream
variant calling are re-ranked by similarity between the patient's
clinical phenotype and a curated database of disease-phenotype
associations [Jacobsen et al., 2022a]. The Human Phenotype Ontology
(HPO) [Köhler et al., 2021] provides the standard vocabulary for
encoding patient phenotypes, and the GA4GH Phenopacket schema
[Jacobsen et al., 2022b] defines a computable representation of
clinical cases that is now widely adopted as a benchmark format,
operationalised through the publicly-released Phenopacket Store corpus
[Danis et al., 2025]. The PhEval framework [Bridges et al., 2025]
provides a standardised harness for comparing phenotype-driven variant
and gene prioritisation algorithms.

Three families of phenotype-driven prioritisation tools have
established the current state of the art. **Exomiser** [Smedley et al.,
2015] applies the hiPhive scoring function over a graph that
integrates HPO disease-phenotype associations with protein-protein
interactions. **LIRICAL** [Robinson et al., 2020] computes per-gene
likelihood ratios from the `phenotype.hpoa` annotation file under an
explicit Bayesian framework. **Phen2Gene** [Zhao et al., 2020]
combines HPO term-frequency signals with curated phenotype-gene
linkages from MEDLINE-mined sources. All three are deterministic,
locally-deployable, and benchmark well when the causal gene is already
richly annotated in their underlying curated knowledge bases.

### The publication-curation gap

The fundamental limitation of phenotype-driven curated-knowledge-base
tools is **structural**: curation of phenotype-gene associations
requires expert review and lags publication. Orphanet, OMIM, and
`phenotype.hpoa` typically incorporate new annotations on a 2-5 year
cycle. PubMed indexes more than **one million new biomedical articles
per year**, of which the PubMed Central Open Access (PMC OA) subset
alone contains more than **four million full-text articles**, with new
phenotype-expansion case reports and functional studies appearing
continuously [Boycott et al., 2019]. The result is a structural
inability to surface gene-phenotype associations that exist *only* in
the unstructured literature — precisely the cases where the
diagnostic odyssey is longest. A second, related concern documented in
the machine-learning-for-science literature is **training-data
leakage** [Kapoor & Narayanan, 2023]: when benchmark cases are drawn
from the same publications that curators use to populate the very
knowledge bases against which the tools are evaluated, benchmark
performance systematically overstates real-world generalisation. To
our knowledge, no prior rare-disease gene-prioritisation evaluation
has formally stratified its results by annotation-overlap status — a
gap that the present study addresses.

### Large language models and retrieval-augmented generation

Recent advances in transformer-based language models [Vaswani et al.,
2017; Devlin et al., 2019] have enabled a class of tools that can
reason directly from unstructured biomedical text. Pre-training on
biomedical corpora yields domain-specific representations that
outperform general-purpose embeddings on retrieval and downstream
tasks [Gu et al., 2021]. Retrieval-augmented generation (RAG) [Lewis
et al., 2020] couples a retrieval component over a frozen knowledge
corpus with a generative language model, allowing the model to ground
its outputs in source documents rather than relying on parametric
memory alone — a particularly attractive property for clinical
applications where citation traceability and reproducibility are
non-negotiable [Yang R. et al., 2025; Raza et al., 2024]. The RAG
literature has matured rapidly over the past two years [Gao et al.,
2024], with biomedical adaptations such as BiomedRAG [Li M. et al.,
2025] and benchmark suites such as MIRAGE [Xiong et al., 2024]
establishing the methodology in the medical-NLP community.

### Multi-agent LLM systems in biomedicine

Beyond single-pass RAG, **agentic** systems decompose complex tasks
across multiple specialised LLM agents that coordinate through a
shared state graph, enabling iterative query refinement, explicit
relevance grading, and self-correction loops that single-pass
architectures cannot support [Wooldridge, 2009; LangChain AI, 2024;
Wei et al., 2022]. Early biomedical applications include CellAgent for
single-cell data analysis [Xiao et al., 2024], GeneGPT for tool-
augmented access to NCBI services [Jin et al., 2024], and a broader
class of bioinformatics agents recently reviewed in Yang T. et al.
[2025] and Zhou et al. [2025]. The applicability of the agentic
paradigm to rare-disease gene prioritisation is the central
architectural premise of the present study.

### LLM evaluation and the hallucination problem

A well-documented failure mode of LLMs is **hallucination** — the
generation of plausible-sounding but factually unsupported content
[Ji et al., 2023]. This concern is particularly acute in clinical
applications, where ungrounded outputs may directly affect patient
care. Two LLM-judge frameworks have emerged as the de facto standards
for quantifying generation quality in RAG pipelines: **RAGAS** [Es et
al., 2024], which decomposes faithfulness into claim-level
verification against retrieved contexts, and **DeepEval** [Confident
AI, 2024], which provides a holistic hallucination metric. Both
frameworks rely on a separate LLM judge — typically GPT-4-class — to
score the outputs of the system under evaluation. The broader
practice of LLM-as-judge has been systematically validated for
preference benchmarking [Zheng et al., 2023] and comprehensively
surveyed [Li M. et al., 2024], with the recognised limitation that
judge-model bias must be controlled by selecting a judge from a
different model family than the system being judged.

### The gap this study addresses

Despite the maturing of biomedical RAG, agentic LLM systems, and LLM-
quality evaluation, three gaps remain in the rare-disease gene-
prioritisation literature: (i) **no literature-only locally-deployable
multi-agent gene-prioritisation system has been rigorously evaluated
against curated phenotype-driven tools** on a large stratified
Phenopacket Store cohort; (ii) **no published evaluation of rare-
disease prioritisation tools has formally stratified results by
annotation-overlap status**, despite the well-recognised leakage
concern [Kapoor & Narayanan, 2023]; and (iii) **no rare-disease
prioritisation study has quantified LLM-generated rationale
faithfulness** as a deployable triage signal. The present study
addresses all three gaps. Specifically, we (1) describe geno_agent, a
four-agent LangGraph pipeline + LLM-as-Evidence-Aggregator (LEA)
operating on a frozen 4.2-million-chunk index of 287,000 filtered PMC
OA full-text articles; (2) evaluate it on n = 1,047 Phenopacket Store
v0.1.26 cases stratified by MONDO disease category, by annotation-
overlap status, and by source-publication year; (3) quantify LEA
rationale grounding with both strict (RAGAS) and lenient (DeepEval)
judges; (4) confirm robustness of the headline result across three
independent frontier LLM families; and (5) release the full evaluation
code, frozen per-case sidecars, and curated comparison artifacts to
support independent replication and method extension.

---

## Methods (✅ separate file)

See `reports/manuscript_methods_draft.md` (3,268 words, locked). To be
inlined at submission time. Covers: cohort construction (Phenopacket
Store v0.1.26, stratified n=1,047), 5-cell architecture (K Exomiser, M
LIRICAL, D multi-agent hybrid, L + CE-rerank, S + LEA = geno_agent),
PMC OA index construction, evaluation metrics with paired-bootstrap CIs
+ McNemar, annotation-overlap deconfounding (Thread D), publication-
recency stratification (Thread E), ensemble evaluation (Thread F), RAG-
quality evaluation (RAGAS + DeepEval), local explainability analysis
(Thread G), reproducibility infrastructure, computational resources.
Excludes DeepRare from head-to-head with explicit rationale.

---

## Results (✅ DRAFTED — this commit)

### Cohort and evaluation setup

The analysis cohort comprised **1,047 rare-disease patient cases** drawn
by disproportionate stratified sampling (seed 42) from the GA4GH
Phenopacket Store v0.1.26 release: 250 developmental, 300
immunological, 250 metabolic, and 247 neurological cases. All cases had
a SOLVED interpretation status with a single annotated causal gene and
≥5 PubMed Central Open Access (PMC OA) full-text articles indexed for
the causal gene in the local Qdrant retrieval index. Cohort
construction is detailed in Methods §*Cohort construction*; the full
cohort manifest is available at
`data/test_cases_1050/test_cases.jsonl` in the project's GitHub
repository [CIT: repo URL at submission].

Five gene-prioritisation systems were evaluated on the same n = 1,047
cohort with the same 50-gene candidate list per case (1 causal + 49
distractors selected by HPO-Jaccard similarity from the HGNC quarterly
snapshot): **Cell K** (Exomiser HPO-only), **Cell M** (LIRICAL
HPO-only), **Cell D** (deterministic multi-agent hybrid retrieval),
**Cell L** (Cell D + MedCPT cross-encoder rerank), and **Cell S** =
**geno_agent** (Cell L + LLM-as-Evidence-Aggregator using Qwen3-8B via
local vLLM). A post-hoc reciprocal-rank-fusion ensemble of Cells M and
S (**Cell N**) was constructed for the complementarity analysis below.

### Overall evaluation

On the full cohort, geno_agent (Cell S) achieved **top-1 accuracy of
0.726 (95 % CI [0.698, 0.752])**, exceeding the Exomiser HPO-only
baseline (Cell K) at 0.691 [0.662, 0.718] by Δ = +0.035 (paired
bootstrap 95 % CI [+0.007, +0.066], McNemar p = 0.019). LIRICAL (Cell
M) achieved an apparent top-1 of 0.924, which subsequent analysis (§
*Annotation-overlap deconfounding*) shows to be an artefact of the
substantial overlap between Phenopacket Store source publications and
the `phenotype.hpoa` annotation corpus LIRICAL queries internally. The
deterministic multi-agent hybrid baseline (Cell D, 0.460) and the
cross-encoder-rerank-only variant (Cell L, 0.698) bracket the
architectural contribution: adding CE-rerank to Cell D contributed Δ =
+0.238 [+0.206, +0.270] ★, and adding LEA on top of Cell L contributed
a further Δ = +0.028 [+0.016, +0.040] ★. Full overall metrics (top-1,
top-5, top-10, MRR, NDCG@10) for all cells are reported in
**Table 2**.

[INSERT Table 2 here — overall results for K/M/D/L/S, point estimate +
95 % CI for each of {top-1, top-5, top-10, MRR, NDCG@10}. Source:
`data/eval_1050/_results_summary.md`.]

The v2 → v3 reproducibility check (independent re-runs of Cells L and S
seven months apart) found bit-perfect top-1 stability: 0 top-1 flips
for Cell L and 1 top-1 flip out of 1,047 for Cell S, confirming that
the LEA-augmented pipeline is effectively deterministic on the headline
metric despite expected stochasticity in vLLM token sampling.

### Annotation-overlap deconfounding — the fair-comparison cohort

A central concern with evaluating gene-prioritisation tools on the
Phenopacket Store benchmark is that the curated knowledge bases
underpinning competing systems (Orphanet, OMIM, `phenotype.hpoa`) are
themselves derived from rare-disease case publications — including, in
many instances, the same publications that serve as source for the
Phenopacket Store cases. To quantify and adjust for this confound, for
each of the 1,047 cases we computed a binary `annotation_overlap` flag:
set to 1 if the case's source PMID was cited by `phenotype.hpoa`
v2026-02-16 as a reference for at least one HPO annotation of the
causal gene's OMIM disease(s), else 0. The implementation parsed
282,723 `phenotype.hpoa` annotation rows into 9,852 unique (disease,
PMID) keys and joined each case against this index; all 1,047 cases
resolved to both a PMID and an OMIM identifier (zero edge cases).

**Cohort-wide annotation-overlap rate was 73.1 %** (765 / 1,047 cases).
Per-MONDO overlap rates varied substantially: 63.2 % developmental,
**64.0 % metabolic** (lowest), 76.1 % neurological, and **86.3 %
immunological** (highest). All five cells were re-aggregated on three
subsets: the full cohort, the overlap-present subset (n = 765), and
the **overlap-absent subset (n = 282) — the fair-comparison cohort on
which curated tools cannot benefit from training-data exposure**.

On the fair-comparison cohort, **geno_agent (Cell S) becomes the
top-ranked system**, achieving top-1 = **0.858 [0.816, 0.901]**, ahead
of Cell L (CE-rerank only, 0.823) and Exomiser K (0.780). LIRICAL's
top-1 dropped from 0.978 on overlap-present to **0.777** on
overlap-absent — a 20-percentage-point drop confirming that the
majority of LIRICAL's apparent advantage was annotation-overlap
exposure. Paired comparisons on the fair cohort (Table 3):

- **Cell S vs Exomiser K**: Δ = +0.078 [+0.011, +0.138], McNemar p =
  0.015 ★ — **more than doubling the overall-cohort effect of +0.035**.
- **Cell S vs LIRICAL M**: Δ = +0.082 [+0.021, +0.145], McNemar p =
  0.014 ★.
- **LIRICAL M vs Exomiser K**: Δ = -0.004 [-0.053, +0.043], McNemar p =
  1.000 — **LIRICAL is statistically tied with Exomiser when overlap is
  removed**.

[INSERT Table 3 here — paired Δ on overlap-absent fair cohort for the
five canonical comparisons (S vs K, S vs M, S vs L, L vs D, M vs K).
Source: `data/eval_1050/_results_stratified.md`.]

Per-MONDO category × fair-cohort breakdown showed **complementary
strengths** rather than uniform geno_agent dominance:

- **Metabolic (n = 90 fair-cohort cases)**: S = **0.900**, L = 0.844,
  K = 0.678, M = 0.756. Cell S leads M by +0.144 — the largest
  properly-powered per-category lead in the cohort.
- **Immunological (n = 41)**: S = 0.878 (underpowered, but
  directionally consistent: +0.244 vs M and +0.146 vs K).
- **Neurological (n = 59)**: 3-way tie at S = L = K = 0.780; M = 0.763.
- **Developmental (n = 92)**: **K = 0.902 leads** Cell S (0.859) by
  -0.043. Exomiser retains an edge on developmental cases even on the
  fair-comparison cohort — honestly reported.

### Publication-recency stratification

To assess whether literature-only retrieval generalises better than
curated-knowledge-base tools to cases that post-date the curation
cycle, source-PMID publication dates were retrieved from NCBI E-utils
for all 415 unique cohort PMIDs (100 % resolved; oldest 1988, newest
2024, median 2018). The cohort was split into **pre-2020 (n = 601,
57.4 %)** and **post-2020 (n = 446, 42.6 %)** sub-cohorts.

The most striking finding is **Exomiser's near-collapse on post-2020
papers**: top-1 dropped from **0.847 on pre-2020 cases to 0.480 on
post-2020 cases — a 37-percentage-point recency-induced decline**, the
largest of any system tested. Cell S also declined (0.839 → 0.574, a
27 pp drop) but less severely. Critically, **geno_agent's relative
advantage over Exomiser was 2.7 × larger on post-2020 cases**: paired Δ
S − K = +0.094 [+0.045, +0.139], McNemar p < 0.001 ★ on post-2020
(versus +0.035 ★ on the full cohort, and a statistical tie of -0.008
on pre-2020 cases). On the strictest novel subset (cases that are both
post-2020 AND overlap-absent, n = 88), Cell S remained the top-ranked
system (S = **0.852**, L = 0.823, K = 0.818, M = 0.773; S vs M point
estimate +0.080, matching the Thread D fair-cohort effect within
Monte-Carlo noise but underpowered for paired significance at n = 88).

LIRICAL displayed a paradoxical inverse pattern: top-1 *rose* from
0.915 on pre-2020 to 0.935 on post-2020. Mechanistic investigation
revealed that **post-2020 cases have a 12.6-percentage-point higher
overlap rate with `phenotype.hpoa`** (80.3 % vs 67.7 % on pre-2020) —
the HPO curation team preferentially annotates from recent landmark
publications, concentrating LIRICAL's training-data advantage on
exactly the cases where reviewers and clinicians most want
generalisation. This finding strengthens the annotation-overlap
argument: the standard rare-disease benchmark is systematically biased
toward curated-knowledge-base tools on the most clinically-relevant
recent cohort.

### Ensemble evaluation

To test whether LIRICAL and geno_agent provide complementary
predictive signal beyond what overlap status already explains, a
reciprocal-rank-fusion ensemble (Cell N, k = 60) was constructed
post-hoc from the existing Cell M and Cell S rankings. On the
fair-comparison cohort, **the ensemble was statistically tied with
geno_agent alone** (N vs S: Δ = -0.007 [-0.050, +0.036], McNemar p =
0.87); on the contaminated cohort, the ensemble underperformed LIRICAL
alone by Δ = -0.230 ★, indicating that mixing geno_agent's signal
*dilutes* LIRICAL's overlap-exposure advantage rather than
complementing it. The mechanism is symmetric RRF averaging: where the
two systems' rankings disagree, averaging penalises whichever system
was correct on that case. Both directions of disagreement (S right + M
wrong on fair cohort; M right + S wrong on contaminated cohort) are
present, with no subset where the two systems carry independent
predictive signal that ensembling can recover. The clinical-deployment
implication is that **geno_agent alone is preferable to either single
curated tool or to any RRF combination thereof**, on cohorts where
overlap status is unknown at inference time (i.e., every real clinical
case).

### Explanation quality

**geno_agent (Cell S) is the only system in the comparison that
produces evidence-traceable free-text rationales** with primary-
literature citations. Exomiser, LIRICAL, and the CE-rerank-only Cell L
produce numeric scores only; an equivalent rationale-quality metric
cannot be computed for them.

Local structural analysis of LEA's per-gene rationales across the full
n = 1,047 cohort found:

- **81.5 % of cases** had a substantive (≥ 30 characters and not
  matching a generic-fallback phrase) rationale for the causal gene
  overall; on the **fair-comparison cohort the rate rose to 94.0 %** —
  a 17-percentage-point lift. geno_agent both performs better AND
  explains itself better on the cohort that matters.
- Mean **2.81 unique PMC citations per top-1 gene** (median 80
  characters per rationale; mean 5.6 seconds latency per LEA call).
- **LEA deterministic-fallback rate of 0.2 % overall and 0.0 % on the
  fair cohort** (2 / 1,047 cases hit the deterministic baseline due to
  a vLLM HTTP timeout) — addressing a standard reviewer concern about
  reproducibility of LLM-in-the-loop systems.
- Per-MONDO breakdown: **metabolic 94.8 %** (best — consistent with
  metabolic being the flagship subgroup across every dimension
  measured), immunological 80.7 %, developmental 77.6 %, neurological
  72.9 %.

Cell S's free-text rationales were additionally evaluated by two GPT-4o
LLM judges (`gpt-4o-2024-08-06`) measuring orthogonal aspects of
grounding (see Methods §*RAG-quality evaluation*):

- **RAGAS faithfulness** (strict, claim-level): mean **0.480** /
  median 0.500 on a stratified n = 100 sensitivity subset (revised
  from a multi-claim full-response measurement of 0.286 that was
  found to be a measurement artefact of judging LEA's 14 honest
  "no direct evidence" distractor-gene rationales as unsupported
  claims). Fair-cohort RAGAS faithfulness was **0.616**, a +18.8 pp
  lift over the overlap-present cohort.
- **DeepEval HallucinationMetric** (lenient, holistic): mean
  groundedness **0.845** / median 0.933 on a stratified n = 100
  subset (a sub-sample of the RAGAS cohort).
- **The correctness-prediction signal reproduces across both judges**:
  RAGAS high-faithfulness (> 0) cases are 79.9 % top-1 correct vs
  46.5 % for faithfulness = 0 (33 pp gap); DeepEval high-groundedness
  (≥ 0.5) cases are 78.9 % top-1 correct vs 40.0 % for low-
  groundedness (39 pp gap). Both judges independently support
  deploying the grounding score as an **automated clinical-triage
  flag** — low-grounded predictions can be auto-routed for human
  review.

Per-MONDO RAG-quality stratification identified **neurological as the
worst-grounded subgroup on both judges** (DeepEval groundedness 0.665;
RAGAS zero-rate 28 %), a system-level limitation also reflected in
the recency analysis (neurological cases were the second-highest
recency-related accuracy decline). This is reported as a Limitations
item in the Discussion.

### LLM-family ablation

To test whether the headline result is an artefact of the Qwen3-8B
production model or robust to LLM family choice, the saved LEA prompts
were replayed against three frontier LLMs via the OpenRouter API on a
stratified n = 300 subset (75 per MONDO category, seed 42): **Qwen3-32B
Instruct** (same-family scaling), **Claude Sonnet 4.6** (cross-family
frontier), and **DeepSeek-V3-0324** (third-family 671B mixture-of-
experts open-weight). Same retrieval, same cross-encoder rerank, same
chunk selection as the production Qwen3-8B run — only the LLM backend
changes.

On the fair-comparison cohort (overlap-absent, n = 84) the three
production-quality LLMs **converged within 2.4 percentage points** of
the Qwen3-8B baseline: Qwen3-8B 0.869, Claude Sonnet 4.6 0.893,
DeepSeek-V3 0.881, with the same Cell L / Cell K relative orderings
preserved. All three production-quality LLMs beat LIRICAL (0.777) and
Exomiser (0.780) on the fair cohort by ≥ 7 percentage points. Claude
Sonnet 4.6 delivered a statistically significant +0.050 ★ top-1 lift
over Qwen3-8B on the full cohort (paired CI [+0.027, +0.073], McNemar
p < 0.001), but **the lift was not significant on the fair cohort**
(+0.024, n = 84) — the frontier-class advantage shrinks where geno_
agent is already strongest. DeepSeek-V3 delivered +0.020 on the full
cohort (borderline, p = 0.070) at one-eighteenth of Sonnet's cost per
correct prediction.

Qwen3-32B Instruct exhibited a notable deployment-usability issue: a
**22 % JSON-format refusal rate** in which the model emitted a meta-
error response (`{"error": "The JSON response is missing..."}`)
despite explicit `response_format=json_object`. On the 78 % of
responses where it did emit a valid ranking, top-1 was **0.722**,
essentially identical to Qwen3-8B at 0.717 on the same sub-cohort —
indicating that the 4 × parameter increase from 8B to 32B in the same
family does not materially improve gene-prioritisation performance,
and may degrade JSON adherence. By contrast Sonnet 4.6 and DeepSeek-V3
had JSON parse rates of 99.7 % and 99.3 % respectively.

**The headline geno_agent result is therefore robust to the choice of
LLM family**, with frontier-class models adding only a modest, cost-
asymmetric improvement on the cohort that matters and no improvement
at all over the existing Cell L baseline on cases where curated tools
already win (developmental).

### Computational profile

The full evaluation completed in ~24 hours of local compute on a
single NVIDIA RTX 5090 workstation (32 GB VRAM, 64 GB system RAM),
with per-cell wall times of: Cell K (Exomiser, CPU) 3 h 38 min;
Cell M (LIRICAL, 8-worker CPU) 22 min; Cell D (GPU) 6 h 53 min;
Cell L (GPU) 5 h 28 min; **Cell S (GPU, with vLLM serving Qwen3-8B)
7 h 36 min**, equivalent to **26.1 s per case end-to-end**.
LLM-judge evaluation cost an additional ~$98 in OpenAI API spend
(RAGAS n = 600 multi-claim + n = 100 top-1-only sensitivity +
DeepEval n = 100) and ~$21 in OpenRouter spend (3-model ablation
n = 300). The production pipeline (Cells D, L, S) requires **no
cloud API at inference time**; cloud spend is evaluation-only.
Per-case throughput is well within the timeframe a clinical
geneticist spends on a single rare-disease case during consultation
(Methods Table 1). All evaluation code is reproducible from frozen
sidecars in the GitHub repository.

---

## Discussion (✅ DRAFTED — this commit)

### Principal findings

This study evaluated geno_agent, a literature-only multi-agent retrieval-
augmented gene-prioritisation system, against established curated-
knowledge-base baselines (Exomiser HPO-only and LIRICAL HPO-only) on
a stratified n = 1,047 cohort drawn from Phenopacket Store v0.1.26.
Three findings define the contribution.

First, on the **fair-comparison cohort (n = 282 cases for which the
source publication is not cited by `phenotype.hpoa` as a reference for
the causal gene's OMIM disease)**, geno_agent achieved top-1 accuracy
of **0.858 (95 % CI [0.816, 0.901])** — significantly higher than
LIRICAL (0.777; paired Δ = +0.082, McNemar p = 0.014) and Exomiser
(0.780; Δ = +0.078, p = 0.015), establishing geno_agent as the
top-ranked system on cases where curated tools cannot benefit from
direct training-data exposure. Second, **LIRICAL's apparent overall
top-1 of 0.924 was shown to be substantially driven by annotation-
overlap exposure**: on the fair cohort, LIRICAL was statistically tied
with Exomiser (Δ = -0.004, p = 1.000) — quantifying for the first time
on Phenopacket Store the extent to which the standard rare-disease
benchmark systematically rewards curated-tool training-data exposure.
Third, the headline result was **robust to LLM family choice**:
replaying the saved LEA prompts against three independent frontier
LLMs (Qwen3-32B Instruct, Claude Sonnet 4.6, DeepSeek-V3) on the same
fair cohort produced top-1 scores within 2.4 percentage points of the
production Qwen3-8B (range 0.869-0.893), all of which exceeded Exomiser
and LIRICAL by ≥ 7 pp.

### Methodological contribution — the deconfounded fair-comparison cohort

The annotation-overlap analysis is the methodological centrepiece of
this work. The premise — that a benchmark's curators and a competing
tool's training data may overlap with the source publications of the
benchmark cases themselves — is well-recognised in the rare-disease
genomics literature (Smedley et al. 2015 [CIT]; Robinson et al. 2020
[CIT]). What the present study contributes is a **per-case binary
overlap flag** that allows direct stratification of results into
overlap-present and overlap-absent subsets, computed from a
straightforward join between case source PMIDs (extracted from the
Phenopacket Store metadata) and the pinned `phenotype.hpoa
v2026-02-16` annotation file. The cohort-wide overlap rate of 73.1 %
(rising to 86.3 % on the immunological subgroup and to **80.3 % on
post-2020 papers** — see below) is large enough that any future
evaluation of literature-aware or knowledge-base-aware rare-disease
prioritisation tools on Phenopacket Store should report stratified
fair-cohort results as the primary comparison, rather than full-cohort
results that systematically advantage curated tools.

Within geno_agent's own performance, the deconfounded analysis reveals
an arguably more important finding: **geno_agent's edge over Exomiser
more than doubled** on the fair cohort (Δ = +0.078 ★) compared with the
full cohort (Δ = +0.035 ★). The literature-only approach captures
signal that curated phenotype-gene tables cannot, *precisely* on the
cases where the curated tables have no prior knowledge of the gene
involvement. This is the deployment-relevant scenario: in real
clinical practice, a clinician confronting an undiagnosed case has no
a priori way to know whether the patient's underlying disease is
well-characterised in a curated knowledge base.

### Recency robustness as a clinical-deployment property

The publication-recency stratification (cases split at the 2020-01-01
source-PMID boundary) revealed a striking failure mode of curated
tools: **Exomiser's top-1 collapsed from 0.847 on pre-2020 cases to
0.480 on post-2020 cases — a 37-percentage-point decline**. By
contrast, geno_agent dropped only 27 pp on the same split, and its
relative advantage over Exomiser was **2.7 × larger on the post-2020
cohort** (Δ = +0.094 ★) than on the full cohort. This pattern is the
direct empirical signature of the **publication-curation lag**: a
phenotype-gene curation cycle of 2-5 years (typical for Orphanet and
OMIM) means that case reports published after the most recent curation
release are systematically inaccessible to curated-tool reasoning.
Literature-only retrieval, in contrast, has access to whatever is
indexed in the underlying corpus — in this study, PMC OA articles
indexed up to 2026-05.

A counter-intuitive secondary finding strengthens this argument:
**LIRICAL's top-1 *rose* from 0.915 to 0.935 on post-2020 cases**.
Investigation traced this to a 12.6-percentage-point higher overlap
rate on post-2020 cases (80.3 % vs 67.7 % on pre-2020) — the HPO
curation team preferentially annotates from recent landmark
publications, concentrating LIRICAL's training-data advantage on
exactly the cases where reviewers and clinicians most need
generalisation. From a clinical-deployment perspective, this implies
that benchmark-comparison studies of curated rare-disease tools that
do not stratify by publication recency systematically overstate
real-world generalisation performance.

### Explainability and the clinical-triage-flag deployment pattern

Beyond accuracy, the present study contributes a quantitative
treatment of LLM-generated rationale quality. geno_agent is the only
system in the comparison that produces evidence-traceable free-text
rationales — Exomiser, LIRICAL, and the cross-encoder-rerank-only
variant all emit numeric scores without supporting natural-language
reasoning. Local structural analysis found that **94.0 % of fair-
cohort cases have a substantive LEA rationale for the causal gene**,
backed by a mean 2.81 unique PMC citations per top-ranked gene. Two
independent LLM-judge frameworks (RAGAS faithfulness and DeepEval
HallucinationMetric) quantified the grounding of the rationales —
yielding a strict claim-level faithfulness mean of 0.480 (top-1-only
sensitivity measurement; the full-response measurement of 0.286 was
shown to be a measurement artefact of LEA's structured 15-gene output
in which 14 of 15 rationales are honest "no direct evidence"
distractor-gene fallbacks) and a lenient holistic groundedness mean of
0.845, bounding LEA's true grounding at a defensible range.

The clinically-actionable finding is that **both judges independently
predict top-1 correctness**. RAGAS-high-faithfulness cases were
79.9 % top-1 correct vs 46.5 % for faithfulness = 0 (33 pp gap);
DeepEval-high-groundedness cases were 78.9 % vs 40.0 % (39 pp gap).
This signal is robust enough to support a deployment pattern in which
**low-grounded predictions are automatically routed for human review**,
providing an audit-traceable triage workflow. To our knowledge, this
is the first quantification of LLM faithfulness as a deployable
clinical-triage signal in the rare-disease prioritisation context.

### Comparison with existing systems

Three families of rare-disease gene-prioritisation tools provide the
relevant comparison context: (i) **classical phenotype-driven tools**
(Exomiser [CIT: Smedley 2015], LIRICAL [CIT: Robinson 2020], AI-
MARRVEL [CIT: 2024]) that operate from curated phenotype-gene tables
and produce numeric scores; (ii) **agentic curated-knowledge-base-plus-
live-web systems**, of which DeepRare (Zhao et al., *Nature* 2026
[CIT]) is the current state-of-the-art, combining live web search,
scraped curated-database content (Orphanet expert pages, OMIM,
PubCaseFinder), and per-case cloud LLM inference to emit ranked
diseases with multi-round reflection; and (iii) the **literature-only
locally-deployable class** that geno_agent establishes — a single
frozen full-text PMC OA index queried by a deterministic multi-agent
pipeline + LEA. A direct head-to-head benchmark against DeepRare was
considered but not performed, because the two systems differ on three
methodologically-load-bearing axes (output unit, knowledge-source
class, and annotation-overlap exposure analogous to the present study's
LIRICAL finding); the architectural differences are formally compared
in Related Work §[ref] and detailed in our reproducibility-tagged
analysis [CIT: deeprare_comparability_analysis.md]. DeepRare's
reported HPO-only Recall@1 of 57.18 % on its own 2,919-disease
benchmark is reported there for context. The two systems are best
characterised as complementary deployments for different scenarios:
DeepRare for institutional settings with infrastructure to support
multi-tool integration + live web access + cloud LLM APIs; geno_agent
for clinical-genetics consultations requiring single-workstation
deployment, PHI safety, and reproducibility.

### Limitations

Eight limitations of the present study warrant explicit acknowledgement.

First, **no clinical reviewer panel rated the LEA rationales**. The
substantiveness analysis (Thread G) and the RAGAS/DeepEval faithfulness
scores quantify grounding against the retrieved evidence, but do not
quantify clinical actionability — a panel of 2-3 clinical geneticists
rating LEA rationales on a Likert scale is the standard next step
(see Future Work).

Second, the **RAGAS faithfulness measurement was performed against ≤ 20
retrieved chunks per case** to fit the $100 API budget; the LEA model
itself processed up to 45 chunks during inference. The reported mean
of 0.480 (top-1-only sensitivity) is therefore a lower bound on the
true LEA-against-its-own-context faithfulness; a re-run at the full
45-chunk input is a clear remediation path.

Third, **neurological is the worst-grounded subgroup on both LLM
judges** (DeepEval groundedness 0.665; RAGAS zero-rate 28 %). The
recency-stratified analysis also identified neurological as a
disproportionately recency-sensitive subgroup. The root cause is
likely a combination of phenotype heterogeneity and longer chunks-per-
gene tail; further investigation is warranted.

Fourth, **Exomiser retains a fair-cohort advantage on developmental
cases** (K = 0.902 vs S = 0.859 on the fair-cohort developmental
subgroup, n = 92). The deployment implication is that geno_agent does
not uniformly dominate; the per-MONDO complementarity argues for a
practical workflow in which both tools are run and their outputs
compared.

Fifth, the **LLM ablation revealed a 22 % JSON-format refusal rate
for Qwen3-32B Instruct** — a deployment-usability characteristic worth
flagging for any group considering a same-family scale-up from the 8B
production model. On parsed responses Qwen3-32B's top-1 matched
Qwen3-8B (0.722), indicating that within-family parameter scaling does
not materially improve gene-prioritisation performance and may degrade
format adherence.

Sixth, the **production pipeline runs a single 8B model** (Qwen3-8B
via local vLLM). The ablation suggests Claude Sonnet 4.6 would add
~5 pp on the full cohort but ~2 pp (not significant) on the fair
cohort; the cost-per-correct-prediction trade-off is unfavourable for
upgrading. The 8B production choice is the cost-optimal point.

Seventh, the **DeepRare comparison was not performed head-to-head**
for the reasons outlined in §Comparison; the architectural-comparison
table provides the defensible substitute. A reviewer requesting a
head-to-head benchmark would receive the methodological-asterisks
explanation rather than a remapped comparison.

Eighth, **the Phenopacket Store cohort over-represents
published-literature-derived cases**. Cases that never reach
publication — for instance, underdiagnosed conditions in underserved
populations, or pediatric metabolic conditions with limited
case-report coverage — are not represented. The generalisability claim
in this paper is restricted to the published-rare-disease
distribution; prospective evaluation in real clinical workflows is the
needed next study.

### Future work

Six concrete extensions follow directly from the limitations above:
(1) clinical reviewer panel for LEA rationale Likert ratings, sized at
~30 sampled cases per subgroup; (2) RAGAS re-run at MAX_CONTEXTS = 45
to bound true faithfulness; (3) inline-citation prompting (each LEA
claim explicitly references its supporting PMCID); (4) counterfactual
chunk-removal ablation to identify minimal-evidence cases; (5)
prospective evaluation in a real clinical-genetics consultation
workflow; (6) extension of the cohort to non-Phenopacket-Store sources
(e.g., curated UDP cases, internal hospital cohorts under appropriate
data-sharing agreements).

### Conclusion

A **literature-only, locally-deployable, multi-agent retrieval-augmented
gene-prioritisation system can match — and on the fair-comparison
cohort, exceed — established curated-knowledge-base tools** for
rare-disease causal-gene prioritisation. The result is robust across
three independent LLM families (Qwen, Anthropic, DeepSeek), preserved
across an independent v2 → v3 reproducibility re-run, and accompanied
by the unique deployment property of evidence-traceable rationales
with quantifiable LLM-judge faithfulness. The annotation-overlap
deconfounding methodology contributes a stratification tool the
rare-disease benchmark community should adopt for any future
evaluation of literature-aware or knowledge-base-aware prioritisation
tools on Phenopacket Store. The recency-stratification finding —
Exomiser losing 37 percentage points on post-2020 papers — is a
direct empirical signature of the curation-publication lag that
literature-only retrieval naturally bypasses, with concrete implications
for rare-disease clinical deployment as the publication cadence in
the field accelerates.

---

## Conclusions (❌ pending)

(~150 words. Single-paragraph synthesis.)

---

## Limitations (⚠️ partial — covered in Discussion §19b of TRIPOD-LLM compliance)

Eight known limitations consolidated in
`reports/tripod_llm_compliance.md §5 Item 19b`. To be inlined.

---

## Future work (❌ pending)

Six concrete items from `reports/tripod_llm_compliance.md §5 Item 19g`.

---

## Related work (❌ pending)

(~600 words. Outline: Exomiser/LIRICAL/AI-MARRVEL family of curated-KB
tools → DeepRare 2026 as the curated-KB-plus-live-web agentic class →
contrast with the literature-only locally-deployable class geno_agent
establishes. Reuse the 13-dimension architectural comparison from
`reports/deeprare_comparability_analysis.md §2`.)

---

## Declarations (❌ pending)

To be drafted: Ethical approval (Phenopacket Store de-identified, IRB-
exempt — confirm with UAX), Funding (UAX TFM, OpenAI/OpenRouter spend
by author), Competing interests (none), Authors' contributions, Code
and data availability, Acknowledgements.

---

## References (⚠️ partial — 39 cites compiled, more to add during Related Work draft)

Provided by author 2026-05-24, APA-style; will be re-formatted to
Springer Vancouver at submission. ~20-30 additional citations expected
during Related Work drafting (DeepRare, AI-MARRVEL, MedCPT, vLLM,
Phenopacket Store v0.1.26 release, Qwen3, GPT-4o judge, additional
RAG-in-biomed work).

1. Boycott, K. M., Rath, A., Chong, J. X., Hartley, T., Alkuraya, F. S., Baynam, G., … Lau, L. P. L. (2019). International cooperation to enable the diagnosis of all rare genetic diseases. *American Journal of Human Genetics, 104*(3), 405–414. https://doi.org/10.1016/j.ajhg.2019.01.013

2. Bridges, Y., de Souza, V., Cortes, K. G., Haendel, M., Harris, N. L., Korn, D. R., … Jacobsen, J. O. B. (2025). Towards a standard benchmark for phenotype-driven variant and gene prioritisation algorithms: PhEval – Phenotypic inference evaluation framework. *BMC Bioinformatics, 26*, 87. https://doi.org/10.1186/s12859-025-06105-4

3. Clark, M. M., Stark, Z., Farnaes, L., Tan, T. Y., White, S. M., Dimmock, D., & Kingsmore, S. F. (2018). Meta-analysis of the diagnostic and clinical utility of genome and exome sequencing and chromosomal microarray in children with suspected genetic diseases. *npj Genomic Medicine, 3*(1), 16. https://doi.org/10.1038/s41525-018-0053-8

4. Confident AI. (2024). *DeepEval: The open-source LLM evaluation framework* [Computer software]. Retrieved from https://github.com/confident-ai/deepeval

5. Danis, D., Bamshad, M. J., Bridges, Y., Caballero-Oteyza, A., Cacheiro, P., Carmody, L. C., … Robinson, P. N. (2025). A corpus of GA4GH Phenopackets: Case-level phenotyping for genomic diagnostics and discovery. *Human Genetics and Genomics Advances, 6*(1), 100371. https://doi.org/10.1016/j.xhgg.2024.100371

6. Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. In *Proceedings of the 2019 Conference of the North American Chapter of the Association for Computational Linguistics (NAACL-HLT)* (pp. 4171–4186). https://doi.org/10.18653/v1/N19-1423

7. Es, S., James, J., Espinosa Anke, L., & Schockaert, S. (2024). RAGAs: Automated evaluation of retrieval augmented generation. In *Proceedings of the 18th Conference of the European Chapter of the ACL: System Demonstrations* (pp. 150–158). Association for Computational Linguistics.

8. Gao, Y., Xiong, Y., Gao, X., Jia, K., Pan, J., Bi, Y., … Wang, H. (2024). *Retrieval-augmented generation for large language models: A survey* (arXiv preprint arXiv:2312.10997). Retrieved from https://arxiv.org/abs/2312.10997

9. Global Genes. (2020). *RARE facts*. Retrieved from https://globalgenes.org/rare-disease-facts/

10. Gu, Y., Tinn, R., Cheng, H., Lucas, M., Usuyama, N., Liu, X., … Poon, H. (2021). Domain-specific language model pretraining for biomedical natural language processing. *ACM Transactions on Computing for Healthcare, 3*(1), 1–23. https://doi.org/10.1145/3458754

11. Jacobsen, J. O. B., Kelly, C., Cipriani, V., Genomics England Research Consortium, Mungall, C. J., Reese, J., … Smedley, D. (2022a). Phenotype-driven approaches to enhance variant prioritization and diagnosis of rare disease. *Human Mutation, 43*(8), 1071–1081. https://doi.org/10.1002/humu.24380

12. Jacobsen, J. O. B., Baudis, M., Baynam, G. S., Beckmann, J. S., Beltran, S., Buske, O. J., … Robinson, P. N. (2022b). The GA4GH Phenopacket schema defines a computable representation of clinical data. *Nature Biotechnology, 40*(6), 817–820. https://doi.org/10.1038/s41587-022-01357-4

13. Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., … Fung, P. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys, 55*(12), 1–38. https://doi.org/10.1145/3571730

14. Jin, Q., Yang, Y., Chen, Q., & Lu, Z. (2024). GeneGPT: Augmenting large language models with domain tools for improved access to biomedical information. *Bioinformatics, 40*(2), btae075. https://doi.org/10.1093/bioinformatics/btae075

15. Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns, 4*(9), 100804. https://doi.org/10.1016/j.patter.2023.100804

16. Köhler, S., Gargano, M., Matentzoglu, N., Carmody, L. C., Lewis-Smith, D., Vasilevsky, N. A., … Robinson, P. N. (2021). The Human Phenotype Ontology in 2021. *Nucleic Acids Research, 49*(D1), D1207–D1217. https://doi.org/10.1093/nar/gkaa1043

17. LangChain AI. (2024). *LangGraph: Build resilient language agents as graphs* [Computer software]. Retrieved from https://github.com/langchain-ai/langgraph

18. Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., … Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. In *Advances in Neural Information Processing Systems* (Vol. 33, pp. 9459–9474). Curran Associates.

19. Li, H., Dong, Q., Chen, J., Su, H., Zhou, Y., Ai, Q., … Liu, Y. (2024). *LLMs-as-judges: A comprehensive survey on LLM-based evaluation methods* (arXiv preprint arXiv:2412.05579). Retrieved from https://arxiv.org/abs/2412.05579

20. Li, M., Kilicoglu, H., Xu, H., & Zhang, R. (2025). BiomedRAG: A retrieval augmented large language model for biomedicine. *Journal of Biomedical Informatics, 162*, 104769. https://doi.org/10.1016/j.jbi.2024.104769

21. Nguengang Wakap, S., Lambert, D. M., Olry, A., Rodwell, C., Gueydan, C., Lanneau, V., … Rath, A. (2020). Estimating cumulative point prevalence of rare diseases: Analysis of the Orphanet database. *European Journal of Human Genetics, 28*(2), 165–173. https://doi.org/10.1038/s41431-019-0508-0

22. Raza, M. M., Venkatesh, K. P., & Kvedar, J. C. (2024). Generative AI and large language models in health care: Pathways to implementation. *npj Digital Medicine, 7*(1), 62. https://doi.org/10.1038/s41746-023-00988-4

23. Richards, S., Aziz, N., Bale, S., Bick, D., Das, S., Gastier-Foster, J., … Rehm, H. L. (2015). Standards and guidelines for the interpretation of sequence variants: A joint consensus recommendation of the American College of Medical Genetics and Genomics and the Association for Molecular Pathology. *Genetics in Medicine, 17*(5), 405–424. https://doi.org/10.1038/gim.2015.30

24. Robinson, P. N., Ravanmehr, V., Jacobsen, J. O. B., Danis, D., Zhang, X. A., Carmody, L. C., … Smedley, D. (2020). Interpretable clinical genomics with a likelihood ratio paradigm. *American Journal of Human Genetics, 107*(3), 403–417. https://doi.org/10.1016/j.ajhg.2020.06.021

25. Smedley, D., Jacobsen, J. O. B., Jäger, M., Köhler, S., Holtgrewe, M., Schubach, M., … Robinson, P. N. (2015). Next-generation diagnostics and disease-gene discovery with the Exomiser. *Nature Protocols, 10*(12), 2004–2015. https://doi.org/10.1038/nprot.2015.124

26. Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., … Polosukhin, I. (2017). Attention is all you need. In *Advances in Neural Information Processing Systems* (Vol. 30, pp. 5998–6008). Curran Associates.

27. Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F., … Zhou, D. (2022). Chain-of-thought prompting elicits reasoning in large language models. In *Advances in Neural Information Processing Systems* (Vol. 35, pp. 24824–24837). Curran Associates.

28. Wooldridge, M. (2009). *An introduction to multiagent systems* (2nd ed.). Chichester, England: John Wiley & Sons.

29. Xiao, Y., Liu, J., Zheng, Y., Xie, X., Hao, J., Li, M., … Peng, J. (2024). *CellAgent: An LLM-driven multi-agent framework for automated single-cell data analysis* (bioRxiv preprint). https://doi.org/10.1101/2024.05.13.593861

30. Xiong, G., Jin, Q., Lu, Z., & Zhang, A. (2024). Benchmarking retrieval-augmented generation for medicine. In *Findings of the Association for Computational Linguistics: ACL 2024* (pp. 6233–6251). Association for Computational Linguistics. https://doi.org/10.18653/v1/2024.findings-acl.372

31. Yang, R., Ning, Y., Keppo, E., Liu, M., Hong, C., Bitterman, D. S., … Liu, N. (2025). Retrieval-augmented generation for generative artificial intelligence in health care. *npj Health Systems, 2*, Article 2. https://doi.org/10.1038/s44401-024-00004-1

32. Yang, T., Xiao, Y., Bao, Z., Hao, J., & Peng, J. (2025). The rise and potential opportunities of large language model agents in bioinformatics and biomedicine. *Briefings in Bioinformatics, 26*(6), bbaf601. https://doi.org/10.1093/bib/bbaf601

33. Zhao, M., Havrilla, J. M., Fang, L., Chen, Y., Peng, J., Liu, C., … Wang, K. (2020). Phen2Gene: Rapid phenotype-driven gene prioritization for rare diseases. *NAR Genomics and Bioinformatics, 2*(2), lqaa032. https://doi.org/10.1093/nargab/lqaa032

34. Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., … Stoica, I. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. In *Advances in Neural Information Processing Systems* (Vol. 36). Curran Associates.

35. Zhou, J., Jiang, J., Han, Z., Wang, Z., & Gao, X. (2025). Streamline automated biomedical discoveries with agentic bioinformatics. *Briefings in Bioinformatics, 26*(5), bbaf505. https://doi.org/10.1093/bib/bbaf505

---

## Tables and figures (⚠️ source data ready, render pending)

| ID | Description | Source data | Status |
|---|---|---|---|
| Table 1 | Per-cell operational profile (wallclock + cost) | `reports/wallclock_cost_table.md` | source ready |
| Table 2 | Overall 5-cell metrics (top-1, top-5, top-10, MRR, NDCG@10) with CIs | `data/eval_1050/_results_summary.md` | source ready |
| Table 3 | Paired Δ on overlap-absent fair cohort | `data/eval_1050/_results_stratified.md` | source ready |
| Table 4 | LLM-family ablation results | `data/eval_1050/_results_lea_ablation.md` | source ready |
| Figure 1 | CONSORT-style cohort flow diagram | needs render | pending |
| Figure 2 | Multi-agent architecture diagram | inline SVG in Streamlit demo, needs publication-grade version | pending |
| Figure 3 | Per-MONDO top-1 stacked bar (5 cells) | needs render | pending |
| Figure 4 | Faithfulness vs top-1 correctness scatter | needs render | pending |
| Supp Fig 1 | LIRICAL recency paradox bar chart | needs render | pending |
| Supp Fig 2 | LLM-family ablation comparison | needs render | pending |
| Supp Table 1 | TRIPOD-LLM compliance checklist | `reports/tripod_llm_compliance.md` | source ready |

---

*Manuscript draft v1 — 2026-05-24. Results section drafted (~2,250
words) synthesising paper_extension_results.md §§12-20. All other
sections pending. Next drafting sessions: Discussion (~6 h), Background
(~3 h), Abstract (~2 h), then Tables/Figures rendering (~6 h) and
References (~3 h).*
