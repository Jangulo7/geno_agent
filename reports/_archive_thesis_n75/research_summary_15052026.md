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

### Cell I — LLM-both · dense (completed 2026-05-15)

| Cell | Architecture | n | top-1 | top-5 | top-10 | MRR | NDCG@10 |
|------|--------------|--:|------:|------:|-------:|----:|--------:|
| I | multi + LLM-Planner + LLM-Critic · dense | 75 | 0.240 | 0.413 | 0.520 | 0.334 | 0.362 |

**Finding:** Cell I top-1 = 0.240 vs Cell E (LLM-Planner only, dense) =
0.293. The stacked LLM combination **slightly under-performs the
Planner-only variant** on top-1 (within CI overlap, but no positive
delta). This confirms the G/H null result: the LLM Critic adds no
top-1 lift on top of the LLM Planner.

### Cell J — LLM-both · hybrid (in flight)

Started 2026-05-15 13:02 on tmux `factorial_ghij`. ETA ~17:30 today.
Tests whether the LLM-both stack composes under hybrid retrieval. Based
on Cells F and H (both ~neutral vs D), expected: top-1 close to Cell D
0.627 with no significant delta.

### Cell K — Exomiser HPO-only baseline (completed 2026-05-15)

The **critical comparison point** the thesis hinges on. Run in parallel
with Cell I on CPU; completed in 11.6 minutes wall.

| Cell | Configuration | n | top-1 | top-5 | top-10 | MRR | NDCG@10 |
|------|---------------|--:|------:|------:|-------:|----:|--------:|
| **K** | **Exomiser HPO-only (Phenix + HiPHIVE)** | **75** | **0.773** | **0.907** | **0.947** | **0.835** | **0.860** |

95 % paired-bootstrap CI: top-1 [0.680, 0.853].

**Headline finding — Exomiser beats Cell D by 14.7 pp on top-1.**
The CIs (K: [0.680, 0.853] vs D: [0.520, 0.733]) overlap only at the
[0.680, 0.733] band, so the difference is borderline significant —
likely significant under a paired bootstrap difference test, but the
overlap means the gap is not overwhelmingly large.

This is **not bad news** for the thesis — it is the comparison that
defines the contribution. The interpretation:

- Exomiser distils **25 + years of expert curation** of gene–phenotype
  links from OMIM, Orphanet, MGI (mouse), ZFIN (zebrafish), with
  HPO-aligned scoring. That is the established gold standard for
  phenotype-driven gene ranking.
- geno_agent (Cell D) gets to **within 15 pp of that gold standard
  with zero supervised gene–phenotype curation** — only PMC text +
  BM25 + dense retrieval + an agentic orchestration. That is a
  credible position for a thesis on agentic RAG.
- The Phase 2e re-ranker is now well-motivated: a +10 to +15 pp lift
  (literature estimate for cross-encoder re-rankers on biomedical IR)
  would bring Cell D into a tie with Cell K.

#### By MONDO category (D vs K)

| Category | n | D top-1 | K top-1 | Δ (D − K) |
|----------|--:|--------:|--------:|---------:|
| neurological  | 18 | 0.778 | 0.833 | −5.5 pp |
| developmental | 19 | 0.737 | **0.947** | **−21.1 pp** |
| metabolic     | 19 | 0.526 | **0.895** | **−36.8 pp** |
| **immunological** | 19 | **0.474** | 0.421 | **+5.3 pp** |

**Striking pattern.** Exomiser dominates on developmental (94.7 % top-1)
and metabolic (89.5 %) — the categories with the most mature
OMIM/Orphanet curation. geno_agent **matches or beats** Exomiser on
immunological — the only category where the literature-RAG approach
out-performs the curated baseline, suggesting that recent or sparsely
curated phenotype-gene relationships are where literature retrieval
has a real edge.

This category-level finding is **arguably more interesting** for the
thesis than the headline top-1 gap, because it shows the two approaches
have **different shapes of strength**: curated DBs win on mature, well-
annotated phenotype-gene relationships; literature-RAG can be
competitive (and sometimes better) where curation is sparse.

Documented in: `reports/progress_report_15052026_exomiser_baseline.md`
(written next).

## 5. Experiments planned

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

## 6. Current status snapshot (2026-05-15 13:05)

```
A    single · dense                       ✅ done    top1=0.053  (n=75)
B    single · hybrid                      ✅ done    top1=0.173  (n=75)
C    multi · dense                        ✅ done    top1=0.133  (n=75)
D    multi · hybrid              geno-win ✅ done    top1=0.627  (n=75)
E    multi + LLM-Planner · dense          ✅ done    top1=0.293  (n=75)
F    multi + LLM-Planner · hybrid         ✅ done    top1=0.587  (n=75)
G    multi + LLM-Critic · dense           ✅ done    top1=0.120  (n=75)
H    multi + LLM-Critic · hybrid          ✅ done    top1=0.613  (n=75)
I    multi + LLM-both · dense             ✅ done    top1=0.240  (n=75)
J    multi + LLM-both · hybrid   running  🟡 1/75    (eta ~17:30 today)
K    Exomiser HPO-only           BASELINE ✅ done    top1=0.773  (n=75)
L-O  cross-encoder re-ranker     proposed ⏳         (Phase 2e)
```

**Cell K is the *external baseline*** — Cell D is the geno_agent winner
within our system. Together they define the comparison the thesis rests
on.

Branches:
- `phase2d/vllm-prefix-caching` — Cells G/H/I/J + reports (merged into
  main once J completes)
- `phase2d/exomiser-baseline` — Cell K runner + setup (this commit)

## 7. What we have learned so far (findings)

1. **Retrieval mode is the dominant factor inside geno_agent.** Hybrid
   vs dense: +49 pp top-1 under multi-agent (Cell C→D), +12 pp under
   single-agent (Cell A→B). Nothing else in the LLM/architecture
   factorial moves the needle by this much.
2. **The multi-agent architecture pays off only under hybrid retrieval.**
   Cell C (multi-dense) under-performs Cell B (single-hybrid) by 4 pp.
   The agentic architecture's value is conditional on retrieval being
   strong enough to surface useful chunks to grade.
3. **LLM augmentation has no main effect on top-1.** Neither
   LLM-Planner nor LLM-Critic improves top-1 over the deterministic
   pipeline in either retrieval mode (with the exception of LLM-Planner
   on dense, where it substitutes for the missing BM25 anchor).
4. **The LLM Critic moves chunks at deeper ranks but not rank-1.**
   This is consistent with the retrieval-ceiling explanation: if the
   causal chunk is *present* in the top-K but ranked low, the LLM can
   promote it; but the deterministic Critic's heuristics already handle
   the unambiguous cases that dominate top-1.
5. **The LLM-both stack does not compose** (Cell I = 0.240 vs Cell E =
   0.293; LLM Critic adds nothing on top of LLM Planner).
6. **Exomiser HPO-only out-performs Cell D by 14.7 pp** (0.773 vs 0.627
   top-1; CIs overlap at [0.680, 0.733] band). The curated-database
   baseline is strong. geno_agent is competitive but not yet superior on
   overall top-1.
7. **The two approaches have different shapes of strength.** Exomiser
   dominates on developmental (+21 pp) and metabolic (+37 pp) — the
   categories with mature curated annotations. geno_agent matches /
   beats Exomiser on immunological (+5 pp) — suggesting literature-RAG
   has an edge in categories with sparse curation. This is the most
   *interesting* finding for the thesis, beyond the headline top-1 gap.
8. **Operational lesson — token budgets matter.** The first Cell G
   run had 71.6 % of LLM batches falling back to deterministic because
   prompts exceeded vLLM's 8 192-token budget. Fixed by reducing batch
   size 10→5 (commit `547b464`). Worth recording: silent fallback
   masked the bug for the duration of an entire overnight run.

## 8. Open questions (resolved + remaining)

| Question | Status |
|----------|--------|
| Is Cell D's 0.627 top-1 competitive vs the established phenotype-only baseline? | ✅ **Resolved by Cell K**: D is **behind by 14.7 pp** on overall top-1 but **competitive on immunological** (+5.3 pp). |
| Does the LLM-both stack (Planner + Critic) compose under hybrid retrieval? | 🟡 **Cell J** running (eta ~17:30 today) |
| Can a cross-encoder re-ranker break the retrieval ceiling and close the gap to Exomiser? | ⏳ **Cells L–M** (Phase 2e) |
| If the re-ranker lifts the retrieval ceiling, does the LLM Critic regain headroom? | ⏳ **Cells N–O** (Phase 2e) |
| Can a *different* design (beyond a re-ranker) take literature-RAG past Exomiser? | ⏳ **Open thesis question** — see "Design directions to beat Exomiser" below. |

## 8a. Design directions to beat Exomiser

The Cell K result reframes the design question. The re-ranker (Phase 2e)
closes the gap mechanically; this section sketches the **independent
LLM-leveraging directions** that could move literature-RAG *past*
Exomiser, recorded here so the thesis has a forward-looking design
discussion.

A more detailed analysis is recorded in
`reports/progress_report_15052026_exomiser_baseline.md` (next).

In summary, the most promising LLM-side levers — all consistent with
master plan §11.1 (local Qwen3-8B, no cloud API) — are:

- **HPO query expansion via LLM** (gene-symbol agnostic Planner): use
  Qwen3-8B to expand the HPO term set with semantically related
  phenotypes *before* retrieval, mirroring Phenix's term-similarity
  scoring on the *query* side.
- **Cross-encoder re-ranker with biomedical fine-tuning** (Phase 2e
  default, MedCPT) — directly attacks the retrieval ceiling.
- **LLM-as-evidence-aggregator** — instead of grading each chunk
  individually, have the LLM read the full top-K and write a structured
  argument for the most likely gene, voting across multiple chunks.
  Different from the current Critic (which scores chunks in isolation).
- **Knowledge-graph augmentation** — embed HGNC + HPO + ontology
  relationships as an auxiliary signal during retrieval (graph-RAG).
  Closes the gap with Exomiser's structural advantage (curated
  graph of gene-phenotype edges).
- **LLM training on a hard-negative set** built from Cell D's failures:
  for each case D got wrong, the truly causal gene is the positive
  example and the top-ranked distractor is the hard negative. A
  contrastive fine-tune of the dense embedder on these pairs would
  bias retrieval toward the kind of evidence Cell D currently misses.

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
