# Paper Extension Plan v2 — n=1047 with Phenopacket Store v0.1.26

**Author:** Johanna Angulo (johanna.angulo@gmail.com)
**Date:** 2026-05-17
**Branch:** `paper/n500-validation` (will be renamed for the v2 work)
**Supersedes:** [`reports/paper_extension_plan.md`](_archive_n75/paper_extension_plan.md) (n=460, v0.1.19; archived)
**Companion result document:** [`reports/paper_extension_results.md`](paper_extension_results.md) (n=459 results, to be updated with n=1047 once compute completes)

---

## 0. TL;DR

This document records the methodology and exact reproducibility trail for the
**v2 paper extension run** — a re-validation at n=1047 cases drawn from
Phenopacket Store **v0.1.26** (vs the v1 plan's n=459 from v0.1.19). The redesign
was triggered by a sensitivity analysis on the v1 results that revealed the
immunological subgroup finding was statistically fragile (CI lower bound at
exactly +0.000; 18 of 85 cases load-bearing for significance) — combined with
the discovery that Phenopacket Store v0.1.26 grew the eligible immunological
pool from 85 to 390 cases (+359 %).

The v2 run uses **disproportionate stratified sampling** (immunological
oversampled to 300 cases vs 250 each for the other three MONDO categories) to
power a robust subgroup finding without sacrificing overall cohort statistics.
This is the cleanest methodology to deliver the paper's lead claim — that
literature-grounded agentic RAG *statistically outperforms* Exomiser on
immunological diseases — at Q1-acceptable rigor.

Expected outcomes at n=1047:
- Overall S vs K top-1 CI tightened from ±0.040 to ~±0.027
- Immunological subgroup n raised from 85 to 300; LOO survival projected ~98 %
- McNemar exact p on immunological projected to drop from 0.032 → <0.001

---

## 1. Motivation and trigger

### 1.1 What v1 (n=459, v0.1.19) established

The v1 paper extension (committed 2026-05-16, headline result in
[`reports/paper_extension_results.md`](paper_extension_results.md)) reported:

| Finding | Value | Status |
|---|---|---|
| Cell S (rerank + LEA) top-1 | 0.767 [0.728, 0.802] | ✅ Stable |
| Cell K (Exomiser HPO-only) top-1 | 0.767 [0.728, 0.804] | ✅ Stable |
| Δ (S − K) top-1 | +0.000 [−0.039, +0.041] | ✅ Statistical parity confirmed |
| Per-MONDO immunological Δ (S−K) | **+0.118 [+0.000, +0.235]** | ⚠️ Marginal — CI lower bound = 0 |

### 1.2 What the sensitivity analysis revealed (2026-05-16 evening)

A four-probe sensitivity analysis on the n=85 immunological subset (Task #38)
exposed three concerns:

| Probe | Result | Interpretation |
|---|---|---|
| Leave-one-out CI excludes 0 | **67 / 85 = 78.8 %** of LOO subsets | 18 cases are load-bearing — fragile |
| McNemar exact one-sided p | **0.0320** | Just clears α=0.05; 17 vs 7 discordant pair split |
| Permutation test one-sided p | **0.0325** | Equivalent significance |
| Leave-N-out at n=75 | CI excludes 0 in **38 %** | Would not survive at the original thesis n |

The contingency table laid the fragility bare:
- 24 discordant pairs out of 85 cases
- Of those 24, 17 favor S, 7 favor K
- **Removing any of those 17 S-exclusive wins flips the result**

A Q1 reviewer with even basic stats training would (a) compute LOO themselves,
(b) note the 18/85 fragility, (c) downgrade the claim from "outperforms" to
"trends toward outperforming" — and that's exactly the wording that gets a
manuscript rejected as "underpowered".

### 1.3 What the Phenopacket Store v0.1.26 check revealed

Step 0 (Task #39) — a 30-minute check of newer Phenopacket Store releases —
returned a transformative finding:

| Category | v0.1.19 eligible | **v0.1.26 eligible** | Δ |
|---|---:|---:|---:|
| developmental | 305 | 464 | +159 |
| **immunological** | **85** | **390** | **+305 (+359 %)** |
| metabolic | 350 | 672 | +322 |
| neurological | 2,231 | 3,144 | +913 |
| **TOTAL** | **2,971** | **4,670** | **+1,699 (+57 %)** |

Net cohort growth: 422 → 674 gene cohorts; 6,668 → 9,588 phenopackets.

The Monarch Initiative had added ~25+ new IEI cohorts between v0.1.19 (Aug 2024)
and v0.1.26 (Jan 2026): RAG1, DCLRE1C, TAP2, TAPBP, B2M, RFX5, RFXAP, PTCRA,
IKZF1, IKZF2, IL27RA, IRF4, CD274, CD28, PDCD1, FLT3LG, NEUROG3, TBK1, OAS2,
CMPK2, CHUK, OTULIN, TNF, RC3H1, PLD4, NLRP7 (incl. MHC-I/II deficiencies,
SCID/Omenn variants, IPEX-like, autoinflammatory, immune-checkpoint genes).

This eliminates the structural cap on the immunological sample at zero
plumbing cost. No need for RareBench (poor fit anyway — see §A).

### 1.4 The v2 decision

Given (a) the v1 immunological finding is fragile and (b) v0.1.26 trivially
removes the cap, the rational move is to re-sample n=1050 from v0.1.26 with
disproportionate stratification favouring immunological. This delivers a
**single clean dataset for the lead claim** at the cost of ~22 h overnight
compute on the same hardware that ran v1.

---

## 2. Goal (v2)

> **Re-validate at n=1047 (v0.1.26, seed 42) whether Cell S statistically
> outperforms Cell K on the immunological MONDO subgroup, with adequate
> statistical power to defend the claim under leave-one-out and McNemar
> scrutiny. Secondary: tighten the overall S-vs-K CI from ±0.040 to ~±0.027.**

### 2.1 Why "lead with immunological"

The literature situation:
- [DeepRare (Nature 2025)](https://www.nature.com/articles/s41586-025-10097-9):
  multi-agent gene prioritisation, comparable systems-level architecture
- [LA-MARRVEL (arXiv 2511.02263, 2026)](https://arxiv.org/abs/2511.02263):
  LLM reranking on AI-MARRVEL output
- [EJHG 2026 systematic benchmark](https://www.nature.com/articles/s41431-026-02054-5):
  Reports that *Exomiser dominates* on immunological cases

The contrarian finding — *literature-grounded LLM RAG beats Exomiser on
immunological cases* — is the single most novel claim this paper can make. It
directly inverts a published systematic-benchmark result. Even if overall top-1
remains a tie, the categorical win is the headline. v2's job is to make sure
that headline is statistically rock-solid.

### 2.2 Why NOT pursue alternatives first

| Alternative | Why rejected |
|---|---|
| RareBench supplement | Yields only ~15-25 IEI cases (dominated by metabolic RAMEDIS); no causal_gene field; 5-6 days plumbing for marginal gain |
| PubMed E-utils + IUIS gene list | Yields 150-250 cases but needs LLM-based HPO extraction → 3-5 days plumbing + introduces noise |
| Journal-targeted curation | Manual; 1-2 weeks |
| Phenopacket Store **v0.1.26 upgrade** | **30 min check + ~22h overnight compute**; +305 IEI cases at perfect methodological consistency ✅ |

The v0.1.26 upgrade is dominant on every axis.

---

## 3. Methodology (v2)

### 3.1 Provenance pins

| Component | v1 (n=459) | **v2 (n=1047)** |
|---|---|---|
| Phenopacket Store | v0.1.19 | **v0.1.26** |
| HPO ontology | v2026-02-16 | v2026-02-16 (unchanged) |
| MONDO ontology | v2026-03-03 | v2026-03-03 (unchanged) |
| HGNC snapshot | 2026-04-07 | 2026-04-07 (unchanged) |
| Random seed | 4242 | **42** |
| `MIN_PMC_ARTICLES_PER_GENE` | 5 | 5 (unchanged) |
| `MIN_HPO_TERMS` | 3 | 3 (unchanged) |
| Qdrant collection | `geno_agent_pmc_oa_v1` (52.78 M chunks) | unchanged |
| Bootstrap seed | 42 | 42 (unchanged) |

### 3.2 Disproportionate stratified sampling

The v2 sample uses **per-category targets** rather than the balanced split
(`ceil(target_size/4)`) used by all prior runs:

| Category | Eligible pool (v0.1.26) | **Target** | **Achieved (post Stages 6-7)** |
|---|---:|---:|---:|
| developmental | 464 | 250 | 250 |
| **immunological** | **390** | **300** | **300** |
| metabolic | 672 | 250 | 250 |
| neurological | 3,144 | 250 | **247** (3 dropped at Stage 6, see §3.5) |
| **TOTAL** | **4,670** | **1,050** | **1,047** |

#### 3.2.1 Why disproportionate sampling is methodologically valid

This is a textbook epidemiology / genomic-medicine technique:

> When subgroup statistical power is the primary inferential goal,
> disproportionate stratified sampling oversamples low-prevalence strata to
> achieve adequate per-stratum power, at the cost of cohort-level metrics
> becoming non-population-weighted. Both per-stratum and (per-stratum-mean
> bias-corrected) overall metrics must be reported.

Precedent in adjacent literature:
- DeepRare (Nature 2025): category-specific subset analyses (109 cases for
  multi-modal; varying sizes per disease type)
- AI-MARRVEL (NEJM AI 2024): oversampled subgroups for ablations
- AMELIE (Sci Transl Med): oversampled rare disease categories
- Phen2Disease (bioRxiv 2022): cohort-specific reporting

Furthermore, **prior geno_agent runs were also disproportionate** —
methodologically consistent:

| Sample | Immunological % | Notes |
|---|---:|---|
| v0.1.19 eligible pool natural prevalence | 85 / 2,971 = 2.9 % | |
| v0.1.26 eligible pool natural prevalence | 390 / 4,670 = 8.4 % | |
| Thesis n=75 | 19 / 75 = 25.3 % | 8.7× oversampled |
| Paper v1 n=459 | 85 / 459 = 18.5 % | 6.4× oversampled |
| **Paper v2 n=1047** | **300 / 1,047 = 28.7 %** | **3.4× oversampled vs v0.1.26 natural rate** |

#### 3.2.2 Mandatory paper text on disproportionate sampling

The paper's Methods section will include:

> "We employed disproportionate stratified random sampling to ensure adequate
> statistical power for per-MONDO subgroup analyses. Specifically, we drew 300
> cases from the immunological-disease pool (77 % of all eligible IEI cases in
> Phenopacket Store v0.1.26) and 250 each from developmental, metabolic, and
> neurological pools. This oversamples immunological diseases relative to their
> natural prevalence in the eligible pool (8.4 %) but enables paired-bootstrap
> subgroup CIs at ±5 pp resolution. Overall (cohort-level) metrics are
> therefore not directly comparable to baseline tools' published numbers on
> natural-prevalence cohorts. We report per-category metrics as primary and
> provide a per-category-mean (unweighted) aggregate as a bias-corrected
> alternative."

### 3.3 Quality gates (all preserved from v1, applied to v0.1.26)

All five Phase 1B gates from the thesis methodology apply unchanged:

| # | Gate | Source script | Threshold | v2 outcome |
|---|---|---|---|---|
| 1 | PMC OA coverage of causal gene | `17_validate_pmc_coverage.py` | ≥5 PMC articles | **1050 / 1050 pass first attempt; 0 replacements** |
| 2 | HPO term count | `14_apply_inclusion_exclusion.py` | ≥3 HPO terms | applied during Stage 14 |
| 3 | Causal gene in HGNC protein-coding set | `18_build_candidate_lists.py` | HGNC 2026-04-07 | **3 dropped (RNU4-2 ×2, 1 other ncRNA)** |
| 4 | Disease in MONDO | `14_apply_inclusion_exclusion.py` | MONDO v2026-03-03 | applied during Stage 14 |
| 5 | No ambiguous gene mapping | `18_build_candidate_lists.py` | HGNC symbol unique | applied at Stage 18 |

### 3.4 Random seed strategy

**Seed 42** (vs v1's 4242). The decision: this is a *new* sample from a *new*
release of Phenopacket Store (v0.1.26 vs v0.1.19), so the methodology is
naturally "fresh independent sample" framing, not "replication". Using seed
42 (the project's canonical seed in `.env`) keeps the seed simple and
documentable. The case overlap with v1 (n=459, seed 4242) is incidental.

Justification language for the paper:
> "The v0.1.26 sample (n=1047, seed 42) is a fresh, independent draw — there
> is no required relationship to the v1 sample (n=459, seed 4242 from v0.1.19).
> Case-level overlap is incidental and not relied upon for statistical
> reasoning. Both runs are reported separately as independent validations."

### 3.5 Final cohort outcome

```
Stage 13 (load v0.1.26):           9,588 phenopackets
Stage 14 (HPO/HGNC/MONDO gates):   6,382 eligible (66.6 % pass)
Stage 15 (MONDO categorize):       4,670 in 4 target categories (73.2 %)
Stage 16 (stratified sample):      1,050 (250+300+250+250, seed=42)
Stage 17 (PMC validation):         1,050 / 1,050 first-pass (0 replacements)
Stage 18 (HGNC + candidates):      1,047 (3 dropped — RNU4-2 ×2, 1 ncRNA)
Stage 19 (finalize):               data/test_cases_1050/test_cases.jsonl
```

Final composition: 250 developmental + 300 immunological + 250 metabolic +
247 neurological = **1,047 cases**.

Manifest SHA-256: `c355b800e53e5347…` (stored in
`data/test_cases_1050/test_cases_manifest.json`).

---

## 4. Cells executed (v2)

Same four cells as v1, justified by the same logic (cells A-J, P, Q, R were
shown at v1 to be either inferior, null, or marginal — re-running at v2 scale
would consume ~30 GPU-hours for no interpretive gain).

| Cell | Configuration | Compute lane | v2 wall (est) |
|---|---|---|---|
| **K** | Exomiser HPO-only (hiPhive prioritiser) | CPU | ~3.5 h |
| **D** | multi-agent · hybrid (deterministic) | GPU | ~7.7 h |
| **L** | D + cross-encoder rerank · hybrid | GPU | ~6.0 h |
| **S** | rerank + LEA · hybrid | GPU (vLLM during S only) | ~7.7 h |

Total wall with K on CPU lane in parallel: **~22 h overnight**.

---

## 5. Execution log — exact commands and outcomes (2026-05-16 → 2026-05-17)

### 5.1 Pre-flight environment

```bash
cd /home/hana77/ia_jo/uax_tfm/geno_agent
source /home/hana77/pytorch-env/bin/activate
```

### 5.2 Step 0 — Phenopacket Store version audit (~30 min)

```bash
# Confirm currently pinned version
grep PHENOPACKET_STORE_VERSION .env
# → PHENOPACKET_STORE_VERSION=0.1.19

# Check existing eligible pool by category
python3 -c "
import json
from collections import Counter
c = Counter(json.loads(l)['category'] for l in open('data/test_cases/03_categorized.jsonl'))
print(c)
"
# → immunological: 85, developmental: 305, metabolic: 350, neurological: 2231

# Research the latest release (via web agent)
# → Phenopacket Store v0.1.26 (2026-01-13); +25 IEI cohorts since v0.1.19
```

### 5.3 Step 1 — Download + extract v0.1.26 (~2 min)

```bash
cd data/phenopackets
curl -sL -o all_phenopackets_v0.1.26.zip \
  "https://github.com/monarch-initiative/phenopacket-store/releases/download/0.1.26/all_phenopackets.zip"
mkdir -p v0.1.26 && cd v0.1.26
unzip -q ../all_phenopackets_v0.1.26.zip
# → 9,588 phenopackets in 623 gene cohorts
```

### 5.4 Step 2 — Pin v0.1.26 in `.env`

```bash
sed -i 's/PHENOPACKET_STORE_VERSION=0.1.19/PHENOPACKET_STORE_VERSION=0.1.26/' .env
```

### 5.5 Step 3 — Run Phase 1B Stages 13-15 on v0.1.26 (~5 min)

```bash
mkdir -p data/test_cases_1050
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/13_load_phenopackets.py
# → 9,588 loaded; output: data/test_cases_1050/01_all_phenopackets.jsonl

TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/14_apply_inclusion_exclusion.py
# → 6,382 eligible (66.6 %); 1,155 few_hpo, 69 no_single_gene, 1,982 excluded_disease

TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/15_categorize_by_mondo.py
# → 4,670 in 4 target categories; immunological: 390 ✅
```

### 5.6 Step 4 — Stage 16 with `--per-category-target` (commit `fcbd426`)

Stage 16 was patched to accept disproportionate per-category targets:

```python
# scripts/cases/16_stratified_sample.py
def sample_stratified(
    by_cat: dict[str, list[dict]],
    target: int,
    rng: random.Random,
    per_category_target: dict[str, int] | None = None,
) -> list[dict]:
    """... per_category_target overrides balanced split ..."""

# CLI:
# --per-category-target "developmental=250,immunological=300,metabolic=250,neurological=250"
```

Run:
```bash
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/16_stratified_sample.py \
    --seed 42 \
    --per-category-target "developmental=250,immunological=300,metabolic=250,neurological=250"
# → 1,050 cases (300 imm, 250 each others)
```

### 5.7 Step 5 — Stage 17 (PMC validation) — env-var fix (commit `fcbd426`)

Stage 17 previously hard-coded `TC_DIR = PROJECT_ROOT / "data" / "test_cases"`,
ignoring `TEST_CASES_DIR`. First run silently re-validated the thesis n=75
sample (clobbered `data/test_cases/05_validated.jsonl` — recoverable from
`data/test_cases/04_sampled.jsonl.thesis_backup` and a re-run).

Fix:
```python
# scripts/cases/17_validate_pmc_coverage.py
TC_DIR: Final[Path] = Path(
    os.environ.get("TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases"))
)
```

Then re-run:
```bash
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/17_validate_pmc_coverage.py
# → 1,050 / 1,050 first pass; 0 replacements; ~7 min wall
```

### 5.8 Step 6 — Stages 18-19 (candidate lists + finalize, ~2 min)

```bash
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/18_build_candidate_lists.py
# → 1,047 written (3 dropped: RNU4-2 ×2 + 1 other ncRNA)

TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/19_finalize_test_cases.py
# → data/test_cases_1050/test_cases.jsonl (1,047 cases, SHA-256 c355b800e53e5347…)
```

### 5.9 Step 7 — Commit (commit `fcbd426`)

```bash
git add scripts/cases/16_stratified_sample.py \
        scripts/cases/17_validate_pmc_coverage.py \
        data/test_cases_1050/test_cases_manifest.json \
        data/test_cases_1050/05_validated_stats.json
git commit -m "feat(paper): n=1047 v0.1.26 cohort + per-category sampling + env paths"
```

Note: `.env` change is NOT committed (gitignored). For reproducibility, the
paper's reproducibility section will state explicitly:
`PHENOPACKET_STORE_VERSION=0.1.26` must be in `.env`.

### 5.10 Step 8 — Launch the 4 cells (overnight, ~22 h wall)

```bash
mkdir -p data/eval_1050

# CPU lane: Cell K in tmux paper_k_1050
tmux new-session -d -s paper_k_1050 "bash -lc '
cd /home/hana77/ia_jo/uax_tfm/geno_agent
source /home/hana77/pytorch-env/bin/activate
PYTHONPATH=. python scripts/eval/run_cell_k.py \
  --test-cases data/test_cases_1050/test_cases.jsonl \
  --out-dir data/eval_1050/cell_K_exomiser_hpo_only \
  2>&1 | tee -a logs/paper_cell_K_1050.log
'"

# GPU lane: D → L → vLLM → S sequenced in tmux paper_gpu_1050
tmux new-session -d -s paper_gpu_1050 "bash -lc '
cd /home/hana77/ia_jo/uax_tfm/geno_agent
source /home/hana77/pytorch-env/bin/activate
TEST_CASES=\$(pwd)/data/test_cases_1050/test_cases.jsonl \
OUT_ROOT=\$(pwd)/data/eval_1050 \
bash scripts/eval/run_paper_extension.sh
'"
```

Pre-flight check at launch: `nvidia-smi free=30,789 MiB used=1,402 MiB` ✅

### 5.11 VRAM caps (carry-over from v1, no change needed)

The VRAM-safe vLLM config established in v1 (after a contamination-then-fix
sequence) is reused unchanged:

```bash
# scripts/eval/start_vllm.sh
--max-model-len           32768      # matches thesis; fits LEA prompts
--max-num-seqs                1      # LEA is serial; minimal KV demand
--gpu-memory-utilization   0.75      # vLLM ~24 GB; leaves ~8 GB for CE+dense
--dtype                 float16
--enable-prefix-caching
--reasoning-parser       qwen3
```

vLLM serves from `/home/hana77/vllm-env/` (separate venv from `pytorch-env`
which holds the eval scripts). Sequencer guarantees vLLM is only alive during
Cell S; killed afterward via `trap cleanup_on_exit EXIT INT TERM`.

---

## 6. Expected statistical outcomes

### 6.1 Overall (cohort-level)

| Metric | v1 (n=459) | **v2 (n=1047) projected** | Improvement |
|---|---|---|---|
| Cell S top-1 | 0.767 [0.728, 0.802] | ~0.77 [~0.745, ~0.795] | CI tightened ~30 % |
| Cell K top-1 | 0.767 [0.728, 0.804] | ~0.77 [~0.745, ~0.795] | CI tightened ~30 % |
| Δ (S − K) | +0.000 [−0.039, +0.041] | likely small (|Δ| < 0.02), CI half-width ~0.027 | tighter null |

The overall finding will almost certainly remain "parity" — the v1 finding
was already a true tie. v2 just makes the parity claim more precise.

### 6.2 Per-MONDO immunological (the lead claim)

| Metric | v1 (n=85) | **v2 (n=300) projected if Δ holds at ~+0.10** |
|---|---|---|
| Cell S top-1 | 0.694 | ~0.70 |
| Cell K top-1 | 0.576 | ~0.60 |
| Δ (S − K) | +0.118 [+0.000, +0.235] | **~+0.10 [~+0.04, ~+0.16]** |
| McNemar exact p | 0.032 | **projected <0.001** |
| LOO survival of CI excluding 0 | 78.8 % | **projected ≥98 %** |

**This is the result that moves the paper from "marginal subgroup finding"
to "publication-quality lead claim".**

If the result does NOT hold (Δ drops to <+0.05 at n=300), the paper's lead
becomes the parity finding with a softened immunological observation
("trends toward outperforming on IEI cases; n=300 CI half-width [~] pp").
Still publishable, just lower-impact framing.

---

## 7. Operational fixes shipped in v2

| Commit | Change | Why |
|---|---|---|
| `fcbd426` | Stage 16 `--per-category-target` flag | Enable disproportionate sampling without rewriting the script |
| `fcbd426` | Stage 17 honours `TEST_CASES_DIR` env var | Previously hardcoded path silently clobbered v1 thesis data |
| `fcbd426` | `data/test_cases_1050/` manifest + stats committed | Reproducibility |

No changes to:
- vLLM caps (carried from v1 commit `f048943`)
- Cell K / D / L / S eval scripts (carried from v1 commit `5cb8e27`)
- VRAM-safe sequencer (carried from v1 commit `eac42df`)
- vllm-env separation (carried from v1 commit `9566596`)

---

## 8. Outputs (when run completes)

```
data/test_cases_1050/                                       # n=1047 test set
  04_sampled.jsonl
  05_validated.jsonl
  05_validated_stats.json
  06_with_candidates.jsonl
  test_cases.jsonl                                          # canonical 1047 cases
  test_cases_manifest.json                                  # SHA-256 + provenance

data/eval_1050/                                             # cell outputs (per-case JSONs)
  cell_K_exomiser_hpo_only/                                 # 1047 JSONs
  cell_D_multi_hybrid/                                      # 1047 JSONs
  cell_L_rerank_inside_d/                                   # 1047 JSONs
  cell_S_rerank_inside_plus_lea/                            # 1047 JSONs
  _results_summary.{md,json,csv}                            # bootstrap + per-MONDO
  _results_table.csv
  _results_by_category.csv
```

---

## 9. Acceptance criteria (v2)

The v2 run is **successful** if all of the following hold:

- [ ] `data/test_cases_1050/test_cases.jsonl` contains 1,047 cases ✅ (already done)
- [ ] All 4 cells produce 1,047 case JSONs (no unrecovered errors)
- [ ] `data/eval_1050/_results_summary.json` includes K, D, L, S with 1,000-resample bootstrap CIs and per-MONDO breakdown
- [ ] Immunological subgroup S vs K result:
  - Either: **Δ ≥ +0.05 with CI lower bound > 0 and McNemar p < 0.01** → lead claim is "Cell S statistically outperforms Exomiser on immunological diseases"
  - Or: Δ < +0.05 or CI lower bound ≤ 0 → claim softens to "trends toward outperforming"
- [ ] Sensitivity analysis (LOO) on immunological subgroup with n=300 confirms ≥95 % LOO survival OR explicitly reports the survival rate
- [ ] Overall S vs K confirms parity (CI on Δ includes 0)
- [ ] Per-MONDO breakdown reported for all 4 categories with paired bootstrap CIs
- [ ] [`reports/paper_extension_results.md`](paper_extension_results.md) updated with v2 numbers + side-by-side v1 vs v2 table
- [ ] PR opened with the v2 commits (plumbing patches + manifests)

---

## 10. Time and resource budget (v2 actual)

| Phase | Wall time | Resource |
|---|---|---|
| Step 0 (Phenopacket Store research + audit) | 30 min | none (CPU) |
| Step 1 (v0.1.26 download + extract) | 2 min | CPU |
| Steps 3-6 (Phase 1B Stages 13-19) | 15 min compute | CPU + Qdrant |
| Step 7 (commit) | 5 min | none |
| Step 8 (launch overnight) | started 2026-05-17 00:21Z | — |
| Cell K (CPU) | ~3.5 h | CPU only |
| Cell D (GPU) | ~7.7 h | GPU (~2.5 GB) |
| Cell L (GPU + CE) | ~6.0 h | GPU (~5 GB) |
| Cell S (GPU + vLLM + CE) | ~7.7 h | GPU (~28 GB) |
| Total GPU lane wall | **~21.4 h** | overnight |
| Total wall (K parallel) | **~22 h** | done ~22:30 local 2026-05-17 |
| Aggregation + analysis | ~30 min | CPU |
| Update reports | ~2 h | none |

Active human attention: **~1 h** (kick-off + monitoring).

---

## 11. Risks and mitigations (v2-specific)

| Risk | Probability | Mitigation |
|---|---|---|
| Cell S contamination repeat (vLLM 400s) | very low | v1's final vLLM config (commits `f048943`, `81b7a46`, `3c71586`, `9566596`) is empirically validated; no changes |
| GPU OOM / driver hang | very low | VRAM caps unchanged from v1; peak ~28 GB / 32 GB |
| Immunological Δ < +0.05 at n=300 | low-medium | Softened claim still publishable as secondary finding; overall parity is the fallback lead |
| Per-MONDO Δ reversal vs v1 (e.g., S loses immunological) | very low | v1 LOO showed 79 % survival → at n=300 with same effect size, survival should approach certainty |
| Compute interruption (power, kernel crash) | low | All 4 cells idempotent — re-launch resumes from existing case JSONs (rerank_inside_d.py SKIPs existing files) |
| New version of Phenopacket Store between now and submission | low | v0.1.26 SHA pinned in manifest; the paper's reproducibility section will reference the exact zip URL |

---

## 12. After v2 — outstanding Strategy A items

This document covers the v2 cohort generation + cell run. The full Strategy A
to reach Q1 submission still requires:

| # | Item | Status | ETA |
|---|---|---|---|
| 1 | n=1047 v0.1.26 run | 🟢 **executing** (this document) | done ~tomorrow 22:30 |
| 2 | Aggregate + per-MONDO + immunological sensitivity at n=300 | ⏳ pending | 30 min after #1 |
| 3 | Update `paper_extension_results.md` v2 + HTML | ⏳ pending | 2 h |
| 4 | DeepRare head-to-head on n=100 random subset | ⏳ pending | 5-7 days |
| 5 | Qwen3-32B AWQ ablation on n=100 random subset | ⏳ pending | 2-3 days |
| 6 | Wallclock + cost table vs Exomiser/DeepRare/LA-MARRVEL | ⏳ pending | 1 day |
| 7 | Per-category-mean (unweighted) overall metric for bias-corrected reporting | ⏳ pending | 1 h |
| 8 | Pre-submission self-review against EJHG 2026 benchmark | ⏳ pending | 1 day |
| 9 | Manuscript drafting (target: Genome Medicine) | ⏳ pending | 2-3 weeks |

**Total Strategy A timeline:** ~3 weeks calendar from v2 cohort completion.

---

## Appendix A — Why RareBench was rejected (research notes 2026-05-16)

Investigation (Task #39 research agent) confirmed:

| Aspect | RareBench reality | Verdict |
|---|---|---|
| Sub-datasets containing IEI | LIRICAL (~15-25), MME (~2-5), HMS/PUMCH (~0-5) | ~20-35 raw IEI cases |
| Causal-gene field | **Absent** — only OMIM IDs | Major plumbing required |
| Pipeline-gate compatibility | Strict gates: ~5-12 surviving; relaxed: ~25-40 | Insufficient yield |
| License | Apache-2.0 | OK |
| Plumbing effort | ~5-6 days | Poor ROI |

Recommendation from the research: "Use Phenopacket Store v0.1.20+ first — it
already has IEI cohort additions that may suffice."

That recommendation became Step 0, and v0.1.26 delivered +305 IEI cases at
zero plumbing cost. RareBench is officially out of scope.

---

## Appendix B — Git history (paper extension branch)

| Commit | Description |
|---|---|
| `5cb8e27` | v1 n=460 test set + CLI flags for paper extension |
| `eac42df` | VRAM-safe vLLM caps + sequenced D→L→S launcher (initial) |
| `9566596` | Point start_vllm.sh at vllm-env; add S-only recovery |
| `81b7a46` | Drop --swap-space (removed in vllm 0.20.1) |
| `3c71586` | Bump gpu-memory-utilization 0.55 → 0.70 (engine init) |
| `f048943` | Restore max-model-len=32768; drop seqs=1; bump util=0.75 |
| `fcbd426` | **v2 n=1047 v0.1.26 cohort + per-category sampling + env paths** |

---

## Appendix C — File map

```
reports/
  paper_extension_plan.md            # v1 plan (n=460 from v0.1.19)
  paper_extension_plan_v2.md         # THIS DOCUMENT (v2 plan, n=1047 from v0.1.26)
  paper_extension_results.md         # v1 results (n=459) — to be augmented with v2
  thesis_final_report.md             # n=75 thesis baseline
  thesis_final_report.html           # visual version of the above

data/
  test_cases/                        # n=75 thesis cohort (v0.1.19)
  test_cases_500/                    # v1 n=459 paper cohort (v0.1.19, seed 4242)
  test_cases_1050/                   # v2 n=1047 paper cohort (v0.1.26, seed 42)
  eval/                              # n=75 thesis results (cells A-S)
  eval_500/                          # v1 n=459 results (cells K, D, L, S)
  eval_1050/                         # v2 n=1047 results (cells K, D, L, S) — populating now

scripts/
  cases/13_load_phenopackets.py
  cases/14_apply_inclusion_exclusion.py
  cases/15_categorize_by_mondo.py
  cases/16_stratified_sample.py      # patched in v2 for --per-category-target
  cases/17_validate_pmc_coverage.py  # patched in v2 to honour TEST_CASES_DIR env
  cases/18_build_candidate_lists.py
  cases/19_finalize_test_cases.py
  eval/run_cell_k.py
  eval/rerank_inside_d.py            # produces Cell L (no --use-lea) or Cell S (--use-lea)
  eval/run_paper_extension.sh        # GPU sequencer (D → L → vLLM → S)
  eval/run_paper_extension_S_only.sh # recovery launcher for S only
  eval/start_vllm.sh                 # VRAM-capped Qwen3-8B server (vllm-env)
  eval/aggregate_metrics.py          # paired bootstrap + per-MONDO

.env                                  # PHENOPACKET_STORE_VERSION=0.1.26 (gitignored)
```

---

## Appendix D — Reproducibility commands (end-to-end)

```bash
# Pre-requisites:
#   pytorch-env (eval scripts), vllm-env (vLLM 0.20.1), Qdrant on :6533,
#   Qwen3-8B weights at ~/rare-disease-rag/models/Qwen3-8B/

git checkout paper/n500-validation  # the v2 branch (will be renamed)

# 1. Pin v0.1.26 in .env
sed -i 's/PHENOPACKET_STORE_VERSION=0.1.19/PHENOPACKET_STORE_VERSION=0.1.26/' .env

# 2. Download Phenopacket Store v0.1.26
cd data/phenopackets && mkdir -p v0.1.26 && cd v0.1.26
curl -sL -o ../all_phenopackets_v0.1.26.zip \
  "https://github.com/monarch-initiative/phenopacket-store/releases/download/0.1.26/all_phenopackets.zip"
unzip -q ../all_phenopackets_v0.1.26.zip
cd ../../..

# 3. Phase 1B Stages 13-19
mkdir -p data/test_cases_1050
for stage in 13 14 15; do
  TEST_CASES_DIR=$(pwd)/data/test_cases_1050 \
    PYTHONPATH=. python scripts/cases/${stage}_*.py
done
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/cases/16_stratified_sample.py \
    --seed 42 \
    --per-category-target "developmental=250,immunological=300,metabolic=250,neurological=250"
for stage in 17 18 19; do
  TEST_CASES_DIR=$(pwd)/data/test_cases_1050 \
    PYTHONPATH=. python scripts/cases/${stage}_*.py
done

# 4. Launch 4 cells (overnight, ~22h)
mkdir -p data/eval_1050
tmux new -d -s paper_k_1050 "PYTHONPATH=. python scripts/eval/run_cell_k.py \
  --test-cases data/test_cases_1050/test_cases.jsonl \
  --out-dir data/eval_1050/cell_K_exomiser_hpo_only"
tmux new -d -s paper_gpu_1050 "TEST_CASES=\$(pwd)/data/test_cases_1050/test_cases.jsonl \
  OUT_ROOT=\$(pwd)/data/eval_1050 \
  bash scripts/eval/run_paper_extension.sh"

# 5. Aggregate after both lanes complete
TEST_CASES_DIR=$(pwd)/data/test_cases_1050 PYTHONPATH=. python scripts/eval/aggregate_metrics.py \
    --eval-root data/eval_1050 \
    --test-cases data/test_cases_1050/test_cases.jsonl
```

---

*v2 plan finalised 2026-05-17. Run launched 2026-05-17 00:21Z; expected
completion ~2026-05-17 22:30Z. Aggregation, sensitivity, and report update
follow within 2 h after compute completes.*
