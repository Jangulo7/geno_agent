"""Critic agent (master plan §11.1).

The third node in the LangGraph state graph. Grades each retrieved chunk
on three dimensions:

  1. ``gene_mention_valid`` — does the chunk text mention the candidate
     gene by symbol or HGNC alias?
  2. ``relevance`` — ordinal 1-5 capturing phenotype-gene association
     strength in this specific chunk.
  3. ``evidence_type`` — case_report / functional / association / review /
     unknown, derived from section type + keyword heuristics.

This module ships a **deterministic, no-LLM implementation** that scores
chunks via lexical co-occurrence and section heuristics. It produces
useful relevance labels for offline evaluation and the demo path.

An LLM-driven variant (Qwen3-8B reasoning over chunk+HPO+gene) can
replace ``grade_chunk`` later. The :class:`CriticGrade` schema and the
node interface stay stable.
"""

from __future__ import annotations

import logging
import re
from itertools import pairwise

import pronto

from src.agents.state import AgentState, CriticGrade, EvidenceType, RetrievedChunk
from src.tools.hgnc import HgncIndex, canonicalize
from src.tools.hpo import lookup_term

logger = logging.getLogger(__name__)

# Co-occurrence window: how close gene + HPO label must appear (in chars).
NEAR_WINDOW_CHARS: int = 200

# Keyword cues for evidence-type classification.
_FUNCTIONAL_CUES = re.compile(
    r"\b(luciferase|knockout|knock-out|knock out|"
    r"transfection|over-?express|protein expression|"
    r"in vitro|in vivo|cell line|"
    r"functional (analysis|study|assay)|"
    r"loss[-\s]of[-\s]function|gain[-\s]of[-\s]function)\b",
    re.IGNORECASE,
)
_CASE_CUES = re.compile(
    r"\b(patient|proband|family|case (report|series|presentation)|"
    r"index case|clinical (presentation|history))\b",
    re.IGNORECASE,
)
_ASSOCIATION_CUES = re.compile(
    r"\b(case[-\s]control|cohort|gwas|odds ratio|"
    r"OR\s*=\s*\d|p\s*[<=]\s*0\.|95%\s*CI|"
    r"meta[-\s]analysis|allele frequency)\b",
    re.IGNORECASE,
)
_REVIEW_CUES = re.compile(
    r"\b(review of|literature review|summarized|previous(ly)? reported|"
    r"comprehensive review|systematic review)\b",
    re.IGNORECASE,
)


def _hpo_labels_for_state(state: AgentState, ontology: pronto.Ontology) -> list[str]:
    """Resolve the patient's (preferably expanded) HPO IDs to display labels."""
    source_ids = state.expanded_hpo or state.hpo_terms
    labels: list[str] = []
    for hpo_id in source_ids:
        term = lookup_term(hpo_id, ontology)
        if term is not None and term.name:
            labels.append(term.name)
    return labels


def grade_gene_mention(chunk: RetrievedChunk, gene: str, hgnc: HgncIndex) -> bool:
    """Return True if the chunk text mentions the gene (canonical or alias).

    Iterates over HGNC's alias map, building the set of recognized symbols
    that point at ``gene``, then checks chunk text for any of them
    (case-insensitive, word-boundary).

    Args:
        chunk: One retrieved chunk.
        gene: Canonical HGNC gene symbol under review.
        hgnc: Loaded HGNC index.

    Returns:
        True iff the chunk text contains the gene symbol or any of its
        HGNC-recognized aliases as a whole token.
    """
    canonical = canonicalize(gene, hgnc)
    if canonical is None:
        return False

    # Build the set of accepted spellings: canonical symbol + any aliases
    # that point back to it. Word-boundary regex avoids matching within
    # other words (e.g., "BRCA1" in "BRCA1A" or vice-versa).
    accepted: set[str] = {canonical}
    for alias, target in hgnc.alias_to_symbol.items():
        if target == canonical:
            accepted.add(alias)

    text = chunk.text
    for spelling in accepted:
        pattern = rf"\b{re.escape(spelling)}\b"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def grade_relevance(chunk: RetrievedChunk, gene_in_chunk: bool, hpo_labels: list[str]) -> int:
    """Score phenotype-gene association strength on a 1-5 ordinal scale.

    The deterministic heuristic looks at:
      * Whether the gene was found in the chunk (boolean from
        ``grade_gene_mention``).
      * How many of the patient's HPO labels appear in the chunk text.
      * Whether at least one HPO label co-occurs with the gene within
        a NEAR_WINDOW_CHARS-character window (suggests direct association).

    Score table:
      * 5 — gene + ≥2 HPO labels with at least one near-window co-occurrence
      * 4 — gene + ≥1 HPO label (any distance)
      * 3 — gene mentioned, no HPO labels
      * 2 — HPO labels present but no gene mention
      * 1 — neither

    Args:
        chunk: The retrieved chunk.
        gene_in_chunk: Output of :func:`grade_gene_mention`.
        hpo_labels: Patient HPO labels (display names, English).

    Returns:
        Integer 1-5.
    """
    text = chunk.text
    text_lower = text.lower()
    matched_labels = [label for label in hpo_labels if label.lower() in text_lower]

    if gene_in_chunk and len(matched_labels) >= 2:
        if _has_near_cooccurrence(text, "", matched_labels, gene_in_chunk=True):
            return 5
        return 4
    if gene_in_chunk and len(matched_labels) >= 1:
        return 4
    if gene_in_chunk:
        return 3
    if matched_labels:
        return 2
    return 1


def _has_near_cooccurrence(
    text: str, _gene: str, hpo_labels: list[str], *, gene_in_chunk: bool
) -> bool:
    """Return True if any HPO label appears within ``NEAR_WINDOW_CHARS`` of any other label.

    This is a coarse proxy for "the chunk discusses gene + phenotype together"
    when the gene mention is already known to be present. Iterates over
    pairs of label positions in the text.
    """
    if not gene_in_chunk:
        return False
    text_lower = text.lower()
    positions: list[int] = []
    for label in hpo_labels:
        idx = text_lower.find(label.lower())
        if idx >= 0:
            positions.append(idx)
    positions.sort()
    return any(b - a <= NEAR_WINDOW_CHARS for a, b in pairwise(positions))


def classify_evidence_type(chunk: RetrievedChunk) -> EvidenceType:
    """Categorize the chunk by section type + keyword cues.

    Decision priority (first match wins):
      1. Section type ``"case"`` -> ``case_report``
      2. Functional cue regex hit -> ``functional``
      3. Association cue regex hit -> ``association``
      4. Section ``"introduction"`` + review cue -> ``review``
      5. Case cue regex hit -> ``case_report``
      6. Otherwise -> ``unknown``
    """
    text = chunk.text
    if chunk.section_type == "case":
        return "case_report"
    if _FUNCTIONAL_CUES.search(text):
        return "functional"
    if _ASSOCIATION_CUES.search(text):
        return "association"
    if chunk.section_type == "introduction" and _REVIEW_CUES.search(text):
        return "review"
    if _CASE_CUES.search(text):
        return "case_report"
    return "unknown"


def _build_rationale(
    gene: str,
    gene_in_chunk: bool,
    matched_labels: list[str],
    relevance: int,
    evidence_type: EvidenceType,
) -> str:
    """One-line human-readable Critic justification for the UI."""
    parts: list[str] = []
    if gene_in_chunk:
        parts.append(f"{gene} mentioned")
    else:
        parts.append(f"{gene} NOT mentioned")
    if matched_labels:
        n = len(matched_labels)
        sample = ", ".join(matched_labels[:3])
        suffix = "…" if n > 3 else ""
        parts.append(f"{n} HPO label{'s' if n != 1 else ''} matched ({sample}{suffix})")
    else:
        parts.append("no HPO labels matched")
    parts.append(f"relevance={relevance}")
    parts.append(f"evidence={evidence_type}")
    return "; ".join(parts)


def grade_chunk(
    chunk: RetrievedChunk,
    gene: str,
    hpo_labels: list[str],
    hgnc: HgncIndex,
) -> CriticGrade:
    """Produce a complete :class:`CriticGrade` for one chunk.

    Args:
        chunk: Retrieved chunk to grade.
        gene: Canonical HGNC symbol under review.
        hpo_labels: Patient's HPO display names.
        hgnc: Loaded HGNC index.

    Returns:
        :class:`CriticGrade` with all four fields populated.
    """
    gene_in_chunk = grade_gene_mention(chunk, gene, hgnc)
    relevance = grade_relevance(chunk, gene_in_chunk, hpo_labels)
    evidence_type = classify_evidence_type(chunk)
    text_lower = chunk.text.lower()
    matched_labels = [lbl for lbl in hpo_labels if lbl.lower() in text_lower]
    rationale = _build_rationale(gene, gene_in_chunk, matched_labels, relevance, evidence_type)
    return CriticGrade(
        chunk_id=chunk.chunk_id,
        gene_mention_valid=gene_in_chunk,
        relevance=relevance,
        evidence_type=evidence_type,
        rationale=rationale,
    )


def critic_node(
    state: AgentState,
    hpo_ontology: pronto.Ontology,
    hgnc: HgncIndex,
) -> AgentState:
    """LangGraph node: grade every retrieved chunk per gene; populate ``state.grades``.

    Args:
        state: Agent state with ``state.retrieved`` populated by C4.
        hpo_ontology: Loaded HPO ontology, used to resolve label strings.
        hgnc: Loaded HGNC index for gene-mention validation.

    Returns:
        Same state, mutated. ``state.grades`` is keyed by gene symbol; each
        list parallels ``state.retrieved[gene]`` element-wise.
    """
    hpo_labels = _hpo_labels_for_state(state, hpo_ontology)

    n_chunks_total = 0
    n_low_confidence = 0
    for gene, chunks in state.retrieved.items():
        grades: list[CriticGrade] = []
        for chunk in chunks:
            grade = grade_chunk(chunk, gene, hpo_labels, hgnc)
            grades.append(grade)
            if grade.relevance <= 2:
                n_low_confidence += 1
        state.grades[gene] = grades
        n_chunks_total += len(grades)

    logger.info(
        "Critic: %d genes / %d chunks graded; %d low-confidence (<=2). iteration=%d/%d",
        len(state.retrieved),
        n_chunks_total,
        n_low_confidence,
        state.iteration,
        state.max_iterations,
    )
    return state
