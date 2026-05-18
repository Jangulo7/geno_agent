# geno_agent — Agentic Multi-Agent RAG for Gene Prioritization

Authoritative spec: `./MASTER_PROJECT_v2.2.md` (read in full before any task).
Private GitHub repo: github.com/Jangulo7/geno_agent

## Architecture clarifications (master plan §0)

Only PMC OA full-text articles are loaded into Qdrant. The ontologies
(HPO, MONDO, GO, HGNC) are NEVER embedded or indexed — they live as
files in `./data/` and are read at runtime via `pronto` (OBO files) and
`pandas` (HGNC TSV). Do not write code that uploads ontology terms to
Qdrant under any pretext.

## Hard rules

- Phase 1A must complete end-to-end before Phase 1B starts (master plan §0).
- Phase 2 (agentic UI layer, master plan §11) requires Phase 1A + 1B complete
  for the formal evaluation. Phase 2c UI development against the demo Qdrant
  collection is OK in parallel, but the §11.5 factorial cannot run until 1B.
- Qdrant storage stays on the Linux fs at `~/rare-disease-rag/qdrant_storage/`.
  Bulk PMC processing goes on `/mnt/c/pmc_workspace/`. Never invert this.
- Determinism: `PYTHONHASHSEED=42`, UUID5 chunk IDs, pinned ontology versions.
- BM25 = `fastembed.SparseTextEmbedding("Qdrant/bm25")` only. No hash-based
  fallback under any circumstances.
- Heavy persistent artifacts (qdrant_storage, models, logs) live OUTSIDE
  the git repo, under `~/rare-disease-rag/`.
- Phase 2 LLM is local: Qwen3-8B (or open-weights ~8B fallback) via vLLM.
  No cloud LLM API in any code path. CopilotKit Cloud is NOT used; the
  React UI talks to the local FastAPI backend on loopback only.

## Code style

### Python (scripts/, src/agents/, src/api/)
- PEP 8, with type hints on every public function and method.
- Google-style docstrings on every module, class, and public function.
- No bare `except:` — catch specific exceptions, log with context.
- Prefer `pathlib.Path` over `os.path`. Prefer f-strings over `.format()`/`%`.
- Keep functions under ~50 lines; split when they grow past that.

### TypeScript / React (frontend/)
- Phase 2c only. The frontend is a separate npm project; npm and Node.js
  commands are allowed there. Do NOT add Node.js dependencies to the Python
  side or vice versa.
- Use the project's prevailing CopilotKit + Next.js conventions.
- geno_agent-specific React components live under `frontend/src/geno_agent/`
  and consume `@copilotkit/react-core` from npm. CopilotKit framework code
  is NOT vendored — it is a normal npm dependency.
- Source for the React framework is the user's fork:
  https://github.com/Jangulo7/agent_UI (upstream `CopilotKit/CopilotKit`).
  Kept around as a reference; not pinned as a git submodule.

## Git workflow (private repo: github.com/Jangulo7/geno_agent)

- `main` is protected — no direct commits. Work on feature branches:
  `phase1a/step-3-acquisition`, `phase1b/step-2-filtering`, etc.
- Commit after each completed numbered step in §3 of the master plan.
  Conventional Commits format: `feat(phase1a): add JATS XML parser`.
- One logical change per commit. No "wip" or "fix stuff" messages.
- Open a PR per step; do not merge until the step's acceptance criteria
  in the master plan are met and recorded in `data/MANIFEST.tsv`.
- Never commit: `.env`, `qdrant_storage/`, `models/`, `data/pmc_oa/`,
  anything under `/mnt/c/pmc_workspace/`, `*.parquet`, `*.jsonl` over 10 MB,
  `frontend/node_modules/`, `frontend/.next/`, `frontend/.turbo/`,
  Qwen3-8B model weights (`~/rare-disease-rag/models/Qwen3-8B/`).
- Never commit secrets. Reference via `os.environ[...]` and document them
  in `.env.example` (which IS committed).

## Environment

- Project root in WSL: `/home/hana77/ia_jo/uax_tfm/geno_agent`
- WSL2 Ubuntu 24.04, Windows host, NVIDIA RTX 5090 32GB VRAM, 64GB RAM.
- Python via `uv` (preferred) or `venv`. Pin every dependency in
  `pyproject.toml` with exact versions for reproducibility (§4.1.3).

## Qdrant deployment

- Two unrelated Qdrant containers already exist on this host and must
  remain untouched: `qdrant_pubmed_full` (ports 6333/6334) and
  `qdrant_local` (port 6335).
- This project runs its own dedicated Qdrant container on alternate
  ports to avoid collision:
  - REST: localhost:6533
  - gRPC: localhost:6534
  - Container name: `qdrant_geno_agent`
  - Image: `qdrant/qdrant:v1.14.1` (pinned to align with `qdrant-client==1.14.3` in pytorch-env — v1.14.1 is the highest server tag in the v1.14.x line, no v1.14.3 server release exists; bumped from v1.12.4 in §7 step [4] before any data was written)
  - Storage: bind-mounted to `~/rare-disease-rag/qdrant_storage/`
- Connection settings live in `.env` as `QDRANT_HOST`, `QDRANT_PORT`,
  `QDRANT_GRPC_PORT`. All Python code reads from these env vars — no
  hardcoded ports anywhere in `src/`.
- Master plan §3.5 examples show port 6333. Treat those as illustrative;
  the actual port is 6533 per this project's `.env`.

## Ontology versions (2026 releases — deliberate update from plan)

The master plan v2.2 originally pinned 2024 versions. We have updated
the pins to 2026 releases (the current files in `./data/`). This
deviation is recorded in master plan §10. The pinned versions are:

- HPO:   `v2026-02-16`
- MONDO: `v2026-03-03`
- GO:    `2026-03-25`
- HGNC:  `2026-04-07` quarterly snapshot

`data/MANIFEST.tsv` must be regenerated whenever any of these change,
with SHA-256 of every file recorded.

### HGNC URL change (additional deviation)

HGNC migrated their archive files from EBI FTP to a Google Cloud
Storage bucket. The master plan's download URL has been updated to:
`https://storage.googleapis.com/public-download-files/hgnc/archive/archive/quarterly/tsv/hgnc_complete_set_${HGNC_SNAPSHOT}.txt`
(note the doubled `archive/archive/` — that is the actual bucket layout,
not a typo). Recorded in master plan §10.

## Task workflow

- Work phase by phase, step by step. Stop and confirm after each
  numbered step in §3 of the master plan.
- Before any download or write: state what will change, where, and why.
  Wait for explicit approval if the change is non-trivial.
- Record every downloaded artifact in `data/MANIFEST.tsv` with date
  and SHA-256 (master plan fix #8).
