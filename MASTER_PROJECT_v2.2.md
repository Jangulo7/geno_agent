# MASTER PROJECT FILE v2.2 — Agentic Multi-Agent RAG for Gene Prioritization

Private GitHub repository: https://github.com/Jangulo7/geno_agent
Project Local folder: `/home/hana77/ia_jo/uax_tfm/geno_agent`
Tool: VS Code Server for Linux x64
Authoritative methodology reference (consolidated 2026-05-18): [`reports/methodology.md`](reports/methodology.md)

## Phase 1A + Phase 1B (Database & Cohort) + Phase 3 (Paper Extension)

> **Target executor:** Claude Code on WSL2 Ubuntu 24 (Windows host, NVIDIA RTX 5090 32 GB VRAM, 64 GB RAM)
> **Methodology source:** Chapter 4 — Methodology v3 + [`reports/methodology.md`](reports/methodology.md) (2026-05-18 consolidated)
> **Storage strategy:** Linux (~700 GB) for Qdrant + models + code; Windows (`/mnt/c/`) for temporary bulk processing

---

## CHANGELOG — v2.1 → v2.2 (Paper Extension, 2026-05-15 → 2026-05-18)

v2.2 reflects the post-thesis paper-extension phase: evaluation scaled from
n=75 to n=1,047, two new baselines added (LIRICAL Cell M alongside Exomiser
Cell K), two new evaluation axes (RAGAS + DeepEval), and four new analyses
(Threads D-G in the v3 plan). The v2.1 phase-1 core (Phase 1A corpus, Phase 1B
cohort generation, original 16-cell factorial) is unchanged; v2.2 adds Phase 3
(paper extension) and refines the runtime configuration accordingly.

**Cohort upgrades:**

1. **Phenopacket Store v0.1.19 → v0.1.26** (released 2026-01-13). +252 new gene cohorts, +1,699 new eligible cases. Immunological-disease eligible pool grew 85 → 390 (+359 %), eliminating the structural cap on the paper's lead categorical analysis.
2. **Disproportionate stratified sampling** added to Stage 16 via new `--per-category-target "cat=N,..."` flag. Allows oversampling the limiting category (immunological at 300 / pool 390 = 77 %) for subgroup statistical power while keeping the others at 250 each.
3. **n=1,047 (250 dev + 300 imm + 250 met + 247 neuro)** is the canonical paper-extension cohort.

**New baselines (Phase 3):**

4. **Cell M — LIRICAL HPO-only** (Robinson et al. AJHG 2020) as a second curated baseline alongside Exomiser. Wrapped by `src/baselines/lirical_runner.py` with disease→gene mapping via NCBI mim2gene_medgen + Orphanet en_product6.xml + HGNC. 8-worker parallel pool in `scripts/eval/run_cell_m.py`. Initial result: LIRICAL top-1 = 0.924 on n=1,047 — likely reflects annotation overlap with `phenotype.hpoa` source PMIDs; see Thread D in plan v3.

**New evaluation axes (Phase 3):**

5. **RAGAS** evaluation pipeline (`scripts/eval/run_ragas.py`) computing faithfulness, context_precision, context_recall, answer_relevance over Cell L and Cell S sidecars. GPT-4o (`gpt-4o-2024-08-06`) as the LLM judge via OpenAI API — a documented project-rule deviation for evaluation only (production stays all-local).
6. **DeepEval** hallucination metric (`scripts/eval/run_deepeval.py`) on Cell S, same GPT-4o judge.
7. **Per-case response sidecars** persisted at `data/eval_1050/cell_{L,S}_responses/<case>.json` with full LEA prompt, raw response text, parsed JSON ranking, token counts, finish reason, and per-gene retrieved chunks (PMCIDs, section types, RRF scores). Required for RAGAS/DeepEval.

**New analyses (Phase 3 — Threads D-G in plan v3):**

8. **Thread D — LIRICAL annotation-overlap analysis.** Per-case binary flag for whether the case source PMID is referenced in `phenotype.hpoa` for the causal gene's OMIM disease. Stratifies all 5 cells' results into overlap-present vs overlap-absent subsets to deconfound LIRICAL's apparent dominance.
9. **Thread E — Novel-cases subset.** Filter the n=1,047 to cases whose source PMID was published after `phenotype.hpoa` v2026-02-16 release. LIRICAL has no annotations for these → fair comparison. Expected ~150-300 case subset.
10. **Thread F — LIRICAL + LEA ensemble.** Combine M and S rankings via Reciprocal Rank Fusion + weighted blend. Demonstrates complementarity.
11. **Thread G — Explanation quality contrast.** Only Cell S produces evidence-traceable rationales with PMC citations. RAGAS faithfulness on Cell S has no equivalent on curated tools.

**Runtime infrastructure refinements (Phase 3):**

12. **VRAM caps for vLLM Cell S** finalized after 4 iterations: `--gpu-memory-utilization 0.75`, `--max-model-len 32768`, `--max-num-seqs 1`, `--dtype float16`, `--enable-prefix-caching`. Documented in `scripts/eval/start_vllm.sh`. Leaves ~8 GB free for CE + dense + activations.
13. **Sequenced GPU resource scheduling** (`scripts/eval/run_paper_extension.sh`): Cells D → L → [start vLLM] → S → [kill vLLM]. vLLM is alive only during Cell S, explicitly torn down via `trap` to release VRAM for next stage.
14. **vLLM in dedicated venv** (`~/vllm-env/`, separate from `pytorch-env`). `start_vllm.sh` uses `${VLLM_PYTHON:-${HOME}/vllm-env/bin/python}`.
15. **Stage 16 patched** with `--per-category-target` flag (disproportionate sampling). **Stage 17 patched** to honour `TEST_CASES_DIR` env var (previously hardcoded path).

**Documentation additions (Phase 3):**

16. [`reports/paper_extension_plan.md`](reports/paper_extension_plan.md) — v1 plan (n=460, v0.1.19, seed 4242)
17. [`reports/paper_extension_plan_v2.md`](reports/paper_extension_plan_v2.md) — v2 plan (n=1,047, v0.1.26, seed 42)
18. [`reports/paper_extension_plan_v3.md`](reports/paper_extension_plan_v3.md) — v3 plan (LIRICAL, RAGAS, DeepEval, Threads D-G)
19. [`reports/paper_extension_results.md`](reports/paper_extension_results.md) + `.html` — v2 final results (Cell S beats Exomiser, Δ=+3.4 pp ★)
20. [`reports/methodology.md`](reports/methodology.md) — consolidated authoritative methodology reference

**Headline result (v2 final, tagged `paper-v2-final`):**

> Cell S (rerank + LEA) statistically outperforms Exomiser HPO-only on overall top-1 at n=1,047 (Δ = +0.034, paired-bootstrap 95 % CI [+0.006, +0.064]). Statistically wins on metabolic (+8.4 pp) and immunological (+6.7 pp) MONDO subgroups. LEA contributes a significant +2.7 pp over rerank alone. Immunological lead claim survives 100 % leave-one-out at n=300 (McNemar exact p = 0.008).

**v3 paper-extension status (REVISED 2026-05-23, after Threads D-G + v3-5 aggregation):**

24. **v3-5 aggregation** (commit `1b65028`): 5-cell paired-Δ + paired-bootstrap CI + exact McNemar across n=1,047 on D/K/L/M/S. Reusable toolkit (`scripts/eval/paired_diff.py`) for Threads D-G.
25. **Thread D — annotation-overlap deconfounding** (commit `308fb2e`): Per-case overlap flag from `phenotype.hpoa v2026-02-16` (`scripts/eval/compute_annotation_overlap.py`). Cohort overlap rate 73.1 %. **On the fair cohort (overlap-absent, n=282), Cell S becomes the #1 system**: S = 0.858, L = 0.823, K = 0.780, M = 0.777, D = 0.475. S beats M by Δ = +0.082 [+0.021, +0.145] ★ McNemar p = 0.014. S beats K by Δ = +0.078 [+0.011, +0.138] ★ (>2× the +0.035 on full cohort). **M ties K** (Δ = -0.004, p = 1.000) — LIRICAL's apparent +0.23 advantage is artefact.
26. **Thread E — recency-stratified analysis** (commit `6a812a4`, pivoted): The plan's strict "PMID > hpoa pin" subset is empty by construction (Phenopacket Store is curated from already-published literature). Pivoted to pre_2020 (n=601) vs post_2020 (n=446) split using NCBI E-utils PMID dates. **Exomiser top-1 collapses 0.847 → 0.480 on post-2020 papers** (Δ = -37 pp, largest recency drop of any system). geno_agent's edge over Exomiser is **2.7× larger on recent cases** (Δ S−K = +0.094 ★ post_2020 vs +0.035 ★ full cohort). LIRICAL paradoxically *rises* (0.915 → 0.935) due to a 12.6 pp higher overlap rate on recent cases — hpoa preferentially curates recent landmark publications.
27. **Thread F — RRF ensemble check** (commit `178ed68`, scoped to 1-day): Cell N = RRF(M, S) at k=60. On the fair cohort, **N is statistically tied with S alone** (Δ = -0.007 NS); on the contaminated cohort, N is significantly worse than M alone (Δ = -0.230 ★). The two systems carry no independent predictive signal beyond what overlap status already explains. "Did you try ensembling?" reviewer question closed with a one-sentence Discussion conclusion.
28. **Thread G — explanation-quality structural part** (commit `49ebaca`): Cell S is the only system in the comparison that produces evidence-traceable rankings. **81.5 % of cases have a substantive LEA rationale for the causal gene** overall, rising to **94.0 % on the fair-comparison cohort**. Mean 2.81 unique PMC citations per top-1 gene. **LEA deterministic-fallback rate = 0.2 % overall and 0.0 % on the fair cohort** — concrete answer to the LLM-reproducibility reviewer concern. RAGAS faithfulness pending Thread C completion.
29. **Thread C / RAGAS scope** (in flight 2026-05-23): Smoke test revealed real cost ~$160 for the originally-planned full-cohort × both-cells × 4-metrics design — over the $100 budget. Final scope: **Cell S only, n=600 stratified (150 per MONDO, seed 42), 3 metrics (faithfulness + context_precision + context_recall), MAX_CONTEXTS=20, ~$95**.
29a. **Thread C / RAGAS COMPLETED 2026-05-23 18:13Z** (167.8 min wall, $95 spent — within budget). Aggregate scores: **faithfulness mean 0.286 / median 0.433; context_precision 0.650; context_recall 0.796**. Key secondary finding: **faithfulness is a strong correctness predictor** — cases at faithfulness=0 are 46.5 % top-1 correct vs 79.9 % at faithfulness>0 (33-pp gap), usable as an auto-triage flag for clinical deployment. Faithfulness is also slightly higher on the fair-comparison cohort (0.310 vs 0.276 mean), consistent with Thread G's rationale-coverage story. Honest caveat documented: faithfulness was computed against ≤ 20 contexts per case (budget cap) while LEA itself saw up to 45 chunks — the 0.286 is plausibly a lower bound on the true value.

29b. **DeepEval HallucinationMetric COMPLETED 2026-05-23 18:40Z** (3.1 min wall, $1.20 spent — combined RAGAS+DeepEval $96.20 / $100 budget). n=100 stratified subset (25/MONDO, seed 42 — a subset of the RAGAS n=600), same gpt-4o-2024-08-06 judge, MAX_CONTEXTS=45. **Mean groundedness 0.845 / median 0.933, hallucination rate 0.155**. Independent reproduction of the RAGAS findings: (i) correctness-prediction signal reproduces (78.9 % top-1 correct at groundedness ≥ 0.5 vs 40.0 % at < 0.5, 39-pp gap matching RAGAS's 33-pp); (ii) fair-cohort lift reproduces (0.894 overlap_absent vs 0.830 overlap_present). Per-MONDO: developmental 0.898, immunological 0.946, metabolic 0.872, **neurological 0.665 (worst on both judges — robustly-documented system-level limitation)**. The two metrics together bound LEA grounding quality at a defensible range (0.286 strict claim-level ↔ 0.845 lenient holistic) — the paper reports both rather than cherry-picking.

**Strategy A timeline revised:** ~3-4 weeks remaining to Genome Medicine submission (was ~12-13 weeks at v3 start). Threads D-G collapsed from ~8-11 day estimate to ~1 h actual wall — Thread D's per-case PMID/overlap toolkit made Threads E/F/G mechanical.

**Project-rule deviations (recorded in §10):**

30. Ontology versions pinned to 2026 releases instead of 2024.
31. Phenopacket Store upgraded v0.1.19 → v0.1.26 between v1 and v2 paper extension.
32. GPT-4o cloud API used for RAGAS/DeepEval judging only — production pipeline (Cells D, L, S) remains 100 % local. Required because using a Qwen-family judge would introduce self-evaluation bias; GPT-4o is the de-facto standard RAG-eval judge in 2025-2026.
33. Thread E pivoted from "PMID > hpoa pin date" (empty by construction in our cohort) to a publication-recency split; documented in `paper_extension_results.md §14` and `methodology.md §4.8`.
34. Thread F scoped down from 3-day full ensemble experiment to 1-day RRF(M,S) check after Thread D + E established the ensemble is mathematically bounded by the better of M and S on each subset.

**Headline result (REVISED 2026-05-23, supersedes the v2-final headline for paper framing):**

> On the fair-comparison cohort (n = 282 cases whose source publication is not cited in `phenotype.hpoa` for the causal disease), geno_agent (Cell S) is the **#1 system**: top-1 = 0.858 [0.816, 0.901], beating LIRICAL (0.777, Δ = +8.2 pp ★) and Exomiser (0.780, Δ = +7.8 pp ★). LIRICAL's apparent dominance on the full cohort (top-1 = 0.924) is shown to be an **annotation-overlap artefact** (73 % of cases have source PMIDs cited in LIRICAL's hpoa for the causal disease); once deconfounded LIRICAL is **statistically tied** with Exomiser. geno_agent additionally provides: 2.7× larger relative advantage on post-2020 papers, 94 % substantive rationale coverage on the fair cohort with 2.81 PMC citations per top-1 gene, and 0.0 % LLM-fallback rate on the fair cohort.

---

## CHANGELOG — v2 → v2.1

This release fixes the three blocking defects in v2 and adds the Phase 1B test-case-preparation pipeline that v2 omitted.

**Blocking fixes (Phase 1A):**

1. **BM25 sparse-vector implementation rewritten.** v2 used Python's salted `hash()` over whitespace-tokenized lowercased text. v2.1 uses Qdrant's first-class BM25 via `fastembed.SparseTextEmbedding("Qdrant/bm25")`, which provides deterministic indices, biomedical-aware tokenization, and the document/query asymmetry that BM25 actually requires.
2. **Deterministic chunk IDs.** v2 used `uuid.uuid4()` (random per run). v2.1 uses `uuid.uuid5(NAMESPACE, content_key)` so identical inputs always produce identical chunk IDs across runs and machines.
3. **Pinned ontology versions.** v2 downloaded `latest` from the OBO Foundry. v2.1 downloads explicit, dated releases (HPO `v2026-02-16`, MONDO and GO snapshotted by date) and writes a SHA-256 manifest of every downloaded asset.

**Polishing fixes (Phase 1A):**

4. `PYTHONHASHSEED=42` is now exported in `.env` and explicit `torch`/`numpy`/`random` seeding added to embedding generation.
5. Qdrant collection now uses `on_disk_payload=True` to keep RAM bounded for ~2–5 M chunks.
6. Filter step now hard-asserts retention is in `[100_000, 600_000]` and exits with a clear message if not.
7. Validation step uses `client.count(...)` (modern API) instead of the deprecated `vectors_count`.
8. Acquisition manifest (`data/MANIFEST.tsv`) records date + SHA-256 of every downloaded artifact.

**Additions (Phase 1B — new):**

9. Phenopacket-store v0.1.19 ingest from a pinned release tarball.
10. Inclusion/exclusion filtering (≥3 HPO terms, single-gene pathogenic variant, no chromosomal/mitochondrial diseases).
11. MONDO-based disease categorization (neurological, metabolic, immunological, developmental).
12. Stratified random sampling of 50–100 cases (seed = 42).
13. PMC OA causal-gene coverage validation (≥5 articles per causal gene) against the Phase 1A index.
14. Candidate gene list builder (1 causal + 49 HGNC protein-coding distractors per case, seed = 42).
15. Test-case manifest persisted as a single canonical JSONL the experiment runner consumes.

**Additions (Phase 2 — added 2026-05-09):**

16. **LangGraph 4-agent state graph** (Query Planner → Retriever → Critic → Synthesizer) with conditional self-correction edges back to the Retriever. See §11.1.
17. **FastAPI + `copilotkit-sdk-python`** endpoint exposing the graph over the AG-UI protocol with SSE streaming of agent state. See §11.2.
18. **CopilotKit React UI** at `frontend/`, sourced from the user's fork [`github.com/Jangulo7/agent_UI`](https://github.com/Jangulo7/agent_UI) (upstream `CopilotKit/CopilotKit`). Custom geno_agent components: `<HPOPicker>`, `<CandidateGeneList>`, `<AgentTracePanel>`, `<GeneCandidateCard>`, `<CitationHover>`. See §11.3.
19. **Qwen3-8B Instruct via vLLM** as the local reasoning model for all agent calls. RTX 5090 32 GB VRAM hosts the LLM, PubMedBERT, and Qdrant queries together. See §11.4.
20. **2×2+1 factorial evaluation** harness (single-agent vs multi-agent × dense-only vs hybrid + Exomiser baseline) over the Phase 1B test cases. Output: LaTeX-ready results table per metric. See §11.5.

A formal "Deviations from methodology" log is included in §10.

---

## 0. ARCHITECTURAL CLARIFICATION — What Goes Where and Why

Before executing anything, understand the **role of each data resource** in the system:

### Resources that GO INTO the Vector Database (Qdrant)

| Resource | Role | Preparation |
|----------|------|-------------|
| **PMC OA Subset (XML)** | Primary retrieval corpus — the RAG knowledge base | Heavy: parse JATS XML → filter by MeSH/keywords → section-aware chunking (512 tokens, 50-token overlap) → PubMedBERT embedding (768-dim) → index in Qdrant with dense HNSW + BM25 sparse vectors |

**Only PMC OA goes into Qdrant.** This is the corpus the Retriever Agent searches at runtime.

### Resources used OFFLINE / AT RUNTIME (never loaded into Qdrant)

| Resource | Role | When Used |
|----------|------|-----------|
| **HPO** (`hp.obo` + gene/phenotype association files) | Query expansion — synonym/parent-term broadening | Runtime: Query Planner Agent uses `pronto` to traverse the ontology graph |
| **MONDO** (`mondo.obo`) | Disease classification for stratified sampling | **Phase 1B**: test-case categorization (neurological, metabolic, immunological, developmental) |
| **Gene Ontology** (`go.obo` + `goa_human.gaf`) | Gene-function annotations, semantic similarity | Offline: subgroup analysis and error analysis |
| **HGNC Complete Set** | Canonical gene symbols for distractor selection | **Phase 1B**: candidate-list construction (49 random protein-coding distractors per case) |
| **Phenopacket-store v0.1.19** | Benchmark test cases (ground truth) | **Phase 1B**: test-case selection, phenotype extraction |

### Why This Separation Matters

The ontologies and gene databases are **structured knowledge** (graphs, tables) — they don't benefit from vector similarity search. They are accessed programmatically via their native APIs (`pronto` for OBO files, `pandas` for TSV files). Uploading them to Qdrant would:
- Destroy their graph structure (is-a hierarchies, synonym relations)
- Create noisy, low-quality chunks that pollute retrieval results
- Waste storage and embedding compute

The PMC OA corpus is **unstructured text** — full-text articles that need semantic search to find relevant evidence. This is exactly what vector databases are designed for.

### Phase 1A vs Phase 1B Boundary

- **Phase 1A** (§§3.1, 3.2, 3.3, 3.5, 4) builds the Qdrant index of biomedical literature.
- **Phase 1B** (§§3.4, 6) builds the benchmark test set of clinical cases.

Phase 1B has a hard dependency on Phase 1A: candidate-causal-gene PMC coverage (≥5 articles) is verified against the Phase 1A index. Run 1A first, end-to-end, then 1B.

---

## 1. PROJECT DIRECTORY STRUCTURE

```bash
# ============================================================
# WSL2 DUAL-DRIVE STORAGE STRATEGY
# ============================================================
# LINUX (~700 GB) — Performance-critical persistent data:
#   ~/rare-disease-rag/                Project code, config, models
#   ~/rare-disease-rag/qdrant_storage/ Qdrant index (~300-500 GB)
#
# WINDOWS (/mnt/c/ or /mnt/d/) — Temporary bulk processing:
#   /mnt/c/pmc_workspace/              Raw XML, intermediates (deleted after use)
#
# WHY: WSL2 accesses Windows via 9P protocol (5-10x slower I/O).
#      Qdrant HNSW graph traversal MUST be on native Linux filesystem.
#      Bulk sequential read/write (XML parsing) tolerates /mnt/c/ latency.
# ============================================================

PROJECT_ROOT="$HOME/rare-disease-rag"
PMC_WORKSPACE="/mnt/c/pmc_workspace"   # CHANGE to /mnt/d/ if C: lacks space

# Linux side: persistent project structure
mkdir -p "$PROJECT_ROOT"/{
  scripts/{corpus,ontology,embedding,indexing,cases,utils,demo,eval},
  src/{agents,api,tools},                    # Phase 2 Python (LangGraph + FastAPI)
  frontend,                                  # Phase 2c Node.js / CopilotKit (separate npm project)
  config,
  logs,
  tests/{agents,corpus,indexing},
  results,
  data/{ontologies,hgnc,phenopackets,test_cases},
  models,                                    # Local LLM weights (Qwen3-8B); see §11.4
  qdrant_storage
}

# Windows side: temporary processing workspace
mkdir -p "$PMC_WORKSPACE"/{xml_raw,parsed,filtered,chunks,embeddings}

# Create a .env file for project-wide configuration
cat > "$PROJECT_ROOT/config/.env" << 'EOF'
# === Linux paths (persistent, fast I/O) ===
PROJECT_ROOT=$HOME/rare-disease-rag
ONTOLOGY_DIR=$PROJECT_ROOT/data/ontologies
HGNC_DIR=$PROJECT_ROOT/data/hgnc
PHENOPACKET_DIR=$PROJECT_ROOT/data/phenopackets
TEST_CASES_DIR=$PROJECT_ROOT/data/test_cases
QDRANT_STORAGE=$PROJECT_ROOT/qdrant_storage
QDRANT_HOST=localhost
QDRANT_PORT=6333
COLLECTION_NAME=pmc_rare_disease_v1
EMBEDDING_MODEL=NeuML/pubmedbert-base-embeddings
EMBEDDING_DIM=768
CHUNK_MAX_TOKENS=512
CHUNK_OVERLAP_TOKENS=50
RANDOM_SEED=42
LOG_DIR=$PROJECT_ROOT/logs

# === Pinned ontology versions ===
HPO_VERSION=v2026-02-16
MONDO_VERSION=v2026-03-03
GO_VERSION=2026-03-25
HGNC_SNAPSHOT=2026-04-07           # quarterly archive directory
PHENOPACKET_STORE_VERSION=0.1.19

# === Determinism ===
PYTHONHASHSEED=42

# === Phase 1B sample parameters ===
SAMPLE_TARGET_SIZE=75              # midpoint of methodology's 50–100 range
MIN_HPO_TERMS=3
MIN_PMC_ARTICLES_PER_GENE=5
N_DISTRACTORS=49                   # → 50-gene candidate list (1 causal + 49 distractors)

# === Windows paths (temporary bulk workspace, slower I/O) ===
PMC_WORKSPACE=/mnt/c/pmc_workspace
PMC_RAW_DIR=$PMC_WORKSPACE/xml_raw
PMC_PARSED_DIR=$PMC_WORKSPACE/parsed
PMC_FILTERED_DIR=$PMC_WORKSPACE/filtered
CHUNKS_DIR=$PMC_WORKSPACE/chunks
EMBEDDING_DIR=$PMC_WORKSPACE/embeddings
EOF
```

---

## 2. ENVIRONMENT SETUP

```bash
cd "$PROJECT_ROOT"

# Create Python virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Core dependencies
pip install --upgrade pip

# Corpus processing
pip install lxml requests tqdm

# Ontology handling
pip install pronto obonet networkx

# Embedding and ML
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install sentence-transformers transformers tokenizers

# Vector database + sparse embeddings (CRITICAL: fastembed for BM25)
pip install qdrant-client[fastembed] fastembed

# Phase 1B — Phenopacket ingest
pip install phenopackets    # Official GA4GH Python protobuf bindings

# Data handling
pip install pandas pyarrow

# Utilities
pip install python-dotenv joblib psutil

# Phase 2a — agent orchestration
pip install langgraph langchain-core
pip install vllm                                      # GPU inference; ollama acceptable for dev

# Phase 2b — API
pip install fastapi 'uvicorn[standard]' sse-starlette
pip install copilotkit                                # Python SDK; AG-UI protocol

# Phase 2c — frontend (Node.js, NOT pip; runs in frontend/ subdirectory)
# Requires Node.js >= 20 + npm. Install via nvm or distro package manager.
# Once Node.js is available:
#   cd frontend && npx copilotkit@latest create -f next
# The frontend is a standalone npm project; see §11.3.

# Freeze requirements
pip freeze > requirements.txt
```

### 2.1 Install and Start Qdrant (Docker)

```bash
# NOTE: You may already have a Qdrant instance running with another research DB.
# Option A: Use the SAME Qdrant container (recommended — just add a new collection)
#   Your existing collections are untouched. The new collection "pmc_rare_disease_v1"
#   coexists alongside your other DB. Ensure the storage volume has ≥500 GB free.

# Check if Qdrant is already running:
docker ps | grep qdrant
curl -s http://localhost:6333/collections | python3 -m json.tool

# Option B: Run a second container on a different port for isolation:
# docker run -d \
#   --name qdrant-geneprio \
#   --restart unless-stopped \
#   -p 6335:6333 \
#   -p 6336:6334 \
#   -v "$PROJECT_ROOT/qdrant_storage:/qdrant/storage:z" \
#   qdrant/qdrant:latest
# Then change QDRANT_PORT=6335 in config/.env

# IMPORTANT FOR WSL2: Qdrant storage MUST be on Linux filesystem, not /mnt/c/.

# Verify connectivity
curl -s http://localhost:6333/healthz
```

### 2.2 Determinism Settings (NEW in v2.1)

Reproducibility requires that every stochastic surface is pinned. The `.env` file already exports `PYTHONHASHSEED=42` and `RANDOM_SEED=42`. Every Python entrypoint that does any embedding, sampling, or randomized work must apply the seeds explicitly:

```python
# scripts/utils/seed.py
import os, random, hashlib
import numpy as np

def apply_seeds(seed: int = 42) -> None:
    """Apply deterministic seeds across all stochastic surfaces."""
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        # Best-effort determinism on CUDA; warn_only=True so cuBLAS ops with
        # no deterministic implementation don't crash the embedding job.
        torch.use_deterministic_algorithms(True, warn_only=True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except ImportError:
        pass

def stable_hash(s: str) -> int:
    """Cross-process stable hash (replaces salted Python hash())."""
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")
```

Every script in §§3–6 imports `apply_seeds()` at startup.

---

## 3. DOWNLOAD ALL RESOURCES

### 3.1 PMC Open Access Subset (Knowledge Corpus for RAG)

The methodology specifies AWS S3 as the preferred download method (NCBI FTP deprecated August 2026).

```bash
# ============================================================
# SCRIPT: scripts/corpus/01_download_pmc_oa.sh
# PURPOSE: Download PMC OA XML from AWS S3
# TIME: ~4-8 hours depending on bandwidth (~120-150 GB compressed)
# ============================================================

#!/bin/bash
set -euo pipefail
source config/.env

echo "=== Downloading PMC OA Subset from AWS S3 ==="
echo "This will download ~120-150 GB compressed XML across 3 license tiers."
echo "Estimated disk after decompression: ~400-500 GB"

# Install AWS CLI if not present
if ! command -v aws &> /dev/null; then
    pip install awscli
fi

# Download all three license tiers (methodology requires all three)
for TIER in oa_comm oa_noncomm oa_other; do
    echo "--- Downloading tier: $TIER ---"
    mkdir -p "$PMC_RAW_DIR/$TIER"

    # S3 bucket is public, no credentials needed
    aws s3 sync \
        --no-sign-request \
        "s3://pmc-oa-opendata/$TIER/xml/all/" \
        "$PMC_RAW_DIR/$TIER/" \
        --only-show-errors \
        2>&1 | tee -a "$LOG_DIR/download_pmc_$TIER.log"

    echo "--- Completed: $TIER ---"
done

# Record acquisition timestamp (per-file SHA-256 deferred to manifest step)
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$PMC_RAW_DIR/.acquired_at"

echo "=== PMC OA Download Complete ==="
du -sh "$PMC_RAW_DIR"/*
```

### 3.2 Ontological Resources (Pinned Versions, NOT for Qdrant)

```bash
# ============================================================
# SCRIPT: scripts/ontology/02_download_ontologies.sh
# PURPOSE: Download HPO (PINNED v2026-02-16), MONDO, GO + annotation files
# SIZE: < 100 MB total
# ============================================================

#!/bin/bash
set -euo pipefail
source config/.env

echo "=== Downloading Ontological Resources (pinned versions) ==="

# --- HPO (Human Phenotype Ontology) — PINNED to v2026-02-16 per methodology §4.2.3 ---
echo "--- HPO Ontology (${HPO_VERSION}) ---"
mkdir -p "$ONTOLOGY_DIR/hpo"

# Pinned release URL (NOT the latest /obo/hp.obo)
wget -O "$ONTOLOGY_DIR/hpo/hp.obo" \
    "https://github.com/obophenotype/human-phenotype-ontology/releases/download/${HPO_VERSION}/hp.obo"

# Gene-phenotype association files from the same release tag
wget -O "$ONTOLOGY_DIR/hpo/genes_to_phenotype.txt" \
    "https://github.com/obophenotype/human-phenotype-ontology/releases/download/${HPO_VERSION}/genes_to_phenotype.txt"
wget -O "$ONTOLOGY_DIR/hpo/phenotype_to_genes.txt" \
    "https://github.com/obophenotype/human-phenotype-ontology/releases/download/${HPO_VERSION}/phenotype_to_genes.txt"
wget -O "$ONTOLOGY_DIR/hpo/phenotype.hpoa" \
    "https://github.com/obophenotype/human-phenotype-ontology/releases/download/${HPO_VERSION}/phenotype.hpoa"

echo "HPO ${HPO_VERSION} downloaded: $(ls -la "$ONTOLOGY_DIR/hpo/")"

# --- MONDO Disease Ontology — PINNED ---
echo "--- MONDO Ontology (${MONDO_VERSION}) ---"
mkdir -p "$ONTOLOGY_DIR/mondo"
wget -O "$ONTOLOGY_DIR/mondo/mondo.obo" \
    "https://github.com/monarch-initiative/mondo/releases/download/${MONDO_VERSION}/mondo.obo"

echo "MONDO ${MONDO_VERSION} downloaded: $(ls -la "$ONTOLOGY_DIR/mondo/")"

# --- Gene Ontology (GO) — PINNED by date ---
echo "--- Gene Ontology (${GO_VERSION}) ---"
mkdir -p "$ONTOLOGY_DIR/go"
wget -O "$ONTOLOGY_DIR/go/go.obo" \
    "http://release.geneontology.org/${GO_VERSION}/ontology/go.obo"

# Human GO annotations — pinned by release directory
wget -O "$ONTOLOGY_DIR/go/goa_human.gaf.gz" \
    "http://release.geneontology.org/${GO_VERSION}/annotations/goa_human.gaf.gz"
gunzip -k "$ONTOLOGY_DIR/go/goa_human.gaf.gz"

echo "GO ${GO_VERSION} downloaded: $(ls -la "$ONTOLOGY_DIR/go/")"

echo "=== All Ontologies Downloaded (pinned) ==="
du -sh "$ONTOLOGY_DIR"
```

### 3.3 Reference Gene Database (Pinned HGNC Snapshot, NOT for Qdrant)

```bash
# ============================================================
# SCRIPT: scripts/ontology/03_download_hgnc.sh
# PURPOSE: Download a PINNED quarterly HGNC snapshot
# SIZE: < 10 MB
# ============================================================

#!/bin/bash
set -euo pipefail
source config/.env

echo "=== Downloading HGNC Complete Gene Set (snapshot ${HGNC_SNAPSHOT}) ==="
mkdir -p "$HGNC_DIR"

# Use a quarterly archive snapshot (path format: archive/quarterly/tsv/<YYYY-MM-DD>/hgnc_complete_set_<YYYY-MM-DD>.txt)
# Adjust HGNC_SNAPSHOT in .env to a date for which a snapshot exists.
wget -O "$HGNC_DIR/hgnc_complete_set.txt" \
    "https://storage.googleapis.com/public-download-files/hgnc/archive/archive/quarterly/tsv/hgnc_complete_set_${HGNC_SNAPSHOT}.txt" \
    || (echo "Quarterly snapshot not found; falling back to current set (NOTE: not reproducible across time)" && \
        wget -O "$HGNC_DIR/hgnc_complete_set.txt" \
            "https://ftp.ebi.ac.uk/pub/databases/genenames/hgnc/tsv/hgnc_complete_set.txt")

echo "HGNC: $(wc -l < "$HGNC_DIR/hgnc_complete_set.txt") lines"
echo "File size: $(du -h "$HGNC_DIR/hgnc_complete_set.txt" | cut -f1)"
```

### 3.4 Phenopacket-Store v0.1.19 (NEW — Phase 1B benchmark cases)

```bash
# ============================================================
# SCRIPT: scripts/cases/04_download_phenopacket_store.sh
# PURPOSE: Download the pinned v0.1.19 release tarball of GA4GH Phenopackets
# SIZE: ~50 MB compressed
# ============================================================

#!/bin/bash
set -euo pipefail
source config/.env

echo "=== Downloading Phenopacket-store v${PHENOPACKET_STORE_VERSION} ==="
mkdir -p "$PHENOPACKET_DIR"

# The release ships a zip of all phenopackets organized by cohort
RELEASE_URL="https://github.com/monarch-initiative/phenopacket-store/releases/download/${PHENOPACKET_STORE_VERSION}/all_phenopackets.zip"

wget -O "$PHENOPACKET_DIR/all_phenopackets.zip" "${RELEASE_URL}"

# Unzip into a versioned directory so future re-runs don't collide
unzip -q "$PHENOPACKET_DIR/all_phenopackets.zip" -d "$PHENOPACKET_DIR/v${PHENOPACKET_STORE_VERSION}"

# Quick sanity report
NUM_JSON=$(find "$PHENOPACKET_DIR/v${PHENOPACKET_STORE_VERSION}" -name '*.json' | wc -l)
echo "Phenopacket-store v${PHENOPACKET_STORE_VERSION}: ${NUM_JSON} phenopacket JSON files extracted"
echo "Methodology expects 6,668 phenopackets — verify the count matches before proceeding."

if [ "$NUM_JSON" -lt 6000 ] || [ "$NUM_JSON" -gt 7500 ]; then
    echo "WARNING: file count ${NUM_JSON} is far from the expected 6,668."
    echo "         Check the release URL and the unzip target before proceeding."
fi
```

### 3.5 Acquisition Manifest (NEW — SHA-256 of every downloaded asset)

```bash
# ============================================================
# SCRIPT: scripts/utils/05_write_manifest.sh
# PURPOSE: Record date + SHA-256 of every downloaded asset
# OUTPUT: data/MANIFEST.tsv  (per methodology §4.11.7)
# ============================================================

#!/bin/bash
set -euo pipefail
source config/.env

MANIFEST="$PROJECT_ROOT/data/MANIFEST.tsv"
echo -e "path\tsha256\tbytes\tacquired_at" > "$MANIFEST"

ACQUIRED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Hash everything reproducibility-critical
find "$ONTOLOGY_DIR" "$HGNC_DIR" "$PHENOPACKET_DIR" -type f \
    \( -name '*.obo' -o -name '*.txt' -o -name '*.gaf' -o -name '*.gaf.gz' \
       -o -name '*.hpoa' -o -name '*.zip' -o -name '*.json' \) \
    | while read f; do
        SHA=$(sha256sum "$f" | awk '{print $1}')
        SIZE=$(stat -c '%s' "$f")
        echo -e "${f#$PROJECT_ROOT/}\t${SHA}\t${SIZE}\t${ACQUIRED_AT}" >> "$MANIFEST"
    done

echo "Manifest written: $MANIFEST  ($(wc -l < "$MANIFEST") entries)"
```

The manifest satisfies methodology §4.11.7 (reproducibility package). Every value reported in the final paper must be reproducible from the artifacts listed here.

---

## 4. CORPUS PROCESSING PIPELINE — Phase 1A (The Critical Path)

Each step must be executed sequentially. The output of each step feeds the next.

> **Deviation note:** Methodology §4.2.2 names `xml.etree.ElementTree`. We use `lxml` instead — it is ~10× faster, more namespace-robust, and required for tractable processing of 4M articles. Recorded in §10 (Deviations Log).

### Step 1 — Parse JATS XML → Structured Sections

```python
# ============================================================
# SCRIPT: scripts/corpus/06_parse_jats_xml.py
# PURPOSE: Extract structured sections from JATS XML files
# INPUT:   Raw .xml.gz / .tar.gz files from PMC OA
# OUTPUT:  JSONL files with parsed article sections
# TIME:    ~4-8 hours for full corpus
# ============================================================

"""
JATS XML parser for the PMC Open Access Subset.

Per methodology §4.2.2:
- Extract structured sections: abstract, introduction, methods, results,
  discussion, case_report.
- Preserve metadata: PMCID, title, publication year, MeSH terms,
  section type, section heading.
- Section ordering is stable: abstract first, then body sections in
  document order.
"""

import os, sys, json, gzip, tarfile, logging
from pathlib import Path
from lxml import etree
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('logs/parse_jats.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

SECTION_TYPE_MAP = {
    'abstract': 'abstract',
    'intro': 'introduction', 'introduction': 'introduction',
    'methods': 'methods', 'materials': 'methods',
    'materials and methods': 'methods', 'materials|methods': 'methods',
    'results': 'results', 'results and discussion': 'results',
    'discussion': 'discussion', 'conclusions': 'discussion',
    'case report': 'case_report', 'case presentation': 'case_report',
    'case description': 'case_report', 'clinical report': 'case_report',
}


def classify_section(sec_type_attr: str, heading_text: str) -> str:
    if sec_type_attr:
        key = sec_type_attr.lower().strip()
        if key in SECTION_TYPE_MAP:
            return SECTION_TYPE_MAP[key]
    if heading_text:
        heading_lower = heading_text.lower().strip()
        for pattern, sec_type in SECTION_TYPE_MAP.items():
            if pattern in heading_lower:
                return sec_type
    return 'other'


def extract_text_recursive(element) -> str:
    if element is None:
        return ""
    texts = []
    if element.text:
        texts.append(element.text)
    for child in element:
        tag = etree.QName(child.tag).localname if '}' in str(child.tag) else child.tag
        if tag in ('fig', 'table-wrap', 'supplementary-material', 'media'):
            for caption in child.findall('.//caption') + child.findall('.//{*}caption'):
                cap_text = extract_text_recursive(caption)
                if cap_text.strip():
                    texts.append(f" [Caption: {cap_text.strip()}] ")
        else:
            texts.append(extract_text_recursive(child))
        if child.tail:
            texts.append(child.tail)
    return ''.join(texts)


def get_mesh_terms(root) -> list:
    mesh_terms, seen = [], set()
    for kwd_group in root.findall('.//kwd-group') + root.findall('.//{*}kwd-group'):
        kwd_type = kwd_group.get('kwd-group-type', '').lower()
        if kwd_type in ('mesh', 'mesh-terms', ''):
            for kwd in kwd_group.findall('.//kwd') + kwd_group.findall('.//{*}kwd'):
                term = extract_text_recursive(kwd).strip()
                if term and term.lower() not in seen:
                    mesh_terms.append(term); seen.add(term.lower())
    for subj in root.findall('.//subject') + root.findall('.//{*}subject'):
        term = extract_text_recursive(subj).strip()
        if term and term.lower() not in seen:
            mesh_terms.append(term); seen.add(term.lower())
    return mesh_terms


def parse_single_article(xml_content: bytes) -> dict | None:
    try:
        root = etree.fromstring(xml_content)
    except etree.XMLSyntaxError as e:
        logger.warning(f"XML parse error: {e}")
        return None

    pmcid = None
    for article_id in root.findall('.//article-id') + root.findall('.//{*}article-id'):
        if article_id.get('pub-id-type') == 'pmc':
            txt = (article_id.text or "").strip()
            pmcid = txt if txt.startswith('PMC') else f"PMC{txt}"
            break
    if not pmcid:
        return None

    title_elem = root.find('.//article-title') or root.find('.//{*}article-title')
    title = extract_text_recursive(title_elem).strip() if title_elem is not None else ""

    pub_year = None
    for pub_date in root.findall('.//pub-date') + root.findall('.//{*}pub-date'):
        year_elem = pub_date.find('year') or pub_date.find('{*}year')
        if year_elem is not None and year_elem.text:
            try:
                pub_year = int(year_elem.text.strip()); break
            except ValueError:
                continue

    mesh_terms = get_mesh_terms(root)

    sections = []
    # 1. Abstract first (deterministic ordering)
    for abstract in root.findall('.//abstract') + root.findall('.//{*}abstract'):
        abstract_text = extract_text_recursive(abstract).strip()
        if abstract_text and len(abstract_text) > 50:
            sections.append({
                'section_type': 'abstract',
                'heading': 'Abstract',
                'text': abstract_text,
            })
            break  # Only first abstract — deterministic

    # 2. Body sections in document order
    body = root.find('.//body') or root.find('.//{*}body')
    if body is not None:
        for sec in body.findall('.//sec') + body.findall('.//{*}sec'):
            parent = sec.getparent()
            parent_tag = etree.QName(parent.tag).localname if '}' in str(parent.tag) else parent.tag
            if parent_tag not in ('body', 'sec'):
                continue
            sec_type_attr = sec.get('sec-type', '')
            heading_elem = sec.find('title') or sec.find('{*}title')
            heading = extract_text_recursive(heading_elem).strip() if heading_elem is not None else ''
            section_type = classify_section(sec_type_attr, heading)
            paragraphs = []
            for p in sec.findall('./p') + sec.findall('./{*}p'):
                p_text = extract_text_recursive(p).strip()
                if p_text:
                    paragraphs.append(p_text)
            text = '\n\n'.join(paragraphs)
            if text and len(text) > 50:
                sections.append({
                    'section_type': section_type,
                    'heading': heading,
                    'text': text,
                })

    if not sections:
        return None

    return {
        'pmcid': pmcid, 'title': title, 'pub_year': pub_year,
        'mesh_terms': mesh_terms, 'sections': sections,
    }


def process_tar_gz(tar_path: str, output_file, stats: dict):
    try:
        with tarfile.open(tar_path, 'r:gz') as tar:
            for member in sorted(tar.getmembers(), key=lambda m: m.name):  # deterministic order
                if member.name.endswith('.xml') and member.isfile():
                    stats['total_xml'] += 1
                    try:
                        f = tar.extractfile(member)
                        if f is None: continue
                        article = parse_single_article(f.read())
                        if article:
                            output_file.write(json.dumps(article) + '\n')
                            stats['parsed'] += 1
                        else:
                            stats['skipped'] += 1
                    except Exception as e:
                        stats['errors'] += 1
                        if stats['errors'] <= 100:
                            logger.warning(f"Error processing {member.name}: {e}")
    except Exception as e:
        logger.error(f"Error opening {tar_path}: {e}")


def main():
    from dotenv import load_dotenv
    load_dotenv('config/.env')

    raw_dir = Path(os.environ['PMC_RAW_DIR'])
    output_dir = Path(os.environ['PMC_FILTERED_DIR']).parent / 'parsed'
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = {'total_xml': 0, 'parsed': 0, 'skipped': 0, 'errors': 0}

    for tier in ['oa_comm', 'oa_noncomm', 'oa_other']:
        tier_dir = raw_dir / tier
        if not tier_dir.exists():
            logger.warning(f"Tier directory not found: {tier_dir}"); continue

        output_path = output_dir / f'{tier}_parsed.jsonl'
        tar_files = sorted(tier_dir.glob('*.tar.gz')) + sorted(tier_dir.glob('*.xml.tar.gz'))
        xml_files = sorted(tier_dir.glob('*.xml'))

        logger.info(f"Processing tier {tier}: {len(tar_files)} archives, {len(xml_files)} loose XML files")

        with open(output_path, 'w') as out:
            for tar_path in tqdm(tar_files, desc=f"Parsing {tier} archives"):
                process_tar_gz(str(tar_path), out, stats)
            for xml_path in tqdm(xml_files, desc=f"Parsing {tier} XML files"):
                stats['total_xml'] += 1
                try:
                    article = parse_single_article(xml_path.read_bytes())
                    if article:
                        out.write(json.dumps(article) + '\n')
                        stats['parsed'] += 1
                except Exception as e:
                    stats['errors'] += 1
        logger.info(f"Tier {tier} complete. Output: {output_path}")

    logger.info(f"=== Parsing Complete ===")
    logger.info(f"Total XML files seen:  {stats['total_xml']}")
    logger.info(f"Successfully parsed:   {stats['parsed']}")
    logger.info(f"Skipped (no content):  {stats['skipped']}")
    logger.info(f"Errors:                {stats['errors']}")


if __name__ == '__main__':
    main()
```

### Step 2 — Filter for Genetics/Genomics/Rare Disease Articles

```python
# ============================================================
# SCRIPT: scripts/corpus/07_filter_corpus.py
# PURPOSE: Retain only articles relevant to genetics/genomics/rare diseases
# INPUT:   Parsed JSONL from Step 1
# OUTPUT:  Filtered JSONL (~200,000-400,000 articles per methodology §4.2.2)
# METHOD:  MeSH-term matching + keyword filtering on title/abstract
# TIME:    ~30-60 minutes
#
# v2.1 CHANGE: hard-asserts retention is in [100K, 600K]; aborts otherwise.
# ============================================================

import os, sys, json, re, logging
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('logs/filter_corpus.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

TARGET_MESH_TERMS = {
    'genetics', 'genomics', 'rare diseases', 'genetic diseases, inborn',
    'genetic diseases inborn', 'exome sequencing', 'mutation', 'phenotype',
    'genotype', 'whole exome sequencing', 'genetic variation',
    'genetic predisposition to disease', 'genome-wide association study',
    'gene expression', 'dna mutational analysis', 'sequence analysis, dna',
    'polymorphism, single nucleotide', 'chromosomal disorders',
    'hereditary diseases', 'mendelian inheritance', 'alleles',
    'exome', 'genome', 'variant', 'variants', 'pathogenic',
}

KEYWORD_PATTERNS = [
    r'\bgene\b', r'\bgenetic\b', r'\bgenomic[s]?\b', r'\bmutation[s]?\b',
    r'\bvariant[s]?\b', r'\ballele[s]?\b', r'\bphenotype[s]?\b',
    r'\bgenotype[s]?\b', r'\brare\s+disease[s]?\b', r'\bmendelian\b',
    r'\bexome\b', r'\bwhole.?genome\b', r'\bpathogenic\b',
    r'\binherited\b', r'\bhereditary\b', r'\bcongenital\b',
    r'\bchromosom\w+\b', r'\bhomozygous\b', r'\bheterozygous\b',
    r'\bde\s+novo\b', r'\bautosomal\b', r'\bx-linked\b',
    r'\bloss.of.function\b', r'\bgain.of.function\b',
    r'\bmissense\b', r'\bnonsense\b', r'\bframeshift\b',
    r'\bsplice.site\b', r'\bcopy.number\b',
    r'\borphan\s+disease\b', r'\bundiagnosed\b',
    r'\bdiagnostic\s+odyssey\b', r'\bnext.generation\s+sequencing\b',
    r'\bwhole\s+exome\b', r'\bclinical\s+exome\b',
    r'\bHPO\b', r'\bOMIM\b', r'\bOrphanet\b',
]
KEYWORD_RE = re.compile('|'.join(KEYWORD_PATTERNS), re.IGNORECASE)

# Methodology §4.2.2 expects ~200K-400K articles after filter.
# Outside this range × 2 → almost certainly a regex regression.
RETENTION_MIN, RETENTION_MAX = 100_000, 600_000


def passes_mesh_filter(mesh_terms: list) -> bool:
    return any(t.lower().strip() in TARGET_MESH_TERMS for t in mesh_terms)


def passes_keyword_filter(article: dict) -> bool:
    if KEYWORD_RE.search(article.get('title', '')):
        return True
    for section in article.get('sections', []):
        if section.get('section_type') == 'abstract':
            if KEYWORD_RE.search(section.get('text', '')):
                return True
    return False


def main():
    parsed_dir = Path(os.environ['PMC_FILTERED_DIR']).parent / 'parsed'
    output_dir = Path(os.environ['PMC_FILTERED_DIR'])
    output_dir.mkdir(parents=True, exist_ok=True)

    total = kept_mesh = kept_keyword = dropped = 0

    for jsonl_file in sorted(parsed_dir.glob('*_parsed.jsonl')):
        tier_name = jsonl_file.stem.replace('_parsed', '')
        output_path = output_dir / f'{tier_name}_filtered.jsonl'
        logger.info(f"Filtering: {jsonl_file.name}")
        with open(jsonl_file) as fin, open(output_path, 'w') as fout:
            for line in tqdm(fin, desc=f"Filtering {tier_name}"):
                total += 1
                article = json.loads(line)
                if passes_mesh_filter(article.get('mesh_terms', [])):
                    fout.write(line); kept_mesh += 1; continue
                if passes_keyword_filter(article):
                    fout.write(line); kept_keyword += 1; continue
                dropped += 1
        logger.info(f"Output: {output_path}")

    kept_total = kept_mesh + kept_keyword
    logger.info(f"=== Filtering Complete ===")
    logger.info(f"Total articles processed: {total}")
    logger.info(f"Kept (MeSH match):        {kept_mesh}")
    logger.info(f"Kept (keyword match):     {kept_keyword}")
    logger.info(f"Total retained:           {kept_total}")
    logger.info(f"Dropped:                  {dropped}")
    logger.info(f"Retention rate:           {kept_total / max(total, 1) * 100:.1f}%")

    # Hard fail if retention is far from methodology expectation (§4.2.2)
    if not (RETENTION_MIN <= kept_total <= RETENTION_MAX):
        logger.error(
            f"ABORT: retained {kept_total} articles, outside expected "
            f"[{RETENTION_MIN:,}, {RETENTION_MAX:,}]. "
            f"Likely a regex regression in MeSH or keyword filters. "
            f"Investigate before spending GPU-hours on embeddings."
        )
        sys.exit(1)


if __name__ == '__main__':
    main()
```

### Step 3 — Section-Aware Semantic Chunking (Deterministic IDs)

```python
# ============================================================
# SCRIPT: scripts/corpus/08_section_aware_chunking.py
# PURPOSE: Chunk filtered articles preserving section boundaries
# INPUT:   Filtered JSONL from Step 2
# OUTPUT:  Chunked JSONL ready for embedding
# SPEC:    512 tokens max, 50-token overlap, PubMedBERT tokenizer
# TIME:    ~2-4 hours
#
# v2.1 CHANGE: chunk_id is now uuid.uuid5(NAMESPACE, content_key) — deterministic.
# ============================================================

"""
Section-Aware Semantic Chunking with deterministic chunk IDs.

Per methodology §4.2.2 + §4.1.3 (reproducibility):
- Section boundaries preserved (chunks never span sections).
- Each section: max 512 tokens, 50-token overlap, PubMedBERT tokenizer.
- chunk_id = uuid5(NAMESPACE, "pmcid|section_type|chunk_index|hash(text[:64])")
  → identical inputs ALWAYS yield identical chunk IDs across runs and machines.
"""

import os, sys, json, uuid, hashlib, logging
from pathlib import Path
from tqdm import tqdm
from transformers import AutoTokenizer
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('logs/chunking.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

TOKENIZER_NAME = "NeuML/pubmedbert-base-embeddings"
MAX_TOKENS = int(os.environ.get('CHUNK_MAX_TOKENS', 512))
OVERLAP_TOKENS = int(os.environ.get('CHUNK_OVERLAP_TOKENS', 50))

# Stable namespace UUID for chunk ID derivation (DO NOT CHANGE — would invalidate every existing index).
CHUNK_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")


def deterministic_chunk_id(pmcid: str, section_type: str, chunk_index: int, chunk_text: str) -> str:
    """Identical content ALWAYS yields the same UUID."""
    text_digest = hashlib.blake2b(chunk_text.encode('utf-8'), digest_size=16).hexdigest()
    key = f"{pmcid}|{section_type}|{chunk_index}|{text_digest}"
    return str(uuid.uuid5(CHUNK_NAMESPACE, key))


def chunk_section_text(text: str, tokenizer,
                       max_tokens: int = MAX_TOKENS,
                       overlap_tokens: int = OVERLAP_TOKENS) -> list[str]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= max_tokens:
        return [text]
    chunks = []
    stride = max_tokens - overlap_tokens
    for start in range(0, len(token_ids), stride):
        end = min(start + max_tokens, len(token_ids))
        chunk_text = tokenizer.decode(token_ids[start:end], skip_special_tokens=True).strip()
        if chunk_text:
            chunks.append(chunk_text)
        if end >= len(token_ids):
            break
    return chunks


def process_article(article: dict, tokenizer) -> list[dict]:
    out = []
    pmcid = article['pmcid']
    for section in article.get('sections', []):
        section_type = section.get('section_type', 'other')
        heading = section.get('heading', '')
        text = section.get('text', '')
        if not text or len(text.strip()) < 50:
            continue
        text_chunks = chunk_section_text(text, tokenizer)
        for i, chunk_text in enumerate(text_chunks):
            out.append({
                'chunk_id': deterministic_chunk_id(pmcid, section_type, i, chunk_text),
                'pmcid': pmcid,
                'title': article.get('title', ''),
                'section_type': section_type,
                'section_heading': heading,
                'pub_year': article.get('pub_year'),
                'mesh_terms': article.get('mesh_terms', []),
                'chunk_index': i,
                'total_chunks_in_section': len(text_chunks),
                'text': chunk_text,
            })
    return out


def main():
    logger.info(f"Loading tokenizer: {TOKENIZER_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    logger.info(f"Tokenizer loaded. Vocab size: {tokenizer.vocab_size}")
    logger.info(f"Chunking params: max_tokens={MAX_TOKENS}, overlap={OVERLAP_TOKENS}")

    filtered_dir = Path(os.environ['PMC_FILTERED_DIR'])
    chunks_dir = Path(os.environ['CHUNKS_DIR'])
    chunks_dir.mkdir(parents=True, exist_ok=True)

    total_articles = total_chunks = 0
    for jsonl_file in sorted(filtered_dir.glob('*_filtered.jsonl')):
        tier_name = jsonl_file.stem.replace('_filtered', '')
        output_path = chunks_dir / f'{tier_name}_chunks.jsonl'
        logger.info(f"Chunking: {jsonl_file.name}")
        with open(jsonl_file) as fin, open(output_path, 'w') as fout:
            for line in tqdm(fin, desc=f"Chunking {tier_name}"):
                article = json.loads(line)
                chunks = process_article(article, tokenizer)
                for chunk in chunks:
                    fout.write(json.dumps(chunk) + '\n')
                total_articles += 1
                total_chunks += len(chunks)
        logger.info(f"Output: {output_path}")

    logger.info(f"=== Chunking Complete ===")
    logger.info(f"Total articles chunked:  {total_articles}")
    logger.info(f"Total chunks produced:   {total_chunks}")
    logger.info(f"Average chunks/article:  {total_chunks / max(total_articles, 1):.1f}")


if __name__ == '__main__':
    main()
```

### Step 4 — Embedding Generation (Explicit Seeding)

```python
# ============================================================
# SCRIPT: scripts/embedding/09_generate_embeddings.py
# PURPOSE: Generate PubMedBERT embeddings for all chunks
# INPUT:   Chunked JSONL from Step 3
# OUTPUT:  Parquet shards with chunk metadata + 768-dim embedding bytes
# MODEL:   NeuML/pubmedbert-base-embeddings (768-dim)
# TIME:    ~24-48 hours on a single RTX 5090
#
# v2.1 CHANGE: explicit deterministic seeding via apply_seeds() (§2.2).
# ============================================================

import os, sys, json, logging
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)   # MUST be called before importing torch backend usage

load_dotenv('config/.env')
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('logs/embeddings.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get('EMBEDDING_MODEL', 'NeuML/pubmedbert-base-embeddings')
EMBEDDING_DIM = int(os.environ.get('EMBEDDING_DIM', 768))
BATCH_SIZE = 256                  # Safe for RTX 5090 32 GB
CHECKPOINT_EVERY = 50_000
SHARD_SIZE = 500_000


def main():
    logger.info(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME, device='cuda')
    logger.info(f"Model loaded. Dim: {model.get_sentence_embedding_dimension()}")

    chunks_dir = Path(os.environ['CHUNKS_DIR'])
    output_dir = Path(os.environ['EMBEDDING_DIR'])
    output_dir.mkdir(parents=True, exist_ok=True)

    for jsonl_file in sorted(chunks_dir.glob('*_chunks.jsonl')):
        tier_name = jsonl_file.stem.replace('_chunks', '')
        logger.info(f"Embedding: {jsonl_file.name}")

        chunks, texts = [], []
        with open(jsonl_file) as f:
            for line in f:
                chunk = json.loads(line)
                chunks.append(chunk); texts.append(chunk['text'])
        logger.info(f"Loaded {len(chunks)} chunks from {tier_name}")

        all_embeddings = []
        for batch_start in tqdm(
            range(0, len(texts), BATCH_SIZE),
            desc=f"Embedding {tier_name}",
            total=(len(texts) + BATCH_SIZE - 1) // BATCH_SIZE,
        ):
            batch_texts = texts[batch_start:batch_start + BATCH_SIZE]
            batch_embeddings = model.encode(
                batch_texts, batch_size=BATCH_SIZE, show_progress_bar=False,
                normalize_embeddings=True,    # L2-normalized for cosine
                convert_to_numpy=True,
            )
            all_embeddings.append(batch_embeddings)
            processed = batch_start + len(batch_texts)
            if processed % CHECKPOINT_EVERY == 0:
                logger.info(f"Checkpoint: {processed}/{len(texts)}")

        embeddings_matrix = np.vstack(all_embeddings).astype(np.float32)
        logger.info(f"Embeddings shape: {embeddings_matrix.shape}")

        for shard_idx in range(0, len(chunks), SHARD_SIZE):
            shard_end = min(shard_idx + SHARD_SIZE, len(chunks))
            shard_chunks = chunks[shard_idx:shard_end]
            shard_embeddings = embeddings_matrix[shard_idx:shard_end]
            data = {
                'chunk_id':       [c['chunk_id'] for c in shard_chunks],
                'pmcid':          [c['pmcid'] for c in shard_chunks],
                'title':          [c['title'] for c in shard_chunks],
                'section_type':   [c['section_type'] for c in shard_chunks],
                'section_heading':[c['section_heading'] for c in shard_chunks],
                'pub_year':       [c['pub_year'] for c in shard_chunks],
                'mesh_terms':     [json.dumps(c['mesh_terms']) for c in shard_chunks],
                'chunk_index':    [c['chunk_index'] for c in shard_chunks],
                'text':           [c['text'] for c in shard_chunks],
                'embedding':      [emb.tobytes() for emb in shard_embeddings],
            }
            shard_path = output_dir / f'{tier_name}_shard_{shard_idx // SHARD_SIZE:04d}.parquet'
            pq.write_table(pa.table(data), shard_path)
            logger.info(f"Saved shard: {shard_path} ({shard_end - shard_idx} chunks)")

        logger.info(f"Completed {tier_name}: {len(chunks)} embedded")

    logger.info("=== Embedding Generation Complete ===")


if __name__ == '__main__':
    main()
```

### Step 5 — Create Qdrant Collection and Index (FastEmbed BM25, on-disk payload)

```python
# ============================================================
# SCRIPT: scripts/indexing/10_create_qdrant_index.py
# PURPOSE: Create Qdrant collection with dense HNSW + native BM25 sparse vectors
# INPUT:   Parquet files with embeddings from Step 4
# OUTPUT:  Populated Qdrant collection
# TIME:    ~2-6 hours depending on corpus size
#
# v2.1 CRITICAL CHANGES:
#   * Sparse vectors via fastembed.SparseTextEmbedding("Qdrant/bm25").
#     Replaces v2's broken hash-of-whitespace tokens.
#   * on_disk_payload=True for memory efficiency on 2-5 M chunks.
#   * Document-side embeddings via .embed() (uses TF + IDF).
#     Query-side embeddings (Step 6) use .query_embed() (TF only — BM25 asymmetry).
# ============================================================

import os, sys, json, logging
import numpy as np
import pyarrow.parquet as pq
from pathlib import Path
from tqdm import tqdm
from qdrant_client import QdrantClient, models
from fastembed import SparseTextEmbedding
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('logs/qdrant_index.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

QDRANT_HOST = os.environ.get('QDRANT_HOST', 'localhost')
QDRANT_PORT = int(os.environ.get('QDRANT_PORT', 6333))
COLLECTION_NAME = os.environ.get('COLLECTION_NAME', 'pmc_rare_disease_v1')
EMBEDDING_DIM = int(os.environ.get('EMBEDDING_DIM', 768))
UPLOAD_BATCH_SIZE = 100

# Native Qdrant BM25 — deterministic, biomedical-aware tokenization
BM25_MODEL_NAME = "Qdrant/bm25"


def create_collection(client: QdrantClient):
    collections = client.get_collections().collections
    if any(c.name == COLLECTION_NAME for c in collections):
        logger.warning(f"Collection '{COLLECTION_NAME}' already exists. Skipping creation.")
        logger.warning("To recreate: client.delete_collection(COLLECTION_NAME) first.")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE,
                on_disk=True,
                hnsw_config=models.HnswConfigDiff(
                    m=16, ef_construct=200, full_scan_threshold=10000,
                ),
            ),
        },
        sparse_vectors_config={
            "bm25": models.SparseVectorParams(
                modifier=models.Modifier.IDF,   # IDF weighting handled by Qdrant
            ),
        },
        on_disk_payload=True,                   # v2.1: keep payload off RAM
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000),
    )

    # Payload indices for filterable fields
    client.create_payload_index(
        collection_name=COLLECTION_NAME, field_name="section_type",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME, field_name="pmcid",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME, field_name="pub_year",
        field_schema=models.PayloadSchemaType.INTEGER,
    )

    logger.info(f"Collection '{COLLECTION_NAME}' created (dense HNSW + BM25 sparse, on_disk_payload=True)")


def upload_parquet_files(client: QdrantClient, embedding_dir: Path):
    parquet_files = sorted(embedding_dir.glob('*.parquet'))
    if not parquet_files:
        logger.error(f"No Parquet files found in {embedding_dir}")
        return

    logger.info(f"Found {len(parquet_files)} Parquet shards")
    logger.info(f"Loading BM25 sparse model: {BM25_MODEL_NAME}")
    bm25_model = SparseTextEmbedding(model_name=BM25_MODEL_NAME)

    total_uploaded = 0

    for pq_file in parquet_files:
        logger.info(f"Processing: {pq_file.name}")
        table = pq.read_table(pq_file)
        n_rows = table.num_rows

        for batch_start in tqdm(
            range(0, n_rows, UPLOAD_BATCH_SIZE),
            desc=f"Uploading {pq_file.stem}",
            total=(n_rows + UPLOAD_BATCH_SIZE - 1) // UPLOAD_BATCH_SIZE,
        ):
            batch_end = min(batch_start + UPLOAD_BATCH_SIZE, n_rows)
            batch = table.slice(batch_start, batch_end - batch_start)

            # Materialize batch columns once
            ids       = batch.column('chunk_id').to_pylist()
            pmcids    = batch.column('pmcid').to_pylist()
            titles    = batch.column('title').to_pylist()
            sec_types = batch.column('section_type').to_pylist()
            sec_heads = batch.column('section_heading').to_pylist()
            years     = batch.column('pub_year').to_pylist()
            mesh_strs = batch.column('mesh_terms').to_pylist()
            cidx      = batch.column('chunk_index').to_pylist()
            texts     = batch.column('text').to_pylist()
            emb_bytes = batch.column('embedding').to_pylist()

            # Batch BM25 (document side — uses .embed, NOT .query_embed)
            sparse_embs = list(bm25_model.embed(texts))

            points = []
            for i in range(len(ids)):
                dense = np.frombuffer(emb_bytes[i], dtype=np.float32).tolist()
                sv = sparse_embs[i]
                payload = {
                    'chunk_id':       ids[i],
                    'pmcid':          pmcids[i],
                    'title':          titles[i],
                    'section_type':   sec_types[i],
                    'section_heading':sec_heads[i],
                    'pub_year':       years[i],
                    'mesh_terms':     json.loads(mesh_strs[i]) if mesh_strs[i] else [],
                    'chunk_index':    cidx[i],
                    'text':           texts[i],
                }
                points.append(models.PointStruct(
                    id=ids[i],
                    vector={
                        "dense": dense,
                        "bm25": models.SparseVector(
                            indices=sv.indices.tolist(),
                            values=sv.values.tolist(),
                        ),
                    },
                    payload=payload,
                ))

            client.upsert(collection_name=COLLECTION_NAME, points=points)
            total_uploaded += len(points)

        logger.info(f"Completed {pq_file.name}: {n_rows} points")

    logger.info(f"=== Upload Complete: {total_uploaded} total points ===")


def main():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)
    logger.info(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")

    create_collection(client)

    embedding_dir = Path(os.environ['EMBEDDING_DIR'])
    upload_parquet_files(client, embedding_dir)

    # Modern API: client.count() instead of deprecated vectors_count
    count = client.count(collection_name=COLLECTION_NAME, exact=True).count
    info  = client.get_collection(COLLECTION_NAME)
    logger.info("=== Collection Info ===")
    logger.info(f"Points count:   {count}")
    logger.info(f"Status:         {info.status}")


if __name__ == '__main__':
    main()
```

### Step 6 — Validate Index Integrity (FastEmbed Queries Too)

```python
# ============================================================
# SCRIPT: scripts/indexing/11_validate_index.py
# PURPOSE: Run probe queries for known gene-phenotype associations
#
# v2.1 CRITICAL: BM25 query embeddings use .query_embed() (NOT .embed()).
#   BM25 indexing and querying use different functions — query_embed
#   gives the TF-only query side that pairs with the IDF-weighted index.
# ============================================================

"""
Index Validation — methodology §4.11.5 acceptance criterion 1A:
"5 known gene-phenotype probe queries return ≥1 relevant chunk in top-10".
"""

import os, sys, logging
from pathlib import Path
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

VALIDATION_QUERIES = [
    {"query": "BRCA1 breast cancer hereditary susceptibility",
     "expected_gene": "BRCA1", "expected_topic": "breast cancer"},
    {"query": "CFTR cystic fibrosis chloride channel mutation",
     "expected_gene": "CFTR", "expected_topic": "cystic fibrosis"},
    {"query": "FBN1 Marfan syndrome connective tissue disorder",
     "expected_gene": "FBN1", "expected_topic": "Marfan syndrome"},
    {"query": "HEXA Tay-Sachs disease hexosaminidase deficiency",
     "expected_gene": "HEXA", "expected_topic": "Tay-Sachs"},
    {"query": "PKD1 polycystic kidney disease autosomal dominant",
     "expected_gene": "PKD1", "expected_topic": "polycystic kidney"},
    {"query": "SCN1A Dravet syndrome epilepsy sodium channel",
     "expected_gene": "SCN1A", "expected_topic": "Dravet syndrome"},
    {"query": "TP53 Li-Fraumeni syndrome tumor suppressor cancer predisposition",
     "expected_gene": "TP53", "expected_topic": "Li-Fraumeni"},
]


def validate_dense(client, dense_model, collection):
    logger.info("=== Dense Retrieval Validation ===")
    passed = 0
    for vq in VALIDATION_QUERIES:
        q = dense_model.encode(vq['query'], normalize_embeddings=True).tolist()
        res = client.query_points(
            collection_name=collection, query=q, using="dense",
            limit=10, with_payload=True,
        )
        found_gene  = any(vq['expected_gene'].lower()  in p.payload.get('text','').lower() for p in res.points)
        found_topic = any(vq['expected_topic'].lower() in p.payload.get('text','').lower() for p in res.points)
        ok = found_gene and found_topic
        passed += int(ok)
        logger.info(f"  [{'PASS' if ok else 'FAIL'}] {vq['expected_gene']} / {vq['expected_topic']}  gene={found_gene} topic={found_topic}")
    logger.info(f"Dense retrieval: {passed}/{len(VALIDATION_QUERIES)} passed")
    return passed


def validate_hybrid(client, dense_model, bm25_model, collection):
    logger.info("\n=== Hybrid Retrieval Validation (RRF) ===")
    passed = 0
    for vq in VALIDATION_QUERIES:
        q_dense = dense_model.encode(vq['query'], normalize_embeddings=True).tolist()
        # CRITICAL: query_embed (NOT embed) for BM25 query side
        q_sparse = next(iter(bm25_model.query_embed([vq['query']])))

        res = client.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(query=q_dense, using="dense", limit=20),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=q_sparse.indices.tolist(),
                        values=q_sparse.values.tolist(),
                    ),
                    using="bm25", limit=20,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=10, with_payload=True,
        )
        found_gene  = any(vq['expected_gene'].lower()  in p.payload.get('text','').lower() for p in res.points)
        found_topic = any(vq['expected_topic'].lower() in p.payload.get('text','').lower() for p in res.points)
        ok = found_gene and found_topic
        passed += int(ok)
        logger.info(f"  [{'PASS' if ok else 'FAIL'}] {vq['expected_gene']} / {vq['expected_topic']}")
    logger.info(f"Hybrid retrieval: {passed}/{len(VALIDATION_QUERIES)} passed")
    return passed


def validate_section_filter(client, dense_model, collection):
    logger.info("\n=== Section-Type Filtering Validation ===")
    q = dense_model.encode("BRCA1 breast cancer mutation", normalize_embeddings=True).tolist()
    for st in ['abstract', 'results', 'case_report', 'discussion']:
        res = client.query_points(
            collection_name=collection, query=q, using="dense",
            query_filter=models.Filter(must=[
                models.FieldCondition(key="section_type", match=models.MatchValue(value=st)),
            ]),
            limit=5, with_payload=True,
        )
        logger.info(f"  Section '{st}': {len(res.points)} results")


def main():
    client = QdrantClient(
        host=os.environ.get('QDRANT_HOST', 'localhost'),
        port=int(os.environ.get('QDRANT_PORT', 6333)),
    )
    collection = os.environ.get('COLLECTION_NAME', 'pmc_rare_disease_v1')

    dense_model = SentenceTransformer(
        os.environ.get('EMBEDDING_MODEL', 'NeuML/pubmedbert-base-embeddings'),
        device='cuda',
    )
    bm25_model  = SparseTextEmbedding(model_name="Qdrant/bm25")

    d = validate_dense(client, dense_model, collection)
    h = validate_hybrid(client, dense_model, bm25_model, collection)
    validate_section_filter(client, dense_model, collection)

    n = len(VALIDATION_QUERIES)
    logger.info(f"\n{'='*60}\nVALIDATION SUMMARY")
    logger.info(f"Dense:  {d}/{n}")
    logger.info(f"Hybrid: {h}/{n}")
    if d >= n - 1 and h >= n - 1:
        logger.info("STATUS: PASS — Phase 1A index ready for Phase 1B")
    else:
        logger.warning("STATUS: REVIEW NEEDED — investigate before running Phase 1B")
        sys.exit(1)


if __name__ == '__main__':
    main()
```

---

## 5. ONTOLOGY VERIFICATION (Post-Download Sanity Checks)

```python
# ============================================================
# SCRIPT: scripts/ontology/12_verify_ontologies.py
# PURPOSE: Verify all downloaded ontological resources load correctly
# ============================================================

import os, sys, logging
import pandas as pd
import pronto
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def verify_hpo():
    logger.info("=== Verifying HPO ===")
    d = Path(os.environ['ONTOLOGY_DIR']) / 'hpo'
    hpo = pronto.Ontology(str(d / 'hp.obo'))
    terms = [t for t in hpo.terms() if t.id.startswith('HP:')]
    logger.info(f"HPO terms loaded: {len(terms)}")
    test = hpo.get('HP:0001250')  # Seizure
    if test:
        logger.info(f"Test term: {test.id} — {test.name}")
        parents = list(test.superclasses(distance=1, with_self=False))
        logger.info(f"  Parents: {[f'{p.id} ({p.name})' for p in parents[:3]]}")
        synonyms = [s.description for s in test.synonyms]
        logger.info(f"  Synonyms: {synonyms[:5]}")
    g2p = pd.read_csv(d / 'genes_to_phenotype.txt', sep='\t', comment='#')
    p2g = pd.read_csv(d / 'phenotype_to_genes.txt', sep='\t', comment='#')
    logger.info(f"genes_to_phenotype: {len(g2p)} rows")
    logger.info(f"phenotype_to_genes: {len(p2g)} rows")


def verify_mondo():
    logger.info("\n=== Verifying MONDO ===")
    mondo = pronto.Ontology(str(Path(os.environ['ONTOLOGY_DIR']) / 'mondo' / 'mondo.obo'))
    terms = [t for t in mondo.terms() if t.id.startswith('MONDO:')]
    logger.info(f"MONDO terms loaded: {len(terms)}")
    for tid in ['MONDO:0007947', 'MONDO:0005071', 'MONDO:0005066', 'MONDO:0005046']:
        t = mondo.get(tid)
        if t: logger.info(f"  {t.id} — {t.name}")


def verify_go():
    logger.info("\n=== Verifying GO ===")
    d = Path(os.environ['ONTOLOGY_DIR']) / 'go'
    go = pronto.Ontology(str(d / 'go.obo'))
    logger.info(f"GO terms loaded: {len(list(go.terms()))}")
    gaf = pd.read_csv(
        d / 'goa_human.gaf', sep='\t', comment='!', header=None,
        names=['DB','DB_Object_ID','DB_Object_Symbol','Qualifier','GO_ID','DB_Reference',
               'Evidence_Code','With_From','Aspect','DB_Object_Name','DB_Object_Synonym',
               'DB_Object_Type','Taxon','Date','Assigned_By','Annotation_Extension',
               'Gene_Product_Form_ID'],
        low_memory=False,
    )
    logger.info(f"GO human annotations: {len(gaf)} rows; unique genes: {gaf['DB_Object_Symbol'].nunique()}")


def verify_hgnc():
    logger.info("\n=== Verifying HGNC ===")
    hgnc = pd.read_csv(Path(os.environ['HGNC_DIR']) / 'hgnc_complete_set.txt', sep='\t')
    logger.info(f"HGNC total entries: {len(hgnc)}")
    pc = hgnc[hgnc['locus_group'] == 'protein-coding gene']
    logger.info(f"Protein-coding genes: {len(pc)}")
    logger.info(f"Sample: {list(pc['symbol'].head(10))}")


def main():
    verify_hpo(); verify_mondo(); verify_go(); verify_hgnc()
    logger.info("\n=== All Verifications Complete ===")


if __name__ == '__main__':
    main()
```

---

## 6. TEST CASE PREPARATION — Phase 1B (NEW)

This section corresponds to methodology §§4.2.1, 4.6 Phase 1B, and acceptance criteria 1B and 1C in §4.11.5. Phase 1B **requires Phase 1A to be complete** because step 5 below queries the Qdrant index to verify the causal-gene PMC coverage.

The full pipeline produces a single canonical artifact: **`data/test_cases/test_cases.jsonl`** — one line per test case, consumed unchanged by all six experimental conditions C1–C6.

### Step 1 — Phenopacket Ingest

```python
# ============================================================
# SCRIPT: scripts/cases/13_load_phenopackets.py
# PURPOSE: Load all phenopacket JSON files from the v0.1.19 release
# INPUT:   data/phenopackets/v0.1.19/**/*.json
# OUTPUT:  data/test_cases/01_all_phenopackets.jsonl
# ============================================================

"""
Load every phenopacket JSON file from the pinned Phenopacket-store release
and emit a single normalized JSONL with the fields the rest of Phase 1B needs:

{
  "case_id":     "<cohort>:<file_stem>",
  "source_path": "data/phenopackets/v0.1.19/.../foo.json",
  "subject_id":  "patient-001",
  "hpo_terms":   ["HP:0001250", ...],         # observed only (excluded=False)
  "diseases":    [{"id": "OMIM:154700", "label": "..."}, ...],
  "interpretations": [
      {"gene_symbol": "FBN1", "hgnc_id": "HGNC:3603",
       "variant": "...", "ascertained": true}
  ]
}
"""

import os, sys, json, logging
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler('logs/phase1b_ingest.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

VERSION = os.environ['PHENOPACKET_STORE_VERSION']
PPKT_ROOT = Path(os.environ['PHENOPACKET_DIR']) / f"v{VERSION}"
OUT_DIR = Path(os.environ['TEST_CASES_DIR']); OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "01_all_phenopackets.jsonl"


def extract_hpo_terms(pp: dict) -> list[str]:
    """Return only observed (non-excluded) HPO term IDs."""
    out = []
    for pf in pp.get('phenotypicFeatures', []):
        if pf.get('excluded'):
            continue
        type_ = pf.get('type', {})
        tid = type_.get('id')
        if tid and tid.startswith('HP:'):
            out.append(tid)
    # Deduplicate, preserve order
    seen = set(); deduped = []
    for t in out:
        if t not in seen:
            deduped.append(t); seen.add(t)
    return deduped


def extract_diseases(pp: dict) -> list[dict]:
    out = []
    for d in pp.get('diseases', []):
        if d.get('excluded'):
            continue
        term = d.get('term', {})
        out.append({'id': term.get('id'), 'label': term.get('label')})
    return out


def extract_interpretations(pp: dict) -> list[dict]:
    """
    Extract the causal genetic interpretation(s).

    Phenopacket schema v2 stores diagnoses under
    interpretations[].diagnosis.genomicInterpretations[]
    Each genomic interpretation has .variantInterpretation
    .variationDescriptor.geneContext (gene symbol + HGNC ID).
    """
    out = []
    for interp in pp.get('interpretations', []):
        diag = interp.get('diagnosis', {})
        for gi in diag.get('genomicInterpretations', []):
            status = gi.get('interpretationStatus', '')
            vi = gi.get('variantInterpretation', {})
            vd = vi.get('variationDescriptor', {})
            gc = vd.get('geneContext', {})
            symbol = gc.get('symbol')
            value_id = gc.get('valueId') or ''
            if symbol:
                out.append({
                    'gene_symbol': symbol,
                    'hgnc_id':     value_id if value_id.startswith('HGNC:') else None,
                    'variant':     vd.get('label') or vd.get('id', ''),
                    'ascertained': status in ('CAUSATIVE', 'CONTRIBUTORY', ''),
                })
    return out


def main():
    json_files = sorted(PPKT_ROOT.rglob('*.json'))
    if not json_files:
        logger.error(f"No JSON files under {PPKT_ROOT}. Did §3.4 unzip succeed?")
        sys.exit(1)
    logger.info(f"Found {len(json_files)} phenopacket JSON files under {PPKT_ROOT}")

    n_in = n_out = 0
    with open(OUT_PATH, 'w') as fout:
        for jf in tqdm(json_files, desc="Loading phenopackets"):
            n_in += 1
            try:
                pp = json.loads(jf.read_text(encoding='utf-8'))
            except Exception as e:
                logger.warning(f"Skipped (parse error) {jf}: {e}")
                continue

            cohort = jf.parent.name
            case_id = f"{cohort}:{jf.stem}"

            record = {
                'case_id': case_id,
                'source_path': str(jf.relative_to(Path(os.environ['PROJECT_ROOT']))),
                'subject_id': pp.get('subject', {}).get('id'),
                'hpo_terms': extract_hpo_terms(pp),
                'diseases': extract_diseases(pp),
                'interpretations': extract_interpretations(pp),
            }
            fout.write(json.dumps(record) + '\n')
            n_out += 1

    logger.info(f"=== Ingest Complete ===")
    logger.info(f"JSON files seen:    {n_in}")
    logger.info(f"Records written:    {n_out}")
    logger.info(f"Output:             {OUT_PATH}")

    # Methodology says the v0.1.19 store has 6,668 phenopackets
    if not (6000 <= n_out <= 7500):
        logger.warning(f"Record count {n_out} is far from the methodology's 6,668. Investigate.")


if __name__ == '__main__':
    main()
```

### Step 2 — Inclusion/Exclusion Filter

```python
# ============================================================
# SCRIPT: scripts/cases/14_apply_inclusion_exclusion.py
# PURPOSE: Apply methodology §4.2.1 inclusion/exclusion criteria
# INPUT:   data/test_cases/01_all_phenopackets.jsonl
# OUTPUT:  data/test_cases/02_eligible.jsonl
#
# Inclusion (all required):
#   * ≥3 observed HPO terms                  → MIN_HPO_TERMS
#   * Confirmed pathogenic variant in a single gene
#
# Exclusion (any disqualifies):
#   * Chromosomal aberrations
#   * Mitochondrial diseases
# ============================================================

import os, sys, json, logging
from pathlib import Path
import pronto
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler('logs/phase1b_filter.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

MIN_HPO = int(os.environ.get('MIN_HPO_TERMS', 3))
TC_DIR = Path(os.environ['TEST_CASES_DIR'])
IN_PATH  = TC_DIR / "01_all_phenopackets.jsonl"
OUT_PATH = TC_DIR / "02_eligible.jsonl"

# MONDO term IDs used as exclusion roots
EXCLUDE_MONDO_ROOTS = {
    "MONDO:0019042",  # chromosomal disorder
    "MONDO:0044970",  # mitochondrial disease
}


def build_exclude_descendant_set(mondo: pronto.Ontology) -> set[str]:
    """All MONDO descendants of the exclusion roots (plus the roots themselves)."""
    excluded = set()
    for root_id in EXCLUDE_MONDO_ROOTS:
        root = mondo.get(root_id)
        if root is None:
            logger.warning(f"MONDO term {root_id} not found in ontology; check MONDO_VERSION.")
            continue
        for term in root.subclasses(with_self=True):
            excluded.add(term.id)
    return excluded


def disease_id_to_mondo(disease_id: str, mondo: pronto.Ontology) -> str | None:
    """
    Resolve OMIM/Orphanet disease IDs to MONDO via xref.
    Cheap O(N) scan because phenopacket disease counts are small per case.
    """
    if disease_id is None:
        return None
    if disease_id.startswith('MONDO:'):
        return disease_id
    # Lookup via xref
    for term in mondo.terms():
        for x in term.xrefs:
            if x.id == disease_id:
                return term.id
    return None


def main():
    mondo = pronto.Ontology(str(Path(os.environ['ONTOLOGY_DIR']) / 'mondo' / 'mondo.obo'))
    excluded_ids = build_exclude_descendant_set(mondo)
    logger.info(f"Exclusion set size: {len(excluded_ids)} MONDO terms")

    # Build a once-per-process xref → MONDO map (faster than re-scanning per case)
    xref_to_mondo: dict[str, str] = {}
    for term in mondo.terms():
        for x in term.xrefs:
            xref_to_mondo.setdefault(x.id, term.id)

    n_in = n_kept = 0
    drop_reasons = {'few_hpo': 0, 'no_single_gene': 0, 'multi_gene': 0,
                    'excluded_disease': 0, 'no_disease': 0}

    with open(IN_PATH) as fin, open(OUT_PATH, 'w') as fout:
        for line in fin:
            n_in += 1
            r = json.loads(line)

            # Inclusion: ≥3 HPO terms
            if len(r['hpo_terms']) < MIN_HPO:
                drop_reasons['few_hpo'] += 1; continue

            # Inclusion: exactly one ascertained causal gene
            asc = [g for g in r['interpretations'] if g.get('ascertained')]
            unique_genes = {g['gene_symbol'] for g in asc if g.get('gene_symbol')}
            if len(unique_genes) == 0:
                drop_reasons['no_single_gene'] += 1; continue
            if len(unique_genes) > 1:
                drop_reasons['multi_gene'] += 1; continue
            causal_gene = next(iter(unique_genes))

            # Exclusion: chromosomal / mitochondrial diseases
            if not r['diseases']:
                drop_reasons['no_disease'] += 1; continue
            mondo_ids = []
            for d in r['diseases']:
                m = d['id'] if d['id'] and d['id'].startswith('MONDO:') else xref_to_mondo.get(d['id'])
                if m: mondo_ids.append(m)
            if any(m in excluded_ids for m in mondo_ids):
                drop_reasons['excluded_disease'] += 1; continue

            r['causal_gene'] = causal_gene
            r['mondo_ids'] = mondo_ids
            fout.write(json.dumps(r) + '\n')
            n_kept += 1

    logger.info(f"=== Filtering Complete ===")
    logger.info(f"Input cases:    {n_in}")
    logger.info(f"Eligible cases: {n_kept}")
    for k, v in drop_reasons.items():
        logger.info(f"  Dropped — {k}: {v}")


if __name__ == '__main__':
    main()
```

### Step 3 — MONDO-Based Disease Categorization

```python
# ============================================================
# SCRIPT: scripts/cases/15_categorize_by_mondo.py
# PURPOSE: Assign each eligible case to one of the 4 disease categories
#          (methodology §4.2.1: neurological, metabolic, immunological, developmental).
# INPUT:   data/test_cases/02_eligible.jsonl
# OUTPUT:  data/test_cases/03_categorized.jsonl
# ============================================================

"""
Category roots in MONDO:
  neurological:   MONDO:0005071  ('nervous system disorder')
  metabolic:      MONDO:0005066  ('metabolic disease')
  immunological:  MONDO:0005046  ('immune system disorder')
  developmental:  MONDO:0021147  ('inborn genetic disease')
                  + MONDO:0019118 ('developmental and epileptic encephalopathy')
                  We treat 'developmental' as the broad bucket of inborn
                  genetic diseases that are NOT in the other three buckets
                  (this catches congenital malformation syndromes, etc.).

Cases falling into multiple categories are assigned to the FIRST matching
category in priority order: neurological > metabolic > immunological > developmental.
This is recorded in the case record as `category_resolution`.
"""

import os, sys, json, logging
from pathlib import Path
import pronto
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler('logs/phase1b_categorize.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

CATEGORY_ROOTS = [
    ('neurological',  ['MONDO:0005071']),
    ('metabolic',     ['MONDO:0005066']),
    ('immunological', ['MONDO:0005046']),
    ('developmental', ['MONDO:0021147', 'MONDO:0019118']),
]

TC_DIR = Path(os.environ['TEST_CASES_DIR'])
IN_PATH = TC_DIR / "02_eligible.jsonl"
OUT_PATH = TC_DIR / "03_categorized.jsonl"


def descendants(mondo: pronto.Ontology, root_ids: list[str]) -> set[str]:
    s = set()
    for rid in root_ids:
        r = mondo.get(rid)
        if r is None:
            logger.warning(f"MONDO {rid} not found")
            continue
        for t in r.subclasses(with_self=True):
            s.add(t.id)
    return s


def main():
    mondo = pronto.Ontology(str(Path(os.environ['ONTOLOGY_DIR']) / 'mondo' / 'mondo.obo'))
    cat_sets = [(name, descendants(mondo, roots)) for name, roots in CATEGORY_ROOTS]
    for name, s in cat_sets:
        logger.info(f"Category '{name}': {len(s)} MONDO descendants")

    counts = {name: 0 for name, _ in cat_sets}
    counts['unmatched'] = 0
    n_in = n_out = 0

    with open(IN_PATH) as fin, open(OUT_PATH, 'w') as fout:
        for line in fin:
            n_in += 1
            r = json.loads(line)
            mids = set(r.get('mondo_ids', []))
            assigned = None
            for name, s in cat_sets:
                if mids & s:
                    assigned = name; break
            if assigned is None:
                counts['unmatched'] += 1
                continue   # Drop unmatched — not in any of the 4 strata
            r['category'] = assigned
            r['category_resolution'] = 'first-matching priority order'
            fout.write(json.dumps(r) + '\n')
            counts[assigned] += 1
            n_out += 1

    logger.info(f"=== Categorization Complete ===")
    logger.info(f"Input:  {n_in}")
    logger.info(f"Output: {n_out}")
    for k, v in counts.items():
        logger.info(f"  {k:<14}: {v}")


if __name__ == '__main__':
    main()
```

### Step 4 — Stratified Random Sampling (50–100 cases, seed=42)

```python
# ============================================================
# SCRIPT: scripts/cases/16_stratified_sample.py
# PURPOSE: Sample N cases stratified across the 4 disease categories
# INPUT:   data/test_cases/03_categorized.jsonl
# OUTPUT:  data/test_cases/04_sampled.jsonl
# ============================================================

"""
Methodology §4.2.1: 'Stratified random sampling across four disease
categories ... ensuring representativeness'.

We allocate proportionally to category availability when the eligible
pool is small in some categories, and use ceiling-rounded equal-quartile
allocation (~SAMPLE_TARGET_SIZE/4) where availability allows.

All randomness derives from RANDOM_SEED for reproducibility.
"""

import os, sys, json, math, random, logging
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler('logs/phase1b_sample.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

CATEGORIES = ['neurological', 'metabolic', 'immunological', 'developmental']
TARGET = int(os.environ.get('SAMPLE_TARGET_SIZE', 75))

TC_DIR = Path(os.environ['TEST_CASES_DIR'])
IN_PATH = TC_DIR / "03_categorized.jsonl"
OUT_PATH = TC_DIR / "04_sampled.jsonl"


def main():
    by_cat = defaultdict(list)
    with open(IN_PATH) as f:
        for line in f:
            r = json.loads(line)
            by_cat[r['category']].append(r)

    # Sort within category for deterministic ordering before sampling
    for c in by_cat:
        by_cat[c].sort(key=lambda r: r['case_id'])
        logger.info(f"Eligible in '{c}': {len(by_cat[c])}")

    # Equal allocation, capped by availability
    per_cat = math.ceil(TARGET / len(CATEGORIES))
    sample = []
    rng = random.Random(int(os.environ.get('RANDOM_SEED', 42)))

    for c in CATEGORIES:
        pool = by_cat.get(c, [])
        n = min(per_cat, len(pool))
        chosen = rng.sample(pool, n)
        sample.extend(chosen)
        logger.info(f"  Sampled {n} from '{c}'")

    # If we over-shot the target slightly, trim the last category
    if len(sample) > TARGET:
        rng.shuffle(sample)
        sample = sample[:TARGET]

    with open(OUT_PATH, 'w') as f:
        for r in sample:
            f.write(json.dumps(r) + '\n')

    logger.info(f"=== Sampling Complete ===")
    logger.info(f"Final sample size: {len(sample)}")
    cat_dist = defaultdict(int)
    for r in sample:
        cat_dist[r['category']] += 1
    for c in CATEGORIES:
        logger.info(f"  {c}: {cat_dist[c]}")


if __name__ == '__main__':
    main()
```

### Step 5 — PMC Causal-Gene Coverage Validation (≥5 articles)

```python
# ============================================================
# SCRIPT: scripts/cases/17_validate_pmc_coverage.py
# PURPOSE: Per methodology §4.2.1, every selected case's causal gene
#          must have ≥5 associated publications in the PMC OA filtered corpus.
#          Cases failing this are REPLACED from the eligible pool.
# INPUT:   data/test_cases/04_sampled.jsonl  (current sample)
#          data/test_cases/03_categorized.jsonl (replacement pool)
# OUTPUT:  data/test_cases/05_validated.jsonl
# ============================================================

"""
For each candidate causal gene, query the Phase 1A Qdrant index for
the gene symbol and count distinct PMCIDs returned.

If <MIN_PMC_ARTICLES_PER_GENE distinct PMCIDs:
  the case is dropped and replaced with another case of the same
  category drawn from the eligible pool, deterministically.
"""

import os, sys, json, logging, random
from collections import defaultdict, Counter
from pathlib import Path
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler('logs/phase1b_pmc_coverage.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

MIN_PMC = int(os.environ.get('MIN_PMC_ARTICLES_PER_GENE', 5))
COLLECTION = os.environ.get('COLLECTION_NAME', 'pmc_rare_disease_v1')

TC_DIR = Path(os.environ['TEST_CASES_DIR'])
SAMPLE_PATH      = TC_DIR / "04_sampled.jsonl"
ELIGIBLE_PATH    = TC_DIR / "03_categorized.jsonl"
OUT_PATH         = TC_DIR / "05_validated.jsonl"


def gene_pmc_count(client, dense_model, bm25_model, gene_symbol: str, k: int = 100) -> int:
    """Count distinct PMCIDs returned by a hybrid query for the gene symbol."""
    q_dense = dense_model.encode(gene_symbol, normalize_embeddings=True).tolist()
    q_sparse = next(iter(bm25_model.query_embed([gene_symbol])))
    res = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(query=q_dense, using="dense", limit=k),
            models.Prefetch(
                query=models.SparseVector(
                    indices=q_sparse.indices.tolist(),
                    values=q_sparse.values.tolist()),
                using="bm25", limit=k,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k, with_payload=True,
    )
    return len({p.payload.get('pmcid') for p in res.points if p.payload.get('pmcid')})


def main():
    client = QdrantClient(host=os.environ.get('QDRANT_HOST', 'localhost'),
                          port=int(os.environ.get('QDRANT_PORT', 6333)))
    dense_model = SentenceTransformer(os.environ['EMBEDDING_MODEL'], device='cuda')
    bm25_model  = SparseTextEmbedding(model_name="Qdrant/bm25")

    sample = [json.loads(l) for l in open(SAMPLE_PATH)]
    eligible_pool = defaultdict(list)
    for line in open(ELIGIBLE_PATH):
        r = json.loads(line)
        eligible_pool[r['category']].append(r)
    sample_ids = {r['case_id'] for r in sample}
    rng = random.Random(int(os.environ.get('RANDOM_SEED', 42)))

    validated: list[dict] = []
    rejected = []
    replacements_made = 0
    unreplaced = 0

    # First pass: validate the initial sample
    for r in sample:
        n_pmc = gene_pmc_count(client, dense_model, bm25_model, r['causal_gene'])
        r['pmc_article_count'] = n_pmc
        if n_pmc >= MIN_PMC:
            validated.append(r)
        else:
            rejected.append(r)
            logger.info(f"REJECT {r['case_id']} (causal {r['causal_gene']}, only {n_pmc} PMCIDs)")

    # Replacement loop
    for rej in rejected:
        category = rej['category']
        pool = [c for c in eligible_pool[category] if c['case_id'] not in sample_ids]
        rng.shuffle(pool)
        replaced = False
        for cand in pool:
            n_pmc = gene_pmc_count(client, dense_model, bm25_model, cand['causal_gene'])
            cand['pmc_article_count'] = n_pmc
            if n_pmc >= MIN_PMC:
                validated.append(cand)
                sample_ids.add(cand['case_id'])
                logger.info(f"REPLACE {rej['case_id']} → {cand['case_id']} ({n_pmc} PMCIDs)")
                replaced = True
                replacements_made += 1
                break
        if not replaced:
            unreplaced += 1
            logger.warning(f"NO REPLACEMENT found for {rej['case_id']} in category '{category}'")

    with open(OUT_PATH, 'w') as f:
        for r in validated:
            f.write(json.dumps(r) + '\n')

    logger.info(f"=== PMC Coverage Validation Complete ===")
    logger.info(f"Initial sample:    {len(sample)}")
    logger.info(f"Rejected:          {len(rejected)}")
    logger.info(f"Replaced:          {replacements_made}")
    logger.info(f"Could not replace: {unreplaced}")
    logger.info(f"Final validated:   {len(validated)}")
    cat_counts = Counter(r['category'] for r in validated)
    for c, n in cat_counts.items():
        logger.info(f"  {c}: {n}")


if __name__ == '__main__':
    main()
```

### Step 6 — Candidate Gene List Builder (1 causal + 49 distractors, seed=42)

```python
# ============================================================
# SCRIPT: scripts/cases/18_build_candidate_lists.py
# PURPOSE: For each validated case, build the 50-gene candidate list:
#          1 true causal gene + 49 HGNC-approved protein-coding distractors.
# INPUT:   data/test_cases/05_validated.jsonl
#          data/hgnc/hgnc_complete_set.txt
# OUTPUT:  data/test_cases/06_with_candidates.jsonl
#
# Per methodology §4.2.1: distractor selection uses RANDOM_SEED=42.
# We derive a deterministic per-case seed from the global seed + case_id
# so that re-sampling a single case is reproducible without re-sampling all.
# ============================================================

import os, sys, json, hashlib, random, logging
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler('logs/phase1b_candidates.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

N_DISTRACTORS = int(os.environ.get('N_DISTRACTORS', 49))
GLOBAL_SEED   = int(os.environ.get('RANDOM_SEED', 42))

TC_DIR = Path(os.environ['TEST_CASES_DIR'])
IN_PATH  = TC_DIR / "05_validated.jsonl"
OUT_PATH = TC_DIR / "06_with_candidates.jsonl"


def per_case_seed(case_id: str) -> int:
    """Deterministic seed derived from global seed + case_id."""
    h = hashlib.blake2b(f"{GLOBAL_SEED}|{case_id}".encode(), digest_size=8).digest()
    return int.from_bytes(h, 'big')


def main():
    # Load HGNC protein-coding symbols
    hgnc_path = Path(os.environ['HGNC_DIR']) / 'hgnc_complete_set.txt'
    hgnc = pd.read_csv(hgnc_path, sep='\t')
    pc = hgnc[hgnc['locus_group'] == 'protein-coding gene']
    all_symbols = sorted(pc['symbol'].dropna().unique().tolist())   # SORTED for determinism
    logger.info(f"HGNC protein-coding symbols available: {len(all_symbols)}")

    n_in = n_out = 0
    with open(IN_PATH) as fin, open(OUT_PATH, 'w') as fout:
        for line in fin:
            n_in += 1
            r = json.loads(line)
            causal = r['causal_gene']

            # Pool excludes the causal gene
            pool = [s for s in all_symbols if s != causal]

            rng = random.Random(per_case_seed(r['case_id']))
            distractors = rng.sample(pool, N_DISTRACTORS)

            # Final candidate list = causal + distractors, then shuffled with same RNG
            # to avoid a positional bias that an RNG-aware system could exploit.
            candidates = [causal] + distractors
            rng.shuffle(candidates)

            r['candidate_genes'] = candidates
            r['n_candidates'] = len(candidates)
            r['causal_gene_index_in_candidates'] = candidates.index(causal)
            fout.write(json.dumps(r) + '\n')
            n_out += 1

    logger.info(f"=== Candidate Lists Built ===")
    logger.info(f"Cases in:  {n_in}")
    logger.info(f"Cases out: {n_out}")
    logger.info(f"Each candidate list: 1 causal + {N_DISTRACTORS} distractors (= 50)")


if __name__ == '__main__':
    main()
```

### Step 7 — Persist Canonical Test-Case Manifest

```python
# ============================================================
# SCRIPT: scripts/cases/19_finalize_test_cases.py
# PURPOSE: Emit data/test_cases/test_cases.jsonl — the single artifact
#          consumed by every experimental condition C1-C6.
# INPUT:   data/test_cases/06_with_candidates.jsonl
# OUTPUT:  data/test_cases/test_cases.jsonl
#          data/test_cases/test_cases_manifest.json
# ============================================================

import os, sys, json, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler('logs/phase1b_finalize.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

TC_DIR = Path(os.environ['TEST_CASES_DIR'])
IN_PATH  = TC_DIR / "06_with_candidates.jsonl"
OUT_PATH = TC_DIR / "test_cases.jsonl"
MANIFEST = TC_DIR / "test_cases_manifest.json"


def main():
    cases = [json.loads(l) for l in open(IN_PATH)]
    # Sort by case_id for canonical ordering
    cases.sort(key=lambda r: r['case_id'])

    # Project to the canonical schema consumed by C1-C6
    canonical = []
    for r in cases:
        canonical.append({
            'case_id':           r['case_id'],
            'category':          r['category'],
            'hpo_terms':         r['hpo_terms'],
            'diseases':          r['diseases'],
            'causal_gene':       r['causal_gene'],
            'candidate_genes':   r['candidate_genes'],
            'pmc_article_count': r['pmc_article_count'],
            'source_phenopacket': r['source_path'],
        })

    with open(OUT_PATH, 'w') as f:
        for r in canonical:
            f.write(json.dumps(r) + '\n')

    sha = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    cat_dist = Counter(r['category'] for r in canonical)
    manifest = {
        'created_at_utc':          datetime.now(timezone.utc).isoformat(),
        'phenopacket_store_version': os.environ['PHENOPACKET_STORE_VERSION'],
        'mondo_version':            os.environ['MONDO_VERSION'],
        'hgnc_snapshot':            os.environ['HGNC_SNAPSHOT'],
        'random_seed':              int(os.environ['RANDOM_SEED']),
        'n_cases':                  len(canonical),
        'category_distribution':    dict(cat_dist),
        'min_hpo_terms':            int(os.environ['MIN_HPO_TERMS']),
        'min_pmc_articles_per_gene':int(os.environ['MIN_PMC_ARTICLES_PER_GENE']),
        'n_distractors_per_case':   int(os.environ['N_DISTRACTORS']),
        'output_path':              str(OUT_PATH.relative_to(Path(os.environ['PROJECT_ROOT']))),
        'sha256':                   sha,
        'bytes':                    OUT_PATH.stat().st_size,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    logger.info(f"=== Phase 1B Complete ===")
    logger.info(f"Final test cases: {OUT_PATH} ({len(canonical)} cases, sha256={sha[:16]}…)")
    logger.info(f"Manifest:         {MANIFEST}")
    logger.info(f"Category distribution: {dict(cat_dist)}")


if __name__ == '__main__':
    main()
```

### Step 8 — Validate Final Test Set (Acceptance Gate)

```python
# ============================================================
# SCRIPT: scripts/cases/20_validate_test_cases.py
# PURPOSE: Acceptance gate per methodology §4.11.5 (1B + 1C):
#   * Every case has ≥3 HPO terms                              [1B]
#   * Every case has 50 unique candidate genes (1 causal + 49) [1B]
#   * Every case's causal gene is in its candidate_genes        [1B]
#   * Every case's causal gene has ≥5 PMC articles             [1B]
#   * Sample is balanced across the 4 MONDO categories (±20%)  [1B]
# INPUT:  data/test_cases/test_cases.jsonl
# EXIT:   0 if all checks pass, 1 otherwise.
# ============================================================

import os, sys, json, logging
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.seed import apply_seeds
apply_seeds(42)

load_dotenv('config/.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

CATEGORIES = ['neurological', 'metabolic', 'immunological', 'developmental']
PATH = Path(os.environ['TEST_CASES_DIR']) / "test_cases.jsonl"
MIN_HPO = int(os.environ['MIN_HPO_TERMS'])
MIN_PMC = int(os.environ['MIN_PMC_ARTICLES_PER_GENE'])
N_DISTRACTORS = int(os.environ['N_DISTRACTORS'])
EXPECTED_CANDIDATES = N_DISTRACTORS + 1


def main():
    cases = [json.loads(l) for l in open(PATH)]
    failures = []

    for c in cases:
        if len(c['hpo_terms']) < MIN_HPO:
            failures.append(f"{c['case_id']}: only {len(c['hpo_terms'])} HPO terms (<{MIN_HPO})")
        if len(set(c['candidate_genes'])) != EXPECTED_CANDIDATES:
            failures.append(f"{c['case_id']}: {len(set(c['candidate_genes']))} unique candidates (expected {EXPECTED_CANDIDATES})")
        if c['causal_gene'] not in c['candidate_genes']:
            failures.append(f"{c['case_id']}: causal gene {c['causal_gene']} missing from candidates")
        if c['pmc_article_count'] < MIN_PMC:
            failures.append(f"{c['case_id']}: only {c['pmc_article_count']} PMC articles for causal (<{MIN_PMC})")

    # Category balance: each category within 20% of expected per-category share
    cat = Counter(c['category'] for c in cases)
    expected = len(cases) / len(CATEGORIES)
    tol = 0.20 * expected
    for c_name in CATEGORIES:
        if abs(cat.get(c_name, 0) - expected) > tol:
            failures.append(f"category '{c_name}' has {cat.get(c_name, 0)} cases (expected {expected:.0f} ± {tol:.0f})")

    logger.info(f"Validated {len(cases)} cases.")
    logger.info(f"Category distribution: {dict(cat)}")

    if failures:
        logger.error(f"FAILED ({len(failures)} issues):")
        for f in failures[:50]:
            logger.error(f"  - {f}")
        if len(failures) > 50:
            logger.error(f"  ... and {len(failures) - 50} more")
        sys.exit(1)

    logger.info("STATUS: PASS — Phase 1B test set ready for experimentation")


if __name__ == '__main__':
    main()
```

---

## 7. EXECUTION ORDER — Claude Code Checklist (Updated for v2.1)

Execute the scripts in this exact order. Each step depends on the previous one.

**CRITICAL: Tier-by-Tier Streaming Strategy for the 700 GB Linux Constraint**

Do NOT download and decompress all 400-500 GB at once. Process each PMC license tier sequentially through the full pipeline, then delete intermediates before starting the next tier.

```
PHASE 1A: DATABASE CREATION (must complete before Phase 1B)

[1] Create project structure (§1)
     └── Linux:   ~/rare-disease-rag/
     └── Windows: /mnt/c/pmc_workspace/

[2] Set up Python env + verify Qdrant + write seed util (§§2, 2.2)
     ├── pip install … (note: qdrant-client[fastembed] + fastembed)
     ├── docker ps | grep qdrant
     └── scripts/utils/seed.py (deterministic seeding helper)

[3] Download ontologies (PINNED), HGNC (PINNED snapshot) — §§3.2, 3.3
     ├── scripts/ontology/02_download_ontologies.sh    (~5 min, < 100 MB)
     ├── scripts/ontology/03_download_hgnc.sh          (~1 min, < 10 MB)
     └── scripts/ontology/12_verify_ontologies.py      (~2 min)

[4] Create empty Qdrant collection (FastEmbed BM25, on_disk_payload):
     └── scripts/indexing/10_create_qdrant_index.py   (collection only)

[5] TIER-BY-TIER CORPUS PIPELINE (repeat for each license tier):
    ┌─────────────────────────────────────────────────────────────┐
    │ For TIER in oa_comm, oa_noncomm, oa_other:                 │
    │                                                             │
    │ [5a] Download TIER → /mnt/c/pmc_workspace/xml_raw/TIER     │
    │      ~40-50 GB compressed per tier                          │
    │                                                             │
    │ [5b] Parse JATS XML → JSONL on /mnt/c/                     │
    │      scripts/corpus/06_parse_jats_xml.py    (~1.5-3 hrs)   │
    │                                                             │
    │ [5c] Filter corpus → JSONL on /mnt/c/                      │
    │      scripts/corpus/07_filter_corpus.py     (~10-20 min)   │
    │      ABORTS if retention not in [100K, 600K]               │
    │                                                             │
    │ [5d] Chunk sections (DETERMINISTIC chunk_ids) → /mnt/c/    │
    │      scripts/corpus/08_section_aware_chunking.py (~1-2 hrs)│
    │                                                             │
    │ [5e] Generate embeddings (with seeds applied) → /mnt/c/    │
    │      scripts/embedding/09_generate_embeddings.py(~8-16 hrs)│
    │                                                             │
    │ [5f] Upload to Qdrant via FastEmbed BM25                   │
    │      scripts/indexing/10_create_qdrant_index.py (~1-2 hrs) │
    │                                                             │
    │ [5g] *** DELETE /mnt/c/pmc_workspace/ contents ***          │
    │      Frees ~200 GB for the next tier                       │
    └─────────────────────────────────────────────────────────────┘

[6] Validate complete index (FastEmbed query_embed for BM25):
     └── scripts/indexing/11_validate_index.py        (~5 min)

[7] Write acquisition manifest (SHA-256 of every input asset):
     └── scripts/utils/05_write_manifest.sh

CHECKPOINT 1A: Phase 1A complete. Qdrant has the corpus, validated.

────────────────────────────────────────────────────────────────────
PHASE 1B: TEST CASE PREPARATION (depends on Phase 1A)

[8]  Download Phenopacket-store v0.1.19 (PINNED release tarball)
     └── scripts/cases/04_download_phenopacket_store.sh

[9]  Ingest all phenopackets → 01_all_phenopackets.jsonl
     └── scripts/cases/13_load_phenopackets.py

[10] Apply inclusion/exclusion criteria → 02_eligible.jsonl
     └── scripts/cases/14_apply_inclusion_exclusion.py

[11] MONDO-based categorization → 03_categorized.jsonl
     └── scripts/cases/15_categorize_by_mondo.py

[12] Stratified random sampling (seed=42) → 04_sampled.jsonl
     └── scripts/cases/16_stratified_sample.py

[13] PMC coverage validation + replacement → 05_validated.jsonl
     └── scripts/cases/17_validate_pmc_coverage.py
     (queries the Phase 1A Qdrant index)

[14] Build candidate gene lists (1 + 49) → 06_with_candidates.jsonl
     └── scripts/cases/18_build_candidate_lists.py

[15] Finalize canonical test_cases.jsonl + manifest
     └── scripts/cases/19_finalize_test_cases.py

[16] Acceptance gate (must pass before any experiment runs):
     └── scripts/cases/20_validate_test_cases.py

CHECKPOINT 1B: Phase 1B complete.
  Inputs ready for C1-C6:
    data/test_cases/test_cases.jsonl
    data/test_cases/test_cases_manifest.json
    data/MANIFEST.tsv

────────────────────────────────────────────────────────────────────
PHASE 2: AGENTIC UI LAYER (depends on Phase 1A + 1B)

[17] Scaffold src/agents/ — state schema (AgentState dataclass) +
     four agent node stubs (Query Planner, Retriever, Critic, Synthesizer)
     └── src/agents/{state.py, query_planner.py, retriever.py,
                     critic.py, synthesizer.py, graph.py}

[18] Implement Query Planner — HPO expansion via pronto, MeSH lookup
     └── src/tools/hpo.py · scripts/eval/probe_query_planner.py

[19] Implement Retriever — Qdrant hybrid search wrapper with RRF +
     payload filters (section_type / pmcid / pub_year)
     └── src/tools/qdrant_search.py · scripts/eval/probe_retriever.py

[20] Implement Critic — relevance grader, HGNC alias validator,
     evidence-type classifier
     └── src/tools/hgnc.py · src/tools/critic_grader.py

[21] Implement Synthesizer — per-gene aggregation + re-ranking with
     citation extraction
     └── src/agents/synthesizer.py

[22] Wire LangGraph state graph + conditional self-correction edges
     └── src/agents/graph.py + tests/agents/test_graph_smoke.py

[23] Stand up Qwen3-8B in vLLM, smoke test 4-agent flow on demo Qdrant
     collection (1,625 chunks). Validate ≥5 tok/s under multi-agent load.
     └── docker-compose.vllm.yml · scripts/eval/smoke_demo.py

[24] FastAPI + copilotkit-sdk-python wrapper
     └── src/api/main.py · curl smoke test against /api/agent/run

[25] CopilotKit React frontend (Phase 2c)
     ├── cd frontend && npx copilotkit@latest create -f next
     ├── Add geno_agent/ component package: HPOPicker, CandidateGeneList,
     │   AgentTracePanel, GeneCandidateCard, CitationHover
     └── End-to-end demo: HPO selection in browser → ranked output

[26] 2x2+1 evaluation harness on Phase 1B test cases
     └── scripts/eval/run_factorial.py
         (cells A-D: single/multi-agent x dense-only/hybrid; cell E: Exomiser)

[27] Generate LaTeX results tables + thesis figures from eval output
     └── scripts/eval/render_results.py → results/{tables,figures}/

CHECKPOINT 2: Phase 2 complete. Defense-grade UI + evaluation results
              ready for thesis manuscript.
```

### Disk Usage Estimates (WSL2 Dual-Drive)

```
LINUX FILESYSTEM (~700 GB available):
  ~/rare-disease-rag/
  ├── qdrant_storage/              300-500 GB  (grows tier by tier)
  ├── models/                       ~16 GB    (Qwen3 + PubMedBERT)
  ├── data/ontologies+hgnc/         < 1 GB
  ├── data/phenopackets/v0.1.19/    < 100 MB
  ├── data/test_cases/              < 10 MB
  ├── .venv/                        ~3 GB
  ├── code + config + logs          < 1 GB
  └── TOTAL PERSISTENT:             ~320-520 GB  ✓ fits in 700 GB

WINDOWS FILESYSTEM (/mnt/c/pmc_workspace/):
  Peak per tier:                    ~200 GB
  After cleanup:                    0 GB
```

Estimated total time: ~5–9 days for Phase 1A + ~1–2 hours for Phase 1B (excluding corpus build).

---

## 8. KEY DESIGN DECISIONS AND RATIONALE

### Why deterministic chunk IDs (UUID5) instead of UUID4?

Methodology §4.1.3 declares reproducibility a first-class requirement: identical inputs must yield byte-identical outputs. UUID4 (random) breaks this — re-running the chunker on the same corpus produces a completely different set of point IDs in Qdrant, invalidating any downstream artifact that pins to a specific chunk. UUID5 derived from `(pmcid, section_type, chunk_index, content_hash)` makes the ID a pure function of the content.

### Why FastEmbed `Qdrant/bm25` instead of a hash-based sparse vector?

v2 used Python's salted `hash()` over whitespace-tokenized lowercased text. Three independent failures resulted: (a) `hash()` is randomized per Python process unless `PYTHONHASHSEED` is fixed, so the index identity of every token would change between runs; (b) whitespace splitting destroys biomedical tokens like `BRCA1/2`, `c.35delG`, `p.Arg175His`; (c) hash collisions further degrade IDF weighting. `Qdrant/bm25` provides deterministic indices, biomedical-aware tokenization, and the document/query asymmetry that the BM25 algorithm actually requires (`.embed()` for documents, `.query_embed()` for queries — different functions).

### Why pin every ontology version?

Methodology §4.2.3 explicitly pins HPO to v2026-02-16. The OBO Foundry's `latest` URLs always serve the most recent release, so v2's downloads would silently drift over time, breaking any future reproduction attempt. Pinning every ontology to a release tag (and hashing the file in MANIFEST.tsv) ensures that a re-run six months from now downloads literally the same bytes.

### Why 512 tokens and not larger chunks?

The methodology explicitly states: "The 512-token limit matches PubMedBERT's maximum sequence length; longer chunks would be silently truncated and lose information." This is a hard constraint from the embedding model architecture.

### Why 50-token overlap?

Overlap prevents information loss at chunk boundaries. A sentence that straddles two chunks will appear (at least partially) in both. The 50-token overlap (~10% of chunk size) balances redundancy against storage overhead.

### Why section-aware chunking instead of naive chunking?

The methodology emphasizes that "text from each section is chunked independently, preserving section boundaries." This means a chunk will never span from a Methods section into a Results section. Critical because:
- Section type is a filterable metadata field in Qdrant
- The Retriever Agent can restrict searches to specific sections
- Mixing section types in a single chunk creates noisy, low-quality context

### Why both dense AND sparse indices?

Gene symbols like `TP53` or `BRCA1` are short lexical tokens that dense embeddings may not match precisely. BM25 (sparse) catches these exact keyword matches. Reciprocal Rank Fusion (RRF) combines both signals, yielding better retrieval than either alone.

### Why store text in the payload, and on disk?

The Critic Agent needs to read the actual text of retrieved chunks to assess relevance. The Synthesizer Agent needs the text to generate evidence summaries with citations. Storing text in the payload avoids a second lookup against the original corpus. With ~2–5 M chunks each carrying ~2 KB of payload, that's 4–10 GB; setting `on_disk_payload=True` keeps RAM bounded without sacrificing the ability to retrieve text inline.

### Why a per-case derived seed for distractor sampling (Phase 1B)?

Using a single global RNG to sample distractors for all cases means resampling a single case forces resampling of all subsequent cases (the RNG state advances). Deriving a per-case seed from `blake2b(global_seed | case_id)` lets us regenerate any single case's candidate list in isolation while remaining fully deterministic.

### Why MONDO categorization with a priority order?

A single disease can map to multiple MONDO categories (e.g., a metabolic disorder with neurological symptoms). The methodology's stratification needs each case in exactly one stratum. We resolve overlaps by a fixed priority `neurological > metabolic > immunological > developmental` and record the resolution in the case record so it's transparent in the audit trail.

---

## 9. TROUBLESHOOTING

| Issue | Likely Cause | Fix |
|-------|--------------|-----|
| AWS S3 download fails | Network/firewall | Use `--no-sign-request` flag; try NCBI FTP as fallback |
| JATS XML parse errors | Malformed XML in PMC | Parser has try/except; check logs for error rate |
| Out of GPU VRAM during embedding | Batch size too large | Reduce `BATCH_SIZE` in Step 4 (try 128 or 64) |
| Qdrant upload timeouts | Too many points per batch | Reduce `UPLOAD_BATCH_SIZE` in Step 5 |
| Qdrant disk full | Index overhead ~2x data | Ensure 500 GB free on Linux partition |
| Filter abort: retention out of range | MeSH/keyword regex regression | Inspect filtered output, relax/tighten patterns, re-run |
| `pronto` fails on OBO file | Encoding or format issue | Try `obonet` as fallback for networkx graph |
| Slow I/O on /mnt/c/ | WSL2 9P filesystem overhead | Normal — bulk processing tolerates it; NEVER put Qdrant there |
| CUDA not found in WSL2 | Missing NVIDIA WSL2 driver | Install NVIDIA CUDA driver for WSL from nvidia.com |
| Docker not working in WSL2 | Docker Desktop not configured | Enable WSL2 backend in Docker Desktop → Settings → Resources |
| Existing Qdrant collection conflict | Same collection name | Check `curl localhost:6333/collections`; use unique `COLLECTION_NAME` |
| Linux disk filling up mid-pipeline | Intermediates on Linux | Move all intermediates to /mnt/c/; keep ONLY qdrant_storage on Linux |
| **HPO release URL 404** | **`HPO_VERSION` is wrong/unavailable** | **Check https://github.com/obophenotype/human-phenotype-ontology/releases** |
| **HGNC quarterly snapshot 404** | **`HGNC_SNAPSHOT` date doesn't exist** | **Browse https://storage.googleapis.com/public-download-files/hgnc/archive/archive/quarterly/tsv/** |
| **`pronto` finds 0 MONDO category descendants** | **MONDO term IDs changed between versions** | **Verify `MONDO:0005071` etc. exist in your `MONDO_VERSION`; update IDs in Step 3 if needed** |
| **Phenopacket ingest yields 0 interpretations** | **Schema v1 vs v2 difference; field names changed** | **Inspect a sample JSON; adjust `extract_interpretations()` paths accordingly** |
| **PMC coverage validation rejects most cases** | **Causal genes obscure or filter too aggressive** | **Lower `MIN_PMC_ARTICLES_PER_GENE` temporarily, inspect rejected cases, decide if filter relaxation is needed** |
| **Sample categories unbalanced after replacement** | **One category exhausted in eligible pool** | **Increase eligible pool by relaxing `MIN_HPO_TERMS`, OR reduce `SAMPLE_TARGET_SIZE`** |
| **`fastembed` model download fails** | **First-run cache miss / no network** | **Pre-warm: `python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')"`** |
| **Determinism warning from `torch.use_deterministic_algorithms`** | **Op without deterministic CUDA implementation** | **Expected with `warn_only=True`; embedding determinism is preserved at the model.encode level** |

---

## 10. DEVIATIONS FROM METHODOLOGY (v2.1)

These are intentional deviations from the literal text of Chapter 4 v3, with rationale. All are recorded here so a peer reviewer can locate them quickly.

| Methodology Spec | Implementation | Rationale |
|------------------|----------------|-----------|
| §4.2.2 — "using `xml.etree.ElementTree`" | We use `lxml` | ~10× faster on 4M articles, more namespace-robust, tractable for the project budget. Output is byte-equivalent JSONL. |
| §4.2.2 — "sparse (BM25) index for lexical keyword matching" (no library specified) | We use Qdrant's native BM25 via `fastembed.SparseTextEmbedding("Qdrant/bm25")` | Not a deviation in spirit — this is the canonical Qdrant-native BM25. v2.1 explicitly names the implementation for transparency. |
| §4.2.1 — "50–100 cases" (open range) | We default to `SAMPLE_TARGET_SIZE=75` | Midpoint of the methodology range; configurable in `.env`. |
| §4.2.1 — "stratified random sampling across four disease categories" | Equal allocation per category, capped at availability, with category-priority resolution for cases mapping to multiple categories | Resolves the implicit ambiguity of multi-category MONDO mappings deterministically; recorded per-case in `category_resolution`. |
| §4.2.1 — "approved by HGNC" | We snapshot HGNC (`HGNC_SNAPSHOT=2026-04-07`) instead of using the rolling current set | Required for byte-reproducibility per §4.1.3; falls back to current set with a warning if the snapshot is unavailable. |
| §3 / §4.2.3 — pinned 2024 ontology releases | Updated pins to 2026 releases: HPO `v2026-02-16`, MONDO `v2026-03-03`, GO `2026-03-25`, HGNC `2026-04-07` | Project executed in 2026; the 2024 versions referenced in v2.1 are out of date. SHA-256 of all files recorded in `data/MANIFEST.tsv`. |
| §3.1 — bucket layout `s3://pmc-oa-opendata/{oa_comm,oa_noncomm,oa_other}/xml/all/` | Bucket is now flat: `s3://pmc-oa-opendata/PMC<id>.<version>/<files>` with no tier-prefix directories (license tier lives only in each per-article JSON metadata file). NCBI HTTPS bulk fallback at `https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/` returned 404 on 2026-05-09 — deprecated earlier than the master plan's stated August 2026. | Verified directly with `aws s3api list-objects-v2` against the public bucket on 2026-05-09. **Implication:** master plan §7's "tier-by-tier streaming" (download `oa_comm` → process → delete → next tier) is replaced by a single full-corpus XML-only sync via `--exclude '*' --include '*/*.xml'`. License-tier classification, if needed for analysis, is done downstream by reading `PMC<id>.<version>.json`. Total disk impact unchanged (~150 GB). Implemented in `scripts/corpus/01_download_pmc_oa.sh` with `--limit N` and `--dry-run` modes for partial syncs and previews. |
| HGNC download URL (EBI FTP) | Switched to Google Cloud Storage bucket `public-download-files` with flat archive layout | HGNC migrated all archive files from EBI FTP to GCS; the original FTP archive paths now return 404. New URL pattern: `https://storage.googleapis.com/public-download-files/hgnc/archive/archive/quarterly/tsv/hgnc_complete_set_${HGNC_SNAPSHOT}.txt`. |
| §2 line 176 — `python3.11 -m venv .venv` | Use system `python3.12.3`; no project-local `.venv` | Python 3.11 is not installed on the host; 3.12 is the only available interpreter and is fully compatible with every pinned dep. `requires-python = ">=3.12,<3.13"` recorded in `pyproject.toml`. |
| §2 line 189 — `pip install torch ... --index-url https://download.pytorch.org/whl/cu124` | Pinned to `torch==2.9.0.dev20250820+cu128` (and matching torchvision/torchaudio nightlies) | The host's RTX 5090 is Blackwell (sm_120) and requires CUDA 12.8+. cu124 wheels fail at first kernel launch on this hardware. The cu128 nightly is the working configuration validated by the user prior to this project. |
| §2 — fresh project-local `.venv` | Reuse existing `/home/hana77/pytorch-env/` (Python 3.12.3) | Avoids re-downloading ~5 GB of cu128 torch wheels into a duplicate venv. `pyproject.toml` is the source of truth: it pins every project-relevant dep to the exact version actually installed in `pytorch-env`, and `pip freeze > requirements.lock.txt` snapshots the full env when needed. The project is NOT installed via `pip install -e .` to keep the shared env clean. |
| §11.4 — `pip install vllm` into `pytorch-env` | **Deferred to a separate venv (or driver upgrade).** vLLM 0.20.1 (the only version on PyPI as of 2026-05-09) hard-pins `torch==2.11.0+cu130`. Installing it into `pytorch-env` overwrote the cu128 nightly torch with a cu130 build that the host's NVIDIA driver (CUDA 12.9) cannot use, breaking `torch.cuda.is_available()` for the entire env including PubMedBERT. Recovery: force-reinstalled `torch==2.12.0.dev20260407+cu128` (the original `2.9.0.dev20250820+cu128` had rotated off the nightly index — a forced bump). The `transformers`, `tokenizers`, and `openai` packages were also bumped by vLLM's deps and could not be cleanly rolled back; pins were updated in `pyproject.toml`. | Recorded 2026-05-09 during step C7b. **Implication:** the local LLM client (`src/tools/llm.py`) and operational scripts (`scripts/eval/start_vllm.sh`, `scripts/eval/probe_vllm.py`) ship in this PR; the actual vLLM serving will be enabled in C7c via either (a) a NVIDIA driver upgrade to a CUDA 13-capable build (>=545.x), (b) installing vLLM in a dedicated venv with its own `torch==2.11+cu130` while keeping `pytorch-env` on cu128 nightly for embedding, or (c) Ollama as a development fallback per §11.1 ("Ollama is acceptable for development iteration"). The wrapper code is interface-compatible with all three. |
| §2 line 189 — exact torch nightly pinned | Bumped 2026-05-09 from `torch==2.9.0.dev20250820+cu128` to `torch==2.12.0.dev20260407+cu128` (matching torchvision/torchaudio) | The original 2025-08-20 nightly had aged off the PyTorch nightly index after the vLLM install required a clean reinstall. The 2026-04-07 nightly is the closest available cu128 build at restore time. All 200 unit tests pass on the bumped version; CUDA available + RTX 5090 detected. |

### Resolved reconciliations

- **Qdrant client/server version match (resolved in §7 step [4]).** `docker-compose.yml` was bumped from `qdrant/qdrant:v1.12.4` → `qdrant/qdrant:v1.14.1` to align with `qdrant-client==1.14.3` in pytorch-env. v1.14.1 is the highest server tag in the v1.14.x line (no v1.14.3 server release exists). Bump performed before any collection had data, so no migration was required.

- **Factorial cell letter remapping (Phase 2d, 2026-05-14 → 2026-05-15).** The original §11.5 names *Cell E* as the Exomiser baseline. Phase 2d added six LLM-augmented cells in alphabetical order *after* the deterministic 2×2, pushing Exomiser from E to K. Phase 2e (§11.8, added 2026-05-15) reserves L-O for the cross-encoder re-ranker cells. Final layout: A–D deterministic 2×2 · E–F LLM-Planner · G–H LLM-Critic · I–J LLM-both · K Exomiser (deferred) · L–O re-ranker (proposed). The §11.5 prose still describes the original 2×2+1 design; this remapping is an additive extension, not a replacement.

### Phase 2 design choices (added 2026-05-09)

| Methodology spec | Implementation | Rationale |
|---|---|---|
| §0 — local LLM unspecified | Pinned to **Qwen3-8B Instruct** via **vLLM** | 8B params fit RTX 5090 32 GB VRAM with headroom for KV cache and PubMedBERT. Strong biomedical reasoning vs comparable open-weights models. vLLM gives ≥5 tok/s under agent load; Ollama acceptable as dev fallback. |
| §0 — UI unspecified | **CopilotKit** React framework, sourced from the user's fork [`github.com/Jangulo7/agent_UI`](https://github.com/Jangulo7/agent_UI) (upstream `CopilotKit/CopilotKit`) | Co-author of the **AG-UI protocol** with LangChain. First-class LangGraph integration via `copilotkit-sdk-python`. Ships chat UI, generative UI, shared-state, and human-in-the-loop primitives that map 1-to-1 to the Critic/Synthesizer agent outputs. MIT-licensed, fully self-hostable. |
| §2 — Python only | Adds **Node.js + npm** under `frontend/` | CopilotKit is React-based. The frontend is a standalone npm project that communicates with the FastAPI backend over loopback HTTP+SSE. Python remains the only required language for Phase 1A and Phase 1B. |
| §0 — agent orchestration unspecified | **LangGraph** state graph with conditional self-correction edges | Native to CopilotKit's AG-UI streaming. Native dataclass state schema. The conditional re-entry to the Retriever is the "agentic" capability that single-pass RAG cannot reproduce. |

---

## 11. PHASE 2 — AGENTIC UI LAYER (added 2026-05-09)

Phase 2 wraps the Phase 1A retrieval substrate and the Phase 1B test cases in a **four-agent LangGraph orchestration**, exposes it via FastAPI using `copilotkit-sdk-python`, and ships a **CopilotKit-based React UI** (forked from `CopilotKit/CopilotKit` at [`github.com/Jangulo7/agent_UI`](https://github.com/Jangulo7/agent_UI)) that surfaces agent reasoning to a clinician-style end user. Phase 2 is the visible product of the thesis and the basis for the defense demo.

**Hard precondition:** Phase 1A and Phase 1B must complete first (per `CLAUDE.md`). Phase 2c can be developed against the Phase 1A *demo* Qdrant collection (1,625 chunks) for iteration; the production index plus the Phase 1B benchmark are required for the formal evaluation in §11.5.

### 11.0 Phase 2 architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  CopilotKit React UI  (frontend/, sourced from Jangulo7/agent_UI)  │
│  geno_agent components: HPOPicker · CandidateGeneList ·             │
│                         AgentTracePanel · GeneCandidateCard ·       │
│                         CitationHover                                │
└────────────────────────┬────────────────────────────────────────────┘
                         │ HTTP + SSE (CopilotKit AG-UI protocol)
┌────────────────────────▼────────────────────────────────────────────┐
│  FastAPI app  (src/api/main.py) + copilotkit-sdk-python             │
│  /api/agent/run · /api/agent/stream · /api/health                   │
└────────────────────────┬────────────────────────────────────────────┘
                         │ LangGraph state-graph invocation
┌────────────────────────▼────────────────────────────────────────────┐
│  LangGraph state graph  (src/agents/graph.py)                       │
│   ┌──────────────┐  ┌────────────┐  ┌────────┐  ┌────────────┐      │
│   │QueryPlanner  │→ │  Retriever │→ │ Critic │→ │ Synthesizer│      │
│   │HPO expansion │  │Qdrant      │  │relevance│ │rerank +    │      │
│   │MeSH queries  │  │hybrid+RRF  │  │grading  │ │cite        │      │
│   └──────────────┘  └────────────┘  └────┬───┘  └─────┬──────┘      │
│                                          │             │             │
│                          ┌───────────────┘             │             │
│                          ▼ (low-confidence loop)       ▼             │
│                  back to Retriever (max 3 iter)      END             │
└────────────────────────┬────────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────────┐
│  Qdrant 1A · HPO/MONDO/HGNC ontologies · PubMedBERT · Qwen3-8B/vLLM │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.1 Phase 2a — LangGraph state graph (~1 week)

#### Reasoning model

**Qwen3-8B Instruct** served via **vLLM** on the same RTX 5090 the
retrieval pipeline uses. VRAM budget at peak load:

| Component | VRAM |
|---|---|
| Qwen3-8B (FP16) | ~16 GB |
| vLLM KV cache + paged-attention scratch | ~8–12 GB |
| PubMedBERT (FP32, kept resident for query encoding) | ~440 MB |
| Qdrant query overhead (CPU-side) | 0 GB |
| **Total / 32 GB available** | **~25–28 GB (fits 5090 with headroom)** |

Fallback if Qwen3-8B is unavailable: any open-weights ~8B instruction
model (Llama-3.1-8B-Instruct, Mistral-7B-Instruct-v0.3). Must be
local — no cloud LLM dependency per master plan §0.

vLLM is mandatory for the §11.5 evaluation runs (latency budget); Ollama
is acceptable for development iteration.

#### Agent roster and tools

| Agent | Role | Tool catalog |
|---|---|---|
| **Query Planner** | Receives patient HPO terms + candidate genes; expands HPO via parent-term traversal; generates MeSH-style query strings. | `hpo_expand(hpo_id, distance=2)`, `mesh_lookup(symbol)` |
| **Retriever** | For each `(HPO subset, candidate gene)` pair, runs Qdrant hybrid search (dense + BM25 + RRF) with payload filters on `section_type` / `pmcid` / `pub_year`. | `qdrant_hybrid_search(query, gene_filter, top_k)` |
| **Critic** | Grades each retrieved chunk for: (a) gene-mention validity (HGNC alias check), (b) phenotype-gene association strength (1–5 ordinal), (c) evidence type (case report / functional / association / review). | `hgnc_validate(symbol)`, `relevance_grade(chunk, hpo_terms, gene)` |
| **Synthesizer** | Aggregates Critic grades into per-gene confidence; produces a re-ranked candidate list with cited supporting passages. Returns structured output for UI rendering. | (none — pure aggregation) |

#### State schema

```python
# src/agents/state.py — schematic
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class RetrievedChunk:
    chunk_id: str
    pmcid: str
    text: str
    section_type: str
    score_dense: float
    score_bm25: float
    score_rrf: float

@dataclass
class CriticGrade:
    chunk_id: str
    gene_mention_valid: bool
    relevance: int  # 1..5
    evidence_type: Literal["case_report", "functional", "association", "review", "unknown"]
    rationale: str

@dataclass
class GeneCandidate:
    symbol: str
    is_causal: bool                  # ground truth, Phase 1B only
    aggregate_confidence: float
    supporting_chunks: list[str]     # chunk_ids
    final_rank: int

@dataclass
class AgentState:
    case_id: str
    hpo_terms: list[str]
    candidate_genes: list[str]       # 50 from Phase 1B (1 causal + 49 distractors)
    expanded_hpo: list[str] = field(default_factory=list)
    mesh_queries: list[str] = field(default_factory=list)
    retrieved: dict[str, list[RetrievedChunk]] = field(default_factory=dict)
    grades: dict[str, list[CriticGrade]] = field(default_factory=dict)
    ranked: list[GeneCandidate] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 3
```

#### Graph construction (LangGraph)

```python
# src/agents/graph.py — schematic
from langgraph.graph import StateGraph, END

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("query_planner", query_planner_node)
    graph.add_node("retriever",     retriever_node)
    graph.add_node("critic",        critic_node)
    graph.add_node("synthesizer",   synthesizer_node)

    graph.set_entry_point("query_planner")
    graph.add_edge("query_planner", "retriever")
    graph.add_edge("retriever",     "critic")
    graph.add_conditional_edges(
        "critic",
        # Re-enter retriever if many low-confidence grades remain and budget allows
        lambda s: ("retriever"
                   if s.iteration < s.max_iterations
                      and count_low_confidence(s) > 5
                   else "synthesizer"),
    )
    graph.add_edge("synthesizer", END)
    return graph.compile()
```

The conditional re-entry into the Retriever is the **self-correction
loop** that single-pass RAG architectures cannot reproduce. It is the
empirical contribution of the multi-agent design (cell C vs cell A in
the §11.5 factorial).

### 11.2 Phase 2b — FastAPI + copilotkit-sdk-python (~2 days)

`src/api/main.py` wraps the compiled LangGraph in a FastAPI app that
speaks the **AG-UI protocol** via `copilotkit-sdk-python`. The React UI
talks to it over Server-Sent Events so agent traces stream in real time.

```python
# src/api/main.py — schematic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from copilotkit import CopilotKitSDK, LangGraphAgent
from src.agents.graph import build_graph

app = FastAPI(title="geno_agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"], allow_headers=["*"],
)

sdk = CopilotKitSDK(agents=[
    LangGraphAgent(name="prioritizer", graph=build_graph()),
])
sdk.attach(app, path="/api/agent")
```

Endpoints (auto-mounted by `sdk.attach`):

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/agent/run` | One-shot run, returns final `GeneCandidate[]` |
| `GET` | `/api/agent/stream` | SSE stream of `AgentState` updates per node |
| `GET` | `/api/health` | Liveness probe (returns Qdrant + vLLM health) |

Run with `uvicorn src.api.main:app --reload --port 8000`.

### 11.3 Phase 2c — CopilotKit React UI (~3–5 days)

#### Source and adoption

The CopilotKit framework lives at the user's fork
[`github.com/Jangulo7/agent_UI`](https://github.com/Jangulo7/agent_UI) (upstream
`CopilotKit/CopilotKit`). **Adoption decision: standalone clone**, *not* git submodule:

| Option | Tradeoff |
|---|---|
| **A.** Git submodule of `agent_UI` | One command to update; adds submodule complexity to `git clone`. |
| **B. (chosen)** Standalone clone; `frontend/` in geno_agent contains only geno_agent-specific React components | Cleanest separation. Two repos to manage but each stays small. CopilotKit framework is consumed via `npm install @copilotkit/react-core` like any other npm dep. |
| **C.** Vendored copy (drop `.git`) | Self-contained but loses upstream updates. |

**`frontend/`** in this repo is initialized from the CopilotKit project template (`npx copilotkit@latest create -f next`) and adds the geno_agent-specific components below. The `agent_UI` fork is kept around as a reference and source of upstream patches if framework hacking ever becomes necessary.

#### geno_agent custom components (`frontend/src/geno_agent/`)

| Component | Purpose |
|---|---|
| `<HPOPicker>` | Multi-select with autocomplete fed by the local `hp.obo`; supports synonym matching and parent-term hover. |
| `<CandidateGeneList>` | Editable list of HGNC symbols (paste-friendly; validates against `data/hgnc/hgnc_complete_set.txt`). |
| `<AgentTracePanel>` | Live timeline of LangGraph state transitions (Query Planner → Retriever → Critic [→ Retriever]* → Synthesizer). |
| `<GeneCandidateCard>` | Per-gene tile in the ranked output: symbol, aggregate confidence, supporting-passage carousel, citation links to PMC. |
| `<CitationHover>` | Hover-card showing the exact retrieved chunk with section type and PMC ID; click opens PMC article. |

#### Wiring (Next.js page)

```tsx
// frontend/app/page.tsx — schematic
"use client";
import { CopilotKit, useCoAgent } from "@copilotkit/react-core";
import { HPOPicker, CandidateGeneList,
         AgentTracePanel, GeneCandidateCard } from "@/geno_agent";

export default function PrioritizerPage() {
  const { state, run } = useCoAgent({
    name: "prioritizer",
    initialState: { hpo_terms: [], candidate_genes: [] },
  });
  return (
    <CopilotKit runtimeUrl="http://localhost:8000/api/agent">
      <HPOPicker onChange={(hpo) => state.setHPO(hpo)} />
      <CandidateGeneList onChange={(g) => state.setGenes(g)} />
      <button onClick={() => run({ hpo_terms: state.hpo, candidate_genes: state.genes })}>
        Prioritize
      </button>
      <AgentTracePanel events={state.events} />
      <div className="grid grid-cols-2 gap-4">
        {state.ranked.map((c) => (
          <GeneCandidateCard key={c.symbol} candidate={c} />
        ))}
      </div>
    </CopilotKit>
  );
}
```

### 11.4 Hardware co-location

Single RTX 5090 hosts everything:

- **Qwen3-8B + vLLM** (~16 GB FP16 weights + ~8–12 GB KV cache)
- **PubMedBERT** (~440 MB, kept resident for query encoding)
- **Qdrant** (CPU-side, `on_disk_payload=True`, bind-mounted to `~/rare-disease-rag/qdrant_storage/`)
- **FastAPI** (CPU-side, ~50 MB)
- **CopilotKit dev server** (Node.js, CPU-side, ~200 MB)

Network is loopback only (no public exposure). The only TCP ports
opened are :3000 (Next.js dev), :8000 (FastAPI), :6533 (Qdrant REST),
:6534 (Qdrant gRPC), and whatever vLLM picks (default :8001).

### 11.5 Evaluation harness — 2×2+1 factorial

Hypothesis: the multi-agent architecture *and* hybrid retrieval each
contribute meaningfully to gene-prioritization performance. The
evaluation isolates each contribution.

| | Dense-only retrieval | Dense + BM25 (hybrid) |
|---|---|---|
| **Single-agent** (one-shot Synthesizer over retrieved chunks) | **Cell A** — control | **Cell B** — retrieval contribution |
| **Multi-agent** (Planner + Retriever + Critic + Synthesizer) | **Cell C** — architecture contribution | **Cell D** — full system |

**Cell E:** [Exomiser](https://exomiser.readthedocs.io) baseline —
HPO-driven prioritization without literature evidence; the established
gold standard for phenotype-driven gene ranking.

For each Phase 1B case (50–100 cases per master plan §6), all five
cells produce a ranked list of the 50 candidate genes (1 causal + 49
HGNC distractors, seed = 42). Metrics:

- **Top-1 accuracy** — fraction of cases with causal gene at rank 1
- **Top-5 / Top-10 accuracy**
- **Mean reciprocal rank (MRR)**
- **NDCG@10**

Statistical significance: paired bootstrap over cases (1000 resamples,
95 % CI). Output: a single LaTeX-ready results table per metric +
per-cell confidence intervals + per-cell error analysis grouped by
MONDO category.

### 11.6 Acceptance criteria — Phase 2 done = ALL of

- [ ] `src/agents/graph.py` builds a 4-node LangGraph that produces
  `GeneCandidate[]` from `(hpo_terms, candidate_genes)` input.
- [ ] `tests/agents/` has unit tests for each agent node with mocked
  retrieval, asserting expected state transitions.
- [ ] Qwen3-8B (or fallback) loads in vLLM and serves the agents at
  ≥ 5 tokens/s under multi-agent load on the RTX 5090.
- [ ] `src/api/main.py` exposes the graph via `/api/agent/*` and
  passes a `curl`-driven smoke test with one Phase 1B case.
- [ ] CopilotKit React frontend runs at `http://localhost:3000`
  and successfully prioritizes a Phase 1B test case end-to-end (HPO
  selection → ranked output with cited passages).
- [ ] Evaluation harness (`scripts/eval/`) produces the 2×2+1 results
  table with all Phase 1B cases and statistical CIs.
- [ ] `data/MANIFEST.tsv` updated with a `models/` section listing
  SHA-256 of the Qwen3-8B weights and the evaluation seed.

### 11.7 Time estimate

| Sub-phase | Engineering | Calendar w/ debugging |
|---|---|---|
| 2a — LangGraph + 4 agents + Qwen3 / vLLM | 5 days | ~7 days |
| 2b — FastAPI + copilotkit-sdk-python wrapper | 2 days | ~3 days |
| 2c — CopilotKit React UI + custom geno_agent components | 3–5 days | ~5–7 days |
| Eval harness + LaTeX results | 2 days | ~3 days |
| 2d — LLM-augmented factorial (Planner + Critic) | 3 days | ~5 days |
| **2e — Cross-encoder re-ranker (§11.8)** | **3 days** | **~4 days** |
| **Total Phase 2** | **18–20 days** | **~4 weeks** |

---

### 11.8 Phase 2e — Cross-encoder re-ranker (added 2026-05-15)

**Motivation.** The Phase 2d LLM-augmented factorial (cells E-J,
`reports/progress_report_15052026_llm_critic_results.md`) showed that
neither LLM-Planner nor LLM-Critic produces a top-1 improvement over the
deterministic Cell D (multi-agent + hybrid retrieval). The factorial
decomposition cleanly isolates **retrieval** as the binding constraint:

- Retrieval mode (dense → hybrid) is worth ~+49 pp top-1 on Cell C → D.
- Architecture (single → multi) is worth ~+5 pp under hybrid.
- LLM augmentation has no main effect on top-1; it only redistributes
  ranks beyond position 1.

The direct way to attack the retrieval ceiling is a re-ranking stage
between first-stage retrieval and the Critic.

**Pipeline change.**

```
Current  (Phase 2d):  query → planner → retrieve(top_k=50) → critic → synth
Proposed (Phase 2e):  query → planner → retrieve(top_k=50) → reranker(top_k=10) → critic → synth
```

A cross-encoder computes a single relevance score by attending jointly
over (query, chunk) — much higher capacity than the two-tower
(query · chunk) dot product used at retrieval time, but too expensive
to run on the full corpus. Restricting it to the top-50 retrieved
candidates is the standard two-stage IR pattern (Nogueira & Cho 2019;
MS MARCO leaderboard; BEIR benchmark).

**Default model.** `ncbi/MedCPT-Cross-Encoder` (440 MB, ~25 ms/chunk on
RTX 5090). PubMed-fine-tuned on query–passage pairs — direct domain
match. Fallback: `BAAI/bge-reranker-v2-m3` (600 MB, ~28 ms/chunk).
Both are open-weight, local, no cloud API — consistent with §11.1.

**Expected lift.** From the IR literature on biomedical retrieval
benchmarks (TREC-COVID, BioASQ, NFCorpus):

- BM25 → BM25 + BGE-reranker-large: **+5 to +15 pp top-1**
- Hybrid → hybrid + cross-encoder: **+3 to +10 pp top-1**

Applied to Cell D's 0.627 top-1: conservative estimate ≈ 0.65; optimistic
estimate ≈ 0.73.

**Compute budget.** Per case: 2 500 chunk-gene pairs × 25 ms ≈ 62 s of
re-ranking. VRAM resident: ~600 MB next to Qwen3-8B (16 GB) and
PubMedBERT (440 MB). RTX 5090 has 32 GB; plenty of headroom. Four
re-ranker factorial cells × 75 cases × ~62 s = ~5.2 h GPU; overnight
feasible.

**Factorial cells (L–O).**

- **Cell L** — multi-agent + reranker · dense
- **Cell M** — multi-agent + reranker · hybrid
- **Cell N** — multi-agent + reranker + LLM-Planner · hybrid
- **Cell O** — multi-agent + reranker + LLM-Critic · hybrid

Cells L and M isolate the reranker's main effect; N and O test whether
re-ranking restores the LLM components' lost headroom.

**Implementation outline.**

```
src/agents/reranker.py
    class CrossEncoderReranker:
        def __init__(self, model_id: str = "ncbi/MedCPT-Cross-Encoder"): ...
        def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]: ...

src/agents/graph.py
    add use_reranker: bool = False kwarg to build_graph()
    insert a rerank node between retrieve and critic when True

scripts/eval/run_factorial.py
    add cells L, M, N, O to the dispatch table

tests/test_reranker.py
    smoke test for chunk-id integrity + deterministic top-k slicing
```

**Determinism.** Cross-encoders are deterministic at inference time
(no sampling, no temperature). Same `PYTHONHASHSEED=42` policy applies.
The re-ranker score will be recorded in each chunk's metadata for
auditability.

**Milestones (estimated).**

| Day | Deliverable |
|-----|-------------|
| 1 | `src/agents/reranker.py` + `build_graph` integration behind a feature flag; smoke test on 1 case. |
| 2 | Cells L + M (reranker on deterministic multi-agent). ~10 h GPU. |
| 3 | Cells N + O (reranker stacked on LLM-Planner + LLM-Critic). ~10 h GPU. |
| 4 | Aggregator update + milestone report + PR `phase2e/cross-encoder-reranker` → main. |

**Acceptance criteria (Phase 2e done = ALL of).**

- [ ] `src/agents/reranker.py` loads the chosen cross-encoder and
  exposes a deterministic `rerank()` method with unit tests.
- [ ] `scripts/eval/run_factorial.py` runs cells L–O end-to-end.
- [ ] `data/eval/_results_summary.{md,json,csv}` includes cells A–O
  with paired bootstrap 95 % CIs.
- [ ] Phase 2e milestone report (`reports/progress_report_*_reranker_results.md`)
  + visual HTML variant documents the lift (or lack of it) and updates
  the thesis findings.
- [ ] `data/MANIFEST.tsv` records the cross-encoder model SHA-256.

**Open questions resolved in Step 1.**

1. **Truncation depth.** Re-rank top-50 → top-10 (default); revisit
   top-100 → top-10 if compute allows.
2. **Per-gene vs global re-ranking.** Per-gene first (preserves
   existing architecture); global pooling deferred to a follow-up.
3. **Score combination.** Straight replacement of the second-stage
   score (the standard IR pattern). No learned linear combinations
   until baseline lift is established.

**Master plan impact.** No change to §0 (phase ordering), §11.1 (LLM
stack: re-ranker is a separate non-LLM model), §11.4 (compute budget:
fits inside existing VRAM), or §11.6 (Phase 2 acceptance criteria
remain a strict subset of Phase 2e acceptance). Phase 2e is **additive**
to the Phase 2 commitments, not a replacement.

---

*End of MASTER PROJECT FILE v2.1.*
