# geno_agent — Research Summary — 2026-05-15

**Author:** Johanna Angulo
**Repository:** [github.com/Jangulo7/geno_agent](https://github.com/Jangulo7/geno_agent) (private)
**Master plan:** `MASTER_PROJECT_v2.1.md`
**Branch:** `phase2d/vllm-prefix-caching`

This document consolidates **what we are testing, why, and where we are** as
of 2026-05-15. It is the canonical "where does this thesis stand?" reference
and supersedes the day-by-day progress reports for narrative purposes.
The day-by-day reports remain authoritative for specific numbers and CIs.

---

## 1. Research question

> **Can a multi-agent, retrieval-augmented system, working from medical
> literature, prioritise causal genes for rare-disease cases as well as
> a curated-database baseline — using phenotype information only?**

Three things this question pins down:

- **Phenotype only.** Input is HPO terms + a candidate gene list. No
  variant calls (VCFs), no allele frequencies, no zygosity.
- **Causal-gene prioritisation.** Output is a *ranked list* over the
  candidate genes; the metric of interest is whether the truly causal
  gene lands at the top.
- **Compared to a curated baseline.** The reference point is Exomiser
  in HPO-only mode — the de-facto gold standard for phenotype-driven
  gene ranking. The thesis claim is *competitive parity or better*,
  not strictly "better than every alternative".

## 2. Why HPO-only and not full variant prioritisation

This is the single most important methodological choice. Stating it
clearly so that a reviewer can locate the rationale.

### The two modes of Exomiser

| Mode | Input | What it adds | Database needs |
|---|---|---|---|
| **HPO-only** (Phenix, HiPHIVE) | HPO terms + candidate gene list | Curated gene–phenotype annotations from OMIM, Orphanet, MGI (mouse), ZFIN (zebrafish) | ~5 GB phenotype data |
| **Full variant prioritisation** (PHIVE, ExomeWalker, hiPHIVE) | HPO terms + VCF + pedigree | The above PLUS variant pathogenicity (CADD, REVEL), population frequencies (gnomAD), ClinVar | ~50 GB |

### Why the geno_agent comparison uses HPO-only

1. **Inputs must match.** Our pipeline takes HPO terms plus a candidate
   gene list. It does *not* take variants. Comparing it against
   Exomiser-full (which takes variants on top) would be comparing an
   HPO-only system against an HPO+variant system — and Exomiser-full
   would win by construction, simply because it has more information.
2. **The Phenopackets we use *contain* a declared causal variant** —
   feeding that variant in would leak the answer. The test is
   explicitly: *can we find the gene from phenotype alone?*
3. **Variant prioritisation is a different research problem.** The
   thesis does not claim "agentic RAG beats an exome pipeline". It
   claims "for the phenotype-driven gene-prioritisation sub-task,
   literature-RAG matches curated-database approaches". Cell K
   (Exomiser HPO-only) is the right anchor for that narrower claim.
4. **Clinical-use framing.** geno_agent's intended role is a
   *literature-first triage step* in workups where exome data is
   not yet available, or to augment exome workflows where the variant
   scoring is inconclusive. Variants are downstream; phenotype-driven
   literature search is upstream.

### Limitation of this comparison

The HPO-only baseline does not answer "is geno_agent better than a
full clinical exome pipeline?" — the thesis does not make that claim.
Including a full variant pipeline would broaden the research question
beyond what is testable with our data (single declared variant per
Phenopacket, no exome VCFs available).

### Authority

This choice is recorded in master plan §11.5:

> Cell E: Exomiser baseline — **HPO-driven prioritization without
> literature evidence**; the established gold standard for
> phenotype-driven gene ranking.

(Cell E in the original master plan; renamed Cell K in the extended
factorial — see §10 deviation note.)

## 3. Experimental design — the extended factorial

The thesis decomposes the contribution of each architectural choice
via a factorial design. Each cell is a fully runnable end-to-end
configuration; the same 75 test cases (Phase 1B) and the same metrics
(top-1, top-5, top-10, MRR, NDCG@10) are computed for every cell.

### The base 2×2 (deterministic)

|                            | Dense retrieval | Hybrid retrieval (dense + BM25) |
|----------------------------|-----------------|---------------------------------|
| **Single-agent**           | **A** — control: no architecture, no lexical signal | **B** — isolates retrieval contribution |
| **Multi-agent** (Planner + Retriever + Critic + Synthesiser) | **C** — isolates architecture contribution | **D** — full deterministic system |

This 2×2 decomposes:

- **Retrieval main effect** (A→B, C→D)
- **Architecture main effect** (A→C, B→D)
- **Retrieval × architecture interaction** (whether multi-agent helps
  *more* when retrieval is hybrid)

### LLM-augmented cells (E–J)

Built on top of Cell C/D by replacing one or both deterministic agent
nodes with Qwen3-8B-prompted versions:

| Cell | LLM component | Retrieval | What it tests |
|------|---------------|-----------|---------------|
| **E** | LLM-Planner | dense   | Does LLM query-reformulation help when there is no BM25 anchor? |
| **F** | LLM-Planner | hybrid  | Does LLM query-reformulation help on top of hybrid retrieval? |
| **G** | LLM-Critic  | dense   | Does LLM chunk-grading help when retrieval is weak? |
| **H** | LLM-Critic  | hybrid  | Does LLM chunk-grading help on top of hybrid retrieval? |
| **I** | both (Planner + Critic) | dense | Do LLM components compose? |
| **J** | both (Planner + Critic) | hybrid | Do LLM components compose under hybrid? |

### Baseline cell (K)

| Cell | Configuration | What it tests |
|------|---------------|---------------|
| **K** | Exomiser HPO-only (Phenix + HiPHIVE) | How does the established baseline compare to Cell D? |

### Re-ranker cells (L–O), proposed Phase 2e

| Cell | Configuration | What it tests |
|------|---------------|---------------|
| **L** | det multi-agent + cross-encoder reranker, dense | Does a reranker break the retrieval ceiling on dense? |
| **M** | det multi-agent + cross-encoder reranker, hybrid | Does a reranker break the retrieval ceiling on hybrid (i.e. on top of Cell D)? |
| **N** | reranker + LLM-Planner, hybrid | Does reranker restore the LLM-Planner's lost headroom? |
| **O** | reranker + LLM-Critic, hybrid | Does reranker restore the LLM-Critic's lost headroom? |

Total: **15 cells** (A–O). Of those, A–J are runnable today; K depends
on Exomiser setup; L–O depend on Phase 2e implementation.

## 4. Experiments executed so far

### Cells A–D — deterministic 2×2 (completed 2026-05-13)

| Cell | Architecture × Retrieval | top-1 | top-10 | MRR |
|------|--------------------------|------:|-------:|----:|
| A | single · dense   | 0.053 | 0.187 | 0.126 |
| B | single · hybrid  | 0.173 | 0.307 | 0.229 |
| C | multi · dense    | 0.133 | 0.293 | 0.194 |
| **D** | **multi · hybrid** | **0.627** | **0.733** | **0.670** |

**Finding:** Retrieval mode dominates. The dense→hybrid transition
adds +49 pp to top-1 under the multi-agent architecture. The multi-agent
architecture is only valuable when paired with hybrid retrieval — under
dense retrieval, multi-agent only adds +8 pp over single-agent. This
is the **headline retrieval×architecture interaction**.

Documented in: `reports/progress_report_13052026_factorial_results.md`.

### Cells E–F — LLM-Planner (completed 2026-05-14)

| Cell | Architecture | top-1 | top-10 | MRR |
|------|--------------|------:|-------:|----:|
| E | multi + LLM-Planner · dense  | 0.293 | 0.413 | 0.352 |
| F | multi + LLM-Planner · hybrid | 0.587 | 0.707 | 0.640 |

**Finding:** The LLM Planner is a *substitute* for hybrid retrieval,
not a complement. Under dense retrieval it adds +16 pp (E vs C); under
hybrid it loses 4 pp (F vs D). Interpretation: BM25 already provides
the lexical signal that the LLM's query reformulation tries to inject,
so adding the LLM on top dilutes the BM25 anchor without offering new
signal.

Documented in: `reports/progress_report_14052026_llm_planner_results.md`.

### Cells G–H — LLM-Critic (completed 2026-05-15)

| Cell | Architecture | top-1 | top-5 | top-10 | NDCG@10 |
|------|--------------|------:|------:|-------:|--------:|
| G | multi + LLM-Critic · dense  | 0.120 | 0.253 | 0.333 | 0.207 |
| H | multi + LLM-Critic · hybrid | 0.613 | 0.693 | 0.747 | 0.680 |

**Finding:** The LLM Critic has **no effect on top-1** in either
retrieval mode (G−C = −1.3 pp; H−D = −1.4 pp, both inside the 95 %
bootstrap CI). It re-orders chunks at top-5 / top-10 (G top-5 +6.6 pp;
H top-10 +1.4 pp) but does not change rank-1. The Critic operates on
a *fixed* chunk set; if the truly causal chunk is not in the top-K
retrieved set, no Critic — at any model size — can rescue it.

This is a **thesis-useful negative result**: it justifies keeping the
deterministic Critic in production (50× faster, reproducible,
identical top-1) and **isolates retrieval as the binding constraint**.

Documented in: `reports/progress_report_15052026_llm_critic_results.md`.

### Cells I–J — LLM-both (in flight)

Cell I (multi + LLM-Planner + LLM-Critic · dense) is at 48/75 cases
(~3.5 min/case). Cell J (hybrid) will run after. Partial Cell I result
(n=14) gives top-1 = 0.286, statistically indistinguishable from Cell E
(LLM-Planner only) = 0.293 — suggesting the LLM Critic adds nothing on
top of the LLM Planner, consistent with the G/H null result.

ETA: full I + J complete ~17:00 today.

## 5. Experiments planned

### Cell K — Exomiser HPO-only baseline (next)

The **critical missing comparison point**. Sequencing decision (2026-05-15):
Cell K runs *before* the Phase 2e re-ranker, because it anchors the
entire factorial. Without Cell K, "Cell D = 0.627" is uninterpretable —
we do not know whether 0.627 is competitive (Exomiser ≈ 0.5–0.6) or
behind a stronger baseline (Exomiser ≈ 0.7+).

| Aspect | Plan |
|--------|------|
| Mode | HPO-only (no variant pipeline) — see §2 above |
| Prioritisers | Phenix + HiPHIVE (Exomiser-CLI default for phenotype-only) |
| Input | Same 75 cases (HPO terms + 50 candidate genes per case, seed=42) |
| Setup time | ~3–5 h (Java 17 + Exomiser CLI + ~5 GB phenotype data + wrapper) |
| Compute time | ~5–15 s/case → ~20 min total for 75 cases (CPU only) |
| Compatibility | Can run in parallel with Cell I/J on GPU (different resource) |

### Cells L–O — Cross-encoder re-ranker (Phase 2e)

Proposed in `MASTER_PROJECT_v2.1.md` §11.8. Rationale: the LLM-Planner
and LLM-Critic ablations both isolate retrieval as the bottleneck.
A cross-encoder re-ranker between retrieval and the Critic is the
literature-standard way to break that ceiling.

| Aspect | Plan |
|--------|------|
| Default model | `ncbi/MedCPT-Cross-Encoder` (PubMed-fine-tuned, 440 MB) |
| Expected lift | +3 to +10 pp top-1 over Cell D (literature estimate) |
| Setup time | ~1 day (`src/agents/reranker.py` + graph integration) |
| Compute time | ~62 s/case re-ranking + pipeline → ~5 h per cell |
| Total | ~3–4 days dev + ~20 h GPU for 4 cells |

## 6. Current status snapshot (2026-05-15)

```
A    single · dense                       ✅ done    top1=0.053  (n=75)
B    single · hybrid                      ✅ done    top1=0.173  (n=75)
C    multi · dense                        ✅ done    top1=0.133  (n=75)
D    multi · hybrid              winner   ✅ done    top1=0.627  (n=75)
E    multi + LLM-Planner · dense          ✅ done    top1=0.293  (n=75)
F    multi + LLM-Planner · hybrid         ✅ done    top1=0.587  (n=75)
G    multi + LLM-Critic · dense           ✅ done    top1=0.120  (n=75)
H    multi + LLM-Critic · hybrid          ✅ done    top1=0.613  (n=75)
I    multi + LLM-both · dense    running  🟡 48/75   (eta ~13:00 today)
J    multi + LLM-both · hybrid   pending  ⏳ 0/75    (eta ~17:00 today)
K    Exomiser HPO-only           planned  ⏳         (setup starting now)
L-O  cross-encoder re-ranker     proposed ⏳         (Phase 2e)
```

Branch: `phase2d/vllm-prefix-caching` (Cells G/H/I/J commits; Cell K
will go on a parallel branch `phase2d/exomiser-baseline`).

## 7. What we have learned so far (interim findings)

1. **Retrieval mode is the dominant factor.** Hybrid vs dense:
   +49 pp top-1 under multi-agent (Cell C→D), +12 pp under single-agent
   (Cell A→B). Nothing else in the factorial moves the needle by this
   much.
2. **The multi-agent architecture pays off only under hybrid retrieval.**
   Cell C (multi-dense) under-performs Cell B (single-hybrid) by 4 pp.
   The agentic architecture's value is conditional on retrieval being
   strong enough to surface useful chunks to grade.
3. **LLM augmentation has no main effect on top-1.** Neither
   LLM-Planner nor LLM-Critic improves rank-1 over the deterministic
   pipeline in either retrieval mode (with the exception of LLM-Planner
   on dense, where it substitutes for the missing BM25 anchor).
4. **The LLM Critic moves chunks at deeper ranks but not rank-1.**
   This is consistent with the retrieval-ceiling explanation: if the
   causal chunk is *present* in the top-K but ranked low, the LLM can
   promote it; but the deterministic Critic's heuristics already handle
   the unambiguous cases that dominate top-1.
5. **Operational lesson — token budgets matter.** The first Cell G
   run had 71.6 % of LLM batches falling back to deterministic because
   prompts exceeded vLLM's 8 192-token budget. Fixed by reducing batch
   size 10→5 (commit `547b464`). Worth recording: silent fallback
   masked the bug for the duration of an entire overnight run.

## 8. Open questions (resolved by remaining experiments)

| Question | Resolved by |
|----------|-------------|
| Is Cell D's 0.627 top-1 competitive vs the established phenotype-only baseline? | **Cell K** (Exomiser HPO-only) |
| Can a cross-encoder re-ranker break the retrieval ceiling? | **Cells L–M** |
| If the re-ranker lifts the retrieval ceiling, does the LLM Critic regain headroom? | **Cells N–O** |
| Does the LLM-both stack (Planner + Critic) compose under hybrid retrieval, or is the null result of G/H confirmed by J? | **Cell J** (running tonight) |

## 9. Files and artefacts

```
MASTER_PROJECT_v2.1.md                                  (authoritative spec)
src/agents/                                             (graph, planner, critic, retriever, synthesiser)
src/agents/query_planner_llm.py                         (LLM Planner)
src/agents/critic_llm.py                                (LLM Critic, batched + concurrent)
scripts/eval/run_factorial.py                           (10-cell dispatcher)
scripts/eval/aggregate_metrics.py                       (CIs + LaTeX table)
scripts/eval/start_vllm.sh                              (vLLM Qwen3-8B + prefix-caching)
data/eval/cell_{A..J}_*/                                (75 case JSONs per cell)
data/eval/_results_summary.{md,json,csv}                (aggregator output)
data/eval/_results_by_category.csv                      (per-MONDO breakdown)
reports/progress_report_13052026_factorial_results.md   (Cells A–D)
reports/progress_report_14052026_llm_planner_results.md (Cells E–F)
reports/progress_report_15052026_llm_critic_results.md  (Cells G–H + Phase 2e proposal)
reports/research_summary_15052026.md                    (this file)
reports/research_summary_15052026.html                  (visual variant)
```

---

*Updated as cells complete. The day-by-day progress reports remain
authoritative for specific numbers; this document is the narrative
overview a thesis reviewer should read first.*
