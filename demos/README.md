# geno_agent — demo apps

Lightweight demo applications that load **pre-computed** per-case JSONs
from the project's evaluation directories. No live LLM / Qdrant calls —
safe to run on a laptop without GPU or network during a presentation.

## Streamlit thesis-defense demo

**File**: `streamlit_thesis_demo.py`

Self-contained Streamlit app that lets a defense audience pick a case
from the thesis n=75 cohort (or the paper-extension n=1,047 cohort) and
see Cell S vs Cell K side-by-side rankings, the causal gene's position
across cells, and (for paper-cohort cases) the full LEA rationale with
PMC citation trail.

### Run locally

```bash
cd /path/to/geno_agent
source ~/pytorch-env/bin/activate
streamlit run demos/streamlit_thesis_demo.py
```

The app opens at http://localhost:8501. Use the left sidebar to:

1. **Pick a cohort**: thesis n=75 (the original defense data) or paper
   n=1,047 (paper-extension cohort with richer v3 LEA logs).
2. **Filter by MONDO category** (developmental / immunological /
   metabolic / neurological).
3. **Pick a case**: each case is a phenotyped patient with a known
   causal gene per Phenopacket Store's SOLVED interpretation status.
4. **Pick which cells to compare side-by-side**: Cell S (geno_agent
   full stack), Cell K (Exomiser HPO-only baseline), Cell L (CE-rerank
   only), Cell D (multi-agent hybrid), Cell M (LIRICAL, paper cohort
   only), Cell N (RRF ensemble, paper cohort only).

### What the demo shows

- **Case header**: case_id, causal gene, MONDO category, source PMID,
  diagnosed OMIM/MONDO disease.
- **Patient HPO phenotypes**: HPO IDs with human-readable labels
  (loaded from `data/Human_Phenotype_Ontology/hp.obo`).
- **Side-by-side ranking cards**: top-10 ranked genes per selected
  cell, with confidence scores, and an indicator showing where the
  causal gene placed (top-1 = green, top-5 = blue, top-10 = yellow,
  outside = red).
- **Cross-cell rank chart**: bar chart of the causal gene's rank in
  each cell (lower = better; missing or >50 shown as 51).
- **LEA rationale** (paper cohort only — thesis sidecars don't have
  this): free-text rationale per top-ranked gene, with the supporting
  retrieved chunks (PMC citations linked to ncbi.nlm.nih.gov), token
  counts, latency, and fallback status.

### Requirements

- Python 3.12 + Streamlit 1.40+
- Read access to:
  - `data/test_cases/test_cases.jsonl` (thesis cohort)
  - `data/test_cases_1050/test_cases.jsonl` (paper cohort)
  - `data/eval/cell_*/` (thesis-era 16-cell factorial results)
  - `data/eval_1050/cell_*/` (paper-extension 5-cell results)
  - `data/eval_1050/cell_S_responses/` (paper cohort v3 LEA sidecars)
  - `data/Human_Phenotype_Ontology/hp.obo` (HPO labels — optional)

Already installed in the project's `pytorch-env` virtual environment.

### What this demo deliberately does NOT do

- **No live LLM inference**: rankings are pre-computed and loaded from
  disk. This is intentional — a defense laptop should not depend on a
  16 GB+ GPU + 24 GB+ VRAM vLLM server being up.
- **No live retrieval**: no Qdrant query at runtime. The retrieved
  chunks shown for the paper cohort are those captured during the
  original Cell S evaluation runs.
- **No write operations**: read-only on the data directories.

If you want a live demo with full retrieval + LEA inference, that's a
different deployment — see CLAUDE.md §Phase 2 for the production
FastAPI + CopilotKit + Next.js stack that runs against a live local
vLLM + Qdrant.

### Suggested presentation flow

1. **Open with a known-good case**: pick a metabolic case where
   Cell S = rank 1 and Cell K (Exomiser) is also top-5. Frames
   geno_agent as "the strongest literature-only system".
2. **Show a case where Cell S beats Exomiser dramatically**: e.g., an
   immunological case where Cell S = rank 1 and Exomiser = rank 10+.
3. **Show the LEA rationale** (paper cohort): expand the top-1 gene's
   rationale to show the system explains *why* it picked that gene,
   with PMC citation links.
4. **Show a case where geno_agent fails**: pick an overlap-present
   developmental case where Exomiser wins. Honest framing.
5. **(Q&A backup)**: switch cohorts to demonstrate the paper-extension
   work; show a Thread D fair-cohort case where geno_agent (S) =
   top-1 and LIRICAL (M) is wrong.

### Troubleshooting

- "Could not load test cases" → cohort path doesn't exist; check
  `data/test_cases*/test_cases.jsonl`.
- HPO labels missing → `hp.obo` not present at expected path; demo
  still works, IDs shown without labels.
- LEA rationale section empty for thesis cohort → expected; thesis
  sidecars predate the v3 response-logging patch. Use the paper
  cohort for rationale demos.

---

*Demo built for the geno_agent TFM defense at Universidad Alfonso X,
2026-05. Companion to the paper-extension manuscript work targeting
Genome Medicine.*
