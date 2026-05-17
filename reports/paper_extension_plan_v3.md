# Paper Extension Plan v3 — LIRICAL + RAGAS + DeepEval

**Author:** Johanna Angulo (johanna.angulo@gmail.com)
**Date:** 2026-05-17
**Branch:** `paper/n500-validation`
**Supersedes:** [`paper_extension_plan_v2.md`](paper_extension_plan_v2.md) by extending Strategy A with two new workstreams before the DeepRare comparison
**v2 result baseline:** [`paper_extension_results.md`](paper_extension_results.md) (n=1,047, S beats K by Δ=+3.4 pp ★)

---

## 0. TL;DR

After the v2 run produced a Q1-grade headline (Cell S statistically beats
Exomiser HPO-only at n=1,047), we add **two methodological strengtheners** that
the original master plan did not include but are now standard practice for
rare-disease gene-prioritisation papers in 2025-2026:

1. **Cell M — LIRICAL HPO-only baseline.** LIRICAL ([Robinson et al. 2020 AJHG](https://www.cell.com/ajhg/fulltext/S0002-9297(20)30230-5))
   is the de-facto third baseline alongside Exomiser. The EJHG 2026 systematic
   benchmark uses Exomiser + LIRICAL + Phen2Gene as the trio. Adding it
   eliminates the "you only compared against one baseline" reviewer comment.

2. **RAGAS + DeepEval evaluation axis.** Currently we report only end-to-end
   accuracy (top-1/5/10/MRR/NDCG). A reviewer can ask "is the LLM actually
   using the retrieved evidence, or just memorizing genes from training?".
   RAGAS measures faithfulness, context precision, context recall, answer
   relevance. DeepEval measures hallucination rate. **Both are computed by
   an LLM judge** — we will use **GPT-4o via API** as the judge.

3. **Documented project-rule deviation.** `CLAUDE.md` rule: "No cloud LLM API
   in any code path." Using GPT-4o as a RAGAS/DeepEval judge is a deliberate
   deviation **for evaluation only** (not production). Documented in the paper
   Methods and below in §3.5.

Total added work: ~2 weeks of compute + plumbing, ~$50-80 in GPT-4o API spend.

---

## 1. Motivation and additions

### 1.1 What the v2 baseline established

v2 (n=1,047) ([`paper_extension_results.md`](paper_extension_results.md)) showed
Cell S statistically beats Exomiser HPO-only on overall top-1 (Δ=+3.4 pp, CI
[+0.006, +0.064]) with two categorical wins (metabolic +8.4 pp, immunological
+6.7 pp). The immunological lead claim is bulletproof (LOO 300/300, McNemar
p=0.0076).

### 1.2 Why LIRICAL is the next-most-important comparison

The EJHG 2026 benchmark (cited in [`paper_extension_results.md`](paper_extension_results.md))
that we will be compared against uses **Exomiser + LIRICAL + Phen2Gene** as the
trio of curated baselines. We currently have only Exomiser. Reviewers will ask
why LIRICAL is missing.

LIRICAL adds:
- **A second curated-table comparator** — a check that the +Δ over K isn't just
  Exomiser-specific
- **Disease-level priors** (vs Exomiser's gene-level) — different mechanism
- **Likelihood-ratio reasoning** — a well-defined statistical framework
- **HPO-only mode native** — matches our evaluation regime

### 1.3 Why RAGAS / DeepEval is essential for Q1

A Q1 reviewer at Genome Medicine, Bioinformatics, or JAMIA will scrutinise:

| Question | Answered by current eval? | Answered by RAGAS/DeepEval? |
|---|---|---|
| "Is the LLM ranking based on retrieved evidence, not training data?" | ❌ | ✅ Faithfulness |
| "Is retrieval surfacing the right chunks?" | ❌ | ✅ Context precision/recall |
| "Does the gene ranking address the patient phenotype?" | partially (top-1 ≠ semantic alignment) | ✅ Answer relevance |
| "Hallucination rate?" | ❌ | ✅ DeepEval hallucination metric |
| "Top-1/5/10 accuracy" | ✅ | — |

Without RAGAS metrics, a sophisticated reviewer can argue: "your top-1 win might
just be the LLM regurgitating training memorized genes; show that the retrieved
evidence is actually driving the answer." With RAGAS, we have the answer.

---

## 2. Cell M — LIRICAL HPO-only

### 2.1 Tool details

| Property | Value |
|---|---|
| Repo | https://github.com/TheJacksonLaboratory/LIRICAL |
| Version | **v2.4.0** (released 2026-04-09) |
| License | BSD-3-Clause |
| Distribution | `lirical-cli-2.4.0-distribution.zip` (26.5 MB) |
| Runtime | Java 17+ (have Java 21) |
| Mode | `lirical prioritize --observed-phenotypes HP:...,HP:... -d data/ -f tsv -o results/` |
| Output | Disease-level ranking with posttest probability + composite LR |

### 2.2 Critical integration note — disease-to-gene mapping

LIRICAL ranks **diseases**, not genes. To compare against our gene-level evaluation:

1. Parse LIRICAL's TSV/JSON output (ranked diseases with OMIM/MONDO CURIE)
2. Build a `disease_id → [gene_symbol]` lookup from:
   - `phenotype.hpoa` (OMIM → disease)
   - `mim2gene_medgen` (OMIM → NCBI Gene)
   - `Homo_sapiens.gene_info.gz` (NCBI Gene → symbol)
3. For each candidate gene in our 50-gene list, find its highest-ranked disease
   and use that rank
4. Resolve symbols via our pinned `hgnc_complete_set_2026-04-07.txt`

This is identical to how PhEval ([2024 bioRxiv](https://www.biorxiv.org/content/10.1101/2024.06.13.598672v1.full.pdf))
handles LIRICAL output for gene-level evaluation.

### 2.3 Output flags required

LIRICAL defaults emit only top-10 diseases above threshold 0.01. To rank all 50
candidate genes safely:

```bash
lirical prioritize \
  --observed-phenotypes "${HPO_IDS}" \
  -d ${LIRICAL_DATA_DIR} \
  -t 0.0 \
  -m 100000 \
  -f json \
  -o results/${CASE_ID}/
```

Candidates with no matching disease fall to rank 51 (tied last) — same convention
we use for Exomiser.

### 2.4 Data overrides for methodological consistency

LIRICAL's `download` command pulls **current** HPO. We override with our pinned
v2026-02-16 versions:

```bash
# After lirical download -d ~/rare-disease-rag/lirical_data/, override:
cp data/Human_Phenotype_Ontology/hp.json ~/rare-disease-rag/lirical_data/
cp data/Human_Phenotype_Ontology/phenotype.hpoa ~/rare-disease-rag/lirical_data/
```

(`hp.obo` → `hp.json` conversion via `pronto` if needed; LIRICAL accepts `.json`.)

### 2.5 Parallel execution

One LIRICAL invocation = one JVM (~5-10 s warmup + ~5-10 s computation = ~30 s/case).
Serial 1,047 × 30 s = ~8.7 h. With 16-way parallelism: ~35 min. Mirror the worker-pool
pattern from `scripts/eval/run_cell_k.py` for Cell M.

### 2.6 Files to create

| File | Purpose |
|---|---|
| `src/baselines/lirical_runner.py` | LIRICAL invocation + output parsing + disease→gene mapping |
| `scripts/eval/run_cell_m.py` | Cell M launcher, mirrors `run_cell_k.py` |
| (data) `~/rare-disease-rag/lirical_data/` | LIRICAL data dir (HPO + HPOA + Jannovar ~2 GB) |
| `~/rare-disease-rag/lirical-cli-2.4.0/` | LIRICAL distribution |

### 2.7 Expected output

```
data/eval_1050/cell_M_lirical_hpo_only/
  <case_id>.json   # 1047 case JSONs in our standard schema
```

Then run aggregation:
```bash
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python \
    scripts/eval/aggregate_metrics.py \
    --eval-root data/eval_1050 \
    --test-cases data/test_cases_1050/test_cases.jsonl
```

Aggregator already supports adding new cells (`CELLS` dict in
`aggregate_metrics.py`); we add an `"M"` entry pointing at `cell_M_lirical_hpo_only`.

### 2.8 Estimated timeline

| Task | Effort |
|---|---|
| Download LIRICAL + data (one-time) | 30 min (depends on network) |
| Write `lirical_runner.py` + disease→gene mapping | 1-2 days |
| Write `run_cell_m.py` (16-way pool) | 0.5 day |
| Smoke test on 5 cases | 0.5 day |
| Full run n=1,047 (16-way) | ~35 min - 1 h compute |
| Aggregate + add to reports | 0.5 day |
| **Total** | **2-3 days plumbing + ~1 h compute** |

---

## 3. RAGAS + DeepEval evaluation

### 3.1 Why both frameworks

| Framework | Primary metrics | Strength |
|---|---|---|
| **RAGAS** ([repo](https://github.com/explodinggradients/ragas)) | faithfulness, context precision, context recall, answer relevance | Most mature RAG-eval; well-cited |
| **DeepEval** ([repo](https://github.com/confident-ai/deepeval)) | hallucination, bias, toxicity, custom metrics | Broader; better for specific clinical-quality metrics |

We use RAGAS for the 4 RAG-quality metrics and DeepEval for the dedicated
hallucination metric. Both frameworks support custom LLM judges and can use
the same GPT-4o endpoint.

### 3.2 Per-case data needed

To compute these metrics, each Cell L / Cell S case needs:

| Field | Source |
|---|---|
| `question` | Patient phenotype (HPO labels) |
| `retrieved_contexts` | Top-K PMC chunks per gene (currently in `state.retrieved` but not persisted to case JSON) |
| `answer` | LEA's final ranking with reasoning (currently only ranking persisted) |
| `ground_truth` | Causal gene + disease (in test_cases.jsonl) |

**The current Cell L/S outputs do NOT persist `retrieved_contexts` or LEA's
reasoning text.** We need to:

1. Patch `synthesizer_lea.py` to log per-case: LEA prompt, LEA response, retrieved chunks per gene
2. Re-run Cell L and Cell S to capture these sidecars (~14 h compute)

Alternative: run only on a 200-case subset. **Decision: full n=1,047** per user
request, for maximum statistical power.

### 3.3 Response-logging schema

New file per case: `data/eval_1050/cell_S_responses/<case_id>.json`:

```json
{
  "case_id": "...",
  "hpo_terms": ["HP:0001250", ...],
  "candidate_genes": [...50 symbols...],
  "causal_gene": "AIRE",
  "retrieved_per_gene": {
    "AIRE": [
      {"chunk_id": "...", "text": "...", "score": 0.83, "source_pmid": "..."},
      ...
    ],
    ...49 more genes...
  },
  "critic_evidence": {...},  # from critic_node
  "lea_prompt": "Rank these genes by likelihood of being causal...",
  "lea_response_raw": "...",  # full Qwen3-8B text response
  "lea_response_parsed": {...},  # parsed JSON ranking
  "final_ranking": [...],  # same as existing cell_S_*/<case>.json content
  "elapsed_s": 26.5
}
```

For Cell L (no LEA), the sidecar omits `lea_*` fields but keeps `retrieved_per_gene`
and `critic_evidence` (needed for RAGAS context precision/recall on the retrieval
stage).

### 3.4 RAGAS judge prompts

RAGAS computes each metric via an LLM call:

| Metric | Judge prompt (paraphrased) |
|---|---|
| **Faithfulness** | "Given the retrieved contexts, are the claims in the answer supported by the contexts? Output a score 0-1." |
| **Context precision** | "Given the question and the retrieved contexts, what fraction of the top-K contexts are relevant to answering the question? Score 0-1." |
| **Context recall** | "Given the question, the answer, and the ground truth, what fraction of the ground truth's relevant claims are present in the retrieved contexts? Score 0-1." |
| **Answer relevance** | "Given the answer, generate N artificial questions; compute cosine similarity to the original question. Score 0-1." |

Each metric = 1 GPT-4o call per case. RAGAS framework handles the orchestration.

### 3.5 ⚠️ Documented project-rule deviation

`CLAUDE.md` rule: *"No cloud LLM API in any code path. CopilotKit Cloud is NOT used;
the React UI talks to the local FastAPI backend on loopback only."*

**Deviation for v3 evaluation:** GPT-4o (or GPT-4o-mini) via OpenAI API is used
**only as the RAGAS/DeepEval judge**. Justification:

1. **Evaluation-only** — production pipeline (Cells D/L/S) remains 100 % local.
2. **Methodological standard** — RAGAS and DeepEval defaults are GPT-4o judges;
   using a different/local judge would invite the reviewer comment "why are you
   using a non-standard judge?"
3. **Repeatability** — GPT-4o is the most widely-used judge in 2025-2026 RAG
   papers; numbers are comparable to published works.
4. **Cost is bounded** — ~$50-80 total spend; documented in the paper.

The deviation is recorded in the paper Methods:

> "RAGAS faithfulness, context precision, context recall, and answer relevance
> were computed using GPT-4o (`gpt-4o-2024-08-06`) as the LLM judge via the
> OpenAI API. DeepEval hallucination was computed with the same judge. The
> judge is invoked only at evaluation time and does not interact with the
> production pipeline (Cells D, L, S), which uses Qwen3-8B locally via vLLM."

### 3.6 Cost estimate

| Component | Per case | × 1,047 cases × 2 cells | Total estimate |
|---|---|---|---|
| RAGAS faithfulness (1 judge call, ~2k tok in / 200 tok out) | $0.006 | × 2 cells (L, S) | ~$13 |
| RAGAS context precision (1 call) | $0.005 | × 2 | ~$11 |
| RAGAS context recall (1 call) | $0.005 | × 2 | ~$11 |
| RAGAS answer relevance (1 call, generates N questions) | $0.008 | × 2 | ~$17 |
| DeepEval hallucination (1 call) | $0.006 | × 1 cell (S only) | ~$6 |
| **TOTAL** | | | **~$58** |

Buffer 30% for retries / longer prompts: **budget ~$80**.

### 3.7 Estimated timeline

| Task | Effort |
|---|---|
| Patch `synthesizer_lea.py` to log responses | 0.5 day |
| Patch `rerank_inside_d.py` (Cell L stage) for retrieval logging | 0.5 day |
| Re-run Cell L + Cell S with logging | ~14 h compute (overnight) |
| Install `ragas` + `deepeval`; set up GPT-4o judge | 0.5 day |
| Write `scripts/eval/run_ragas.py` + `scripts/eval/run_deepeval.py` | 2 days |
| Smoke test on 5 cases | 0.5 day |
| Full run n=1,047 × 2 cells × 5 metrics | ~3-4 h compute (mostly API latency) |
| Aggregate + write into reports | 1 day |
| **Total** | **4-5 days plumbing + ~14 h compute (re-run) + ~4 h API run** |

---

## 4. Revised Strategy A roadmap

| # | Item | Phase | Status | ETA |
|---|---|---|---|---|
| 1 | n=1047 v0.1.26 4-cell run | done | ✅ committed `paper-v2-final` | — |
| 2 | Aggregation + sensitivity + reports | done | ✅ | — |
| 3 | Cell M (LIRICAL) integration + run | v3 | ✅ done (commits `8e9f9dc`, `5df44fa`) | — |
| **3b** | **LIRICAL annotation-overlap analysis (Thread D — NEW)** | **v3** | **🆕 added after observing LIRICAL top-1 = 0.924** | **~3 days** |
| 4 | Response-logging patches + re-run L+S | v3 | 🟢 running (tmux `paper_ls_v3`) | ~14 h overnight |
| **5** | **RAGAS pipeline + n=1,047 run** | **v3** | **pending OPENAI_API_KEY** | **3-4 days** |
| **6** | **DeepEval hallucination + n=1,047 run** | **v3** | pending | 1-2 days |
| 7 | Wallclock + cost table (K, M, D, L, S) | v3 | pending | 1 day |
| 8 | DeepRare head-to-head on n=100 | post-v3 | pending | 5-7 days |
| 9 | Qwen3-32B AWQ ablation on n=100 | post-v3 | pending | 2-3 days |
| 10 | Pre-submission self-review | post-v3 | pending | 1 day |
| 11 | Manuscript drafting (Genome Medicine) | post-v3 | pending | 2-3 weeks |

**Total Strategy A timeline (revised): ~10-11 weeks to Genome Medicine submission.**

---

## 3b. Thread D — LIRICAL annotation-overlap analysis (NEW, added 2026-05-17)

### 3b.1 Why this thread exists

The v3 LIRICAL run produced an unexpected result: **Cell M top-1 = 0.924**
vs Cell S 0.725 and Cell K 0.691. LIRICAL appears to vastly outperform all
other cells, including geno_agent. Initial analysis suggests this is almost
certainly an **annotation overlap artifact**:

- LIRICAL's core knowledge base is `phenotype.hpoa` (HPO-disease annotations)
- `phenotype.hpoa` is curated from rare-disease publications (PMIDs)
- **Phenopacket Store cases are derived from the same publications**: each
  phenopacket has a `metaData.externalReferences.id` PMID, and that paper's
  HPO terms become the patient's phenotype
- Therefore: LIRICAL is being scored against annotations directly derived
  from the case's source paper → information leakage

Concrete example. Case `AIRE:PMID_16965330_Sibling_of_patient_11`:
- Patient's HPO terms came from PMID 16965330
- `phenotype.hpoa` contains: `OMIM:240300 (APS-1) HP:0002841 PMID:16965330 PCS …`
- LIRICAL uses these annotations to compute likelihood ratios
- → LIRICAL knows the answer because the answer was annotated *from this exact paper*

This is a well-documented issue in the rare-disease genomics literature
(Smedley et al. 2015; EJHG 2026 benchmark also notes the limitation).

### 3b.2 Why we do NOT drop LIRICAL from the paper

| If we drop LIRICAL | If we include LIRICAL + overlap analysis |
|---|---|
| Looks like cherry-picking | Demonstrates methodological rigour |
| Reviewers will ask "why no LIRICAL?" | Reviewer question already answered in §X |
| EJHG 2026 included LIRICAL → omission stands out | Aligns with the standard benchmark practice |
| "Why exclude a tool you actually ran?" academic-integrity risk | Honest reporting of what was measured |

**Decision: include LIRICAL, do the overlap analysis, reframe geno_agent
as "the strongest LITERATURE-ONLY system" (no curated phenotype-gene
tables) — Exomiser and LIRICAL both use curated knowledge bases of
different kinds. This is a fundamentally different category and the
paper's contribution stands.**

### 3b.3 Methodology

For each of the n=1,047 cases, compute a per-case binary flag
`annotation_overlap = {0, 1}`:

1. Parse the case's source PMID from the test-case manifest (or
   re-extract from the phenopacket store metaData).
2. Look up the causal gene's OMIM disease IDs via `mim2gene_medgen`.
3. For each OMIM disease, scan `phenotype.hpoa` for rows where
   `database_id == OMIM:<id>` AND `reference == PMID:<src_pmid>`.
4. If any such row exists → `annotation_overlap = 1`; else 0.

This gives us a 1,047-element vector that splits the cohort into:
- **Overlap-present subset** (expected: ~50-70% of cases)
- **Overlap-absent subset** (the "fair" comparison cohort)

Then stratify all 5 cells' top-1/5/10 + MRR + per-MONDO results into
the two subsets and report side-by-side.

### 3b.4 Expected outcomes (hypotheses to test)

| Hypothesis | Expected on overlap-present | Expected on overlap-absent |
|---|---|---|
| LIRICAL top-1 | very high (≈0.95+) | drops materially (perhaps to 0.65-0.75) |
| Exomiser top-1 | high (Exomiser uses similar but distinct curated tables) | moderate drop |
| Cell S top-1 | moderate (literature retrieval is partly insulated from overlap) | small or no change |

If hypothesis holds: LIRICAL's advantage is shown to be artefactual,
geno_agent's relative position improves, and the paper has a strong
methodological contribution.

If hypothesis fails (LIRICAL stays high on overlap-absent too): we
honestly report it as "LIRICAL is genuinely better on this benchmark
regardless of annotation overlap" — paper still has the overlap
analysis as a contribution, just with a less favourable conclusion.
Either way the analysis is publishable.

### 3b.5 Implementation files

| File | Purpose |
|---|---|
| `scripts/eval/compute_annotation_overlap.py` (NEW) | Builds per-case `annotation_overlap` flag, writes `data/test_cases_1050/annotation_overlap.json` |
| `scripts/eval/aggregate_stratified.py` (NEW) | Re-aggregates all 5 cells stratified by overlap; output `data/eval_1050/_results_stratified.{md,json,csv}` |
| `reports/paper_extension_results.md` update | Add §4.X "Annotation overlap analysis" with stratified tables |
| `reports/paper_extension_results.html` update | Add stratified bar charts |

### 3b.6 Required data sources

- `data/test_cases_1050/test_cases.jsonl` — already exists
- Phenopacket source PMIDs — re-extract from raw v0.1.26 phenopackets in
  `data/phenopackets/v0.1.26/`
- `phenotype.hpoa` v2026-02-16 — already pinned in
  `data/Human_Phenotype_Ontology/` and in LIRICAL data dir
- `mim2gene_medgen` (NCBI) — already in LIRICAL data dir

### 3b.7 Estimated effort

| Task | Effort |
|---|---|
| Source PMID extraction from phenopackets | 0.5 day |
| `compute_annotation_overlap.py` | 1 day |
| `aggregate_stratified.py` (mostly reuses `aggregate_metrics.py`) | 0.5 day |
| Sensitivity probes (LOO on overlap-absent subset) | 0.5 day |
| Update reports (md + html) | 0.5 day |
| **Total** | **~3 days** |

### 3b.8 Acceptance criteria for Thread D

- [ ] `annotation_overlap.json` produced with per-case binary flag
- [ ] `_results_stratified.{md,json}` produced with all 5 cells × 2 subsets
- [ ] Overlap-absent S vs K, S vs M, K vs M deltas reported with paired-bootstrap CIs
- [ ] Per-MONDO breakdown on overlap-absent subset reported
- [ ] Paper extension results document includes:
  - Raw LIRICAL number (0.924) reported honestly
  - Overlap analysis section explaining the confound
  - Deconfounded numbers with CIs
  - Reframing of geno_agent as "strongest literature-only system"
- [ ] Methods section text explaining the overlap analysis
- [ ] Sequence: runs *after* L+S v3 re-run completes (independent of RAGAS/DeepEval)

### 3b.9 Risks and mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| Overlap analysis doesn't materially reduce LIRICAL's advantage | medium | Report honestly as "LIRICAL is genuinely better on this benchmark"; paper still benefits from the rigour of the analysis |
| Phenopacket source PMID extraction has edge cases (multi-PMID per case, missing PMIDs) | medium | Document each case; if a case has no PMID, mark overlap as N/A and exclude from stratified analysis |
| `phenotype.hpoa` updated between annotation date and our analysis | low | Pinned to v2026-02-16 (same as project's HPO) |
| Overlap-absent subset is too small for meaningful per-MONDO analysis | medium | Report subset n explicitly; if any category has <50 cases, mark as underpowered and combine where appropriate |

---

## 5. Tonight's execution sequence

Independent threads that can run in parallel:

### Thread A: LIRICAL plumbing
1. Download LIRICAL v2.4.0 distribution + data
2. Build `src/baselines/lirical_runner.py` with disease→gene mapping
3. Write `scripts/eval/run_cell_m.py` (16-way parallel pool)
4. Smoke test on 5 cases
5. Launch on n=1,047 in tmux (~1 h compute)

### Thread B: Response logging (for RAGAS later)
1. Patch `src/agents/synthesizer_lea.py` to record prompt + raw response
2. Patch `scripts/eval/rerank_inside_d.py` to persist `retrieved_per_gene` per case
3. Add new sidecar output directory: `data/eval_1050/cell_S_responses/`
4. Smoke test on 3 cases
5. Launch full re-run on n=1,047 in tmux (overnight, ~14 h)

### Thread C (pending OPENAI_API_KEY)
6. Install `ragas` + `deepeval`
7. Write evaluation scripts
8. Run on response sidecars

The compute lanes can stack: Thread A finishes in ~1 h, then GPU is free for
Thread B's re-run of Cell L → Cell S overnight.

---

## 6. Acceptance criteria (v3)

The v3 phase is successful when:

- [x] `data/eval_1050/cell_M_lirical_hpo_only/` contains 1,047 case JSONs (LIRICAL) ✅
- [x] LIRICAL is added to `aggregate_metrics.py` CELLS dict ✅
- [x] `_results_summary.{md,json,csv}` is regenerated with K, D, L, S, M ✅
- [ ] LIRICAL results are documented in `paper_extension_results.md` + .html (including the +annotation-overlap-caveat framing)
- [ ] **NEW: `annotation_overlap.json` produced for all 1,047 cases**
- [ ] **NEW: `_results_stratified.{md,json}` reports cells × overlap-subsets**
- [ ] **NEW: paper extension results includes Annotation Overlap Analysis section with deconfounded numbers**
- [ ] **NEW: framing reframed to "strongest literature-only system" (Exomiser + LIRICAL = curated; geno_agent = literature-only)**
- [ ] `data/eval_1050/cell_S_responses/` contains 1,047 sidecar JSONs with full LEA prompt/response/contexts
- [ ] `data/eval_1050/cell_L_responses/` similarly for Cell L
- [ ] `scripts/eval/run_ragas.py` produces per-case + aggregate RAGAS metrics
- [ ] `scripts/eval/run_deepeval.py` produces per-case + aggregate hallucination metrics
- [ ] RAGAS + DeepEval results are documented in updated reports
- [ ] Project-rule deviation is documented in `CLAUDE.md` and paper Methods
- [ ] All artefacts committed to `paper/n500-validation` branch with a `paper-v3-final` tag

---

## 7. Risks and mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| LIRICAL data download is slow / breaks | low | Distribution is one file; project's HPO/HPOA already pinned and can override |
| LIRICAL disease→gene mapping has edge cases (multi-gene OMIM, ambiguous symbols) | medium | Use HGNC canonical symbols; document mapping rules; cross-check via Exomiser overlap on causal genes (sanity check) |
| Response-logging adds compute overhead to Cell L/S re-run | low | Logging is just JSON serialization; negligible vs LEA's LLM call latency |
| GPT-4o API rate limits | medium | Use `ragas` built-in throttling; batch requests; fall back to GPT-4o-mini if needed |
| GPT-4o judge is non-deterministic across runs | medium | Document `temperature=0`, fix `seed=42` in API calls; report aggregate over multiple judge calls per metric |
| OPENAI_API_KEY not yet available | high | Threads A and B don't depend on it; we can start tonight and add Thread C as soon as the key is provided |
| Cost overrun | low | $80 budget is conservative; throttle if approaching limit |
| LIRICAL annotation overlap not reducible | medium | Honest reporting; paper still benefits from showing the analysis (Thread D §3b.9) |
| Reviewers reject the "literature-only" reframing | low | The category distinction is well-established (curated vs unsupervised); EJHG 2026 paper uses similar framing |

---

## 8. Git landmarks (in progress)

| Commit | Description |
|---|---|
| `6366b8f` | v2 final results (n=1,047, S beats K) |
| `ee44a25` | v2 plan |
| `fcbd426` | v2 cohort + Stage 16/17 patches |
| `7d99104` | v3 plan (this document, v1) |
| `8e9f9dc` | LIRICAL runner + Cell M launcher + response-logging patches |
| `a42ad9d` | RAGAS + DeepEval scripts (GPT-4o judge) |
| `5df44fa` | Cell M aggregation; LIRICAL top-1 = 0.924 finding |
| TBD | **v3 plan v2 — add Thread D (overlap analysis) (this update)** |
| TBD | L+S v3 re-run (sidecars + possibly updated S top-1) |
| TBD | Thread D: annotation-overlap analysis + stratified aggregation |
| TBD | RAGAS + DeepEval n=1,047 runs |
| TBD | v3 final results + reports + `paper-v3-final` tag |

---

*Plan v3 finalised 2026-05-17. Threads A, B, C as originally planned;
Thread D (LIRICAL overlap analysis) added 2026-05-17 after observing
LIRICAL top-1 = 0.924 in the Cell M run. Thread D begins after L+S
v3 re-run completes (~14 h compute) and runs in parallel with the
RAGAS/DeepEval evaluation phase.*
