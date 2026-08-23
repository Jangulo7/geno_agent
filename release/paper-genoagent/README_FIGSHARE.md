# Figshare item — P2: geno_agent (GenoAgent)

**Title.** Benchmark Contamination in Rare-Disease Gene Prioritisation:
Annotation-Overlap Stratification and Clustered Inference on 1,047 Cases from 415
Publications — GenoAgent code

> Retitled 2026-08-15 to mirror the P2 manuscript title, so a reader arriving from
> the paper recognises the deposit immediately. Safe to do because the item has
> never been published, so no existing citation resolves against the old wording;
> the DOI is unchanged either way. **Keep it in step with the paper**: if the title
> changes at review, change it here, on Figshare, and in `CITATION.cff`. The
> trailing *— GenoAgent code* is what distinguishes this Software item from the
> manuscript itself: the deposit ships the figure/table **generators**
> (`scripts/manuscript/`), not the manuscripts, which stay local until publication.

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**License.** Code: AGPL-3.0-or-later. Result artifacts: AGPL-3.0.

**Snapshot.** Git tag `paper-genoagent-v1.8` (resolve the exact commit with
`git rev-parse paper-genoagent-v1.8`). This is the item's **first public release**;
the tag number is internal build history, not a sequence of published versions, so
Figshare's own version counter starts at 1.
**Repository.** https://github.com/Jangulo7/geno_agent

## What this item is

The GenoAgent system: four role-specialized LangGraph agents (Query Planner →
Retriever → Critic → Synthesizer) with Qwen3-8B LEA and MedCPT reranking, plus the
full n=1,047 evaluation against Exomiser and LIRICAL HPO-only baselines. The
evaluation is a **difficulty × leakage 2×2**: results are stratified by
annotation-overlap (leakage) status and reported on **two case-paired distractor
cohorts** — a *standard* cohort (49 uniformly-random distractors) and a *hard* cohort
(49 phenotype-similar distractors by HPO Resnik best-match-average). It includes the
annotation-overlap stratification, leave-one-paper-out, publication-recency, and
LLM-family and prompt-sensitivity robustness analyses; an **LLM-only no-retrieval
control (Cell O)** — the same Qwen3-8B backbone with neither retrieval nor the
agentic workflow — that isolates the joint contribution of retrieval and
orchestration (overlap-absent top-1 0.667 vs geno_agent's 0.858); the RAGAS
rationale-grounding judge on both cohorts; and the publication figures and tables.

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
  RAGAS, LOPO, aggregation, multiplicity correction, and the `revision/`
  re-analysis + verification suite), the figure generators,
  tests, build/env config, `README.md` (the explanatory document),
  `REPRODUCE.md`, and **`reports/p2_revision/`** — the machine-readable output of
  every revision analysis, so any reported number can be checked without re-running
  the pipeline, including `tripod_llm_checklist.csv`, the machine-readable copy of
  the supplement's completed TRIPOD-LLM checklist (Table S1).
- `…_data.zip` — committed per-case results, aggregates, paired significance, and judge
  summaries for **both cohorts** (`data/eval_1050/`, `data/eval_hard/`), including the
  Cell R similarity-floor rankings, plus `data/eval_1050_lopo_full/` summaries; the
  publication figures and tables; and the license-clean, text-stripped **rationale
  derivative** for the champion cell in both cohorts (see `artifacts_manifest.tsv`);
  and the prompt-sensitivity per-case outputs.
- `CHECKSUMS.sha256` — SHA-256 of every file in this bundle; verify after download
  with `sha256sum -c CHECKSUMS.sha256`.
- `LICENSE` — AGPL-3.0 (the result artifacts' license; see the **License** note above).

**Not included (by design):** the raw LLM response dumps — they embed **verbatim
PMC-OA passages** (mixed CC tiers), so they are not license-clean to publish (the
text-stripped rationale derivative is included instead); the shared foundation
(reference P1's DOI); models / baseline tools (reference upstream by pinned version);
and the unpublished drafts / internal reports (kept local until publication).

## Figshare description field — paste this verbatim

The canonical description for the Figshare item, kept here so it is
version-controlled rather than retyped. Update here first, then paste. Do **not**
paste the whole of this README — the description field is the condensed
public-facing summary.

The item has never been published, so this describes the current state of the work
and carries no version-history or corrections narrative. If a version is ever
released publicly and later superseded, add a change note at that point.

```text
The GenoAgent system: four role-specialized LangGraph agents (Query Planner →
Retriever → Critic → Synthesizer) with a Qwen3-8B LLM-as-Evidence-Aggregator and
MedCPT reranking, plus the full n=1,047 evaluation against Exomiser and LIRICAL
HPO-only baselines.

The evaluation is a difficulty × leakage 2×2. Results are stratified by a per-case
annotation-overlap flag — whether a case's source publication is cited by
phenotype.hpoa for the causal gene's disease — and reported on two case-paired
distractor cohorts: a standard cohort (49 uniformly-random distractors) and a hard
cohort (49 phenotype-similar distractors by HPO Resnik best-match-average). Also
included: leave-one-paper-out, publication-recency, annotation-density,
design-weighted, LLM-family and prompt-sensitivity analyses; an LLM-only
no-retrieval control (Cell O) — the same Qwen3-8B backbone with neither retrieval
nor the agentic workflow — isolating the joint contribution of retrieval and
orchestration; a model-free similarity floor (Cell R, HPO Resnik
best-match-average, no training and no retrieval) that reproduces the
annotation-overlap signature without a model and bounds hard-cohort construction
bias; the RAGAS rationale-grounding judge on both cohorts; and the figure and table
generators.

Principal finding. Annotation overlap is pervasive (73.1%, 765/1,047) and
materially distorts the apparent leaderboard. LIRICAL's apparent top-1 of 0.924
falls to 0.777 on the overlap-absent subset, where it is statistically tied with
Exomiser (Δ = −0.004, p = 1.000). The evidence is a difference-in-differences
rather than an absolute comparison: every system with no exposure to
phenotype.hpoa scores higher on the overlap-absent subset — the LLM-only control
by +21.3 pp, GenoAgent by +18.1 pp, Exomiser by +12.3 pp — while LIRICAL alone
scores lower (−20.1 pp), a system × overlap interaction of +0.382 against
GenoAgent (p ≈ 1e-27). It survives publication clustering, direct standardisation
for disease composition, and adjustment for annotation density — which explains
the common rise for every system except the one whose knowledge base the flag
indexes.

Inference clusters on source publication. The 1,047 cases derive from only 415
publications (the overlap-absent subset: 282 cases from 93), so every estimate and
paired test carries a publication-level bootstrap interval and a cluster-level
permutation test, with the case-level result reported alongside. Under that
inference GenoAgent matches rather than exceeds the curated baselines at rank 1 on
the standard cohort: margins of +0.078 over Exomiser and +0.082 over LIRICAL on
the overlap-absent subset are not significant (p = 0.45 and 0.41), because 20 of
the 22 net discordances against Exomiser come from a single publication. What does
hold under clustering is the contribution of retrieval and the agentic workflow
over the identical backbone LLM (+0.191, p < 0.001), the advantage over Exomiser
on post-2020 source publications (+0.094, Holm p = 0.002), and the hard-cohort
margin over Exomiser (+0.152, Holm p = 0.002). Anyone reusing this cohort should
cluster likewise: resampling cases yields intervals that are too narrow, and the
error is largest in exactly the leakage-stratified cells that are most interesting
to interpret.

reports/p2_revision/ holds the machine-readable output of every analysis, so any
reported number can be checked without re-running the pipeline, alongside the
machine-readable TRIPOD-LLM checklist. Rationale grounding is reported from RAGAS;
DeepEval's HallucinationMetric was evaluated and is not reported, because it does
not discriminate on this task shape (chance-level AUROC 0.512 for predicting top-1
correctness, and a degenerate per-case distribution).

What is in the two files. The code zip is the tracked source at git tag
paper-genoagent-v1.8: the agents and tools, the baselines, the evaluation harness
including the revision re-analysis and verification scripts, the figure and table
generators, and reports/p2_revision/. The data zip is the per-case results for
every cell on both cohorts, the aggregates, paired significance and judge
summaries, the leave-one-paper-out summaries, the prompt-sensitivity per-case
outputs, the figures and tables, and a licence-clean rationale derivative with
verbatim source text stripped. Raw LLM response dumps are withheld because they
embed verbatim PMC Open Access passages of mixed licence.

How to check the headline numbers without re-running anything. Every value in the
paper traces to a file in reports/p2_revision/ through the script-to-result map in
Supplementary Table S12. Two gates re-verify the manuscript against those files
(consistency_check.py, latex_lint.py); their output is archived as
reports/p2_revision/i2_gate_run.txt. The three secondary cells that read exactly
1.000 are re-derived from the per-case artefacts by verify_perfect_cells.py,
independently of the shared metric helper, and are 282/282 in each.

The two-paper relationship
P1 — methods + shared foundation (corpus/index recipe, ontologies, cohorts).
P2 (this item) — the GenoAgent system and its evaluation. This item depends on P1
and references it by DOI rather than copying it.

License: AGPL-3.0.
```

## How to cite

> Angulo, J., Espinos-Morato, H., & Yeste, V. (2026). *Benchmark Contamination in
> Rare-Disease Gene Prioritisation: Annotation-Overlap Stratification and Clustered
> Inference on 1,047 Cases from 415 Publications — GenoAgent code* [Software].
> Figshare. https://doi.org/10.6084/m9.figshare.32814497
