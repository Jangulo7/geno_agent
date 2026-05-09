# geno_agent — Comprehensive Project Report (v3, consolidated)

**Author:** Johanna Angulo (johanna.angulo@gmail.com)
**Project:** TFM, Universidad UAX — *Agentic Multi-Agent RAG for Gene Prioritization in Rare Mendelian Disease*
**Repository:** [github.com/Jangulo7/geno_agent](https://github.com/Jangulo7/geno_agent) (private)
**Date:** 2026-05-09 21:00 local
**Snapshot of:** `main` @ `dbb08a8`
**Supersedes:** `progress_report_09052026.{md,html}` (v1), `progress_report_09052026_v2.{md,html}` (v2), `technical_report.md`, `visual_report.html`

This report is the canonical, standalone deep-technical document for the `geno_agent` project as of 2026-05-09. It captures the full system as conceived and built — methodology, architecture, every script, every pinned version, every reproducibility decision, and every deviation from the master plan — in a form sufficient to (a) reproduce the work bit-for-bit on equivalent hardware, (b) understand the system's design and intent, and (c) resume implementation from the current state.

---

## Table of contents

1. Executive summary
2. Project context and motivation
3. System architecture
4. Hardware specification
5. Software stack and pinned versions
6. Phase 1A — corpus pipeline (implementation per script)
7. Phase 1B — test-case curation (implementation per script)
8. Demo run — end-to-end evidence
9. Phase 2 — agentic UI layer (specification)
10. Reproducibility design
11. Master plan deviations (full §10)
12. Configuration files
13. Data acquisition manifest
14. Operational runbook
15. Limitations, risks, and next steps
16. Repository layout
17. Citation
18. Acknowledgments and prior work

---

## 1. Executive summary

The `geno_agent` project is an agentic, multi-agent retrieval-augmented generation (RAG) system that automates literature-based evidence synthesis for the most labor-intensive step of the rare-disease diagnostic pipeline: deciding which candidate gene most plausibly causes a patient's phenotype. The system targets **on-device deployment on a single workstation** (no cloud LLM dependency) and is designed for **byte-stable reproducibility** across runs and machines.

As of this snapshot:

| Phase | Status | Headline |
|---|---|---|
| 1A — pipeline scripts | ✅ Complete | All 7 scripts validated end-to-end on 100-article demo (44 s wall-clock, 1,625 chunks indexed, 12 / 12 probe queries return relevant top-1 hits) |
| 1A — production corpus | 🔄 Running | AWS S3 sync of ~5M PMC OA articles (~150 GB filtered to XML) launched 2026-05-09 19:20 UTC; ~5–9 day estimated wall-clock |
| 1B — test cases (§6) | 🟡 56 % (5 / 9 scripts) | 6,668 phenopackets ingested → 3,878 eligible → 2,971 categorized → **75-case stratified sample drawn deterministically (seed=42)** |
| 1B — coverage validation (step [13]) | ⏳ Hard-blocked on full corpus | Awaits production index |
| 2 — agentic UI layer (§11) | ⏳ Plan locked | LangGraph + FastAPI + CopilotKit React (forked from `Jangulo7/agent_UI`) + Qwen3-8B/vLLM. ~12–14 engineering days projected. |

The project has been built reproducibility-first: every external artifact is pinned by exact version, content-hashed (SHA-256), and recorded in `data/MANIFEST.tsv`. Chunk IDs are deterministic UUID5 derivations of content; random seeds are pinned to 42; CUDA determinism flags are enabled with warn-only fallback for cuBLAS kernels lacking deterministic implementations. Identical inputs on the same hardware yield byte-identical Qdrant point IDs and payloads.

Phase 1A's production-scale build is the critical-path gate to all quantitative results: Phase 1B step [13] (PMC coverage validation) and the Phase 2 §11.5 evaluation harness both query the populated index. The build is currently in flight.

---

## 2. Project context and motivation

### 2.1 The clinical problem

Rare diseases collectively affect an estimated [300 million people worldwide](https://doi.org/10.1038/s41431-019-0508-0) — between 3.5 % and 8 % of the global population. Despite the maturation of next-generation sequencing, roughly **half of all exome and genome sequencing referrals remain without a molecular diagnosis** ([Clark et al., 2018](https://doi.org/10.1038/s41525-018-0053-8)).

A substantial fraction of the diagnostic gap is not undetectable variants but the limits of phenotype-driven prioritization tools when the causal gene is novel, under-annotated, or only described in case reports, functional studies, or phenotype-expansion papers. This material lives in unstructured PubMed Central (PMC) literature and cannot be hand-curated at scale: PMC indexes over a million new articles per year, and the PMC Open Access subset alone contains more than four million full-text articles.

### 2.2 The methodological gap

Phenotype-driven prioritization tools such as [Exomiser](https://exomiser.readthedocs.io) ([Smedley et al., 2015](https://doi.org/10.1038/nprot.2015.124)) work well when the causal gene is already well annotated in curated phenotype databases. They cannot surface novel or emerging gene–phenotype associations that exist *only* in unstructured literature.

Monolithic single-pass RAG systems ([Lewis et al., 2020](https://arxiv.org/abs/2005.11401)) retrieve once and generate once; they cannot perform **iterative query refinement**, **explicit relevance grading per chunk**, or **self-correction loops** — capabilities that are clinically useful when the first retrieval misses the true causal evidence.

### 2.3 The geno_agent thesis

This project asks whether a **multi-agent RAG architecture deployed on local hardware**, grounded in pinned PMC OA literature, can meaningfully assist the literature-evidence-synthesis step that currently consumes hours of clinical-genetics-team time per patient. The architecture decomposes the task across four specialized agents — Query Planner, Retriever, Critic, Synthesizer — coordinated as a stateful graph in [LangGraph](https://github.com/langchain-ai/langgraph). The thesis evaluation isolates two contributions independently: (a) the multi-agent decomposition vs a single-agent baseline, (b) hybrid dense + BM25 retrieval vs dense-only.

### 2.4 What this work is and is not claiming

**Claiming:** novelty in *application* — to our knowledge the first end-to-end validated agentic multi-agent RAG system designed and evaluated specifically for causal gene prioritization in rare Mendelian disease via literature evidence synthesis, with rigorous reproducibility design and a 2×2+1 factorial evaluation against an external phenotype-driven baseline (Exomiser).

**Not claiming:** novelty in *technique*. RAG itself, multi-agent LLM systems generally, hybrid dense + sparse retrieval, and the use of PMC as a corpus are all established methods. The contribution is the application of these techniques, in this combination, to this clinical problem, with a reproducibility-first methodology.

---

## 3. System architecture

### 3.1 High-level pipeline

The system is split into three implementation phases plus an evaluation phase:

```
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 1A — Knowledge corpus build                                  │
│  PMC OA → JATS parse → genetics filter → UUID5 chunks → PubMedBERT  │
│  → Qdrant (dense HNSW + BM25 sparse + section-typed payload)        │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│  PHASE 1B — Test-case benchmark                                     │
│  Phenopacket-Store v0.1.19 → eligibility filter → MONDO categorize  │
│  → seed=42 stratified sample → PMC coverage validate → +49 distractr │
│  → canonical test_cases.jsonl (50-100 cases, 1 causal + 49 distract) │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│  PHASE 2 — Agentic UI layer                                         │
│  LangGraph state graph (4 agents) ↔ FastAPI + copilotkit-sdk-python │
│  ↔ CopilotKit React UI (HPOPicker/CandidateGeneList/AgentTracePanel)│
│  Local LLM: Qwen3-8B via vLLM                                       │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│  PHASE 2 EVALUATION — 2×2+1 factorial vs Exomiser baseline          │
│  Cells A (single-agent dense) / B (single hybrid) / C (multi dense) │
│  / D (multi hybrid) / E (Exomiser)                                  │
│  Metrics: top-1, top-5, top-10, MRR, NDCG@10 with bootstrap CIs     │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Architectural principles

Three principles drive every design decision:

1. **Reproducibility-first.** Identical inputs on the same hardware must yield byte-identical outputs. Operationally: UUID5 chunk IDs, pinned PubMedBERT revision, pinned Qdrant image, dated ontology releases SHA-256-hashed in `MANIFEST.tsv`, `RANDOM_SEED=42` everywhere, `PYTHONHASHSEED=42` in `.env`, `torch.use_deterministic_algorithms(warn_only=True)`.
2. **Hybrid retrieval native to the index.** Dense PubMedBERT vectors capture biomedical semantics; Qdrant's native BM25 sparse vectors (via `fastembed.SparseTextEmbedding("Qdrant/bm25")`) capture exact gene/disease lexical matches. Fusion is reciprocal rank at query time via Qdrant's `FusionQuery(Fusion.RRF)`. Master plan v2.1 explicitly forbids any hash-of-whitespace BM25 fallback.
3. **Local hardware sufficient.** The full system targets a single workstation with no cloud LLM dependency. Important for both reproducibility and any future extension to protected clinical data.

### 3.3 Storage strategy (WSL2 dual-drive)

WSL2 is used in dual-drive mode per master plan §1:

| Filesystem | Path | Purpose | Why |
|---|---|---|---|
| Linux (~700 GB) | `~/rare-disease-rag/qdrant_storage/` | Qdrant index | HNSW graph traversal demands native fs latency (5-10× faster than 9P) |
| Linux | `~/rare-disease-rag/models/` | Model weights (Qwen3-8B, PubMedBERT) | Same |
| Windows (`/mnt/c/`) | `/mnt/c/pmc_workspace/` | Raw XML + intermediate parquet | Bulk sequential I/O tolerates 9P; deletable per pipeline stage |

The pipeline scripts respect this split: chunkers and embedders write shards to `/mnt/c/`; the indexer pulls them in and writes only fixed-size payload to Qdrant on the Linux side.

### 3.4 Qdrant collection schema

Created by `scripts/indexing/10_create_qdrant_index.py`. Collection name from `.env`: `geno_agent_pmc_oa_v1`.

| Vector / index | Configuration | Rationale |
|---|---|---|
| Dense `"dense"` | 768-dim, COSINE, `on_disk=True`, HNSW `m=16` / `ef_construct=200` / `full_scan_threshold=10000` | PubMedBERT's native dim; cosine pairs with L2-normalized vectors; on-disk avoids RAM blow-up at 5M chunks |
| Sparse `"bm25"` | `Modifier.IDF` | Qdrant computes IDF server-side; query side uses `query_embed()` (TF-only) — see §6.6 below |
| Payload | `on_disk_payload=True` | Master plan v2.1 fix #5; mandatory for the 2-5 M chunk corpus |
| Indexed payload fields | `section_type` (KEYWORD), `pmcid` (KEYWORD), `pub_year` (INTEGER) | Filter dimensions for the Retriever agent |

---

## 4. Hardware specification

The reference deployment runs entirely on a single workstation:

| Component | Specification |
|---|---|
| GPU | NVIDIA GeForce RTX 5090, 32 GB VRAM, Blackwell architecture (sm_120, Compute Capability 12.0) |
| CPU | (host CPU, used for orchestration, Qdrant queries, JATS parsing, BM25) |
| RAM | 64 GB system memory |
| Storage (Linux) | ~1.7 TB on `/dev/sdc`, of which ~870 GB available at snapshot time |
| Storage (Windows scratch) | ~3.7 TB on `C:`, of which ~1.2 TB available at snapshot time |
| Operating system | WSL2 Ubuntu 24.04 LTS on Windows 11 host |
| CUDA | 12.8+ (required by Blackwell sm_120) |
| Container runtime | Docker Desktop (Windows host), exposing containers to WSL2 |

**VRAM budget at full Phase 2 load** (per master plan §11.4):

| Component | VRAM |
|---|---|
| Qwen3-8B (FP16) | ~16 GB |
| vLLM KV cache + paged-attention scratch | ~8–12 GB |
| PubMedBERT (FP32, kept resident for query encoding) | ~440 MB |
| Qdrant queries (CPU-side) | 0 GB |
| **Peak** | **~25–28 GB** (fits 32 GB with headroom) |

**Disk budget at full build** (verified 2026-05-09 21:00):

| Filesystem | Required peak | Available | Slack |
|---|---|---|---|
| Linux (Qdrant + models) | ~516 GB | 870 GB | ~354 GB ✓ |
| Windows (XML + intermediates) | ~215 GB | 1.2 TB | ~985 GB ✓ |

---

## 5. Software stack and pinned versions

### 5.1 Python — pinned in `pyproject.toml`

Reuses the host's existing `/home/hana77/pytorch-env/` virtualenv (Python 3.12.3) instead of creating a project-local `.venv`. Rationale recorded in master plan §10: avoids re-downloading ~5 GB of cu128 nightly torch wheels into a duplicate venv. The `pyproject.toml` is the source of truth: every project-relevant dependency is pinned to the exact version actually installed in `pytorch-env`.

**Reproducibility contract:** `requires-python = ">=3.12,<3.13"`. To freeze a complete snapshot of the env, `pip freeze > requirements.lock.txt`.

| Category | Package | Version | Notes |
|---|---|---|---|
| Corpus parsing | `lxml` | 5.4.0 | Master plan deviation §10: replaces `xml.etree.ElementTree` (~10× faster) |
| HTTP | `requests` | 2.32.5 | NCBI E-utilities, GitHub releases |
| Progress | `tqdm` | 4.67.1 | All long-running scripts |
| Ontology | `pronto` | 2.7.3 | OBO file loading (HPO, MONDO, GO) |
| Ontology | `obonet` | 1.1.1 | (transitive convenience; not directly imported) |
| Graph | `networkx` | 3.5 | (transitive; pronto dependency) |
| Embedding | `torch` | 2.9.0.dev20250820+cu128 | **Required by RTX 5090** — master plan §10 deviation from cu124 |
| Embedding | `torchvision` | 0.24.0.dev20250820+cu128 | matched nightly |
| Embedding | `torchaudio` | 2.8.0.dev20250820+cu128 | matched nightly |
| Embedding | `sentence-transformers` | 4.1.0 | Wraps PubMedBERT with mean pooling + L2 norm |
| Embedding | `transformers` | 4.55.3 | Tokenizer + model loading |
| Embedding | `tokenizers` | 0.21.4 | (transformers dependency) |
| Vector DB | `qdrant-client` | 1.14.3 | Pin matches server v1.14.1 (master plan §10 reconciliation) |
| Sparse | `fastembed` | 0.8.0 | **Hard rule:** BM25 is `SparseTextEmbedding("Qdrant/bm25")` only |
| Phase 1B | `phenopackets` | 2.0.2.post5 | GA4GH phenopacket Python protobuf bindings |
| Data | `pandas` | 2.2.3 | TSV reading (HGNC, GO GAF, HPO associations) |
| Data | `pyarrow` | 19.0.1 | Parquet I/O for embedding shards |
| Utility | `python-dotenv` | 1.0.1 | `.env` loading |
| Utility | `joblib` | 1.5.1 | (currently transitive; reserved for embedding parallelism) |
| Utility | `psutil` | 7.0.0 | Future health checks |
| Phase 1A prod | `awscli` | 1.45.6 | Anonymous S3 sync via `--no-sign-request` |

### 5.2 Phase 2 dependencies (planned, not yet installed)

Per master plan §11:

| Category | Package | Notes |
|---|---|---|
| Agents | `langgraph` | State-graph orchestration |
| Agents | `langchain-core` | LangGraph dep |
| LLM serving | `vllm` | GPU inference; Ollama acceptable as dev fallback |
| API | `fastapi` | HTTP layer wrapping LangGraph |
| API | `uvicorn[standard]` | ASGI server |
| API | `sse-starlette` | Server-Sent Events for streaming agent state |
| API | `copilotkit` | Python SDK; AG-UI protocol contract |
| Frontend | (Node.js + npm) | Standalone npm project at `frontend/` — communicates with FastAPI over loopback HTTP+SSE |

### 5.3 Pinned ontologies and datasets (2026 releases)

The master plan v2.1 originally pinned 2024 versions; updated to current 2026 releases per master plan §10. SHA-256 of every file in `data/MANIFEST.tsv`.

| Resource | Pinned version | Source URL |
|---|---|---|
| Human Phenotype Ontology (`hp.obo`) | `v2026-02-16` | `https://github.com/obophenotype/human-phenotype-ontology/releases/download/v2026-02-16/hp.obo` |
| HPO `genes_to_phenotype.txt` | same release | same release |
| HPO `phenotype_to_genes.txt` | same release | same release |
| HPO `phenotype.hpoa` | same release | same release |
| Mondo Disease Ontology (`mondo.obo`) | `v2026-03-03` | `https://github.com/monarch-initiative/mondo/releases/download/v2026-03-03/mondo.obo` |
| Gene Ontology (`go.obo`) | `2026-03-25` | `http://release.geneontology.org/2026-03-25/ontology/go.obo` |
| GO human annotations (`goa_human.gaf.gz`) | `2026-03-25` | `http://release.geneontology.org/2026-03-25/annotations/goa_human.gaf.gz` |
| HGNC complete set | `2026-04-07` quarterly | `https://storage.googleapis.com/public-download-files/hgnc/archive/archive/quarterly/tsv/hgnc_complete_set_2026-04-07.txt` (master plan §10 deviation: GCS bucket replaces deprecated EBI FTP) |
| GA4GH Phenopacket-Store | `0.1.19` | `https://github.com/monarch-initiative/phenopacket-store/releases/download/0.1.19/all_phenopackets.zip` |
| PMC Open Access full corpus | latest | `s3://pmc-oa-opendata/` (anonymous, master plan §10 deviation: flat layout, no tier prefixes — see §11) |

### 5.4 Models

| Model | Version / source | Role |
|---|---|---|
| **PubMedBERT** | `NeuML/pubmedbert-base-embeddings` (HuggingFace) | 768-dim sentence embeddings for dense retrieval; mean-pooled, L2-normalized |
| **Qdrant BM25** | `Qdrant/bm25` (via `fastembed`) | Native Qdrant BM25; document side TF+IDF, query side TF only |
| **Qwen3-8B Instruct** (planned, not yet downloaded) | `Qwen/Qwen3-8B` (HuggingFace) | Local reasoning model for Phase 2 agents |

### 5.5 Infrastructure

| Component | Version | Notes |
|---|---|---|
| Qdrant server (Docker) | `qdrant/qdrant:v1.14.1` | Bumped from v1.12.4 in PR #5 to match `qdrant-client==1.14.3` |
| REST port | `:6533` (host) → `:6333` (container) | Alternate port — coexists with two other Qdrant containers on host |
| gRPC port | `:6534` (host) → `:6334` (container) | |
| Storage | `~/rare-disease-rag/qdrant_storage/` (bind mount) | Linux fs |
| Container name | `qdrant_geno_agent` | |

---

## 6. Phase 1A — corpus pipeline (implementation per script)

All scripts under `scripts/corpus/`, `scripts/embedding/`, and `scripts/indexing/`. Each is independently runnable; the orchestrator `scripts/demo/run_pipeline.sh` chains them all for the demo path.

### 6.1 §3.2/§3.3 — ontology and HGNC acquisition

Implemented inline (downloaded directly via `wget`) and verified by `scripts/ontology/12_verify_ontologies.py`. The verifier loads each OBO with pronto, asserts the embedded `data-version` matches the pin in `.env`, walks one parent edge on `HP:0001250` (Seizure), resolves four MONDO disease-category roots, and spot-checks `BRCA1`/`TP53`/`TTN` in the HGNC protein-coding subset.

Demo run output (~9 s on RTX 5090 host):
- HPO: 19,944 HP terms, version `2026-02-16` ✓
- MONDO: 30,538 terms, `2026-03-03` ✓; 4 category roots all resolve
- GO: 48,291 terms, `2026-03-25` ✓; 880,928 human GAF annotations across 38,816 gene symbols
- HGNC: 44,981 total entries, 19,296 protein-coding, BRCA1/TP53/TTN spot-check ✓

### 6.2 §3.1 / §7 step [5a] — PMC OA corpus download

**Two paths, both implemented:**

`scripts/corpus/01_demo_fetch_pmc.py` — Demo path. Uses NCBI E-utilities (`esearch.fcgi` + `efetch.fcgi`) over plain HTTPS to fetch ~100 stratified rare-disease open-access papers across the 4 MONDO categories that Phase 1B will use. ~95 s end-to-end including NCBI rate-limit (3 req/s).

`scripts/corpus/01_download_pmc_oa.sh` — Production path (PR #10). Anonymous AWS S3 sync filtered to `*.xml` only. Currently running. Bucket-layout deviation (master plan §10): the public `s3://pmc-oa-opendata/` is now flat — articles live at `s3://pmc-oa-opendata/PMC<id>.<version>/` with no `oa_comm/oa_noncomm/oa_other` tier prefixes (license tier lives only in each article's per-article JSON metadata file). NCBI HTTPS bulk fallback at `https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/` returned 404 on 2026-05-09 (deprecated earlier than the master plan's stated August 2026). Consequence: master plan §7's "tier-by-tier streaming" strategy is replaced by a single full-corpus XML-only sync. Total disk impact unchanged (~150 GB).

The script supports `--limit N` (sample mode) and `--dry-run` (preview).

### 6.3 §4 step 1 / §7 step [5b] — JATS XML parsing

`scripts/corpus/06_parse_jats_xml.py`. Uses `lxml` (master plan deviation §10: ~10× faster than the spec's `xml.etree.ElementTree` on millions of articles). Output schema (one JSON per line):

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

Section-type classification uses the `<sec sec-type="...">` attribute when present and falls back to a regex on the heading text otherwise (regex covers `introduction|methods|results|case|discussion|conclusion|other`).

Demo run: 100 / 100 parsed in <1 s, 559 sections, 3.4 M characters total. Section distribution: results 462, other 346, methods 315, discussion 255, introduction 170, conclusion 57, case 20.

### 6.4 §4 step 2 / §7 step [5c] — genetics / rare-disease filter

`scripts/corpus/07_filter_corpus.py`. Retains an article if any of:

1. **MeSH:** any term in `mesh_terms` is in the genetics whitelist (`{genetics, genomics, mutation, hereditary, mendelian, ...}` plus specific rare-disease names).
2. **Keyword:** any `<kwd>` is in the same whitelist.
3. **Title/abstract regex:** OR of seven patterns covering `(genetic|genomic|hereditary|mendelian|inborn)`, `(mutation|variant|deletion|duplication|insertion|polymorphism)`, `(HPO|OMIM|Orphanet|GeneReviews|MONDO|HGNC|ClinVar)`, `phenotypic`, `(rare|orphan) (disease|disorder|condition|syndrome)`, `(exome|genome|RNA-seq|transcriptome) sequencing`, `(autosomal (dominant|recessive)|X-linked)`.

Master plan v2.1 fix #6: hard-asserts retention is in `[100,000, 600,000]` for the production run (gated behind `--strict`; off by default for the demo).

Demo run: 89 / 100 retained (89 %). Eleven articles rejected because the selected disease-MeSH paper happened to focus on a non-genetic complication and used no genetics vocabulary.

### 6.5 §4 step 3 / §7 step [5d] — section-aware UUID5 chunking

`scripts/corpus/08_section_aware_chunking.py`. Chunks never span section boundaries. Within a section, the PubMedBERT tokenizer (`NeuML/pubmedbert-base-embeddings`) produces token IDs; the chunker emits 512-token windows with 50-token overlap.

Each chunk receives a deterministic ID (master plan v2.1 fix #2):

```python
CHUNK_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")  # pinned, DO NOT CHANGE
text_digest = hashlib.blake2b(chunk_text.encode("utf-8"), digest_size=16).hexdigest()
chunk_id = str(uuid.uuid5(
    CHUNK_NAMESPACE,
    f"{pmcid}|{section_type}|{chunk_index}|{text_digest}"
))
```

This makes Qdrant upserts idempotent — re-running the entire pipeline produces the same set of point IDs and the same set of payloads. It also makes the manifest hash byte-stable across machines.

Demo run: 89 articles → 1,625 chunks (avg 18.3/article). 21 sections skipped as too short (< 50 chars).

### 6.6 §4 step 4 / §7 step [5e] — PubMedBERT embedding

`scripts/embedding/09_generate_embeddings.py`. Loads `NeuML/pubmedbert-base-embeddings` via `sentence-transformers`, encodes all chunks in batches of 32 with mean pooling and L2 normalization for cosine similarity. Output is a single zstd-compressed parquet shard with a binary `embedding` column (np.float32 bytes).

Demo run: 1,625 chunks encoded in **4.7 s on RTX 5090**, sustained throughput **351 chunks/s**. Output parquet is 5.5 MB. For the production 3-million-chunk corpus this projects to ~140 minutes of pure GPU encoding.

### 6.7 §4 step 5 / §7 steps [4] + [5f] — Qdrant collection + upload

`scripts/indexing/10_create_qdrant_index.py`. Collection-only by default (creates schema and exits — what step [4] requires). With `--upload`, also reads parquet shards from `--embedding-dir` and upserts in batches.

For each parquet row, the script:

1. Reconstructs the dense vector from the binary column (`np.frombuffer(emb, dtype=np.float32).tolist()`).
2. Computes the BM25 sparse vector using `SparseTextEmbedding("Qdrant/bm25").embed(texts)` — the **document-side** call producing TF + IDF (master plan §4 step 5 line 1107). The query side uses `.query_embed()` (TF only) — the IDF-weighted index is server-side via `Modifier.IDF`.
3. Builds a `PointStruct` with both vectors, `chunk_id` as the point ID (idempotent), and the full payload.
4. Upserts in batches of 128.

Demo run: 1,625 points uploaded in ~1.5 s. Final collection state: status `green`, dense + BM25 + on_disk_payload.

### 6.8 §4 step 6 / §7 step [6] — index validation

`scripts/indexing/11_validate_index.py`. Twelve rare-disease probe queries run in three modes each:

| Mode | API | Notes |
|---|---|---|
| Dense | `client.query_points(query=vec, using="dense")` | PubMedBERT-encoded query |
| BM25 | `client.query_points(query=SparseVector(...), using="bm25")` | `SparseTextEmbedding.query_embed()` (TF only) |
| Hybrid | `prefetch=[dense, bm25]; query=FusionQuery(Fusion.RRF)` | Reciprocal rank fusion at query time |

Probe set covers all 4 disease categories: Huntington / CMT / Rett / PKU / Fabry / Niemann-Pick / agammaglobulinemia / CVID / SCID / Marfan / Noonan / DiGeorge.

Selected demo results (full output: `reports/run_logs/11_validate.log`):
- `"common variable immunodeficiency B cell"` → top dense hit `PMC11949678` introduction: *"Common variable immunodeficiency (CVID) is a primary B-cell immunodeficiency disorder characterized by marked hypogammaglobulinemia..."* (cosine 0.741)
- `"DiGeorge syndrome 22q11 deletion thymus"` → top hybrid hit `PMC5916974` introduction directly describing 22q11 microdeletions (RRF score 1.000)
- `"phenylketonuria PAH enzyme deficiency"` → top hybrid hit `PMC2885380` introduction citing OMIM 221600 (RRF score 0.833)
- `"Marfan syndrome FBN1 fibrillin aortic"` → top hybrid hit `PMC7735621` mentioning Marfan/Noonan/DiGeorge mendelian-syndromes paper

All 12 probes return relevant top-1 chunks across all three modes.

### 6.9 Orchestration and observability

`scripts/demo/run_pipeline.sh` chains all 7 stages with per-step logging to `reports/run_logs/`. `scripts/demo/collect_stats.py` parses the logs into `reports/pipeline_stats.json`. `scripts/demo/make_visualizations.py` renders five matplotlib charts to `reports/images/`.

Demo run wall-clock breakdown (live from `reports/pipeline_stats.json`):

| Stage | Wall-clock |
|---|---|
| Fetch (NCBI esearch+efetch) | ~95 s first run, ~2 s cached |
| Parse JATS | <1 s |
| Filter | <1 s |
| Chunk | ~1.5 s |
| Embed | 4.7 s |
| Upload | ~1.5 s |
| Validate | ~5 s |
| **Total** | **~44 s** end-to-end |

---

## 7. Phase 1B — test-case curation (implementation per script)

All scripts under `scripts/cases/`. As of this snapshot, **5 of 9 scripts are implemented**. Steps [13]–[16] remain.

### 7.1 §3.4 / §7 step [8] — Phenopacket-Store download

`scripts/cases/04_download_phenopacket_store.sh` (PR #11). Downloads pinned `v0.1.19` release from GitHub releases. Idempotent (skips download if zip exists; skips unzip if extracted). Sanity-checks expected count (~6,668 phenopackets per master plan §3.4).

Live run: 11.6 MB zip → 6,668 JSONs in `data/phenopackets/v0.1.19/` (sha256 `5e7b48c0...` recorded in MANIFEST.tsv).

### 7.2 §6 step 1 / §7 step [9] — phenopacket ingest

`scripts/cases/13_load_phenopackets.py` (PR #12). Walks `data/phenopackets/v0.1.19/` recursively, parses each JSON, normalizes into a single JSONL with the four field families Phase 1B steps 2–6 need. Output schema:

```json
{
  "case_id":         "<cohort>:<file_stem>",
  "source_path":     "data/phenopackets/v0.1.19/.../foo.json",
  "subject_id":      "Patient 3",
  "hpo_terms":       ["HP:0041056", "HP:0001321", ...],     // observed only, deduplicated
  "diseases":        [{"id": "OMIM:154700", "label": "Marfan syndrome"}],
  "interpretations": [{"gene_symbol": "FBN1", "hgnc_id": "HGNC:3603",
                       "variant": "...", "ascertained": true}]
}
```

Live run on full Phenopacket-Store v0.1.19:
- 6,668 / 6,668 records written (0 parse errors)
- 97.9 % have ≥ 1 HPO term (avg 8.1 HPO terms / case — well above the methodology's `MIN_HPO_TERMS=3`)
- 100 % have ≥ 1 disease
- 99.0 % have ≥ 1 genomic interpretation (avg 1.07 interpretations / case — mostly single-gene Mendelian, matches the inclusion rule)
- Throughput: ~3,941 records / s

### 7.3 §6 step 2 / §7 step [10] — inclusion / exclusion filter

`scripts/cases/14_apply_inclusion_exclusion.py` (PR #13). Per methodology §4.2.1.

**Inclusion (all required):**
- ≥ `MIN_HPO_TERMS` (default 3) observed HPO terms
- Exactly 1 ascertained causal gene across all genomic interpretations

**Exclusion (any disqualifies):**
- Disease MONDO term is descendant of `MONDO:0019042` (chromosomal disorder)
- Disease MONDO term is descendant of `MONDO:0044970` (mitochondrial disease)

Implementation: loads MONDO with pronto, computes 1,247 descendants of the two exclusion roots, builds a 139,514-entry OMIM/Orphanet → MONDO xref index, then filters in O(1) per case. Each retained record is augmented with `causal_gene` and `mondo_ids` fields.

Live run: 3,878 / 6,668 eligible (58.2 %). Drop reasons: 1,051 too few HPO terms, 1,670 chromosomal/mito, 69 no single-gene interpretation. Throughput ~171k cases / s after MONDO load.

### 7.4 §6 step 3 / §7 step [11] — MONDO disease categorization

`scripts/cases/15_categorize_by_mondo.py` (PR #14). Bins each eligible case into one of four disease categories.

**Category roots:**
- **neurological**: `MONDO:0005071` (nervous system disorder)
- **metabolic**: `MONDO:0005066` (metabolic disease)
- **immunological**: `MONDO:0005046` (immune system disorder)
- **developmental**: `MONDO:0021147` (inborn genetic disease) + `MONDO:0019118` (developmental and epileptic encephalopathy)

**Priority resolution** (master plan §10): cases matching multiple categories are assigned to the FIRST in priority order — neurological > metabolic > immunological > developmental. The complete `matched=[...]` list is recorded per case in `category_resolution` for transparent audit.

Live run: 2,971 / 3,878 categorized (76.6 %). Distribution: neurological 2,231 / metabolic 350 / immunological 85 / developmental 305. 512 cases matched multiple categories (largest overlap: neurological+developmental, 227 cases).

### 7.5 §6 step 4 / §7 step [12] — stratified random sampling

`scripts/cases/16_stratified_sample.py` (PR #15). Equal allocation across 4 categories, capped by availability, with `random.Random(seed=42)` for reproducibility.

Algorithm:
1. Load + group by category, sort within each by `case_id` (deterministic ordering before sampling).
2. `ceil(target/4) = 19` per category.
3. `rng.sample()` (sampling without replacement).
4. If overshoot, shuffle + truncate to exact target.
5. Output sorted by (category, case_id) for clean review.

Live run: exactly 75 cases drawn — distribution **18 neuro / 19 metabolic / 19 immuno / 19 developmental**. Fully reproducible: same seed produces identical 75-case set on any host.

### 7.6 §6 steps 5–8 / §7 steps [13]–[16] — pending

| Step | Script | Status | Blocker |
|---|---|---|---|
| [13] | `17_validate_pmc_coverage.py` | ❌ Not started | **Hard-blocked on production Qdrant index** (queries each case's causal gene and requires ≥ 5 PMC articles) |
| [14] | `18_build_candidate_lists.py` | ❌ Not started | None — can run on current 75-case sample with HGNC distractors |
| [15] | `19_finalize_test_cases.py` | ❌ Not started | Pure aggregation |
| [16] | `20_validate_test_cases.py` | ❌ Not started | Acceptance gate |

Step [14] will draw 49 HGNC protein-coding distractors per case, with a per-case derived seed `blake2b(global_seed | case_id)` so individual cases can be regenerated in isolation while remaining fully deterministic.

---

## 8. Demo run — end-to-end evidence

The pipeline was executed end-to-end on a 100-article rare-disease sample on 2026-05-09 (commit `c553d14`). Artifacts:

- `reports/pipeline_stats.json` — structured stats
- `reports/run_logs/*.log` — full per-step stdout
- `reports/images/*.png` — five matplotlib charts
- `reports/visual_report.html` — original visual demo report
- `reports/technical_report.md` — original technical demo report

Quantitative results:

| Stage | Output | Rate |
|---|---|---|
| Fetch | 100 PMC articles, 12.8 MB | NCBI rate-limited (3 req/s), ~95 s |
| Parse | 559 sections, 3.4 M chars | <1 s |
| Filter | 89 / 100 retained | <1 s |
| Chunk | 1,625 chunks (avg 18.3/article) | <2 s |
| Embed | 1,625 × 768d float32 | **351 chunks/s on RTX 5090** |
| Upload | 1,625 Qdrant points | <2 s |
| Validate | 12 probes × 3 modes | <5 s |

All 12 probes returned relevant top-1 hits across dense / BM25 / hybrid modes (sample shown in §6.8).

---

## 9. Phase 2 — agentic UI layer (specification)

Detailed in master plan §11 (added 2026-05-09). Three sub-phases.

### 9.1 Phase 2a — LangGraph state graph (~1 week engineering)

**Reasoning model:** Qwen3-8B Instruct via vLLM, served on the same RTX 5090. VRAM budget per master plan §11.4 (see §4 above). Fallback: any open-weights ~8B instruction model (Llama-3.1-8B-Instruct, Mistral-7B-Instruct-v0.3). vLLM mandatory for §11.5 evaluation runs (latency budget); Ollama acceptable for development iteration.

**Agent roster and tool catalog:**

| Agent | Role | Tools |
|---|---|---|
| **Query Planner** | HPO expansion via `pronto`; MeSH-style query construction | `hpo_expand(hpo_id, distance=2)`, `mesh_lookup(symbol)` |
| **Retriever** | Per (HPO subset, candidate gene), Qdrant hybrid search with payload filters | `qdrant_hybrid_search(query, gene_filter, top_k)` |
| **Critic** | Grade chunks for: (a) gene mention validity (HGNC alias check), (b) phenotype-gene association strength (1-5 ordinal), (c) evidence type | `hgnc_validate(symbol)`, `relevance_grade(chunk, hpo_terms, gene)` |
| **Synthesizer** | Aggregate Critic grades into per-gene confidence; produce re-ranked candidate list with cited supporting passages | (none — pure aggregation) |

**State schema** (master plan §11.1):

```python
@dataclass
class AgentState:
    case_id: str
    hpo_terms: list[str]
    candidate_genes: list[str]               # 50 from Phase 1B (1 causal + 49 distractors)
    expanded_hpo: list[str]
    mesh_queries: list[str]
    retrieved: dict[str, list[RetrievedChunk]]    # gene -> chunks
    grades: dict[str, list[CriticGrade]]
    ranked: list[GeneCandidate]
    iteration: int                            # for self-correction loop
    max_iterations: int = 3
```

**Graph topology:** `query_planner → retriever → critic → (conditional: re-enter retriever if many low-confidence grades remain and budget allows, else synthesizer) → END`. The conditional re-entry is the **self-correction loop** that single-pass RAG architectures cannot reproduce — this is the empirical contribution of the multi-agent design (cell C vs cell A in the §11.5 factorial).

### 9.2 Phase 2b — FastAPI + copilotkit-sdk-python (~2 days engineering)

`src/api/main.py` wraps the compiled LangGraph in a FastAPI app speaking the AG-UI protocol via `copilotkit-sdk-python`.

```python
from copilotkit import CopilotKitSDK, LangGraphAgent
sdk = CopilotKitSDK(agents=[LangGraphAgent(name="prioritizer", graph=build_graph())])
sdk.attach(app, path="/api/agent")
```

Endpoints auto-mounted:
- `POST /api/agent/run` — synchronous one-shot, returns final `GeneCandidate[]`
- `GET /api/agent/stream` — SSE stream of `AgentState` updates per node
- `GET /api/health` — liveness probe

### 9.3 Phase 2c — CopilotKit React UI (~3–5 days engineering)

Sourced from the user's fork [`github.com/Jangulo7/agent_UI`](https://github.com/Jangulo7/agent_UI) (upstream `CopilotKit/CopilotKit`).

**Adoption decision (master plan §11.3):** standalone clone, NOT git submodule. The CopilotKit framework is consumed via `npm install @copilotkit/react-core` like any other npm dependency. `frontend/` in this repo contains only the geno_agent-specific React components.

**Custom components:**

| Component | Purpose |
|---|---|
| `<HPOPicker>` | Multi-select with autocomplete fed by local `hp.obo`; supports synonym matching |
| `<CandidateGeneList>` | Editable list of HGNC symbols (paste-friendly; validated against HGNC) |
| `<AgentTracePanel>` | Live timeline of LangGraph state transitions (Query Planner → Retriever → Critic [→ Retriever]\* → Synthesizer) |
| `<GeneCandidateCard>` | Per-gene tile in ranked output: symbol, score, supporting passage carousel, citation links to PMC |
| `<CitationHover>` | Hover-card showing the exact retrieved chunk with section type and PMC ID |

### 9.4 Phase 2 evaluation — 2×2+1 factorial (~3 days engineering)

| | Dense-only | Hybrid (dense + BM25 + RRF) |
|---|---|---|
| **Single-agent** (one-shot Synthesizer) | Cell A — control | Cell B — retrieval contribution |
| **Multi-agent** (4 agents w/ self-correction) | Cell C — architecture contribution | Cell D — full system |

**Cell E:** [Exomiser](https://exomiser.readthedocs.io) — phenotype-driven baseline (no literature evidence); the established gold standard.

For each Phase 1B case (75 cases), all 5 cells produce a ranked list of the 50 candidate genes. Metrics: top-1 / top-5 / top-10 accuracy, MRR, NDCG@10. Statistical significance via paired bootstrap over cases (1000 resamples, 95 % CI). Output: LaTeX-ready results table per metric with per-cell CI.

### 9.5 Phase 2 acceptance criteria

Phase 2 is "done" iff ALL of:

- [ ] `src/agents/graph.py` builds a 4-node LangGraph that produces `GeneCandidate[]` from `(hpo_terms, candidate_genes)`.
- [ ] `tests/agents/` has unit tests for each agent node with mocked retrieval.
- [ ] Qwen3-8B (or fallback) loads in vLLM and serves agents at ≥ 5 tok/s under multi-agent load on the RTX 5090.
- [ ] `src/api/main.py` exposes the graph via `/api/agent/*` and passes a `curl`-driven smoke test on one Phase 1B case.
- [ ] CopilotKit React frontend runs at `http://localhost:3000` and prioritizes a Phase 1B case end-to-end.
- [ ] Evaluation harness (`scripts/eval/`) produces the 2×2+1 results table with Phase 1B cases and statistical CIs.
- [ ] `data/MANIFEST.tsv` updated with `models/` section listing SHA-256 of Qwen3-8B weights and the evaluation seed.

---

## 10. Reproducibility design

| Surface | Mechanism |
|---|---|
| Random seeds | `RANDOM_SEED=42`, `PYTHONHASHSEED=42` in `.env`. `scripts/utils/seed.py:apply_seeds()` is imported at every entrypoint and sets `random`, `numpy`, `torch.cuda` seeds, `torch.use_deterministic_algorithms(warn_only=True)`, cuDNN deterministic flags. |
| Chunk IDs | UUID5 over `(pmcid, section_type, chunk_index, blake2b(text))` with the pinned namespace `6f9619ff-8b86-d011-b42d-00cf4fc964ff` — DO NOT CHANGE. |
| Cross-process hashing | `scripts/utils/seed.py:stable_hash()` uses BLAKE2b — Python's built-in `hash()` is salted per-process, unsafe for byte-stable artifacts. |
| Per-case derived seeds | Phase 1B distractor sampling uses `blake2b(global_seed | case_id)` so individual cases can be regenerated in isolation. |
| Stratified case sample | `random.Random(42)` ensures the same 75 case_ids appear in the same order across runs and machines. |
| Ontology versions | All 4 pinned by exact dated release. SHA-256 of every file in `data/MANIFEST.tsv`. |
| Embedding model | `NeuML/pubmedbert-base-embeddings` — the canonical PubMedBERT sentence embedding model. |
| BM25 model | `Qdrant/bm25` via `fastembed.SparseTextEmbedding`. Hard rule: no hash-of-whitespace fallback. |
| Qdrant server | `qdrant/qdrant:v1.14.1` pinned in `docker-compose.yml`. |
| Python deps | All 21 deps in `pyproject.toml` pinned to exact `==X.Y.Z` matching what's installed in `pytorch-env`. |
| Phase 2 LLM | (Future) Qwen3-8B weights SHA-256 to be appended to `MANIFEST.tsv`. |

The verifier `scripts/ontology/12_verify_ontologies.py` confirms the data-version stamp embedded in each downloaded OBO file matches the pin, on every run.

---

## 11. Master plan deviations (full §10)

The full deviations log is in `MASTER_PROJECT_v2.1.md` §10. Reproduced here for self-containment.

| # | Methodology spec | Implementation | Rationale |
|---|---|---|---|
| 1 | §4.2.2 — `xml.etree.ElementTree` | `lxml` | ~10× faster on 4M articles, more namespace-robust |
| 2 | §4.2.2 — sparse BM25 (no library specified) | `fastembed.SparseTextEmbedding("Qdrant/bm25")` | Canonical Qdrant-native BM25; explicitly named for transparency |
| 3 | §4.2.1 — "50–100 cases" (open range) | Default `SAMPLE_TARGET_SIZE=75` | Midpoint; configurable in `.env` |
| 4 | §4.2.1 — "stratified random sampling" | Equal allocation per category, capped by availability, with priority resolution for multi-category MONDO mappings | Resolves the implicit ambiguity of multi-category mappings deterministically; recorded per-case in `category_resolution` |
| 5 | §4.2.1 — "approved by HGNC" | Snapshot HGNC at `2026-04-07` | Required for byte-reproducibility per §4.1.3 |
| 6 | §3 / §4.2.3 — pinned 2024 ontology releases | Updated to 2026 releases (HPO `v2026-02-16`, MONDO `v2026-03-03`, GO `2026-03-25`, HGNC `2026-04-07`) | Project executed in 2026; 2024 versions out of date |
| 7 | HGNC EBI FTP URL | Switched to GCS bucket `public-download-files` | EBI FTP archive paths now 404 |
| 8 | §2 line 176 — `python3.11 -m venv .venv` | Use system `python3.12.3`; no project-local `.venv` | Python 3.11 not installed; 3.12 fully compatible with every pinned dep |
| 9 | §2 line 189 — torch `cu124` | Pinned `torch==2.9.0.dev20250820+cu128` | RTX 5090 (Blackwell sm_120) requires CUDA 12.8+; cu124 fails at first kernel launch |
| 10 | §2 — fresh project-local `.venv` | Reuse existing `/home/hana77/pytorch-env/` | Avoids ~5 GB redundant cu128 torch download |
| 11 | §2.1 — `qdrant/qdrant:v1.12.4` | Bumped to `qdrant/qdrant:v1.14.1` | Aligns with `qdrant-client==1.14.3` in pytorch-env, eliminates UserWarning |
| 12 | §3.1 — `aws s3 sync` for PMC OA (demo) | NCBI esearch + efetch demo path | Demo path; production AWS sync via separate script |
| 13 | §3.1 — bucket layout `s3://pmc-oa-opendata/{oa_comm,oa_noncomm,oa_other}/xml/all/` | Bucket is now flat: `s3://pmc-oa-opendata/PMC<id>.<version>/<files>` with no tier prefixes (license tier in per-article JSON only). NCBI HTTPS bulk fallback also returned 404 on 2026-05-09. | Single full-corpus XML-only sync via `--exclude '*' --include '*/*.xml'`. License-tier classification done downstream via per-article JSON. Total disk impact unchanged (~150 GB). |
| 14 | §0 — local LLM unspecified | Qwen3-8B Instruct via vLLM | 8B fits 32 GB VRAM with KV-cache headroom; vLLM ≥ 5 tok/s required for evaluation |
| 15 | §0 — UI unspecified | CopilotKit React (sourced from `Jangulo7/agent_UI` fork) | Co-author of AG-UI protocol with LangChain; first-class LangGraph integration; MIT-licensed self-hostable |
| 16 | §2 — Python only | Adds Node.js + npm under `frontend/` | CopilotKit is React-based; standalone npm project |
| 17 | §0 — agent orchestration unspecified | LangGraph state graph with conditional self-correction edges | Native to CopilotKit AG-UI streaming; conditional re-entry is the agentic capability single-pass RAG cannot reproduce |

---

## 12. Configuration files

### 12.1 `pyproject.toml` (current)

See file at repository root. All 21 deps pinned to exact `==X.Y.Z` matching `/home/hana77/pytorch-env/`. `requires-python = ">=3.12,<3.13"`.

### 12.2 `.env.example` (committed template)

```bash
# Reproducibility
PYTHONHASHSEED=
RANDOM_SEED=

# Qdrant (this project's instance — NOT the pubmed one on 6333)
QDRANT_HOST=
QDRANT_PORT=
QDRANT_GRPC_PORT=
QDRANT_COLLECTION=

# Paths
PROJECT_ROOT=
QDRANT_STORAGE=
PMC_WORKSPACE=
ONTOLOGY_DIR=$PROJECT_ROOT/data/ontologies
HGNC_DIR=$PROJECT_ROOT/data/hgnc
PHENOPACKET_DIR=$PROJECT_ROOT/data/phenopackets
TEST_CASES_DIR=$PROJECT_ROOT/data/test_cases

# Ontology / dataset versions (2026 releases — see master plan §10)
HPO_VERSION=
MONDO_VERSION=
GO_VERSION=
HGNC_SNAPSHOT=
PHENOPACKET_STORE_VERSION=0.1.19
```

### 12.3 `docker-compose.yml`

```yaml
services:
  qdrant_geno_agent:
    image: qdrant/qdrant:v1.14.1
    container_name: qdrant_geno_agent
    restart: unless-stopped
    ports:
      - "6533:6333"   # REST (host:container)
      - "6534:6334"   # gRPC
    volumes:
      - ${HOME}/rare-disease-rag/qdrant_storage:/qdrant/storage
    environment:
      - QDRANT__SERVICE__HTTP_PORT=6333
      - QDRANT__SERVICE__GRPC_PORT=6334
      - QDRANT__STORAGE__ON_DISK_PAYLOAD=true
```

---

## 13. Data acquisition manifest

`data/MANIFEST.tsv` records SHA-256 of every reproducibility-critical input. Current contents (9 entries; PMC OA appended after production build completes):

| Path | SHA-256 (prefix) | Bytes | Acquired at (UTC) |
|---|---|---|---|
| `data/Human_Phenotype_Ontology/hp.obo` | `8d6c2379...` | 10,703,106 | 2026-05-09T11:05:23Z |
| `data/MONDO_Disease_Ontology/mondo.obo` | `9be712b2...` | 51,259,763 | 2026-05-09T11:05:23Z |
| `data/Gene_Ontology/go.obo` | `58a3432d...` | 36,555,702 | 2026-05-09T11:05:23Z |
| `data/HGNC/hgnc_complete_set_2026-04-07.txt` | `1182d184...` | 17,031,001 | 2026-05-09T12:57:03Z |
| `data/Human_Phenotype_Ontology/genes_to_phenotype.txt` | `25d3e5a4...` | 20,533,481 | 2026-05-09T13:42:47Z |
| `data/Human_Phenotype_Ontology/phenotype_to_genes.txt` | `a0b501b8...` | 65,852,754 | 2026-05-09T13:42:47Z |
| `data/Human_Phenotype_Ontology/phenotype.hpoa` | `5d7aedee...` | 35,261,380 | 2026-05-09T13:42:47Z |
| `data/Gene_Ontology/goa_human.gaf.gz` | `17b3efdd...` | 14,775,581 | 2026-05-09T13:42:47Z |
| `data/phenopackets/all_phenopackets.zip` | `5e7b48c0...` | 11,620,861 | 2026-05-09T18:40:54Z |

Total tracked: ~257 MB (excluding PMC OA which is gitignored regardless).

---

## 14. Operational runbook

### 14.1 First-time setup on a fresh machine

```bash
# 1. Clone
git clone git@github.com:Jangulo7/geno_agent.git
cd geno_agent

# 2. Python env (reuses existing pytorch-env with cu128 nightly torch — see master plan §10)
source /home/hana77/pytorch-env/bin/activate
# Verify: python --version  → Python 3.12.3
# Verify: torch.__version__  → 2.9.0.dev20250820+cu128

# 3. Install missing deps (pip will skip already-installed ones)
pip install -r <(python -c "
import tomllib; d = tomllib.load(open('pyproject.toml', 'rb'))
print('\n'.join(d['project']['dependencies']))")

# 4. Bring up Qdrant (alternate ports 6533/6534 to avoid collision with other Qdrant containers on host)
docker compose up -d
curl http://localhost:6533/healthz       # expect: healthz check passed

# 5. Configure .env (copy from template)
cp .env.example .env
# Edit .env — set PROJECT_ROOT, paths, versions

# 6. Verify ontologies load + match pins
python scripts/ontology/12_verify_ontologies.py

# 7. Create empty Qdrant collection
python scripts/indexing/10_create_qdrant_index.py
```

### 14.2 Run the demo end-to-end

```bash
bash scripts/demo/run_pipeline.sh                       # ~44 s
python scripts/demo/collect_stats.py                    # → reports/pipeline_stats.json
python scripts/demo/make_visualizations.py              # → reports/images/*.png
```

### 14.3 Run the production corpus build

```bash
# Inside tmux/screen so disconnects don't kill it:
tmux new -s pmc-sync
PATH=/home/hana77/pytorch-env/bin:$PATH \
    bash scripts/corpus/01_download_pmc_oa.sh           # ~3-8 hours
# Ctrl+b then d to detach

# After completion, run the rest of the pipeline:
python scripts/corpus/06_parse_jats_xml.py --input-dir /mnt/c/pmc_workspace/xml_raw/all/
python scripts/corpus/07_filter_corpus.py --strict      # hard-asserts retention in [100K, 600K]
python scripts/corpus/08_section_aware_chunking.py
python scripts/embedding/09_generate_embeddings.py      # ~24-48 GPU hours
python scripts/indexing/10_create_qdrant_index.py --upload
python scripts/indexing/11_validate_index.py
```

### 14.4 Run Phase 1B test-case curation

```bash
bash scripts/cases/04_download_phenopacket_store.sh
python scripts/cases/13_load_phenopackets.py
python scripts/cases/14_apply_inclusion_exclusion.py
python scripts/cases/15_categorize_by_mondo.py
python scripts/cases/16_stratified_sample.py
# Future:
# python scripts/cases/17_validate_pmc_coverage.py     # requires production Qdrant
# python scripts/cases/18_build_candidate_lists.py
# python scripts/cases/19_finalize_test_cases.py
# python scripts/cases/20_validate_test_cases.py
```

### 14.5 Monitor the running production build

```bash
tail -f logs/download_pmc_oa.log                        # live log
watch -n 60 'du -sh /mnt/c/pmc_workspace/xml_raw/all/'  # disk growth
pgrep -af 01_download_pmc_oa                            # process check
```

### 14.6 Stop the production build (graceful)

```bash
pkill -f 01_download_pmc_oa.sh                          # S3 sync is resumable
```

### 14.7 Recovery from interrupted runs

- **`aws s3 sync`** is idempotent — rerun picks up where it left off.
- **Chunking** is idempotent at the chunk_id level — rerun upserts the same UUIDs.
- **Embedding** is per-shard — rerun starts from the next unfinished parquet shard.
- **Qdrant** upserts are idempotent on `chunk_id`.

### 14.8 Backup the Qdrant index

The production index will be ~300–500 GB. Before any destructive operation:

```bash
# Cold backup
docker compose down
tar -czf ~/rare-disease-rag-backup-$(date +%Y%m%d).tar.gz ~/rare-disease-rag/qdrant_storage/
docker compose up -d
```

---

## 15. Limitations, risks, and next steps

### 15.1 What this work does NOT (yet) demonstrate

- **No quantitative results.** Phase 2 evaluation harness is unbuilt; no MRR / NDCG / Top-K numbers vs Exomiser yet.
- **No clinician evaluation.** Even after the quantitative harness runs, clinical utility judgments by genetics professionals are out of scope of this thesis.
- **Not validated for real clinical use.** This is research software, not a CE-marked device.

### 15.2 Known risks (with mitigations)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| S3 sync fails mid-download (network, host sleep) | Medium | High | Running under `nohup`; sync is resumable; consider `tmux` for any restart |
| Filter retention falls outside [100K, 600K] band | Low | High | Run without `--strict` first; inspect retention before chaining 5d-5f |
| Embedding OOM on long inputs | Low | Medium | Tokenizer enforces 512-token chunks at chunking time; embedder receives uniform-length tensors |
| Qdrant index corruption from forced kill | Low | High | Always `docker compose down`, never `kill -9` |
| `pytorch-env` torch nightly drift | Low | Medium | `pyproject.toml` records exact versions; `pip install -r requirements.lock.txt` to re-pin |
| Disk fills mid-build | Very low (verified 870 GB Linux + 1.2 TB Windows free) | High | `du -sh` monitoring; intermediates can be deleted between stages |
| Phenopacket-store v0.1.19 release URL changes | Low | Medium | Pinned URL recorded in script; SHA-256 in MANIFEST as integrity check |
| Qwen3-8B model URL changes | Low | Medium | (Future) SHA-256 in MANIFEST after download |

### 15.3 Open follow-ups (not in critical path)

- Add Qdrant payload index on `mesh_terms` (currently unindexed; needed for Critic agent's MeSH-filtered queries).
- Snapshot `requirements.lock.txt` via `pip freeze` as a definitive env fingerprint.
- After Phase 2c lands, add a `tests/e2e/` Playwright suite that drives the CopilotKit UI from a Phase 1B case to a ranked output.

### 15.4 Recommended next actions in priority order

| P | Action | Track | Time | Why now |
|---|---|---|---|---|
| **P0** | Wait for production corpus to populate (passive, machine) | A | ~5–9 days | Unblocks B6 and Phase 2 evaluation |
| **P1** | Implement B7 (`18_build_candidate_lists.py`) | B | ~1 hour | No Qdrant dep; runs on current 75-case sample |
| **P1** | Implement B8 (`19_finalize_test_cases.py`) | B | ~30 min | Pure aggregation |
| **P1** | Implement B9 (`20_validate_test_cases.py`) — acceptance gate | B | ~30 min | Final Phase 1B step before Phase 2 |
| P2 | Scaffold Phase 2a `src/agents/state.py` + tools | C | ~half day | Develop against demo collection while corpus builds |
| P2 | Download Qwen3-8B weights to `~/rare-disease-rag/models/` | C | ~15 min | Required for any agent prompt iteration |
| P2 | `pip install vllm` into pytorch-env | C | ~5 min | LLM serving |

---

## 16. Repository layout

```
geno_agent/
├── MASTER_PROJECT_v2.1.md            # Authoritative project spec (Phases 1A, 1B, 2)
├── CLAUDE.md                          # Project rules + memory pointers
├── README.md                          # Public-facing overview
├── pyproject.toml                     # 21 pinned Python dependencies
├── docker-compose.yml                 # Qdrant v1.14.1 on :6533/:6534
├── .env.example                       # Configuration template
├── data/
│   ├── MANIFEST.tsv                   # SHA-256 of every reproducibility input
│   ├── Human_Phenotype_Ontology/      # v2026-02-16
│   ├── MONDO_Disease_Ontology/        # v2026-03-03
│   ├── Gene_Ontology/                 # 2026-03-25
│   ├── HGNC/                          # 2026-04-07
│   ├── ontologies/                    # path-alias symlinks (master-plan layout)
│   ├── hgnc                           # symlink → HGNC/
│   ├── phenopackets/                  # v0.1.19 (gitignored)
│   ├── test_cases/                    # generated JSONL artifacts (gitignored)
│   ├── intermediate/                  # gitignored
│   └── pmc_oa/                        # gitignored
├── scripts/
│   ├── utils/seed.py                  # apply_seeds(), stable_hash()
│   ├── ontology/12_verify_ontologies.py
│   ├── corpus/
│   │   ├── 01_demo_fetch_pmc.py       # NCBI E-utilities demo (PR #6)
│   │   ├── 01_download_pmc_oa.sh      # Production AWS S3 sync (PR #10)
│   │   ├── 06_parse_jats_xml.py
│   │   ├── 07_filter_corpus.py
│   │   └── 08_section_aware_chunking.py
│   ├── embedding/09_generate_embeddings.py
│   ├── indexing/
│   │   ├── 10_create_qdrant_index.py  # collection-only by default; --upload for indexing
│   │   └── 11_validate_index.py
│   ├── cases/                         # Phase 1B (5 of 9 done)
│   │   ├── 04_download_phenopacket_store.sh
│   │   ├── 13_load_phenopackets.py
│   │   ├── 14_apply_inclusion_exclusion.py
│   │   ├── 15_categorize_by_mondo.py
│   │   └── 16_stratified_sample.py
│   ├── eval/                          # Phase 2 evaluation harness (planned)
│   └── demo/
│       ├── run_pipeline.sh            # End-to-end demo orchestrator
│       ├── collect_stats.py           # Logs → JSON
│       └── make_visualizations.py     # JSON → matplotlib PNGs
├── src/                               # Phase 2 application code (planned)
│   ├── agents/                        # LangGraph state graph + 4 agent nodes
│   ├── api/                           # FastAPI + copilotkit-sdk-python
│   └── tools/                         # Shared HPO/MeSH/HGNC/Qdrant utilities
├── frontend/                          # Phase 2c CopilotKit React UI (planned)
├── tests/                             # Unit + integration
├── config/                            # Prompt templates, agent configs
├── reports/
│   ├── visual_report.html             # Original demo visual report
│   ├── technical_report.md            # Original demo technical report
│   ├── progress_report_09052026.{md,html}     # Status snapshot v1
│   ├── progress_report_09052026_v2.{md,html}  # Status snapshot v2
│   ├── progress_report_09052026_v3.{md,html}  # THIS document (consolidated)
│   ├── pipeline_stats.json            # Demo run stats
│   ├── images/                        # architecture.svg + 5 PNGs
│   └── run_logs/                      # Captured demo stdout
├── logs/                              # Production run logs (gitignored)
└── ~/rare-disease-rag/                # OUTSIDE the repo
    ├── qdrant_storage/                # Qdrant index (~300-500 GB at full build)
    ├── models/                        # Qwen3-8B + PubMedBERT cache
    └── logs/
```

---

## 17. Citation

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

---

## 18. Acknowledgments and prior work

This work builds on the open ecosystem of biomedical NLP and bioinformatics — particularly the [Monarch Initiative](https://monarchinitiative.org), the [Human Phenotype Ontology Consortium](https://hpo.jax.org), the [GA4GH community](https://www.ga4gh.org), and the maintainers of [PMC Open Access](https://pmc.ncbi.nlm.nih.gov/) — without which a project of this scope would not be possible from a single workstation.

Key cited prior work:

- Lewis et al. (2020) — RAG: [arxiv.org/abs/2005.11401](https://arxiv.org/abs/2005.11401)
- Smedley et al. (2015) — Exomiser: [doi.org/10.1038/nprot.2015.124](https://doi.org/10.1038/nprot.2015.124)
- Clark et al. (2018) — diagnostic yield of clinical sequencing: [doi.org/10.1038/s41525-018-0053-8](https://doi.org/10.1038/s41525-018-0053-8)
- Köhler et al. — HPO consortium publications
- CopilotKit team — AG-UI Protocol: [github.com/ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui)

---

*End of v3 consolidated report. This document is intended to be the canonical project record. Regenerate after the production corpus build completes (estimated 2026-05-14 to 2026-05-18) so the report reflects the populated Qdrant index, the closed-out Phase 1B, and any Phase 2 progress.*
