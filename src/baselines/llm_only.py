"""LLM-only (no-retrieval) baseline — Cell O.

A control that isolates the joint contribution of retrieval **and** the agentic
workflow. It asks the *same* locally-served Qwen3-8B that Cell S uses to rank a
case's candidate genes using ONLY the model's parametric knowledge — no PMC
retrieval, no Critic grading, no evidence chunks. Every other input is identical
to the other cells (the patient's HPO phenotypes + the 50-gene candidate list),
and the output matches the schema consumed by ``scripts/eval/aggregate_metrics.py``::

    [{"symbol", "is_causal", "aggregate_confidence", "supporting_chunks": [],
      "final_rank"}, ...]

Design (mirrors the LEA synthesiser for a fair paired comparison):
  * ``temperature=0.0`` + a ``/no_think`` prompt prefix (deterministic decoding).
  * The prompt gives the LLM the same HPO *labels* Cell S's LEA sees, and the
    candidate genes in their per-case seed-shuffled order.
  * **Free-form generation + robust extraction.** The model is asked for a JSON
    array of gene symbols in ranked order (most-likely first); confidence is then
    derived from rank position. Parsing is tolerant (:func:`_parse_ranking`):
    strict JSON when the output is well-formed, else the candidate symbols are
    recovered from the raw text in order of appearance. This preserves a partial
    ranking when a verbose response is truncated, instead of losing the case.
    Grammar-constrained (guided) decoding was evaluated and *rejected*: at
    ``temperature=0`` it distorted the model's behaviour on hard cases (collapsing
    to an empty array or repeat-padding), so it is not a neutral measurement of the
    model's parametric ranking ability.
  * Only a response with **no** recoverable candidate gene falls back to the
    **input candidate order**. Because that order is per-case seed-shuffled
    (``18_build_candidate_lists.py``), the fallback carries no positional signal
    about the causal gene — it degrades to chance rather than leaking the answer.
    Genes the model omits are likewise appended in input order. Both are logged.

No new dependencies: reuses ``src.tools.llm`` (the openai->vLLM client) exactly
as Cell S does, so running this baseline needs only the vLLM server already used
for the headline system.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Final

from src.tools.llm import LlmConfig, generate

logger = logging.getLogger(__name__)

# Cap HPO labels fed into the prompt (matches the LEA synthesiser's _PROMPT_HPO_CAP).
_PROMPT_HPO_CAP: Final[int] = 12

# A ranked JSON array of ~50 bare gene symbols is only a few hundred tokens; 4096
# is generous headroom. A rare verbose response may still truncate — the tolerant
# parser recovers the ranked prefix rather than discarding the case.
_MAX_OUTPUT_TOKENS: Final[int] = 4096

# Token used to pull candidate symbols out of a non-JSON / truncated response.
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9\-]+")

SYSTEM_PROMPT: Final[str] = (
    "/no_think\n"
    "You are a clinical genomics expert ranking candidate causal genes for a "
    "patient. You are given the patient's HPO phenotypes and a list of candidate "
    "genes. Using ONLY your own knowledge of gene-disease associations (NO external "
    "evidence is provided), rank the genes from MOST to LEAST likely to be the "
    "single causal gene for this phenotype profile.\n\n"
    "Output a single JSON ARRAY of the gene symbols (strings) in ranked order, most "
    "likely first. Use each candidate symbol exactly as provided, include EVERY "
    "candidate gene exactly once, and output nothing else — no confidence scores, no "
    'rationale, no markdown, no prose. Example shape: ["GENEA", "GENEB", ...].'
)


def _build_prompt(hpo_labels: list[str], candidate_genes: list[str]) -> str:
    """Compose the user prompt: phenotypes + candidate genes, no evidence."""
    labels_str = ", ".join(hpo_labels[:_PROMPT_HPO_CAP]) or "(no HPO labels)"
    return "\n".join(
        [
            "Patient HPO phenotypes:",
            labels_str,
            "",
            f"Candidate genes to rank ({len(candidate_genes)}):",
            ", ".join(candidate_genes),
            "",
            "Rank ALL candidate genes above from most to least likely, using only "
            "your own knowledge. Return a JSON array of the gene symbols only.",
        ]
    )


def _strip_fences(text: str) -> str:
    """Drop surrounding markdown code fences, if any."""
    t = text.strip()
    for fence in ("```json", "```"):
        if t.startswith(fence):
            t = t[len(fence) :].strip()
    if t.endswith("```"):
        t = t[:-3].strip()
    return t


def _parse_ranking(text: str, valid_genes: set[str]) -> list[str] | None:
    """Recover an ordered list of candidate gene symbols from the model's reply.

    Two-stage, tolerant of the two ways a small model degrades this task:
      1. **Strict JSON** — if the reply is a well-formed JSON list, take its string
         elements in order (the common, clean path).
      2. **Regex recovery** — otherwise (e.g. a verbose reply truncated mid-array),
         scan the raw text and take candidate symbols in order of appearance. This
         salvages the ranked prefix instead of dropping the whole case.

    In both stages unknown / duplicate symbols are ignored (first occurrence wins,
    order preserved). Returns ``None`` only when *no* candidate symbol is present
    (the caller then falls back to signal-free input order).
    """
    stripped = _strip_fences(text)
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    ordered: list[str] = []
    seen: set[str] = set()
    if isinstance(parsed, list):
        for gene in parsed:
            if isinstance(gene, str) and gene in valid_genes and gene not in seen:
                seen.add(gene)
                ordered.append(gene)
        if ordered:
            return ordered

    # Fallback: recover symbols from the raw text (handles truncated / non-JSON).
    for match in _TOKEN_RE.finditer(stripped):
        gene = match.group(0)
        if gene in valid_genes and gene not in seen:
            seen.add(gene)
            ordered.append(gene)
    return ordered or None


def _payload_from_order(
    ordered_genes: list[str],
    causal_gene: str,
    confidences: dict[str, float],
) -> list[dict]:
    """Build the aggregator-format payload from a ranked gene ordering."""
    return [
        {
            "symbol": gene,
            "is_causal": gene == causal_gene,
            "aggregate_confidence": round(confidences.get(gene, 0.0), 4),
            "supporting_chunks": [],
            "final_rank": rank,
        }
        for rank, gene in enumerate(ordered_genes, start=1)
    ]


def rank_llm_only(
    case: dict,
    *,
    hpo_labels: list[str],
    llm_cfg: LlmConfig | None = None,
) -> list[dict]:
    """Rank a case's candidate genes with the LLM alone (no retrieval).

    Args:
        case: A test case with ``candidate_genes`` (50 symbols, seed-shuffled)
            and ``causal_gene``.
        hpo_labels: Patient HPO display names (resolved by the caller from the
            HPO ontology, exactly as Cell S's LEA does).
        llm_cfg: Optional LLM server config; defaults to the local vLLM.

    Returns:
        A ranked payload list in ``aggregate_metrics`` schema. On any LLM or
        parse failure, genes are returned in their input (seed-shuffled) order.
    """
    candidate_genes: list[str] = list(case["candidate_genes"])
    causal_gene: str = case["causal_gene"]
    valid = set(candidate_genes)
    case_id = case.get("case_id", "?")

    try:
        response = generate(
            _build_prompt(hpo_labels, candidate_genes),
            cfg=llm_cfg,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:  # LLM connection/timeout/etc. — never crash the run
        logger.warning(
            "Cell O %s: LLM call failed (%s), falling back to input order",
            case_id,
            type(e).__name__,
        )
        return _payload_from_order(candidate_genes, causal_gene, {})

    ranked = _parse_ranking(response.text, valid)
    if ranked is None:
        logger.warning("Cell O %s: no recoverable ranking, falling back to input order", case_id)
        return _payload_from_order(candidate_genes, causal_gene, {})

    # The LLM's ordering is the ranking. Any candidate the model omitted is
    # appended in its original (seed-shuffled) input order — a stable, signal-free
    # tiebreak that carries no positional cue about the causal gene.
    ranked_set = set(ranked)
    ordered = ranked + [g for g in candidate_genes if g not in ranked_set]

    # Positional confidence for the aggregate_metrics schema: monotonically
    # decreasing over the model's ranked genes (rank 1 -> ~1.0). Omitted genes get
    # 0.0, so a case's nonzero-confidence count still reports how many the model
    # actually ranked. Ordering — the only thing the top-1/MRR metrics use — comes
    # from ``ordered``, not from these values.
    n = len(candidate_genes)
    confidences = {gene: round((n - i) / n, 4) for i, gene in enumerate(ranked)}

    n_ranked = len(ranked)
    if n_ranked < n:
        logger.info(
            "Cell O %s: LLM ranked %d/%d genes; rest appended in input order",
            case_id,
            n_ranked,
            n,
        )
    return _payload_from_order(ordered, causal_gene, confidences)
