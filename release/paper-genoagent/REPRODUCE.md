# REPRODUCE — P2 (GenoAgent)

Reproduce the n=1,047 evaluation and the headline result. Requires the **P1 shared
foundation** (Qdrant index + n=1,047 cohort) — see P1's `REPRODUCE.md` / DOI first.

> Authoritative methodology + exact flags:
> [`reports/methodology.md`](../../reports/methodology.md),
> [`reports/agent_architecture.md`](../../reports/agent_architecture.md), and
> [`MASTER_PROJECT_v2.2.md`](../../MASTER_PROJECT_v2.2.md) §11.

## 0. Preconditions

- P1 foundation present: Qdrant collection `geno_agent_pmc_oa_v1` (52,777,395 pts,
  verified against `data/MANIFEST.tsv`) and `data/test_cases_1050/test_cases.jsonl`.
- Study env `~/pytorch-env` (Python 3.12.3, `torch==2.12.0.dev20260407+cu128`);
  `pyproject.toml` is the authoritative pin set. `.env` configured.
- Local LLM: Qwen3-8B via vLLM 0.20.1. Baselines: Exomiser 14.0.2, LIRICAL 2.4.0.

## 1. Run the cells (D → L → S, plus baselines K/M)

```bash
source ~/pytorch-env/bin/activate
docker compose up -d              # Qdrant
bash scripts/eval/start_vllm.sh   # Qwen3-8B server

bash scripts/eval/run_paper_extension.sh   # D (multi+hybrid) -> L (+CE rerank) -> S (+LEA)
python scripts/eval/run_cell_k.py          # Exomiser HPO-only  (curated baseline)
python scripts/eval/run_cell_m.py          # LIRICAL  HPO-only  (curated baseline)
python scripts/eval/aggregate_metrics.py   # top-1/5/10, MRR, NDCG@10 + bootstrap 95% CIs
```

## 2. Deconfounding & robustness

```bash
python scripts/eval/compute_annotation_overlap.py   # fair-cohort flag (overlap-absent)
python scripts/eval/run_lopo.py                     # leave-one-paper-out retrieval
python scripts/eval/aggregate_lopo.py
python scripts/eval/multiplicity_correction.py      # Holm / Benjamini-Hochberg
python scripts/eval/weighted_overall.py             # stratum-weighted sensitivity
```

## 3. Optional RAG-quality judges (measurement only — external endpoint)

```bash
# These call an external OpenAI-compatible endpoint (GPT-4o in the paper) to MEASURE
# rationale quality. They never touch gene prioritisation. Set the key in .env:
#   OPENAI_API_KEY=...      (run_ragas.py / run_deepeval.py)
python scripts/eval/run_ragas.py
python scripts/eval/run_deepeval.py
```

## Headline result to reproduce

> Fair-comparison cohort (overlap-absent, n=282): geno_agent **Cell S** is the
> top-ranked system, **top-1 = 0.858**, beating Exomiser HPO-only (+0.078, p=0.015)
> and LIRICAL HPO-only (+0.082, p=0.014); both survive Holm correction. LOPO leaves
> the fair-cohort top-1 unchanged (0.858 → 0.858, McNemar p=1.0).

Committed result artifacts: `data/eval_1050/_results_summary.{json,md}`,
`_results_stratified.*`, `_results_recency.*`, and
`data/eval_1050_lopo_full/_lopo_*` (see `artifacts_manifest.tsv`).

## 4. Demo (no GPU / index needed)

```bash
streamlit run demos/streamlit_thesis_demo.py   # browse pre-computed rankings
```
