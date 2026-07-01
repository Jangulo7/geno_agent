# Figshare item — P2: geno_agent (GenoAgent)

**Title.** GenoAgent: An Agentic-Workflow RAG System for Gene Prioritization in
Rare Mendelian Disease (code, evaluation results, and manuscript artifacts)

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**License.** Code: AGPL-3.0-or-later. Result artifacts: AGPL-3.0.

**Version.** v1.1  ·  **Git tag.** `paper-genoagent-v1.1` (resolve the exact commit with `git rev-parse paper-genoagent-v1.1`)
**Repository.** https://github.com/Jangulo7/geno_agent

## What this item is

The GenoAgent system: four role-specialized LangGraph agents (Query Planner →
Retriever → Critic → Synthesizer) with Qwen3-8B LEA and MedCPT reranking, plus the
full n=1,047 evaluation against Exomiser and LIRICAL HPO-only baselines. The
evaluation is a **difficulty × leakage 2×2**: results are stratified by
annotation-overlap (leakage) status and reported on **two case-paired distractor
cohorts** — a *standard* cohort (49 uniformly-random distractors) and a *hard* cohort
(49 phenotype-similar distractors by HPO Resnik best-match-average). It includes the
annotation-overlap deconfounding, leave-one-paper-out, publication-recency, and
LLM-family robustness analyses; the RAGAS/DeepEval rationale-grounding judges on both
cohorts; and the publication figures and tables.

## What's new in v1.1

- Adds the **hard (phenotype-similar distractor) cohort** — per-cell rankings,
  aggregates, paired significance, and RAGAS/DeepEval judges — completing the
  difficulty × leakage 2×2.
- On the deconfounded fair cohort, geno_agent remains the top-ranked system in **both**
  difficulty regimes and its margin over both curated baselines **widens** under hard
  distractors (Holm-significant).
- Release-clean `README.md` is the single explanatory document; unpublished drafts and
  internal working reports are kept local and are not bundled.

## The three-paper relationship

- **P1** — methods + shared foundation (corpus/index recipe, ontologies, cohort).
- **P2 (this item)** — the GenoAgent system and its evaluation. This item
  **depends on P1 and references it by DOI** rather than copying it.
- **P3** — variant-interpretation safety benchmark in the separate
  `geno_agent_variant` repo; reuses P1's foundation and forks P2's agent code under
  AGPL-3.0.

> **Shared-foundation DOI (from P1): 10.6084/m9.figshare.32814491** — the
> retrieval-index build recipe needed to run this code comes from the P1 methods item.
> **Benchmark cohort DOIs:** standard (random distractors)
> **10.6084/m9.figshare.32814449** · hard (phenotype-similar distractors)
> **10.6084/m9.figshare.32816468** — the two case-paired Dataset items this system is
> evaluated on.

## Contents

- `…_code_<commit>.zip` — agents, tools, baselines, the evaluation harness (factorial,
  RAGAS/DeepEval, LOPO, aggregation, multiplicity correction), the figure generator,
  demos, tests, build/env config, `README.md` (the explanatory document), and
  `REPRODUCE.md`.
- `…_data.zip` — committed per-case results, aggregates, paired significance, and judge
  summaries for **both cohorts** (`data/eval_1050/`, `data/eval_hard/`) plus
  `data/eval_1050_lopo_full/` summaries; the publication figures and tables; and the
  license-clean, text-stripped **rationale derivative** for the champion cell in both
  cohorts (see `artifacts_manifest.tsv`).
- `CHECKSUMS.sha256` — SHA-256 of every file in this bundle; verify after download
  with `sha256sum -c CHECKSUMS.sha256`.
- `LICENSE` — AGPL-3.0 (the result artifacts' license; see the **License** note above).

**Not included (by design):** the raw LLM response dumps — they embed **verbatim
PMC-OA passages** (mixed CC tiers), so they are not license-clean to publish (the
text-stripped rationale derivative is included instead); the shared foundation
(reference P1's DOI); models / baseline tools (reference upstream by pinned version);
and the unpublished drafts / internal reports (kept local until publication).

## How to cite

> Angulo, J. (2026). *GenoAgent: An Agentic-Workflow RAG System for Gene
> Prioritization in Rare Mendelian Disease (code, evaluation results, and
> manuscript artifacts)* (v1.1) [Software & data set]. Figshare.
> https://doi.org/10.6084/m9.figshare.32814497
