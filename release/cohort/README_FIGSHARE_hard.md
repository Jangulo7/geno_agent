# Phenotype-Similar Distractor Variant of the Stratified Rare-Disease Cohort (n=1,047)

**Title.** A Phenotype-Similar Distractor Variant of
the Stratified Rare-Disease Cohort for Literature-Based Causal Gene
Prioritisation (n=1,047)

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**Figshare item type.** Dataset · **License.** CC BY 4.0 · **Version.** v1.0

**DOI (this dataset).** `10.6084/m9.figshare.32816468`
**Base/standard cohort (sibling).** `10.6084/m9.figshare.32814449`

## Summary

A **hard** variant of the stratified rare-disease benchmark cohort. It contains the **same
1,047 rare-disease cases** as the standard cohort (DOI `10.6084/m9.figshare.32814449`) — identical
`case_id`, `causal_gene`, `hpo_terms`, `diseases`, and the same case-level metadata
layers — but the 49 distractor genes per case are **phenotypically similar to the
case** rather than random. This turns distractor difficulty into an explicit
experimental axis, orthogonal to the annotation-overlap (leakage) axis shipped
with the standard cohort, enabling a 2×2 (difficulty × leakage) evaluation.

## How the hard distractors are chosen (deterministic, version-pinned)

- **Similarity.** HPO **Resnik** term similarity (information content of the
  most-informative common ancestor) aggregated by **best-match-average (BMA)**
  between the case HPO profile and each gene's known HPO annotations — the
  Phenomizer/Exomiser-standard symmetric phenotypic-similarity measure.
- **Information content.** Computed from the gene→HPO annotation corpus
  (`genes_to_phenotype.txt`), frequencies propagated over the `hp.obo` is-a DAG.
- **Pool & exclusions.** Candidates are HGNC protein-coding genes (the same pool
  as the standard cohort) that carry HPO annotations, **excluding** the causal
  gene and **excluding any gene annotated to the case's own causal disease(s)**,
  so no distractor is a *curated* alternative cause for that diagnosis.
  Distractors are negatives relative to the single recorded causal gene; for a
  case with digenic or oligogenic contributions that labelling may be
  incomplete. The exclusion is a defined, recomputable filter, not a guarantee
  of clean negatives.
- **Selection.** The **top-49** by BMA; ties broken by gene symbol (deterministic).
- **Shuffle.** The final 50-gene list is shuffled with the **same per-case seed**
  as the standard cohort (`BLAKE2b(global_seed=42 | case_id)`), so the variant is
  as reproducible and case-paired as the original.

## Analysis caveats (inherited from the base cohort)

Because this variant shares the base cohort's cases, both caveats below apply
unchanged; see the standard-variant deposit
([10.6084/m9.figshare.32814449](https://doi.org/10.6084/m9.figshare.32814449))
for the full sampling-design table.

- **Clustered cases.** The 1,047 cases derive from **415 unique source
  publications** (median 1, mean 2.5, max 42 per publication), so per-case metrics
  treated as independent observations understate variance. Cluster confidence
  intervals on the source PMID encoded in `case_id`.
- **Sampling weights.** The four strata were drawn at inclusion probabilities
  ranging from 0.769 (immunological) to 0.0786 (neurological). Unweighted pooling
  estimates a design-defined quantity, not a population one.
- **Tool-class asymmetry.** Distractors are selected by HPO Resnik
  best-match-average similarity computed over `genes_to_phenotype` — the same
  curated resource from which knowledge-base tools derive their gene–phenotype
  associations. Results on this variant should be read as performance against an
  HPO-similarity-defined adversary, not as a tool-neutral difficulty increase.
  Cross-tool comparisons are more safely made on the standard variant.

## Provenance

| Input | Pinned version | License |
|---|---|---|
| GA4GH Phenopacket Store (cases) | v0.1.26 (2026-01-13) | CC BY 4.0 |
| HPO `hp.obo` + `genes_to_phenotype.txt` (similarity) | v2026-02-16 | open (HPO) |
| HGNC complete set (distractor gene pool) | 2026-04-07 | open (EBI/HGNC) |

## Files

| File | Rows | What |
|---|---:|---|
| `test_cases_hard.jsonl` | 1,047 | Canonical hard cohort — same schema as the standard cohort plus `candidate_difficulty: "hard"`. SHA-256 in `test_cases_hard_manifest.json`. |
| `hard_candidates_stats.json` | — | Per-case selection diagnostics (causal vs distractor BMA, #scored candidates) + `meta`. |
| `test_cases_hard_manifest.json` | — | Build manifest: pinned versions, seed, SHA-256 + bytes, relation to base DOI. |
| `CHECKSUMS.sha256` | — | SHA-256 of every file in this bundle (verify with `sha256sum -c`). |
| `LICENSE` | — | CC BY 4.0 dataset license (machine-discoverable; SPDX `CC-BY-4.0`). |

## Data dictionary

Identical to the standard cohort, with one added field:

| Field | Type | Description |
|---|---|---|
| `candidate_genes` | list[string] | 50 HGNC symbols: causal + **49 phenotype-similar** distractors. |
| `causal_gene_index_in_candidates` | int | 0-based index of the causal gene. |
| `candidate_difficulty` | string | `"hard"` (marks this as the hard variant). |

All other fields (`case_id`, `category`, `hpo_terms`, `diseases`, `causal_gene`,
`pmc_article_count`, `source_phenopacket`) are byte-for-byte the values of the
matching case in the standard cohort.

## Recommended use

Pair with the standard cohort for a **difficulty × leakage** analysis: report on
the standard (random) and hard (phenotype-similar) candidate lists, each split by
the annotation-overlap fair subset. The hard variant stresses
differential-diagnosis behaviour; the leakage split keeps the comparison fair to
literature-based vs curated tools.

## How to regenerate

```bash
# Methods/foundation release (stages 13-20 build the base cohort), then:
python scripts/cases/18b_build_hard_candidates.py   # Resnik-BMA top-49, seed 42
```
Verify `test_cases_hard.jsonl` against `test_cases_hard_manifest.json`, which
carries two digests: `sha256_test_cases_hard` (`01f086ad343fd9a8…`) over the full
canonical file, and `sha256_test_cases_hard_core` (`c20eb7bb389a9df0…`) over the
same records with the index-derived `pmc_article_count` removed. **Check the core
digest** if you rebuilt from the pinned files alone — a rebuild on different
hardware may return slightly different values for that one descriptor, which
enters no metric and no inclusion decision. Methods/foundation code DOI:
`10.6084/m9.figshare.32814491`.

## License

**CC BY 4.0.** Derived from the GA4GH Phenopacket Store (CC BY 4.0); annotated
with HPO/HGNC (open). Reuse freely with attribution.

## Recommended citation

```bibtex
@dataset{angulo2026rd_cohort_hard,
  author    = {Angulo, Johanna},
  title     = {A Phenotype-Similar Distractor Variant
               of the Stratified Rare-Disease Cohort for Literature-Based Causal
               Gene Prioritisation (n=1,047)},
  year      = {2026},
  publisher = {Figshare},
  version   = {v1.0},
  doi       = {10.6084/m9.figshare.32816468},
  note      = {Case-paired hard variant of DOI 10.6084/m9.figshare.32814449;
               derived from GA4GH Phenopacket Store v0.1.26; CC BY 4.0.}
}
```

## Relationship to the associated papers

- **Standard cohort** (random distractors): DOI `10.6084/m9.figshare.32814449`.
- **This hard variant**: `10.6084/m9.figshare.32816468`.
- **Methods / foundation** (build recipe incl. `18b_build_hard_candidates.py`):
  DOI `10.6084/m9.figshare.32814491`.
- **GenoAgent system** (an agentic-RAG system evaluated on both variants — a separate paper): DOI `10.6084/m9.figshare.32814497`.
