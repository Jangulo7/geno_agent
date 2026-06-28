# Benchmark dataset development — method & reproducibility

**Scope.** This document records the reasoning and the exact, reproducible steps used to build the
two sibling benchmark datasets shipped with this work:

| Dataset | Distractors | File | n |
|---|---|---|--:|
| **Standard** (genome-wide) | 49 **random** HGNC protein-coding genes | `data/test_cases_1050/test_cases.jsonl` | 1,047 |
| **Hard** (differential-diagnosis) | 49 **phenotype-similar** genes (Resnik BMA) | `data/test_cases_hard/test_cases_hard.jsonl` | 1,047 |

The two variants are **case-paired**: identical `case_id`, `causal_gene`, `hpo_terms`, `diseases`,
and the shared deconfounding metadata (see [`annotation-overlap-method.md`](annotation-overlap-method.md));
**only `candidate_genes` (and the recorded `causal_gene_index_in_candidates`) differ.** This yields a
**difficulty axis orthogonal to the leakage axis**, enabling a clean difficulty × leakage factorial.

All numbers below were re-derived from the pipeline's intermediate artefacts and match the
manuscript text.

---

## 1. Source cohort & provenance

Cases were drawn from the **GA4GH Phenopacket Store v0.1.26** (released 2026-01-13), which aggregates
literature-curated rare-disease phenopackets with gene-level *solved* diagnoses. Each case therefore
ties a real patient phenotype to a peer-reviewed source publication and a curated causal gene —
the basis for both the literature-retrieval task and the annotation-overlap deconfounding.

**Pinned inputs (provenance).**

| Resource | Version | Path / source |
|---|---|---|
| GA4GH Phenopacket Store | **v0.1.26** (2026-01-13) | `monarch-initiative/phenopacket-store` release |
| HPO (`hp.obo`, `genes_to_phenotype.txt`, `phenotype.hpoa`) | **2026-02-16** | `data/Human_Phenotype_Ontology/` |
| Mondo Disease Ontology (`mondo.obo`) | **releases/2026-03-03** | `data/MONDO_Disease_Ontology/mondo.obo` |
| HGNC complete set | **2026-04-07** | `data/HGNC/hgnc_complete_set_2026-04-07.txt` |
| PMC OA retrieval index | `geno_agent_pmc_oa_v1` (Qdrant) | retrieval-index build (separate pipeline) |

> **Reproducibility note.** The helper `scripts/cases/04_download_phenopacket_store.sh` still defaults
> to `PHENOPACKET_STORE_VERSION=0.1.19`; the released cohort was built from **v0.1.26** (as pinned in
> `scripts/cases/18b_build_hard_candidates.py`). Re-running the download must set
> `PHENOPACKET_STORE_VERSION=0.1.26`, and the script default should be bumped to match.

---

## 2. Inclusion / exclusion funnel

Of **9,588** phenopackets loaded (`01_all_phenopackets.jsonl`), inclusion required:

1. **(i)** a single causal gene with a **SOLVED** interpretation status;
2. **(ii)** **≥ 3 HPO terms** (HPO 2026-02-16);
3. **(iii)** a **Mondo** mapping (2026-03-03) to one of four broad categories —
   *developmental, immunological, metabolic, neurological*; and
4. **(iv)** **≥ 5 PMC OA full-text articles** indexed for the causal gene in the retrieval index, so
   that literature retrieval is non-trivial.

**Reasoning.** (i)–(ii) guarantee an unambiguous label and enough phenotype signal to query on;
(iii) gives a tractable, clinically meaningful stratification and removes unmappable/junk diseases;
(iv) guarantees the retrieval task is *answerable from the corpus* rather than testing corpus gaps.

**Funnel (each step = one pipeline artefact):**

| Step | Criterion | Artefact | n |
|---|---|---|--:|
| load | — | `01_all_phenopackets.jsonl` | 9,588 |
| (i)+(ii) | single SOLVED gene · ≥3 HPO | `02_eligible.jsonl` | 6,382 |
| (iii) | Mondo → 4 categories | `03_categorized.jsonl` | 4,670 |
| sample | stratified draw (seed 42) | `04_sampled.jsonl` | 1,050 |
| (iv) | ≥5 PMC articles (verified on sample) | `05_validated.jsonl` | 1,050 |
| candidate lists | protein-coding pool (RNU drop) | `06_with_candidates.jsonl` → `test_cases.jsonl` | **1,047** |

The eligible pool after (iii) was **4,670** cases — **464** developmental, **390** immunological,
**672** metabolic, **3,144** neurological. Criterion (iv) was verified on the drawn sample and **did
not reduce it** (`05_validated` = `04_sampled` = 1,050).

Scripts: `13_load_phenopackets.py` · `14_apply_inclusion_exclusion.py` · `15_categorize_by_mondo.py`
· `17_validate_pmc_coverage.py` (`MIN_PMC_ARTICLES_PER_GENE = 5`, live hybrid query against the index).

---

## 3. Disproportionate stratified sampling

To adequately power analysis of the smallest categorical subgroup (immunological), a
**disproportionate stratified sample of 1,050** cases was drawn with **seed 42**: **250 each** from
the developmental, metabolic, and neurological pools and **300** from the immunological pool.

**Reasoning.** Disproportionate stratified sampling is standard when one subgroup is rate-limiting for
power and the overall cohort is large enough that stratum-weighted estimates remain unbiased. The
immunological pool (390 eligible) is the binding constraint, so it is over-sampled relative to its
share; reported overall estimates are stratum-weighted to remain representative.

Script: `16_stratified_sample.py` (seed 42).

---

## 4. Candidate-list construction — standard variant

For each case a **50-gene candidate list** was assembled as the single causal gene **plus 49
distractor genes** drawn **uniformly at random, without replacement**, from the pinned **HGNC
protein-coding** gene set (**19,296** approved symbols; HGNC 2026-04-07), **excluding the causal gene**.

Sampling uses a **per-case derived seed** — `BLAKE2b("{global_seed}|{case_id}")` with global seed 42
(`digest_size=8` → integer seed) — so **any single case regenerates independently and bit-identically**
without resampling the others. The 50-gene list is then **shuffled** and the causal gene's resulting
position recorded as `causal_gene_index_in_candidates`.

**Protein-coding exclusion (1,050 → 1,047).** Three sampled neurological cases whose causal gene is a
**small nuclear RNA** gene — **two `RNU4-2`** (`PMID_38991538` Individual 2 / Individual 42) and **one
`RNU2-2`** (`PMID_40442284` Individual 4) — fall outside the protein-coding pool and were dropped at
this stage, giving the final **n = 1,047** (250 developmental, 300 immunological, 250 metabolic,
**247** neurological).

This is the standard candidate-list variant; random distractors from the full protein-coding space
constitute a standard **genome-wide** design (separability across the whole genome).

Script: `18_build_candidate_lists.py` (`N_DISTRACTORS = 49`, `RANDOM_SEED = 42`).

---

## 5. Candidate-list construction — hard variant

To provide a **difficulty axis orthogonal to the leakage axis**, we additionally release a **hard**
variant in which the 49 distractors are the genes **phenotypically most similar** to each case rather
than random — stressing differential-diagnosis behaviour instead of genome-wide separability.

**Similarity (deterministic, version-pinned).**

- Phenotypic similarity between the case HPO profile and a gene's annotated phenotypes is the
  **best-match-average (BMA)** of **Resnik** term similarities — the information content (IC) of the
  most-informative common ancestor over the HPO is-a DAG. BMA is symmetric: `(fwd + rev) / 2` over the
  two term sets (the Phenomizer/Exomiser-standard measure).
- **IC** is computed from the gene→HPO annotation corpus (`genes_to_phenotype.txt`, HPO 2026-02-16),
  with annotation frequencies **propagated over the `hp.obo` is-a DAG**; `IC(t) = −ln P(t)`.

**Selection.** The candidate pool is the HGNC protein-coding genes (same pool as §4) **that have HPO
annotations**, with two exclusions so that *a distractor can never be a genuine alternative cause*:

- exclude the **causal gene**, and
- exclude **any gene annotated to the case's own causal disease(s)** (clean hard negatives, no label
  ambiguity).

The **top-49 by BMA** are taken; **ties broken by gene symbol (ascending)** for determinism. The
final 50-gene list is shuffled with the **same per-case `BLAKE2b(42|case_id)` seed** as the standard
variant, so the hard variant is equally deterministic and case-paired. **All 1,047 cases yielded ≥ 49
scored candidates, so no random fill was required** (the stage-18 random-fill fallback exists for
`< 49` scored candidates but was never triggered).

Script: `18b_build_hard_candidates.py`.

---

## 6. Case-paired design & shared deconfounding layers

| Field | Standard | Hard |
|---|---|---|
| `case_id`, `causal_gene`, `hpo_terms`, `diseases` | identical | identical |
| `annotation_overlap` / recency strata | identical (independent of distractors) | identical |
| `candidate_genes`, `causal_gene_index_in_candidates` | random | Resnik-similar |

Because the deconfounding flag depends only on the *causal disease and source publication* — not on
the distractor list — the **fair (overlap-absent, n = 282)** and recency strata are **identical**
across both variants (see [`annotation-overlap-method.md`](annotation-overlap-method.md)). This is
what makes the **difficulty (standard/hard) × leakage (full/fair)** contrast a clean, fully paired
2×2.

---

## 7. Reproduction

```bash
# 0) source cohort (pin the version explicitly — see provenance note)
PHENOPACKET_STORE_VERSION=0.1.26 bash scripts/cases/04_download_phenopacket_store.sh

# 1) funnel: load -> inclusion/exclusion -> categorize -> stratified sample -> PMC coverage
PYTHONPATH=. python scripts/cases/13_load_phenopackets.py
PYTHONPATH=. python scripts/cases/14_apply_inclusion_exclusion.py
PYTHONPATH=. python scripts/cases/15_categorize_by_mondo.py
PYTHONPATH=. python scripts/cases/16_stratified_sample.py        # seed 42
PYTHONPATH=. python scripts/cases/17_validate_pmc_coverage.py    # >=5 PMC articles

# 2a) STANDARD candidate lists (random distractors) -> test_cases.jsonl
PYTHONPATH=. python scripts/cases/18_build_candidate_lists.py
PYTHONPATH=. python scripts/cases/19_finalize_test_cases.py
PYTHONPATH=. python scripts/cases/20_validate_test_cases.py

# 2b) HARD candidate lists (Resnik-similar distractors) -> test_cases_hard.jsonl
PYTHONPATH=. python scripts/cases/18b_build_hard_candidates.py
```

**Determinism.** Every stochastic step is seeded: stratified sampling at global seed 42, and each
case's candidate shuffle at `BLAKE2b("42|case_id")`. Given the pinned inputs, both datasets
regenerate **bit-identically**, and any single case can be regenerated in isolation without
perturbing the others.

**Archived artefacts.** Standard cohort — Figshare DOI `10.6084/m9.figshare.32814449`; hard sibling —
Figshare DOI `10.6084/m9.figshare.32816468` (drop-in `test_cases_hard.jsonl`). Intermediate funnel
artefacts (`01`–`06_*.jsonl`) are retained under `data/test_cases_1050/` for audit.

---

## 8. Limitations

- **Disproportionate sampling** trades representativeness of raw counts for subgroup power; overall
  estimates must be stratum-weighted (they are) to stay unbiased.
- **Protein-coding restriction** excludes non-coding causal genes (the 3 RNU cases); the benchmark
  therefore measures protein-coding gene prioritisation specifically.
- **Hard distractors** are phenotype-similar by Resnik BMA over *current* HPO annotations; genes with
  sparse/absent HPO annotations cannot be selected as hard distractors, so difficulty is bounded by
  annotation completeness.
- **Version coupling.** All counts are exact for the pinned resource versions above; a different HPO,
  Mondo, HGNC, or Phenopacket-Store release can shift the funnel and must be reported.

---

*Scripts:* `scripts/cases/13`–`20` and `18b`.  *Related:* [`annotation-overlap-method.md`](annotation-overlap-method.md)
(deconfounding metadata), `reports/methodology_test_case_selection.md`.
