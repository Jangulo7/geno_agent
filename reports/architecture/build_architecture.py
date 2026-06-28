#!/usr/bin/env python3
"""Poster-grade architecture figure for the geno_agent system.

Generates a single, print-ready landscape SVG (and a PNG preview) that makes
BOTH the engineering (agentic RAG pipeline, hybrid retrieval, infra) and the
science (2x2 deconfounded design, factorial ablation, statistical rigor) legible
at conference-poster distance.

    python reports/architecture/build_architecture.py

Outputs:
    reports/architecture/geno_agent_architecture.svg   (canonical, vector)
    reports/architecture/geno_agent_architecture.png   (high-res preview)
"""
from __future__ import annotations

import html
from pathlib import Path

# ---------------------------------------------------------------- design system
W, H = 2560, 1900
SANS = "Helvetica, Arial, 'DejaVu Sans', sans-serif"
MONO = "'DejaVu Sans Mono', monospace"

INK, INK2, MUTE = "#1f2a44", "#3d4a66", "#6b7794"
WHITE = "#ffffff"
PANEL, PANEL2, BORDER = "#f7f8fb", "#eef1f6", "#cdd6e4"

# (accent, light-bg, border) per family
BLUE = ("#2f5bd6", "#eef2fd", "#9db4ee")
GREEN = ("#2e8b57", "#eaf6ee", "#9ad0ae")
PURP = ("#6a4fb0", "#f0ecfa", "#c3b3e6")
ORNG = ("#e07a1f", "#fdf3e6", "#f0c184")
PINK = ("#c2497d", "#fbecf3", "#e7b0ca")
TEAL = ("#1f8f8f", "#e6f5f4", "#9bd4d2")
SLATE = ("#516079", "#eef1f6", "#b9c3d4")
RED = "#d6453f"

E: list[str] = []


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def rrect(x, y, w, h, r=16, fill=WHITE, stroke=BORDER, sw=2, dash=None, opacity=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    o = f' opacity="{opacity}"' if opacity != 1.0 else ""
    E.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" ry="{r}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>'
    )


def txt(x, y, s, size=18, weight="normal", fill=INK, anchor="start", family=SANS, ls=None):
    extra = f' letter-spacing="{ls}"' if ls else ""
    E.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}>{esc(s)}</text>'
    )


def line(x1, y1, x2, y2, stroke=INK2, sw=2.5, dash=None, marker=True):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = ' marker-end="url(#arrow)"' if marker else ""
    E.append(
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{sw}"{d}{m}/>'
    )


def path(d, stroke=INK2, sw=2.5, fill="none", dash=None, marker=True):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    m = ' marker-end="url(#arrow)"' if marker else ""
    E.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{da}{m}/>')


def section_header(x, y, num, title, accent):
    E.append(f'<circle cx="{x+20}" cy="{y}" r="20" fill="{accent}"/>')
    txt(x + 20, y + 9, num, size=24, weight="bold", fill=WHITE, anchor="middle")
    txt(x + 54, y + 9, title, size=30, weight="bold", fill=INK)


def card(x, y, w, h, title, accent, lines, sub=None, r=14, title_size=20, mono_lines=()):
    """A titled card with an accent-colored bold title and body lines."""
    ac, bg, bd = accent
    rrect(x, y, w, h, r=r, fill=bg, stroke=bd, sw=2)
    rrect(x, y, 7, h, r=r, fill=ac, stroke=ac, sw=0)  # accent spine
    txt(x + 22, y + 32, title, size=title_size, weight="bold", fill=ac)
    cy = y + 32
    if sub:
        cy += 24
        txt(x + 22, cy, sub, size=14, weight="normal", fill=MUTE)
    cy += 30
    for i, ln in enumerate(lines):
        fam = MONO if i in mono_lines else SANS
        sz = 15 if fam == MONO else 17
        txt(x + 22, cy, ln, size=sz, weight="normal", fill=INK2, family=fam)
        cy += 26


# ================================================================== background
E.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
E.append(
    '<defs>'
    '<marker id="arrow" markerWidth="11" markerHeight="11" refX="8" refY="4" orient="auto">'
    '<path d="M0,0 L9,4 L0,8 z" fill="#3d4a66"/></marker>'
    '<marker id="arrowB" markerWidth="11" markerHeight="11" refX="8" refY="4" orient="auto">'
    '<path d="M0,0 L9,4 L0,8 z" fill="#2f5bd6"/></marker>'
    '<marker id="arrowR" markerWidth="11" markerHeight="11" refX="8" refY="4" orient="auto">'
    '<path d="M0,0 L9,4 L0,8 z" fill="#d6453f"/></marker>'
    '</defs>'
)

# ===================================================================== header
txt(W / 2, 62, "geno_agent — Multi-agent RAG for rare-disease causal-gene prioritization",
    size=44, weight="bold", fill=INK, anchor="middle")
txt(W / 2, 100,
    "Agentic retrieval over full-text biomedical literature  ·  engineered for scale  ·  evaluated with deconfounded statistical rigor",
    size=22, weight="normal", fill=MUTE, anchor="middle")

# ----------------------------------------------------------- hero metric strip
metrics = [
    ("1,047", "patient cases"),
    ("50", "candidate genes / case"),
    ("4 + 1", "agents + self-correction"),
    ("768-d", "PubMedBERT hybrid"),
    ("12", "factorial ablation cells"),
    ("2 × 2", "difficulty × leakage"),
    ("n = 282", "deconfounded FAIR cohort"),
    ("Holm / BH", "multiplicity-corrected"),
]
mx, my, mw, mh, mgap = 60, 132, (W - 120 - 7 * 14) / 8, 70, 14
for i, (big, small) in enumerate(metrics):
    x = mx + i * (mw + mgap)
    rrect(x, my, mw, mh, r=12, fill=PANEL, stroke=BORDER, sw=2)
    txt(x + mw / 2, my + 33, big, size=27, weight="bold", fill=BLUE[0], anchor="middle")
    txt(x + mw / 2, my + 56, small, size=14, weight="normal", fill=INK2, anchor="middle")

# ============================================================== hero I/O flow
fy, fh = 228, 150
inp_w, sys_w, out_w = 640, 760, 700
gap = (W - 120 - inp_w - sys_w - out_w) / 2
ix = 60
sx = ix + inp_w + gap
ox = sx + sys_w + gap

# input
rrect(ix, fy, inp_w, fh, r=16, fill=BLUE[1], stroke=BLUE[2], sw=2)
txt(ix + 26, fy + 38, "Patient case  (input)", size=22, weight="bold", fill=BLUE[0])
for k, ln in enumerate(["HPO phenotype terms (observed)",
                        "50 candidate genes  =  1 causal + 49 distractors",
                        "no genome / variants — phenotype-driven"]):
    txt(ix + 26, fy + 74 + k * 28, "•  " + ln, size=18, fill=INK2)

# system (emphasized)
rrect(sx, fy, sys_w, fh, r=18, fill="#2f5bd6", stroke="#2747a8", sw=2)
txt(sx + sys_w / 2, fy + 50, "geno_agent", size=36, weight="bold", fill=WHITE, anchor="middle")
txt(sx + sys_w / 2, fy + 84, "multi-agent Retrieval-Augmented Generation over a PMC-OA corpus",
    size=19, fill="#dce6ff", anchor="middle")
txt(sx + sys_w / 2, fy + 116, "LangGraph state-graph  ·  hybrid retrieval  ·  LLM evidence aggregation",
    size=16, fill="#b9c9f7", anchor="middle")

# output
rrect(ox, fy, out_w, fh, r=16, fill=GREEN[1], stroke=GREEN[2], sw=2)
txt(ox + 26, fy + 38, "Ranked diagnosis  (output)", size=22, weight="bold", fill=GREEN[0])
for k, ln in enumerate(["genes re-ranked 1 → 50 by aggregate confidence",
                        "supporting literature chunks + per-gene rationale",
                        "explainable & auditable (RAGAS / DeepEval validated)"]):
    txt(ox + 26, fy + 74 + k * 28, "•  " + ln, size=18, fill=INK2)

line(ix + inp_w, fy + fh / 2, sx - 8, fy + fh / 2, stroke="#2f5bd6", sw=4)
line(sx + sys_w, fy + fh / 2, ox - 8, fy + fh / 2, stroke="#2f5bd6", sw=4)

# ======================================================= SECTION 1 — SYSTEM
CL, CR = 86, W - 86          # content left / right margins
s1x, s1y, s1w = 60, 430, W - 120
s1h = 588
rrect(s1x, s1y, s1w, s1h, r=18, fill=PANEL, stroke=BORDER, sw=2)
section_header(CL, s1y + 40, "1", "The system  —  engineering", BLUE[0])
txt(CR, s1y + 49, "deterministic by default; any agent swappable to an LLM variant",
    size=16, fill=MUTE, anchor="end")

# --- agent graph row (spread to fill content width)
node_w, node_h, dr = 330, 96, 60
gy = s1y + 130
dcy = gy + node_h / 2
# evenly distribute: planner, retriever, critic, <diamond>, synthesizer across [CL, CR]
span = CR - CL
fixed = 4 * node_w + 2 * dr
gap = (span - fixed) / 4
xp = CL
xr = xp + node_w + gap
xc = xr + node_w + gap
dia_cx = xc + node_w + gap + dr
xs = dia_cx + dr + gap
agent_nodes = [
    (xp, "query_planner", "HPO expand (dist 2)\n→ per-gene queries"),
    (xr, "retriever", "hybrid search\ntop-k = 10 / gene"),
    (xc, "critic", "grade chunks 1–5\n+ evidence type"),
    (xs, "synthesizer", "aggregate → rank\ndet  |  LEA (LLM)"),
]
for nx, name, sub in agent_nodes:
    rrect(nx, gy, node_w, node_h, r=14, fill=WHITE, stroke=BLUE[0], sw=2.5)
    txt(nx + node_w / 2, gy + 36, name, size=22, weight="bold", fill=BLUE[0], anchor="middle", family=MONO)
    for j, sln in enumerate(sub.split("\n")):
        txt(nx + node_w / 2, gy + 62 + j * 22, sln, size=15, fill=INK2, anchor="middle")
# diamond router
E.append(f'<path d="M{dia_cx},{dcy-dr} L{dia_cx+dr},{dcy} L{dia_cx},{dcy+dr} L{dia_cx-dr},{dcy} z" '
         f'fill="{ORNG[1]}" stroke="{RED}" stroke-width="2.5"/>')
txt(dia_cx, dcy - 4, "router", size=17, weight="bold", fill=RED, anchor="middle")
txt(dia_cx, dcy + 20, "low-conf?", size=13, fill=RED, anchor="middle")
# linear arrows
line(xp + node_w, dcy, xr - 8, dcy, stroke=BLUE[0], sw=3)
line(xr + node_w, dcy, xc - 8, dcy, stroke=BLUE[0], sw=3)
line(xc + node_w, dcy, dia_cx - dr - 6, dcy, stroke=BLUE[0], sw=3)
line(dia_cx + dr, dcy, xs - 8, dcy, stroke=GREEN[0], sw=3)
txt((dia_cx + dr + xs) / 2, dcy - 12, "finalize", size=14, weight="bold", fill=GREEN[0], anchor="middle")
# self-correction loop: router top → arc above → retriever top
loop_top = gy - 40
path(f"M{dia_cx},{dcy-dr} C{dia_cx},{loop_top} {xr+node_w/2},{loop_top} {xr+node_w/2},{gy-6}",
     stroke=RED, sw=3, marker=True)
txt((dia_cx + xr) / 2, loop_top - 10,
    "self-correction loop  ≤ 3   (re-retrieve while low-confidence grades > 5)",
    size=15, weight="bold", fill=RED, anchor="middle")

# --- AgentState bus
busy = gy + node_h + 46
rrect(CL, busy, CR - CL, 58, r=12, fill=PURP[1], stroke=PURP[2], sw=2)
txt(CL + 20, busy + 24, "AgentState", size=18, weight="bold", fill=PURP[0])
txt(CL + 156, busy + 24, "shared typed state flowing through every node", size=15, fill=MUTE)
txt(CL + 20, busy + 47,
    "hpo_terms · candidate_genes · expanded_hpo · mesh_queries · retrieved{gene→chunks} · grades{gene→1–5} · ranked[50] · iteration · lea_log",
    size=14, fill=INK2, family=MONO)
for nx, *_ in agent_nodes:
    line(nx + node_w / 2, gy + node_h, nx + node_w / 2, busy, stroke=PURP[2], sw=1.6, dash="4,4", marker=False)

# --- retrieval engine + inference + index (3 sub-cards, 5 lines each)
sub_y = busy + 78
sub_h = 196
col_w = (CR - CL - 2 * 30) / 3
rx1, rx2, rx3 = CL, CL + col_w + 30, CL + 2 * (col_w + 30)
card(rx1, sub_y, col_w, sub_h, "Hybrid retrieval engine", TEAL,
     ["Dense — PubMedBERT 768-d (cosine, HNSW)",
      "Sparse — BM25 / IDF (fastembed)",
      "Fusion — Reciprocal Rank Fusion (RRF)",
      "Rerank — MedCPT cross-encoder 50 → 10",
      "Store — Qdrant (on-disk HNSW · ~26 GB)"])
card(rx2, sub_y, col_w, sub_h, "On-prem LLM inference", PINK,
     ["Qwen3-8B (FP16) via vLLM :8001 · temp 0",
      "RTX 5090 · OpenAI-compatible endpoint",
      "drives LLM query-planner / LLM-critic",
      "+ LEA (LLM-as-Evidence-Aggregator)",
      "no patient data leaves the host"],
     mono_lines={0})
card(rx3, sub_y, col_w, sub_h, "Offline literature index", ORNG,
     ["PMC-OA full text (FTP · s5cmd bulk sync)",
      "parse JATS-XML → normalize → dedupe",
      "section-aware chunking (UUID5 ids)",
      "embed on CUDA → L2-norm parquet",
      "upsert → Qdrant (dense + BM25)"])

# ================================================ models / ontologies strip
mstrip_y = s1y + s1h + 24
mstrip_h = 134
rrect(60, mstrip_y, W - 120, mstrip_h, r=16, fill=GREEN[1], stroke=GREEN[2], sw=2)
txt(CL, mstrip_y + 34, "Ontologies + models  (knowledge & ML resources consumed)",
    size=22, weight="bold", fill=GREEN[0])
models = [
    ("HPO", "hp.obo · phenotype\nexpansion + labels"),
    ("HGNC", "gene symbols\n+ aliases"),
    ("MONDO", "disease ontology\ncohort categories"),
    ("Gene Ontology", "go.obo\n(reference)"),
    ("PubMedBERT", "768-d dense\nembeddings"),
    ("BM25", "sparse lexical\n(fastembed)"),
    ("MedCPT", "cross-encoder\nrerank 50→10"),
    ("Qwen3-8B", "local LLM (vLLM)\nplanner/critic/LEA"),
    ("GPT-4o", "LLM judge only\nnever prioritizes"),
]
ms_n, ms_gap = len(models), 16
ms_w = (CR - CL - (ms_n - 1) * ms_gap) / ms_n
for i, (nm, ds) in enumerate(models):
    x = CL + i * (ms_w + ms_gap)
    yy = mstrip_y + 50
    rrect(x, yy, ms_w, 66, r=10, fill=WHITE, stroke=GREEN[2], sw=1.6)
    txt(x + ms_w / 2, yy + 25, nm, size=16, weight="bold", fill=GREEN[0], anchor="middle")
    for j, sln in enumerate(ds.split("\n")):
        txt(x + ms_w / 2, yy + 44 + j * 16, sln, size=12, fill=INK2, anchor="middle")

# ================================================ SECTION 2 — SCIENCE
s2y = mstrip_y + mstrip_h + 26
s2h = H - s2y - 110
rrect(60, s2y, W - 120, s2h, r=18, fill=PANEL, stroke=BORDER, sw=2)
section_header(CL, s2y + 40, "2", "The evaluation  —  science & rigor", PURP[0])
txt(CR, s2y + 49, "controlled · deconfounded · multiplicity-corrected", size=16, fill=MUTE, anchor="end")

inner_y = s2y + 76
lc_x, lc_w = CL, 720
cc_x, cc_w = lc_x + lc_w + 36, 768
rc_x = cc_x + cc_w + 36
rc_w = CR - rc_x

# -- left column: cohort + factorial + baselines
card(lc_x, inner_y, lc_w, 152, "Cohort construction (Phase 1B)", TEAL,
     ["GA4GH Phenopacket Store v0.1.26 — 6,668 packets",
      "filters → 4 MONDO categories (neuro/metab/immuno/develop)",
      "1,047 cases · per-case blake2b-seeded 50-gene lists"],
     sub="real patients → reproducible benchmark")
card(lc_x, inner_y + 170, lc_w, 152, "Factorial ablation (12 cells)", PURP,
     ["{single | multi-agent} × {dense | hybrid}",
      "× {det | LLM-planner | LLM-critic} × {LEA}",
      "headline: D (multi·hybrid) · L (+CE) · S = geno_agent"],
     sub="isolates the contribution of every design choice", mono_lines={2})
card(lc_x, inner_y + 340, lc_w, 134, "Baselines (HPO-only, curated tools)", PINK,
     ["Exomiser v14.0.2 (Cell K) — hiPhive prioritiser",
      "LIRICAL v2.4.0 (Cell M) — likelihood-ratio diagnosis",
      "RRF ensemble (Cell N/P · k = 60)"])

# -- center: the 2x2 design centerpiece (self-contained card with internal axes)
cc_h = 474
rrect(cc_x, inner_y, cc_w, cc_h, r=16, fill=WHITE, stroke=PURP[2], sw=2.5)
txt(cc_x + cc_w / 2, inner_y + 40, "2 × 2 controlled design", size=25, weight="bold",
    fill=PURP[0], anchor="middle")
txt(cc_x + cc_w / 2, inner_y + 68, "distractor difficulty  ×  literature data-leakage",
    size=16, fill=MUTE, anchor="middle")
strip = 150                      # left strip for row labels
g2x = cc_x + strip
g2y = inner_y + 130
g2w = cc_w - strip - 26
g2h = 252
cell_w, cell_h = g2w / 2, g2h / 2
col_labels = [("Full cohort", "n = 1,047"), ("FAIR · overlap-absent", "n = 282")]
row_labels = [("Standard", "random distractors"), ("Hard", "Resnik-similar")]
cell_txt = [["leaky + easy", "deconfounded"], ["leaky + hard", "fair + hard"]]
cell_tag = [["", ""], ["", "strongest test"]]
cell_fill = [[BLUE[1], TEAL[1]], [ORNG[1], GREEN[1]]]
for c in range(2):
    cx = g2x + c * cell_w
    txt(cx + cell_w / 2, g2y - 36, col_labels[c][0], size=16, weight="bold", fill=INK, anchor="middle")
    txt(cx + cell_w / 2, g2y - 16, col_labels[c][1], size=14, fill=MUTE, anchor="middle")
for r in range(2):
    ry = g2y + r * cell_h
    txt(g2x - 18, ry + cell_h / 2 - 6, row_labels[r][0], size=16, weight="bold", fill=INK, anchor="end")
    txt(g2x - 18, ry + cell_h / 2 + 16, row_labels[r][1], size=13, fill=MUTE, anchor="end")
    for c in range(2):
        cx = g2x + c * cell_w
        strong = (r == 1 and c == 1)
        rrect(cx + 6, ry + 6, cell_w - 12, cell_h - 12, r=12,
              fill=cell_fill[r][c], stroke=(RED if strong else BORDER), sw=(3 if strong else 1.8))
        txt(cx + cell_w / 2, ry + cell_h / 2 - 8, "top-1 accuracy", size=15, weight="bold",
            fill=INK, anchor="middle")
        txt(cx + cell_w / 2, ry + cell_h / 2 + 14, cell_txt[r][c], size=13,
            fill=(RED if strong else INK2), anchor="middle")
        if cell_tag[r][c]:
            txt(cx + cell_w / 2, ry + cell_h / 2 + 33, "← " + cell_tag[r][c], size=12,
                weight="bold", fill=RED, anchor="middle")
txt(cc_x + cc_w / 2, inner_y + cc_h - 18,
    "standard row published · hard row in progress — same cases, distractors differ",
    size=13, fill=MUTE, anchor="middle")

# -- right column: confound callout + stats + judges
card(rc_x, inner_y, rc_w, 186, "Data-leakage control  (the key science)", SLATE,
     ["765 / 1,047 cases cite their source PMID",
      "in phenotype.hpoa — HPO-only tools then",
      "recall memorized labels, not predict.",
      "Removing them → FAIR cohort (n = 282)",
      "isolates phenotype-driven signal."])
rrect(rc_x, inner_y, rc_w, 186, r=14, fill="none", stroke=RED, sw=2.5)  # emphasis ring
card(rc_x, inner_y + 204, rc_w, 134, "Statistical rigor", BLUE,
     ["paired McNemar (top-1) · bootstrap 95% CI",
      "Holm (FWER) + Benjamini-Hochberg (FDR)",
      "stratified by category × overlap status"])
card(rc_x, inner_y + 356, rc_w, 118, "LLM-as-judge validation", ORNG,
     ["RAGAS faithfulness + DeepEval · GPT-4o",
      "n = 100 stratified · seed 42",
      "measures faithfulness — never ranks"])

# ===================================================================== footer
fyy = H - 104
rrect(60, fyy, W - 120, 52, r=12, fill=PANEL2, stroke=BORDER, sw=2)
txt(86, fyy + 33,
    "Stack:  Python · LangGraph · Qdrant · vLLM · sentence-transformers · fastembed · pronto · RAGAS · DeepEval · Streamlit · Vercel",
    size=17, weight="bold", fill=INK2)
txt(W - 86, fyy + 33, "Johanna Angulo  ·  Universidad Europea (PhD)",
    size=17, weight="bold", fill=BLUE[0], anchor="end")

# legend of decision points along the very bottom (clear of the footer box)
txt(86, H - 22,
    "decision points:  ◇ retrieval mode (dense|bm25|hybrid)  ·  agent variant (det|LLM)  ·  synthesizer (det|LEA)  ·  loop (rel≤2 >5 & iter<3)  ·  CE-rerank (cells L/S)  ·  ensemble (RRF k=60)",
    size=14, fill=MUTE)

# ===================================================================== write
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
       f'viewBox="0 0 {W} {H}">' + "".join(E) + "</svg>")
out = Path(__file__).resolve().parent
(out / "geno_agent_architecture.svg").write_text(svg, encoding="utf-8")
print("wrote geno_agent_architecture.svg")
try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(out / "geno_agent_architecture.png"),
                     output_width=W * 2, output_height=H * 2)
    print("wrote geno_agent_architecture.png")
except Exception as exc:  # pragma: no cover
    print("PNG render skipped:", exc)
