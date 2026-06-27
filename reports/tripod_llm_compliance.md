# TRIPOD-LLM compliance checklist for the geno_agent Q1 manuscript

**Version:** v2 (re-audit) — 2026-05-24
**Reporting guideline:** TRIPOD-LLM (Gallifant et al., *Nature Medicine*
31, 60-69, 2025; doi:10.1038/s41591-024-03425-5; living version at
https://tripod-llm.vercel.app/).

**Re-audit context:** v1 of this checklist was written on 2026-05-23
*before* the manuscript prose pass (Options A-D, commits 646971a /
c2fafbe / 2a6a611 / 8f5d191). v2 reflects the post-drafting state of
`reports/manuscript_q1_draft.md` v10 and
`reports/manuscript_methods_draft.md` v2. Most ⚠️ items have been
resolved by the drafting work; all ❌ items have been resolved or
demoted to ⚠️ pending external confirmation.

**Affiliation correction:** The Q1 paper is submitted as part of the
first author's **PhD work at Universidad Europea (UE)**, not the UAX
Master's. The IRB exemption letter referenced in Item 13 is from UE.

**Study classification under TRIPOD-LLM tags**:
- **E** = LLM evaluation (applies — Cell S is an LLM-in-the-loop evaluation study)
- **H** = LLM evaluation in healthcare settings (applies — rare-disease clinical prioritisation)
- **IR** = Information retrieval (applies — gene prioritisation is a ranking task)
- Does **not** apply: M (LLM methods), D (de novo development), QA, SS, MT, DG

We are not developing a new LLM; we are evaluating an LLM-in-the-loop
retrieval-augmented system for gene prioritisation on clinical phenotype
input.

**CONSORT-AI applicability:** CONSORT-AI extends CONSORT for
*randomised controlled trials* with AI interventions. Our study is a
methodological development/evaluation study, not an RCT, so CONSORT-AI
does not strictly apply — TRIPOD-LLM is the correct primary reporting
guideline. §8 below provides the mapping in case Genome Medicine
reviewers request it.

**Status legend:**
- ✅ **Addressed** — content is present in the manuscript draft
- ⚠️ **Partial** — content exists but needs expansion, OR awaiting a
  signed external document (IRB letter, Zenodo DOI)
- ❌ **Pending** — content not yet drafted
- ➖ **Not applicable** — item is for a different study design / LLM task

**Manuscript locations referenced (paths from repo root):**
- `reports/manuscript_q1_draft.md` (main manuscript v10, 9,433 w)
- `reports/manuscript_methods_draft.md` (Methods draft v2, 2,611 w proper)
- `reports/tables/` (Tables 1-4, Supp Table 1)
- `reports/figures/` (Figures 1-4, Supp Figs 1-2; all 300 dpi)
- `reports/methodology.md` (v3.1 consolidated technical reference)
- `reports/wallclock_cost_table.md` (Methods Table 1 source)
- `reports/deeprare_comparability_analysis.md` (architectural comparison)
- `reports/explainability_report.md` (XAI companion-paper foundation)

---

## 1. Title and Abstract

### Item 1 — Title

**TRIPOD-LLM (verbatim):** *Identify the study as developing, fine-tuning
and/or evaluating the performance of an LLM, specifying the task, the
target population and the outcome to be predicted.*

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_q1_draft.md` §Title — 3 candidate titles
drafted, each declaring (i) evaluation study, (ii) gene prioritisation,
(iii) rare-disease target, (iv) gene-level outcome. Final title to be
selected by co-authors before submission.

### Item 2 — Abstract

**TRIPOD-LLM (verbatim):** *See TRIPOD-LLM for abstracts.*

**Status:** ✅ **Addressed** (was ❌).

**Evidence:** `manuscript_q1_draft.md` §Abstract — structured 350-word
abstract (Background / Methods / Results / Conclusions) at Genome
Medicine's word limit, 13 keywords. Headline numbers, deconfounding
methodology, RAGAS/DeepEval grounding, and 3-LLM ablation all covered.

---

## 2. Introduction

### Item 3a — Background and rationale

**TRIPOD-LLM (verbatim):** *Explain the healthcare context/use case
(for example, administrative, diagnostic, therapeutic and clinical
workflow) and rationale for developing or evaluating the LLM, including
references to existing approaches and models.*

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_q1_draft.md` §Background — 1,072 w in 7
subsections: §Rare-disease diagnostic burden, §Phenotype-driven
computational prioritisation, §The publication-curation gap, §LLMs and
RAG, §Multi-agent LLM systems in biomedicine, §LLM evaluation and the
hallucination problem, §The gap this study addresses. References to
Exomiser, LIRICAL, AI-MARRVEL, DeepRare, plus RAG/agentic-LLM literature.

### Item 3b — Target population and intended use

**TRIPOD-LLM (verbatim):** *Describe the target population and the
intended use of the LLM in the context of the care pathway, including
its intended users in current gold standard practices.*

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:**
- `manuscript_q1_draft.md` §Background §The gap this study addresses
  (target population = rare-disease patients).
- `manuscript_q1_draft.md` §Discussion §Explainability and the clinical-
  triage-flag deployment pattern (intended users = clinical geneticists;
  intended use = post-phenotyping triage decision support, NOT autonomous
  diagnosis).
- `manuscript_q1_draft.md` §Discussion §Comparison with existing systems
  (deployment context vs DeepRare).

### Item 4 — Objectives

**TRIPOD-LLM (verbatim):** *Specify the study objectives, including
whether the study describes the initial development, fine-tuning or
validation of an LLM (or multiple stages).*

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_q1_draft.md` §Background §The gap this study
addresses + `manuscript_methods_draft.md` opening — both explicitly
state this is a methodological evaluation study, no fine-tuning, with
the five evaluation axes (head-to-head vs curated, fair-cohort, recency,
faithfulness, LLM-family robustness).

---

## 3. Methods

### Item 5a — Data sources

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Cohort construction +
§Index construction. Phenopacket Store v0.1.26, PMC OA corpus (~3.4M
genetics-relevant articles → 52,777,395 chunks). Qwen3-8B used as-released
(no fine-tuning).

### Item 5b — Data point distribution

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Cohort construction
(disproportionate-stratified 250/300/250/247 = 1,047, seed 42) +
`manuscript_q1_draft.md` §Results §Cohort and evaluation setup
(per-MONDO breakdown, PMID year distribution 1988-2024 median 2018).

### Item 5c — Date range

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Cohort (source PMID dates
1988-2024, median 2018) + §Index (PMC OA indexed to 2026-05) + pinned
ontology versions HPO 2026-02-16, MONDO 2026-03-03, GO 2026-03-25,
HGNC 2026-04-07.

### Item 5d — Preprocessing and quality checking

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Cohort construction
(4-criterion inclusion filter applied uniformly) + §Index construction
(MeSH-genetics filter, 512-token chunking, PubMedBERT tokeniser, UUID5
deterministic IDs).

### Item 5e — Missing and imbalanced data

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Cohort construction
(exclusion of cases lacking ≥5 PMC articles or ≥1 HPO term) +
`manuscript_q1_draft.md` §Results §LLM-family ablation (Qwen3-32B
JSON-refusal rate transparently reported) + §Local explainability
(LEA-fallback rate 0.2 % overall, 0.0 % on fair cohort).

### Item 6a — LLM name, version, last training date

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Comparator systems Cell S
— Qwen3-8B (Yang et al. 2025), vLLM 0.20.1, Apache 2.0 licence,
HuggingFace path. Ablation models: Qwen3-32B, Claude Sonnet 4.6,
DeepSeek-V3-0324, all via OpenRouter. Judge: GPT-4o-2024-08-06.

### Item 6b — LLM development process

**Status:** ➖ **Not applicable** — evaluation study, no fine-tuning.
**Evidence:** Explicit statement in `manuscript_methods_draft.md`
§Comparator systems Cell S that LLMs are used as-released.

### Item 6c — Prompt + inference settings

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Comparator systems Cell S
(temperature 0.0, top-p 1.0, json_object response format) +
§Reproducibility infrastructure (PYTHONHASHSEED=42, seed 42,
deterministic state-graph traversal, full prompts captured per-case in
sidecars).

### Item 6d — Initial and post-processed LLM output

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Comparator systems Cell S
(LEA JSON output schema: ranked `{gene, confidence, rationale}`) +
§Reproducibility infrastructure (5-shape tolerant parser, fallback to
CE-rerank ordering on parse failure).

### Item 6e — Classification thresholds

**Status:** ➖ **Not applicable** — task is ranking, not threshold-based
classification.

### Item 7a — Output quality metrics

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Evaluation metrics
(top-1/5/10, MRR, NDCG@10 with paired-bootstrap 95 % CIs and McNemar
tests) + §RAG-quality evaluation (RAGAS faithfulness, DeepEval
HallucinationMetric) + §Local explainability analysis (rationale
substantiveness, citation count). All metrics reported with CIs in
`manuscript_q1_draft.md` §Results.

### Item 7b — Outcome metrics' relevance to deployment

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence (task-relevance):**
- `manuscript_q1_draft.md` §Discussion §Explainability and the clinical-
  triage-flag deployment pattern — RAGAS-high-faithfulness 79.9 %
  top-1 vs faithfulness=0 46.5 % (33 pp gap); analogous DeepEval gap
  39 pp. Supports a deployment pattern in which low-grounded
  predictions are routed for human review.

**Evidence (no human evaluation panel — honestly flagged):**
- `manuscript_q1_draft.md` §Discussion §Limitations item 1 explicitly
  states *"no clinical reviewer panel rated the LEA rationales"* and
  identifies a clinical-geneticist Likert panel as the planned next
  study.

### Item 7c — Outcome definition, prediction formula, inference date

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Evaluation metrics
(outcome = causal gene's rank 1-50) + §Reproducibility infrastructure
(code paths to `scripts/eval/rerank_inside_d.py`, etc.) + Methods
checklist for Q1 reviewers (inference dates: Cell S 2026-05-18, Q1-B
ablation 2026-05-23, RAGAS 2026-05-23, DeepEval 2026-05-23).

### Item 7d — Subjective assessor qualifications

**Status:** ➖ **Not applicable** — outcome (causal gene rank) is
objective; gold standard is Phenopacket Store SOLVED status.

### Item 7e — Performance comparison to other systems

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_q1_draft.md` §Results §§Overall through
§LLM-family ablation — paired Δ vs Exomiser, LIRICAL, internal
ablations, ensemble, and 3 frontier LLMs, plus §Discussion §Comparison
with existing systems (architectural framing of DeepRare exclusion).
Tables 2-4 + Figures 3-4 + Supp Fig 2.

### Item 8 — Annotation

**Status:** ➖ **Not applicable** — Phenopacket Store comes
pre-annotated by its curators; we use it as-is.

### Item 9a — Prompt design process

**TRIPOD-LLM (verbatim):** *If research involved prompting LLMs, provide
details on the processes used during prompt design, curation and
selection.*

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_methods_draft.md` §Prompt design and curation
(single design pass, no formal A/B iteration, no in-context exemplars,
no chain-of-thought elicitation; per-case prompt templates captured
deterministically in `data/eval_1050/cell_S_responses/<case>.json:
lea_log.*` for replay) + §Comparator systems Cell S (LEA prompt intent
+ inference settings).

### Item 9b — Data used to develop prompts

**TRIPOD-LLM (verbatim):** *If research involved prompting LLMs, report
what data were used to develop the prompts.*

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_methods_draft.md` §Prompt design and curation
— explicit statement that prompts were validated only on hand-
constructed synthetic toy inputs, with no case from the n = 1,047
evaluation cohort or the n = 300 ablation sub-sample used to develop
or tune the prompt.

### Item 10 — Summarization preprocessing

**Status:** ➖ **Not applicable** — task is ranking, not summarization.

### Item 11 — Instruction tuning / alignment

**Status:** ➖ **Not applicable** — no fine-tuning or alignment
modification performed.

### Item 12 — Compute reporting

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_q1_draft.md` §Results §Computational profile
+ `reports/tables/table1_wallclock_cost.{md,csv}` (per-cell wallclock,
throughput, cloud-equivalent cost). Hardware: 1 × RTX 5090 (32 GB),
64 GB RAM. Cell S = 26.1 s/case end-to-end.

### Item 13 — Ethical approval

**TRIPOD-LLM (verbatim):** *Name the institutional research board or
ethics committee that approved the study and describe the participant-
informed consent or the ethics committee waiver of informed consent.*

**Status:** ⚠️ **Partial** (was ❌).

**Coverage so far:** `manuscript_q1_draft.md` §Declarations §Ethics
approval — explicit statement that the study uses de-identified data
from GA4GH Phenopacket Store v0.1.26 (already-published case data, no
new patient data collected), and that **Universidad Europea (UE)** has
confirmed exemption from prospective IRB review.

**Gap:** The Declarations paragraph currently flags the UE exemption
letter as pending signature. The user already holds a UE exemption
letter for the broader doctoral research scope; a publication-specific
confirmation signed by the UE ethics secretary is requested via the
template in `reports/ue_irb_exemption_request_template.md`. Once
received, the flag is removed and Item 13 becomes ✅.

### Item 14a — Funding source

**Status:** ✅ **Addressed** (was ❌).
**Evidence:** `manuscript_q1_draft.md` §Declarations §Funding —
explicit statement that the work is part of doctoral research at
Universidad Europea (UE), with no external grant funding. Workstation
and cloud API spend ($119.62) borne by the first author.

### Item 14b — Conflicts of interest

**Status:** ✅ **Addressed** (was ❌).
**Evidence:** `manuscript_q1_draft.md` §Declarations §Competing
interests — explicit "no competing financial or non-financial interests"
statement.

### Item 14c — Study protocol availability

**Status:** ✅ **Addressed** (was ⚠️).
**Evidence:** `manuscript_q1_draft.md` §Declarations §Availability of
data and materials — repository and protocol documents
(`reports/paper_extension_plan_v3.md`, `MASTER_PROJECT_v2.2.md`)
publicly available at https://github.com/Jangulo7/geno_agent upon
submission.

### Item 14d — Study registration

**Status:** ✅ **Addressed** (was ❌; explicit sentence added in v2
sweep).

**Evidence:** `manuscript_q1_draft.md` §Declarations §Ethics approval
— explicit no-registration sentence ("This methodological
development/evaluation study was not registered with a clinical-trial
registry, as it is not a clinical trial and does not involve a
clinical intervention or patient follow-up.").

### Item 14e — Data availability

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_q1_draft.md` §Declarations §Availability of
data and materials — Phenopacket Store v0.1.26 source link, PMC OA
source link, all derived data sidecars committed at
`data/eval_1050/cell_*/`. Frozen Zenodo deposition flagged pending
submission-time DOI mint.

### Item 14f — Code availability

**Status:** ✅ **Addressed**.
**Evidence:** Same Declarations paragraph + repository at
https://github.com/Jangulo7/geno_agent under MIT licence (proposed).

### Item 15 — Patient and public involvement

**Status:** ✅ **Addressed** (was ❌; explicit sentence added in v2
sweep).

**Evidence:** `manuscript_q1_draft.md` §Declarations §Ethics approval
— explicit no-PPI paragraph ("This study did not involve direct
patient or public participation. The Phenopacket Store cases used as
evaluation data were originally consented at the time of source
publication by the authors of the underlying case reports.").

---

## 4. Results

### Item 16a — Patient/EHR flow

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Cohort construction (4-step
filter funnel) + `reports/figures/fig1_consort_flow.png` (CONSORT-style
flow diagram, 300 dpi) referenced as Figure 1 in
`manuscript_q1_draft.md` §Tables and figures.

### Item 16b — Patient characteristics

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_methods_draft.md` §Cohort construction +
`manuscript_q1_draft.md` §Results §Cohort and evaluation setup
(per-MONDO breakdown, overlap rate, PMID year distribution).

### Item 16c — Distribution comparison (development vs evaluation)

**Status:** ➖ **Not applicable** — evaluation-only study; no
development split.

### Item 16d — n per analysis

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_q1_draft.md` §Results — per-analysis n is
explicit throughout (full cohort 1,047; fair cohort 282; recency 601/446;
ablation 300; RAGAS 600; DeepEval 100; per-MONDO subgroups).

### Item 17 — Performance

**Status:** ✅ **Addressed**.
**Evidence:** `manuscript_q1_draft.md` §Results §§Overall through
§LLM-family ablation + Tables 2-4 + Figures 3-4 + Supp Fig 2.

### Item 18 — LLM updating

**Status:** ➖ **Not applicable** — no LLM updating performed.

---

## 5. Discussion

### Item 19a — Interpretation

**Status:** ✅ **Addressed** (was ⚠️).
**Evidence:** `manuscript_q1_draft.md` §Discussion §Principal findings
+ §Methodological contribution — the deconfounded fair-comparison cohort
+ §Recency robustness as a clinical-deployment property — synthesises
headline findings including metabolic-flagship and immunological-fair-
cohort wins, plus honestly-reported developmental and neurological
caveats.

### Item 19b — Limitations

**Status:** ✅ **Addressed** (was ⚠️).
**Evidence:** `manuscript_q1_draft.md` §Discussion §Limitations — 8
explicit numbered limitations (no clinical panel; RAGAS chunk-budget
bound; neurological-subgroup weakness; Exomiser developmental advantage;
Qwen3-32B JSON refusals; 8B production model; no DeepRare head-to-head;
Phenopacket-Store cohort representativeness).

### Item 19c — Known data challenges (fairness, representation)

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_q1_draft.md` §Discussion §Fairness and
representation — dedicated subsection covering the three distributional
features that bound generalisability (Phenopacket-Store
published-literature bias, English-language PMC OA bias,
disproportionate-stratification choice), plus explicit acknowledgement
that geno_agent inherits any upstream phenotyping bias.

### Item 19d — Intended use, end-user, autonomy level

**Status:** ✅ **Addressed** (was ⚠️).
**Evidence:** `manuscript_q1_draft.md` §Discussion §Explainability and
the clinical-triage-flag deployment pattern (intended autonomy =
decision-support, not autonomous diagnosis; clinician retains full
responsibility) + §Comparison with existing systems (deployment
scenarios vs DeepRare).

### Item 19e — Handling poor-quality input

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_q1_draft.md` §Discussion §Deployment
operational characteristics — explicit description of the three
protection layers (cohort-construction exclusions, runtime CE-rerank
fallback with logged reason, per-gene LEA confidence threshold at 0.8
for manual-review routing).

### Item 19f — User interaction requirements

**Status:** ✅ **Addressed** (was ⚠️).

**Evidence:** `manuscript_q1_draft.md` §Discussion §Deployment
operational characteristics — explicit description of the required
clinical-genetics expertise (upstream HPO phenotyping + downstream
variant interpretation) and of the clinician-facing UI that fully
automates retrieval and aggregation.

### Item 19g — Future research directions

**Status:** ✅ **Addressed** (was ⚠️).
**Evidence:** `manuscript_q1_draft.md` §Discussion §Future work — 6
concrete extensions explicitly listed (clinical reviewer panel,
prospective evaluation, inline-citation prompting, counterfactual
chunk-removal ablation, non-Phenopacket-Store cohorts, non-HPO-input
modalities).

---

## 6. Summary scorecard (v2.1 — Methods + Discussion prose closure)

| Section | Items | ✅ Addressed | ⚠️ Partial | ❌ Pending | ➖ NA |
|---|---:|---:|---:|---:|---:|
| Title/Abstract | 2 | 2 | 0 | 0 | 0 |
| Introduction | 3 | 3 | 0 | 0 | 0 |
| Methods - Data | 5 | 5 | 0 | 0 | 0 |
| Methods - LLM (output + analytical) | 10 | 7 | 0 | 0 | 3 |
| Methods - Annotation | 1 | 0 | 0 | 0 | 1 |
| Methods - Prompting | 2 | 2 | 0 | 0 | 0 |
| Methods - Other (incl. summarization, tuning, compute, ethics, PPI) | 4 | 2 | 1 | 0 | 2 |
| Methods - Open science (funding/COI/protocol/registration/data/code) | 6 | 6 | 0 | 0 | 0 |
| Results | 6 | 4 | 0 | 0 | 2 |
| Discussion | 7 | 7 | 0 | 0 | 0 |
| **TOTAL (v2.1)** | **46** | **38 (83 %)** | **1 (2 %)** | **0 (0 %)** | **7 (16 %)** |

Of the **39 items that apply** to this study (46 minus 7 NA):
- **38 (97 %)** are fully addressed by current manuscript prose
- **1 (3 %)** is partial — Item 13 (ethics approval), awaiting the UE
  ethics-secretariat signature on the publication-specific exemption
  letter (template at `reports/ue_irb_exemption_request_template.md`).
- **0 (0 %)** are pending

**Headline shift across audit revisions:**

| Status | v1 (2026-05-23) | v2 (re-audit) | v2.1 (prose closure) |
|---|---:|---:|---:|
| ✅ Addressed | 23 | 31 | **38** |
| ⚠️ Partial | 16 | 8 | **1** |
| ❌ Pending | 5 | 0 | **0** |

**The single remaining ⚠️ is external** — the UE ethics-secretariat
signature on the publication-specific exemption letter. No remaining
items are blocked by missing experiments, data, or prose.

---

## 7. Pre-submission checklist (v2.1, action items in order)

Updates from v2: items 4-7 from v2 (prose additions to Methods +
Discussion) are now ✅ DONE inline. Remaining items below are all
external actions or final-pass mechanics.

1. [ ] **Obtain UE IRB exemption letter signed for this publication**
   (Item 13) — request template at
   `reports/ue_irb_exemption_request_template.md`. Once received,
   reference its document ID in `manuscript_q1_draft.md` §Declarations
   §Ethics and attach as Supp File 2.

2. [ ] **Generate the TRIPOD-LLM-statement PDF** via
   https://tripod-llm.vercel.app/ using the per-item statuses in §3-5
   above — submit as a supplementary file (Supp File 1).

3. [ ] **Mint Zenodo DOI** for the frozen Qdrant index snapshot at
   submission time. Update Declarations §Availability with the DOI.

4. [ ] **Confirm final co-author list and CRediT contributions** with
   the UE PhD supervisor. Update §Authors and §Authors' contributions.

5. [ ] **Reformat references** from APA to Springer Vancouver per the
   Genome Medicine submission template.

6. [ ] **Draft cover letter + 3-5 suggested reviewers** for the Genome
   Medicine submission portal.

7. [ ] **Final compliance audit with co-authors** — walk this v2.1
   checklist together and confirm every ✅ before submission.

---

## 8. CONSORT-AI assessment

**Verdict:** CONSORT-AI does not apply (extends CONSORT for RCTs).
This is a methodological evaluation study, not an RCT. Per Genome
Medicine reviewer practice, TRIPOD-LLM is the appropriate primary
reporting guideline.

| CONSORT-AI principle | Equivalent in TRIPOD-LLM | This manuscript |
|---|---|---|
| AI intervention specified | Item 6a | Methods §Comparator systems Cell S |
| Inputs and outputs of the AI | Items 6c, 6d | Methods §Comparator systems Cell S |
| Handling of out-of-distribution inputs | Item 19e | Discussion §Limitations + §Explainability |
| Human-AI interaction | Items 19d, 19f | Discussion §Explainability |
| Errors and performance issues | Items 7a, 19b | Results §LLM ablation + Discussion §Limitations |

If Genome Medicine specifically requests CONSORT-AI: *"As a
methodological evaluation study rather than an RCT, the study is
reported per TRIPOD-LLM (Gallifant et al., Nature Medicine 2025); the
CONSORT-AI principles relevant to AI intervention reporting are covered
as documented in Supplementary Table 1."*

---

*TRIPOD-LLM compliance checklist v2.1 — 2026-05-24 (prose-closure
pass). Re-mapped against `manuscript_q1_draft.md` v12 +
`manuscript_methods_draft.md` v3 post Methods §Prompt design and
Discussion §Deployment operational characteristics + §Fairness and
representation. 38 of 39 applicable items fully addressed (was 31 in
v2, 23 in v1); 1 partial (Item 13, awaiting UE signature); 0 pending.
Affiliation set to Universidad Europea (UE) for PhD submission.
Per-item table also rendered as
`reports/tables/supp_table1_tripod_llm.md` for inclusion as
Supplementary Table 1 with the submission package.*
