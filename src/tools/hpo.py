"""HPO ontology helpers used by the Query Planner agent.

The Query Planner expands patient HPO terms by walking the HPO graph —
adding parent terms (more general) and synonyms — to broaden retrieval
queries. This module wraps `pronto` with a tiny façade so the agent
code stays free of pronto-specific types.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pronto

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class HpoTerm:
    """One HPO term, projected to the fields agents consume."""

    id: str
    name: str
    synonyms: tuple[str, ...]
    parents: tuple[str, ...]


@lru_cache(maxsize=2)
def load_hpo(obo_path: Path) -> pronto.Ontology:
    """Load and cache the HPO ontology from a `.obo` file.

    Args:
        obo_path: Path to ``hp.obo``.

    Returns:
        Parsed :class:`pronto.Ontology` ready for traversal.

    Raises:
        FileNotFoundError: If ``obo_path`` does not exist.
    """
    if not obo_path.exists():
        raise FileNotFoundError(f"HPO obo not found: {obo_path}")
    logger.info(f"Loading HPO from {obo_path}")
    return pronto.Ontology(str(obo_path))


def lookup_term(hpo_id: str, ontology: pronto.Ontology) -> HpoTerm | None:
    """Look up a single HPO term by ID and return a slim record.

    Args:
        hpo_id: HPO identifier (e.g. ``"HP:0001250"``).
        ontology: Loaded HPO ontology.

    Returns:
        :class:`HpoTerm` with id, name, synonyms, immediate parents, or
        ``None`` if the term is not found / obsolete.
    """
    term = ontology.get(hpo_id)
    if not isinstance(term, pronto.Term):
        return None
    parents = tuple(p.id for p in term.superclasses(distance=1, with_self=False) if p.id != hpo_id)
    synonyms = tuple(s.description for s in term.synonyms if s.description)
    return HpoTerm(id=term.id, name=term.name or "", synonyms=synonyms, parents=parents)


def hpo_expand(hpo_id: str, ontology: pronto.Ontology, distance: int = 2) -> list[str]:
    """Return the closure of HPO IDs within ``distance`` ancestors of ``hpo_id``.

    Used by the Query Planner to broaden a patient's specific HPO term to
    its more general parents, increasing retrieval recall. Always includes
    the input ``hpo_id`` itself.

    Args:
        hpo_id: Starting HPO identifier.
        ontology: Loaded HPO ontology.
        distance: How many parent edges to walk (default 2 per master plan §11.1).

    Returns:
        Deduplicated list of HPO IDs (input + ancestors) preserving traversal
        order. Empty list if ``hpo_id`` not found.
    """
    term = ontology.get(hpo_id)
    if not isinstance(term, pronto.Term):
        return []
    ancestors: list[str] = []
    seen: set[str] = set()
    for ancestor in term.superclasses(distance=distance, with_self=True):
        if ancestor.id not in seen and ancestor.id.startswith("HP:"):
            seen.add(ancestor.id)
            ancestors.append(ancestor.id)
    return ancestors


def expand_many(hpo_ids: list[str], ontology: pronto.Ontology, distance: int = 2) -> list[str]:
    """Expand a list of HPO IDs and return the deduplicated union.

    Order follows first-seen traversal — within each input term the
    parents come immediately after the term itself. Useful for the
    Query Planner's HPO expansion pass over a patient's full term list.
    """
    out: list[str] = []
    seen: set[str] = set()
    for hpo_id in hpo_ids:
        for ancestor in hpo_expand(hpo_id, ontology, distance):
            if ancestor not in seen:
                seen.add(ancestor)
                out.append(ancestor)
    return out
