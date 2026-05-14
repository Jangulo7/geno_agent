"""LLM-prompted Critic variant (master plan §11.1, C7c).

Replaces ``src.agents.critic.grade_chunk`` with a Qwen3-8B-prompted
version that reads the chunk text and produces a :class:`CriticGrade`
(gene_mention_valid + relevance 1-5 + evidence_type + rationale).
Interface-compatible drop-in: same
``(chunk, gene, hpo_labels, hgnc) -> CriticGrade`` signature.

Design notes:
  * **Thinking mode ON.** Qwen3 has native ``<think>...</think>`` support
    and our vLLM startup script (PR #30) passes ``--reasoning-parser qwen3``
    so the thinking tokens land in ``response.reasoning_content`` and are
    kept out of the JSON ``content`` field. The Critic's job — does this
    chunk substantively support a gene->phenotype claim, and what kind of
    evidence is it? — is exactly the reasoning-heavy operation that
    benefits from thinking.
  * **Cross-check against deterministic gene-mention regex.** The LLM is
    allowed to set ``gene_mention_valid=True`` even when the deterministic
    regex would say False, but only if the LLM's response includes the
    gene symbol literally. This catches a class of hallucinations where
    the model insists the chunk talks about the gene despite the symbol
    being absent.
  * **JSON-structured response** with the same four fields as
    :class:`CriticGrade`. Malformed JSON or any field mismatch -> fall
    back to the deterministic ``grade_chunk`` (logged).
  * **Determinism**: ``temperature=0.0``. Same caveat as the Planner:
    near-identical but not byte-identical across runs.
"""

from __future__ import annotations

import logging
from typing import Final, get_args

from src.agents.critic import (
    _hpo_labels_for_state,
    grade_gene_mention,
)
from src.agents.critic import (
    grade_chunk as _deterministic_grade_chunk,
)
from src.agents.state import CriticGrade, EvidenceType, RetrievedChunk
from src.tools.hgnc import HgncIndex
from src.tools.llm import LlmConfig, generate_json

logger = logging.getLogger(__name__)

# Max output tokens INCLUDING the Qwen3 thinking trace. vLLM with
# --reasoning-parser qwen3 puts thinking in response.raw[…].reasoning
# (NOT in content), but the thinking still counts against max_tokens.
# A typical Critic thinking pass is ~400-600 tokens; the JSON answer
# adds ~120; 1024 gives generous headroom.
_MAX_OUTPUT_TOKENS: Final[int] = 1024

# Cap chunk text fed into the prompt. Most chunks are < 512 tokens already;
# this is a defensive cap to avoid prompt overflow on outlier long chunks.
_CHUNK_TEXT_CAP_CHARS: Final[int] = 2400

# Cap on HPO labels included in the prompt (defensive, matches the
# deterministic critic's label-handling assumption).
_PROMPT_HPO_CAP: Final[int] = 12

# Allowed evidence-type values (sourced from EvidenceType Literal).
_ALLOWED_EVIDENCE_TYPES: Final[frozenset[str]] = frozenset(get_args(EvidenceType))


SYSTEM_PROMPT: Final[str] = (
    "/no_think\n"
    "You grade a single literature chunk for whether it supports an association "
    "between a specific gene and a patient's phenotype profile. "
    "Output a single JSON object with exactly these keys:\n"
    '  "gene_mention_valid" (bool): true ONLY if the gene symbol or an officially '
    "recognized alias appears literally in the chunk text.\n"
    '  "relevance" (int 1-5): 1 = irrelevant; 2 = tangentially mentions phenotype '
    "or gene but not both; 3 = mentions both but no causal claim; "
    "4 = phenotype-gene association stated; 5 = strong direct causal evidence "
    "(e.g. mutation type, mechanism, or case demonstrating gene->phenotype).\n"
    '  "evidence_type" (string): one of "case_report", "functional", '
    '"association", "review", "unknown".\n'
    '  "rationale" (string, ≤180 chars): a one-sentence reason for the grade.\n'
    "No prose outside the JSON object. No markdown, no code fences."
)


def _build_prompt(chunk: RetrievedChunk, gene: str, hpo_labels: list[str]) -> str:
    """Compose the user-side prompt for one (chunk, gene, hpo) triple."""
    text = (chunk.text or "")[:_CHUNK_TEXT_CAP_CHARS]
    labels_str = ", ".join(hpo_labels[:_PROMPT_HPO_CAP]) or "(no HPO labels)"
    return (
        f"Gene under review: {gene}\n"
        f"Patient HPO phenotypes: {labels_str}\n"
        f"Section type: {chunk.section_type}\n\n"
        f"Chunk text:\n{text}\n\n"
        "Grade this chunk. Return JSON only."
    )


def _validate_and_coerce(parsed: object, chunk_id: str) -> CriticGrade | None:
    """Validate the LLM JSON response and convert to CriticGrade.

    Returns None if any required field is missing / wrong type / out of
    range. Caller handles fallback to deterministic on None.
    """
    if not isinstance(parsed, dict):
        return None
    try:
        gene_mention_valid = bool(parsed["gene_mention_valid"])
        relevance = int(parsed["relevance"])
        evidence_type = str(parsed["evidence_type"]).lower().strip()
        rationale = str(parsed.get("rationale", "")).strip()
    except (KeyError, ValueError, TypeError):
        return None

    if relevance < 1 or relevance > 5:
        return None
    if evidence_type not in _ALLOWED_EVIDENCE_TYPES:
        # The LLM occasionally invents adjacent types like "clinical" or
        # "mechanistic". Soft-coerce to the closest allowed value
        # rather than discard the whole grade.
        mapping = {
            "clinical": "case_report",
            "mechanistic": "functional",
            "in vitro": "functional",
            "study": "association",
            "meta-analysis": "review",
        }
        evidence_type = mapping.get(evidence_type, "unknown")

    return CriticGrade(
        chunk_id=chunk_id,
        gene_mention_valid=gene_mention_valid,
        relevance=relevance,
        evidence_type=evidence_type,  # type: ignore[arg-type]
        rationale=rationale[:200],
    )


def grade_chunk_llm(
    chunk: RetrievedChunk,
    gene: str,
    hpo_labels: list[str],
    hgnc: HgncIndex,
    *,
    llm_cfg: LlmConfig | None = None,
    enable_thinking: bool = True,
) -> CriticGrade:
    """LLM-prompted replacement for :func:`grade_chunk`.

    Falls back to the deterministic grader on any LLM / parsing failure.
    The fallback path uses the same ``hgnc`` index that the deterministic
    Critic node uses, so the interface is fully drop-in.

    Args:
        chunk: Retrieved chunk to grade.
        gene: Canonical HGNC gene symbol.
        hpo_labels: Patient HPO display names.
        hgnc: HGNC index — used by the deterministic fallback AND for a
            sanity check on the LLM's ``gene_mention_valid`` claim
            (rejects LLM=True when neither the canonical symbol nor any
            HGNC alias appears literally in the text).
        llm_cfg: Optional LLM server config. Defaults to local vLLM.
        enable_thinking: Pass through to the LLM (currently unused at the
            HTTP level — vLLM handles thinking via its global flag set in
            ``scripts/eval/start_vllm.sh``). Kept as a parameter so the
            caller can audit intent.

    Returns:
        :class:`CriticGrade`.
    """
    user_prompt = _build_prompt(chunk, gene, hpo_labels)
    try:
        parsed, response = generate_json(
            user_prompt,
            cfg=llm_cfg,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:
        logger.warning(
            "LLM Critic failed for chunk %s (gene %s, error %s); "
            "falling back to deterministic grader",
            chunk.chunk_id,
            gene,
            e.__class__.__name__,
        )
        return _deterministic_grade_chunk(chunk, gene, hpo_labels, hgnc)

    grade = _validate_and_coerce(parsed, chunk.chunk_id)
    if grade is None:
        logger.warning(
            "LLM Critic returned malformed JSON for chunk %s (gene %s); "
            "falling back to deterministic",
            chunk.chunk_id,
            gene,
        )
        return _deterministic_grade_chunk(chunk, gene, hpo_labels, hgnc)

    # Sanity check: gene_mention_valid=True must be supportable by the chunk text.
    # Defends against the failure mode where the model fabricates a mention.
    # Reuse the deterministic gene-mention check (regex over canonical + aliases)
    # so the override semantics match the rest of the codebase.
    if grade.gene_mention_valid and not grade_gene_mention(chunk, gene, hgnc):
        grade.gene_mention_valid = False
        note = " [override: no literal symbol/alias in text]"
        grade.rationale = (grade.rationale + note)[:200]

    # Audit: log thinking trace at DEBUG if vLLM exposed it via raw payload.
    # vLLM's --reasoning-parser qwen3 surfaces thinking as message.reasoning.
    reasoning = (response.raw or {}).get("choices", [{}])[0].get("message", {}).get("reasoning")
    if reasoning:
        logger.debug(
            "Critic thinking for chunk=%s gene=%s: %s",
            chunk.chunk_id,
            gene,
            reasoning[:300],
        )
    return grade


# Default chunks-per-LLM-call for the batched grader. With thinking ON,
# Qwen3-8B does its reasoning once over the whole batch and then emits N
# JSON entries, which is much faster than N independent calls. Empirically
# 10 chunks/call lands around 5-8 sec/call -> ~6 min per 75-gene case.
_DEFAULT_BATCH_SIZE: Final[int] = 10

BATCH_SYSTEM_PROMPT: Final[str] = (
    "/no_think\n"
    "You grade a BATCH of literature chunks for a specific gene/phenotype profile. "
    "For each chunk in the input, produce one JSON object with these keys:\n"
    '  "chunk_idx" (int): the chunk index from the input (0-based).\n'
    '  "gene_mention_valid" (bool): true ONLY if the gene symbol or alias appears literally.\n'
    '  "relevance" (int 1-5): 1=irrelevant; 5=strong direct causal evidence.\n'
    '  "evidence_type" (string): one of "case_report", "functional", "association", "review", "unknown".\n'
    '  "rationale" (string, <=180 chars): one sentence per chunk.\n\n'
    "Output a single JSON ARRAY containing one object per input chunk, "
    "in the SAME ORDER as the input. No prose outside the array, no markdown."
)


def _build_batch_prompt(chunks: list[RetrievedChunk], gene: str, hpo_labels: list[str]) -> str:
    """Compose a batched user prompt for a list of chunks under one gene."""
    labels_str = ", ".join(hpo_labels[:_PROMPT_HPO_CAP]) or "(no HPO labels)"
    lines = [
        f"Gene under review: {gene}",
        f"Patient HPO phenotypes: {labels_str}",
        f"Number of chunks: {len(chunks)}",
        "",
        "Chunks:",
    ]
    for i, ch in enumerate(chunks):
        text = (ch.text or "")[:_CHUNK_TEXT_CAP_CHARS]
        lines.append(f"\n[chunk_idx={i}] section={ch.section_type}")
        lines.append(text)
    lines.append("\nGrade every chunk. Return a JSON array of {len(chunks)} objects.")
    return "\n".join(lines)


def grade_chunks_llm_batched(
    chunks: list[RetrievedChunk],
    gene: str,
    hpo_labels: list[str],
    hgnc: HgncIndex,
    *,
    llm_cfg: LlmConfig | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> list[CriticGrade]:
    """Grade ``chunks`` in batches via the LLM; preserve input order.

    Falls back per-chunk to the deterministic grader on malformed batch
    output (logged). Returns ``[CriticGrade]`` aligned 1:1 with input.
    """
    out: list[CriticGrade | None] = [None] * len(chunks)
    # Slice into batches of size ``batch_size``.
    for start in range(0, len(chunks), batch_size):
        sub = chunks[start : start + batch_size]
        # Thinking budget grows with batch size (Qwen3 reasons over more
        # chunks). Empirically at batch=10 thinking can hit 2000+ tokens.
        # Set a fat budget so JSON output fits AFTER thinking. vLLM's
        # max_model_len=8192 caps the total; we leave ~1000 for the prompt.
        budget = 1500 + 250 * len(sub)
        prompt = _build_batch_prompt(sub, gene, hpo_labels)
        try:
            parsed, _resp = generate_json(
                prompt,
                cfg=llm_cfg,
                system_prompt=BATCH_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=budget,
            )
        except Exception as e:
            logger.warning(
                "LLM Critic batch failed for gene %s (start=%d, n=%d, error %s); "
                "falling back to deterministic for this batch",
                gene,
                start,
                len(sub),
                e.__class__.__name__,
            )
            for i, ch in enumerate(sub):
                out[start + i] = _deterministic_grade_chunk(ch, gene, hpo_labels, hgnc)
            continue

        if not isinstance(parsed, list):
            logger.warning(
                "LLM Critic batch returned non-list for gene %s start=%d "
                "(got %s); falling back deterministic",
                gene,
                start,
                type(parsed).__name__,
            )
            for i, ch in enumerate(sub):
                out[start + i] = _deterministic_grade_chunk(ch, gene, hpo_labels, hgnc)
            continue

        # Index responses by chunk_idx for robustness to model reordering.
        by_idx: dict[int, dict] = {}
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("chunk_idx", -1))
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(sub):
                by_idx[idx] = entry

        for i, ch in enumerate(sub):
            entry = by_idx.get(i)
            grade = _validate_and_coerce(entry, ch.chunk_id) if entry is not None else None
            if grade is None:
                # This chunk's slot was missing or malformed; deterministic fallback.
                out[start + i] = _deterministic_grade_chunk(ch, gene, hpo_labels, hgnc)
            else:
                # Sanity check on gene_mention_valid, same as single-chunk path.
                if grade.gene_mention_valid and not grade_gene_mention(ch, gene, hgnc):
                    grade.gene_mention_valid = False
                    note = " [override: no literal symbol/alias in text]"
                    grade.rationale = (grade.rationale + note)[:200]
                out[start + i] = grade

    # By construction every slot is filled (real or fallback) — assert + cast.
    assert all(g is not None for g in out), "LLM Critic produced an unfilled slot"
    return [g for g in out if g is not None]


def critic_node_llm(
    state,
    hpo_ontology,
    hgnc: HgncIndex,
    *,
    llm_cfg: LlmConfig | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
):
    """LangGraph node: LLM-prompted Critic, BATCHED for throughput.

    Identical control flow to ``critic.critic_node`` but uses
    :func:`grade_chunks_llm_batched` so we make ~1 LLM call per
    ``batch_size`` chunks instead of one call per chunk. Thinking
    happens once per batch and then the model emits N JSON entries.
    """
    hpo_labels = _hpo_labels_for_state(state, hpo_ontology)
    n_chunks_total = 0
    n_low_confidence = 0

    for gene, chunks in state.retrieved.items():
        grades = grade_chunks_llm_batched(
            chunks, gene, hpo_labels, hgnc, llm_cfg=llm_cfg, batch_size=batch_size
        )
        state.grades[gene] = grades
        n_chunks_total += len(grades)
        n_low_confidence += sum(1 for g in grades if g.relevance <= 2)

    logger.info(
        "Critic (LLM, batched=%d): %d genes / %d chunks graded; "
        "%d low-confidence (<=2). iteration=%d/%d",
        batch_size,
        len(state.retrieved),
        n_chunks_total,
        n_low_confidence,
        state.iteration,
        state.max_iterations,
    )
    return state
