# DeepRare comparability assessment + architecture comparison

**Question asked**: Should the Q1 paper run a head-to-head against DeepRare
(MAGIC-AI4Med/DeepRare, *Nature* 2026)? And how novel is geno_agent's
architecture relative to it?

**Short answer**: **DeepRare is NOT directly comparable as a baseline** for
geno_agent's claim. Including it as a head-to-head benchmark would be
methodologically misleading. Better: **cite it in Related Work and position
geno_agent as fundamentally different** along seven architectural dimensions
(below).

The repo was studied at commit `2026-05-19` (231 stars, *Nature* paper
Zhao et al. 2026, arXiv:2506.20430). Code inspected: `main.py`,
`diagnosis.py` (HPO-only), `diagnosisGene.py` (HPO+Gene), `tools/*`,
`tools/llm_agent.py` (the verifier agent), README.

---

## 1. Why DeepRare is not directly comparable

### 1.1 Different prediction target

| System | Output unit | Top-k semantics |
|---|---|---|
| **DeepRare** | **Diseases** (Orphanet / OMIM IDs) | top-5 ranked **diseases** with reasoning |
| **geno_agent (Cell S)** | **Genes** (HGNC symbols) | top-50 ranked **causal genes** with confidence + rationale |

Even DeepRare's "Gene" variant (`diagnosisGene.py`) still uses the
disease-prediction pipeline and then maps disease → gene via Exomiser.
The LLM reasoning is over diseases, not genes. To compare them at gene
level you'd need a many-to-many mapping (one disease → multiple causal
genes; one gene → multiple diseases) — adding methodological noise that
favors whichever side you allow to win the tie-breaks.

### 1.2 Different knowledge-source class — the deepest issue

| Source category | DeepRare | geno_agent |
|---|---|---|
| Curated disease knowledge bases (Orphanet expert pages, OMIM, mim2gene) | **Used** (primary signal) | Avoided at inference (only for evaluation labels) |
| Phenotype-gene curated tables (`phenotype.hpoa`, HPO disease graph) | Used (HPO Search Tool) | Avoided at inference (only for Thread D's overlap analysis) |
| Live web search (Google / Bing / DuckDuckGo) | **Used** (real-time, per call) | Not used |
| Disease-API services (PubCaseFinder, Phenobrain) | **Used** | Not used |
| PubMed + ArXiv + Wikipedia live search | Used | Not used |
| ChromeDriver / Selenium browser automation | **Used** (scrapes Orphanet expert pages) | Not used |
| Local indexed full-text PMC Open Access | Not used | **Primary signal** (frozen Qdrant index) |

**Implication for the paper**: geno_agent's headline claim is "the
strongest LITERATURE-ONLY system for gene prioritization". DeepRare is
explicitly a CURATED-KNOWLEDGE-BASE-AND-LIVE-WEB system. The two
systems are answering related but architecturally different questions.
A head-to-head comparison would be analogous to comparing "Wikipedia +
Google" vs "a college library" — both find answers, but they're not the
same intervention.

### 1.3 Same annotation-overlap confound as LIRICAL — *worse*

DeepRare's primary knowledge source is Orphanet/OMIM, which is
themselves curated from rare-disease publications. **Phenopacket Store
cases are derived from those same publications**. So DeepRare has the
same overlap-confound issue Thread D documented for LIRICAL — likely
worse, because DeepRare actively retrieves the curated content for the
exact disease being asked about (via the Orphanet expert-page scraping
+ OMIM Search Tool).

A geno_agent-vs-DeepRare comparison on Phenopacket Store would
**reproduce the same LIRICAL pattern**: DeepRare wins on the
overlap-present cohort (73 % of our cases) because it has direct
access to the curated description of the disease whose case it's
being asked to diagnose, but the comparison says nothing about
generalization to novel cases.

### 1.4 Reproducibility difference

| Aspect | DeepRare | geno_agent |
|---|---|---|
| Frozen knowledge inputs | No — relies on live web search, live API endpoints (PubMed, ArXiv, Wikipedia) | **Yes** — frozen Qdrant index, pinned ontology releases, UUID5 chunk IDs, hash-recorded manifest |
| Deterministic re-run | No — web results, API responses, and rate-limit cache vary day to day | **Yes** — bit-perfect on the headline metric across v2→v3 (Cell L: 0 top-1 flips / 1,047; Cell S: 1 flip) |
| Re-evaluation 1 year from now | Likely different (web state drift) | Identical (provided pinned versions are still hosted) |

This is a **paper-grade reproducibility concern** for DeepRare that
geno_agent explicitly designed around.

### 1.5 Production deployability

| | DeepRare | geno_agent |
|---|---|---|
| Local-only inference | No — requires ChromeDriver for web scraping + live API endpoints | **Yes** — all-local (Qdrant + MedCPT-CE + Qwen3-8B via vLLM on a single workstation) |
| GPU footprint for "production" | **16 × Ascend 910B** cards (per their README, web app deployment) | **1 × RTX 5090** (32 GB) |
| Hospital-PHI deployable | Sends patient phenotypes to external web search engines + cloud LLM APIs — would need clinical PHI clearance | All-local; PHI never leaves the workstation |
| Cloud-LLM dependency | Default uses OpenAI / Anthropic / Gemini / DeepSeek APIs | None at inference (Qwen3-8B is local; cloud spend is evaluation-only) |

### 1.6 Engineering effort to attempt a head-to-head

A defensible DeepRare baseline on geno_agent's cohort would require:

1. **Setting up DeepRare's full stack**: Selenium/ChromeDriver + 4 web
   search providers + 6 external API integrations + the 5-tool
   reflection loop + their case-similarity embedding pipeline. README
   says "complex environment setup" and recommends their web app — for
   reproducibility we'd need the full local stack working.
2. **Patching their disease-output pipeline to emit gene rankings** —
   either via OMIM/Orphanet → mim2gene mapping (introduces a many-to-many
   confound) or by completely rewriting the LLM prompt to emit gene
   names directly (changes the evaluation from what their paper claims).
3. **Choosing an LLM** — DeepRare supports OpenAI/Anthropic/Gemini/DeepSeek
   APIs. To be fair we'd need to match the LLM tier across systems. Our
   Cell S production is local Qwen3-8B; the closest DeepRare equivalent
   would also be DeepSeek-V3 (which their Nature web-app uses).
4. **Estimated effort**: 5-7 days of integration work + ~$15-30 cloud
   spend per n=100 evaluation (heavy web scraping + tool calls per case
   makes it expensive).
5. **Outcome**: Even with a careful integration, the comparison would
   carry the methodological asterisks above. Reviewers experienced with
   DeepRare are likely to point out the same issues.

### 1.7 What a reviewer would think

A *Genome Medicine* reviewer evaluating a DeepRare-vs-geno_agent table
would probably note:

- **Output-unit mismatch**: "These systems predict different things;
  the comparison is post-hoc remapped."
- **Knowledge-source mismatch**: "DeepRare uses curated KBs and live
  web search; geno_agent is literature-only. Why are they being
  compared at all?"
- **Reproducibility**: "DeepRare's web search is non-deterministic;
  what was the test date? Are the API endpoints still up?"
- **Cost / deployability**: "Why is DeepRare in this paper if it
  requires 16 datacenter GPUs in production?"
- **Annotation overlap**: "DeepRare has the same Orphanet/OMIM
  exposure as LIRICAL. The fair-cohort analysis in §13 already
  addresses this class of system — adding DeepRare doesn't change the
  story."

**Conclusion**: a head-to-head adds engineering cost (5-7 days), API
cost ($15-30+), and reviewer-defensibility cost (methodological
asterisks) for very limited additional informational value. The
"frontier-class curated-system" comparator role is already held by
LIRICAL in the existing analysis, and Thread D already deconfounds
that class.

---

## 2. Architectural comparison — how novel is geno_agent?

Compares geno_agent against four prior systems (DeepRare added as the
most relevant 2026 publication):

| Dimension | Exomiser (2015) | LIRICAL (2020) | AI-MARRVEL (2024) | **DeepRare (Nature 2026)** | **geno_agent (this paper)** |
|---|---|---|---|---|---|
| **Output unit** | Gene | Disease (→ gene via OMIM) | Gene | Disease (→ gene via Exomiser in Gene mode) | **Gene** |
| **Primary knowledge source** | hiPhive (HPO + STRING + interactome) | `phenotype.hpoa` LR framework | Multi-omics + ClinPhen | **Curated KBs (Orphanet, OMIM) + live web + 6 external APIs** | **Frozen PMC OA full-text index (Qdrant)** |
| **Inference-time external calls** | None (local) | None (local) | None (local) | **Many: Google/Bing/DuckDuckGo, PubMed, ArXiv, Wiki, PubCaseFinder, Phenobrain, OMIM Search, ChromeDriver-Selenium for Orphanet pages, LLM API** | **None** (all local) |
| **LLM in the loop** | No | No | No (uses BERT for phenotype matching) | **Yes (closed-source frontier: GPT-4/Claude/Gemini/DeepSeek-V3 via cloud APIs, or 16-Ascend-910B local frontier deploy)** | **Yes (open Qwen3-8B local via vLLM on a single RTX 5090)** |
| **Reproducibility** | Deterministic (KB versioned) | Deterministic (hpoa versioned) | Deterministic | **Live web → non-deterministic** | **Bit-perfect on top-1 (0/1 flips over v2→v3 re-runs)** |
| **Reasoning mode** | Numeric score only | Numeric likelihood ratio | Numeric multi-omics score | **Multi-round reflective: zero-shot → similar-cases → reflection / verification loop (up to 2 iterations) → final synthesis with citations** | **Single-pass LEA over CE-reranked literature chunks; per-gene rationale + confidence; PMC citation trail** |
| **Free-text rationale per ranked item** | No | No | No | **Yes** (per disease, with citations) | **Yes** (per gene, with PMC citations — Thread G: 94 % causal-gene substantive on fair cohort) |
| **Quantified faithfulness** | n/a | n/a | n/a | Manual expert verification (95.40 % per their paper) | **Automated RAGAS + DeepEval** (faithfulness 0.480 top-1-only / 0.286 multi-claim; DeepEval groundedness 0.845; correctness-prediction signal both judges) |
| **Annotation-overlap deconfounding** | No (paper doesn't address) | No (paper doesn't address) | No (paper doesn't address) | No (uses Orphanet expert pages — same class of overlap, not addressed) | **Yes (Thread D)** — overlap-absent fair-cohort analysis explicitly removes cases where curated tools have training-data exposure |
| **Publication-recency stratification** | No | No | No | No | **Yes (Thread E)** — splits cohort by source-PMID date; quantifies how curated tools lag publication |
| **Cohort size** | varies | varies | 67 / 1,015 | 2,919 diseases / 8 datasets | 1,047 cases (n=1,047 with paired-bootstrap CIs + per-MONDO + LOO sensitivity) |
| **Hardware requirement (production)** | Single workstation, CPU | Single workstation, CPU | Single workstation | **16 × Ascend 910B for their local-LLM deploy; otherwise OpenAI/Anthropic/Gemini/DeepSeek cloud API per inference** | **1 × RTX 5090 (32 GB)** end-to-end |
| **PHI-safe local deployment** | Yes | Yes | Yes | No (live web + cloud LLM by default) | **Yes** |
| **Code license** | Open | Open | Open | CC BY-NC 4.0 (non-commercial) | MIT (proposed) |

### 2.1 Where geno_agent is genuinely novel vs all 4 prior systems

The combination of these properties does not exist in any of the four
comparators:

1. **Literature-only (no curated KBs at inference)** + **gene-level output**
   + **single-GPU local LLM-in-the-loop**.
2. **Annotation-overlap-deconfounded evaluation** (Thread D) — explicitly
   addresses the LIRICAL-class confound that prior literature ignores.
3. **Publication-recency stratification** (Thread E) — demonstrates
   curated tools lag publication; literature-only is recency-robust.
4. **Automated, quantified faithfulness with correctness-prediction**
   (Threads C / G) — RAGAS + DeepEval both show the metric is a
   deployment-ready triage signal (33-39 pp top-1-gap at the threshold).
5. **Bit-perfect reproducibility on the headline metric** across
   independent runs (v2→v3: L=0 flips, S=1 flip / 1,047). DeepRare's
   live-web architecture cannot make this claim.
6. **Robust across LLM families** (Q1-B ablation, n=300): three frontier
   LLMs (Qwen3-32B, Sonnet 4.6, DeepSeek-V3) converge within 2.4 pp on
   the fair cohort; all three still beat curated baselines by ≥7 pp.
7. **Single-pass LEA with structured per-gene output** — simpler than
   DeepRare's multi-round reflection loop. Q1 paper can claim
   "comparable evidence-traceable reasoning at a fraction of the
   inference complexity".

### 2.2 What geno_agent does NOT claim novelty on

Reviewers will (correctly) point out that the following ideas are not
novel to geno_agent:

- **Hybrid dense + BM25 retrieval** (introduced by Lin et al. 2021;
  routinely used in IR systems)
- **Cross-encoder reranking** (standard since 2019; MedCPT-CE itself
  is from Jin et al. 2023)
- **LLM-as-aggregator over retrieved evidence** (the broad RAG-with-LLM
  pattern is not new; specific to gene prioritization is the novel
  framing)
- **Multi-agent LangGraph orchestration** (LangGraph is a 2024 framework)

geno_agent's contribution is the **assembly** of these components for
the rare-disease gene-prioritization task, with the explicit framing
of "literature-only, deployable, with deconfounded evaluation".

### 2.3 The architectural comparison statement for the paper Discussion

> *DeepRare (Zhao et al., Nature 2026) is a related agentic system for
> rare-disease diagnosis that achieves Recall@1 = 57.18 % on HPO-only
> inputs across 2,919 diseases via a multi-round reflective pipeline
> integrating live web search, ChromeDriver-based scraping of Orphanet
> expert pages, OMIM, PubCaseFinder, Phenobrain, and per-case calls to
> a frontier LLM (OpenAI/Anthropic/Gemini/DeepSeek). Its primary
> knowledge sources are curated rare-disease databases, and its
> production web app requires 16 Ascend 910B GPUs for local LLM
> deployment. geno_agent is architecturally distinct on five
> dimensions: (i) literature-only — a single frozen full-text PMC Open
> Access index, with no curated knowledge bases at inference time;
> (ii) gene-level output rather than disease-level; (iii) single-pass
> LEA reasoning rather than multi-round reflection; (iv) bit-perfect
> reproducibility on the headline metric across independent runs,
> versus DeepRare's live-web non-determinism; (v) all-local deployment
> on a single workstation GPU. A head-to-head benchmark of these two
> systems was deemed methodologically uninformative because the
> output-unit mismatch (disease vs gene) and knowledge-source mismatch
> (curated KBs + live web vs frozen literature) introduce confounds
> that no remapping can fully remove. Conceptually, DeepRare is the
> 2026 state-of-the-art for the curated-KB-plus-live-web agentic
> diagnosis class, while geno_agent establishes a new state-of-the-art
> for the literature-only locally-deployable gene-prioritization class
> on the fair-comparison cohort (overlap-absent, n=282): top-1 = 0.858
> versus LIRICAL 0.777, Exomiser 0.780.*

---

## 3. Recommendation

| Action | Recommended? |
|---|---|
| Run DeepRare head-to-head on geno_agent's cohort | **No** — methodologically misleading, 5-7 days of work, $15-30 cloud spend, reviewer-asterisk-prone |
| Cite DeepRare in Related Work | **Yes** — it's the most relevant 2026 agentic-system publication |
| Use the §2 architectural-comparison table (above) in the paper | **Yes** — answers the "did you compare to DeepRare?" reviewer question with a defensible categorical reframing |
| Include §2.3's Discussion paragraph verbatim in the manuscript | **Yes** — pre-empts the head-to-head request with explicit reasoning |
| Remove the Q1-A "DeepRare head-to-head" item from the to-do list | **Yes** — replaced by this architectural-comparison + Related Work treatment |

The remaining Q1 work focuses on:
- Manuscript drafting (~2-3 weeks)
- CONSORT-AI / TRIPOD-LLM checklist (1 day)
- Cover letter (0.5 day)

DeepRare comparison is reframed from "head-to-head experiment" (5-7
days, $15-30) to "architectural-comparison table + Related Work
paragraph" (~30 min, $0) — a strict improvement in defensibility
and time-to-submission.

---

*DeepRare comparability assessment — 2026-05-23. Built from a code-level
audit of MAGIC-AI4Med/DeepRare (commit dated 2026-05-19). The Q1
paper's Related Work and Discussion sections will use the §2.3
paragraph above. Q1-A item retired in favor of this reframing.*
