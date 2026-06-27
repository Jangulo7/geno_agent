# GenoAgent Benchmark Cohort (n=1,047) — Data Descriptor

**Title.** GenoAgent Benchmark: A Stratified Rare-Disease Benchmark Cohort for
Literature-Based Causal Gene Prioritization (n=1,047)

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**Figshare item type.** Dataset · **License.** CC BY 4.0 · **Version.** v1.0 (n=1,047)

**DOI (this dataset).** `10.6084/m9.figshare.32814449`

## Summary

A deterministic, reproducible benchmark of **1,047 rare-disease cases** for
evaluating *literature-based* causal gene prioritization. Each case pairs a
patient phenotype profile (Human Phenotype Ontology terms) with a 50-gene
candidate list (1 causal + 49 distractor genes) and the true causal gene,
stratified across four disease categories. Derived from the GA4GH Phenopacket
Store v0.1.26 by a seeded, version-pinned pipeline so the cohort regenerates
bit-for-bit.

The cohort additionally ships two **deconfounding sidecars** used in the
accompanying study: per-case annotation-overlap flags (whether a case's source
publication is cited by `phenotype.hpoa` for the causal gene) and source
publication dates (for recency stratification).

## Provenance

| Input | Pinned version | License |
|---|---|---|
| GA4GH Phenopacket Store | **v0.1.26** (released 2026-01-13) | CC BY 4.0 |
| MONDO Disease Ontology (categorisation) | v2026-03-03 | CC BY 4.0 |
| HGNC complete set (distractor gene pool) | 2026-04-07 | open (EBI/HGNC) |
| HPO `phenotype.hpoa` (overlap flag) | v2026-02-16 | open (HPO) |

- **Random seed:** 42 (`RANDOM_SEED`); distractor sampling uses a per-case derived
  seed `blake2b(global_seed, case_id)` so individual cases regenerate independently.
- **Sampling:** disproportionate stratified — 250 developmental + 300 immunological
  + 250 metabolic + 247 neurological (immunological oversampled for subgroup power).
- **Coverage gate:** every causal gene has ≥5 PMC Open Access articles (validated
  against the `geno_agent_pmc_oa_v1` index; fingerprint in `MANIFEST.tsv`).
- **Pipeline:** stages 13–20 (`scripts/cases/`) of the GenoAgent methods/foundation
  release — see *How to regenerate*.

## Files

| File | Rows | What |
|---|---:|---|
| **`test_cases.jsonl`** | 1,047 | **Canonical cohort** — one JSON object per case (schema below). SHA-256 pinned in `test_cases_manifest.json`. |
| `06_with_candidates.jsonl` | 1,047 | Pre-finalisation record with extra provenance fields (`subject_id`, `mondo_ids`, `interpretations`, `category_resolution`, `source_path`, `n_candidates`). |
| `05_validated.jsonl` | 1,050 | Cases passing the PMC-coverage acceptance gate (pre-candidate-list). |
| `04_sampled.jsonl` | 1,050 | Stratified sample before validation. |
| `03_categorized.jsonl` | 4,670 | Eligible cases assigned to a MONDO category. |
| `02_eligible.jsonl` | 6,382 | Cases passing inclusion/exclusion (≥3 HPO terms, single causal gene). |
| `01_all_phenopackets.jsonl` | 9,588 | All loaded phenopackets (raw provenance root). |
| `annotation_overlap.json` | — | Per-case annotation-overlap flags + `meta` (cohort overlap rate). Deconfounding input. |
| `pmid_dates.json` | — | Source-publication dates per PMID + `meta` (recency stratification input). |
| `test_cases_manifest.json` | — | Build manifest: pinned versions, seed, category distribution, SHA-256 + byte size of `test_cases.jsonl`. |
| `05_validated_stats.json` | — | Validation statistics (pass/fail/replacements). |
| `MANIFEST.tsv` | — | Provenance + SHA-256 of upstream sources (incl. the index fingerprint). |
| `CHECKSUMS.sha256` | — | SHA-256 of every file in this bundle. |

The 01–06 staged files are included for full provenance/transparency; **most reusers
need only `test_cases.jsonl`** plus the two sidecars.

## Data dictionary — `test_cases.jsonl`

| Field | Type | Description |
|---|---|---|
| `case_id` | string | Stable ID, `"{CAUSAL_GENE}:{phenopacket_id}"` (e.g. `AAGAB:PMID_24573067_CASE_REPORT`). |
| `category` | string | One of `developmental` \| `immunological` \| `metabolic` \| `neurological`. |
| `hpo_terms` | list[string] | Patient phenotype as HPO term IDs (`HP:NNNNNNN`), ≥3 per case. |
| `diseases` | list[object] | Associated disease(s): `{ "id": "OMIM:NNNNNN", "label": str }`. |
| `causal_gene` | string | HGNC symbol of the true causal gene (the prediction target). |
| `candidate_genes` | list[string] | 50 HGNC symbols: the causal gene + 49 seeded distractors. This is the input list to rank. |
| `causal_gene_index_in_candidates` | int | 0-based index of `causal_gene` within `candidate_genes` (ground-truth position). |
| `pmc_article_count` | int | Number of PMC OA articles mentioning the causal gene (coverage; ≥5 by construction). |
| `source_phenopacket` | string | Relative path to the source phenopacket JSON within Phenopacket Store v0.1.26. |

**Sidecars.** `annotation_overlap.json` and `pmid_dates.json` are objects with a
`meta` block (cohort-level counts) plus per-case entries keyed by `case_id` /
source PMID; see their `meta` for field definitions. The `meta.hpoa_source` in
`annotation_overlap.json` records the local generation path (benign provenance,
no secret).

## License

**CC BY 4.0.** Derived from the GA4GH Phenopacket Store (CC BY 4.0); annotated with
HPO/MONDO/HGNC (open / CC BY). Reuse freely **with attribution** (cite below).

## Recommended citation

```bibtex
@dataset{angulo2026genoagent_cohort,
  author    = {Angulo, Johanna},
  title     = {A Stratified Rare-Disease Benchmark Cohort for Literature-Based
               Causal Gene Prioritization (n=1,047)},
  year      = {2026},
  publisher = {Figshare},
  version   = {v1.0},
  doi       = {10.6084/m9.figshare.32814449},
  note      = {Derived from GA4GH Phenopacket Store v0.1.26; CC BY 4.0.}
}
```

## How to regenerate (verify reproducibility)

The cohort is fully reproducible from public inputs + the methods/foundation code:

```bash
# GenoAgent methods/foundation release (its own DOI / repo), stages 13-20:
python scripts/cases/13_load_phenopackets.py        # Phenopacket Store v0.1.26
python scripts/cases/14_apply_inclusion_exclusion.py
python scripts/cases/15_categorize_by_mondo.py
python scripts/cases/16_stratified_sample.py --per-category-target 250,300,250,247
python scripts/cases/17_validate_pmc_coverage.py
python scripts/cases/18_build_candidate_lists.py    # seed 42
python scripts/cases/19_finalize_test_cases.py
python scripts/cases/20_validate_test_cases.py
```

Verify your `test_cases.jsonl` against the SHA-256 in `test_cases_manifest.json`
(`c355b800e53e5347…`). Methods/foundation code DOI: `10.6084/m9.figshare.32814491`.

## Known limitations

- A **curated/derived** benchmark (selection + seeded distractor sampling), not
  primary clinical data — appropriate as a reproducible evaluation set, not a
  population sample.
- Cohort **annotation-overlap rate ≈ 73%** (765/1,047): for many cases the source
  publication is cited by `phenotype.hpoa` for the causal gene. The
  `annotation_overlap.json` flag lets you evaluate on the **fair (overlap-absent)**
  subset — recommended for unbiased comparison against curated tools.
- One causal gene per case; distractors are protein-coding HGNC genes.

## Related materials (Figshare metadata)

These are the relations declared on the Figshare item (relation type · identifier
type · identifier):

| Relation type | Identifier type | Identifier |
|---|---|---|
| Is derived from | URL | `https://github.com/monarch-initiative/phenopacket-store` (GA4GH Phenopacket Store v0.1.26) |
| Is supplemented by | DOI | `10.6084/m9.figshare.32814491` (build-recipe / methods item) |
| Is referenced by | DOI | `10.6084/m9.figshare.32814497` (system evaluated on this cohort) |
| Is supplemented by | URL | `https://github.com/Jangulo7/geno_agent` (source-code repository) |

## Relationship to the GenoAgent papers

- This **dataset** is the citable benchmark, used by the GenoAgent system evaluation.
- **Methods / foundation** (corpus + index build recipe, ontology provenance) is a
  separate release/item: `10.6084/m9.figshare.32814491`.
- **GenoAgent system** (the agentic-RAG that is evaluated on this cohort): `10.6084/m9.figshare.32814497`.
- A separate variant-interpretation safety benchmark (different repository) reuses
  the shared foundation by DOI.
