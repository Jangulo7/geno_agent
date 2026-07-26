# geno_agent — System Architecture (companion legend)

Diagram source: [`build_architecture.py`](build_architecture.py) (reproducible generator) →
[`geno_agent_architecture.svg`](geno_agent_architecture.svg) (canonical, print-ready vector) +
[`geno_agent_architecture.png`](geno_agent_architecture.png) (5120×3800 preview).
Poster-grade landscape figure designed to make the **engineering** and the **science** legible at
a glance. Re-render (edit text/colors/layout in the script, then):
`python reports/architecture/build_architecture.py`
(needs `cairosvg` for the PNG: `pip install cairosvg`; the SVG is written without it).
Visual style derives from the user-provided base `geno_agent_architecture_styled.svg`.

**One line:** a multi-agent Retrieval-Augmented Generation (RAG) pipeline that ranks the
likely **causal gene** for a rare-disease patient from their HPO phenotypes + a 50-gene
candidate list, using biomedical-literature evidence retrieved from a PMC Open-Access corpus.

---

## 1. Presentation layer 🖥️
| Component | Role | Tech |
|---|---|---|
| **Web app (Vercel)** — `geno-agent-master.vercel.app` | Upload a case, watch progress, view ranked genes + explainable report | deployed on **Vercel** |
| **Streamlit demos** (`demos/streamlit_thesis_*`) | Offline/no-GPU thesis presentation + data browser | Streamlit 1.48 |
| **FastAPI serving** | REST entrypoint — present in deps, **Phase 2b deferred** | FastAPI 0.136 / uvicorn |

## 2. Per-case input 📥
`case_id` · patient **HPO terms** · **50 candidate genes** · (eval only) `causal_gene` + its index.

## 3. Online pipeline 🧠 — LangGraph `StateGraph` (the heart of the system)
Topology: `START → A1 Query Planner → A2 Retriever → A3 Critic → ⬦ → {retriever_loop → A3 | A4 Synthesizer} → END`.
All nodes read/write one shared **`AgentState`** (typed dataclass: `hpo_terms`, `candidate_genes`,
`expanded_hpo`, `mesh_queries`, `retrieved{gene→chunks}`, `grades{gene→CriticGrade}`, `ranked`,
`iteration`/`max_iterations=3`, `lea_log`).

| Agent | Objective | Key tasks / functions | Reads → Writes | Models / tools |
|---|---|---|---|---|
| **A1 Query Planner** | Expand phenotype + build per-gene literature queries | HPO parent-walk (dist=2); query = gene + top-5 HPO labels | `hpo_terms, candidate_genes` → `expanded_hpo, mesh_queries` | HPO (pronto); **LLM variant**: Qwen3-8B |
| **A2 Retriever** | Fetch top-K evidence chunks per gene | Qdrant search, mode `dense\|bm25\|hybrid(RRF)`, `top_k=10`, prefetch ×4 | `mesh_queries` → `retrieved` | PubMedBERT + BM25 + Qdrant |
| **A3 Critic** | Grade each chunk | gene-mention via HGNC aliases; relevance 1–5 (phenotype co-occurrence); evidence type; rationale | `retrieved` → `grades` | HGNC, HPO; **LLM variant**: Qwen3-8B + thinking (batch 5, 8 workers) |
| **A4 Synthesizer** | Aggregate grades → per-gene confidence → rank 1..50 | det: `relevance × evidence-weight`, top-3 chunks/gene | `grades` → `ranked` | det; **LEA variant**: Qwen3-8B re-ranks top-15 genes (3 chunks each) → `lea_log` |

**Self-correction loop (`critic_router`)** — a pure routing function: re-enter the Retriever when
`#grades with relevance ≤ 2  > 5`  **AND**  `iteration < 3`; otherwise go to the Synthesizer.

## 4. Ontologies + Models 📚🤖 (resources consumed)
- **Ontologies/knowledge:** HPO (`hp.obo`, pronto) · HGNC complete set (symbols+aliases) ·
  MONDO (case categorization) · Gene Ontology (`go.obo`, reference).
- **Embedding / retrieval models:** **PubMedBERT** `NeuML/pubmedbert-base-embeddings` (768-d dense) ·
  **BM25** `Qdrant/bm25` (fastembed, sparse) · **MedCPT-Cross-Encoder** `ncbi/MedCPT-Cross-Encoder`
  (reranks 50→10 in eval cells L/S).
- **Generative LLM:** **Qwen3-8B** (FP16) served locally by **vLLM** at `:8001`
  (util 0.55–0.75, max-len 16–32 k) — powers LLM Planner/Critic and the LEA synthesizer.
- **Judge LLM (measurement only, never prioritizes):** OpenAI **GPT-4o-2024-08-06**.

## 5. Offline indexing pipeline 🏗️ (built once, before the online pipeline)
`scripts/corpus → embedding → indexing`:
**PMC-OA corpus** (FTP, s5cmd bulk sync, JATS-XML) → parse/normalize/dedupe/filter →
section-aware **chunking** (`chunk_id` UUID5, `section_type`, `pub_year`) →
**embed** with PubMedBERT (CUDA, L2-norm parquet shards) →
**Qdrant collection `geno_agent_pmc_oa_v1`** (Docker, ~26 GB RAM; dense HNSW m=16/ef200 cosine +
BM25 sparse w/ IDF; on-disk payload). This is the **vector database created** by the project.

## 6. Offline cohort construction 🧬 — `scripts/cases` (Phase 1B)
**GA4GH Phenopacket Store v0.1.26** (6,668 packets → HPO + disease + causal gene) →
load → inclusion/exclusion → categorize by MONDO (neuro / metabolic / immuno / developmental) →
stratified sample → validate PMC coverage → build **50-gene candidate lists** (per-case
`blake2b`-seeded shuffle). Two **datasets created**:
- `test_cases_1050.jsonl` — **standard**: 49 **random** distractors (mean sim ≈ .449).
- `test_cases_hard.jsonl` — **hard**: 49 **phenotype-similar** distractors (Resnik BMA, script `18b`).

## 7. Baselines ⚖️ (HPO-only, external CLIs)
**Exomiser** v14.0.2 (Cell K, hiPhive) · **LIRICAL** v2.4.0 (Cell M, disease→gene via OMIM/Orphanet) ·
**RRF ensemble** (Cell N/P, k=60).

## 8. Evaluation harness 🧪 — `scripts/eval`
- **Factorial cells A–J, Q, R**: single/multi-agent × dense/hybrid × deterministic/LLM-planner/
  LLM-critic × LEA.
- **Headline cells**: **D** (multi·hybrid) · **L** (+ CE-rerank-inside) · **S = geno_agent**
  (rerank + LEA).
- **Aggregation**: `aggregate_metrics`, `aggregate_stratified` (full vs **FAIR** = annotation-overlap-absent),
  `paired_diff` (McNemar), `multiplicity_correction` (Holm / BH).
- **LLM judge**: RAGAS (faithfulness), n=100 / n=600 stratified, seed 42 (calls GPT-4o).

## 9. Persistence + outputs 💾
`data/eval_{1050,hard}/cell_*/<case>.json` (ranked 50-gene lists, shared schema) ·
`cell_S_responses/` LEA sidecars (→ judges) · `_results_summary/_stratified`, `_paired_diffs`,
`supp_table_multiplicity`, figures/reports → surfaced back in the frontend.

## 10. Key decision points ⬦
1. **Retrieval mode** — dense | bm25 | **hybrid (RRF)**.
2. **Agent variant** — deterministic | LLM (Query Planner and/or Critic).
3. **Synthesizer** — deterministic | **LEA**.
4. **Self-correction loop** — re-retrieve while low-confidence grades (rel ≤ 2) > 5 and iter < 3.
5. **CE-rerank-inside** — MedCPT cross-encoder reranks 50→10 (cells L/S).
6. **Ensemble fusion** — RRF over baseline + system rankings (k=60).

---

### Technology stack (pinned)
Python 3.12 · **LangGraph** 1.2.1 · **Qdrant** 1.14.3 (Docker, :6533) · **sentence-transformers** 4.1 ·
**fastembed** 0.8 (BM25) · **pronto** 2.7.3 (HPO) · **vLLM** (Qwen3-8B) · **openai** 2.36 (local + judges) ·
**torch** 2.12 nightly cu128 (RTX 5090) · **Streamlit** 1.48 · **FastAPI** 0.136 (deferred) ·
**Vercel** (web frontend) · RAGAS (eval judge).
