# Figshare item — P1: geno_agent methods & shared foundation

**Title.** An Annotation-Overlap-Flagged 1,047-Case Rare-Disease
Gene-Prioritisation Benchmark and PMC Open Access Index — methods code and build
artefacts

> Retitled 2026-08-15 to mirror the P1 manuscript title, so a reader arriving from
> the paper recognises the deposit, and de-branded for the same reason records 1
> and 2 were: the manuscript names no downstream system. The trailing qualifier is
> what distinguishes this Software item from the paper and from the two cohort
> Datasets — this record is the build recipe and verification artefacts, not the
> benchmark itself. Safe to rename because the item is still unpublished, so no
> citation resolves against the old wording; the DOI is unchanged. **Keep it in
> step with the paper**: if the title changes at review, change it here, on
> Figshare, and in `CITATION.cff`.

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**License.** Code: AGPL-3.0-or-later. Data artifacts retain upstream licenses
(cohort: CC BY 4.0, derived from the GA4GH Phenopacket Store).

**Snapshot.** Git tag `paper-methods-v1.3` (resolve the exact commit with
`git rev-parse paper-methods-v1.3`). This is the item's **first public release**;
the tag number is internal build history, not a sequence of published versions, so
Figshare's own version counter starts at 1.
**Repository.** https://github.com/Jangulo7/geno_agent

## What this item is

The reproducible foundation shared by the geno_agent paper programme: the build
recipe for the PMC-OA Qdrant retrieval index (52,777,395 chunks), the pinned
ontology set (HPO/MONDO/GO/HGNC), and the construction of the n=1,047 stratified
evaluation cohort from Phenopacket Store v0.1.26. The cohort is released in **two
case-paired difficulty variants** — a *standard* variant (49 uniformly-random
HGNC protein-coding distractors per case) and a *hard* variant (49
phenotype-similar distractors selected by HPO Resnik best-match-average
similarity) — each as its own Figshare Dataset (DOIs below). This item is the
shared **build recipe/code** for both cohort variants and the index; it is
designed to be **cited by reference**, not duplicated, by the downstream papers.

The two distractor variants are produced by
`scripts/cases/18_build_candidate_lists.py` (standard) and
`scripts/cases/18b_build_hard_candidates.py` (hard); both share the same cases and
per-case BLAKE2b seed, so they are deterministic and case-paired.

## The three-paper relationship

- **P1 (this item)** — methods + shared foundation. Owns the corpus/index recipe,
  ontology pins, and the cohort.
- **P2** — *geno_agent* four-agent LangGraph RAG gene prioritisation (separate Figshare
  item; references this item's DOI for the foundation).
- **P3** — variant-interpretation safety benchmark, in the separate
  `geno_agent_variant` repository. **Reuses this shared foundation by DOI and forks
  the agent code under AGPL-3.0.**

> **Shared-foundation DOI: 10.6084/m9.figshare.32814491**
> Record this DOI; it must be pasted into the P3 (`geno_agent_variant`) repository
> so P3 references — rather than copies — this foundation.

## Contents

- `…_code_<commit>.zip` — corpus/cohort pipeline code, tests, env/build config,
  `MANIFEST.tsv`, methods docs, and `REPRODUCE.md`.
- `artifacts_manifest.tsv` — every resource with its action (upload / reference /
  recipe-only) and license.
- `*.sha256` — checksums for every uploaded file.

> **The n=1,047 benchmark cohort is shipped as *separate* Figshare Dataset items**
> (type: Dataset, CC BY 4.0) so each has its own citable DOI — they are **not**
> duplicated here. This methods item is the shared build recipe/code; it references
> the cohorts by DOI:
> - **Standard cohort (random distractors): `10.6084/m9.figshare.32814449`**
> - **Hard cohort (phenotype-similar distractors): `10.6084/m9.figshare.32816468`**

**Not included (by design):** the 323 GB Qdrant index and PMC chunk text
(recipe-only, mixed CC; rebuild from the recipe and verify against the chunk-set
fingerprint `70759656…aa39ea` in `release/index_fingerprint/chunk_id_fingerprint.txt`);
ontologies / phenopackets / models (reference
upstream by pinned version); any personal correspondence.

## How to cite

> Angulo, J. (2026). *An Annotation-Overlap-Flagged 1,047-Case Rare-Disease
> Gene-Prioritisation Benchmark and PMC Open Access Index — methods code and build
> artefacts* [Data set & software]. Figshare.
> https://doi.org/10.6084/m9.figshare.32814491
