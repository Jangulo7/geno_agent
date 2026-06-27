# REPRODUCE — P1 (methods / shared foundation)

Rebuild the **shared foundation**: the PMC-OA Qdrant index and the n=1,047
evaluation cohort. P2 (GenoAgent) and the external P3 repo both depend on this.

> The full, authoritative command sequence with exact flags lives in
> [`reports/methodology.md`](../../reports/methodology.md) and
> [`MASTER_PROJECT_v2.2.md`](../../MASTER_PROJECT_v2.2.md) §4 (Phase 1A) and §6/§7
> (Phase 1B). This file is the entry-point map and the verification contract.

## 0. Environment (as actually run in the study — do not "upgrade")

- Python **3.12.3**, NVIDIA RTX 5090 (32 GB), WSL2 Ubuntu 24.04.
- The study env is `~/pytorch-env` with **`torch==2.12.0.dev20260407+cu128`**
  (CUDA 12.8 nightly, required by the RTX 5090) — matching `pyproject.toml`.
  Install needs the PyTorch cu128 nightly index; PyPI alone will not resolve the
  nightly wheels.
- Determinism: `PYTHONHASHSEED=42`, `RANDOM_SEED=42`, UUID5 chunk IDs, pinned
  ontology versions. Copy `.env.example` → `.env` and fill in paths/ports.

> Note: `requirements.lock.txt` is a historical 2026-05 snapshot and lists an
> older torch (`2.9.0.dev…`); **`pyproject.toml` is authoritative** and matches the
> installed environment.

## 1. Phase 1A — PMC-OA corpus → Qdrant index

```bash
source ~/pytorch-env/bin/activate
cp .env.example .env          # edit paths/ports
docker compose up -d          # Qdrant v1.14.1 on :6533/:6534

# acquire + parse + filter + chunk  (MASTER_PROJECT §4 / §7 step 5)
python scripts/corpus/02_extract_and_parse_ftp.py
python scripts/corpus/03_normalize_dedupe_filter.py
python scripts/corpus/06_parse_jats_xml.py
python scripts/corpus/07_filter_corpus.py
python scripts/corpus/08_section_aware_chunking.py

# embed (PubMedBERT, 768-d) + index (dense HNSW + BM25 sparse)
python scripts/embedding/05_embed_chunks.py
python scripts/indexing/10_create_qdrant_index.py --upload
python scripts/indexing/11_validate_index.py
```

**Verify:** collection `geno_agent_pmc_oa_v1` must report **52,777,395** points and
match the fingerprint in `data/MANIFEST.tsv`
(`c6e53665e0e32e39e2871b705c32f8e0d69dd3654a20da4749bcf672d07f3d6e`).

## 2. Phase 1B — Phenopackets → n=1,047 cohort

```bash
python scripts/ontology/12_verify_ontologies.py   # HPO/MONDO/GO/HGNC integrity
python scripts/cases/13_load_phenopackets.py
python scripts/cases/14_apply_inclusion_exclusion.py
python scripts/cases/15_categorize_by_mondo.py
python scripts/cases/16_stratified_sample.py --per-category-target 250,300,250,247
python scripts/cases/17_validate_pmc_coverage.py
python scripts/cases/18_build_candidate_lists.py   # 1 causal + 49 distractors, seeded
python scripts/cases/19_finalize_test_cases.py
python scripts/cases/20_validate_test_cases.py     # 5-point acceptance gate
```

**Output:** `data/test_cases_1050/test_cases.jsonl` (250 dev + 300 imm + 250 met +
247 neuro, seed 42, Phenopacket Store v0.1.26).

## 3. Test the foundation code (no GPU / index needed)

```bash
pytest -m "not integration"   # 200 unit tests; deterministic chunk-ID + cohort contracts
```

## Recipe-only note (corpus / index)

The Qdrant index and chunk/parsed JSONL embed verbatim PMC-OA full text across
**mixed CC license tiers** and total ~370 GB — **not redistributed**. Reproduce by
rebuilding from the public PMC-OA snapshot (pinned date) using the scripts above;
the chunk count + fingerprint above let you verify your rebuild matches.
