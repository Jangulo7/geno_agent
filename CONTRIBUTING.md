# Contributing & Project Conventions

Engineering conventions and hard project rules for `geno_agent`. These are the
authoritative project rules referenced throughout the code and docs.

## Project hard rules

- **Corpus vs ontologies.** Only PMC Open Access full-text articles are embedded
  and indexed in Qdrant. The ontologies (HPO, MONDO, GO, HGNC) are NEVER embedded
  or indexed — they are read at runtime via `pronto` (OBO files) and `pandas`
  (HGNC TSV).
- **Determinism.** `PYTHONHASHSEED=42`, UUID5 content-derived chunk IDs, pinned
  ontology versions, explicit `torch` / `numpy` / `random` seeds, and
  `RANDOM_SEED=42` for cohort sampling.
- **Sparse retrieval.** BM25 is `fastembed.SparseTextEmbedding("Qdrant/bm25")`
  only — no hash-based fallback under any circumstances.
- **Local inference.** The production / inference LLM is local (Qwen3-8B via
  vLLM). No cloud LLM API in the production or inference code path. The sole
  exception is the offline RAGAS / DeepEval rationale-quality evaluation, which
  calls an external OpenAI-compatible endpoint for *measurement only*, never for
  gene prioritisation.
- **Storage layout.** Heavy persistent artifacts (Qdrant storage, model weights,
  logs, raw corpus) live OUTSIDE the git repo, under `~/rare-disease-rag/`. Qdrant
  storage stays on the Linux filesystem; bulk PMC processing uses `/mnt/c/`.
- **Phase ordering.** Phase 1A (corpus → index) must complete before Phase 1B
  (cohort). The formal evaluation requires both.

## Qdrant deployment

- Dedicated container `qdrant_geno_agent`, image `qdrant/qdrant:v1.14.1` (aligned
  with `qdrant-client`), REST `localhost:6533`, gRPC `localhost:6534`, storage
  bind-mounted to `~/rare-disease-rag/qdrant_storage/`.
- Connection settings live in `.env` (`QDRANT_HOST`, `QDRANT_PORT`,
  `QDRANT_GRPC_PORT`); no hardcoded ports in `src/`.

## Pinned ontology versions (2026 releases)

- HPO `v2026-02-16`, MONDO `v2026-03-03`, GO `2026-03-25`, HGNC `2026-04-07`.
- HGNC archive files are served from a Google Cloud Storage bucket; the path
  contains a doubled `archive/archive/` segment (the actual bucket layout, not a
  typo).
- `data/MANIFEST.tsv` is regenerated with the SHA-256 of every file whenever any
  pinned version changes.

## Code style

**Python (`scripts/`, `src/`)**
- PEP 8, with type hints on every public function and method.
- Google-style docstrings on every module, class, and public function.
- No bare `except:` — catch specific exceptions and log with context.
- Prefer `pathlib.Path` over `os.path`; prefer f-strings.
- Keep functions under ~50 lines; split when they grow past that.
- Enforced by `ruff` and `mypy` (see `pyproject.toml` and `.pre-commit-config.yaml`).

**TypeScript / React (`frontend/`, Phase 2c)**
- Follow the project's CopilotKit + Next.js conventions. Do not mix Node.js and
  Python dependencies across the two sides.

## Git workflow

- `main` is protected; work on feature branches (e.g. `phase1a/step-3-acquisition`).
- Conventional Commits (`feat(phase1a): add JATS XML parser`). One logical change
  per commit; open a PR per numbered step.
- Never commit: `.env`, `qdrant_storage/`, `models/`, raw corpus, `*.parquet`,
  large `*.jsonl`, frontend build artifacts, or model weights. Reference secrets
  via `os.environ[...]` and document them in `.env.example`.

## Environment

- Python 3.12 via `uv` (preferred) or `venv`. Pin every dependency in
  `pyproject.toml` with exact versions for reproducibility.
