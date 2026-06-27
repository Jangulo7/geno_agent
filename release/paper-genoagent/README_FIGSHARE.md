# Figshare item — P2: geno_agent (GenoAgent)

**Title.** geno_agent: An Agentic-Workflow RAG System for Gene Prioritization in
Rare Mendelian Disease (code, evaluation results, and manuscript artifacts)

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**License.** Code: AGPL-3.0-or-later. Result/manuscript artifacts: AGPL-3.0.

**Git tag.** `paper-genoagent-v1.0`  ·  **Commit.** `c2a2059`
**Repository.** https://github.com/Jangulo7/geno_agent
**Target journal.** Genome Medicine (fallbacks: Bioinformatics, JAMIA, Briefings in Bioinformatics)

## What this item is

The GenoAgent system: four role-specialized LangGraph agents (Query Planner →
Retriever → Critic → Synthesizer) with Qwen3-8B LEA and MedCPT reranking, plus the
full n=1,047 factorial evaluation against Exomiser and LIRICAL baselines, the
deconfounding / leave-one-paper-out robustness analyses, figures, tables, and the
manuscript draft.

## The three-paper relationship

- **P1** — methods + shared foundation (corpus/index recipe, ontologies, cohort).
- **P2 (this item)** — the GenoAgent system and its evaluation. This item
  **depends on P1 and references it by DOI** rather than copying it.
- **P3** — variant-interpretation safety benchmark in the separate
  `geno_agent_variant` repo; reuses P1's foundation and forks P2's agent code under
  AGPL-3.0.

> **Shared-foundation DOI (from P1): 10.6084/m9.figshare.32814491** — the retrieval-index build
> recipe needed to run this code comes from the P1 methods item; paste its DOI here.
> **Benchmark cohort DOI: 10.6084/m9.figshare.32814449** — the n=1,047 cohort this
> system is evaluated on is a separate Dataset item.

## Contents

- `…_code_<commit>.zip` — agents, tools, baselines, evaluation harness, demos,
  tests, build/env config, methods + architecture docs, and `REPRODUCE.md`.
- Results bundle — `data/eval_1050/` committed per-case results + summaries and
  `data/eval_1050_lopo_full/` summaries (see `artifacts_manifest.tsv`).
- Manuscript bundle — `reports/manuscript_q1_draft*.md`, figures, tables,
  supporting analyses.
- `*.sha256` — checksums for every uploaded file.

**Not included (by design):** the 1.9 GB raw LLM response dumps — they embed
**verbatim PMC-OA passages** (mixed CC tiers), so they are not license-clean to
publish; keep local / recipe-only, or publish the text-stripped rationale
derivative described in `artifacts_manifest.tsv`. Also excluded: the shared
foundation (reference P1's DOI); models / baseline tools (reference upstream by
pinned version); the personal cover letter.

## How to cite

> Angulo, J. (2026). *geno_agent: An Agentic-Workflow RAG System for Gene
> Prioritization in Rare Mendelian Disease* [Software & data set]. Figshare.
> https://doi.org/10.6084/m9.figshare.32814497
