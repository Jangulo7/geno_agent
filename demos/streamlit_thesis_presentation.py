"""Defense-grade Streamlit presentation for the geno_agent TFM.

Narrative 4-page app (The Challenge → How It Works → Try It Live →
The Numbers) optimised for a thesis-defense audience. No live LLM /
Qdrant — loads pre-computed thesis-cohort sidecars from
``data/eval/cell_*/``. Highlights the multi-agent architecture
explicitly with an animated SVG diagram and a progressive-reveal demo
mode that walks the audience through each agent's contribution.

Designed for ~10-15 min defense talks: open on The Challenge, switch
to How It Works for the architecture pitch, run a live demo on a
curated "wow" case, finish on The Numbers.

Run::

    cd /path/to/geno_agent
    source ~/pytorch-env/bin/activate
    streamlit run demos/streamlit_thesis_presentation.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HPO_OBO = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"
THESIS_CASES = PROJECT_ROOT / "data" / "test_cases" / "test_cases.jsonl"
THESIS_EVAL = PROJECT_ROOT / "data" / "eval"

# Curated demo cases — hand-picked from the n=75 thesis cohort
CURATED_CASES: Final[dict[str, dict]] = {
    "🏆 The wow case — geno_agent rank 1, Exomiser rank 16": {
        "case_id": "ADRA2A:PMID_27376152_FPLD1223",
        "narrative": (
            "Patient with familial partial lipodystrophy type 8. The full "
            "geno_agent stack (multi-agent + CE-rerank + LEA) ranks the "
            "causal gene ADRA2A at **#1**, while Exomiser puts it at #16 "
            "and the deterministic multi-agent baseline misses it "
            "entirely (rank 50). This is the case that motivates the "
            "thesis: literature-grounded reasoning surfaces a gene a "
            "phenotype-database tool cannot."
        ),
    },
    "✅ Clean win — both systems get it right": {
        "case_id": "STXBP1:PMID_35190816_STX_26514728_Patient_18",
        "narrative": (
            "Patient with STXBP1-associated developmental and epileptic "
            "encephalopathy. Both geno_agent (S) and Exomiser (K) "
            "correctly rank STXBP1 at #1 — a clean, well-characterised "
            "case where curated tools work as well as literature retrieval."
        ),
    },
    "🔍 The hard case — geno_agent struggles": {
        "case_id": "KDM6B:PMID_37196654_Individual44DDD_286674",
        "narrative": (
            "Patient with KDM6B-related neurodevelopmental disorder. "
            "Exomiser correctly ranks KDM6B at #1 (it's well-characterised "
            "in their curated KB); geno_agent (S) places it at #11. "
            "Honest reporting — the literature-only approach has limits "
            "when curated phenotype-gene tables already capture the gene "
            "perfectly."
        ),
    },
}

# Multi-agent pipeline metadata for the architecture diagram
AGENTS = [
    {
        "id": "input",
        "name": "Patient HPO",
        "icon": "🧬",
        "color": "#64748b",
        "role": "Input",
        "description": "Patient's phenotypic profile encoded as HPO terms + a 50-gene candidate list from upstream variant calling.",
    },
    {
        "id": "planner",
        "name": "Planner",
        "icon": "🎯",
        "color": "#3b82f6",
        "role": "Query Planner Agent",
        "description": "Decomposes the HPO term set into focused literature queries — one per gene x phenotype combination — handling synonym expansion and clinical-language reformulation.",
        "output": "Per-gene query packets",
    },
    {
        "id": "retriever",
        "name": "Retriever",
        "icon": "📚",
        "color": "#8b5cf6",
        "role": "Retriever Agent",
        "description": "Hybrid dense + BM25 search over a frozen Qdrant index of 4.2M chunks from 287K PMC Open Access articles. Reciprocal-rank fusion combines the two signals.",
        "output": "Top-50 chunks per gene",
    },
    {
        "id": "critic",
        "name": "Critic",
        "icon": "⚖️",
        "color": "#ec4899",
        "role": "Critic Agent",
        "description": "Cross-encoder rerank (MedCPT) over the retrieved chunks. Re-scores each chunk for query-specific relevance using a biomedical-tuned bi-directional model.",
        "output": "Top-3 reranked chunks per top-15 gene",
    },
    {
        "id": "synthesizer",
        "name": "Synthesiser",
        "icon": "📊",
        "color": "#f97316",
        "role": "Synthesiser Agent",
        "description": "Aggregates per-gene chunk scores into a deterministic preliminary ranking (Cell L). Identifies the top-15 genes worth deep LLM reasoning.",
        "output": "Top-15 gene shortlist",
    },
    {
        "id": "lea",
        "name": "LEA",
        "icon": "🧠",
        "color": "#10b981",
        "role": "LLM-as-Evidence-Aggregator",
        "description": "Qwen3-8B (local vLLM) reads the top-15 genes x top-3 chunks each, reasons over the evidence, and emits a final ranked list with per-gene confidence + free-text rationale citing PMC passages.",
        "output": "Final ranking with rationale + citations",
    },
    {
        "id": "output",
        "name": "Ranking",
        "icon": "🎯",
        "color": "#15803d",
        "role": "Output",
        "description": "Ranked candidate genes with confidence scores, per-gene rationale, and traceable PMC literature citations. Ready for clinician review.",
    },
]


# ----------------------------------------------------------------------------
# CSS theme + page config
# ----------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
  /* Hero typography */
  .hero-title {
    font-size: 3.2rem;
    font-weight: 800;
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem;
    line-height: 1.1;
  }
  .hero-tagline {
    font-size: 1.4rem;
    color: #475569;
    font-weight: 400;
    margin-bottom: 2rem;
  }
  /* Stat cards */
  .stat-card {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-left: 6px solid #3b82f6;
    border-radius: 0.75rem;
    padding: 1.5rem;
    margin: 1rem 0;
  }
  .stat-card.win {
    border-left-color: #10b981;
    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  }
  .stat-card.warn {
    border-left-color: #f59e0b;
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  }
  .stat-card.fail {
    border-left-color: #dc2626;
    background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  }
  .stat-number {
    font-size: 3rem;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 0.2rem;
  }
  .stat-label {
    color: #64748b;
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }
  /* Agent cards (for architecture page) */
  .agent-card {
    background: white;
    border-radius: 0.75rem;
    border: 2px solid #e2e8f0;
    padding: 1.2rem;
    margin: 0.5rem 0;
    transition: all 0.2s ease;
  }
  .agent-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1);
  }
  .agent-card .icon {
    font-size: 2.5rem;
    line-height: 1;
  }
  .agent-card .name {
    font-size: 1.2rem;
    font-weight: 700;
    color: #1e293b;
  }
  .agent-card .role {
    font-size: 0.85rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  /* Top-1 hero box */
  .top1-hero {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    border-radius: 1rem;
    padding: 2rem;
    margin: 1rem 0;
    text-align: center;
  }
  .top1-hero.fail {
    background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
  }
  .top1-hero .gene {
    font-size: 3rem;
    font-weight: 800;
    letter-spacing: 0.02em;
  }
  .top1-hero .conf {
    font-size: 1.2rem;
    opacity: 0.95;
  }
  /* Step indicator */
  .step-pill {
    display: inline-block;
    background: #e0e7ff;
    color: #4338ca;
    padding: 0.25rem 0.8rem;
    border-radius: 1rem;
    font-size: 0.85rem;
    font-weight: 600;
    margin-right: 0.5rem;
  }
  .step-pill.done {
    background: #d1fae5;
    color: #065f46;
  }
  .step-pill.active {
    background: #fef3c7;
    color: #92400e;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }
  /* Section dividers */
  .section-header {
    color: #1e293b;
    font-size: 1.8rem;
    font-weight: 700;
    margin-top: 2rem;
    margin-bottom: 1rem;
    border-bottom: 3px solid #3b82f6;
    padding-bottom: 0.5rem;
  }
</style>
"""

# ----------------------------------------------------------------------------
# Cached data loading (same loaders as the data-browser demo)
# ----------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def load_hpo_labels() -> dict[str, str]:
    """Parse hp.obo into {HP:0000001: 'Phenotypic abnormality', ...}."""
    if not HPO_OBO.exists():
        return {}
    labels: dict[str, str] = {}
    current_id: str | None = None
    for line in HPO_OBO.read_text().splitlines():
        if line.startswith("id: HP:"):
            current_id = line[4:].strip()
        elif line.startswith("name: ") and current_id:
            labels[current_id] = line[6:].strip()
            current_id = None
        elif line.startswith("[Term]"):
            current_id = None
    return labels


@st.cache_data(show_spinner=False)
def load_test_cases() -> dict[str, dict]:
    """Thesis test cases."""
    if not THESIS_CASES.exists():
        return {}
    out: dict[str, dict] = {}
    with THESIS_CASES.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            c = json.loads(line)
            out[c["case_id"]] = c
    return out


@st.cache_data(show_spinner=False)
def load_ranking(cell_dir: str, case_id: str) -> list[dict] | None:
    path = THESIS_EVAL / cell_dir / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def causal_rank(ranking: list[dict] | None, causal: str) -> int | None:
    if not ranking:
        return None
    for e in ranking:
        if e.get("symbol") == causal:
            return e.get("final_rank")
    return None


# ----------------------------------------------------------------------------
# Architecture diagram (inline SVG)
# ----------------------------------------------------------------------------


def render_architecture_svg(
    active_agent: str | None = None, completed: set[str] | None = None
) -> str:
    """Render the 7-stage pipeline as an SVG.

    Args:
        active_agent: id of the currently-running agent (yellow pulse)
        completed: set of agent ids that have completed (green check)
    """
    completed = completed or set()
    width = 1100
    height = 220
    box_w, box_h = 130, 110
    gap = 20

    # Layout: 7 boxes left to right, evenly spaced
    n = len(AGENTS)
    margin_left = (width - (n * box_w + (n - 1) * gap)) // 2

    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width: 100%; height: auto; max-height: 240px;">',
        "<defs>",
        '  <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" '
        'orient="auto" markerUnits="strokeWidth">',
        '    <path d="M0,0 L0,6 L9,3 z" fill="#94a3b8" />',
        "  </marker>",
        "</defs>",
    ]

    for i, ag in enumerate(AGENTS):
        x = margin_left + i * (box_w + gap)
        y = 55
        # Determine state
        if ag["id"] in completed:
            stroke = "#10b981"
            badge = "✓"
            badge_fill = "#10b981"
        elif ag["id"] == active_agent:
            stroke = "#f59e0b"
            badge = "⟳"
            badge_fill = "#f59e0b"
        else:
            stroke = "#cbd5e1"
            badge = ""
            badge_fill = ""

        # Box
        svg_parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" '
            f'rx="14" fill="white" stroke="{stroke}" stroke-width="3"/>'
        )
        # Icon
        svg_parts.append(
            f'<text x="{x + box_w // 2}" y="{y + 38}" text-anchor="middle" '
            f'font-size="28">{ag["icon"]}</text>'
        )
        # Name
        svg_parts.append(
            f'<text x="{x + box_w // 2}" y="{y + 65}" text-anchor="middle" '
            f'font-size="14" font-weight="700" fill="{ag["color"]}">{ag["name"]}</text>'
        )
        # Role hint
        svg_parts.append(
            f'<text x="{x + box_w // 2}" y="{y + 85}" text-anchor="middle" '
            f'font-size="10" fill="#64748b">{ag.get("role", "")[:18]}</text>'
        )
        # Status badge
        if badge:
            svg_parts.append(
                f'<circle cx="{x + box_w - 12}" cy="{y + 12}" r="10" fill="{badge_fill}"/>'
            )
            svg_parts.append(
                f'<text x="{x + box_w - 12}" y="{y + 16}" text-anchor="middle" '
                f'font-size="12" fill="white" font-weight="700">{badge}</text>'
            )
        # Arrow to next
        if i < n - 1:
            x_arrow_start = x + box_w
            x_arrow_end = x + box_w + gap - 2
            y_arrow = y + box_h // 2
            svg_parts.append(
                f'<line x1="{x_arrow_start}" y1="{y_arrow}" '
                f'x2="{x_arrow_end}" y2="{y_arrow}" '
                f'stroke="#94a3b8" stroke-width="2.5" marker-end="url(#arrow)"/>'
            )

    # Title above
    svg_parts.insert(
        1,
        (
            '<text x="550" y="30" text-anchor="middle" '
            'font-size="18" font-weight="700" fill="#1e293b">'
            "Multi-agent retrieval-augmented gene prioritisation pipeline"
            "</text>"
        ),
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------


def page_challenge() -> None:
    st.markdown(
        '<div class="hero-title">geno_agent</div>'
        '<div class="hero-tagline">Multi-agent literature-grounded reasoning '
        "for rare-disease gene prioritisation</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown('<div class="section-header">The Challenge</div>', unsafe_allow_html=True)

    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            '<div class="stat-card">'
            '<div class="stat-number" style="color:#3b82f6;">300M</div>'
            '<div class="stat-label">people affected globally</div>'
            '<p style="margin-top:0.8rem;color:#475569;">'
            "Rare diseases (each <1:2,000) collectively affect an estimated "
            "300 million people worldwide — between 3.5 % and 8 % of the "
            "global population."
            "</p></div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            '<div class="stat-card warn">'
            '<div class="stat-number" style="color:#f59e0b;">5-7 yrs</div>'
            '<div class="stat-label">average diagnostic odyssey</div>'
            '<p style="margin-top:0.8rem;color:#475569;">'
            "Rare-disease patients see on average 7 different specialists "
            "and wait 5-7 years to receive a correct molecular diagnosis."
            "</p></div>",
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            '<div class="stat-card fail">'
            '<div class="stat-number" style="color:#dc2626;">~50 %</div>'
            '<div class="stat-label">remain undiagnosed</div>'
            '<p style="margin-top:0.8rem;color:#475569;">'
            "Despite next-generation sequencing, roughly half of all exome "
            "and genome sequencing cases remain without a molecular "
            "diagnosis (Clark et al., 2018)."
            "</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="section-header">Why curated tools fall short</div>', unsafe_allow_html=True
    )

    st.markdown(
        "Phenotype-driven prioritisation tools such as **Exomiser** and "
        "**LIRICAL** work well when the causal gene is already richly "
        "annotated in their curated knowledge bases. But they cannot "
        "surface **novel** or **emerging** gene-phenotype associations that "
        "exist only in the unstructured literature — case reports, "
        "functional studies, phenotype-expansion papers."
    )

    st.markdown(
        "PubMed indexes **>1,000,000 new articles per year**. The PMC Open "
        "Access subset alone contains **>4 million full-text articles**. "
        "No human curator — and no static knowledge base — can keep pace."
    )

    st.markdown('<div class="section-header">The geno_agent thesis</div>', unsafe_allow_html=True)

    st.markdown(
        "> **An agentic, multi-agent retrieval-augmented generation (RAG) "
        "system, deployed on local hardware and grounded in PMC Open Access "
        "full text, can meaningfully assist rare-disease gene prioritisation — "
        "matching or exceeding curated-knowledge-base tools while producing "
        "evidence-traceable, clinician-readable rationales.**"
    )

    cols2 = st.columns(3)
    with cols2[0]:
        st.markdown(
            "**🧠 Four specialised agents** — Query Planner, Retriever, "
            "Critic, Synthesiser — orchestrated as a LangGraph state "
            "graph, enabling iterative refinement."
        )
    with cols2[1]:
        st.markdown(
            "**📚 Frozen PMC OA index** — 4.2M chunks from 287K articles "
            "in a local Qdrant, reproducible bit-perfect across runs."
        )
    with cols2[2]:
        st.markdown(
            "**🔬 Local LLM** — Qwen3-8B as evidence aggregator, with "
            "free-text rationale per ranked gene + PMC citations. No "
            "cloud APIs at inference."
        )

    st.info(
        "👉 **Continue to *How It Works* in the sidebar** to see the "
        "multi-agent architecture in detail, then *Try It Live* for "
        "a walk-through on a real patient case."
    )


def page_architecture() -> None:
    st.markdown(
        '<div class="hero-title" style="font-size:2.5rem;">How It Works</div>'
        '<div class="hero-tagline">The four agents + LEA, end-to-end</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown(
        render_architecture_svg(completed={a["id"] for a in AGENTS}), unsafe_allow_html=True
    )

    st.markdown('<div class="section-header">The agents in detail</div>', unsafe_allow_html=True)

    for ag in AGENTS:
        if ag["id"] in ("input", "output"):
            continue
        with st.container():
            cols = st.columns([1, 5])
            with cols[0]:
                st.markdown(
                    f'<div style="font-size:4rem;text-align:center;'
                    f"background:{ag['color']}22;border-radius:1rem;"
                    f'padding:1rem 0;">{ag["icon"]}</div>',
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(
                    f'<div class="agent-card" style="border-left:6px solid {ag["color"]};">'
                    f'<div class="role">{ag["role"]}</div>'
                    f'<div class="name">{ag["name"]}</div>'
                    f'<p style="margin-top:0.5rem;color:#334155;">{ag["description"]}</p>'
                    f'<div style="margin-top:0.8rem;font-size:0.9rem;color:#475569;">'
                    f"<strong>Output:</strong> {ag.get('output', '—')}"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

    st.markdown('<div class="section-header">Why multi-agent?</div>', unsafe_allow_html=True)
    st.markdown(
        "**The §11.5 factorial result speaks for itself:**\n\n"
        "- **Single-agent · dense retrieval** (Cell A): top-1 = **0.053** — "
        "essentially random on 50-gene candidate lists.\n"
        "- **Multi-agent · hybrid retrieval** (Cell D): top-1 = **0.627** — "
        "a **+57.4 percentage-point lift** from the same task.\n"
        "- **+ Cross-encoder rerank + LEA** (Cell S, full stack): "
        "top-1 = **0.787** — beating the Exomiser HPO-only baseline at 0.773.\n\n"
        "The multi-agent decomposition is the single largest architectural "
        "lever in the pipeline. The LLM at the end adds the final +5 pp on "
        "top of an already-strong rerank."
    )


def page_demo() -> None:
    st.markdown(
        '<div class="hero-title" style="font-size:2.5rem;">Try It Live</div>'
        '<div class="hero-tagline">Pick a patient case; watch the agents work</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    test_cases = load_test_cases()
    hpo_labels = load_hpo_labels()
    if not test_cases:
        st.error("Test-case data missing.")
        return

    # Curated case picker
    st.markdown("### Choose a demo scenario")
    scenario = st.radio(
        "Scenario",
        [*list(CURATED_CASES), "📋 Browse all 75 cases"],
        index=0,
        label_visibility="collapsed",
    )

    if scenario == "📋 Browse all 75 cases":
        case_id = st.selectbox("Case", sorted(test_cases))
        narrative = None
    else:
        case_id = CURATED_CASES[scenario]["case_id"]
        narrative = CURATED_CASES[scenario]["narrative"]

    if case_id not in test_cases:
        st.error(f"Case {case_id} not found in cohort.")
        return

    case = test_cases[case_id]
    causal = case["causal_gene"]
    src_pmid = case_id.split(":", 1)[1].split("_")[1] if ":" in case_id else "?"

    if narrative:
        st.info(narrative)

    # Patient card
    st.markdown('<div class="section-header">Patient profile</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    cols[0].metric("Causal gene", causal)
    cols[1].metric("Disease category", case.get("category", "?"))
    cols[2].metric("HPO terms", len(case.get("hpo_terms", [])))
    cols[3].metric("Source", f"PMID:{src_pmid}")

    with st.expander(
        f"📋 Patient's {len(case.get('hpo_terms', []))} HPO phenotypes", expanded=True
    ):
        for hpo_id in case.get("hpo_terms", []):
            label = hpo_labels.get(hpo_id, "")
            st.markdown(f"- `{hpo_id}` **{label}**" if label else f"- `{hpo_id}`")

    # Progressive reveal
    st.markdown(
        '<div class="section-header">Multi-agent pipeline — live walkthrough</div>',
        unsafe_allow_html=True,
    )

    # Session state for revealed stages
    state_key = f"reveal__{case_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = set()

    revealed = st.session_state[state_key]

    btn_col, reset_col = st.columns([3, 1])
    with btn_col:
        if len(revealed) < len(AGENTS):
            next_id = next(ag["id"] for ag in AGENTS if ag["id"] not in revealed)
            next_name = next(ag["name"] for ag in AGENTS if ag["id"] == next_id)
            if st.button(f"▶ Reveal: {next_name}", type="primary", use_container_width=True):
                st.session_state[state_key].add(next_id)
                st.rerun()
        else:
            st.success("✅ All pipeline stages revealed. See the final ranking below.")
    with reset_col:
        if st.button("↺ Reset", use_container_width=True):
            st.session_state[state_key] = set()
            st.rerun()

    # Diagram with completion state
    active = None
    if len(revealed) < len(AGENTS):
        active = next(ag["id"] for ag in AGENTS if ag["id"] not in revealed)
    st.markdown(
        render_architecture_svg(active_agent=active, completed=revealed), unsafe_allow_html=True
    )

    # Per-stage details
    for ag in AGENTS:
        if ag["id"] not in revealed:
            continue
        with st.container():
            cols = st.columns([1, 8])
            cols[0].markdown(
                f'<div style="font-size:2.5rem;text-align:center;">{ag["icon"]}</div>',
                unsafe_allow_html=True,
            )
            with cols[1]:
                st.markdown(
                    f'<div class="step-pill done">✓ {ag["role"]}</div>'
                    f" <strong>{ag['name']}</strong>",
                    unsafe_allow_html=True,
                )
                st.markdown(ag["description"])

                # Per-case data demos for some stages
                if ag["id"] == "input":
                    st.caption(
                        f"Input: {len(case.get('hpo_terms', []))} HPO terms, "
                        f"50-gene candidate list (1 causal + 49 distractors)"
                    )
                elif ag["id"] == "retriever":
                    st.caption(
                        "Hybrid retrieval over the frozen PMC OA index "
                        "(4.2M chunks from 287K articles) — top-50 chunks per gene"
                    )
                elif ag["id"] == "critic":
                    st.caption(
                        "MedCPT cross-encoder rerank — keeps top-3 chunks per gene "
                        "based on biomedical-tuned query-chunk similarity"
                    )
                elif ag["id"] == "synthesizer":
                    # Show Cell D / L preliminary ranking
                    d_rank = causal_rank(load_ranking("cell_D_multi_hybrid", case_id), causal)
                    l_rank = causal_rank(load_ranking("cell_L_rerank_inside_d", case_id), causal)
                    if d_rank or l_rank:
                        st.caption(
                            f"Preliminary deterministic ranking — "
                            f"causal gene {causal} at rank "
                            f"{d_rank or '?'} (Cell D) → "
                            f"{l_rank or '?'} (Cell L, after CE-rerank)"
                        )
                elif ag["id"] == "lea":
                    s_rank = causal_rank(
                        load_ranking("cell_S_rerank_inside_plus_lea", case_id), causal
                    )
                    if s_rank == 1:
                        st.caption(
                            f"🎯 **Causal gene {causal} now at rank 1** "
                            f"after LEA reasoning over the literature evidence"
                        )
                    elif s_rank:
                        st.caption(f"Causal gene {causal} at final rank {s_rank}")
        st.markdown("")

    # Final ranking (after LEA stage revealed)
    if "lea" in revealed:
        st.markdown(
            '<div class="section-header">Final ranking — geno_agent vs Exomiser</div>',
            unsafe_allow_html=True,
        )
        s_ranking = load_ranking("cell_S_rerank_inside_plus_lea", case_id)
        k_ranking = load_ranking("cell_K_exomiser_hpo_only", case_id)

        cols = st.columns(2)
        with cols[0]:
            st.markdown("#### 🧬 geno_agent (Cell S)")
            _render_top1_hero(s_ranking, causal)
            _render_top_table(s_ranking, causal, show_top=5)
        with cols[1]:
            st.markdown("#### 🏥 Exomiser HPO-only")
            _render_top1_hero(k_ranking, causal)
            _render_top_table(k_ranking, causal, show_top=5)


def _render_top1_hero(ranking: list[dict] | None, causal: str) -> None:
    if not ranking:
        st.warning("No ranking data.")
        return
    top1 = ranking[0]
    top1_gene = top1.get("symbol", "?")
    top1_conf = top1.get("aggregate_confidence", 0)
    is_correct = top1_gene == causal
    rank = causal_rank(ranking, causal)
    klass = "top1-hero" if is_correct else "top1-hero fail"
    badge = "✅ CORRECT" if is_correct else f"❌ Causal at rank {rank}"
    st.markdown(
        f'<div class="{klass}">'
        f'<div style="font-size:0.85rem;opacity:0.9;text-transform:uppercase;'
        f'letter-spacing:0.05em;font-weight:600;">Predicted top-1</div>'
        f'<div class="gene">{top1_gene}</div>'
        f'<div class="conf">confidence {top1_conf:.3f} · {badge}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_top_table(ranking: list[dict] | None, causal: str, show_top: int = 5) -> None:
    if not ranking:
        return
    rows = []
    for e in ranking[:show_top]:
        sym = e.get("symbol", "?")
        rank_pos = e.get("final_rank", "?")
        conf = e.get("aggregate_confidence", 0)
        marker = "🎯 " if sym == causal else ""
        rows.append({"Rank": rank_pos, "Gene": f"{marker}{sym}", "Confidence": f"{conf:.3f}"})
    st.dataframe(rows, use_container_width=True, hide_index=True, height=220)


def page_numbers() -> None:
    st.markdown(
        '<div class="hero-title" style="font-size:2.5rem;">The Numbers</div>'
        '<div class="hero-tagline">Headline results from the thesis-defended n=75 cohort</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            '<div class="stat-card win">'
            '<div class="stat-number" style="color:#10b981;">0.787</div>'
            '<div class="stat-label">top-1 — geno_agent (Cell S)</div>'
            '<p style="margin-top:0.5rem;color:#475569;">'
            "Multi-agent + CE-rerank + LEA on the n=75 thesis cohort."
            "</p></div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            '<div class="stat-card">'
            '<div class="stat-number" style="color:#3b82f6;">0.773</div>'
            '<div class="stat-label">top-1 — Exomiser HPO-only</div>'
            '<p style="margin-top:0.5rem;color:#475569;">'
            "Industry-standard phenotype-driven baseline."
            "</p></div>",
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            '<div class="stat-card win">'
            '<div class="stat-number" style="color:#10b981;">+1.4 pp</div>'
            '<div class="stat-label">geno_agent vs Exomiser</div>'
            '<p style="margin-top:0.5rem;color:#475569;">'
            "Literature-only approach matches the curated-KB gold standard."
            "</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="section-header">Architectural ablation — what each layer contributes</div>',
        unsafe_allow_html=True,
    )

    ablation_data = {
        "Cell A — single-agent · dense": 0.053,
        "Cell B — single-agent · hybrid": 0.173,
        "Cell C — multi-agent · dense": 0.133,
        "Cell D — multi-agent · hybrid (deterministic)": 0.627,
        "Cell L — D + CE-rerank": 0.733,
        "Cell K — Exomiser HPO-only (baseline)": 0.773,
        "Cell S — D + CE-rerank + LEA (geno_agent)": 0.787,
    }
    st.bar_chart(ablation_data, horizontal=True, height=350)
    st.caption(
        "Each row = a cell from the §11.5 factorial. The +57.4 pp lift from A → D "
        "is the multi-agent + hybrid-retrieval contribution; +10.6 pp from D → L is "
        "CE-rerank; +5.4 pp from L → S is LEA."
    )

    st.markdown(
        '<div class="section-header">Per-MONDO category breakdown (Cell S vs Cell K)</div>',
        unsafe_allow_html=True,
    )

    per_mondo = {
        "developmental (n=19)": {"Cell S (geno_agent)": 0.789, "Cell K (Exomiser)": 0.947},
        "immunological (n=10)": {"Cell S (geno_agent)": 0.900, "Cell K (Exomiser)": 0.700},
        "metabolic (n=22)": {"Cell S (geno_agent)": 0.864, "Cell K (Exomiser)": 0.864},
        "neurological (n=24)": {"Cell S (geno_agent)": 0.667, "Cell K (Exomiser)": 0.667},
    }
    st.bar_chart(per_mondo, height=300, stack=False)
    st.caption(
        "Cell S wins on immunological (+20 pp), ties on metabolic + neurological, "
        "trails on developmental (where Exomiser's curated DB is most mature)."
    )

    st.markdown('<div class="section-header">Operational profile</div>', unsafe_allow_html=True)
    cols2 = st.columns(4)
    cols2[0].metric("Hardware", "1 x RTX 5090")
    cols2[1].metric("Wall time / case", "~26 s")
    cols2[2].metric("Cloud API spend", "$0")
    cols2[3].metric("Reproducibility", "Bit-perfect on top-1")

    st.info(
        "**The defence claim**: a multi-agent literature-only system, running "
        "all-local on a single workstation GPU, matches an established "
        "curated-knowledge-base gold standard on rare-disease gene prioritisation. "
        "The architectural decomposition (4 agents + LEA) accounts for the lift; "
        "the LLM is not the headline, the orchestration is."
    )


def page_about() -> None:
    st.markdown(
        '<div class="hero-title" style="font-size:2.5rem;">About</div>'
        '<div class="hero-tagline">Master\'s thesis · Universidad Alfonso X · 2026</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    cols = st.columns([2, 1])
    with cols[0]:
        st.markdown(
            "### Thesis\n"
            "**Multi-Agent RAG for Rare-Disease Gene Prioritization**\n\n"
            "Master in Artificial Intelligence, Universidad Alfonso X (UAX).\n"
            "Defended 2026-05.\n\n"
            "**Author:** Johanna Angulo Quintero\n\n"
            "### Companion work\n"
            "A post-thesis paper extension (n=1,047 cohort, annotation-overlap "
            "deconfounding, publication-recency stratification, LLM-family ablation, "
            "RAGAS + DeepEval evaluation) is targeting *Genome Medicine* and will be "
            "published openly upon acceptance.\n\n"
            "### Code & data\n"
            "- Thesis snapshot: github.com/Jangulo7/geno_agent_thesis (publishing on defence day)\n"
            "- Paper extension: github.com/Jangulo7/geno_agent (private until paper acceptance)\n"
            "- All HPO / MONDO / Phenopacket Store inputs pinned to 2026 releases\n\n"
            "### Methodology references\n"
            "- Smedley et al. *Nat Protoc* 2015 — Exomiser HPO-only baseline\n"
            "- Robinson et al. *Am J Hum Genet* 2020 — LIRICAL likelihood-ratio framework\n"
            "- Jin et al. 2023 — MedCPT cross-encoder\n"
            "- Phenopacket Store consortium 2026 — v0.1.19 cohort source"
        )
    with cols[1]:
        st.markdown(
            '<div class="stat-card">'
            '<div class="stat-label">Cohort</div>'
            '<div style="font-size:2rem;font-weight:700;color:#1e293b;">n = 75</div>'
            '<div style="color:#64748b;">Phenopacket Store v0.1.19</div>'
            '<div style="color:#64748b;">stratified, seed 4242</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="stat-card">'
            '<div class="stat-label">Pipeline</div>'
            '<div style="font-size:1.4rem;font-weight:700;color:#1e293b;">4 agents + LEA</div>'
            '<div style="color:#64748b;">LangGraph state graph</div>'
            '<div style="color:#64748b;">Qwen3-8B local vLLM</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.caption(
        "This presentation app loads pre-computed thesis-cohort sidecars "
        "from `data/eval/cell_*/`. No live LLM / Qdrant calls — safe for "
        "any defence laptop without GPU or network. Built with Streamlit."
    )


# ----------------------------------------------------------------------------
# Main / router
# ----------------------------------------------------------------------------

PAGES = {
    "🧬 The Challenge": page_challenge,
    "🧠 How It Works": page_architecture,
    "🎯 Try It Live": page_demo,
    "📊 The Numbers": page_numbers,
    "👩‍🎓 About": page_about,
}


def main() -> None:
    st.set_page_config(
        page_title="geno_agent — TFM defence",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Sidebar nav
    st.sidebar.markdown(
        '<div style="text-align:center;font-size:3rem;">🧬</div>'
        '<div style="text-align:center;font-weight:800;font-size:1.4rem;'
        'color:#1e293b;">geno_agent</div>'
        '<div style="text-align:center;color:#64748b;font-size:0.9rem;'
        'margin-bottom:1rem;">TFM defence</div>',
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio("Section", list(PAGES), label_visibility="collapsed", index=0)
    st.sidebar.markdown("---")
    st.sidebar.caption("Universidad Alfonso X\n\nMaster in AI · 2026")

    PAGES[page]()


if __name__ == "__main__":
    main()
