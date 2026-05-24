# Supplementary Table 1 — TRIPOD-LLM (Gallifant et al., 2025) per-item compliance

**Reporting guideline:** TRIPOD-LLM (*Nature Medicine* 31:60-69, 2025;
doi:10.1038/s41591-024-03425-5). Re-audit v2 of `tripod_llm_compliance.md`
maps every TRIPOD-LLM item to the manuscript location where it is addressed
(or to the rationale when the item is not applicable to this study class).

**Study class under TRIPOD-LLM tags:** E (LLM evaluation), H (healthcare),
IR (information retrieval). Not applicable: M, D, QA, SS, MT, DG, C, OF.

**Status legend:** ✅ Addressed | ⚠️ Partial | ❌ Pending | ➖ Not applicable

| # | Item (TRIPOD-LLM) | Status | Manuscript location / rationale |
|---|---|---|---|
| **Title and Abstract** ||||
| 1 | Title — identifies study as LLM evaluation, task, target population, outcome | ✅ | `manuscript_q1_draft.md` §Title (3 candidates) |
| 2 | Structured abstract | ✅ | `manuscript_q1_draft.md` §Abstract (350 w at GM limit; Background / Methods / Results / Conclusions; 13 keywords) |
| **Introduction** ||||
| 3a | Background and clinical-use-case rationale | ✅ | §Background §§Rare-disease diagnostic burden, Phenotype-driven computational prioritisation, The publication-curation gap, LLMs and RAG, Multi-agent LLM systems in biomedicine, LLM evaluation and the hallucination problem |
| 3b | Target population and intended use (incl. intended users) | ✅ | §Background §The gap this study addresses + §Discussion §Explainability and the clinical-triage-flag deployment pattern |
| 4 | Study objectives (evaluation vs development) | ✅ | §Background §The gap this study addresses + `manuscript_methods_draft.md` Methods opening |
| **Methods — Data** ||||
| 5a | Data sources (training/tuning/evaluation, separately) | ✅ | Methods §Cohort construction + §Index construction |
| 5b | Data-point distribution and dataset descriptors | ✅ | Methods §Cohort construction + §Results §Cohort and evaluation setup |
| 5c | Date range of training and evaluation text | ✅ | Methods §Cohort (PMID 1988-2024 median 2018) + §Index (PMC OA to 2026-05); pinned ontology versions |
| 5d | Preprocessing and quality checking | ✅ | Methods §Cohort (4-criterion inclusion filter) + §Index (MeSH filter, 512-token chunking, PubMedBERT tokeniser, UUID5 IDs) |
| 5e | Missing / imbalanced data | ✅ | Methods §Cohort exclusions + §Results §LLM-family ablation (Qwen3-32B JSON refusals reported) + §Local explainability (LEA-fallback 0.2 %) |
| **Methods — LLM (analytical and output)** ||||
| 6a | LLM name, version, last training date | ✅ | Methods §Comparator systems Cell S (Qwen3-8B [Yang 2025], vLLM 0.20.1; ablation models + GPT-4o judge specified) |
| 6b | LLM development process (architecture, training, alignment) | ➖ | Not applicable — evaluation study, no fine-tuning; explicit statement in Methods §Comparator systems |
| 6c | Prompt + inference settings (seed, temperature, etc.) | ✅ | Methods §Comparator systems Cell S + §Reproducibility infrastructure |
| 6d | Initial vs post-processed LLM output | ✅ | Methods §Comparator systems Cell S (LEA JSON schema + 5-shape tolerant parser + CE-rerank fallback) |
| 6e | Classification thresholds | ➖ | Not applicable — task is ranking, not threshold classification |
| 7a | Output quality metrics (consistency, accuracy, errors) | ✅ | Methods §Evaluation metrics + §RAG-quality evaluation + §Local explainability analysis |
| 7b | Outcome metrics' deployment relevance + correlation to human eval | ✅ | §Discussion §Explainability — triage-flag deployment pattern with 33-39 pp gap between high- and low-faithfulness cases; §Limitations item 1 honestly flags absence of clinical Likert panel |
| 7c | Outcome definition, prediction code, inference dates | ✅ | Methods §Evaluation metrics + §Reproducibility infrastructure + Methods checklist for Q1 reviewers (inference dates) |
| 7d | Subjective assessor qualifications | ➖ | Not applicable — outcome (causal-gene rank) is objective; gold standard from Phenopacket Store SOLVED status |
| 7e | Performance comparison to other systems | ✅ | §Results §§Overall through §LLM-family ablation + §Discussion §Comparison with existing systems + Tables 2-4, Figures 3-4, Supp Fig 2 |
| **Methods — Annotation** ||||
| 8 | Annotation process | ➖ | Not applicable — Phenopacket Store provides pre-curated cases; no annotation performed by us |
| **Methods — Prompting** ||||
| 9a | Prompt design / curation / selection process | ✅ | Methods §Prompt design and curation (single design pass, no formal A/B iteration, no exemplars, no chain-of-thought) + §Comparator systems Cell S |
| 9b | Data used to develop prompts | ✅ | Methods §Prompt design and curation — explicit statement that no case from the n = 1,047 cohort or n = 300 ablation was used to develop or tune the prompt |
| **Methods — Other** ||||
| 10 | Summarization preprocessing | ➖ | Not applicable — task is ranking, not summarization |
| 11 | Instruction tuning / alignment | ➖ | Not applicable — no fine-tuning |
| 12 | Compute reporting | ✅ | §Results §Computational profile + Table 1 (per-cell wallclock, throughput, cost); hardware = 1 × RTX 5090 32 GB + 64 GB RAM |
| 13 | Ethics approval / IRB | ⚠️ | §Declarations §Ethics approval — statement present, UE IRB exemption letter pending signature (template at `reports/ue_irb_exemption_request_template.md`) |
| **Methods — Open science** ||||
| 14a | Funding source | ✅ | §Declarations §Funding (UE doctoral research; no external grants; $119.62 cloud spend self-funded) |
| 14b | Conflicts of interest | ✅ | §Declarations §Competing interests (none) |
| 14c | Study protocol availability | ✅ | §Declarations §Availability of data and materials (repo + paper_extension_plan_v3.md + MASTER_PROJECT_v2.2.md publicly available) |
| 14d | Study registration | ✅ | §Declarations §Ethics approval — explicit no-registration sentence |
| 14e | Data availability | ✅ | §Declarations §Availability — Phenopacket Store v0.1.26, PMC OA, committed sidecars at `data/eval_1050/cell_*/`, Zenodo DOI flagged pending |
| 14f | Code availability | ✅ | §Declarations §Availability — github.com/Jangulo7/geno_agent under MIT (proposed) |
| **Methods — PPI** ||||
| 15 | Patient and public involvement | ✅ | §Declarations §Ethics approval — explicit no-PPI paragraph |
| **Results** ||||
| 16a | Patient / text flow through study | ✅ | Methods §Cohort + Figure 1 (CONSORT-style flow, 300 dpi) |
| 16b | Patient characteristics | ✅ | Methods §Cohort + §Results §Cohort and evaluation setup |
| 16c | Distribution comparison (development vs evaluation) | ➖ | Not applicable — evaluation-only study, no development split |
| 16d | n per analysis | ✅ | §Results throughout (full 1,047; fair 282; recency 601/446; ablation 300; RAGAS 600; DeepEval 100; per-MONDO) |
| 17 | Performance reporting | ✅ | §Results §§Overall through §LLM-family ablation + Tables 2-4, Figures 3-4, Supp Fig 2 |
| 18 | LLM updating | ➖ | Not applicable — no LLM updating performed |
| **Discussion** ||||
| 19a | Interpretation of results | ✅ | §Discussion §Principal findings + §Methodological contribution + §Recency robustness |
| 19b | Limitations | ✅ | §Discussion §Limitations (8 explicit numbered items) |
| 19c | Known data challenges (fairness, representation) | ✅ | §Discussion §Fairness and representation — dedicated subsection on Phenopacket-Store published-literature bias, English-language PMC OA bias, disproportionate-stratification rationale, upstream HPO-phenotyping bias |
| 19d | Intended use, end-user, autonomy level | ✅ | §Discussion §Explainability (decision-support, not autonomous; clinician retains responsibility) + §Comparison with existing systems |
| 19e | Handling of poor-quality input | ✅ | §Discussion §Deployment operational characteristics — three protection layers (cohort exclusions, CE-rerank fallback, confidence threshold 0.8) |
| 19f | User interaction requirements / expertise | ✅ | §Discussion §Deployment operational characteristics — required clinical-genetics expertise upstream + downstream, clinician-facing UI automation |
| 19g | Future research directions | ✅ | §Discussion §Future work (6 concrete extensions enumerated) |

## Summary

| Status | Count | % of total | % of applicable |
|---|---:|---:|---:|
| ✅ Addressed | 38 | 83 % | 97 % |
| ⚠️ Partial | 1 | 2 % | 3 % |
| ❌ Pending | 0 | 0 % | 0 % |
| ➖ Not applicable | 7 | 16 % | — |
| **Total** | **46** | **100 %** | **39 applicable** |

**Headline shift across audit revisions:** v1 (pre-drafting): 23 ✅
/ 16 ⚠️ / 5 ❌. v2 (post-drafting re-audit): 31 ✅ / 8 ⚠️ / 0 ❌.
v2.1 (prose closure pass): **38 ✅ / 1 ⚠️ / 0 ❌**.

The single remaining ⚠️ is Item 13 (ethics approval), awaiting the UE
ethics-secretariat signature on the publication-specific exemption
letter (request template at
`reports/ue_irb_exemption_request_template.md`). No items remain
blocked by missing experiments, data, or prose.

---

*Supplementary Table 1 — TRIPOD-LLM per-item compliance for
geno_agent Q1 manuscript. Re-audit v2.1 — 2026-05-24. Companion to
`reports/tripod_llm_compliance.md` v2.1.*
