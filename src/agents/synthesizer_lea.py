"""LLM-as-Evidence-Aggregator Synthesiser (master plan §11.9, cells Q/R).

Replaces :func:`src.agents.synthesizer.synthesizer_node` with a single
LLM call that reads chunks from the top-N candidate genes and produces
the full ranked output directly. Conceptually different from the
LLM-Critic ablation (cells G/H) -- which graded chunks in isolation --
because LEA gets the *full evidence corpus* and reasons across genes
in one pass.

Design notes (recorded for the thesis):

* **Pre-filter via the deterministic synth.** The factorial test cases
  have 50 candidate genes; feeding all 50 x 3 chunks = 75K tokens
  would not fit a 32K context. LEA uses the deterministic synth's
  preliminary ranking to pick the top-15 genes, then re-ranks only
  those. The other 35 genes keep their preliminary rank shifted to
  positions 16-50. This trades thoroughness for fit; in practice the
  causal gene is in the preliminary top-15 for 73 / 75 cases under
  Cell D's hybrid retrieval.

* **Why top-15 / top-3.** 15 genes x 3 chunks x ~500 tokens = ~22.5K
  tokens of evidence + ~2K system / patient HPO + ~1.5K JSON response
  = 26K total, well under vLLM's bumped 32 768 cap.

* **Critic stays in the pipeline.** LEA replaces *synth*, not Critic.
  Critic's per-chunk grades drive both the top-15 pre-filter and the
  top-3 chunks shown to LEA. This isolates LEA's contribution.

* **Thinking mode OFF** (``/no_think``) -- empirically the multi-gene
  aggregation prompt does not benefit from thinking, and we want
  budget headroom for the JSON response.

* **Determinism**: ``temperature=0.0``. Same caveat as the LLM Planner
  / Critic: near-identical but not byte-identical across runs.

The graph integration adds a ``use_lea_synthesiser: bool`` kwarg to
``build_graph`` mirroring the existing ``use_llm_planner`` /
``use_llm_critic`` flags.
"""

from __future__ import annotations

import logging
from typing import Final

from src.agents.state import AgentState, CriticGrade, GeneCandidate, RetrievedChunk
from src.agents.synthesizer import (
    chunk_contribution,
    rank_genes,
)
from src.tools.llm import LlmConfig, generate_json

logger = logging.getLogger(__name__)

# How many of the 50 candidate genes LEA sees full evidence for.
# Beyond this, the deterministic preliminary rank is preserved.
_DEFAULT_LEA_TOP_GENES: Final[int] = 15

# How many chunks per gene LEA sees.
_DEFAULT_LEA_CHUNKS_PER_GENE: Final[int] = 3

# Per-chunk text cap (chars) before assembling the prompt. Defensive
# truncation against outlier long chunks.
_CHUNK_TEXT_CAP_CHARS: Final[int] = 1600

# HPO label cap (matches Planner / Critic conventions).
_PROMPT_HPO_CAP: Final[int] = 12

# Max output tokens. The JSON response is one entry per top-N gene
# (gene + confidence + rationale, ~80 tokens each) plus structure.
# 15 entries x 80 + braces = 1300. Budget 1500 for headroom.
_MAX_OUTPUT_TOKENS: Final[int] = 1500


SYSTEM_PROMPT: Final[str] = (
    "/no_think\n"
    "You are a clinical genomics expert ranking candidate causal genes for a "
    "patient. You receive the patient's HPO phenotypes and, for each candidate "
    "gene, a small set of literature evidence chunks. Reason ACROSS the candidate "
    "genes: which one's evidence most directly supports it as the causal gene for "
    "this phenotype profile?\n\n"
    "Output a single JSON ARRAY, ordered by descending confidence. Each element "
    "must have exactly these keys:\n"
    '  "gene" (string): the HGNC gene symbol exactly as provided.\n'
    '  "confidence" (float 0.0-1.0): your belief this gene is the causal one.\n'
    '  "rationale" (string, <=180 chars): one-sentence justification.\n\n'
    "Only one gene is causal. Confidence values should reflect that -- the top "
    "entry should be substantially higher than the rest. Include EVERY input "
    "gene exactly once. Output only the JSON array, no markdown, no prose."
)


def _select_top_chunks_for_gene(
    chunks: list[RetrievedChunk],
    grades: list[CriticGrade],
    top_k: int,
) -> list[tuple[RetrievedChunk, CriticGrade]]:
    """Pick the top-``top_k`` (chunk, grade) pairs for one gene.

    Ordering is by Critic contribution score (relevance x evidence
    weight x mention multiplier). Falls back to Critic ``relevance``
    alone if the contribution math degenerates.
    """
    grade_by_id: dict[str, CriticGrade] = {g.chunk_id: g for g in grades}
    pairs = []
    for ch in chunks:
        g = grade_by_id.get(ch.chunk_id)
        if g is None:
            continue
        pairs.append((ch, g, chunk_contribution(g)))
    pairs.sort(key=lambda t: t[2], reverse=True)
    return [(ch, g) for ch, g, _ in pairs[:top_k]]


def _format_gene_block(
    gene: str,
    chunk_grade_pairs: list[tuple[RetrievedChunk, CriticGrade]],
) -> str:
    """Build the per-gene section of the LEA user prompt."""
    if not chunk_grade_pairs:
        return f"=== Gene: {gene} ===\n(no evidence chunks)\n"
    lines = [f"=== Gene: {gene} ==="]
    for i, (ch, g) in enumerate(chunk_grade_pairs, start=1):
        text = (ch.text or "")[:_CHUNK_TEXT_CAP_CHARS]
        lines.append(
            f"[chunk_{i}] section={ch.section_type} "
            f"mention={'yes' if g.gene_mention_valid else 'no'} "
            f"critic_relevance={g.relevance}/5"
        )
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _build_lea_prompt(
    hpo_labels: list[str],
    top_genes: list[str],
    evidence: dict[str, list[tuple[RetrievedChunk, CriticGrade]]],
) -> str:
    """Compose the LEA user prompt across all top-N genes."""
    labels_str = ", ".join(hpo_labels[:_PROMPT_HPO_CAP]) or "(no HPO labels)"
    sections = [
        "Patient HPO phenotypes:",
        labels_str,
        "",
        f"Candidate genes to rank ({len(top_genes)}):",
        ", ".join(top_genes),
        "",
        "Evidence per gene:",
        "",
    ]
    for gene in top_genes:
        sections.append(_format_gene_block(gene, evidence.get(gene, [])))
    sections.append(
        "Rank ALL candidate genes above by confidence (highest first). Return JSON only."
    )
    return "\n".join(sections)


def _parse_lea_response(
    parsed: object,
    valid_genes: set[str],
) -> dict[str, tuple[float, str]] | None:
    """Validate LEA's JSON response → ``{gene: (confidence, rationale)}``.

    Returns None if the response is malformed (caller falls back to the
    deterministic synth).
    """
    if not isinstance(parsed, list):
        return None
    out: dict[str, tuple[float, str]] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        gene = entry.get("gene")
        if not isinstance(gene, str) or gene not in valid_genes:
            continue
        try:
            conf = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        if not 0.0 <= conf <= 1.0:
            conf = max(0.0, min(1.0, conf))
        rationale = str(entry.get("rationale", ""))[:200]
        # First occurrence wins (LEA shouldn't repeat genes, but be defensive).
        out.setdefault(gene, (conf, rationale))
    return out or None


def lea_synthesizer_node(
    state: AgentState,
    hpo_ontology=None,
    *,
    llm_cfg: LlmConfig | None = None,
    top_genes: int = _DEFAULT_LEA_TOP_GENES,
    chunks_per_gene: int = _DEFAULT_LEA_CHUNKS_PER_GENE,
) -> AgentState:
    """LangGraph node: LEA-driven synthesiser.

    Replaces :func:`synthesizer_node`. Pre-filters genes via the
    deterministic preliminary rank, then makes one LLM call that
    re-ranks the top-``top_genes`` across all their evidence.

    Args:
        state: Agent state populated by Critic.
        hpo_ontology: Optional pronto ontology for HPO label lookup. Pass
            ``None`` to use raw HPO IDs in the prompt.
        llm_cfg: Optional LLM server config; defaults to local vLLM.
        top_genes: How many genes LEA re-ranks. Default 15.
        chunks_per_gene: Chunks shown per gene. Default 3.

    Returns:
        Same state, with ``state.ranked`` populated.
    """
    # Preliminary deterministic ranking (uses Critic grades).
    preliminary = rank_genes(state)

    if not preliminary:
        state.ranked = []
        logger.warning("LEA synthesiser: no candidate genes to rank")
        return state

    # The first `top_genes` enter the LEA prompt; the rest keep their
    # preliminary rank shifted to positions (top_genes+1)..N.
    head = preliminary[:top_genes]
    tail = preliminary[top_genes:]

    # Build the per-gene evidence dict.
    evidence: dict[str, list[tuple[RetrievedChunk, CriticGrade]]] = {}
    for cand in head:
        chunks = state.retrieved.get(cand.symbol, [])
        grades = state.grades.get(cand.symbol, [])
        evidence[cand.symbol] = _select_top_chunks_for_gene(chunks, grades, top_k=chunks_per_gene)

    # HPO labels -- fall back to raw IDs when no ontology provided.
    if hpo_ontology is not None:
        from src.agents.critic import _hpo_labels_for_state

        hpo_labels = _hpo_labels_for_state(state, hpo_ontology)
    else:
        hpo_labels = list(state.hpo_terms)

    top_gene_symbols = [c.symbol for c in head]
    user_prompt = _build_lea_prompt(hpo_labels, top_gene_symbols, evidence)

    # Persist a per-case sidecar log for RAGAS/DeepEval evaluation. Attached
    # via setattr because AgentState is a frozen dataclass; consumed by
    # scripts/eval/rerank_inside_d.py to write data/eval_*/cell_S_responses/.
    # When the LEA call fails or returns invalid JSON, the log records the
    # failure mode so faithfulness/hallucination metrics can mark these cases
    # as deterministic-synth fallbacks (their LEA response is N/A).
    log_payload: dict = {
        "lea_system_prompt": SYSTEM_PROMPT,
        "lea_user_prompt": user_prompt,
        "lea_top_gene_symbols": list(top_gene_symbols),
        "hpo_labels": list(hpo_labels),
        "lea_evidence_per_gene": {
            g: [
                {
                    "chunk_id": getattr(ch, "chunk_id", None),
                    "text": (ch.text or "")[:2000],
                    "source_pmcid": getattr(ch, "pmcid", None),
                    "section_type": getattr(ch, "section_type", None),
                    "score_dense": getattr(ch, "score_dense", None),
                    "score_bm25": getattr(ch, "score_bm25", None),
                    "score_rrf": getattr(ch, "score_rrf", None),
                }
                for (ch, _grade) in pairs
            ]
            for g, pairs in evidence.items()
        },
        "lea_response_raw": None,
        "lea_response_parsed": None,
        "lea_fallback_reason": None,
    }
    object.__setattr__(state, "lea_log", log_payload)

    try:
        parsed, response_obj = generate_json(
            user_prompt,
            cfg=llm_cfg,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
        # response_obj is an LlmResponse dataclass — pull serialisable fields
        log_payload["lea_response_raw"] = getattr(response_obj, "text", None)
        log_payload["lea_response_tokens_in"] = getattr(response_obj, "tokens_in", None)
        log_payload["lea_response_tokens_out"] = getattr(response_obj, "tokens_out", None)
        log_payload["lea_response_finish_reason"] = getattr(response_obj, "finish_reason", None)
        log_payload["lea_response_latency_s"] = getattr(response_obj, "latency_s", None)
        log_payload["lea_response_parsed"] = parsed
    except Exception as e:
        logger.warning(
            "LEA LLM call failed (%s); falling back to deterministic synth",
            type(e).__name__,
        )
        log_payload["lea_fallback_reason"] = f"llm_call_failed:{type(e).__name__}"
        state.ranked = preliminary
        return state

    lea_scores = _parse_lea_response(parsed, set(top_gene_symbols))
    if lea_scores is None:
        logger.warning("LEA JSON response invalid; falling back to deterministic synth")
        log_payload["lea_fallback_reason"] = "json_response_invalid"
        state.ranked = preliminary
        return state

    # Build the head ranking from LEA's confidences.
    head_ranked: list[GeneCandidate] = []
    seen: set[str] = set()
    # Iterate genes by LEA confidence (descending). For genes LEA didn't
    # score (shouldn't happen, but be defensive), fall back to the
    # preliminary order.
    lea_sorted = sorted(((g, *lea_scores[g]) for g in lea_scores), key=lambda t: -t[1])
    head_by_symbol: dict[str, GeneCandidate] = {c.symbol: c for c in head}
    for gene, conf, _rationale in lea_sorted:
        if gene not in head_by_symbol:
            continue
        c = head_by_symbol[gene]
        head_ranked.append(
            GeneCandidate(
                symbol=c.symbol,
                is_causal=c.is_causal,
                aggregate_confidence=conf,
                supporting_chunks=c.supporting_chunks,
                final_rank=0,  # re-assigned below
            )
        )
        seen.add(gene)

    # Defensive: any head gene LEA didn't score -- append in preliminary order.
    for cand in head:
        if cand.symbol not in seen:
            head_ranked.append(cand)

    # Concatenate head + tail; re-assign final_rank.
    final_ranked: list[GeneCandidate] = head_ranked + tail
    for i, cand in enumerate(final_ranked, start=1):
        # Mutate in place via dataclass replace pattern.
        object.__setattr__(cand, "final_rank", i)

    state.ranked = final_ranked

    if final_ranked:
        top = final_ranked[0]
        logger.info(
            "LEA synthesiser: ranked %d genes (LEA re-ranked %d head); top=%s (conf=%.3f)",
            len(final_ranked),
            len(head_ranked),
            top.symbol,
            top.aggregate_confidence,
        )
    return state
