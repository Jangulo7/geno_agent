# geno_agent — demo apps

Lightweight demo applications that load **pre-computed** per-case JSONs
from the project's evaluation directories. No live LLM / Qdrant calls —
safe to run on a laptop without GPU or network during a presentation.

Two apps, designed for different audiences:

| App | Audience | Tone |
|---|---|---|
| `streamlit_thesis_presentation.py` ⭐ **Recommended for the defence** | Thesis committee + general audience | Narrative, design-led, 4-page story (Challenge → How It Works → Try It Live → The Numbers) with an animated multi-agent architecture diagram + progressive-reveal demo mode |
| `streamlit_thesis_demo.py` | Technical reviewers / Q&A backup | Utilitarian data browser — full cohort access, multi-cell side-by-side rankings, raw LEA rationale dumps |

## ⭐ Defence-grade presentation app

**File**: `streamlit_thesis_presentation.py`

A 4-page narrative Streamlit app optimised for a ~10-15 min thesis
defence:

1. **🧬 The Challenge** — opens with the problem (300M patients,
   5-7 yr odyssey, 50 % undiagnosed) and the geno_agent value
   proposition in 3 bullets. Gradient hero typography + colour-coded
   stat cards.
2. **🧠 How It Works** — interactive SVG diagram of the 7-stage
   pipeline (HPO → Planner → Retriever → Critic → Synthesiser → LEA
   → Output) with per-agent role cards. Includes the §11.5 factorial
   highlight: single-agent · dense = 5.3 % top-1 → multi-agent ·
   hybrid = 62.7 % (+57.4 pp from the architectural decomposition).
3. **🎯 Try It Live** — curated demo-scenario picker with 3
   hand-selected cases:
   - 🏆 *The wow case* — `ADRA2A` lipodystrophy where geno_agent
     ranks the causal gene at #1 and Exomiser at #16
   - ✅ *Clean win* — `STXBP1` where both systems agree
   - 🔍 *The hard case* — `KDM6B` where Exomiser wins; honest
     reporting
   - Plus a "browse all 75" fallback for Q&A
   Progressive reveal mode: clicks reveal each agent stage in
   sequence, with the SVG diagram showing live ✓ / ⟳ status badges,
   then a final geno_agent vs Exomiser side-by-side ranking with
   green/red hero boxes for the top-1 prediction.
4. **📊 The Numbers** — headline metrics in three stat cards:
   Cell S = 0.787 top-1, Exomiser = 0.773, Δ = +1.4 pp. Architectural-
   ablation bar chart showing the contribution of each layer
   (A → D = +57.4 pp, D → L = +10.6 pp, L → S = +5.4 pp). Per-MONDO
   breakdown chart.
5. **👩‍🎓 About** — thesis info, code/data pointers, methodology
   references.

Run:

```bash
cd /path/to/geno_agent
source ~/pytorch-env/bin/activate
streamlit run demos/streamlit_thesis_presentation.py
```

Opens at http://localhost:8501.

**Suggested defence flow** (10 min):

| Min | Page | Talking point |
|---|---|---|
| 0:00–1:30 | 🧬 The Challenge | Hook the audience with the diagnostic-odyssey stats; introduce the literature-only thesis. |
| 1:30–4:00 | 🧠 How It Works | Walk through the SVG diagram; emphasise that the architecture (not the LLM) is the contribution. Read the +57.4 pp lift aloud. |
| 4:00–7:30 | 🎯 Try It Live | Open the wow case (`ADRA2A`); click "Reveal: …" 7 times to walk through each agent. End on the green hero box (geno_agent rank 1 vs Exomiser rank 16). |
| 7:30–9:00 | 📊 The Numbers | Show the ablation bar chart, then the +1.4 pp result vs Exomiser. |
| 9:00–10:00 | 👩‍🎓 About | Wrap with thesis info + Q&A invitation. |

## Data-browser app (reference / Q&A backup)

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
