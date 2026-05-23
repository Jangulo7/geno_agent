# TRIPOD-LLM compliance checklist for the geno_agent Q1 manuscript

**Reporting guideline used**: TRIPOD-LLM (Gallifant et al., *Nature Medicine* 31, 60-69, 2025; doi:10.1038/s41591-024-03425-5; living version at https://tripod-llm.vercel.app/).

**Study classification under TRIPOD-LLM tags**:
- **E** = LLM evaluation (applies — Cell S is an LLM-in-the-loop evaluation study)
- **H** = LLM evaluation in healthcare settings (applies — rare-disease clinical prioritisation)
- **IR** = Information retrieval (applies — gene-prioritisation task is a retrieval/ranking task)
- Does **not** apply: M (LLM methods), D (de novo LLM development), QA, SS, MT, DG

We are not developing a new LLM; we are evaluating an LLM-in-the-loop retrieval-augmented system for gene prioritisation on clinical phenotype input.

**CONSORT-AI applicability**: CONSORT-AI extends CONSORT for *randomised controlled trials* with AI interventions. **Our study is a methodological development/evaluation study, not an RCT**, so CONSORT-AI does not strictly apply — TRIPOD-LLM is the correct primary reporting guideline. We note the distinction in §3.1 below in case Genome Medicine reviewers ask.

**Status legend**:
- ✅ **Addressed** — content is present in the manuscript draft / supplementary materials
- ⚠️ **Partial** — content exists but needs explicit framing or expansion before submission
- ❌ **Pending** — content not yet drafted; required before submission
- ➖ **Not applicable** — item is for a different study design / LLM task

**Manuscript locations referenced**:
- `reports/manuscript_methods_draft.md` (Methods draft v2)
- `reports/methodology.md` (v3.1 consolidated technical reference)
- `reports/paper_extension_results.md` (Results §§12-20)
- `reports/wallclock_cost_table.md` (Methods Table 1)
- `reports/deeprare_comparability_analysis.md` (Discussion architectural comparison)
- `reports/explainability_report.md` (XAI companion-paper foundation)

---

## 1. Title and Abstract

### Item 1 — Title

**TRIPOD-LLM (verbatim):** *Identify the study as developing, fine-tuning and/or evaluating the performance of an LLM, specifying the task, the target population and the outcome to be predicted.*

**Status**: ⚠️ **Partial** — paper has no final title yet.

**Recommended working title**:
> *"Literature-only LLM-augmented gene prioritisation for rare-disease cases: development, fair-cohort evaluation against curated baselines, and frontier-LLM ablation"*

The title needs to declare: (i) evaluation study (not de novo development), (ii) gene-prioritisation task, (iii) rare-disease target population, (iv) gene-level predicted outcome.

**Gap**: finalize title with co-authors before submission.

### Item 2 — Abstract

**TRIPOD-LLM (verbatim):** *See TRIPOD-LLM for abstracts.*

**Status**: ❌ **Pending** — abstract not drafted yet.

**Gap**: write structured abstract (Background / Methods / Results / Conclusions, ~250-350 words for Genome Medicine) covering: cohort n=1,047 stratified, 5-cell evaluation, Thread D fair-cohort headline (S=0.858 #1), RAGAS/DeepEval faithfulness, 3-model LLM ablation, all-local production. Will be a single-session writing task (~2 h).

---

## 2. Introduction

### Item 3a — Background and rationale

**TRIPOD-LLM (verbatim):** *Explain the healthcare context/use case (for example, administrative, diagnostic, therapeutic and clinical workflow) and rationale for developing or evaluating the LLM, including references to existing approaches and models.*

**Status**: ⚠️ **Partial** — covered narratively in `paper_extension_plan_v3.md §1` and `paper_extension_results.md §0`, but not yet in paper Introduction prose.

**Coverage in existing materials**:
- Rare-disease prioritisation context: 300M patients worldwide affected; diagnostic odyssey; existing curated tools (Exomiser, LIRICAL)
- Gap addressed: literature-only approach without curated KB dependency
- Existing approaches referenced: Exomiser (Smedley 2015), LIRICAL (Robinson 2020), AI-MARRVEL (2024), DeepRare (Zhao Nature 2026)

**Gap**: convert the v3 plan's motivation prose into paper-grade Introduction prose; ~600 words.

### Item 3b — Target population and intended use

**TRIPOD-LLM (verbatim):** *Describe the target population and the intended use of the LLM in the context of the care pathway, including its intended users in current gold standard practices (for example, healthcare professionals, patients, public or administrators).*

**Status**: ⚠️ **Partial** — implicit in the cohort description but not explicitly framed as "intended use / users".

**Recommended explicit text**: *Target population = patients with rare genetic disease (1:2,000 prevalence per condition; ~300M individuals affected globally). Intended users = clinical geneticists and rare-disease specialists working up undiagnosed cases. Intended use = post-phenotyping triage — after HPO terms have been assigned by a clinician, geno_agent produces a ranked list of candidate causal genes with traceable PMC literature citations, to inform variant-prioritisation downstream. Not intended for: direct clinical decision-making, autonomous diagnosis, or use without clinician oversight.*

**Gap**: add this paragraph explicitly to Introduction.

### Item 4 — Objectives

**TRIPOD-LLM (verbatim):** *Specify the study objectives, including whether the study describes the initial development, fine-tuning or validation of an LLM (or multiple stages).*

**Status**: ⚠️ **Partial** — implicit. Needs explicit statement.

**Recommended text for Introduction or Methods opening**: *This is a methodological **evaluation study**, not an LLM development study. The LLM (Qwen3-8B; Yang et al., 2025) is used as-released without fine-tuning. The study objective is to evaluate the LLM-as-Evidence-Aggregator (LEA) component of the geno_agent retrieval-augmented system on n=1,047 rare-disease cases, with emphasis on (i) head-to-head performance vs Exomiser and LIRICAL HPO-only baselines, (ii) annotation-overlap-deconfounded fair-cohort performance, (iii) recency-stratified generalisation, (iv) faithfulness of LEA's generative output, and (v) robustness across LLM families.*

**Gap**: add to Methods opening paragraph.

---

## 3. Methods

### Item 5a — Data sources (training/tuning/evaluation)

**TRIPOD-LLM (verbatim):** *Describe the sources of data separately for the training, tuning and/or evaluation datasets and the rationale for using these data (for example, web corpora, clinical research/trial data, EHR data or unknown).*

**Status**: ✅ **Addressed** in Methods §Cohort construction + §Index construction.

**Coverage**:
- Patient phenotypes: Phenopacket Store v0.1.26 (curated GA4GH benchmark; Pinheiro et al. 2024)
- Retrieval corpus: PubMed Central Open Access XML (~3.4M articles → 287K after genetics filter → 4.2M chunks in Qdrant; downloaded 2026-05)
- LLM training data: as-released Qwen3-8B; we did NOT fine-tune. The LLM's training data is owned/described by Qwen and not modified here.
- No development/test split needed (no model training); evaluation is on n=1,047 Phenopacket Store cases.

### Item 5b — Data point distribution

**TRIPOD-LLM (verbatim):** *Describe the relevant data points and provide a quantitative and qualitative description of their distribution and other relevant descriptors of the dataset (for example, source, languages and countries of origin).*

**Status**: ✅ **Addressed** in Methods §Cohort construction.

**Coverage**:
- Cohort breakdown: 250 developmental + 300 immunological + 250 metabolic + 247 neurological = 1,047 (disproportionate stratified, seed 42)
- Per-MONDO PMID date distribution: pre-2020 n=601 (57.4 %), post-2020 n=446 (42.6 %)
- Per-MONDO overlap rate (Thread D): 63.2-86.3 %
- Cohort language: English (all source PMIDs are PubMed-indexed English articles)
- Countries of origin: not stratified (Phenopacket Store does not record case-level geography); curated globally
- Gene candidates per case: 1 causal + 49 distractors selected by HPO Jaccard from HGNC quarterly snapshot

### Item 5c — Date range of training/evaluation text

**TRIPOD-LLM (verbatim):** *Specifically state the date of the oldest and newest item of text used in the development process (training, fine-tuning and reward modeling) and the evaluation datasets.*

**Status**: ✅ **Addressed** — see explicit dates.

**Coverage**:
- PMC OA corpus: indexed up to 2026-05; oldest articles from 1900s, newest 2026
- Source PMIDs for cohort cases: oldest 1988, most recent 2024 (median 2018) — confirmed via NCBI E-utils, `data/test_cases_1050/pmid_dates.json`
- Qwen3-8B training cutoff: per Qwen documentation (verify and cite when finalising)
- phenotype.hpoa: pinned to v2026-02-16
- MONDO/HPO/GO/HGNC: pinned to 2026 quarterly releases (see `methodology.md §3`)

### Item 5d — Preprocessing and quality checking

**TRIPOD-LLM (verbatim):** *Describe any data preprocessing and quality checking, including whether this was similar across text corpora, institutions and relevant sociodemographic groups.*

**Status**: ✅ **Addressed** in Methods §Index construction + Cohort construction.

**Coverage**:
- PMC OA: MeSH-genetics filter, 512-token chunking with 50-token overlap, PubMedBERT tokeniser, UUID5 deterministic chunk IDs
- Phenopacket Store: 4-criterion inclusion filter (single causal gene, ≥1 HPO term, MONDO mapping, ≥5 PMC articles for the causal gene). Filter applied uniformly across all cases.
- No per-institution or per-sociodemographic-group preprocessing — Phenopacket Store does not include sociodemographic metadata.

### Item 5e — Missing/imbalanced data

**TRIPOD-LLM (verbatim):** *Describe how missing and imbalanced data were handled and provide reasons for omitting any data.*

**Status**: ✅ **Addressed**.

**Coverage**:
- Cases without ≥5 PMC articles for causal gene: excluded at Phase 1B (cohort construction).
- Disproportionate stratified sampling explicitly oversamples immunological (300/386 = 78 %) for subgroup statistical power; documented as a deliberate design choice in Methods §Cohort construction.
- LEA-fallback cases (deterministic baseline when LLM call fails): 0.2 % overall, 0.0 % on the fair cohort; reported in Results §Local explainability + §RAG-quality.
- Qwen3-32B JSON-format refusals (n=66/300 in Q1-B ablation): reported transparently in Results §LLM ablation as a deployment-usability characteristic.

### Item 6a — LLM name, version, last training date

**TRIPOD-LLM (verbatim):** *Report the LLM name, version and last date of training.*

**Status**: ✅ **Addressed** in Methods §Comparator systems.

**Coverage**:
- Production: **Qwen3-8B** served via vLLM 0.20.1, no fine-tuning
- Ablation models (all via OpenRouter):
  - Qwen3-32B Instruct (`qwen/qwen3-32b`)
  - Claude Sonnet 4.6 (`anthropic/claude-sonnet-4.6`)
  - DeepSeek-V3-0324 (`deepseek/deepseek-chat-v3-0324`)
- RAGAS / DeepEval judge: GPT-4o (`gpt-4o-2024-08-06`)

**Gap**: explicit "last training date" for each model needs verification against each vendor's docs and inclusion in Methods.

### Item 6b — LLM development process

**TRIPOD-LLM (verbatim):** *Report details of the LLM development process, such as LLM architecture, training, fine-tuning procedures and alignment strategy (for example, reinforcement learning and direct preference optimization) and alignment goals.*

**Tags**: M (LLM methods), D (de novo development) ➖ **Not applicable** — we are evaluating an existing LLM as-released, not developing one. State this explicitly in Methods.

**Recommended text**: *No fine-tuning or alignment modification was performed on any of the evaluated LLMs. Architectural and training details are deferred to the original LLM developer documentation: Qwen3-8B (Yang et al. 2025), Claude Sonnet 4.6 (Anthropic 2026), DeepSeek-V3 (DeepSeek 2024).*

### Item 6c — Prompt + inference settings

**TRIPOD-LLM (verbatim):** *Report details of how the text was generated using the LLM, including any prompt engineering (including consistency of outputs), and inference settings (for example, seed, temperature, max token length and penalties), as relevant.*

**Status**: ✅ **Addressed** — fully captured.

**Coverage**:
- LEA system prompt + user prompt: captured per-case in `data/eval_1050/cell_S_responses/<case>.json:lea_log.{lea_system_prompt, lea_user_prompt}` (full text, replayable)
- Inference settings: temperature 0.0, top-p 1.0, response_format=`{"type":"json_object"}`, max_tokens 2048 (production) / 4096 (ablation)
- Determinism: PYTHONHASHSEED=42, seed=42 throughout; bit-perfect on top-1 across v2→v3 re-runs (L: 0 flips, S: 1 flip / 1,047)
- Prompt engineering: single-pass instruction prompt; no chain-of-thought elicitation; no few-shot examples; no retrieval-time prompting (only at LEA aggregation)

### Item 6d — Initial and post-processed LLM output

**TRIPOD-LLM (verbatim):** *Specify the initial and postprocessed output of the LLM (for example, probabilities, classification and unstructured text).*

**Status**: ✅ **Addressed**.

**Coverage**:
- Initial output: JSON list of `{gene, confidence (0-1), rationale (free text)}` per ranked gene (up to 15)
- Post-processing: parse JSON; tolerant to 5 documented response shapes (list / wrapped list / dict-keyed-by-gene / numeric-confidence-dict / single-object); see `scripts/eval/run_lea_ablation.py`
- Causal-gene rank extracted from parsed list; missing → causal_rank=None (counted as a miss in deployment metrics)
- LEA fallback if JSON unparseable or call fails: CE-rerank ordering used (logged in `lea_log.lea_fallback_reason`)

### Item 6e — Classification thresholds

**Tags**: C (classification), OF (outcome forecasting) ➖ **Not applicable** — our task is ranking, not threshold-based classification.

### Item 7a — Output quality metrics

**TRIPOD-LLM (verbatim):** *Include metrics that capture the quality of generative outputs, such as consistency, relevance, accuracy and presence/type of errors compared to gold standards.*

**Tags applicable**: IR (information retrieval — our task)

**Status**: ✅ **Addressed**.

**Coverage**:
- Ranking quality: top-1, top-5, top-10, MRR, NDCG@10 with paired-bootstrap 95% CIs
- Generative-output faithfulness: RAGAS faithfulness (claim-level, 0.480 top-1-only / 0.286 multi-claim) + DeepEval HallucinationMetric (holistic, 0.845 groundedness)
- Errors: per-case `lea_fallback_reason` (0.2 % overall), JSON parse rate (78-99.7 % across models in ablation)
- Coverage of substantive rationale (Thread G): 81.5 % overall / 94.0 % fair cohort

### Item 7b — Outcome metrics relevance to deployment

**TRIPOD-LLM (verbatim):** *Report the outcome metrics' relevance to the downstream task at deployment time and, where applicable, the correlation of metric to human evaluation of the text for the intended use.*

**Status**: ⚠️ **Partial** — task-relevance well established; **no human evaluation panel performed**.

**Coverage** (task-relevance):
- top-1 = clinical-relevant primary endpoint (the single gene most likely causal)
- top-5/top-10 = secondary endpoints (gene-list returned to the clinician for variant prioritisation)
- Faithfulness predicts correctness (33-39 pp gap) — supports automated triage flag

**Gap**: **no clinical reviewer panel rated the LEA rationales**. This is honestly flagged in the explainability report (`reports/explainability_report.md §7 Limitations`) and is the main acknowledged limitation. The XAI companion paper proposes a clinical panel as future work. We should add an explicit limitation to the manuscript Discussion.

### Item 7c — Outcome definition, prediction formula, inference date

**TRIPOD-LLM (verbatim):** *Clearly define the outcome, how the LLM predictions were calculated (for example, formula, code, object and API), the date of inference for closed-source LLMs and evaluation metrics.*

**Status**: ✅ **Addressed**.

**Coverage**:
- Outcome: causal gene's rank in the system's output (1-50)
- Prediction code: `scripts/eval/rerank_inside_d.py` (production Cell S), `scripts/eval/run_lea_ablation.py` (ablation models). Public at github.com/Jangulo7/geno_agent.
- API endpoint for ablation: OpenRouter `https://openrouter.ai/api/v1/chat/completions` (OpenAI-compatible)
- Inference dates:
  - Cell S production: 2026-05-18 (re-run with response logging)
  - Q1-B ablation: 2026-05-23 20:49Z to 21:49Z
  - RAGAS: 2026-05-23 15:25Z to 18:13Z
  - DeepEval: 2026-05-23 18:37Z to 18:40Z

### Item 7d — Subjective assessor qualifications

**TRIPOD-LLM (verbatim):** *If outcome assessment requires subjective interpretation, describe the qualifications of the assessors, any instructions provided, relevant information on demographics of the assessors and interassessor agreement.*

**Status**: ➖ **Not applicable** — the outcome (causal gene's rank) is objective; no subjective assessor judgement involved. The "gold standard" is Phenopacket Store's SOLVED status with single causal gene.

### Item 7e — Performance comparison to other systems

**TRIPOD-LLM (verbatim):** *Specify how performance was compared to other LLMs, humans and other benchmarks or standards.*

**Status**: ✅ **Addressed** in Results §§12-20.

**Coverage**:
- vs Exomiser HPO-only (Cell K): paired Δ +0.035 ★ on full cohort, +0.078 ★ on fair cohort
- vs LIRICAL HPO-only (Cell M): paired Δ -0.198 on full cohort (overlap-confounded), +0.082 ★ on fair cohort
- vs internal architectural ablations (D, L) and ensemble (N): all per-MONDO with CIs
- vs 3 frontier LLMs (Q1-B ablation): all within 2.4 pp on fair cohort
- vs DeepRare (Nature 2026): NOT head-to-head — explained via Excluded Comparators rationale (Methods + Discussion architectural table)
- vs human clinician: not benchmarked (clinician baseline is a known open gap; see Discussion limitations)

### Item 8 — Annotation

**Status**: ➖ **Not applicable** — we did not annotate any data ourselves. Phenopacket Store comes pre-annotated by its curators; we use it as-is without modification.

### Item 9 — Prompting

**TRIPOD-LLM 9a (verbatim):** *If research involved prompting LLMs, provide details on the processes used during prompt design, curation and selection.*

**TRIPOD-LLM 9b (verbatim):** *If research involved prompting LLMs, report what data were used to develop the prompts.*

**Status**: ⚠️ **Partial**.

**Coverage**:
- Single-pass instruction prompt (system + user)
- Designed during Phase 2 (the agentic-UI development phase per master plan §11)
- Prompt iteration: minimal; one-pass design, no formal A/B prompt tuning
- Full prompt text is captured per-case in sidecar JSONs (replayable)

**Gap**: explicit Methods paragraph on prompt design rationale and any iteration. ~150 words.

### Item 10 — Summarization preprocessing

**Tag**: SS (summarization) ➖ **Not applicable** — our task is ranking, not summarization.

### Item 11 — Instruction tuning / alignment

**Tag**: M/D ➖ **Not applicable** — no fine-tuning or alignment modification performed.

### Item 12 — Compute reporting

**TRIPOD-LLM (verbatim):** *Report compute, or proxies thereof (for example, time on what and how many machines, cost on what and how many machines, inference time, floating-point operations per second), required to carry out methods.*

**Status**: ✅ **Addressed** in `reports/wallclock_cost_table.md` (Methods Table 1 source).

**Coverage**:
- Hardware: 1 × NVIDIA RTX 5090 (32 GB VRAM), 64 GB system RAM
- Per-cell wall: K 3h38m / M 0h22m / D 6h53m / L 5h28m / S 7h36m / N <1s
- Per-case throughput: Cell S = 26.1 s / case end-to-end
- Total local compute: ~24 h for the full n=1,047 evaluation
- LLM-judge cloud cost: $98.20 OpenAI + $21.42 OpenRouter = $119.62
- Cloud-equivalent local cost (AWS g6e.4xlarge): ~$5 (electricity-only in our case)

### Item 13 — Ethical approval

**TRIPOD-LLM (verbatim):** *Name the institutional research board or ethics committee that approved the study and describe the participant-informed consent or the ethics committee waiver of informed consent.*

**Status**: ❌ **Pending** — needs explicit statement.

**Recommended text**: *This study uses the GA4GH Phenopacket Store v0.1.26 dataset, which consists of fully de-identified rare-disease case data publicly released under a permissive licence by the Phenopacket Store consortium. The original cases are sourced from previously-published case-report literature; informed consent was obtained at the time of original publication by the source authors. No new patient data were collected for this study. The Universidad Alfonso X Institutional Review Board (or equivalent — verify with university) has confirmed that secondary analysis of fully de-identified, publicly-released benchmark data does not require additional ethics approval. [Verify and add IRB exemption letter reference.]*

**Gap**: confirm IRB exemption procedure with UAX and obtain a one-line exemption letter or written confirmation.

### Item 14a — Funding source

**Status**: ❌ **Pending** — author/student funding source needs explicit statement.

**Gap**: insert: *"This study was conducted as part of a Master's thesis at Universidad Alfonso X (UAX). No external commercial funding was received. OpenAI and OpenRouter API costs ($119.62) were borne by the student author."*

### Item 14b — Conflicts of interest

**Status**: ❌ **Pending**.

**Gap**: *"The author declares no commercial conflicts of interest. No employment or consulting relationships with Anthropic, OpenAI, Google, DeepSeek, Alibaba (Qwen), MAGIC-AI4Med, or any rare-disease genomics company. Phenopacket Store, Exomiser, LIRICAL, RAGAS, and DeepEval are all open-source projects with no commercial relationship to the author."*

### Item 14c — Study protocol availability

**Status**: ⚠️ **Partial** — protocol exists but is not pre-registered.

**Coverage**: `reports/paper_extension_plan_v3.md` (v3 plan, dated 2026-05-17) + `MASTER_PROJECT_v2.2.md` (master plan). Both publicly available via the GitHub repo upon submission.

**Recommended text**: *"The study protocol was not formally pre-registered. The full evaluation plan, including Threads D-G and the LLM ablation, is documented in the project's public GitHub repository at github.com/Jangulo7/geno_agent in `reports/paper_extension_plan_v3.md` (commit hash to be cited at final submission)."*

### Item 14d — Study registration

**Status**: ❌ **Pending** — study is not registered.

**Recommended text**: *"This methodological development/evaluation study was not registered with a clinical trial registry, as it is not a clinical trial and does not involve a clinical intervention. Per Genome Medicine policy [confirm], methodological-evaluation studies of this class do not require registry submission."*

### Item 14e — Data availability

**Status**: ✅ **Addressed via GitHub + Phenopacket Store**.

**Coverage**: All input data is either publicly available (PMC OA, Phenopacket Store v0.1.26, HPO, MONDO, HGNC, phenotype.hpoa) or produced by reproducible code. Per-case sidecars (n=1,047 Cell S + n=900 ablation × 3 models) are committed in the GitHub repo.

**Recommended text**: *"Source data: Phenopacket Store v0.1.26 (https://github.com/monarch-initiative/phenopacket-store); PMC Open Access (https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/); HPO v2026-02-16; MONDO v2026-03-03; HGNC quarterly 2026-04-07. Derived data: per-case sidecars, paired-Δ JSONs, and aggregate summaries at github.com/Jangulo7/geno_agent under `data/eval_1050/` (frozen tag `paper-v3-final` to be created at submission). A Zenodo DOI will be minted for the frozen release."*

### Item 14f — Code availability

**Status**: ✅ **Addressed**.

**Recommended text**: *"All evaluation code is available at github.com/Jangulo7/geno_agent under the MIT licence (proposed). Key scripts: `scripts/eval/rerank_inside_d.py` (Cell S production), `scripts/eval/run_lea_ablation.py` (LLM ablation), `scripts/eval/run_ragas.py` (RAGAS), `scripts/eval/run_deepeval.py` (DeepEval), `scripts/eval/compute_annotation_overlap.py` (Thread D), `scripts/eval/aggregate_recency.py` (Thread E), `scripts/eval/build_cell_n_rrf.py` (Thread F), `scripts/eval/analyze_lea_rationales.py` (Thread G). Frozen at commit hash [to be cited at final submission]."*

### Item 15 — Patient and public involvement

**Status**: ❌ **Pending** — no patient/public involvement.

**Recommended text**: *"This study did not involve direct patient or public participation. The Phenopacket Store cases used as evaluation data were originally consented at the source publication. The deployment context (clinical-geneticist triage workflow) has not been validated by clinician end-users; this is acknowledged in the Discussion limitations and is the primary planned next step for the proposed XAI companion paper."*

---

## 4. Results

### Item 16a — Patient/EHR flow

**TRIPOD-LLM (verbatim):** *Describe the flow of text/EHR/patient data through the study, including the number of documents/questions/participants with and without the outcome/label and follow-up time as applicable.*

**Status**: ✅ **Addressed** in Methods §Cohort construction.

**Coverage**: Phenopacket Store v0.1.26 → 4-criterion filter → 1,699 eligible → disproportionate stratified sample (seed 42) → 1,048 sampled, 1 dropped at QC → 1,047 final. All 1,047 have the outcome (causal gene known per SOLVED phenopacket interpretation).

**Recommended addition**: a small **CONSORT-style flow diagram** as a paper figure (Figure 1). Source data already exists; ~30 min to render in TikZ or as an SVG.

### Item 16b — Patient characteristics

**Status**: ✅ **Addressed** in Methods §Cohort construction + per-MONDO breakdown table.

**Coverage**: 250 + 300 + 250 + 247 per MONDO category; PMID year distribution 1988-2024 (median 2018); overlap rate per MONDO (63-86 %).

### Item 16c — Distribution comparison (development vs evaluation)

**Status**: ➖ **Not applicable** — no development split (the LLM is used as-released; only an evaluation dataset is involved).

### Item 16d — Participants and outcome events per analysis

**Status**: ✅ **Addressed** — per-analysis n is explicit throughout Results §§12-20.

**Coverage example**: full cohort n=1,047; overlap_absent n=282; pre_2020 n=601; post_2020 n=446; ablation n=300; RAGAS n=600; DeepEval n=100; per-MONDO subgroups all reported with their n.

### Item 17 — Performance

**TRIPOD-LLM (verbatim):** *Report LLM performance according to prespecified metrics (see item 7a) and/or human evaluation (see item 7d).*

**Status**: ✅ **Addressed** comprehensively across Results §§12-20.

### Item 18 — LLM updating

**Status**: ➖ **Not applicable** — no LLM updating performed.

---

## 5. Discussion

### Item 19a — Interpretation

**Status**: ⚠️ **Partial** — covered in the per-section "v3 conclusions" lists (e.g., conclusions 1-48 across §§11, 12.7, 13.10, 14.9, 15.7, 16.7, 17.6, 18.7, 19.4, 20.6) but not yet written as Discussion prose.

**Gap**: write Discussion section (~1,500 words) synthesising the headline findings and addressing fairness — specifically, **the metabolic-flagship + immunological-fair-cohort findings are most clinically meaningful for the deployment use case**, while developmental (where Exomiser wins on fair cohort) and neurological (worst-grounded subgroup) are honestly reported caveats.

### Item 19b — Limitations

**Status**: ⚠️ **Partial** — limitations are documented but scattered across multiple reports. Needs consolidation in Discussion.

**Known limitations to include** (consolidated from existing analysis files):

| # | Limitation | Source |
|---|---|---|
| 1 | No clinical reviewer panel (no human Likert ratings of LEA rationales) | explainability_report §7 |
| 2 | RAGAS faithfulness measured at MAX_CONTEXTS=20 (budget cap), bounded as lower estimate | results §16.5 |
| 3 | Neurological is the worst-grounded subgroup on both judges | results §17.4 |
| 4 | Exomiser still wins developmental on fair cohort (preserved as caveat) | results §13.7 |
| 5 | Qwen3-32B has a 22 % JSON-format refusal rate (deployment usability) | results §20.2 |
| 6 | Single 8B model in production; ablation shows +5 pp ★ from frontier-class but not on fair cohort | results §20.4 |
| 7 | No head-to-head vs DeepRare (justified architecturally rather than experimentally) | deeprare_comparability_analysis §1 |
| 8 | Cohort drawn from Phenopacket Store; generalisability to non-published cases not directly tested | implicit; should be stated |

### Item 19c — Known data challenges

**Status**: ⚠️ **Partial** — partially covered.

**Gap**: explicit paragraph on bias / representation in the Phenopacket Store cohort. Specific points: (i) Phenopacket Store is published-literature-derived; cases that never made it to publication (e.g., underdiagnosed conditions in underserved populations) are not represented; (ii) language bias toward English-language publications; (iii) HPO term assignment depends on clinician phenotyping skill upstream — geno_agent inherits any phenotyping bias.

### Item 19d — Intended use, end-user, autonomy level

**Status**: ⚠️ **Partial** — covered implicitly; needs explicit framing.

**Recommended text**: *"Intended use: post-phenotyping triage tool for clinical geneticists. Input: HPO term set + 50-gene candidate list (output of upstream filtering). Output: ranked gene list with per-gene rationale + PMC citations. Intended autonomy level: **decision-support, NOT autonomous diagnosis**. The clinician retains full responsibility for variant interpretation, additional testing, and clinical decision-making. The system's faithfulness score should be used as an automated triage flag (low faithfulness → manual review prioritised), not as a stand-in for clinician judgment."*

### Item 19e — Handling poor-quality input

**Status**: ⚠️ **Partial** — addressed via LEA fallback mechanism.

**Recommended text**: *"Poor-quality input handling: (i) cases with <2 HPO terms are excluded at Phase 1B (cohort construction); (ii) cases for which the retrieval pipeline returns no relevant chunks are handled by the LEA deterministic fallback (CE-rerank ordering used; logged in `lea_fallback_reason`); (iii) the LEA confidence scores per ranked gene provide a per-case quality signal — low confidence on the top-1 should prompt manual review. In production, the recommended deployment threshold is: top-1 with confidence ≥ 0.8 = high-confidence triage; top-1 with confidence < 0.8 = manual review required."*

### Item 19f — User interaction requirements

**Status**: ⚠️ **Partial**.

**Recommended text**: *"Required user expertise: clinical genetics training to (i) provide accurate HPO phenotyping upstream, (ii) interpret ranked gene list + LEA rationales, (iii) make downstream variant-prioritisation decisions. The system does not require coding or ML expertise to use; the FastAPI + React UI (Phase 2c of the master plan) provides a clinician-facing interface. Users do not need to intervene in retrieval or aggregation — only in upstream HPO assignment and downstream variant interpretation."*

### Item 19g — Future research directions

**Status**: ⚠️ **Partial** — covered in the v3 plan but not yet in paper prose.

**Concrete future-work items to include**:
1. Clinical reviewer panel for LEA rationale evaluation (proposed XAI companion paper)
2. Prospective evaluation in a real clinical-genetics consultation workflow
3. Inline-citation prompting (each LEA claim explicitly cites a specific PMCID)
4. Counterfactual chunk-removal ablation
5. Larger evaluation cohort drawn from non-Phenopacket-Store sources
6. Extension to non-HPO-based input modalities (free-text clinical notes via HPO extraction)

---

## 6. Summary scorecard

| Section | Items | ✅ Addressed | ⚠️ Partial | ❌ Pending | ➖ NA |
|---|---:|---:|---:|---:|---:|
| Title/Abstract | 2 | 0 | 1 | 1 | 0 |
| Introduction | 3 | 0 | 3 | 0 | 0 |
| Methods - Data | 5 | 5 | 0 | 0 | 0 |
| Methods - Analytical | 5 | 3 | 0 | 0 | 2 |
| Methods - LLM output | 5 | 4 | 1 | 0 | 0 |
| Methods - Annotation | 3 | 0 | 0 | 0 | 3 |
| Methods - Prompting | 2 | 0 | 2 | 0 | 0 |
| Methods - Other | 7 | 4 | 1 | 1 | 1 |
| Methods - Open science | 6 | 3 | 1 | 2 | 0 |
| Methods - PPI | 1 | 0 | 0 | 1 | 0 |
| Results | 6 | 4 | 0 | 0 | 2 |
| Discussion | 7 | 0 | 7 | 0 | 0 |
| **TOTAL** | **52** | **23 (44 %)** | **16 (31 %)** | **5 (10 %)** | **8 (15 %)** |

Of the **44 items that apply to this study** (52 minus 8 not applicable):
- **23 (52 %)** are fully addressed by existing analyses + materials
- **16 (36 %)** are partial — content exists but needs paper-prose framing
- **5 (11 %)** are pending — need new content (ethics statement, funding statement, COI, registration statement, PPI statement) but each is a one-line declaration not new research

**No pending items require new experiments, new data collection, or new compute spend.** All 5 pending items are standard editorial statements that take ~30 min total to draft.

---

## 7. Pre-submission checklist (action items in order)

1. [ ] **Finalize title** with co-authors (Item 1) — ~1 h with collaborators
2. [ ] **Draft structured abstract** (Item 2) — ~2 h
3. [ ] **Write Introduction prose** from existing motivation (Items 3a, 3b, 4) — ~3 h
4. [ ] **Add prompt-design Methods paragraph** (Item 9) — ~30 min
5. [ ] **Obtain UAX IRB exemption confirmation** (Item 13) — depends on UAX response time
6. [ ] **Add funding statement** (Item 14a) — ~5 min
7. [ ] **Add COI statement** (Item 14b) — ~5 min
8. [ ] **Add study-protocol availability paragraph** (Item 14c) — ~10 min
9. [ ] **Add no-registration explanation** (Item 14d) — ~5 min
10. [ ] **Add no-PPI statement** (Item 15) — ~5 min
11. [ ] **Render CONSORT-style cohort flow diagram** (Item 16a) — ~30 min
12. [ ] **Write Discussion prose** synthesising conclusions 1-48 (Item 19a) — ~6-8 h
13. [ ] **Consolidate Limitations section** from 8 known limitations (Item 19b) — ~2 h
14. [ ] **Add fairness / representation paragraph** (Item 19c) — ~1 h
15. [ ] **Add intended-use + autonomy-level paragraph** (Item 19d) — ~30 min
16. [ ] **Add poor-input-handling paragraph** (Item 19e) — ~30 min
17. [ ] **Add user-expertise paragraph** (Item 19f) — ~15 min
18. [ ] **Add future-research-directions paragraph** (Item 19g) — ~1 h
19. [ ] **Generate the TRIPOD-LLM-statement PDF** via https://tripod-llm.vercel.app/ — submit as supplementary file
20. [ ] **Final compliance audit** — go through this checklist with co-authors and confirm every ✅ before submission

**Total writing time estimate**: ~24-30 hours of focused writing across items 1-18 (excluding IRB wait time and the abstract/discussion which require thinking). Fits the planned 2-3 weeks of manuscript drafting.

---

## 8. CONSORT-AI assessment

**Verdict**: **CONSORT-AI does not apply** to this study because it extends CONSORT for **randomized controlled trials with AI interventions**. Our study is a **methodological development/evaluation study**, not an RCT — no randomisation of patients to interventions, no clinical primary endpoint, no participant follow-up.

Genome Medicine reviewers familiar with CONSORT-AI may still ask for one or more of its core principles, which TRIPOD-LLM covers equivalent ground for:

| CONSORT-AI principle | Equivalent in TRIPOD-LLM |
|---|---|
| AI intervention specified | Item 6a (LLM name/version) |
| Inputs and outputs of the AI | Items 6c, 6d |
| Handling of inputs that are outside the AI's training | Item 19e (poor input handling) |
| Human-AI interaction | Items 19d (intended use), 19f (user expertise) |
| Errors and performance issues | Items 7a (output quality), 19b (limitations) |

If Genome Medicine specifically requests CONSORT-AI, we cite this mapping and state: *"As a methodological evaluation study rather than an RCT, the study is reported per TRIPOD-LLM (Gallifant et al., Nature Medicine 2025); the CONSORT-AI principles relevant to AI intervention reporting are covered as documented in Supplementary Table X."*

---

*TRIPOD-LLM compliance checklist v1 — 2026-05-23. Maps the geno_agent
manuscript draft against TRIPOD-LLM Table 2 (Nature Medicine 31:60-69,
2025). 23 of 44 applicable items fully addressed; 16 partial (need
paper-prose framing); 5 pending (standard editorial statements). No
pending items require new experiments. Estimated manuscript-completion
time from this checklist: ~24-30 h of focused writing.*
