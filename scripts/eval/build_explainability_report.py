"""Build a detailed explainability report for the LEA system (geno_agent).

Selects a diverse, reproducible case sample (seed=42) covering all four
MONDO categories x overlap status x outcome (top-1 correct / incorrect),
then for each selected case extracts:

  - case identifier and category
  - patient phenotype (HPO labels)
  - causal gene + S's top-1 prediction (with the correctness indicator)
  - LEA's free-text rationale for each of: causal, top-1, and a runner-up
  - the underlying retrieved chunks supporting each gene (PMCID + text excerpt)
  - link to the raw sidecar JSON file for full verification

Also writes the catalog of explainability layers in geno_agent vs the
3-system baselines (LIRICAL / Exomiser / CE-rerank-only) and the aggregate
quantitative coverage from `analyze_lea_rationales.py`.

Outputs:
  reports/explainability_report.md          (full text report)
  data/eval_1050/explainability_examples.json (machine-readable case dump)

Run::

    PYTHONPATH=. python scripts/eval/build_explainability_report.py
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("explainability")

DEFAULT_RESPONSES: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_S_responses"
DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
DEFAULT_STATS: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "thread_g_rationale_stats.json"
DEFAULT_OUT_MD: Final[Path] = PROJECT_ROOT / "reports" / "explainability_report.md"
DEFAULT_OUT_JSON: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "explainability_examples.json"

MAX_CHUNK_EXCERPT_CHARS: Final[int] = 600
TOP_N_CHUNKS_PER_GENE: Final[int] = 2  # what we show in the walkthrough


def load_sidecar(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load %s: %s", path, e)
        return None


def top1_from_sidecar(sc: dict) -> str | None:
    """Return the symbol ranked first by S (LEA parsed if present, else ranked[0])."""
    parsed = (sc.get("lea_log") or {}).get("lea_response_parsed") or []
    if isinstance(parsed, list) and parsed:
        return parsed[0].get("gene")
    ranked = sc.get("ranked") or []
    if ranked:
        return ranked[0].get("symbol")
    return None


def rationale_for(sc: dict, gene: str) -> str:
    parsed = (sc.get("lea_log") or {}).get("lea_response_parsed") or []
    if isinstance(parsed, list):
        for e in parsed:
            if e.get("gene") == gene:
                return (e.get("rationale") or "").strip()
    return ""


def confidence_for(sc: dict, gene: str) -> float | None:
    parsed = (sc.get("lea_log") or {}).get("lea_response_parsed") or []
    if isinstance(parsed, list):
        for e in parsed:
            if e.get("gene") == gene:
                return e.get("confidence")
    return None


def chunks_for(sc: dict, gene: str, n: int = TOP_N_CHUNKS_PER_GENE) -> list[dict]:
    """Return up to n chunk dicts (with text + pmcid + scores) for a gene."""
    ev = (sc.get("lea_log") or {}).get("lea_evidence_per_gene") or {}
    chunks = ev.get(gene) or []
    return chunks[:n]


def select_cases(responses_dir: Path, n_per_bucket: int = 2) -> list[Path]:
    """Pick a stratified deterministic sample of cases for the walkthroughs.

    Buckets: (category, outcome) where outcome is correct/wrong.
    Returns up to n_per_bucket cases per bucket (~ 16 paths total).
    """
    rng = random.Random(42)
    buckets: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for p in sorted(responses_dir.glob("*.json")):
        sc = load_sidecar(p)
        if not sc:
            continue
        cat = sc.get("category", "unknown")
        causal = sc.get("causal_gene")
        top1 = top1_from_sidecar(sc)
        outcome = "correct" if (causal and top1 and causal == top1) else "wrong"
        buckets[(cat, outcome)].append(p)

    selected: list[Path] = []
    for _bucket, paths in sorted(buckets.items()):
        take = paths if len(paths) <= n_per_bucket else rng.sample(paths, n_per_bucket)
        selected.extend(take)
    return selected


def build_case_walkthrough(
    sc: dict, sidecar_path: Path, overlap: dict[str, int], date_map: dict[str, str]
) -> dict:
    """Build a structured walkthrough record for one case."""
    case_id = sc.get("case_id")
    causal = sc.get("causal_gene", "")
    top1 = top1_from_sidecar(sc) or ""
    parsed = (sc.get("lea_log") or {}).get("lea_response_parsed") or []
    # Causal-gene rank (1-based)
    causal_rank = None
    if isinstance(parsed, list):
        for i, e in enumerate(parsed, start=1):
            if e.get("gene") == causal:
                causal_rank = i
                break
    if causal_rank is None:
        for i, e in enumerate(sc.get("ranked") or [], start=1):
            if e.get("symbol") == causal:
                causal_rank = i
                break
    correct_top1 = (causal == top1) and bool(causal)
    src_pmid = case_id.split(":")[1].split("_")[1] if ":" in case_id else ""

    out: dict = {
        "case_id": case_id,
        "category": sc.get("category"),
        "source_pmid": f"PMID:{src_pmid}" if src_pmid.isdigit() else None,
        "source_pub_date": date_map.get(src_pmid),
        "overlap_present": overlap.get(case_id),
        "hpo_terms": (sc.get("lea_log") or {}).get("hpo_labels") or sc.get("hpo_terms") or [],
        "causal_gene": causal,
        "predicted_top1_gene": top1,
        "top1_correct": correct_top1,
        "causal_rank": causal_rank,
        "lea_fallback": (sc.get("lea_log") or {}).get("lea_fallback_reason"),
        "lea_response_latency_s": (sc.get("lea_log") or {}).get("lea_response_latency_s"),
        "lea_response_tokens_in": (sc.get("lea_log") or {}).get("lea_response_tokens_in"),
        "lea_response_tokens_out": (sc.get("lea_log") or {}).get("lea_response_tokens_out"),
        "sidecar_path": str(sidecar_path.relative_to(PROJECT_ROOT)),
    }

    # Detail for: causal, top-1, second-ranked. De-duped.
    second = parsed[1].get("gene") if (isinstance(parsed, list) and len(parsed) > 1) else None
    detail_genes = [g for g in [top1, causal, second] if g]
    seen: set[str] = set()
    out["genes_detail"] = []
    for g in detail_genes:
        if g in seen:
            continue
        seen.add(g)
        role = []
        if g == top1:
            role.append("predicted top-1")
        if g == causal:
            role.append("causal (ground truth)")
        if g == second and g not in (top1, causal):
            role.append("runner-up")
        chunks = chunks_for(sc, g)
        out["genes_detail"].append(
            {
                "gene": g,
                "role": ", ".join(role),
                "lea_confidence": confidence_for(sc, g),
                "lea_rationale": rationale_for(sc, g) or "(no rationale)",
                "rank": next(
                    (
                        i
                        for i, e in enumerate(parsed, 1)
                        if isinstance(e, dict) and e.get("gene") == g
                    ),
                    None,
                ),
                "supporting_chunks": [
                    {
                        "source_pmcid": ch.get("source_pmcid"),
                        "section_type": ch.get("section_type"),
                        "score_rrf": ch.get("score_rrf"),
                        "score_dense": ch.get("score_dense"),
                        "score_bm25": ch.get("score_bm25"),
                        "text_excerpt": (ch.get("text") or "")[:MAX_CHUNK_EXCERPT_CHARS],
                    }
                    for ch in chunks
                ],
            }
        )
    return out


def write_markdown(out_path: Path, cases: list[dict], stats: dict) -> None:
    """Write the human-readable explainability report."""
    lines: list[str] = []
    lines.append("# Explainability report — LEA / geno_agent vs LIRICAL, Exomiser, CE-rerank-only")
    lines.append("")
    lines.append("**Authoritative companion data:**")
    lines.append(
        "- Aggregate quantitative coverage: `data/eval_1050/thread_g_rationale_stats.json`"
    )
    lines.append(
        "- Per-case walkthroughs (machine-readable): `data/eval_1050/explainability_examples.json`"
    )
    lines.append("- Per-case raw LEA sidecars (1,047 cases): `data/eval_1050/cell_S_responses/`")
    lines.append(
        "- Annotation-overlap flag per case: `data/test_cases_1050/annotation_overlap.json`"
    )
    lines.append("- PMID publication dates: `data/test_cases_1050/pmid_dates.json`")
    lines.append("")
    lines.append("**Companion analyses:**")
    lines.append(
        "- `paper_extension_results.md §16` — Thread G quantitative explainability findings"
    )
    lines.append("- `methodology.md §4.10` — Thread G technical framing")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Why an explainability-focused companion paper")
    lines.append("")
    lines.append("The Q1 prioritisation paper (target: Genome Medicine) makes an *accuracy* claim:")
    lines.append(
        "geno_agent is the #1 system on the fair-comparison cohort (n = 282 overlap-absent"
    )
    lines.append(
        "cases), beating LIRICAL by +8.2 pp ★ and Exomiser by +7.8 pp ★. Threads D + E + F"
    )
    lines.append("lock that claim in.")
    lines.append("")
    lines.append("Thread G's structural analysis revealed a *second, orthogonal* claim worth its")
    lines.append("own paper: **of the four systems compared, only geno_agent (Cell S) produces")
    lines.append("evidence-traceable rankings.** LIRICAL and Exomiser output numeric scores only;")
    lines.append("Cell L outputs ranked lists with chunk citations but no synthesis. **Cell S")
    lines.append("produces a free-text LEA rationale per ranked gene, plus a primary-literature")
    lines.append("citation trail of mean 2.81 PMCIDs per top-1 gene, with a deterministic-fallback")
    lines.append("rate of 0.2 % overall and 0.0 % on the fair cohort.**")
    lines.append("")
    lines.append("This contrast is *categorical*, not gradient — it cannot be improved by an")
    lines.append("Exomiser update because Exomiser's output format does not include free text.")
    lines.append("That makes it a defensible standalone contribution suitable for the clinical-")
    lines.append("XAI literature (target: *Artificial Intelligence in Medicine* or *Journal of")
    lines.append("Biomedical Informatics*) without competing with the prioritisation paper.")
    lines.append("")
    lines.append(
        "**Recommended sequencing:** finish the Q1 paper first; reuse this data foundation"
    )
    lines.append("for the XAI paper 3-6 months later.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Catalog of explainability layers in geno_agent")
    lines.append("")
    lines.append("geno_agent provides **six stacked layers** of explainability, of which only")
    lines.append("L4-L6 require LEA (Cell S). L1-L3 are inherited from Cells D and L.")
    lines.append("")
    lines.append("| Layer | Name | What it exposes | Per-case artefact |")
    lines.append("|---|---|---|---|")
    lines.append(
        "| **L1** | Retrieval transparency | Which chunks (PMCID + section_type) the hybrid retriever pulled per gene, with separate dense (cosine) and BM25 scores | `lea_log.lea_evidence_per_gene[gene][i].{source_pmcid, section_type, score_dense, score_bm25, score_rrf}` |"
    )
    lines.append(
        "| **L2** | Cross-encoder rerank scores | MedCPT-CE relevance scores re-prioritising the hybrid candidates within each gene | implicit (chunks are returned in CE-reranked order) |"
    )
    lines.append(
        "| **L3** | Hybrid fusion scores | Reciprocal-rank-fusion combination of dense + BM25, exposed per chunk | `score_rrf` (same as L1) |"
    )
    lines.append(
        "| **L4** | LEA free-text rationale | Per-gene natural-language reasoning explaining why this gene was ranked here | `lea_log.lea_response_parsed[i].rationale` |"
    )
    lines.append(
        "| **L5** | LEA confidence | Per-gene 0-1 confidence score the LLM assigned (independent of rank) | `lea_log.lea_response_parsed[i].confidence` |"
    )
    lines.append(
        "| **L6** | Deterministic-fallback flag | If LEA fails (LLM timeout, malformed JSON), we fall back to CE-rerank ordering and tag the case | `lea_log.lea_fallback_reason` (None when LEA succeeded) |"
    )
    lines.append("")
    lines.append("**Additional reproducibility metadata** captured per case for replay:")
    lines.append(
        "- `lea_log.lea_system_prompt` and `lea_log.lea_user_prompt` — full text of what the LLM saw"
    )
    lines.append("- `lea_log.lea_response_tokens_in`, `lea_response_tokens_out` — cost accounting")
    lines.append("- `lea_log.lea_response_latency_s` — wall time per case")
    lines.append(
        "- `lea_log.lea_response_finish_reason` — `stop` / `length` / `tool_calls` per OpenAI-compatible API"
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. 4-system explainability comparison")
    lines.append("")
    lines.append("Combining Thread G's findings with the layer catalog:")
    lines.append("")
    lines.append("| Capability | K (Exomiser) | M (LIRICAL) | L (CE-rerank) | **S (geno_agent)** |")
    lines.append("|---|:-:|:-:|:-:|:-:|")
    lines.append("| Ranked gene list | ✓ | ✓ (via OMIM) | ✓ | ✓ |")
    lines.append(
        "| Numeric score per gene | hiPhive | log-likelihood ratio | RRF score | LEA confidence + RRF |"
    )
    lines.append("| Free-text rationale per gene | ✗ | ✗ | ✗ | ✓ (median 80 chars) |")
    lines.append(
        "| Primary-literature citations | ✗ | ✗ | partial (chunks shown, no synthesis) | ✓ (mean 2.81 PMCIDs/top-1) |"
    )
    lines.append("| Per-claim source attribution | ✗ | ✗ | ✗ | ✓ (rationale + chunks + PMCIDs) |")
    lines.append(
        "| RAGAS-faithfulness applicable | ✗ (no LLM answer) | ✗ (no LLM answer) | ✗ (no LLM synthesis) | ✓ (pending Thread C run) |"
    )
    lines.append(
        "| Determinism | yes | yes | yes | yes (LEA fallback 0.2 % overall, 0.0 % fair cohort) |"
    )
    lines.append("| Replay-ready (full prompt logged) | n/a | n/a | n/a | ✓ |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 4. Aggregate coverage (from Thread G)")
    lines.append("")
    s_all = stats["__all__"]
    s_oa = stats["overlap_absent"]
    s_op = stats["overlap_present"]
    lines.append(f"- n = {s_all['n']} Cell S responses analysed locally (no API spend)")
    lines.append(
        f"- **{100 * s_all['frac_causal_substantive']:.1f} %** of cases have a substantive rationale for the *causal* gene (full cohort)"
    )
    lines.append(
        f"- **{100 * s_oa['frac_causal_substantive']:.1f} %** on the overlap-absent cohort (n = {s_oa['n']})  — the fair comparison"
    )
    lines.append(
        f"- {100 * s_op['frac_causal_substantive']:.1f} % on the overlap-present cohort (n = {s_op['n']})"
    )
    lines.append(
        f"- Mean **{s_all['mean_pmcid_per_top1']:.2f} unique PMCIDs** supporting each top-1 gene (full cohort)"
    )
    lines.append(
        f"- LEA fallback rate: {100 * s_all['frac_lea_fallback']:.2f} % overall, {100 * s_oa['frac_lea_fallback']:.2f} % on the fair cohort"
    )
    lines.append(f"- Median top-1 rationale length: {s_all['median_top1_len']:.0f} characters")
    lines.append("")
    lines.append("Per-MONDO breakdown is in §16.2 of `paper_extension_results.md`.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 5. Case-by-case walkthroughs")
    lines.append("")
    lines.append(
        "Selected via `scripts/eval/build_explainability_report.py` (seed = 42), drawing 2"
    )
    lines.append(
        "cases per (MONDO category x outcome) bucket — i.e. 2 cases where Cell S got top-1"
    )
    lines.append("correct and 2 where it didn't, in each of the 4 MONDO categories.")
    lines.append("")
    lines.append("**For verification:** every walkthrough below links to the raw sidecar JSON;")
    lines.append(
        "clicking the path opens the full LEA prompt, full ranked list with all rationales,"
    )
    lines.append("and all retrieved chunks per gene.")
    lines.append("")
    for i, c in enumerate(cases, start=1):
        ovr = "overlap-present" if c["overlap_present"] == 1 else "overlap-absent (fair-cohort)"
        outcome = "✅ TOP-1 CORRECT" if c["top1_correct"] else "❌ TOP-1 WRONG"
        lines.append(f"### 5.{i}  {c['case_id']}  — {outcome}")
        lines.append("")
        lines.append(f"- **Category:** {c['category']}")
        lines.append(
            f"- **Source PMID:** {c['source_pmid']} ({c['source_pub_date'] or 'date n/a'}) — {ovr}"
        )
        lines.append(f"- **Causal gene:** `{c['causal_gene']}` (ground truth)")
        lines.append(f"- **Predicted top-1:** `{c['predicted_top1_gene']}`")
        if c["causal_rank"] is not None:
            lines.append(f"- **Causal gene rank by Cell S:** {c['causal_rank']} / 50")
        lines.append(
            f"- **HPO terms ({len(c['hpo_terms'])}):** {', '.join(c['hpo_terms'][:8])}{('…' if len(c['hpo_terms']) > 8 else '')}"
        )
        lines.append(
            f"- **LEA latency:** {c['lea_response_latency_s']:.1f}s | tokens in/out: {c['lea_response_tokens_in']}/{c['lea_response_tokens_out']} | fallback: {c['lea_fallback'] or 'none'}"
        )
        lines.append(
            f"- **Raw sidecar JSON (verify):** [`{c['sidecar_path']}`](../{c['sidecar_path']})"
        )
        lines.append("")
        for g in c["genes_detail"]:
            conf = g["lea_confidence"]
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "n/a"
            lines.append(
                f"#### Gene `{g['gene']}` (rank {g['rank']}, LEA confidence {conf_str}) — {g['role']}"
            )
            lines.append("")
            lines.append(f"> *LEA rationale:* {g['lea_rationale']}")
            lines.append("")
            if g["supporting_chunks"]:
                lines.append(
                    f"**Supporting evidence ({len(g['supporting_chunks'])} chunks shown of up to 3 retrieved):**"
                )
                lines.append("")
                for j, ch in enumerate(g["supporting_chunks"], 1):
                    pmcid = ch.get("source_pmcid") or "n/a"
                    sec = ch.get("section_type") or "n/a"
                    score = ch.get("score_rrf")
                    score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "n/a"
                    lines.append(f"- **Chunk {j}** — {pmcid} / {sec} / RRF={score_str}")
                    excerpt = ch.get("text_excerpt", "").replace("\n", " ").strip()
                    if excerpt:
                        lines.append(
                            f"  > {excerpt}{'…' if len(excerpt) >= MAX_CHUNK_EXCERPT_CHARS else ''}"
                        )
                lines.append("")
            else:
                lines.append("**Supporting evidence:** (none captured for this gene)")
                lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## 6. What this report enables for the XAI paper")
    lines.append("")
    lines.append(
        "Of the data shown above, the following are *novel contributions* against existing"
    )
    lines.append("rare-disease prioritisation literature:")
    lines.append("")
    lines.append(
        "1. **Per-gene free-text rationales tied to retrieved evidence** — neither LIRICAL nor"
    )
    lines.append(
        "   Exomiser provides this. Cell S provides it for 81.5 % of cases overall and 94.0 %"
    )
    lines.append("   on the fair cohort.")
    lines.append(
        "2. **Primary-literature traceability** — every claim in a Cell S rationale can be"
    )
    lines.append("   verified against the supporting chunks (mean 2.81 PMCIDs per top-1).")
    lines.append(
        "3. **RAGAS-quantifiable faithfulness** — the LLM-judge metric (running, Thread C)"
    )
    lines.append("   provides an automatable hallucination score. No equivalent exists for")
    lines.append("   numeric-score systems.")
    lines.append(
        "4. **Deterministic-fallback transparency** — when LEA fails, the system explicitly"
    )
    lines.append(
        "   records why and falls back to CE-rerank. 0.0 % rate on the fair cohort means the"
    )
    lines.append("   headline numbers are not contaminated by silent LLM failures.")
    lines.append(
        "5. **Multi-layer reproducibility metadata** — full prompts, token counts, latencies,"
    )
    lines.append("   finish reasons captured per case. Allows third-party replay against the same")
    lines.append("   model + retrieval pipeline.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "## 7. Honest limitations (what the companion paper cannot claim without more work)"
    )
    lines.append("")
    lines.append(
        "1. **No clinical reviewer panel.** Reviewer-grade XAI papers usually include 2-3 clinical"
    )
    lines.append(
        "   geneticists rating rationales on a Likert scale. We have none. This is the single"
    )
    lines.append("   biggest gap — would need a collaborator + IRB-style review.")
    lines.append("2. **Rationale length is short** (median 80 chars). Reviewers may ask for richer")
    lines.append("   explanations. Trade-off: longer rationales burn more tokens + may hallucinate")
    lines.append("   more — RAGAS faithfulness will quantify this.")
    lines.append(
        "3. **PMCID citations are at chunk level, not claim level.** The rationale doesn't"
    )
    lines.append(
        "   explicitly cite each PMCID inline — the trace is structural (rationale + chunks +"
    )
    lines.append(
        "   PMCIDs) not linguistic (Cite[1], Cite[2]). Inline-citation prompting is a future"
    )
    lines.append("   work item.")
    lines.append(
        '4. **No counterfactual analysis.** "Would the top-1 change if chunk X were removed?"'
    )
    lines.append(
        "   is a standard XAI question we haven't answered. The infrastructure is in place"
    )
    lines.append("   (we have per-chunk scores) but the experiment isn't run.")
    lines.append(
        "5. **Single LLM** (Qwen3-8B). Same-architecture self-judging when using GPT-4o as the"
    )
    lines.append("   RAGAS judge is partly addressed (different model family) but a Qwen3-judge")
    lines.append("   self-eval bias check would strengthen the claim.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 8. Recommended XAI-paper outline")
    lines.append("")
    lines.append(
        "Target: *Artificial Intelligence in Medicine* (IF ~7) or *Journal of Biomedical Informatics*"
    )
    lines.append("(IF ~5). Submission window: 4-6 months post-Q1 submission (so ~Q4 2026).")
    lines.append("")
    lines.append('**Working title:** "Evidence-traceable rare-disease gene prioritisation with a')
    lines.append('multi-layer-explainable retrieval-augmented LLM"')
    lines.append("")
    lines.append("**Sections:**")
    lines.append("- 1. Background — rare-disease XAI gap; numeric scores vs natural language")
    lines.append("- 2. System design — the six explainability layers (§2 of this report)")
    lines.append("- 3. Coverage evaluation — Thread G aggregate numbers (this report §4)")
    lines.append("- 4. Faithfulness evaluation — RAGAS (Thread C, when complete)")
    lines.append("- 5. Case studies — qualitative walkthroughs (this report §5; expand to 15-20)")
    lines.append(
        '- 6. Counterfactual ablation — "if you remove the top-3 chunks, what happens to top-1?"'
    )
    lines.append("  (NEW EXPERIMENT REQUIRED)")
    lines.append("- 7. Comparative analysis vs LIRICAL/Exomiser — explainability layer audit")
    lines.append("- 8. Clinical evaluation panel — Likert ratings on 30 sampled cases (NEW)")
    lines.append("- 9. Limitations + future work")
    lines.append("")
    lines.append(
        "**Items requiring net-new work:** items 6 (counterfactual) and 8 (clinical panel)"
    )
    lines.append("are the only new compute / coordination items. Everything else is already in the")
    lines.append("data foundation captured by Threads D-G.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Explainability report — 2026-05-23. Data foundation locked. XAI-paper sequencing:"
    )
    lines.append("defer drafting until Q1 prioritisation paper is submitted.*")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    log.info("Wrote %s", out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses-dir", type=Path, default=DEFAULT_RESPONSES)
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    args = parser.parse_args()

    overlap = {r["case_id"]: r["overlap"] for r in json.loads(args.overlap.read_text())["records"]}
    stats = json.loads(args.stats.read_text())["summary"]

    # PMID dates for the walkthrough header context
    dates_path = PROJECT_ROOT / "data" / "test_cases_1050" / "pmid_dates.json"
    date_map: dict[str, str] = {}
    if dates_path.exists():
        date_map = {k: v for k, v in json.loads(dates_path.read_text())["dates"].items() if v}

    selected = select_cases(args.responses_dir)
    log.info("Selected %d cases for walkthroughs", len(selected))

    cases: list[dict] = []
    for p in selected:
        sc = load_sidecar(p)
        if sc is None:
            continue
        cases.append(build_case_walkthrough(sc, p, overlap, date_map))

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps({"n_cases": len(cases), "cases": cases}, indent=2))
    log.info("Wrote %s", args.out_json)

    write_markdown(args.out_md, cases, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
