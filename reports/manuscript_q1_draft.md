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

## Background (❌ pending)

(~600-800 words. Outline: rare-disease diagnostic odyssey → existing
curated tools (Exomiser, LIRICAL, AI-MARRVEL) → DeepRare 2026 →
literature-only gap → this paper's contribution.)

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

## Discussion (❌ pending)

(~1,500 words. Will synthesise: (i) headline finding — geno_agent as
#1 literature-only system on fair cohort; (ii) Thread D as the
methodologically novel deconfounding; (iii) Thread E's clinical
implication of curated-tool recency lag; (iv) Thread G + RAGAS as the
explainability/trust story; (v) LLM ablation as robustness;
(vi) limitations consolidated from `tripod_llm_compliance.md §5`;
(vii) future work; (viii) clinical-deployment context.)

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

## References (❌ pending)

~60-100 citations to compile. Reference manager: [Zotero / Mendeley —
to decide]. Bibliography style: Springer Vancouver per Genome Medicine
[CIT: confirm].

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
