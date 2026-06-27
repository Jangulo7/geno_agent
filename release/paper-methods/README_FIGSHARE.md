# Figshare item — P1: geno_agent methods & shared foundation

**Title.** geno_agent — Methods and Shared Foundation: A Reproducible PMC-OA
Retrieval Index and n=1,047 Rare-Disease Gene-Prioritization Cohort

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**License.** Code: AGPL-3.0-or-later. Data artifacts retain upstream licenses
(cohort: CC BY 4.0, derived from the GA4GH Phenopacket Store).

**Git tag.** `paper-methods-v1.0`  ·  **Commit.** `<filled by build script>`
**Repository.** https://github.com/Jangulo7/geno_agent

## What this item is

The reproducible foundation shared by the geno_agent paper programme: the build
recipe for the PMC-OA Qdrant retrieval index (52,777,395 chunks), the pinned
ontology set (HPO/MONDO/GO/HGNC), and the construction of the n=1,047 stratified
evaluation cohort from Phenopacket Store v0.1.26. It is designed to be **cited by
reference**, not duplicated, by the downstream papers.

## The three-paper relationship

- **P1 (this item)** — methods + shared foundation. Owns the corpus/index recipe,
  ontology pins, and the cohort.
- **P2** — *geno_agent* agentic-workflow RAG gene prioritization (separate Figshare
  item; references this item's DOI for the foundation).
- **P3** — variant-interpretation safety benchmark, in the separate
  `geno_agent_variant` repository. **Reuses this shared foundation by DOI and forks
  the agent code under AGPL-3.0.**

> **Shared-foundation DOI: <to be filled after P1 upload>**
> Record this DOI; it must be pasted into the P3 (`geno_agent_variant`) repository
> so P3 references — rather than copies — this foundation.

## Contents

- `…_code_<commit>.zip` — corpus/cohort pipeline code, tests, env/build config,
  `MANIFEST.tsv`, methods docs, and `REPRODUCE.md`.
- `artifacts_manifest.tsv` — every resource with its action (upload / reference /
  recipe-only) and license.
- `*.sha256` — checksums for every uploaded file.

> **The n=1,047 benchmark cohort is a *separate* Figshare item** (type: Dataset,
> CC BY 4.0) so it has its own citable DOI — it is **not** duplicated here. This
> methods item is the build recipe/code; it references the cohort by DOI.
> **Benchmark cohort DOI: `<to be filled after cohort upload>`**

**Not included (by design):** the 323 GB Qdrant index and PMC chunk text
(recipe-only, mixed CC); ontologies / phenopackets / models (reference upstream by
pinned version); any personal correspondence.

## How to cite

> Angulo, J. (2026). *geno_agent — Methods and Shared Foundation* [Data set & software].
> Figshare. https://doi.org/<filled after upload>
