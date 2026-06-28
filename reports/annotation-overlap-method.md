# Annotation-overlap deconfounding — method & per-case metadata

**Scope.** This document specifies, for reproducibility, a general *annotation-overlap
deconfounding* method and the per-case metadata that operationalises it. The method yields a
**leakage-free fair-comparison subset (n = 282)** of the geno_agent benchmark on which curated,
HPO-annotation-derived tools cannot benefit from exposure to a case's own source publication. It is
one of the methodological contributions of this work and is intended to transfer to any
phenotype-driven gene/disease-prioritization benchmark evaluated against tools curated from a
citation-bearing annotation resource.

---

## 1. The confound

Phenotype-driven prioritisation tools such as **Exomiser** (hiPhive) and **LIRICAL** rank candidate
genes/diseases using knowledge curated in the **HPO annotation file (`phenotype.hpoa`)**, in which
each disease–phenotype annotation carries one or more literature **references** (PMIDs). When a
benchmark case is itself *derived from* a publication that is also a curated reference for that
case's causal disease, the tool's knowledge base already contains a hand-curated, expert-distilled
summary of the very paper the case was built from. Measured performance on such cases conflates
genuine phenotype-driven inference with **recall of memorised, source-aligned annotations** — a
form of train/test leakage specific to ontology-annotation benchmarks. We refer to this as the
**annotation-overlap confound**.

Because leakage status is a property of *(source publication × causal disease × annotation
resource)* — not of the candidate-gene list or of the model under test — it can be computed
*a priori* and used to partition any cohort into a confounded and a deconfounded subset.

---

## 2. General method

Let a benchmark consist of cases `c`, each with

- a **source publication** identified by `pmid(c)` (the paper the case was abstracted from), and
- a set of **ground-truth disease identifiers** `D(c)` in the namespace used by the annotation
  resource (here OMIM).

Let the annotation resource define a set of **reference pairs**

```
R = { (d, p) : disease d is annotated with reference PMID p in the resource }
```

Define the per-case **annotation-overlap flag**

```
overlap(c) = 1   if  ∃ d ∈ D(c)  such that  (d, pmid(c)) ∈ R
           = 0   otherwise
```

The cohort partitions into

- **overlap-present** `{ c : overlap(c) = 1 }` — the case's source paper is a curated reference for
  its causal disease (potential leakage for resource-curated tools), and
- **overlap-absent / fair** `F = { c : overlap(c) = 0 }` — no such citation exists, so a tool curated
  from the resource **cannot have had source-publication exposure** to the case.

All performance comparisons against resource-curated baselines are reported **both** on the full
cohort (for power and external validity) **and** on `F` (the deconfounded primary endpoint). The
method is agnostic to the tool under evaluation: it only requires `pmid(c)`, `D(c)`, and the
resource's reference table.

---

## 3. Deconfounding metadata (operationalisation in this study)

### 3.1 Annotation-overlap flag

For each of the 1,047 cohort cases a binary `annotation_overlap` flag was computed as **1** if the
case's source PMID — encoded in the `case_id` and originally derived from the phenopacket
`metaData.externalReferences[0].id` field at cohort-construction time — appears in
**`phenotype.hpoa` (version 2026-02-16)** as a reference for **any** annotation of **any** of the
case's causal **OMIM** disease IDs; **0** otherwise.

**Procedure** (`scripts/eval/compute_annotation_overlap.py`):

1. **Build the reference index.** Stream `phenotype.hpoa`; for each data row read
   `database_id` (disease), `reference`, and `hpo_id`. The `reference` field may be semicolon-
   delimited; split it and keep only `PMID:`-prefixed references. Accumulate
   `R = {(database_id, PMID) → [hpo_id, …]}`, i.e. **deduplicated `(disease, PMID)` keys** after
   PMID-only filtering. (For 2026-02-16 this yields 282,723 data rows → 9,852 unique `(disease, PMID)`
   keys.)
2. **Resolve each case.** Parse the source PMID from the `case_id` prefix
   (`GENE:PMID_<digits>_…` → `PMID:<digits>`); collect the case's OMIM disease IDs from its
   `diseases[*].id` (those with an `OMIM:` prefix).
3. **Join.** `overlap = 1` iff `(omim, pmid) ∈ R` for at least one of the case's OMIM diseases;
   record the number of matching rows and the matching HPO IDs for audit.

All **1,047** cases resolved to **both** a source PMID and ≥1 OMIM disease ID (no edge cases).

**Result.** The flag partitions the cohort into

| Subset | n | % | Interpretation |
|---|--:|--:|---|
| overlap-present | 765 | 73.1 % | source paper cited for the causal disease in `phenotype.hpoa` |
| **overlap-absent (fair)** | **282** | **26.9 %** | **no source-publication exposure for resource-curated tools** |

**Per-case metadata schema** (`data/test_cases_1050/annotation_overlap.json`; one record per case):

```json
{
  "case_id": "AAGAB:PMID_24573067_CASE_REPORT",
  "source_pmid": "PMID:24573067",
  "omim_ids": ["OMIM:148600"],
  "category": "developmental",
  "overlap": 1,
  "matching_rows": 7,
  "matching_hpo_ids": ["HP:0007530", "HP:0045059", "..."]
}
```

`overlap` is the deconfounding flag; `matching_rows` / `matching_hpo_ids` make every positive call
auditable back to the exact `phenotype.hpoa` annotations responsible for it.

### 3.2 Publication-recency strata

To approximate a *novel-association* setting (where neither the source paper nor knowledge derived
from it could plausibly be in a curated resource), source-publication dates were retrieved for the
**415 unique cohort PMIDs** from **NCBI E-utilities** (`efetch`), using
`<PubMedPubDate PubStatus="pubmed">` as the canonical date (falling back to `JournalIssue/PubDate`
when absent). **100 %** of PMIDs resolved (oldest **1988**, most recent **2025**, **median 2018**
over unique PMIDs).

Cases were split at **2020-01-01** into **pre-2020 (n = 601; 57.4 %)** and **post-2020 (n = 446;
42.6 %)** strata. Crossing recency with annotation overlap gives the strictest available cohort,
**post-2020 × overlap-absent (n = 88; 8.4 %)** — the closest available approximation to a
novel-association cohort: the source PMID is recent **and** the paper is not cited in
`phenotype.hpoa` for the causal OMIM disease. (For completeness, pre-2020 × overlap-absent = 194,
so the two overlap-absent strata sum to the fair cohort, 194 + 88 = 282.)

Script: `scripts/eval/pubmed_date_lookup.py` (batched ≤ 100 PMIDs/request, ≤ 3 retries with
backoff; deterministic given the PMID set).

---

## 4. Resulting analysis subsets

| | Full cohort | overlap-absent (FAIR) |
|---|--:|--:|
| **All cases** | 1,047 | 282 |
| **pre-2020** | 601 | 194 |
| **post-2020** | 446 | **88** (strictest / novel-association proxy) |

The **overlap-absent (FAIR) cohort (n = 282)** is the pre-declared primary endpoint for all
geno_agent-vs-curated-baseline comparisons; the full cohort and recency strata are reported as
supportive analyses. Stratified estimation and paired tests are computed on each subset
(`scripts/eval/aggregate_stratified.py`, `scripts/eval/aggregate_recency.py`), with multiplicity
control over the pre-declared family (`scripts/eval/multiplicity_correction.py`; Holm + Benjamini-
Hochberg).

---

## 5. Reproducibility

**Inputs / versions**

| Resource | Identifier / version | Path or source |
|---|---|---|
| HPO annotations | `phenotype.hpoa` **2026-02-16** | `data/Human_Phenotype_Ontology/phenotype.hpoa` |
| Cohort cases | 1,047-case benchmark (Phase 1B) | `data/test_cases_1050/test_cases.jsonl` |
| Disease namespace | OMIM (from phenopacket `diseases[*].id`) | per-case |
| Source PMIDs | from `case_id` ← phenopacket `metaData.externalReferences[0].id` | per-case |
| Publication dates | NCBI E-utilities `efetch`, `PubMedPubDate[PubStatus="pubmed"]` | live API |
| Recency cutoff | 2020-01-01 | analysis constant |

**Commands**

```bash
# 1) per-case annotation-overlap flag  ->  annotation_overlap.json
PYTHONPATH=. python scripts/eval/compute_annotation_overlap.py \
  --test-cases data/test_cases_1050/test_cases.jsonl \
  --hpoa       data/Human_Phenotype_Ontology/phenotype.hpoa \
  --out        data/test_cases_1050/annotation_overlap.json

# 2) publication dates for the 415 unique PMIDs (recency strata)
PYTHONPATH=. python scripts/eval/pubmed_date_lookup.py

# 3) stratified estimates + paired tests on full vs FAIR (overlap-absent)
PYTHONPATH=. python scripts/eval/aggregate_stratified.py \
  --eval-root data/eval_1050 \
  --test-cases data/test_cases_1050/test_cases.jsonl \
  --overlap data/test_cases_1050/annotation_overlap.json
```

**Determinism & provenance.** The flag is a pure function of (`case_id` PMID, case OMIM IDs,
`phenotype.hpoa` version); given the pinned inputs it is fully reproducible and order-independent.
Every positive call is traceable to specific HPOA rows via `matching_hpo_ids`. The flag depends only
on the *causal disease and source publication* — **not** on the candidate-gene list — so it is
identical across cohort variants that share case IDs and causal genes (e.g. the random-distractor
*standard* and Resnik-similar *hard* cohorts), which is what permits a clean difficulty × leakage
factorial.

---

## 6. Limitations & scope

- **Resource-version dependence.** Overlap status is defined relative to a fixed `phenotype.hpoa`
  release (2026-02-16). A different release can reclassify borderline cases; the version must be
  reported with any result.
- **Citation ≠ exhaustive leakage.** The flag captures *direct* source-paper citation for the causal
  disease. It does not detect indirect leakage (e.g. derivative reviews, or knowledge propagated
  through other annotations); it is therefore a **conservative lower bound** on confounding, and the
  FAIR cohort is a *necessary but not sufficient* deconfounding.
- **OMIM-namespace coupling.** Disease matching uses OMIM IDs; cases whose causal disease is only
  representable in another namespace would need a namespace cross-walk (not required here — all 1,047
  cases carried an OMIM ID).
- **Recency is a proxy.** Publication date approximates, but does not guarantee, absence from a
  curated resource; the post-2020 × overlap-absent cohort is the closest available, not an exact,
  novel-association set.

---

*Scripts:* `scripts/eval/compute_annotation_overlap.py` · `scripts/eval/pubmed_date_lookup.py` ·
`scripts/eval/aggregate_stratified.py` · `scripts/eval/aggregate_recency.py` ·
`scripts/eval/multiplicity_correction.py`.
