# Supplementary Table 1 — TRIPOD-LLM (Gallifant et al., 2025) per-item compliance

**Reporting guideline:** TRIPOD-LLM (*Nature Medicine* 31(1):60-69, 2025;
doi:10.1038/s41591-024-03425-5). This re-audit maps every TRIPOD-LLM item to the
manuscript location where it is addressed (or to the rationale when the item is
not applicable to this study class).

**Study class under TRIPOD-LLM tags:** E (LLM evaluation), H (healthcare),
IR (information retrieval). Not applicable: M, D, QA, SS, MT, DG, C, OF.

**Status legend:** ✅ Addressed | ⚠️ Partial | ❌ Pending | ➖ Not applicable

| # | Item (TRIPOD-LLM) | Status | Manuscript location / rationale |
|---|---|---|---|
| **Title and abstract** ||||
| 1 | Title identifies study as LLM evaluation, task, target population, outcome | ✅ | §Title |
| 2 | Structured abstract | ✅ | §Abstract (Background / Methods / Results / Conclusions) |
| **Introduction** ||||
| 3a | Background and clinical-use-case rationale | ✅ | §Background (rare-disease burden; phenotype-driven prioritisation; publication–curation gap; LLMs & RAG; multi-agent systems; hallucination) |
| 3b | Target population and intended use (incl. intended users) | ✅ | §Background + §Discussion (triage-flag deployment) |
| 4 | Study objectives (evaluation vs development) | ✅ | §Background + Methods opening |
| **Methods — Data** ||||
| 5a | Data sources (training / tuning / evaluation, separately) | ✅ | Methods §Cohort + §Index construction |
| 5b | Data-point distribution and dataset descriptors | ✅ | Methods §Cohort + Results §Cohort setup |
| 5c | Date range of training and evaluation text | ✅ | Methods §Cohort (PMID 1988–2024) + §Index (PMC OA to 2026-05); pinned ontology versions |
| 5d | Preprocessing and quality checking | ✅ | Methods §Cohort (4-criterion filter) + §Index (MeSH filter; 512-token chunking; PubMedBERT tokeniser) |
| 5e | Missing / imbalanced data | ✅ | Methods §Cohort exclusions + Results §Ablation (JSON refusals) + §Explainability (LEA fallback 0.2 %) |
| **Methods — LLM (analytical and output)** ||||
| 6a | LLM name, version, last training date | ✅ | Methods §Comparator systems, Cell S (Qwen3-8B; vLLM 0.20.1; ablation models + GPT-4o judge) |
| 6b | LLM development process (architecture, training, alignment) | ➖ | Not applicable — evaluation study, no fine-tuning |
| 6c | Prompt and inference settings (seed, temperature, etc.) | ✅ | Methods §Comparator systems + §Reproducibility |
| 6d | Initial vs post-processed LLM output | ✅ | Methods, Cell S (LEA JSON schema + tolerant parser + CE-rerank fallback) |
| 6e | Classification thresholds | ➖ | Not applicable — ranking task, not threshold classification |
| 7a | Output quality metrics (consistency, accuracy, errors) | ✅ | Methods §Metrics + §RAG-quality + §Explainability |
| 7b | Outcome metrics' deployment relevance + correlation to human eval | ✅ | §Discussion §Explainability (triage flag, 33–39 pp gap); §Limitations item 1 |
| 7c | Outcome definition, prediction code, inference dates | ✅ | Methods §Metrics + §Reproducibility |
| 7d | Subjective assessor qualifications | ➖ | Not applicable — objective outcome (causal-gene rank), gold standard from Phenopacket Store |
| 7e | Performance comparison to other systems | ✅ | Results §§Overall–Ablation + §Discussion; Tables 2–4, Figs 3–4 |
| **Methods — Annotation** ||||
| 8 | Annotation process | ➖ | Not applicable — pre-curated Phenopacket Store cases; no annotation performed |
| **Methods — Prompting** ||||
| 9a | Prompt design / curation / selection process | ✅ | Methods §Prompt design (single pass; no A/B; no exemplars; no chain-of-thought) |
| 9b | Data used to develop prompts | ✅ | Methods §Prompt design (no cohort or ablation case used to tune) |
| **Methods — Other** ||||
| 10 | Summarisation preprocessing | ➖ | Not applicable — ranking task, not summarisation |
| 11 | Instruction tuning / alignment | ➖ | Not applicable — no fine-tuning |
| 12 | Compute reporting | ✅ | Results §Computational profile + Table 1 (1× RTX 5090, 32 GB) |
| 13 | Ethics approval / IRB | ⚠️ | §Declarations §Ethics — statement present; Universidad Europea exemption confirmation letter pending signature (drafted, to ship as Supplementary File 2; request template at `reports/ue_irb_exemption_request_template.md`) |
| **Methods — Open science** ||||
| 14a | Funding source | ✅ | §Funding (UE doctoral research; no external grants; $117.82 cloud spend self-funded) |
| 14b | Conflicts of interest | ✅ | §Competing interests (none) |
| 14c | Study-protocol availability | ✅ | §Availability (public repository + protocol documentation) |
| 14d | Study registration | ✅ | §Ethics (explicit no-registration statement) |
| 14e | Data availability | ✅ | §Availability — Phenopacket Store v0.1.26, PMC OA; benchmark cohorts DOI 10.6084/m9.figshare.32814449 (standard) and 10.6084/m9.figshare.32816468 (hard) with Croissant 1.0+RAI; per-case sidecars in system item DOI 10.6084/m9.figshare.32814497 |
| 14f | Code availability | ✅ | §Availability — github.com/Jangulo7/geno_agent under AGPL-3.0, archived on Figshare (system item DOI 10.6084/m9.figshare.32814497) |
| **Methods — Patient and public involvement** ||||
| 15 | Patient and public involvement | ✅ | §Ethics (explicit no-PPI statement) |
| **Results** ||||
| 16a | Patient / text flow through study | ✅ | Methods §Cohort + Figure 1 (CONSORT-style flow) |
| 16b | Patient characteristics | ✅ | Methods §Cohort + Results §Cohort setup |
| 16c | Distribution comparison (development vs evaluation) | ➖ | Not applicable — evaluation-only study, no development split |
| 16d | n per analysis | ✅ | Results throughout (full 1,047; fair 282; recency 601/446; ablation 300; RAGAS 600; DeepEval 100) |
| 17 | Performance reporting | ✅ | Results §§Overall–Ablation + Tables 2–4, Figs 3–4 |
| 18 | LLM updating | ➖ | Not applicable — no LLM updating performed |
| **Discussion** ||||
| 19a | Interpretation of results | ✅ | §Discussion §Principal findings + §Methodological contribution + §Recency |
| 19b | Limitations | ✅ | §Discussion §Limitations (8 numbered items) |
| 19c | Known data challenges (fairness, representation) | ✅ | §Discussion §Fairness and representation |
| 19d | Intended use, end-user, autonomy level | ✅ | §Discussion §Explainability (decision support, not autonomous) + §Comparison |
| 19e | Handling of poor-quality input | ✅ | §Discussion §Deployment (three protection layers) |
| 19f | User-interaction requirements / expertise | ✅ | §Discussion §Deployment |
| 19g | Future research directions | ✅ | §Discussion §Future work (6 extensions) |

## Summary

| Status | Count | % of total | % of applicable |
|---|---:|---:|---:|
| ✅ Addressed | 38 | 81 % | 97 % |
| ⚠️ Partial | 1 | 2 % | 3 % |
| ❌ Pending | 0 | 0 % | 0 % |
| ➖ Not applicable | 8 | 17 % | — |
| **Total** | **47** | **100 %** | **39 applicable** |

**Headline shift across audit revisions:** v1 (pre-drafting): 23 ✅ / 16 ⚠️ / 5 ❌.
v2 (post-drafting re-audit): 31 ✅ / 8 ⚠️ / 0 ❌. v2.2 (current): **38 ✅ / 1 ⚠️ / 0 ❌**
of 39 applicable items.

The single remaining ⚠️ is Item 13 (ethics approval), awaiting the Universidad Europea
ethics-secretariat signature on the publication-specific exemption confirmation letter
(draft provided in LaTeX; request/confirmation template at
`reports/ue_irb_exemption_request_template.md`). No items remain blocked by missing
experiments, data, or prose.

---

*Supplementary Table 1 — TRIPOD-LLM per-item compliance for the geno_agent (P2)
manuscript. Companion to `reports/tripod_llm_compliance.md`. LaTeX version:
`supp_table1_tripod_llm.tex`.*
