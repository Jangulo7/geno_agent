# Expert review — geno_agent paper 1 (gene prioritisation) + path to paper 2 (variant prioritisation)

Reviewer stance: senior NLP / health-AI / model-development. Goal: (1) flag real
errors, (2) get paper 1 to defensible Q1 (Genome Medicine) quality, (3) design
paper 2 on variant prioritisation, (4) answer the fine-tuning question honestly.

Date: 2026-06-10. Reviewed: `manuscript_q1_draft.md`, `manuscript_methods_draft.md`,
`data/eval_1050/_results_summary.md`, `_results_stratified.md`, the codebase
(retriever, query planner, indexing, overlap computation), and the
`paper_extension_plan_v1/2/3` documents.

---

## 0. Overall assessment

This is strong, unusually careful work. The deconfounding idea (annotation-overlap
stratification), the recency analysis, the LLM-family ablation, and the
reproducibility discipline are all genuinely Q1-grade *instincts*. The prose is
submission-ready. The statistics are mostly done right (paired bootstrap + McNemar,
CIs reported, honest per-category reporting including where Exomiser wins).

But the paper is **not yet defensible at Genome Medicine**, for one structural
reason and a handful of fixable ones. The single load-bearing claim — "literature-only
system matches/exceeds curated tools" — rests entirely on the fair-cohort
reinterpretation, and that reinterpretation currently controls the confound for
*the competitors but not for geno_agent itself*. Fix that and tighten the
statistics, and this is a publishable, even distinctive, paper.

I rank issues below as **[BLOCKER]** (will likely cause reject/major-revision),
**[MAJOR]** (a good reviewer will demand it), **[MINOR]** (polish / correctness).

---

## 1. [BLOCKER] The source-paper leakage is asymmetric — you deconfound LIRICAL but not geno_agent

### The problem
Your `annotation_overlap` flag (Thread D) = "is the case's source PMID cited by
`phenotype.hpoa` for the causal OMIM disease." You use it to argue LIRICAL's 0.924
is mostly training-data exposure, and that the overlap-absent cohort (n=282) is the
"fair" comparison.

But look at how geno_agent actually retrieves (`src/agents/query_planner.py`): each
per-gene query is `"{gene_symbol} {hpo_label_1} {hpo_label_2} …"`, i.e. the gene
plus the exact HPO phenotype terms that were curated *from the source publication*.
That source publication is a rare-disease case report; if it is in PMC OA (and the
cohort is built precisely from genes with ≥5 PMC OA articles), it is almost
certainly in your Qdrant index, and nothing excludes it (`src/tools/qdrant_search.py`
filters only by gene symbol; no PMID exclusion anywhere; confirmed in
`06_upload_to_qdrant.py`, `state.py`, `run_factorial.py`).

So on a large share of cases, geno_agent is reading **the exact paper the case was
extracted from** — a *stronger* leak than LIRICAL's, because it's the full text of
the source case report, not a derived annotation.

Critically: the overlap-absent flag does **not** remove this. "Not cited by
phenotype.hpoa" ≠ "not in the PMC OA index." Your fair cohort removes LIRICAL's
advantage while leaving geno_agent's intact. A genomics reviewer will see this
immediately, and it turns your headline finding ("geno_agent #1 on the fair cohort,
+0.082 over LIRICAL") into "you handicapped one tool and not the other."

### Why this is actually an opportunity, not a death sentence
You already have the entire machinery to fix it, and fixing it makes the paper
*more* novel, not less. Two reframes:

1. **It is legitimate for a clinical literature tool to find the published answer.**
   If a gene–phenotype link is in the literature, surfacing it *is* the value
   proposition. The benchmark question is only whether you're measuring "retrieve a
   known answer" vs "generalise." The honest answer is: report both.

2. **Run the symmetric experiment: leave-one-paper-out (LOPO) retrieval.** For each
   case, exclude its source PMID(s) from retrieval and re-run Cell S (and D, L).
   This is the geno_agent analogue of your LIRICAL annotation-overlap analysis and
   the single most important experiment you can add.

### Concretely, do all three:
- **Measure the leak.** For each case, log whether the source PMID appears in the
  retrieved/reranked chunks for the causal gene, and at what rank. Report the
  source-paper-in-index rate and source-paper-retrieved rate. (You have PMIDs in
  the Qdrant payload — `06_upload_to_qdrant.py:181` — so this is a logging change,
  not a re-index.)
- **LOPO re-run.** Add a PMID-exclusion filter to `qdrant_search.py` (a
  `must_not` match on `pmid ∈ source_pmids(case)`), re-run Cell D/L/S on the full
  cohort. This is cheap relative to the original run (same retrieval, just a filter)
  and is the killer robustness result. Report top-1 with vs without the source
  paper. If geno_agent still beats Exomiser/LIRICAL on the LOPO + overlap-absent
  cohort, your paper is bulletproof. If the margin shrinks, you report it honestly
  and the paper is still publishable (and far more credible).
- **Re-cast the framing.** "We control source-publication exposure *symmetrically*:
  for curated tools via annotation-overlap stratification, and for geno_agent via
  leave-one-paper-out retrieval." That sentence alone answers the #1 reviewer
  objection before it's raised, and the symmetric-deconfounding story is a stronger
  methodological contribution than the one-sided version you have now.

This is the difference between major-revision-then-reject and accept.

---

## 2. [MAJOR] Multiplicity — the headline p-values are uncorrected and borderline

Your two flagship fair-cohort results are McNemar p = 0.015 (S vs K) and p = 0.014
(S vs M). Across the paper you run ~5 canonical pairwise comparisons × 3 strata
(all / present / absent) × 5 metrics × several subgroups — dozens of tests, no
multiplicity control. Two headline p-values near 0.014 will not survive a
Bonferroni/Holm or even a Benjamini–Hochberg FDR correction if the reviewer asks
for one, and at Genome Medicine they will.

Fixes (do at least the first two):
- Pre-declare a **primary** comparison and metric (e.g., top-1, Cell S vs each
  curated tool on the fair cohort) and treat everything else as secondary/exploratory.
- Apply **Holm or BH** correction within each family of tests and report adjusted
  p-values, or report the discordant-pair counts and let CIs carry the inference.
- Note that the fair-cohort CIs ([+0.011, +0.138] and [+0.021, +0.145]) are wide
  and the lower bounds are close to zero. Honest phrasing: "geno_agent is the
  top-ranked system on the fair cohort, with a modest but significant top-1
  advantage (Δ≈+0.08; adjusted p<0.05)." Don't oversell "more than doubling."

---

## 3. [MAJOR] geno_agent loses top-5 / top-10 to LIRICAL even on the fair cohort — report it up front

From `_results_stratified.md` (overlap-absent, n=282):
- top-5: M 0.965 vs S 0.933; top-10: M **1.000** vs S 0.940 (M>S top-10 Δ=+0.060 ★).
- Exomiser top-5 0.925 ≈ S 0.933.

So on the fair cohort geno_agent wins **top-1** but **loses recall@5/10** to LIRICAL,
significantly at top-10. For a clinical shortlist tool, top-10 recall (does the
causal gene make the review list at all) is arguably more important than top-1. The
manuscript foregrounds top-1 (where you win) and mentions the rest only in tables.

A fair reviewer reads this as cherry-picking the metric. Fix by stating the
trade-off explicitly in Results and Discussion: "geno_agent's strength is precision
at rank 1; LIRICAL retains an edge in top-10 recall. The clinically relevant
deployment is [argue it]." This is also the honest motivation for your Cell N
ensemble — and it's the natural bridge to "use geno_agent's rank-1 + LIRICAL's
recall," which you should frame as complementary rather than dismiss.

---

## 4. [MAJOR] The RAGAS faithfulness number was revised upward after seeing it was low

Methods §RAG-quality: you measured multi-claim faithfulness = 0.286, found it low,
diagnosed it as the "no direct evidence" distractor-rationale artefact, then switched
to a **top-1-only** measurement = 0.480 and report 0.480 as primary. The diagnosis
is plausible and probably correct — but as written it reads as choosing the metric
after seeing the result (HARKing). Reviewers in ML-for-health are now primed to
catch exactly this.

Fixes:
- Frame the top-1-only metric as the **pre-specified unit of analysis** (the
  prediction you act on is the rank-1 gene; distractor rationales are not claims the
  system asserts). Make that the *a priori* definition, with 0.286 as a documented
  sensitivity analysis, not "the number we replaced."
- Better: report a small **human-grounded validation** — have 1–2 clinical
  geneticists rate faithfulness on ~30–50 rank-1 rationales, and show RAGAS/DeepEval
  correlate with human judgement. That converts a contested LLM-judge number into a
  validated instrument. (You already list a reviewer panel as future work — pull a
  small version of it into this paper; it's the cheapest credibility you can buy.)
- The 0.480 strict-faithfulness number is not flattering on its own. Lead with the
  *signal* that's robust (low-grounded → likely wrong, 33–39 pp gap, reproduced
  across two judges) rather than the absolute level.

---

## 5. [MAJOR] The "HPO-only" handicap on Exomiser/LIRICAL needs an honest frame (and it sets up paper 2)

You run Exomiser and LIRICAL in **phenotype-only** mode (no VCF). Both are designed
to fuse variant deleteriousness + frequency + inheritance with phenotype; stripping
the variant layer is not how they're deployed clinically. This is *defensible* —
you're isolating the phenotype-driven gene-ranking signal, and a VCF-based
comparison is paper 2 — but right now it's stated almost in passing. A genomics
reviewer will say "you benchmarked Exomiser with one hand tied."

Fix: state explicitly and early that this is a **phenotype-driven gene-prioritisation**
comparison by construction, that variant-aware prioritisation is out of scope and is
the subject of follow-up work, and that within this scope all systems see identical
inputs (HPO terms + the same 50-gene candidate list). That scoping sentence both
protects the paper and pre-announces paper 2.

---

## 6. [MAJOR] Disproportionate cohort → your "overall" numbers are not population-representative

You oversample immunological (300 = 28.7% of cohort vs ~8% natural). Methods says
overall estimates "remain unbiased after stratum-weight correction," but I don't see
stratum-weighted overall estimates actually reported — the headline 0.726 / 0.691 /
0.924 are unweighted means over a non-representative cohort. With LIRICAL strongest
on immunological-heavy strata, the weighting matters.

Fix: report **both** the unweighted cohort means (for power) and a
prevalence-weighted or equal-weighted-across-strata sensitivity estimate, and confirm
the S vs K / S vs M direction is invariant to weighting. One extra table column.
You already do honest per-stratum reporting, so this is a small, high-credibility add.

---

## 7. [MINOR but real] Internal inconsistencies and numbers to reconcile

A copy-editor's pass will catch these, but reviewers do too:
- **Tool versions disagree across files.** Methods §Comparator systems:
  "Exomiser v14.0.0", "LIRICAL v2.4.0". Manuscript Declarations:
  "Exomiser v14.1.0 and LIRICAL v2.0.2 were used as released." These must be made
  identical, and the LIRICAL version verified (confirm v2.4.0 vs v2.0.2 actually
  exists / was used).
- **Cohort eligibility count disagrees.** Methods says "1,699 cases met all four
  criteria"; the same paragraph then describes the immunological pool as "386 cases
  eligible," and the extension plan cites 390. Reconcile and state one number.
- **Chunk/article counts.** Abstract/Methods: 287,000 articles → 4.2 M chunks
  (internally consistent: ~15 chunks/article). The extension-plan docs reference
  "52.78 M chunks" for `geno_agent_pmc_oa_v1`. Make sure the manuscript's 4.2 M is
  the *indexed, genetics-filtered* collection and explain the relationship to any
  larger pre-filter corpus, so a reviewer cross-checking your repo isn't confused.
- **n=1,047 vs 1,050 vs 282 fair cohort.** Directory names say `eval_1050`; the
  paper says 1,047 (1 excluded for HGNC resolution + sampling). Make sure every
  table caption and the data-availability paths line up with the final n.
- **RAGAS n.** Methods describes the RAGAS subset as both "600-case" (150/MONDO) and
  "n=100 sensitivity"; the abstract cites n=300 for the ablation. Tighten the
  exact n per analysis so reviewers can reproduce.
- **Cloud spend.** "$95", "$98", "$98.20", "~$100 budget" appear in different
  places; pick one figure.

None of these are fatal, but a Q1 desk editor scans for exactly this kind of drift.

---

## 8. [MINOR] Smaller scientific points

- **Distractor construction couples to phenotype.hpoa.** The 49 distractors are the
  top HPO-Jaccard neighbours from `phenotype.hpoa`. That's a reasonable "hard
  negatives" design, but it means the candidate set itself is built from the same
  curated annotation source LIRICAL uses — worth a sentence acknowledging that the
  candidate-list construction is not literature-derived and could subtly advantage
  annotation-based tools (or make the task easier for them).
- **Determinism claim.** "Bit-perfect" + "1 top-1 flip / 1,047" are mildly in
  tension; say "effectively deterministic (1 flip)" and avoid "bit-perfect" for the
  LLM cell (vLLM batched greedy is not bit-identical). You already hedge this in
  Methods — make the Results/abstract language match.
- **DeepRare exclusion.** Your categorical-reframing rationale is reasonable, but
  "we didn't run the SOTA comparator" is a classic reviewer flashpoint. Strengthen
  by adding at least a *gene-level remap* of DeepRare's public outputs on whatever
  overlap of cases exists, even if imperfect, reported as a sensitivity analysis
  with caveats — "no head-to-head at all" is weaker than "imperfect head-to-head
  with documented caveats."
- **MedCPT vs PubMedBERT.** Methods says dense embeddings are PubMedBERT
  (`17`), but the reranker is MedCPT cross-encoder, and the abstract/data-availability
  says "MedCPT dense embeddings." Clarify which model produced the *dense index*
  embeddings vs the *reranker* — these are described inconsistently.

---

## 9. Path to Q1 — prioritised checklist of "measures" (experiments + edits)

Ranked by impact-per-effort. The first two are the difference between accept and
reject.

| # | Measure | Effort | Why |
|---|---------|--------|-----|
| 1 | **Leave-one-paper-out (LOPO) retrieval** re-run of D/L/S (exclude source PMIDs); report top-1 with/without source paper, plus on LOPO ∩ overlap-absent | 1–2 days (filter + re-run) | Removes the #1 BLOCKER; symmetric deconfounding is a *stronger* contribution |
| 2 | **Source-paper-in-index / -retrieved rate** logging | hours | Quantifies the leak you're controlling; needed to interpret #1 |
| 3 | **Multiplicity correction** (Holm/BH) + pre-declared primary endpoint | hours | Headline p≈0.014 won't survive otherwise |
| 4 | **Prevalence-/equal-weighted overall estimates** as sensitivity | hours | Defuses the disproportionate-sampling objection |
| 5 | **Small clinician panel** (~30–50 rank-1 rationales, 1–2 raters, Likert + faithfulness) | days | Validates RAGAS/DeepEval; converts contested LLM-judge into instrument |
| 6 | **Report top-5/10 trade-off honestly** in Results/Discussion text | hours | Pre-empts cherry-picking charge (#3) |
| 7 | **Reconcile versions/counts/spend** across files | hours | Desk-editor hygiene (#7) |
| 8 | **Reframe HPO-only scope** explicitly + announce paper 2 | hours | Protects the comparison (#5) |
| 9 | **RAGAS re-run at full 45 chunks** (already flagged as future work) | ~$100, 1 day | Removes the "lower bound" asterisk |
| 10 | **Imperfect DeepRare remap** as caveated sensitivity | 2–3 days | Closes the "no SOTA comparison" gap |

If you only do 1–4 + 6–8, you are at defensible Q1. 5, 9, 10 move you from
"accept with minor revisions" toward "accept."

---

# PAPER 2 — variant prioritisation: design + the fine-tuning question

## 10. Reframe: this is a different, harder problem — and a much bigger opportunity

Gene prioritisation (paper 1) ranks *genes* from HPO terms. Variant prioritisation
ranks *variants* in a patient's VCF, fusing four signals Exomiser/LIRICAL already
combine well:
1. **Deleteriousness** (CADD, REVEL, AlphaMissense, SpliceAI, ESM1b/ESM1v, EVE…)
2. **Population frequency** (gnomAD)
3. **Inheritance / segregation / mode-of-inheritance fit**
4. **Phenotype match** (hiPhive / LR over phenotype.hpoa)

geno_agent currently contributes a *fifth, orthogonal* signal that neither tool has:
**full-text literature evidence about the specific variant** (functional studies,
prior case reports of the same or nearby residue, segregation, hotspots). That is
the entire reason paper 2 can win, and it dictates the architecture.

**Do not try to beat AlphaMissense/SpliceAI at their own game with an LLM.** You will
lose. The win is *fusion + literature-grounded ACMG evidence*, not variant-effect
prediction.

## 11. Benchmark construction (the hard part — get it right first)

Standard practice (PhEval, the Exomiser/LIRICAL papers): take cases with a known
causal variant and **spike it into a realistic background exome** so the tool must
rank it among thousands of real variants.

- **Cohort:** Phenopacket Store cases that carry a `VariationDescriptor` with
  HGVS/VCF coordinates (a subset of your existing cohort). Cross-check against
  **ClinVar** for the causal variant's coordinates and significance.
- **Background:** spike causal variants into background VCFs from **1000 Genomes /
  gnomAD samples** (this is what the Exomiser benchmark does). Control ancestry and
  variant load. Generate N backgrounds per case for variance estimation.
- **Inputs to all systems:** identical VCF + identical HPO terms. Run **Exomiser and
  LIRICAL in their real variant-aware mode** this time — this also retroactively
  answers paper 1's "HPO-only handicap" critique.
- **Metrics:** causal-variant top-1 / top-k, MRR; **and** clinically: how often the
  causal variant lands in a typical review window (top-5 / top-10).
- **Leakage discipline from day one:** LOPO retrieval *and* ClinVar-date
  stratification (variants classified in ClinVar before vs after a cutoff), so you
  pre-empt the exact leakage objection that bites paper 1. Also stratify by whether
  the causal variant is already in ClinVar at all (the truly hard, novel-variant
  cases are where literature evidence should shine).

## 12. The innovation thesis: literature-grounded, auto-ACMG, citation-traceable variant evidence

No deployed tool auto-generates **ACMG/AMP evidence codes with citations from
full-text literature**. Exomiser/LIRICAL rank; they don't tell you *PS3 (functional
evidence, PMID:…)*, *PM1 (mutational hotspot, PMID:…)*, *PS1/PM5 (same/different
change at a residue known pathogenic, PMID:…)*, *PP1 (segregation)*. ClinGen VCEPs
do this *by hand*, slowly. That gap is your paper-2 thesis and your clinical value:

> geno_agent ranks variants **and** emits, per top variant, a structured ACMG
> evidence summary with PMC citations and a confidence, routable for expert review.

This is publishable even if your top-1 only *matches* Exomiser, because the
explainability + ACMG-evidence layer is a genuine novelty with direct clinical
utility (it accelerates the VUS-resolution bottleneck you cite in paper 1's
Background).

## 13. The fine-tuning question — honest, specific answer

**Yes, fine-tuning can help — but not the way the question is usually meant.** Three
options, in decreasing order of expected ROI, all feasible on your single RTX 5090
(32 GB) with LoRA/QLoRA:

### (A) Learning-to-rank fusion head — *do this first, highest ROI, lowest risk*
Don't fine-tune an LLM to predict pathogenicity. Instead train a small **gradient-
boosted ranker (LightGBM/XGBoost) or a shallow MLP** that fuses per-variant features:
`[CADD, REVEL, AlphaMissense, SpliceAI, gnomAD AF, inheritance-fit, hiPhive/LR
phenotype score, geno_agent literature-evidence score, LEA confidence,
#supporting-PMCs, ACMG-criteria-bitvector]` → causal-variant rank.

- Training data: spiked benchmark with known causal variant as the positive; all
  other variants negative. Pairwise/listwise LTR objective (LambdaMART).
- This is exactly where you can **beat Exomiser**: you give the ranker a literature
  feature it structurally lacks. It's interpretable, cheap, fast to iterate, and
  reviewers trust GBMs over fine-tuned LLMs for tabular fusion.
- Watch leakage: features derived from ClinVar/literature about the *exact* variant
  must be held out under LOPO / ClinVar-date splits, or you'll train on the answer.

### (B) Instruction-tune the LLM for ACMG-evidence extraction — *the novelty engine*
Fine-tune Qwen3-8B (QLoRA, 4-bit) to read retrieved chunks for a variant and emit a
**structured ACMG evidence object** (which criteria apply, the supporting text span,
the PMID, a confidence). This is a *grounded extraction/classification* task, which
8B models do well after tuning — unlike de novo pathogenicity prediction, which they
don't.

- **Training data you already have access to:** ClinVar (variant → significance +
  review status + cited PMIDs); **ClinGen / VCEP** curated classifications that list
  the *explicit ACMG criteria applied* (gold labels for criterion assignment);
  **MaveDB** (functional-assay scores → PS3/BS3 distant supervision); your own PMC
  OA full text for the evidence spans. Distant-supervision recipe: align ClinVar's
  cited PMIDs + ClinGen criteria to passages in your index to build
  (passage → criterion) training pairs.
- Output is **verifiable** (every claim has a citation), which is the whole point and
  also how you keep an 8B model honest.
- Evaluate criterion-assignment precision/recall against held-out ClinGen VCEP
  classifications — a clean, novel, quantitative result.

### (C) Contrastive fine-tuning of the retriever for variant-level evidence — *force multiplier for A and B*
Your dense index is general biomedical (PubMedBERT/MedCPT). Variant-level evidence
("p.Arg175His", "c.1521_1523del", functional rescue assays) needs retrieval that
keys on specific mutations, not just genes. Fine-tune the dense encoder (or train a
small adapter) **contrastively** on (variant-mention, supporting-passage) pairs mined
from ClinVar-cited PMIDs.

- Cheap (sentence-transformers style, fits easily on the 5090), and it lifts the
  ceiling for both A and B by surfacing the *right* chunks.
- Measure with retrieval recall@k of the known supporting PMID for ClinVar variants.

### What NOT to do
- Don't fine-tune an LLM end-to-end to output a pathogenicity score / final rank from
  raw inputs — data-hungry, hard to make deterministic, won't beat AlphaMissense, and
  reviewers will ask why you didn't just use a calibrated VEP + ranker.
- Don't train on ClinVar/literature features about the exact test variant without a
  date/LOPO split — this is the variant-level version of paper 1's leakage and it's
  even easier to do by accident.

### Hardware feasibility
All three fit your RTX 5090. QLoRA on Qwen3-8B (4-bit, LoRA rank 16–32, seq ~4k)
trains comfortably in 32 GB; the GBM ranker and the retriever adapter are
trivial by comparison. No cloud training needed — consistent with your all-local
deployment thesis (and a selling point: "fine-tuned, but still runs on one
workstation, no PHI leaves the building").

## 14. Suggested paper-2 structure (the winning narrative)

1. Variant-aware benchmark with spiked VCFs, **all tools in their real mode**
   (answers paper 1's scope critique).
2. geno_agent-variant = standard VEP features **+ literature evidence feature** fused
   by an LTR head (option A) → show top-1/top-k vs Exomiser/LIRICAL, with leakage
   controlled by LOPO + ClinVar-date splits from the start.
3. Auto-ACMG evidence layer (option B) → criterion-assignment accuracy vs ClinGen
   VCEP gold; qualitative examples of citation-traceable variant rationales.
4. Headline if it lands: "matches/ exceeds Exomiser on variant ranking **and** is the
   only system that outputs auditable, literature-cited ACMG evidence per variant —
   accelerating VUS resolution."

That is a Q1 story even if the ranking is only on par, because the explainability +
ACMG-evidence contribution is novel and clinically load-bearing.

---

## 15. One-paragraph summary

Paper 1 is close. The blocker is that your elegant LIRICAL-deconfounding does not yet
apply to geno_agent's own retrieval of the source case report; fix that with a
leave-one-paper-out re-run (cheap, you have all the machinery), add multiplicity
correction and weighted overall estimates, report the top-10 trade-off and the
RAGAS-revision honestly, and reconcile the version/count drift — then it's defensible
Q1. Paper 2 should be variant prioritisation on spiked VCFs with all tools in their
real variant-aware mode, where your structural advantage is a *literature-evidence
feature* fused by a learning-to-rank head and an *auto-ACMG-evidence* layer
fine-tuned (QLoRA) for grounded criterion extraction — not an LLM trying to out-predict
AlphaMissense. That combination is novel, clinically useful, runs on your single GPU,
and turns paper 1's "HPO-only handicap" critique into paper 2's thesis.
