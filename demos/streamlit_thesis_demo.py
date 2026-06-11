"""Streamlit demo for the geno_agent master-thesis defense presentation.

Self-contained: loads pre-computed per-case JSONs from
``data/eval/cell_*/`` (thesis n=75 cohort) and ``data/eval_1050/cell_*/``
(paper-extension n=1,047 cohort, when the chosen case is also in the
larger cohort). No vLLM / Qdrant / live LLM calls — safe to run on a
defense laptop without GPU or network.

Layout:
  Left sidebar:
    - Cohort picker (thesis n=75 / paper n=1,047)
    - Case picker (searchable dropdown)
    - Side-by-side comparison toggle (which cells to display)

  Main panel:
    - Header: case_id + causal gene + MONDO category + source PMID
    - Patient HPO terms (with labels from hp.obo if available)
    - Side-by-side ranking cards for the selected cells
    - Causal-gene rank-position chart across cells
    - When a v3 paper-cohort case is selected: rich LEA rationale +
      retrieved chunks (PMC citations) per top-ranked gene

Run::

    cd /path/to/geno_agent
    source ~/pytorch-env/bin/activate
    streamlit run demos/streamlit_thesis_demo.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HPO_OBO = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"

# Cohorts available to the demo. Each entry maps to a (test_cases_path, eval_root, cell_to_dir).
COHORTS = {
    "Thesis n=75 (v0.1.19, seed 4242)": {
        "test_cases": PROJECT_ROOT / "data" / "test_cases" / "test_cases.jsonl",
        "eval_root": PROJECT_ROOT / "data" / "eval",
        "cells": {
            "S — geno_agent (rerank + LEA)": "cell_S_rerank_inside_plus_lea",
            "L — Cell D + CE-rerank": "cell_L_rerank_inside_d",
            "D — multi-agent hybrid": "cell_D_multi_hybrid",
            "K — Exomiser HPO-only": "cell_K_exomiser_hpo_only",
            "P — D+K ensemble (RRF)": "cell_P_ensemble_d_k",
        },
        "responses_dir": None,  # thesis sidecars don't have lea_log.lea_user_prompt
    },
    "Paper extension n=1,047 (v0.1.26, seed 42)": {
        "test_cases": PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl",
        "eval_root": PROJECT_ROOT / "data" / "eval_1050",
        "cells": {
            "S — geno_agent (rerank + LEA)": "cell_S_rerank_inside_plus_lea",
            "L — Cell D + CE-rerank": "cell_L_rerank_inside_d",
            "D — multi-agent hybrid": "cell_D_multi_hybrid",
            "K — Exomiser HPO-only": "cell_K_exomiser_hpo_only",
            "M — LIRICAL HPO-only": "cell_M_lirical_hpo_only",
            "N — RRF(M, S) ensemble": "cell_N_rrf_m_s",
        },
        # cell_S_responses/ has the v3 lea_log with full prompts + chunks
        "responses_dir": PROJECT_ROOT / "data" / "eval_1050" / "cell_S_responses",
    },
}


# ----------------------------------------------------------------------------
# Data loading (cached)
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
def load_test_cases(path: Path) -> dict[str, dict]:
    """Load test_cases.jsonl into {case_id: case_dict}."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            c = json.loads(line)
            out[c["case_id"]] = c
    return out


@st.cache_data(show_spinner=False)
def load_ranking(eval_root: Path, cell_dir: str, case_id: str) -> list[dict] | None:
    """Load one (cell, case) ranking JSON. Returns list-of-50 ranked-gene dicts."""
    path = eval_root / cell_dir / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


@st.cache_data(show_spinner=False)
def load_response_sidecar(responses_dir: Path, case_id: str) -> dict | None:
    """Load v3 LEA sidecar with full prompts + per-gene chunks (paper cohort only)."""
    if not responses_dir:
        return None
    path = responses_dir / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ----------------------------------------------------------------------------
# Rendering helpers
# ----------------------------------------------------------------------------


def hpo_term_display(hpo_id: str, labels: dict[str, str]) -> str:
    label = labels.get(hpo_id, "")
    return f"`{hpo_id}` {label}" if label else f"`{hpo_id}`"


def causal_rank(ranking: list[dict], causal: str) -> int | None:
    for e in ranking or []:
        if e.get("symbol") == causal or e.get("gene") == causal:
            return e.get("final_rank") or e.get("rank")
    return None


def render_ranking_card(
    cell_label: str, ranking: list[dict] | None, causal_gene: str, show_top: int = 10
) -> None:
    """Render one cell's top-N ranked-gene cards."""
    st.markdown(f"### {cell_label}")
    if not ranking:
        st.warning("No data for this cell.")
        return
    rank = causal_rank(ranking, causal_gene)
    if rank == 1:
        st.success(f"✅ Causal gene `{causal_gene}` at TOP-1")
    elif rank and rank <= 5:
        st.info(f"🔍 Causal gene `{causal_gene}` at rank {rank} (top-5)")
    elif rank and rank <= 10:
        st.warning(f"📍 Causal gene `{causal_gene}` at rank {rank} (top-10)")
    elif rank:
        st.error(f"❌ Causal gene `{causal_gene}` at rank {rank} (out of top-10)")
    else:
        st.error(f"❌ Causal gene `{causal_gene}` not in this cell's ranking")

    rows = []
    for e in ranking[:show_top]:
        sym = e.get("symbol") or e.get("gene") or "?"
        rank_pos = e.get("final_rank") or e.get("rank") or "?"
        conf = e.get("aggregate_confidence") or e.get("confidence") or 0
        is_causal = sym == causal_gene
        marker = "🎯 " if is_causal else ""
        rows.append(
            {
                "Rank": rank_pos,
                "Gene": f"{marker}{sym}",
                "Confidence": f"{conf:.3f}" if isinstance(conf, (int, float)) else conf,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True, height=400)


def render_lea_rationale(sidecar: dict, top_n: int = 5) -> None:
    """For paper-cohort cases: render the v3 LEA rationale + retrieved chunks."""
    lea = sidecar.get("lea_log") or {}
    parsed = lea.get("lea_response_parsed") or []
    evidence = lea.get("lea_evidence_per_gene") or {}

    if not parsed:
        st.info(
            "This case has no LEA rationale captured (likely from before "
            "the v3 response-logging patch)."
        )
        return

    st.markdown("### LEA rationale (top genes)")
    st.caption(
        f"LEA tokens in/out: "
        f"{lea.get('lea_response_tokens_in', '?')}/{lea.get('lea_response_tokens_out', '?')} | "
        f"latency: {lea.get('lea_response_latency_s', 0):.1f}s | "
        f"fallback: {lea.get('lea_fallback_reason') or 'none'}"
    )

    for entry in parsed[:top_n]:
        gene = entry.get("gene", "?")
        conf = entry.get("confidence", 0.0)
        rationale = entry.get("rationale", "")
        chunks = evidence.get(gene, [])
        with st.expander(f"**{gene}** — confidence {conf:.2f}", expanded=(entry == parsed[0])):
            if rationale:
                st.markdown(f"> {rationale}")
            else:
                st.caption("(no rationale)")
            if chunks:
                st.markdown(f"**Supporting evidence ({len(chunks)} chunks):**")
                for i, ch in enumerate(chunks, 1):
                    pmcid = (ch or {}).get("source_pmcid") if isinstance(ch, dict) else None
                    section = (ch or {}).get("section_type") if isinstance(ch, dict) else None
                    score = (ch or {}).get("score_rrf") if isinstance(ch, dict) else None
                    text = (ch or {}).get("text") if isinstance(ch, dict) else None
                    head = f"**Chunk {i}**"
                    if pmcid:
                        head += f" — [{pmcid}](https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/)"
                    if section:
                        head += f" / {section}"
                    if isinstance(score, (int, float)):
                        head += f" / RRF={score:.3f}"
                    st.markdown(head)
                    if text:
                        st.markdown(f"> {text[:600]}{'…' if len(text) > 600 else ''}")


def render_rank_chart(rankings: dict[str, list[dict] | None], causal_gene: str) -> None:
    """Bar chart of causal-gene rank across cells (lower = better)."""
    data = []
    for cell_label, ranking in rankings.items():
        rank = causal_rank(ranking, causal_gene)
        data.append(
            {"cell": cell_label, "causal_rank": rank if rank else 0, "missing": rank is None}
        )
    st.markdown("### Causal-gene rank across cells (lower is better — 1 = perfect)")
    chart_data = {row["cell"]: (row["causal_rank"] if row["causal_rank"] else 51) for row in data}
    st.bar_chart(chart_data, horizontal=True, height=200)
    st.caption("Missing or >50 cases shown as 51 (max + 1).")


# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="geno_agent — TFM defense demo",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        "# 🧬 geno_agent — Multi-agent RAG for rare-disease gene prioritisation\n"
        "**TFM (Master's thesis) defense demo** | Universidad Alfonso X | "
        "Johanna Angulo"
    )

    hpo_labels = load_hpo_labels()
    if not hpo_labels:
        st.warning(
            "`data/Human_Phenotype_Ontology/hp.obo` not found — "
            "HPO labels will be shown as IDs only."
        )

    # ----- sidebar
    st.sidebar.header("Configuration")
    cohort_name = st.sidebar.radio(
        "Cohort",
        list(COHORTS),
        index=0,
        help="Thesis cohort = n=75 from v0.1.19 (2026-05 thesis defense). "
        "Paper cohort = n=1,047 from v0.1.26 (paper extension).",
    )
    cohort = COHORTS[cohort_name]

    test_cases = load_test_cases(cohort["test_cases"])
    if not test_cases:
        st.error(f"Could not load test cases from {cohort['test_cases']}")
        return

    # Group cases by category for nicer picking
    by_cat = defaultdict(list)
    for cid, case in test_cases.items():
        by_cat[case.get("category", "unknown")].append(cid)
    cats = sorted(by_cat)

    category = st.sidebar.selectbox("Filter by MONDO category", ["(all)", *cats])
    case_options = sorted(test_cases) if category == "(all)" else sorted(by_cat[category])

    case_id = st.sidebar.selectbox(
        f"Case ({len(case_options)} available)",
        case_options,
        help="Each case is a phenotyped patient with a known causal gene "
        "(SOLVED per Phenopacket Store).",
    )
    case = test_cases[case_id]

    cell_labels = list(cohort["cells"])
    selected_cells = st.sidebar.multiselect(
        "Cells to display",
        cell_labels,
        default=[c for c in cell_labels if c.startswith(("S —", "K —"))],
    )

    # ----- main panel
    causal = case.get("causal_gene", "")
    cat_label = case.get("category", "unknown")
    diseases = case.get("diseases", [])
    src_pmid = case_id.split(":", 1)[1].split("_")[1] if ":" in case_id else "?"

    st.markdown(f"## Case: `{case_id}`")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Causal gene", causal)
    col_b.metric("MONDO category", cat_label)
    col_c.metric("HPO terms", len(case.get("hpo_terms", [])))
    col_d.metric("Source", f"PMID:{src_pmid}")

    if diseases:
        st.markdown(
            "**Diagnosed disease(s):** "
            + ", ".join(f"`{d.get('id', '')}` {d.get('label', '')}" for d in diseases)
        )

    with st.expander("Patient HPO phenotypes", expanded=False):
        for hpo_id in case.get("hpo_terms", []):
            st.markdown("- " + hpo_term_display(hpo_id, hpo_labels))

    st.divider()

    # Load rankings for each selected cell
    rankings: dict[str, list[dict] | None] = {}
    for cell_label in selected_cells:
        cell_dir = cohort["cells"][cell_label]
        rankings[cell_label] = load_ranking(cohort["eval_root"], cell_dir, case_id)

    if not selected_cells:
        st.info("Pick at least one cell in the sidebar to see rankings.")
        return

    # Side-by-side ranking cards
    if len(selected_cells) == 1:
        render_ranking_card(selected_cells[0], rankings[selected_cells[0]], causal)
    else:
        cols = st.columns(len(selected_cells))
        for col, cell_label in zip(cols, selected_cells, strict=False):
            with col:
                render_ranking_card(cell_label, rankings[cell_label], causal)

    st.divider()
    render_rank_chart(rankings, causal)

    # v3 LEA rationale section — paper cohort only
    if cohort.get("responses_dir"):
        sidecar = load_response_sidecar(cohort["responses_dir"], case_id)
        if sidecar:
            st.divider()
            render_lea_rationale(sidecar, top_n=5)

    # Footer
    st.divider()
    st.caption(
        f"geno_agent demo · cohort = {cohort_name} · "
        f"data sources: `{cohort['test_cases'].relative_to(PROJECT_ROOT)}` + "
        f"`{cohort['eval_root'].relative_to(PROJECT_ROOT)}/cell_*/` · "
        "no live LLM/Qdrant calls in this demo (pre-computed rankings only)."
    )


if __name__ == "__main__":
    main()
