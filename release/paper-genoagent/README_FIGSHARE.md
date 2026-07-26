# Figshare item — P2: geno_agent (GenoAgent)

**Title.** GenoAgent: An Agentic-Workflow RAG System for Gene Prioritization in
Rare Mendelian Disease (code and evaluation results)

> Title is stable across versions and names the software artefact, not the paper's
> finding, so existing citations keep resolving. Note it says *code and evaluation
> results*: the deposit ships the figure/table **generators**
> (`scripts/manuscript/`), not the manuscripts, which stay local until
> publication.

**Author.** Johanna Angulo (Universidad Europea de Madrid)

**License.** Code: AGPL-3.0-or-later. Result artifacts: AGPL-3.0.

**Version.** v1.2  ·  **Git tag.** `paper-genoagent-v1.2` (resolve the exact commit with `git rev-parse paper-genoagent-v1.2`)
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

## What's new in v1.2

This version supersedes the statistical claims of v1.1. Nothing was re-run: the
per-case artefacts are unchanged and every difference comes from re-analysing them
correctly.

- **Inference now clusters on source publication.** The 1,047 cases derive from 415
  publications (the overlap-absent subset: 282 cases from just 93), so case-level
  intervals and McNemar tests understate variance. Every estimate and paired test is
  re-reported with a publication-level bootstrap and a cluster-level permutation
  test, with the case-level result alongside (`scripts/eval/revision/cluster_inference.py`).
- **Consequence — a claim is withdrawn.** geno_agent's rank-1 margins over Exomiser
  (+0.078) and LIRICAL (+0.082) on the overlap-absent subset are significant at case
  level and **not** under clustered inference (p = 0.45 and 0.41): 20 of the 22 net
  discordances against Exomiser come from a single publication. The system is now
  reported as **matching**, not exceeding, the curated baselines on the standard
  candidate lists. The same applies to the hard-cohort margin over LIRICAL; the
  hard-cohort margin over Exomiser does survive.
- **The overlap finding is unaffected and is strengthened.** It is now reported as a
  difference-in-differences: every system with no exposure to `phenotype.hpoa` scores
  *higher* on the overlap-absent subset, and LIRICAL alone scores lower
  (system × overlap interaction +0.382 vs geno_agent, p ≈ 1e-27). It survives
  clustering, direct standardisation for disease composition, and adjustment for
  annotation density.
- **New: annotation-density analysis** (`annotation_density.py`) separating curation
  depth from annotation exposure. Density explains 78–104 % of the overlap shift for
  every system except LIRICAL, whose effect does not attenuate at all.
- **New: design-weighted estimates** (`design_weighted.py`) for the eligible
  population, using P1's released inclusion probabilities.
- **New: prompt-sensitivity replay** (`prompt_sensitivity.py`, plus per-case outputs in
  `data/eval_1050/prompt_sensitivity/`): two paraphrased LEA prompts over cached
  retrieval. Top-1 moves 3.3 pp; the production prompt replayed through the same
  harness reproduces the published run on 152/152 cases.
- **Rationale grounding is reported from RAGAS alone.** DeepEval's
  `HallucinationMetric` was evaluated and is not carried forward: on this task shape
  it does not discriminate. It scores the fraction of supplied contexts a response
  contradicts, but an LEA response covers 15 candidate genes against a shared
  ≤20-chunk context pool, so most chunks concern other genes and register as
  contradicted regardless of quality. Empirically its per-case distribution is
  degenerate on the standard cohort (median 0.067, IQR 0.062–0.067) and bimodal on
  the hard cohort, and it predicts top-1 correctness at chance (AUROC 0.512).
  `scripts/eval/run_deepeval.py` is retained and its metric polarity is now
  documented explicitly in the module docstring.
- **New: `reports/p2_revision/`** — the machine-readable output of every analysis
  above, so any figure in the paper can be checked without re-running the pipeline,
  plus `consistency_check.py` and `latex_lint.py` verification gates.

## What's new in v1.1

- Adds the **hard (phenotype-similar distractor) cohort** — per-cell rankings,
  aggregates, paired significance, and RAGAS/DeepEval judges — completing the
  difficulty × leakage 2×2.
- On the overlap-absent subset, geno_agent has the highest point estimate in **both**
  difficulty regimes. *(Superseded in v1.2: under publication-clustered inference the
  margin over the curated baselines is not significant on the standard cohort, and only
  the hard-cohort margin over Exomiser survives.)*
- Adds the **LLM-only no-retrieval control (Cell O)** — the same Qwen3-8B backbone with
  neither retrieval nor the agentic workflow (`data/eval_1050/cell_O_llm_only/`) —
  isolating the joint contribution of retrieval and orchestration (full-cohort top-1
  0.511, fair 0.667, vs geno_agent 0.726 / 0.858).
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
  RAGAS, LOPO, aggregation, multiplicity correction, and the `revision/`
  re-analysis + verification suite), the figure generators,
  demos, tests, build/env config, `README.md` (the explanatory document), and
  `REPRODUCE.md`.
- `…_data.zip` — committed per-case results, aggregates, paired significance, and judge
  summaries for **both cohorts** (`data/eval_1050/`, `data/eval_hard/`) plus
  `data/eval_1050_lopo_full/` summaries; the publication figures and tables; and the
  license-clean, text-stripped **rationale derivative** for the champion cell in both
  cohorts (see `artifacts_manifest.tsv`); the prompt-sensitivity per-case outputs; and
  `reports/p2_revision/` — the machine-readable numbers backing the paper.
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
orchestration; the RAGAS rationale-grounding judge on both cohorts; and the figure
and table generators.

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
margin over Exomiser (+0.153, Holm p = 0.002). Anyone reusing this cohort should
cluster likewise: resampling cases yields intervals that are too narrow, and the
error is largest in exactly the leakage-stratified cells that are most interesting
to interpret.

reports/p2_revision/ holds the machine-readable output of every analysis, so any
reported number can be checked without re-running the pipeline. Rationale
grounding is reported from RAGAS; DeepEval's HallucinationMetric was evaluated and
is not reported, because it does not discriminate on this task shape (chance-level
AUROC 0.512 for predicting top-1 correctness, and a degenerate per-case
distribution).

The two-paper relationship
P1 — methods + shared foundation (corpus/index recipe, ontologies, cohorts).
P2 (this item) — the GenoAgent system and its evaluation. This item depends on P1
and references it by DOI rather than copying it.

License: AGPL-3.0.
```

## How to cite

> Angulo, J. (2026). *GenoAgent: An Agentic-Workflow RAG System for Gene
> Prioritization in Rare Mendelian Disease (code and
> evaluation results)* (v1.2) [Software & data set]. Figshare.
> https://doi.org/10.6084/m9.figshare.32814497
