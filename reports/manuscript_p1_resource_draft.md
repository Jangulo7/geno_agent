# Manuscript draft (P1) — A reproducible PMC Open Access retrieval index and a deconfounded, stratified rare-disease gene-prioritisation benchmark (n = 1,047)

**Paper type:** Data / Resource Descriptor.
**Primary target venue:** *GigaScience* (Q1; reproducible-resource and benchmark
scope). **Alternative:** *Scientific Data* (Q1; foreground the cohort Dataset).
**Q2 fallbacks:** *Database* (Oxford), *BMC Bioinformatics*. A *Bioinformatics*
Application Note is possible only if reframed around the build pipeline + evaluation
harness as software (see *Notes for venue adaptation* at the end).

This is the **P1 (methods / shared foundation)** paper of a two-paper programme from
this repository. **P2** is the GenoAgent system + evaluation paper
(`reports/manuscript_q1_draft.md`, target *Genome Medicine*), which **cites this
resource by DOI** for the cohort, the index recipe, and the deconfounding design
rather than re-describing them. The evaluation *results* (system accuracy,
fair-comparison outcomes, explainability) belong to P2; this paper describes the
**reusable resource and how it was built and validated**.

Style: paper voice (passive, third person), Vancouver/numbered citations. All
numbers reference the locked v3 artifacts (`data/test_cases_1050/`,
`data/MANIFEST.tsv`, `reports/paper_extension_results.md`).

---

## Abstract (✅ DRAFTED — ~210 words)

Benchmarking literature-based computational tools for rare-disease gene
prioritisation is confounded by a circularity that is rarely measured: the
published cases used as benchmarks are frequently the same publications from which
knowledge-base tools were curated, so a curated tool may appear to "predict" a case
it was, in effect, trained on. We release a reproducible foundation that addresses
this directly. The resource has two components. First, a **hybrid dense + sparse
retrieval index** over a genetics-relevant subset of the PubMed Central Open Access
corpus (~3.4 million full-text articles; 52,777,395 chunks; PubMedBERT dense
embeddings + BM25 sparse, served from Qdrant), built by a deterministic,
version-pinned pipeline that regenerates bit-for-bit. Second, a **stratified
benchmark of 1,047 rare-disease cases** derived from the GA4GH Phenopacket Store
v0.1.26, each pairing a Human Phenotype Ontology profile with a 50-gene candidate
list (one causal gene plus 49 phenotype-matched distractors) and the true causal
gene, balanced across four disease categories. The benchmark ships two
**deconfounding metadata layers**: a per-case *annotation-overlap* flag that
identifies cases whose source publication is cited by the HPO disease–annotation
file (enabling a leakage-free fair-comparison subset, n = 282), and *publication-recency*
strata. We document the construction, provide technical validation including a
bit-for-bit reproducibility check, and give usage notes for fair benchmarking. All
artifacts are openly archived with persistent DOIs.

---

## Background & Summary (✅ DRAFTED — ~620 words)

Rare diseases collectively affect an estimated 300 million people, and roughly half
of exome/genome cases remain undiagnosed after standard analysis [1, 2].
Phenotype-driven gene prioritisation — ranking candidate genes from a patient's
Human Phenotype Ontology (HPO) profile — is a central computational step, and
curated tools such as Exomiser and LIRICAL are widely used for it [3, 4]. A newer
class of systems instead reasons over the primary literature using retrieval-augmented
large language models. Comparing the two classes fairly requires a benchmark and a
retrieval substrate that are (i) reproducible, (ii) representative across disease
areas, and (iii) **free of curation leakage** — the last of which is the property
most benchmarks omit.

The leakage problem is specific and quantifiable. Public rare-disease benchmarks are
typically assembled from published, molecularly solved cases — for example, the GA4GH
Phenopacket Store [5], which aggregates literature-curated phenopackets. Curated
prioritisation tools draw their disease–phenotype associations from the same
literature: LIRICAL's likelihood ratios, for instance, are computed from the HPO
`phenotype.hpoa` annotation file, which records the very publications it was curated
from. When a benchmark case and a tool's knowledge base derive from the same paper,
the tool has *de facto* exposure to the answer, and reported accuracy is inflated in
a way that penalises literature-based competitors. To our knowledge, no widely used
rare-disease prioritisation benchmark ships a per-case flag that lets users remove
these cases.

This paper releases a foundation built to make such comparisons fair and
reproducible. Its contributions, as a resource, are:

1. **A reproducible hybrid retrieval index** over the genetics-relevant PMC Open
   Access corpus (~3.4 M articles, 52,777,395 chunks), with deterministic chunking,
   content-addressed chunk identifiers, and pinned embedding models, so the index
   regenerates bit-for-bit from public inputs rather than being distributed as an
   opaque 323 GB blob.
2. **A stratified, version-pinned benchmark of 1,047 cases** with 50-gene
   candidate lists built from *phenotype-matched* distractors (a more conservative
   setting than random distractors), balanced across developmental, immunological,
   metabolic, and neurological disease categories.
3. **A general annotation-overlap deconfounding method** and the per-case metadata
   that operationalises it, yielding a leakage-free **fair-comparison subset**
   (n = 282) on which curated tools cannot benefit from training-data exposure.
4. **Publication-recency strata**, supporting the separate question of whether
   literature-based tools generalise better to gene–phenotype associations that
   post-date curation cycles.

The annotation-overlap method is the element that distinguishes this resource from a
simple curated dataset: it is a reusable procedure for detecting curation leakage in
*any* benchmark assembled from published cases, not only the one released here. The
companion system paper (P2) uses this foundation to evaluate an agentic-workflow RAG
prioritiser; here we restrict attention to the resource itself and its validation.

---

## Methods (✅ DRAFTED)

### PMC Open Access corpus acquisition and filtering

A genetics-relevant subset of the PubMed Central Open Access (PMC OA) full-text XML
corpus (retrieved 2026-05; [6]) was selected by Medical Subject Headings (MeSH)
descriptor matching — *Genetic Diseases*, *Rare Diseases*, *Mutation*,
*Pathogenicity*, *Inheritance Patterns* — together with full-text inclusion
criteria, yielding approximately 3.4 million articles. Retracted articles were
excluded during parsing. Article licences within PMC OA are mixed (CC BY, CC BY-NC,
and other tiers); for this reason the verbatim chunk text is **not** redistributed
(see *Data Records* and *Usage Notes*), and the resource provides the build recipe
and fingerprints instead.

### Hybrid retrieval index construction

Each article was chunked at 512 tokens with 50-token overlap using the
PubMedBERT-base tokeniser [7]. Chunk identifiers were assigned deterministically as
UUID5 hashes of the content key, so re-indexing the same corpus reproduces identical
identifiers. Dense embeddings were computed with PubMedBERT [7] and stored in Qdrant
v1.14.1 [8] alongside sparse BM25 embeddings from FastEmbed, enabling hybrid
retrieval combined at query time by Reciprocal Rank Fusion (RRF, k = 60) [9]. The
production collection (`geno_agent_pmc_oa_v1`) contains **52,777,395 chunks**, a
value used as the index fingerprint (verified via the Qdrant `points_count` API and
recorded in `data/MANIFEST.tsv`). A MedCPT cross-encoder [10] is provided as an
optional query-time reranker; it is part of the retrieval substrate but is not
required to reproduce the index.

### Benchmark cohort construction

Cases were drawn from GA4GH Phenopacket Store v0.1.26 (released 13 January 2026;
[5]), which aggregates literature-curated rare-disease phenopackets with gene-level
solved diagnoses. Inclusion required: (i) a single causal gene with a SOLVED
interpretation status; (ii) ≥ 3 HPO terms (HPO v2026-02-16; [11]); (iii) a Mondo
Disease Ontology mapping (MONDO v2026-03-03; [12]) to one of four broad categories —
developmental, immunological, metabolic, or neurological; and (iv) ≥ 5 PMC OA
full-text articles indexed for the causal gene in the retrieval index above, so that
literature retrieval is non-trivial. Criteria (i)–(iii) produced an eligible pool of
4,670 cases (464 developmental, 390 immunological, 672 metabolic, 3,144
neurological); criterion (iv) was verified on the drawn sample and did not reduce it.

To adequately power analysis of the smallest categorical subgroup (immunological),
a **disproportionate stratified sample** of 1,050 cases was drawn with seed 42: 250
each from the developmental, metabolic, and neurological pools and 300 from the
immunological pool (390 eligible). Three neurological cases whose causal gene is not
protein-coding (two *RNU4-2*, one *RNU2-2*, small nuclear RNA genes) were removed at
the candidate-list stage, giving a final **n = 1,047** (250 developmental, 300
immunological, 250 metabolic, 247 neurological). Disproportionate stratified sampling
is standard practice when one subgroup is rate-limiting for power and the overall
cohort is large enough that stratum-weighted estimates remain unbiased [13].

For each case, a 50-gene candidate list was assembled as the single causal gene plus
49 distractor genes sampled deterministically (per-case derived seed: SHA-256 of the
`case_id`) from a *phenotype-matched* pool: candidates were ranked by Jaccard
similarity between the case's HPO term set and each gene's HPO annotations in
`phenotype.hpoa` v2026-02-16 (gene set: HGNC quarterly snapshot 2026-04-07; [14]),
taking the top 49. Phenotype-matched distractors are clinically plausible
alternatives rather than random genes, a deliberately more conservative evaluation
setting.

### Deconfounding metadata

**Annotation-overlap flag.** For each case a binary `annotation_overlap` flag was
computed: 1 if the case's source PMID (parsed from the `case_id` and verified against
the phenopacket `metaData.externalReferences[0].id` field) appears in
`phenotype.hpoa` v2026-02-16 as a reference for any annotation of any of the case's
causal OMIM disease IDs; 0 otherwise. The procedure parses 282,723 `phenotype.hpoa`
rows into 9,852 unique `(disease, PMID)` keys after deduplication and PMID-only
filtering, and joins each case against this index. All 1,047 cases resolved to both a
PMID and an OMIM disease ID (no edge cases). The flag partitions the cohort into an
overlap-present subset and an **overlap-absent fair-comparison subset (n = 282,
26.9 %)** on which a tool curated from `phenotype.hpoa` cannot have source-publication
exposure to the case.

**Publication-recency strata.** Source-publication dates for the 415 unique cohort
PMIDs were retrieved from NCBI E-utilities (`efetch`, `PubMedPubDate`
`PubStatus="pubmed"`); 100 % resolved (oldest 1988, most recent 2024, median 2018).
Cases were split at 2020-01-01 into pre-2020 (n = 601) and post-2020 (n = 446)
strata, and the crossed post-2020 × overlap-absent subset (n = 88) is provided as the
closest available approximation to a "novel-association" cohort.

---

## Data Records (✅ DRAFTED)

The resource is openly archived on Figshare (project "GenoAgent") with persistent
DOIs:

| Record | Figshare type | License | DOI |
|---|---|---|---|
| **Benchmark cohort (n = 1,047)** | Dataset | CC BY 4.0 | `10.6084/m9.figshare.32814449` |
| **Methods / shared foundation** (build recipe, index fingerprint, manifests) | Software | AGPL-3.0 | `10.6084/m9.figshare.32814491` |
| **GenoAgent system** (companion P2 code/results) | Software | AGPL-3.0 | `10.6084/m9.figshare.32814497` |

**Cohort Dataset contents.** The canonical file `test_cases.jsonl` holds one JSON
object per case with the fields in Table 1; the deconfounding sidecars
(`annotation_overlap.json`, `pmid_dates.json`), the staged provenance files
(`01_all_phenopackets.jsonl` … `06_with_candidates.jsonl`), a build manifest with the
SHA-256 and byte size of `test_cases.jsonl`, and per-file checksums are included.

**Table 1 — `test_cases.jsonl` schema.**

| Field | Type | Description |
|---|---|---|
| `case_id` | string | Stable ID, `"{CAUSAL_GENE}:{phenopacket_id}"` |
| `category` | string | `developmental` \| `immunological` \| `metabolic` \| `neurological` |
| `hpo_terms` | list[string] | Patient HPO term IDs (≥ 3) |
| `diseases` | list[object] | `{ "id": "OMIM:NNNNNN", "label": str }` |
| `causal_gene` | string | HGNC symbol of the true causal gene (prediction target) |
| `candidate_genes` | list[string] | 50 HGNC symbols: causal + 49 phenotype-matched distractors |
| `causal_gene_index_in_candidates` | int | 0-based ground-truth position |
| `pmc_article_count` | int | PMC OA articles mentioning the causal gene (≥ 5) |
| `source_phenopacket` | string | Relative path within Phenopacket Store v0.1.26 |

**Retrieval index.** The 323 GB Qdrant index and the verbatim PMC OA chunk text are
**recipe-only** (mixed-licence source text): the methods record provides the
deterministic build pipeline and the fingerprint (`52,777,395` chunks; SHA-256 of
upstream inputs in `data/MANIFEST.tsv`) so that the index regenerates rather than
being hosted. Pinned upstream versions are listed in Table 2.

**Table 2 — pinned inputs (provenance).**

| Input | Pinned version | License |
|---|---|---|
| GA4GH Phenopacket Store | v0.1.26 (2026-01-13) | CC BY 4.0 |
| Human Phenotype Ontology | v2026-02-16 | open (HPO) |
| Mondo Disease Ontology | v2026-03-03 | CC BY 4.0 |
| Gene Ontology | 2026-03-25 | CC BY 4.0 |
| HGNC complete set | 2026-04-07 | open (EBI/HGNC) |
| PubMedBERT embedder | `NeuML/pubmedbert-base-embeddings` | open |
| Qdrant | v1.14.1 | Apache 2.0 |

---

## Technical Validation (✅ DRAFTED)

**Eligibility and coverage.** Every retained case satisfies the four inclusion
criteria above; the ≥ 5-article PMC OA coverage gate guarantees that each causal gene
is non-trivially represented in the retrieval index, so the benchmark exercises
retrieval rather than rewarding genes absent from the corpus. The eligible-pool
counts (4,670; 464/390/672/3,144 by category) and the final balanced cohort
(250/300/250/247) are regenerable from the pinned inputs and seed.

**Reproducibility.** Determinism is enforced by (i) `PYTHONHASHSEED=42`, (ii) UUID5
content-addressed chunk identifiers, (iii) seed-42 sampling at every stochastic step,
including the per-case `blake2b`/SHA-256-derived distractor seed so individual cases
regenerate independently, and (iv) fully pinned dependency versions. A bit-for-bit
cohort check confirms `test_cases.jsonl` matches the SHA-256 recorded in the build
manifest. For the retrieval/answer stack, two independent end-to-end runs seven
months apart were rank-identical on 1,026/1,047 (97.99 %) and 1,024/1,047 (97.80 %)
of cases for the two retrieval-heavy configurations, with zero and one top-1 change
respectively — i.e. the substrate is effectively deterministic at the level a
benchmark cares about.

**Cohort characterisation.** The annotation-overlap analysis shows that **73.1 %**
of cases (765/1,047) are overlap-present — direct evidence that curation leakage is
the common case, not a corner case, and motivating the fair-comparison subset. The
recency split (601 pre-2020 / 446 post-2020; median publication year 2018) and the
four-way category balance are reported as cohort descriptors and are reproducible
from `pmid_dates.json` and the `category` field. Distractor lists are
phenotype-matched (top-49 by HPO Jaccard), so candidate sets are clinically plausible
by construction rather than trivially separable.

**Independence of the deconfounding layer.** The `annotation_overlap` flag depends
only on public inputs (the case PMID and `phenotype.hpoa`) and not on any tool's
output, so it is a property of the benchmark rather than of a particular system, and
can be recomputed by any user against a different `phenotype.hpoa` release.

---

## Usage Notes (✅ DRAFTED)

**Recommended evaluation protocol.** For unbiased comparison of a literature-based
tool against curated tools (e.g. those drawing on `phenotype.hpoa`), report metrics
on the **overlap-absent fair-comparison subset (n = 282)** as the primary endpoint,
with the full cohort as a supportive secondary analysis. Top-k accuracy, Mean
Reciprocal Rank, and NDCG@10 over the 50-gene candidate list are the natural metrics;
the candidate list and ground-truth index are provided so that any ranking system can
be scored identically.

**Recency analysis.** Use the publication-year split (or the crossed
post-2020 × overlap-absent subset, n = 88) to probe generalisation to associations
that post-date curation cycles.

**Rebuilding the index.** The methods record provides the deterministic pipeline
(MeSH filtering → 512/50 chunking → PubMedBERT dense + BM25 sparse → Qdrant) and the
`52,777,395`-chunk fingerprint; rebuilding from a matching PMC OA snapshot reproduces
the substrate. Because PMC OA grows over time, users targeting bit-identical
retrieval should pin the same snapshot date.

**Licensing.** The cohort is CC BY 4.0 (it derives from the CC BY 4.0 Phenopacket
Store and open ontologies). The build/evaluation code is AGPL-3.0. Verbatim PMC OA
chunk text is **not** redistributed because article licences are mixed; users
regenerate it from PMC under the source licences.

**Scope.** This resource describes phenotype-driven prioritisation inputs (HPO terms
+ candidate lists). It does not include patient variant calls; variant-aware
benchmarking is out of scope.

---

## Code availability (✅ DRAFTED)

The construction and validation code (corpus parsing, index build, cohort pipeline
stages, annotation-overlap and recency metadata generation, and checksum/manifest
tooling) is available at https://github.com/Jangulo7/geno_agent under AGPL-3.0 and
archived at DOI `10.6084/m9.figshare.32814491`. Cohort regeneration corresponds to
pipeline stages 13–20 (`scripts/cases/`).

## Data availability (✅ DRAFTED)

The benchmark cohort is archived as a Figshare Dataset under CC BY 4.0 (DOI
`10.6084/m9.figshare.32814449`). Upstream resources are referenced by pinned version
(Table 2) rather than redistributed: GA4GH Phenopacket Store v0.1.26, HPO
v2026-02-16, MONDO v2026-03-03, GO 2026-03-25, HGNC 2026-04-07, and PMC OA (retrieved
2026-05).

---

## References (Vancouver; full entries verified against the P2 reference list)

1. Nguengang Wakap S, Lambert DM, Olry A, Rodwell C, Gueydan C, Lanneau V, et al.
   Estimating cumulative point prevalence of rare diseases: Analysis of the Orphanet
   database. European Journal of Human Genetics. 2020;28(2):165-173.
   doi:10.1038/s41431-019-0508-0.
2. Clark MM, Stark Z, Farnaes L, Tan TY, White SM, Dimmock D, et al. Meta-analysis of
   the diagnostic and clinical utility of genome and exome sequencing and chromosomal
   microarray in children with suspected genetic diseases. npj Genomic Medicine.
   2018;3(1):16. doi:10.1038/s41525-018-0053-8.
3. Smedley D, Jacobsen JOB, Jäger M, Köhler S, Holtgrewe M, Schubach M, et al.
   Next-generation diagnostics and disease-gene discovery with the Exomiser. Nature
   Protocols. 2015;10(12):2004-2015. doi:10.1038/nprot.2015.124.
4. Robinson PN, Ravanmehr V, Jacobsen JOB, Danis D, Zhang XA, Carmody LC, et al.
   Interpretable clinical genomics with a likelihood ratio paradigm. American Journal
   of Human Genetics. 2020;107(3):403-417. doi:10.1016/j.ajhg.2020.06.021.
5. Danis D, Bamshad MJ, Bridges Y, Caballero-Oteyza A, Cacheiro P, Carmody LC, et al.
   A corpus of GA4GH Phenopackets: Case-level phenotyping for genomic diagnostics and
   discovery. Human Genetics and Genomics Advances. 2025;6(1):100371.
   doi:10.1016/j.xhgg.2024.100371.
6. National Library of Medicine. PubMed Central Open Access subset. [Data resource].
   2024. https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/.
7. Gu Y, Tinn R, Cheng H, Lucas M, Usuyama N, Liu X, et al. Domain-specific language
   model pretraining for biomedical natural language processing. ACM Transactions on
   Computing for Healthcare. 2021;3(1):1-23. doi:10.1145/3458754.
8. Qdrant. Qdrant vector search engine. [Computer software]. Version 1.14.1.
   https://github.com/qdrant/qdrant.
9. Cormack GV, Clarke CLA, Büttcher S. Reciprocal Rank Fusion outperforms Condorcet
   and individual rank learning methods. In: Proceedings of the 32nd International
   ACM SIGIR Conference on Research and Development in Information Retrieval
   (SIGIR '09). 2009. doi:10.1145/1571941.1572114.
10. Jin Q, Kim W, Chen Q, Comeau DC, Yeganova L, Wilbur WJ, et al. MedCPT: Contrastive
    pre-trained transformers with large-scale PubMed search logs for zero-shot
    biomedical information retrieval. Bioinformatics. 2023;39(11):btad651.
    doi:10.1093/bioinformatics/btad651.
11. Köhler S, Gargano M, Matentzoglu N, Carmody LC, Lewis-Smith D, Vasilevsky NA,
    et al. The Human Phenotype Ontology in 2021. Nucleic Acids Research.
    2021;49(D1):D1207-D1217. doi:10.1093/nar/gkaa1043.
12. Vasilevsky NA, Matentzoglu NA, Toro S, Flack JE, Hegde H, Unni DR, et al. Mondo:
    Unifying diseases for the world, by the world. medRxiv preprint. 2022.
    doi:10.1101/2022.04.13.22273750.
13. Lohr SL. Sampling: Design and analysis. 3rd ed. Boca Raton: Chapman and Hall/CRC;
    2022. doi:10.1201/9780429298899.
14. Seal RL, Braschi B, Gray KA, Jones TEM, Tweedie S, Haim-Vilmovsky L, et al.
    Genenames.org: the HGNC resources in 2023. Nucleic Acids Research.
    2023;51(D1):D1003-D1009. doi:10.1093/nar/gkac888.

---

## Notes for venue adaptation (not for submission)

- **GigaScience / Scientific Data (Data Descriptor):** use the structure above
  (Background & Summary → Methods → Data Records → Technical Validation → Usage
  Notes). GigaScience additionally welcomes the pipeline as a citable workflow;
  Scientific Data weights the *Data Records* and *Technical Validation* sections most
  heavily and prefers the cohort foregrounded over the index.
- **Bioinformatics Application Note:** compress to ~2 pages, lead with the build
  pipeline + evaluation harness *as software*, move cohort/index detail to
  supplementary, and frame the annotation-overlap method as the tool's novelty.
- **Overlap control with P2:** keep all *system results* out of this paper. P2 cites
  this resource by DOI for the cohort, index, and deconfounding design.

*P1 resource-paper draft v1 — 2026-06-28. Foundation content adapted from
`reports/manuscript_methods_draft.md` (the former P2 Methods section); evaluation/
results content intentionally excluded and retained in P2.*
