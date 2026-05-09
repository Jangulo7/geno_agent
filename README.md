# geno_agent

**An Agentic Multi-Agent RAG System for Gene Prioritization in Rare Mendelian Disease**

> Research prototype accompanying a Master's thesis (TFM) at Universidad UAX. A peer-reviewed manuscript derived from this work is in preparation for submission to a bioinformatics venue (target: *Bioinformatics Advances* / ISMB proceedings).

---

## Overview

`geno_agent` is an agentic, multi-agent retrieval-augmented generation (RAG) system that automates literature-based evidence synthesis for the most labor-intensive step of the rare-disease diagnostic pipeline: deciding which candidate gene most plausibly causes a patient's phenotype.

Given a patient's phenotypic profile (encoded as [Human Phenotype Ontology](https://hpo.jax.org) terms) and a list of candidate genes from upstream variant calling, the system autonomously retrieves full-text articles from PubMed Central Open Access (PMC OA), critically evaluates the relevance and strength of the recovered evidence, and synthesizes a re-ranked candidate list with cited justifications.

Unlike monolithic RAG systems that perform a single retrieve-and-generate pass, `geno_agent` decomposes the task across four specialized agents — **Query Planner**, **Retriever**, **Critic**, and **Synthesizer** — orchestrated as a stateful graph in [LangGraph](https://github.com/langchain-ai/langgraph). This decomposition enables iterative query refinement, explicit relevance grading, and self-correction loops that single-pass architectures cannot support.

## Why this matters

Rare diseases affect an estimated [300 million people worldwide](https://doi.org/10.1038/s41431-019-0508-0) — between 3.5% and 8% of the global population. Despite the maturation of next-generation sequencing, roughly **half of all exome and genome sequencing cases remain without a molecular diagnosis** ([Clark et al., 2018](https://doi.org/10.1038/s41525-018-0053-8)). A substantial fraction of these undiagnosed cases is not due to undetectable variants but to the limits of current bioinformatic tools when interpreting **variants of uncertain significance** (VUS), particularly in patients with atypical or previously undescribed phenotypes.

Phenotype-driven prioritization tools such as [Exomiser](https://exomiser.readthedocs.io) (Smedley et al., 2015) work well when the causal gene is already well annotated in curated phenotype databases. They cannot surface novel or emerging gene–phenotype associations that exist *only* in unstructured literature — which is precisely where the most diagnostically valuable case reports, functional studies, and phenotype-expansion papers live. PubMed indexes over a million new articles per year, and the PMC Open Access subset alone contains more than four million full-text articles. No human curator can keep pace.

This project asks whether an agentic, multi-agent RAG architecture, deployed on local hardware and grounded in the published literature, can meaningfully assist this synthesis step for clinical genetics teams.

## What this project contributes

To our knowledge, this is the first end-to-end validated agentic multi-agent RAG system designed and evaluated specifically for **causal gene prioritization in rare Mendelian disease via literature evidence synthesis**. Specifically, the project contributes:

1. **An open, reproducible architecture** — four specialized agents (Query Planner / Retriever / Critic / Synthesizer) coordinated through LangGraph, with all components, prompts, and configuration released under an open license.
2. **A rigorous 2×2+1 factorial evaluation design** that isolates the contribution of the multi-agent architecture from the contribution of hybrid retrieval. The 2×2 factor crosses *single-agent vs. multi-agent* with *dense-only vs. hybrid (dense + BM25)* retrieval; Exomiser is included as an external phenotype-driven baseline, providing a direct quantitative comparison against an established gold standard.
3. **Local, consumer-GPU deployment** — the system runs end-to-end on a single workstation (NVIDIA RTX 5090, 32 GB VRAM) using [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) as the reasoning model and [PubMedBERT](https://huggingface.co/microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext) for biomedical embeddings. No cloud API dependencies, no per-call cost, no data leaving the workstation — important for both reproducibility and any future extension to protected clinical data.
4. **A standardized benchmark pipeline** built on the [GA4GH Phenopacket-store v0.1.19](https://github.com/monarch-initiative/phenopacket-store), with deterministic case selection (stratified across neurological, metabolic, immunological, and developmental categories) and seeded distractor sampling, so that any reported result can be regenerated bit-for-bit.

Where this work *is not* claiming novelty: RAG itself ([Lewis et al., 2020](https://arxiv.org/abs/2005.11401)), multi-agent LLM systems generally, hybrid dense+sparse retrieval, and the use of PubMed/PMC as a corpus are all established techniques. The contribution is the application of these techniques, in this combination, to this clinical problem, with rigorous evaluation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUT                                       │
│   • HPO phenotype terms (patient profile)                           │
│   • Candidate gene list (1 causal + 49 distractor genes)            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  ① Query Planner Agent         │
              │  Expands HPO terms via         │
              │  ontology graph traversal,     │
              │  generates targeted queries    │
              └────────────────┬───────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  ② Retriever Agent             │
              │  Hybrid search over Qdrant     │
              │  (PubMedBERT dense + BM25)     │
              │  with RRF fusion               │
              └────────────────┬───────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐         ┌──────────────┐
              │  ③ Critic Agent                │ ◄──────►│  Refinement  │
              │  Grades chunk relevance,       │         │  loop        │
              │  detects insufficient evidence │         │  (≤ N iters) │
              └────────────────┬───────────────┘         └──────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  ④ Synthesizer Agent           │
              │  Generates per-gene evidence   │
              │  summary with citations,       │
              │  produces re-ranked list       │
              └────────────────┬───────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         OUTPUT                                      │
│   • Re-ranked candidate gene list                                   │
│   • Per-gene evidence summary with PMC citations                    │
│   • Confidence / faithfulness signals                               │
└─────────────────────────────────────────────────────────────────────┘
```

### Knowledge base

The retrieval corpus is a filtered subset of PMC Open Access full-text articles enriched for rare-disease and clinical genetics content. Articles are parsed from JATS XML, segmented section-aware (Methods, Results, etc.) into 512-token chunks with 50-token overlap, embedded with PubMedBERT (768-dim), and indexed in [Qdrant](https://qdrant.tech) with both dense HNSW and BM25 sparse vectors for hybrid retrieval.

Ontologies (HPO, MONDO, GO, HGNC) are accessed at runtime as structured graph and tabular resources via `pronto` and `pandas` — they are deliberately *not* embedded into the vector index, since their value lies in their graph structure and exact lookups, not in semantic similarity.

## Evaluation design

The 2×2+1 factorial design produces five experimental conditions:

| Condition | Architecture | Retrieval |
|-----------|--------------|-----------|
| C1 | Single-agent RAG | Dense only |
| C2 | Single-agent RAG | Hybrid (dense + BM25) |
| C3 | Multi-agent RAG  | Dense only |
| C4 | Multi-agent RAG  | Hybrid (dense + BM25) |
| C5 | Exomiser (external baseline) | Phenotype-driven |

Test cases (50–100, configurable) are sampled deterministically from the GA4GH Phenopacket-store, stratified across MONDO disease categories, with inclusion criteria requiring ≥3 HPO terms and a single-gene pathogenic variant.

**Metrics**:
- **Ranking quality**: Recall@1, Recall@5, Recall@10, Mean Reciprocal Rank (MRR)
- **Faithfulness**: factual grounding of synthesized claims to retrieved chunks (MIRAGE-style; [Xiong et al., 2024](https://arxiv.org/abs/2402.13178))
- **Retrieval precision**: relevance of top-k retrieved chunks (PhEval-aligned; [Bridges et al., 2025](https://doi.org/10.1093/bioadv/vbaf005))
- **End-to-end latency**: wall-clock time per case

Statistical tests follow the Reform guidelines for ML evaluations ([Kapoor & Narayanan, 2023](https://reforms.cs.princeton.edu)).

## Project status

| Phase | Description | Status |
|-------|-------------|--------|
| 1A | Build PMC OA Qdrant index with hybrid retrieval | 🚧 In progress |
| 1B | Phenopacket-based test-case curation pipeline | 🚧 In progress |
| 2  | Implement four agents and LangGraph orchestration | ⏳ Planned |
| 3  | Run 2×2+1 factorial experiment and statistical analysis | ⏳ Planned |
| 4  | Manuscript preparation and reproducibility package | ⏳ Planned |

## Reproducibility

This project is built reproducibility-first. Every external dataset is pinned to a specific dated release, with SHA-256 hashes recorded in `data/MANIFEST.tsv`:

| Resource | Pinned version |
|---|---|
| Human Phenotype Ontology (HPO) | `v2026-02-16` |
| Mondo Disease Ontology (MONDO) | `v2026-03-03` |
| Gene Ontology (GO)             | `2026-03-25`  |
| HGNC complete set              | `2026-04-07` quarterly |
| Phenopacket-store              | `v0.1.19` |

In addition:
- All chunk identifiers are deterministic UUIDv5 hashes of content, not random UUIDs
- Random seeding is fixed and documented (`PYTHONHASHSEED=42`, explicit `torch` / `numpy` / `random` seeds in embedding generation)
- Qdrant runs in Docker at a pinned image version (`qdrant/qdrant:v1.12.4`)
- Dependencies are pinned in `pyproject.toml` with exact versions
- Distractor gene sampling uses a per-case derived seed (`blake2b(global_seed, case_id)`), so individual cases can be regenerated without disturbing others

The full reproducibility specification is documented in `MASTER_PROJECT_v2.1.md` §4.1.3.

## Repository layout

```
geno_agent/
├── docker-compose.yml        # Qdrant local deployment
├── .env.example              # Template; copy to .env and fill in
├── src/
│   ├── acquisition/          # PMC OA + ontology + phenopacket downloads
│   ├── parsing/              # JATS XML parsing
│   ├── chunking/             # Section-aware 512-token chunking
│   ├── embedding/            # PubMedBERT inference
│   ├── indexing/             # Qdrant collection management
│   ├── retrieval/            # Hybrid dense + BM25 retrieval
│   ├── agents/               # Query Planner, Retriever, Critic, Synthesizer
│   └── utils/
├── scripts/                  # End-to-end pipelines and experiments
├── tests/                    # Unit and integration tests
├── config/                   # Prompt templates, agent configs
└── data/                     # Datasets and manifests (large files .gitignored)
```

Persistent heavy artifacts (Qdrant index, model weights, raw corpus) live outside the repository under `~/rare-disease-rag/` to keep the git history clean.

## Quick start

> ⚠️ The full pipeline is under active development; this section will be expanded as Phase 1A completes. The instructions below set up the infrastructure but do not yet run an end-to-end experiment.

```bash
# 1. Clone and enter
git clone https://github.com/Jangulo7/geno_agent.git
cd geno_agent

# 2. Configure environment
cp .env.example .env
# Edit .env to match your local paths and ports

# 3. Bring up local Qdrant (uses bind-mount to ~/rare-disease-rag/qdrant_storage/)
mkdir -p ~/rare-disease-rag/qdrant_storage
docker compose up -d
curl http://localhost:6533/healthz   # expect: healthz check passed

# 4. Set up Python environment (recommend uv)
uv venv
source .venv/bin/activate
uv pip install -e .
```

Detailed Phase 1A and 1B execution instructions are in `MASTER_PROJECT_v2.1.md`.

## Hardware

The reference deployment targets a single workstation:
- NVIDIA RTX 5090 (32 GB VRAM)
- 64 GB system RAM
- ~700 GB Linux storage for Qdrant index and models
- WSL2 Ubuntu 24.04 on Windows host

The architecture should run on any GPU with ≥24 GB VRAM and is GPU-required for the embedding pipeline; the agent layer can run CPU-only on smaller-context models if VRAM is tight.

## Citation

A peer-reviewed manuscript is in preparation. In the interim, please cite this repository:

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

## License

The code in this repository is released under the MIT License (see [`LICENSE`](LICENSE)). Note that the redistributable artifacts have their own licenses — PMC OA articles retain their original publisher licenses, ontologies (HPO, MONDO, GO) are CC BY 4.0, and HGNC data is publicly available without restriction. Pinned versions and SHA-256 hashes for every external dataset are recorded in `data/MANIFEST.tsv`.

## Acknowledgments

This work is a Master's thesis (TFM) at Universidad UAX, supervised by [advisor name to be added]. It builds on the open ecosystem of biomedical NLP and bioinformatics — particularly the Monarch Initiative, the Human Phenotype Ontology Consortium, the GA4GH community, and the maintainers of PMC Open Access — without which a project of this scope would not be possible from a single workstation.

## Contact

Issues and pull requests are welcome via GitHub. For research correspondence: [email to be added].
