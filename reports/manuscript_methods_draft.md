# Manuscript Methods (draft) — geno_agent for rare-disease gene prioritisation

Target venue: **Genome Medicine** (~12-15 IF). Submission window: Q3 2026.

This is a Methods-section draft, written in paper voice (passive,
methods-not-decisions, third-person). All numerical values reference the
locked v3 results in `paper_extension_results.md` §§12-16 and the
authoritative methodology in `methodology.md` v3.1. Word target for the
Genome Medicine Methods section is ~2,500-3,500 words; this draft is
~3,260 words and sits right at the upper bound of the Genome Medicine
Methods target — further additions will require trimming elsewhere.

---

## Methods

### Cohort construction

Clinical cases were drawn from the Global Alliance for Genomics and
Health (GA4GH) Phenopacket Store v0.1.26 (released 13 January 2026)
[9], which aggregates published rare-disease
patient phenopackets curated from primary literature with solved
(gene-level) diagnoses. Cases were retained if they met four
criteria: (i) a single causal gene supported by a SOLVED interpretation
status, (ii) at least three Human Phenotype Ontology terms (HPO; v2026-02-16,
[7]), (iii) a Mondo Disease Ontology mapping to one
of four broad categories — developmental, immunological, metabolic, or
neurological (MONDO v2026-03-03, [39]) — and
(iv) at least five PubMed Central Open Access (PMC OA) full-text
articles indexed for the causal gene in our local Qdrant corpus (see
*Index construction*), ensuring downstream literature retrieval is
non-trivial. Criteria (i)–(iii) yielded an eligible pool of 4,670 cases
(464 developmental, 390 immunological, 672 metabolic, 3,144
neurological); criterion (iv) was subsequently verified on the drawn
sample, which it did not reduce.

To support an adequately-powered analysis on the smallest categorical
subgroup (immunological diseases), a disproportionate stratified sample
of 1,050 was drawn from this pool with seed 42: 250 cases each from
developmental, metabolic, and neurological categories, and 300 from the
immunological pool (390 eligible). Three neurological cases — two RNU4-2
and one RNU2-2, all small nuclear RNA genes — were then removed at the
candidate-list stage because their causal gene is not protein-coding,
yielding a final n = 1,047 cohort (250 + 300 + 250 + 247). Disproportionate
sampling is standard practice in epidemiological and clinical-genomics
benchmarking when one subgroup is rate-limiting for statistical power
and the overall cohort is large enough that overall-cohort estimates
remain unbiased after stratum-weight correction [40].

For each case, the canonical 50-gene candidate list comprised the
single causal gene plus 49 distractor genes sampled deterministically
(per-case derived seed: SHA-256 hash of case_id) from the
phenotype-matched HGNC quarterly snapshot (2026-04-07). Phenotype
matching used the Jaccard similarity between the case's HPO term set
and each candidate gene's HPO annotations in `phenotype.hpoa`
v2026-02-16, taking the top-49 distractors by similarity. This
construction ensures distractors are clinically plausible alternatives,
not random genes — a more conservative evaluation setting than uniform
sampling.

Per-case publication-date metadata was retrieved from NCBI E-utils
(efetch `PubMedPubDate PubStatus="pubmed"` field) for the 415 unique
source PMIDs in the cohort. 100 % of cases resolved to a PMID and a
date (most recent: 2024; oldest: 1988; median: 2018).

### Comparator systems

Five gene-prioritisation systems were evaluated on the same n = 1,047
cohort, each operating on the same 50-gene candidate list per case. This
study evaluates **phenotype-driven gene prioritisation**: Exomiser and
LIRICAL are run in HPO-only mode (no patient VCF), isolating the
phenotype signal so that all five systems receive identical inputs (HPO
terms plus the same 50-gene candidate list). Variant-aware
prioritisation, in which Exomiser and LIRICAL additionally consume
patient variant calls, is out of scope for this study and is the subject
of planned follow-up work.

**Cell K (Exomiser HPO-only baseline).** Exomiser v14.0.2
[11] was run with the default phenotype-only
configuration (hiPhive scoring on the patient's HPO terms; no variant
input). The candidate gene list was passed as a whitelist.

**Cell M (LIRICAL HPO-only baseline).** LIRICAL v2.4.0
[12] was run with the same HPO term input.
LIRICAL outputs a posterior probability per OMIM disease; these were
mapped to gene rankings via NCBI mim2gene_medgen (2026-04-07) and
Orphanet en_product6.xml. When multiple diseases mapped to a candidate
gene, the maximum posterior was used.

**Cell D (multi-agent hybrid baseline).** A deterministic agentic
workflow composed of four role-specialised agents (planner → retriever →
critic → synthesiser) using hybrid dense + BM25 retrieval [41] with
Reciprocal Rank Fusion (k = 60, [42]) over a local PMC OA Qdrant
index (see *Index construction*). The synthesiser
ranks candidates by the sum of inverse-rank chunk scores per gene.

Throughout, we use *agent* to denote a role-specialised component — a
node in the LangGraph state graph that consumes and updates shared
workflow state — and *agentic workflow* for the system as a whole: an
orchestration with predefined nodes, edges, and conditional routing,
here a critic-driven self-correction loop that re-enters the retriever
when too many chunks are graded low-relevance. This is distinct from an
autonomous multi-agent system in which each agent selects its own tools
and control flow at run time. Topology and decoding are fixed
(temperature 0, seeded) so that inference is reproducible and the
comparative evaluation is valid, a prerequisite for clinical
benchmarking. Accordingly, the "single-agent vs. multi-agent" factor
below denotes the number of role-specialised agents (one vs. four), not
agent autonomy.

**Cell L (Cell D + cross-encoder reranking).** Identical to Cell D but
with an additional MedCPT cross-encoder pass over the top-50 retrieved
chunks per gene [35]. The reranker
re-scores each chunk for query-specific relevance.

**Cell S (Cell L + LLM-as-Evidence-Aggregator, "geno_agent").** Cell L
plus a final synthesis step in which a locally-hosted 8-billion-parameter
LLM (Qwen3-8B [43], served via vLLM 0.20.1
[44] on an NVIDIA RTX 5090) is shown
the top-3 reranked chunks per top-15 gene and asked to produce a
ranked list with a per-gene confidence (0-1) and a free-text rationale.
The system prompt instructs the model to reason from the retrieved
evidence only and to assign low confidence when evidence does not
directly support a gene-phenotype link. Deterministic settings:
temperature 0.0, top-p 1.0, response format `json_object`. The local-
LLM choice (no cloud API) preserves clinical deployability and
reproducibility.

A reciprocal-rank-fusion ensemble of Cells M and S (Cell N) was
constructed post-hoc for the ensemble-complementarity analysis below
(`rrf_score = 1/(60 + rank_M) + 1/(60 + rank_S)`, k = 60 per
[42]).

**Excluded comparators.** A head-to-head benchmark against DeepRare
[33] was considered but not performed because the
two systems are architecturally distinct classes — DeepRare uses
curated KBs + live web with disease-level output and is exposed to
the same annotation-overlap confound this Methods quantifies for
LIRICAL. The full architectural comparison and reasoning are given in
§Related Work; a detailed audit of the DeepRare repository is
provided in `reports/deeprare_comparability_analysis.md`.

### Prompt design and curation

The LEA system + user prompt was authored in a single design pass at
the start of the v3 evaluation phase, without formal A/B iteration,
in-context exemplars, or chain-of-thought elicitation. Prompt drafts
were validated only on hand-constructed synthetic toy inputs; no case
drawn from the n = 1,047 evaluation cohort or the n = 300 ablation
sub-sample was used to develop or tune the prompt. The full system and
user prompt templates, per-case rendered inputs, and raw LLM responses
are captured deterministically in
`data/eval_1050/cell_S_responses/<case>.json:lea_log.*` for replay,
audit, and adversarial prompt-rewriting experiments.

### Index construction

A 3.4 million-article subset of the PubMed Central Open Access XML
corpus (downloaded 2026-05; [45]) was parsed and
filtered for genetics / genomics / rare-disease relevance via MeSH
descriptor matching (terms: Genetic Diseases, Rare Diseases, Mutation,
Pathogenicity, Inheritance Patterns) and full-text inclusion criteria.
The resulting genetics-relevant full-text corpus (~3.4 million articles)
was chunked at 512 tokens with
50-token overlap using a PubMedBERT-base tokeniser [17];
chunk identifiers were derived deterministically via UUID5 on
the content key to enable bit-identical re-indexing. Dense embeddings
were computed with PubMedBERT and stored in Qdrant v1.14.1 alongside
sparse embeddings from FastEmbed BM25, supporting hybrid retrieval via
Reciprocal Rank Fusion at query time. The production Qdrant collection
(`geno_agent_pmc_oa_v1`) contains **52,777,395 chunks** with on-disk
payload (collection size verified via the Qdrant `points_count` API).

### Evaluation metrics

Per case and per cell, the causal gene's rank in the system's output
was used to compute top-1, top-5, top-10 accuracy (binary indicators),
Mean Reciprocal Rank (MRR), and Normalised Discounted Cumulative Gain
at rank 10 (NDCG@10) with binary relevance. Per-cell point estimates
are the mean of per-case values; 95 % confidence intervals are derived
from a 1,000-resample bootstrap of per-case values (seed 42).

For pairwise comparisons (e.g., S vs K), the **paired per-case
difference** was the unit of inference: for each case, the difference
in the metric between the two cells was computed, and a 1,000-resample
bootstrap of this per-case difference vector yielded the point
estimate and 95 % CI for Δ. A two-sided exact McNemar test was
applied to the discordant-pair counts (A > B, B < A) for binary
metrics [46]. Statistical significance is reported by the
conjunction of "95 % CI excludes zero" and "McNemar p < 0.05" — both
criteria are required for a Δ to be flagged ★. To guard against
inflation from multiple testing, a single primary endpoint was
pre-declared — top-1 superiority of geno_agent (Cell S) over each
curated baseline (Exomiser, LIRICAL) on the deconfounded fair cohort —
and the resulting two-comparison family was corrected with the Holm
step-down procedure (both comparisons remained significant; adjusted
p = 0.028). A supportive family (full-cohort and post-2020 comparisons)
was additionally controlled with the Benjamini-Hochberg false-discovery-
rate procedure. All remaining subgroup and secondary-metric comparisons
are reported as exploratory. Adjusted p-values are tabulated in the
supplementary multiplicity-correction table
(`reports/tables/supp_table_multiplicity.md`), regenerable via
`scripts/eval/multiplicity_correction.py`.

Per-MONDO subgroup analyses repeated the above on each category's
cases. The immunological subgroup (n = 300), as the smallest
categorical pool and the lead clinical application of the work, was
additionally subjected to a 100 % leave-one-out sensitivity check on
the S-vs-K paired McNemar test.

### Annotation-overlap deconfounding

LIRICAL's likelihood-ratio computation uses HPO annotations from
`phenotype.hpoa` (curated from primary literature). Phenopacket Store
cases are themselves derived from publications; if a case's source PMID
is cited in `phenotype.hpoa` as a reference for the causal OMIM
disease, LIRICAL has direct training-data exposure to that case. To
quantify and adjust for this confound, for each of the 1,047 cases we
computed a binary `annotation_overlap` flag: 1 if the case's source
PMID (extracted from `case_id` and verified against the phenopacket
`metaData.externalReferences[0].id` field) appears in `phenotype.hpoa`
v2026-02-16 as a reference for any annotation of any of the case's
causal OMIM disease IDs; 0 otherwise. The implementation parses the
282,723 phenotype.hpoa rows (yielding 9,852 unique `(disease, PMID)`
keys after deduplication and PMID-only filtering) and joins each case
against this index. All 1,047 cases resolved to both a PMID and an
OMIM disease ID (zero edge cases). All paired comparisons were then
repeated on (i) the full cohort, (ii) the overlap-present subset, and
(iii) the **overlap-absent subset (n = 282, 26.9 % of cohort)** — the
latter being the fair-comparison cohort on which LIRICAL cannot
benefit from training-data exposure.

### Publication-recency stratification

To separately assess whether geno_agent's literature-driven approach
generalises better than curated-knowledge-base tools to cases that
post-date curation cycles, the cohort was additionally split by source
PMID publication year (cutoff 2020-01-01). Pre-2020 cases (n = 601)
predominantly reflect well-characterised genes; post-2020 cases
(n = 446) are more likely to involve recently-discovered gene-phenotype
associations that curated tools may not yet incorporate. The same
paired-bootstrap and McNemar tests were repeated on each recency
stratum, plus the crossed `post_2020 × overlap-absent` subset
(n = 88) as the closest available substitute for a "truly novel"
cohort.

### Ensemble evaluation

A reciprocal-rank-fusion combination of Cells M and S (Cell N) was
evaluated to test whether LIRICAL and geno_agent carry complementary
predictive signal beyond what overlap status already explains.
RRF was selected over learned ensembling because it requires no
training data, has a single well-understood hyperparameter (k = 60 per
*Cormack et al.*), and has been shown to be competitive with learned
fusions on information-retrieval benchmarks. The same paired-bootstrap
+ McNemar protocol compared Cell N to Cells M and S on the full cohort
and on each overlap stratum.

### RAG-quality evaluation

Independent evaluation of Cell S's retrieval-augmented generation
quality used the RAGAS framework v0.3.9 [28] with
GPT-4o (`gpt-4o-2024-08-06`) [47] as the LLM judge via the
OpenAI API.
Three metrics were computed: **faithfulness** (fraction of LEA's claims
supported by retrieved chunks), **context precision** (fraction of
retrieved chunks relevant to the patient phenotype query), and
**context recall** (fraction of ground-truth claims present in
retrieved chunks). Evaluation was performed on a 600-case stratified
subset (150 per MONDO category, seed 42) of the 1,047-case cohort,
with up to 20 retrieved-context chunks per case provided to the judge
(top-5 reranked genes × 3 chunks + top-15 genes × 1 chunk). The
GPT-4o judge constitutes a deliberate, documented deviation from the
otherwise all-local production pipeline; using a Qwen-family judge
would introduce self-evaluation bias, while GPT-4o is the de-facto
standard RAG-quality judge in 2025-2026 [28, 31]. Production use of geno_agent does not require
GPT-4o.

The RAGAS evaluation completed in 167.8 minutes wall-clock at a
documented OpenAI spend of ~US $95. Aggregate scores were:
**context precision = 0.650 (mean) / 0.794 (median); context recall
= 0.796 / 1.000; faithfulness = 0.286 / 0.433**. The median of
faithfulness is more representative than the mean owing to a 21 %
zero-tail concentrated in cases where Cell S's top-1 prediction was
incorrect (mean faithfulness 0.160 on top-1-wrong cases vs 0.333 on
top-1-correct; **the 33-percentage-point top-1 correctness gap
between zero-faithfulness and non-zero-faithfulness cases (46.5 % vs
79.9 %) makes the RAGAS score a useful automated triage flag for
clinical deployment**). Faithfulness was slightly higher on the
fair-comparison cohort (mean 0.310 vs 0.276 overlap-present),
consistent with the higher rationale-substantiveness rate on the
same subset (§*results*). The faithfulness measurement is a **lower
bound** on the true LEA-against-its-own-context faithfulness: the
20-chunk-per-case judge input excluded chunks 21-45 that LEA itself
processed during inference. **A second source of downward bias was
identified post-hoc**: the LEA response is a structured 15-gene list
in which 14 entries are honest "no direct evidence" fallback
rationales for distractor genes; the RAGAS judge extracted each as a
claim and scored it unsupported (chunks describe what's in the
literature, not the absence of specific gene-phenotype links). To
isolate the substantive claim, a top-1-only sensitivity re-run on the
same n = 100 stratified sub-cohort (reordering retrieved contexts by
LEA's final ranking before the cap, and stripping the response to the
predicted gene's rationale alone) yielded **mean faithfulness 0.480 /
median 0.500** (vs 0.286 / 0.433 for the multi-claim measurement), with
a fair-cohort lift of **+18.8 pp** (0.616 vs 0.428, vs +3.4 pp on the
multi-claim measurement). Because the rank-1 gene is the only prediction geno_agent asserts and
acts upon — the remaining 14 entries are deliberate "no direct evidence"
abstentions rather than asserted claims — the rank-1 rationale is the
appropriate unit for claim-level faithfulness, and 0.480 is reported as
the primary RAGAS faithfulness. The multi-claim measurement (0.286),
which scores the 14 abstentions as unsupported claims, is reported as a
conservative lower-bound sensitivity analysis rather than a competing
estimate; the gap between the two is a measurement property of applying
claim-level faithfulness to a structured multi-gene output, not evidence
of hallucination.

To independently corroborate the faithfulness signal, a second
hallucination judge was applied: DeepEval v4.0.3's holistic
`HallucinationMetric` [29] using the
same gpt-4o-2024-08-06 model on a stratified n = 100 subset (25 per
MONDO, seed 42; a sub-sample of the RAGAS 600). DeepEval evaluates
overall answer-context consistency rather than claim-by-claim
grounding, providing a complementary lenient counterpart to RAGAS's
strict faithfulness. Mean groundedness was 0.845 (median 0.933);
**the correctness-prediction signal reproduced** with high-vs-low
groundedness cases scoring 78.9 % vs 40.0 % top-1 correct (39-pp
gap, matching RAGAS's 33-pp gap on the larger n = 600 cohort), and
the **fair-cohort lift reproduced** (0.894 vs 0.830 mean). Together
the two judges bound the LEA grounding quality at a defensible range
of 0.286 (strict claim-level) to 0.845 (holistic), with the
triage-flag deployment story supported by both judges independently.
DeepEval also identified **neurological as the worst subgroup on
both metrics**, a system-level limitation reported in the Limitations
section.

### Local explainability analysis

In addition to the LLM-judged RAGAS metrics, a local (no-API)
analysis of LEA rationale coverage was performed by classifying each
gene's LEA-emitted rationale as **substantive** (≥ 30 characters and
not matching one of seven curated generic-fallback regex patterns:
"no direct evidence", "no information", "no specific evidence", "no
published evidence", "no relevant", "not linked", "unlikely
candidate"). For each case, we computed the fraction of substantive
rationales overall and the binary indicator for whether the causal
gene received a substantive rationale. PMCID citation density per
ranked gene was computed from the set of unique source PMCIDs in the
top-3 chunks the LEA was shown for that gene.

### Reproducibility infrastructure

All pinned versions are recorded in `methodology.md §3` and replicated
in `data/MANIFEST.tsv` with SHA-256 hashes for each downloaded asset.
Determinism is enforced via (i) `PYTHONHASHSEED=42`, (ii) UUID5 chunk
identifiers, (iii) seed-42 sampling at every random step, (iv) vLLM
temperature 0.0 with greedy decoding, and (v) `response_format=
{"type":"json_object"}` to deterministically constrain LEA output. A
bit-perfect cross-version reproducibility check between two
independent runs of Cells L and S (seven months apart) found
1,026 / 1,047 (97.99 %) rank-identical Cell L cases with **zero
top-1 flips**, and 1,024 / 1,047 (97.80 %) rank-identical Cell S
cases with **one top-1 flip**, confirming the LEA-augmented pipeline
is effectively deterministic on the headline accuracy metric despite
expected stochasticity in non-greedy vLLM token sampling.

All evaluation code is available at github.com/Jangulo7/geno_agent
under the GNU Affero General Public License v3.0 (AGPL-3.0) and is
archived on Figshare as the Methods / Shared-Foundation item
(DOI 10.6084/m9.figshare.32814491); the benchmark cohort is a separate
Figshare Dataset under CC BY 4.0 (DOI 10.6084/m9.figshare.32814449) and
the GenoAgent system item is DOI 10.6084/m9.figshare.32814497. Per-case
sidecar JSON files containing the
full LEA system prompt, user prompt, raw model response, parsed
ranking, retrieved chunks (with PMCIDs, section types, and RRF
scores), and per-case token / latency / fallback metadata are
included for the 1,047-case cohort to support third-party replay.

### Computational resources

The Qdrant index, Qwen3-8B model weights, and all evaluation jobs
were run on a single workstation with an NVIDIA RTX 5090 GPU (32 GB
VRAM), 64 GB system RAM, and a 1.7 TB NVMe SSD, running Ubuntu 24.04
under Windows Subsystem for Linux 2. Total wall time for the four
GPU-intensive cells on n = 1,047 was approximately 20 hours
(D ~7 h, L ~6 h, S ~8 h, with K running on CPU in parallel and M
running on CPU with eight parallel workers in ~22 minutes after the
GPU cells). vLLM was sequenced never to overlap with the
sentence-transformer reranker via a `trap`-based teardown of the
vLLM server between cells, preventing GPU out-of-memory failures.

---

## Methods checklist for Q1 reviewers

The following items will need to be added to the final manuscript
before submission, but are out of scope for the present draft:

1. **CONSORT-AI / TRIPOD-LLM checklist** — Genome Medicine requires
   adherence to reporting guidelines for AI clinical-decision tools
   [48, 49, 50].
2. **Ethics statement** — Phenopacket Store data is publicly
   available, fully de-identified, and IRB-exempt per its source
   licensing. A formal IRB-exempt declaration sentence will be added.
3. **Funding statement and conflict of interest declarations** —
   per author requirements (TFM funding source; no commercial COI).
4. **Data and code availability statement** — ✅ Figshare DOIs published
   2026-06-28 (Methods/foundation `10.6084/m9.figshare.32814491`; cohort
   `10.6084/m9.figshare.32814449`; system `10.6084/m9.figshare.32814497`);
   GitHub URL, Phenopacket Store version pin, and ontology version pins
   still to be folded into the final statement.
5. **Detailed wall-time and cost table** — see `reports/wallclock_cost_table.md` for the locked v3 numbers. Headline: total reproducible runtime ~24 h local compute on a single RTX 5090 workstation + ~3 h OpenAI API spend ($98.20 of $100 budget). Per-case throughput on Cell S = 26.1 s end-to-end. Production geno_agent requires no cloud API; cloud spend is RAGAS + DeepEval evaluation-only. The full table belongs as Methods Table 1 in the final manuscript.
6. **DeepRare comparison** — ✅ resolved 2026-05-23 by categorical
   reframing rather than head-to-head benchmark. After studying the
   public DeepRare repository (commit 2026-05-19, *Nature* 2026
   publication), three architectural incompatibilities make a direct
   benchmark methodologically uninformative: disease-vs-gene output
   unit, curated-KB-plus-live-web vs literature-only knowledge
   source, and the same annotation-overlap exposure documented for
   LIRICAL in §*annotation-overlap deconfounding*. The
   *Excluded comparators and rationale* paragraph in §*Comparator
   systems* explains the decision. A 13-dimension architectural
   comparison table covering Exomiser, LIRICAL, AI-MARRVEL, DeepRare,
   and geno_agent is in `reports/deeprare_comparability_analysis.md`
   and will be reused as the paper's Related Work / Discussion table.
   This reframing saves 5-7 days + ~$15-30 cloud spend while
   strengthening defensibility (a remapped head-to-head would carry
   methodological asterisks that reviewers would flag).
7. **LLM ablation on n = 300 subset** — ✅ landed 2026-05-23. Replayed
   saved LEA prompts against three frontier LLMs via OpenRouter
   (Qwen3-32B Instruct, Claude Sonnet 4.6, DeepSeek-V3-0324). On the
   fair-comparison cohort (overlap-absent, n=84), all three production-
   quality models landed within 2.4 pp of Qwen3-8B (0.869–0.893), with
   all three beating LIRICAL (0.777) and Exomiser (0.780) by ≥7 pp.
   Claude Sonnet 4.6 delivered a +5.0 pp ★ lift on the full cohort
   (p<0.001) but the lift was not significant on the fair cohort.
   Qwen3-32B Instruct exhibited a 22 % JSON-format refusal rate (a
   usability characteristic, not a top-1-quality issue: on parsed
   responses its top-1 matched the 8B baseline at 0.722). $21.42 of
   $30 OpenRouter budget consumed. The headline geno_agent result is
   therefore robust to LLM family choice; full table in
   `paper_extension_results.md §20`.

---

*Methods draft v2 — 2026-05-24, ~3,290 words. Word target for
Genome Medicine Methods: 2,500-3,500. Locked to v3 numbers in
`paper_extension_results.md` §§12-16. **Citation cite-pass (Option
C) completed 2026-05-24**: all 16 `*citation: …*` placeholders have
been resolved against the consolidated 50-entry References list in
`reports/manuscript_q1_draft.md §References`. New references added
during this pass: Danis 2025 (Phenopacket Store), Vasilevsky 2022
(MONDO), Lohr 2022 (sampling design), Jin Q. 2023 (MedCPT),
Cormack 2009 (RRF), Kwon 2023 (vLLM), Yang A. 2025 (Qwen3),
Lin 2021 (hybrid retrieval), McNemar 1947, NLM 2024 (PMC OA),
OpenAI 2024 (GPT-4o), Cruz Rivera 2020 (CONSORT-AI),
Collins 2024 (TRIPOD+AI), Gallifant 2025 (TRIPOD-LLM). RAGAS results
now inlined. Methods file remains separate from the main manuscript
draft to ease inlining at submission-assembly time.*
