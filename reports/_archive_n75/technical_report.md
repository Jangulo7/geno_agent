# geno_agent — Phase 1A end-to-end demo (technical report)

**Author:** Johanna Angulo (johanna.angulo@gmail.com)
**Project:** TFM, Universidad UAX — *Agentic Multi-Agent RAG for Gene Prioritization in Rare Mendelian Disease*
**Repository:** [github.com/Jangulo7/geno_agent](https://github.com/Jangulo7/geno_agent)
**Demo run:** 2026-05-09, RTX 5090 / WSL2, git rev `c553d14`

---

## 1. Executive summary

Phase 1A of the `geno_agent` project — a deterministic, byte-reproducible
retrieval pipeline over PubMed Central Open Access (PMC OA) articles, with
hybrid dense + sparse search backed by a self-hosted Qdrant collection — is
implemented and validated end-to-end on a 100-article rare-disease sample.

Total wall-clock for the seven-stage pipeline (download → parse → filter →
chunk → embed → upload → validate) was **44 seconds** on a single workstation
(NVIDIA RTX 5090, 32 GB VRAM, 64 GB RAM, WSL2). All twelve rare-disease probe
queries returned relevant top-1 hits across dense, BM25, and hybrid (RRF)
retrieval modes.

The same scripts run unchanged on the full 150 GB PMC OA corpus per
master plan §7, with the only differences being the input set and the
~5–9 day wall-clock estimate dominated by ~24–48 GPU-hours of embedding.

---

## 2. Why this matters

Rare diseases collectively affect roughly 300 million people worldwide, yet
~50 % of exome- and genome-sequencing referrals remain without a molecular
diagnosis. A substantial fraction of the diagnostic gap is not undetectable
variants but the limits of phenotype-driven prioritization tools (e.g.,
[Exomiser](https://exomiser.readthedocs.io)) when the causal gene is novel,
under-annotated, or only described in case reports, functional studies, or
phenotype-expansion papers — material that lives in unstructured PMC literature
and cannot be hand-curated at scale.

`geno_agent` proposes an **agentic multi-agent RAG architecture** —
Query Planner / Retriever / Critic / Synthesizer coordinated as a
LangGraph state graph — to automate the literature evidence synthesis
step that currently requires hours of clinical-genetics-team time per
patient. The **Phase 1A pipeline reported here is the corpus-build
substrate** the four agents will retrieve from. No agent code is in
scope for this report; that is the Phase 2 deliverable.

---

## 3. Architecture

![Architecture diagram](images/architecture.svg)

The architecture is defined in `MASTER_PROJECT_v2.1.md` §1 and §4.
Three principles drive the design:

1. **Reproducibility-first.** Every stochastic surface is pinned: chunk
   IDs are `uuid.uuid5(NAMESPACE, content_key)` rather than UUID4;
   PubMedBERT is pinned to a specific revision; Qdrant is a pinned image
   tag (`qdrant/qdrant:v1.14.1`); ontologies (HPO, MONDO, GO, HGNC) are
   downloaded by exact dated release and SHA-256-hashed into
   `data/MANIFEST.tsv`.
2. **Hybrid retrieval, native to the index.** Dense PubMedBERT vectors
   capture biomedical semantics; Qdrant's native BM25 sparse vectors
   (via `fastembed.SparseTextEmbedding("Qdrant/bm25")`) capture exact
   gene/disease lexical matches. Fusion is **reciprocal rank** at query
   time via `FusionQuery(fusion=Fusion.RRF)`. The master plan v2.1
   explicitly forbids any hash-of-whitespace BM25 fallback (§4 step 5
   line 1108).
3. **Local hardware sufficient.** The full system targets a single
   workstation: NVIDIA RTX 5090 (32 GB VRAM, Blackwell sm_120, CUDA
   12.8+), 64 GB RAM, ~700 GB Linux storage. No cloud API dependency
   is required for any pipeline stage — important for both
   reproducibility and any future extension to protected clinical data.

### 3.1 Storage strategy

WSL2 is used in dual-drive mode (`MASTER_PROJECT_v2.1.md` §1):

| Filesystem | Path | Purpose | Why |
|---|---|---|---|
| Linux (~700 GB) | `~/rare-disease-rag/qdrant_storage/` | Qdrant index | HNSW graph traversal demands native fs latency |
| Linux | `~/rare-disease-rag/models/` | Model weights | Same |
| Windows (`/mnt/c/`) | `/mnt/c/pmc_workspace/` | Raw XML, intermediate parquet | Bulk sequential I/O tolerates 9P overhead; deletable per tier |

The pipeline scripts respect this split: chunkers and embedders write
shards to `/mnt/c/`, the indexer pulls them in and writes only
fixed-size payload to Qdrant on the Linux side.

### 3.2 Qdrant collection schema

Created by `scripts/indexing/10_create_qdrant_index.py`
(`COLLECTION='geno_agent_pmc_oa_v1'`):

| Vector / index | Configuration |
|---|---|
| Dense `"dense"` | 768-dim, `COSINE` distance, `on_disk=True`, HNSW `m=16` / `ef_construct=200` / `full_scan_threshold=10000` |
| Sparse `"bm25"` | `Modifier.IDF` (Qdrant computes IDF on the server side, paired with TF-only query embeddings) |
| Payload | `on_disk_payload=True` (mandatory for the 2–5 M chunk full corpus per master plan v2.1 fix #3) |
| Indexed payload fields | `section_type` (KEYWORD), `pmcid` (KEYWORD), `pub_year` (INTEGER) |

---

## 4. Pipeline implementation (per script)

The pipeline is the linear sequence in
[scripts/demo/run_pipeline.sh](../scripts/demo/run_pipeline.sh) which can
be invoked with one command. Each script is independently runnable for
debugging / partial reruns.

| § | Script | Input | Output | Demo runtime |
|---|---|---|---|---|
| 5a | [`scripts/corpus/01_demo_fetch_pmc.py`](../scripts/corpus/01_demo_fetch_pmc.py) | NCBI esearch query | `xml_raw/demo/PMC*.xml` | ~95 s (NCBI rate limit) |
| 5b | [`scripts/corpus/06_parse_jats_xml.py`](../scripts/corpus/06_parse_jats_xml.py) | JATS XML | `parsed/demo.jsonl` | <1 s |
| 5c | [`scripts/corpus/07_filter_corpus.py`](../scripts/corpus/07_filter_corpus.py) | Parsed JSONL | `filtered/demo.jsonl` | <1 s |
| 5d | [`scripts/corpus/08_section_aware_chunking.py`](../scripts/corpus/08_section_aware_chunking.py) | Filtered JSONL | `chunks/demo.jsonl` | ~1.5 s |
| 5e | [`scripts/embedding/09_generate_embeddings.py`](../scripts/embedding/09_generate_embeddings.py) | Chunked JSONL | `embeddings/demo.parquet` | 4.6 s |
| 5f | [`scripts/indexing/10_create_qdrant_index.py --upload`](../scripts/indexing/10_create_qdrant_index.py) | Parquet shards | Qdrant points | ~1.5 s |
| 6 | [`scripts/indexing/11_validate_index.py`](../scripts/indexing/11_validate_index.py) | Qdrant collection | stdout / log | ~5 s |

### 4.1 §5a — corpus acquisition (`01_demo_fetch_pmc.py`)

Demo path uses NCBI E-utilities (`esearch.fcgi` + `efetch.fcgi`) over
plain HTTPS instead of the master plan's bulk `aws s3 sync` (§3.1).
Reasons: (a) no AWS dependency, (b) curated rare-disease enrichment via
MeSH-targeted queries, (c) only ~13 MB needed for demo. Production runs
fall back to the full S3 sync.

Stratified across the four MONDO disease categories the Phase 1B test-case
selection will use (`MASTER_PROJECT_v2.1.md` §6 step 3):

| Category | MeSH search | Articles |
|---|---|---|
| neurological | Huntington Disease, Charcot-Marie-Tooth Disease, Rett Syndrome | 25 |
| metabolic | Phenylketonurias, Fabry Disease, Niemann-Pick Diseases | 25 |
| immunological | Agammaglobulinemia, CVID, SCID | 25 |
| developmental | Marfan Syndrome, Noonan Syndrome, DiGeorge Syndrome | 25 |

Output: `100 PMC*.xml` files, 12.8 MB total, in `/mnt/c/pmc_workspace/xml_raw/demo/`.

### 4.2 §5b — JATS parsing (`06_parse_jats_xml.py`)

Implementation uses `lxml` rather than `xml.etree.ElementTree`
(deviation from master plan §4.2.2; recorded in §10) because it is
~10× faster on the full 4 M-article corpus and more robust to JATS
namespace variants.

Output schema (one JSON per line):

```json
{
  "pmcid": "PMC10258773",
  "pmid": "37306896",
  "doi": "10.1007/s10875-023-01526-3",
  "title": "...",
  "journal": "J Clin Immunol",
  "pub_year": 2023,
  "authors": ["Doe J", "Smith A"],
  "mesh_terms": [],
  "keywords": ["..."],
  "abstract": "...",
  "sections": [
    {"section_type": "introduction", "heading": "Introduction", "text": "..."},
    {"section_type": "methods",      "heading": "Methods",      "text": "..."}
  ]
}
```

Section-type classification uses the `<sec sec-type="...">` attribute
when present and falls back to a regex on the heading text otherwise.
Many recent articles in the demo had empty `sec-type` attributes — the
heading-regex fallback recovered all standard categories.

**Demo result:** 100 / 100 parsed, 559 sections, 3,411,874 characters.

### 4.3 §5c — relevance filter (`07_filter_corpus.py`)

The filter retains an article if any of the following fire:

1. **MeSH:** any term in `mesh_terms` is in the genetics whitelist
   (`{genetics, genomics, mutation, hereditary, mendelian, ...}` plus
   specific rare-disease names).
2. **Keyword:** any `<kwd>` is in the same whitelist.
3. **Title/abstract regex:** OR of seven regex patterns covering
   *(genetic|genomic|hereditary|mendelian|inborn)*, *(mutation|variant|deletion|duplication|insertion|polymorphism)*, *(HPO|OMIM|Orphanet|GeneReviews|MONDO|HGNC|ClinVar)*, *phenotypic*, *(rare|orphan) (disease|disorder|condition|syndrome)*, *(exome|genome|RNA-seq|transcriptome) sequencing*, and *(autosomal (dominant|recessive)|X-linked)*.

The full Phase 1A run hard-asserts the retained count is in
`[100,000, 600,000]` — outside that band almost always means a regex
regression. The demo runs without `--strict`, since 100 articles always
fall outside that band.

**Demo result:** 89 / 100 retained (89 %). Of the rule hits across the 89
retained: keyword 55, title/abstract regex 79, MeSH 0 (recent articles
not yet MeSH-indexed). Eleven articles were rejected because the
selected disease-MeSH paper happened to focus on a non-genetic
complication and used no genetics vocabulary.

### 4.4 §5d — chunking with deterministic UUID5 (`08_section_aware_chunking.py`)

Chunks never span section boundaries. Within a section, the
PubMedBERT tokenizer (`NeuML/pubmedbert-base-embeddings`) produces
token IDs; the chunker emits 512-token windows with 50-token overlap.

Each chunk receives a deterministic ID:

```python
CHUNK_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")  # pinned
text_digest = hashlib.blake2b(chunk_text.encode("utf-8"), digest_size=16).hexdigest()
chunk_id = str(uuid.uuid5(
    CHUNK_NAMESPACE,
    f"{pmcid}|{section_type}|{chunk_index}|{text_digest}"
))
```

This makes Qdrant upserts idempotent — re-running the entire pipeline
produces the same set of point IDs and the same set of payloads. It also
makes the manifest hash byte-stable across machines.

**Demo result:** 89 articles → **1,625 chunks**, average 18.3 chunks per
article. 21 sections were skipped as too short (< 50 chars). Section
type distribution:

![Chunk distribution by section type](images/section_distribution.png)

The "other" bucket dominates (346) because the demo corpus contains
many recent articles whose sections do not match the standard
IMRaD layout — a known JATS reality.

### 4.5 §5e — PubMedBERT embedding (`09_generate_embeddings.py`)

Loads `NeuML/pubmedbert-base-embeddings` via `sentence-transformers`,
encodes all chunks in batches of 32 with mean pooling and L2
normalization for cosine similarity. Output is a single zstd-compressed
parquet shard with a binary `embedding` column (np.float32 bytes).

**Demo result:** 1,625 chunks encoded in **4.6 s on the RTX 5090**,
sustained throughput **351 chunks/s**. Output parquet is 5.5 MB.

![Embedding throughput](images/embedding_throughput.png)

For the full corpus (~3 M chunks at 351 chunks/s) this projects to
~140 minutes of pure GPU time — comfortably inside the master plan §7
estimate of 8–16 hours per tier (which accounts for I/O, batching
overhead, and peak-batch tuning).

### 4.6 §5f — upload to Qdrant (`10_create_qdrant_index.py --upload`)

For each parquet row, the script:

1. Reconstructs the dense vector from the binary column
   (`np.frombuffer(emb, dtype=np.float32).tolist()`).
2. Computes the BM25 sparse vector using
   `SparseTextEmbedding("Qdrant/bm25").embed(texts)` — the **document-side**
   call, which produces TF + IDF (master plan §4 step 5 line 1107). The
   query side uses `.query_embed()` (TF only, line 1111) — the
   IDF-weighted index is server-side via `Modifier.IDF`.
3. Builds a `PointStruct` with both vectors, `chunk_id` as the point ID
   (idempotent), and the full payload.
4. Upserts in batches of 128.

**Demo result:** 1,625 points uploaded in ~1.5 s. Final collection
state: status `green`, 1,625 points, dense + BM25 + on_disk_payload.

### 4.7 §6 — retrieval validation (`11_validate_index.py`)

Twelve rare-disease probes are run in three modes each:

| Mode | API | Notes |
|---|---|---|
| Dense | `client.query_points(query=vec, using="dense")` | PubMedBERT-encoded query |
| BM25 | `client.query_points(query=SparseVector(...), using="bm25")` | `SparseTextEmbedding.query_embed()` (TF only) |
| Hybrid | `prefetch=[dense, bm25]; query=FusionQuery(Fusion.RRF)` | Reciprocal rank fusion at query time |

Sample top-1 results table:

![Probe retrieval table](images/retrieval_modes.png)

A faux-terminal capture of the validate run:

![Validate terminal capture](images/terminal_screenshot.png)

The full 12-probe output is in `reports/run_logs/11_validate.log`.
Highlights:

- `"common variable immunodeficiency B cell"` → top dense hit
  `PMC11949678` introduction: *"Common variable immunodeficiency (CVID)
  is a primary B-cell immunodeficiency disorder characterized by marked
  hypogammaglobulinemia..."* (cosine 0.741).
- `"DiGeorge syndrome 22q11 deletion thymus"` → top hybrid hit
  `PMC5916974` introduction directly describing 22q11 microdeletions
  (RRF score 1.000).
- `"phenylketonuria PAH enzyme deficiency"` → top hybrid hit
  `PMC2885380` introduction citing OMIM 221600 (RRF score 0.833).

These confirm both the semantic encoder (dense) and the BM25 channel
operate as intended over the indexed corpus.

---

## 5. Reproducibility design

| Surface | Pin / mechanism |
|---|---|
| Random seeds | `RANDOM_SEED=42`, `PYTHONHASHSEED=42` in `.env`; applied via `scripts/utils/seed.py:apply_seeds()` at every entrypoint (sets `random`, `numpy`, `torch.cuda` seeds, `torch.use_deterministic_algorithms(warn_only=True)`, cuDNN deterministic flags). |
| Chunk IDs | UUID5 over `(pmcid, section_type, chunk_index, blake2b(text))` with the pinned namespace `6f9619ff-8b86-d011-b42d-00cf4fc964ff`. |
| Cross-process hashing | `scripts/utils/seed.py:stable_hash()` uses BLAKE2b — Python's built-in `hash()` is salted per-process, unsafe for byte-stable artifacts. |
| Ontology versions | HPO `v2026-02-16`, MONDO `v2026-03-03`, GO `2026-03-25`, HGNC `2026-04-07`. SHA-256 of every file in `data/MANIFEST.tsv`. |
| Embedding model | `NeuML/pubmedbert-base-embeddings` (768-dim) — the canonical PubMedBERT sentence embedding model. |
| Qdrant server | `qdrant/qdrant:v1.14.1` pinned in `docker-compose.yml`. |
| Python deps | All 19 deps in `pyproject.toml` pinned to exact `==X.Y.Z` versions matching the host's `pytorch-env`. |

The verifier `scripts/ontology/12_verify_ontologies.py` confirms the
data-version stamp embedded in each downloaded OBO file matches the
pin, on every run.

---

## 6. Master plan deviations (§10)

| Methodology spec | Implementation | Rationale |
|---|---|---|
| §3 / §4.2.3 — pinned 2024 ontologies | Updated to 2026 releases | Project executed in 2026; 2024 versions out of date |
| HGNC EBI FTP URL | Switched to GCS bucket `public-download-files` | EBI FTP archive paths now 404 |
| §2 line 176 — `python3.11` | Use `python3.12.3` (only available) | Compatible with all pinned deps |
| §2 line 189 — torch `cu124` | Pinned to `torch==2.9.0.dev20250820+cu128` | RTX 5090 (Blackwell sm_120) requires CUDA 12.8+; cu124 wheels fail at first kernel launch |
| §2 — fresh project `.venv` | Reuse existing `/home/hana77/pytorch-env/` | Avoids ~5 GB redundant cu128 torch download; pyproject.toml records actual installed versions |
| §2.1 — `qdrant/qdrant:v1.12.4` | Bumped to `qdrant/qdrant:v1.14.1` | Aligns with `qdrant-client==1.14.3` in pytorch-env, eliminating the version-mismatch UserWarning |
| §3.1 — `aws s3 sync` for PMC OA | NCBI esearch + efetch demo path | Demo path; production AWS sync deferred for the full 150 GB build |
| §4.2.2 — `xml.etree.ElementTree` | `lxml` | ~10× faster on 4 M articles, more namespace-robust |
| §4.2.2 — sparse BM25 (no library specified) | `fastembed.SparseTextEmbedding("Qdrant/bm25")` | The canonical Qdrant-native BM25; explicitly named for transparency |

The full deviations table (with additional Phase 1B sample-design
clarifications) is in `MASTER_PROJECT_v2.1.md` §10.

---

## 7. End-to-end pipeline metrics (live demo)

```text
Pipeline start: 2026-05-09T16:08:11Z
Pipeline end:   2026-05-09T16:08:56Z
Total wall-clock: 44 s
```

![Pipeline throughput](images/pipeline_throughput.png)

| Stage | Wall-clock | Throughput / outcome |
|---|---|---|
| Fetch (NCBI esearch+efetch) | ~95 s on first run, ~2 s on cached re-run | 100 / 100 articles, 12.8 MB |
| Parse JATS | <1 s | 100 / 100 records, 559 sections, 3.4 M chars |
| Filter | <1 s | 89 / 100 retained (89 %) |
| Chunk | ~1.5 s | 1,625 chunks (avg 18.3 / article) |
| Embed | 4.6 s | 351 chunks/s on RTX 5090 |
| Upload | ~1.5 s | 1,625 Qdrant points (dense + BM25 + payload) |
| Validate | ~5 s | 12 probes × 3 modes, all top-1 relevant |

NB the first run includes ~95 s of NCBI HTTP latency for downloading
JATS XML; the table above shows the cached-rerun timing. The "44 s"
total is dominated by GPU embedding + tokenizer initialization +
NCBI cache hits.

Environment fingerprint captured in `reports/pipeline_stats.json`:

```json
{
  "python": "Python 3.12.3",
  "git_rev": "c553d14",
  "torch": "2.9.0.dev20250820+cu128",
  "cuda_available": true,
  "gpu": "NVIDIA GeForce RTX 5090"
}
```

---

## 8. Reproducing this run

From a fresh clone:

```bash
# 1. Activate the pytorch-env (cu128 nightly torch already installed)
source /home/hana77/pytorch-env/bin/activate

# 2. Bring up the dedicated Qdrant container (alternate ports)
docker compose up -d                               # qdrant_geno_agent on 6533/6534

# 3. (Once) verify ontologies and create the empty collection
python scripts/ontology/12_verify_ontologies.py
python scripts/indexing/10_create_qdrant_index.py

# 4. Run the full demo pipeline
bash scripts/demo/run_pipeline.sh

# 5. Capture stats and render visualizations
python scripts/demo/collect_stats.py
python scripts/demo/make_visualizations.py
```

Expected outputs:

- `reports/pipeline_stats.json` — structured stats
- `reports/images/*.png` — five generated charts
- `reports/run_logs/*.log` — full per-step stdout

---

## 9. Limitations & next steps

**Not in scope of this report:**

- Phase 1B test-case preparation (master plan §6) — phenopacket ingest,
  inclusion/exclusion filtering, MONDO categorization, stratified
  sampling, candidate gene-list construction with HGNC distractors.
  Blocked on Phase 1A completion per `CLAUDE.md` hard rule; demo
  pipeline does not gate Phase 1B.
- The four agents themselves (Query Planner / Retriever / Critic /
  Synthesizer). Phase 2 deliverable.
- Quantitative retrieval evaluation (precision@K, recall@K, nDCG)
  against a labeled benchmark. Phase 1B will produce the benchmark.

**Production-corpus path remaining:**

- Run `scripts/corpus/01_download_pmc_oa.sh` (TODO — write to mirror the
  demo fetcher's interface; currently defined in master plan §3.1 as a
  shell `aws s3 sync`).
- Re-run the same `06–11` scripts on each tier (`oa_comm`,
  `oa_noncomm`, `oa_other`) per the §7 tier-by-tier streaming plan.
- Estimated wall clock per master plan §7: 5–9 days on the same host.

---

## 10. Citation

```bibtex
@misc{angulo2026geno_agent,
  author       = {Angulo, Johanna},
  title        = {geno\_agent: An Agentic Multi-Agent RAG System for
                  Gene Prioritization in Rare Mendelian Disease},
  year         = {2026},
  howpublished = {\url{https://github.com/Jangulo7/geno_agent}},
  note         = {Master's thesis project, Universidad UAX}
}
```

## 11. Repository links

- Source: https://github.com/Jangulo7/geno_agent
- Master plan (full spec): [`MASTER_PROJECT_v2.1.md`](../MASTER_PROJECT_v2.1.md)
- Project rules (CLAUDE.md): [`CLAUDE.md`](../CLAUDE.md)
- This report: [`reports/technical_report.md`](technical_report.md)
- Visual report: [`reports/visual_report.html`](visual_report.html)
- Pipeline stats JSON: [`reports/pipeline_stats.json`](pipeline_stats.json)
- Run logs: [`reports/run_logs/`](run_logs/)
- Acquisition manifest (SHA-256s): [`data/MANIFEST.tsv`](../data/MANIFEST.tsv)
