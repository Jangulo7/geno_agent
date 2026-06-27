# geno_agent — Test Case Selection Methodology

**Author:** Johanna Angulo
**Project:** `geno_agent` — agentic-workflow RAG for rare-disease gene prioritisation
**Master plan reference:** `MASTER_PROJECT_v2.1.md` §6 (Phase 1B), §11.5 (Evaluation harness)
**Canonical artefact:** `data/test_cases/test_cases.jsonl` (sha256 `4872afb6…`)
**Companion:** `reports/methodology_test_case_selection.html` (visual variant)

This document describes **how the 75 test cases used in every evaluation cell were
selected, why this selection is methodologically sound, and how it makes the
cross-cell comparisons (A–K + P + L) valid**.

---

## 1. Why the test case set matters

The thesis claim — that a literature-driven multi-agent RAG can prioritise causal
genes as well as a curated-database baseline (Exomiser HPO-only) — is only as
strong as the evaluation harness. Three properties are required:

1. **Reproducibility.** Anyone re-running the pipeline must obtain the same 75
   cases, in the same order, with the same 50 candidate genes per case.
2. **Representativeness.** The sample must cover the four target MONDO
   categories defined by the master plan with roughly equal weight.
3. **Comparability.** Every experimental cell must process *exactly the same
   75 cases* so that pairwise comparisons (D vs K, D vs D-with-rerank, etc.)
   are well-defined and statistically meaningful via paired-bootstrap CIs.

The pipeline below was designed around these three properties.

---

## 2. Source of cases

The cases originate in the **GA4GH Phenopacket Store v0.1.19**, a curated
public collection of clinically-described rare-disease cases distributed by
the Monarch Initiative. Each Phenopacket contains:

- `subject.id` — anonymised patient identifier;
- `phenotypicFeatures[]` — HPO term IDs (observed and/or excluded);
- `diseases[]` — OMIM / Orphanet disease IDs;
- `interpretations[]` — causal genomic interpretations: gene symbol, HGNC ID,
  declared causal variant, ascertainment flags.

The Phenopacket Store snapshot is treated as immutable for this project
(versioned by `0.1.19`). All downstream stages reference this version pin.

**Source download:** `scripts/cases/04_download_phenopacket_store.sh` (committed
in the repo). Provenance recorded in `data/test_cases/test_cases_manifest.json`.

---

## 3. The selection pipeline (six stages)

The selection is implemented as a numbered sequence of Python scripts under
`scripts/cases/`. Each stage writes its output to a versioned JSONL file in
`data/test_cases/` so the funnel is transparent and re-runnable.

### Stage 1 — Ingest every Phenopacket into a normalised JSONL

**Script:** `scripts/cases/13_load_phenopackets.py`
**Input:** `~/data/phenopackets/v0.1.19/0.1.19/<cohort>/<file_stem>.json` (~6 700 files)
**Output:** `data/test_cases/01_all_phenopackets.jsonl` — **6 668 lines**

Each line is one Phenopacket flattened to the six field families needed
downstream:

```json
{
  "case_id":         "<cohort>:<file_stem>",
  "source_path":     "data/phenopackets/v0.1.19/.../X.json",
  "subject_id":      "...",
  "hpo_terms":       ["HP:nnnnnnn", ...],     // observed only, dedup, order preserved
  "diseases":        [{"id": "OMIM:nnn", "label": "..."}],
  "interpretations": [{"gene_symbol": "...", "hgnc_id": "...", "variant": "...", "ascertained": bool}]
}
```

### Stage 2 — Eligibility filter

**Script:** `scripts/cases/15_filter_eligible.py` (or equivalent step in the
pipeline)
**Output:** `data/test_cases/02_eligible.jsonl` — **3 878 lines**

Drops cases that fail any of:

- ≥ 1 *observed* HPO term (excludes purely-excluded-features Phenopackets).
- ≥ 1 causal interpretation with a non-null `gene_symbol`.
- Causal `gene_symbol` resolvable to a canonical HGNC symbol via the HGNC
  alias table (snapshot 2026-04-07, 19 296 canonical + 43 263 alias mappings).

Effect: 6 668 → 3 878 cases (58 % retained).

### Stage 3 — MONDO categorisation

**Script:** `scripts/cases/16_categorize_mondo.py`
**Output:** `data/test_cases/03_categorized.jsonl` — **2 971 lines**

Maps each case's disease IDs (OMIM / Orphanet) to one or more MONDO categories
via the MONDO ontology (snapshot v2026-03-03), then keeps only cases that map
to **at least one** of the four target categories:

| Category | MONDO root term |
|---|---|
| developmental | `MONDO:0019052` (developmental delay / intellectual disability) |
| immunological | `MONDO:0021166` (inborn errors of immunity / primary immunodeficiency) |
| metabolic     | `MONDO:0019255` (inherited metabolic disorders) |
| neurological  | `MONDO:0005071` (neurological disorders) |

Cases that map to multiple categories are resolved via a deterministic
category-priority ordering (recorded in master plan §10 deviations).
Cases that match no target category are dropped.

Effect: 3 878 → 2 971 cases (77 % retained from previous stage).

### Stage 4 — Stratified random sample, seed = 42

**Script:** `scripts/cases/17_sample_stratified.py`
**Output:** `data/test_cases/04_sampled.jsonl` — **75 lines**

Draws a stratified sample with equal allocation per category, capped at
availability:

- target 19 / 19 / 19 / 18 per category (developmental / immunological /
  metabolic / neurological)
- `numpy.random.default_rng(seed=42).choice(...)` for the per-category draw
- Sample stored sorted by `case_id` for deterministic downstream ordering

Effect: 2 971 → 75 cases. Sample ratio per category:

| Category | Eligible pool | Sampled | % |
|---|---:|---:|---:|
| developmental | ~880 | 19 | 2.2 % |
| immunological | ~520 | 19 | 3.7 % |
| metabolic     | ~640 | 19 | 3.0 % |
| neurological  | ~931 | 18 | 1.9 % |
| **Total**     | **2 971** | **75** | **2.5 %** |

### Stage 5 — PMC coverage validation

**Script:** `scripts/cases/18_validate_pmc_coverage.py`
**Output:** `data/test_cases/05_validated.jsonl` — **75 lines**

For each sampled case, validates that its causal gene has **≥ 5 PMC OA
articles** in the Phase 1A Qdrant index (`geno_agent_pmc_oa_v1`). The
threshold ensures that the literature-RAG approach has a fair chance of
finding evidence — comparable to what a senior clinical reviewer would
expect a literature review to surface for an established gene-disease link.

Per-case check (parameters in `05_validated_stats.json`):

```
for each (case_id, causal_gene):
    bm25_hits = qdrant.search(query=causal_gene, sparse_only=True, top_k=100)
    distinct_pmcids = {hit.payload["pmcid"] for hit in bm25_hits}
    if len(distinct_pmcids) >= 5:
        keep case
    else:
        replace with another case from the same MONDO category, seed=42
```

**Result of this run:**

| Metric | Value |
|---|---:|
| Initial sample size | 75 |
| Initial pass | **75** |
| Initial fail | 0 |
| Replacements made | 0 |
| Final validated size | 75 |

**Every sampled case passed PMC coverage on first attempt.** This is recorded
verbatim in `data/test_cases/05_validated_stats.json` and reproduces given the
seed + Phase 1A index sha256.

### Stage 6 — Candidate gene draw + finalisation

**Script:** `scripts/cases/19_finalize_test_cases.py`
**Output:** `data/test_cases/06_with_candidates.jsonl` → projection →
`data/test_cases/test_cases.jsonl` — **75 lines**

For each case, draws **49 distractor genes** from the HGNC canonical
symbol set (snapshot 2026-04-07, 19 296 symbols), excluding the case's own
causal gene. The draw is deterministic per case:

```python
rng = numpy.random.default_rng(seed=42 ^ hash_to_uint64(case_id))
pool = sorted(HGNC.canonical_symbols - {causal_gene})
distractors = rng.choice(pool, size=49, replace=False)
```

The 50-gene candidate list is then assembled by inserting `causal_gene` at a
random position chosen by the same RNG (`causal_gene_index_in_candidates`).

The script writes two artefacts:

1. **`test_cases.jsonl`** — the canonical file every evaluation cell reads.
   Sorted by `case_id` for deterministic iteration order.
2. **`test_cases_manifest.json`** — the provenance contract surface (recorded
   sha256, version pins, RNG seed, category distribution, creation timestamp).

---

## 4. Final test case schema

Each line of `test_cases.jsonl` has exactly these fields:

| Field | Type | Description |
|---|---|---|
| `case_id` | string | `"{causal_gene}:{phenopacket_filename}"` — unique, used as filename for all per-case outputs across cells |
| `category` | string | one of `developmental`, `immunological`, `metabolic`, `neurological` |
| `hpo_terms` | list of HPO IDs | observed phenotypic features only |
| `diseases` | list of `{id, label}` | OMIM / Orphanet disease objects |
| `causal_gene` | string | canonical HGNC symbol |
| `candidate_genes` | list of 50 strings | 1 causal + 49 distractors, deterministic order |
| `causal_gene_index_in_candidates` | int | position of `causal_gene` in `candidate_genes` (0-49) |
| `pmc_article_count` | int or null | optional PMC count (null in this run) |
| `source_phenopacket` | string | repo-relative path to the source Phenopacket JSON |

### Example record

```json
{
  "case_id": "ADRA2A:PMID_27376152_FPLD1223",
  "category": "metabolic",
  "hpo_terms": ["HP:0025383", "HP:0002155", "HP:0000819", "HP:0000822",
                "HP:0009125", "HP:0000956", "HP:0003236", "HP:0002240",
                "HP:0003074", "HP:0002149", "HP:0001997", "HP:0002870"],
  "diseases": [{"id": "OMIM:620679",
                "label": "Lipodystrophy, familial partial, type 8"}],
  "causal_gene": "ADRA2A",
  "candidate_genes": ["DCTN6", "TYW3", "CHST6", "CCR10", "CPNE9", ..., "ADRA2A"],
  "causal_gene_index_in_candidates": 49,
  "pmc_article_count": null,
  "source_phenopacket": "data/phenopackets/v0.1.19/0.1.19/ADRA2A/PMID_27376152_FPLD1223.json"
}
```

---

## 5. Final stratification

| Category | n | % of 75 | % of all 4 categories' eligible pool sampled |
|----------|--:|--:|--:|
| developmental | 19 | 25.3 % | 2.2 % |
| immunological | 19 | 25.3 % | 3.7 % |
| metabolic     | 19 | 25.3 % | 3.0 % |
| neurological  | 18 | 24.0 % | 1.9 % |
| **Total**     | **75** | **100 %** | **2.5 %** |

The 19+19+19+18 split is determined by the equal-allocation cap + integer
rounding (75 / 4 = 18.75; the rounding error of 0.75 goes to the largest
category by alphabetical tie-break, which happens to be `developmental` /
`immunological` / `metabolic` per the script).

The master plan §6 calls for an even split; in practice, 18 vs 19 differs by
≤ 5 % which is well inside the acceptance tolerance defined in
`scripts/cases/20_validate_test_cases.py:CATEGORY_TOLERANCE=0.20`.

---

## 6. Acceptance validation

**Script:** `scripts/cases/20_validate_test_cases.py`
**Purpose:** Five independent gates that must all pass before the test case
file is released for evaluation. Each gate surfaces *all* failing cases (not
just the first).

| Gate | Check | Pass on this run? |
|---|---|---|
| 1 | every case has ≥ 3 observed HPO terms | ✅ |
| 2 | every case has exactly 50 unique candidate gene symbols | ✅ |
| 3 | every case's `causal_gene` appears in its `candidate_genes` | ✅ |
| 4 | every case's causal gene has ≥ 5 PMC OA articles in the Phase 1A index | ✅ |
| 5 | the four MONDO categories are within 20 % of equal allocation | ✅ |

Exit code 0 — file is publish-ready.

---

## 7. Reproducibility guarantees

The pipeline is designed to be **bit-stable across re-runs given the same
inputs**:

| Input | How pinned |
|---|---|
| Phenopacket Store version | `v0.1.19` (snapshot held in `~/data/phenopackets/`) |
| HPO ontology | `hp.obo v2026-02-16` (in `data/Human_Phenotype_Ontology/`) |
| MONDO ontology | `v2026-03-03` (in `data/MONDO/`) |
| HGNC snapshot | `hgnc_complete_set_2026-04-07.txt` (sha256 in MANIFEST) |
| RNG seed | `42` across every stage (`PYTHONHASHSEED=42` env var + `numpy.random.default_rng(seed=42)`) |
| Phase 1A index | Qdrant collection `geno_agent_pmc_oa_v1` (sha256 of upload stats in MANIFEST) |
| Final output | `data/test_cases/test_cases.jsonl` sha256 = `4872afb601a07e111b33ad1e52eb5e2652928f09e1aa208c43670f6b4a2b3a53` |

Re-running the pipeline end-to-end produces a `test_cases.jsonl` with the
**exact same sha256** as the version committed in the repo. This is verified
by `scripts/utils/seed.py:apply_seeds()` called by every eval driver.

---

## 8. Why this design makes the 11+ experimental cells comparable

Every evaluation cell (A through K, plus P, L, Q, R, S as they come online)
reads from `data/test_cases/test_cases.jsonl`. Concretely:

| Cell | Driver | Test case loader |
|---|---|---|
| A–J (10 deterministic + LLM cells) | `scripts/eval/run_factorial.py` | reads `test_cases.jsonl` |
| K (Exomiser HPO-only) | `scripts/eval/run_cell_k.py` | reads `test_cases.jsonl` |
| P (D + K RRF ensemble) | `scripts/eval/run_cell_p.py` | reads `cell_D_*/<case_id>.json` + `cell_K_*/<case_id>.json` (built from the same test cases) |
| Cross-encoder rerank diagnostic | `scripts/eval/rerank_diagnostic.py` | reads `test_cases.jsonl` |
| L (full rerank-inside-D) | `scripts/eval/rerank_inside_d.py` | reads `test_cases.jsonl` |
| Q, R, S (LEA cells, planned) | `scripts/eval/run_factorial.py` with `use_lea_synthesiser=True` | reads `test_cases.jsonl` |

Because every cell processes the same 75 (`case_id`, `hpo_terms`,
`candidate_genes`) tuples in the same order, and every cell writes its output
to `data/eval/<cell_dir>/<case_id>.json`, the outputs **pair perfectly** across
cells:

- For any two cells, we can do **paired statistics** (compare top-1 on the
  same case under both pipelines).
- The per-MONDO category breakdown is consistent (Cell K's
  "immunological top-1 = 0.421" is on the same 19 cases as Cell D's
  "immunological top-1 = 0.474").
- The oracle ceiling analysis for Cell P (D ∪ K = 0.827) is well-defined
  because the cases are the same in both inputs.

### What is deterministic vs random

| Component | Determinism class | Reproducibility |
|---|---|---|
| Which 75 cases are in the test set | "random" (statistical) | bit-stable given seed=42 + version pins |
| Gene order in `candidate_genes` | "random" | bit-stable given same seed |
| Which chunks are retrieved | deterministic | same Qdrant index, same query, same top-K → same chunks |
| Deterministic Critic grades | deterministic | regex + section weights |
| LLM Planner / Critic outputs | near-deterministic | temperature=0.0; vLLM has tiny float non-determinism (~1 in 1 000 tokens) |
| Bootstrap CIs (1 000 resamples) | deterministic | seed=42 |
| Cross-encoder rerank | deterministic | inference-time only |

The only non-bit-stable component is the LLM (Qwen3-8B via vLLM), and even
that is within ~0.001 of bit-identical across runs at temperature=0.

---

## 9. Limitations worth flagging

1. **n=75 is modest.** Bootstrap CIs are wide (±~0.10 on top-1 around 0.5–0.7).
   A larger sample (~200) would tighten inferences but was outside compute
   budget.
2. **Four MONDO categories.** The thesis claim only covers those four. Cases
   in oncology, infectious disease, cardiac, dermatological, etc. are *not*
   represented.
3. **Multi-category MONDO mappings handled deterministically.** A case that
   maps to both developmental and metabolic categories is assigned to the
   higher-priority category per the script's tie-break. This is recorded
   as deviation in master plan §10 and is reproducible.
4. **PMC coverage filter is a "fair test" requirement, not a generalisation
   guarantee.** Cases where the causal gene has < 5 PMC articles are
   excluded. This is by design — the literature-RAG approach cannot be
   meaningfully tested on genes without literature — but it means our results
   do not generalise to ultra-rare / undiagnosed cases where the literature
   is genuinely sparse.
5. **Single declared causal gene per case.** Real clinical cases sometimes
   have multiple plausible candidates. The binary top-1 target does not
   capture that complexity.
6. **No held-out validation split.** With only 75 cases, we use the full set
   for every cell. There is no separate held-out subset for hyperparameter
   tuning. Hyperparameters (top-K, batch sizes, RRF damping constant) were
   set from the literature, not tuned on these cases.

---

## 10. Funnel summary

```
+--------------------------------------------------+   stage   files
| Phenopacket Store v0.1.19                        |
| └─ ~6 700 raw JSON files                         |
+----------------------┬───────────────------------+
                       │ ingest & normalise
                       ▼
   01_all_phenopackets.jsonl                            1       6 668
                       │
                       │ eligibility filter (HPO ≥ 1, has gene, HGNC-resolvable)
                       ▼
   02_eligible.jsonl                                    2       3 878
                       │
                       │ MONDO categorisation (4 target categories)
                       ▼
   03_categorized.jsonl                                 3       2 971
                       │
                       │ stratified random sample (seed=42)
                       ▼
   04_sampled.jsonl                                     4          75
                       │
                       │ PMC coverage validation (≥ 5 articles per gene)
                       │ this run: 75/75 passed, 0 replacements
                       ▼
   05_validated.jsonl                                   5          75
                       │
                       │ 49 distractor genes drawn per case (HGNC)
                       ▼
   06_with_candidates.jsonl                             6          75
                       │
                       │ project to canonical schema, sort, sha256
                       ▼
   test_cases.jsonl              ← canonical artefact            75
   test_cases_manifest.json      ← provenance contract
```

Net retention: **75 cases from 6 668** = 1.12 % retained. The selectivity is
driven primarily by the MONDO category filter (we restrict to four out of
~20 possible MONDO branches) and the equal-allocation cap of 75 cases total.

---

## 11. Files and commits

```
scripts/cases/04_download_phenopacket_store.sh          # ingestion entry
scripts/cases/13_load_phenopackets.py                   # stage 1
scripts/cases/15_filter_eligible.py                     # stage 2 (eligibility)
scripts/cases/16_categorize_mondo.py                    # stage 3 (categorisation)
scripts/cases/17_sample_stratified.py                   # stage 4 (sampling, seed=42)
scripts/cases/18_validate_pmc_coverage.py               # stage 5 (PMC ≥ 5)
scripts/cases/19_finalize_test_cases.py                 # stage 6 (distractors + manifest)
scripts/cases/20_validate_test_cases.py                 # 5-gate acceptance

data/test_cases/01_all_phenopackets.jsonl               # 6 668 lines
data/test_cases/02_eligible.jsonl                       # 3 878 lines
data/test_cases/03_categorized.jsonl                    # 2 971 lines
data/test_cases/04_sampled.jsonl                        #    75 lines
data/test_cases/05_validated.jsonl                      #    75 lines
data/test_cases/05_validated_stats.json                 # stats from gate
data/test_cases/06_with_candidates.jsonl                #    75 lines
data/test_cases/test_cases.jsonl                        #    75 lines (canonical)
data/test_cases/test_cases_manifest.json                # provenance
```

Provenance is committed in the repo on branch `main` (Phase 1B PR landed
earlier in May 2026). The artefact files larger than 10 MB are gitignored per
master plan; only the manifest + small JSONL files + scripts are tracked.

---

*This document is the methods reference for the 75-case evaluation set. Cite
this when describing the test population in the thesis or in a manuscript.*
