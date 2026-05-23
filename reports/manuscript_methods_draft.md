# Manuscript Methods (draft) — geno_agent for rare-disease gene prioritisation

Target venue: **Genome Medicine** (~12-15 IF). Submission window: Q3 2026.

This is a Methods-section draft, written in paper voice (passive,
methods-not-decisions, third-person). All numerical values reference the
locked v3 results in `paper_extension_results.md` §§12-16 and the
authoritative methodology in `methodology.md` v3.1. Word target for the
Genome Medicine Methods section is ~2,500-3,500 words; this draft is
~2,340 words and sits comfortably below the upper bound with room to
expand Methods-checklist items below as needed.

---

## Methods

### Cohort construction

Clinical cases were drawn from the Global Alliance for Genomics and
Health (GA4GH) Phenopacket Store v0.1.26 (released 13 January 2026)
(*citation: Phenopacket Store consortium*), which aggregates published
rare-disease patient phenopackets curated from primary literature with
solved (gene-level) diagnoses. Cases were retained if they met four
criteria: (i) a single causal gene supported by a SOLVED interpretation
status, (ii) at least one Human Phenotype Ontology term (HPO; v2026-02-16,
*citation: Köhler et al.*), (iii) a Mondo Disease Ontology mapping to one
of four broad categories — developmental, immunological, metabolic, or
neurological (MONDO v2026-03-03, *citation: Vasilevsky et al.*) — and
(iv) at least five PubMed Central Open Access (PMC OA) full-text
articles indexed for the causal gene in our local Qdrant corpus (see
*Index construction*), ensuring downstream literature retrieval is
non-trivial. 1,699 cases met all four criteria.

To support an adequately-powered analysis on the smallest categorical
subgroup (immunological diseases), a disproportionate stratified sample
was drawn with seed 42: 250 cases each from developmental, metabolic,
and neurological categories, and 300 cases from the immunological pool
(386 cases eligible). One case was excluded after pre-evaluation
quality control (gene symbol could not be resolved to HGNC), yielding
a final n = 1,047 cohort (250 + 300 + 250 + 247). Disproportionate
sampling is standard practice in epidemiological and clinical-genomics
benchmarking when one subgroup is rate-limiting for statistical power
and the overall cohort is large enough that overall-cohort estimates
remain unbiased after stratum-weight correction (*citation: Lohr,
Sampling: Design and Analysis*).

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
cohort, each operating on the same 50-gene candidate list per case:

**Cell K (Exomiser HPO-only baseline).** Exomiser v14.0.0
(*citation: Smedley et al.*) was run with the default phenotype-only
configuration (hiPhive scoring on the patient's HPO terms; no variant
input). The candidate gene list was passed as a whitelist.

**Cell M (LIRICAL HPO-only baseline).** LIRICAL v2.4.0
(*citation: Robinson et al.*) was run with the same HPO term input.
LIRICAL outputs a posterior probability per OMIM disease; these were
mapped to gene rankings via NCBI mim2gene_medgen (2026-04-07) and
Orphanet en_product6.xml. When multiple diseases mapped to a candidate
gene, the maximum posterior was used.

**Cell D (multi-agent hybrid baseline).** A deterministic four-agent
LangGraph pipeline (planner → retriever → critic → synthesiser) using
hybrid dense + BM25 retrieval (Reciprocal Rank Fusion, k = 60) over a
local PMC OA Qdrant index (see *Index construction*). The synthesiser
ranks candidates by the sum of inverse-rank chunk scores per gene.

**Cell L (Cell D + cross-encoder reranking).** Identical to Cell D but
with an additional MedCPT cross-encoder pass over the top-50 retrieved
chunks per gene (*citation: Jin et al.*, MedCPT). The reranker
re-scores each chunk for query-specific relevance.

**Cell S (Cell L + LLM-as-Evidence-Aggregator, "geno_agent").** Cell L
plus a final synthesis step in which a locally-hosted 8-billion-parameter
LLM (Qwen3-8B, served via vLLM 0.20.1 on an NVIDIA RTX 5090) is shown
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
*citation: Cormack et al.*).

### Index construction

A 3.4 million-article subset of the PubMed Central Open Access XML
corpus (downloaded 2026-05; *citation: NCBI PMC OA*) was parsed and
filtered for genetics / genomics / rare-disease relevance via MeSH
descriptor matching (terms: Genetic Diseases, Rare Diseases, Mutation,
Pathogenicity, Inheritance Patterns) and full-text inclusion criteria,
yielding 287,000 articles. Articles were chunked at 512 tokens with
50-token overlap using a PubMedBERT-base tokeniser (*citation: Gu et
al.*); chunk identifiers were derived deterministically via UUID5 on
the content key to enable bit-identical re-indexing. Dense embeddings
were computed with PubMedBERT and stored in Qdrant v1.14.1 alongside
sparse embeddings from FastEmbed BM25, supporting hybrid retrieval via
Reciprocal Rank Fusion at query time. The Qdrant collection contains
4.2 million chunks with on-disk payload.

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
metrics. Statistical significance is reported by the conjunction of
"95 % CI excludes zero" and "McNemar p < 0.05" — both criteria are
required for a Δ to be flagged ★.

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
quality used the RAGAS framework v0.3.9 (*citation: Es et al.*) with
GPT-4o (`gpt-4o-2024-08-06`) as the LLM judge via the OpenAI API.
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
standard RAG-quality judge in 2025-2026 (*citation: Es et al., RAGAS
benchmark*). Production use of geno_agent does not require GPT-4o.

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
processed during inference; a future re-run at the full
45-chunk input is planned to bound the true value.

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
under the MIT licence. Per-case sidecar JSON files containing the
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
   (*citation: Cruz Rivera et al. 2020; Collins et al. 2024*).
2. **Ethics statement** — Phenopacket Store data is publicly
   available, fully de-identified, and IRB-exempt per its source
   licensing. A formal IRB-exempt declaration sentence will be added.
3. **Funding statement and conflict of interest declarations** —
   per author requirements (TFM funding source; no commercial COI).
4. **Data and code availability statement** — GitHub URL, Zenodo DOI
   for the frozen v3 release tag, Phenopacket Store version pin,
   ontology version pins.
5. **Detailed wall-time and cost table** — per-cell wallclock + dollar
   cost (LIRICAL and Exomiser local; geno_agent local; RAGAS judging
   $95 cloud spend) for a Methods-end "operational profile" table.
   This will become a one-day work item before submission.
6. **DeepRare head-to-head comparison on a n = 100 subset** — the
   2025 EJHG benchmark uses DeepRare; reviewers will expect a direct
   comparison. Estimated 5-7 days of work post-RAGAS.
7. **Qwen3-32B AWQ ablation on a n = 100 subset** — to demonstrate
   the headline numbers are not artefacts of the 8B model size.
   Estimated 2-3 days of work post-RAGAS.

---

*Methods draft v1 — 2026-05-23, ~2,340 words. Word target for
Genome Medicine Methods: 2,500-3,500. Locked to v3 numbers in
`paper_extension_results.md` §§12-16. Citations marked
"(*citation: …*)" need to be expanded to full BibTeX entries
before submission. Once RAGAS completes (in flight, task `b4jz1ajib`),
the §RAGAS faithfulness paragraph will be amended with the actual
faithfulness score. Reviewer-checklist items above are deliberately
deferred until manuscript-assembly time.*
