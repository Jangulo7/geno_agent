"""HGNC gene-symbol validation helpers used by the Critic agent.

The Critic agent (master plan §11.1) inspects each retrieved chunk and
decides whether the chunk genuinely mentions the candidate gene under
review. Many gene symbols have HGNC-recognized aliases (e.g., ``HER2``
for ``ERBB2``); the Critic uses these helpers to look up canonical
symbols and validate that an alias resolves to the candidate.

The HGNC TSV is loaded once per process and reduced to two indexes:
``symbol → row`` and ``alias → symbol``. Both are pure-Python dicts
suitable for O(1) lookups inside agent inner loops.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class HgncEntry:
    """One row of HGNC's protein-coding subset, projected to the fields we use."""

    hgnc_id: str
    symbol: str
    name: str
    locus_group: str


class HgncIndex(NamedTuple):
    """Two-way HGNC lookup: canonical symbols + alias → canonical map."""

    by_symbol: dict[str, HgncEntry]
    alias_to_symbol: dict[str, str]


@lru_cache(maxsize=2)
def load_hgnc(tsv_path: Path) -> HgncIndex:
    """Load the HGNC TSV and return both lookups, cached per process.

    Args:
        tsv_path: Path to ``hgnc_complete_set.txt`` (TSV).

    Returns:
        :class:`HgncIndex` containing:
          * ``by_symbol``: dict from canonical symbol to :class:`HgncEntry`.
          * ``alias_to_symbol``: dict from ``alias_symbol`` and ``prev_symbol``
            entries to the canonical symbol they map to.

    Raises:
        FileNotFoundError: If ``tsv_path`` does not exist.
    """
    if not tsv_path.exists():
        raise FileNotFoundError(f"HGNC TSV not found: {tsv_path}")
    logger.info(f"Loading HGNC from {tsv_path}")
    df = pd.read_csv(tsv_path, sep="\t", low_memory=False)
    pc = df[df["locus_group"] == "protein-coding gene"]

    by_symbol: dict[str, HgncEntry] = {}
    alias_to_symbol: dict[str, str] = {}

    for _, row in pc.iterrows():
        symbol = row["symbol"]
        if not isinstance(symbol, str):
            continue
        entry = HgncEntry(
            hgnc_id=str(row.get("hgnc_id", "")),
            symbol=symbol,
            name=str(row.get("name", "")),
            locus_group=str(row.get("locus_group", "")),
        )
        by_symbol[symbol] = entry
        # Aliases & previous symbols are pipe-separated strings.
        for col in ("alias_symbol", "prev_symbol"):
            raw = row.get(col)
            if not isinstance(raw, str):
                continue
            for alias in raw.split("|"):
                alias = alias.strip()
                if alias and alias not in by_symbol:
                    alias_to_symbol.setdefault(alias, symbol)

    logger.info(
        f"  HGNC index: {len(by_symbol):,} canonical symbols, "
        f"{len(alias_to_symbol):,} alias mappings"
    )
    return HgncIndex(by_symbol=by_symbol, alias_to_symbol=alias_to_symbol)


def is_canonical_symbol(symbol: str, index: HgncIndex) -> bool:
    """Return True iff ``symbol`` is a canonical HGNC protein-coding symbol."""
    return symbol in index.by_symbol


def canonicalize(symbol: str, index: HgncIndex) -> str | None:
    """Resolve a symbol or alias to its canonical HGNC symbol.

    Args:
        symbol: Either a canonical symbol or a known alias / previous symbol.
        index: HGNC index from :func:`load_hgnc`.

    Returns:
        The canonical symbol if found, otherwise ``None``. Canonical symbols
        round-trip to themselves.
    """
    if symbol in index.by_symbol:
        return symbol
    return index.alias_to_symbol.get(symbol)


def hgnc_validate(symbol: str, index: HgncIndex) -> bool:
    """Return True iff ``symbol`` resolves to ANY canonical HGNC entry.

    This is the Critic agent's first-line check on chunk text — does the
    chunk mention something HGNC recognizes, even via alias?
    """
    return canonicalize(symbol, index) is not None
