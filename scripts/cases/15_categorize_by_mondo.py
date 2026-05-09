"""Assign each eligible case to one of four disease categories via MONDO.

Implements master plan §6 step 3 (Phase 1B / §7 step [11]). Loads MONDO
once, computes the descendant set for each category root, then bins each
case by checking whether any of its ``mondo_ids`` falls under any
category's descendant set. Cases matching multiple categories are
resolved by **fixed priority order**:

    neurological > metabolic > immunological > developmental

This deterministic resolution is required by methodology §4.2.1 and is
recorded in each case as ``category_resolution`` for full audit traceability.

Category roots (master plan §6 step 3):
  * **neurological**   ``MONDO:0005071`` (nervous system disorder)
  * **metabolic**      ``MONDO:0005066`` (metabolic disease)
  * **immunological**  ``MONDO:0005046`` (immune system disorder)
  * **developmental**  ``MONDO:0021147`` (inborn genetic disease)
                       + ``MONDO:0019118`` (developmental and epileptic
                       encephalopathy) — broad bucket of inborn genetic
                       diseases not in the other three categories.

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/15_categorize_by_mondo.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Final

import pronto
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("categorize_mondo")

# Order matters: priority resolution per master plan §10.
CATEGORY_ROOTS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("neurological",  ("MONDO:0005071",)),
    ("metabolic",     ("MONDO:0005066",)),
    ("immunological", ("MONDO:0005046",)),
    ("developmental", ("MONDO:0021147", "MONDO:0019118")),
)


def descendants(mondo: pronto.Ontology, root_ids: tuple[str, ...]) -> set[str]:
    """Return the closure of MONDO IDs under any of the given roots.

    Args:
        mondo: Loaded MONDO ontology.
        root_ids: Tuple of MONDO root IDs.

    Returns:
        Set including the roots themselves and all of their subclasses.
        Missing roots emit a WARNING and contribute nothing.
    """
    out: set[str] = set()
    for rid in root_ids:
        root = mondo.get(rid)
        if root is None:
            logger.warning(f"MONDO root {rid} not found in ontology")
            continue
        for term in root.subclasses(with_self=True):
            out.add(term.id)
    return out


def assign_category(
    mondo_ids: list[str],
    category_sets: list[tuple[str, set[str]]],
) -> tuple[str | None, list[str]]:
    """Resolve a case's category via first-match priority order.

    Args:
        mondo_ids: MONDO IDs from the case (resolved by B3).
        category_sets: Ordered list of ``(name, descendant_set)`` pairs.

    Returns:
        ``(category_name, all_matching)`` — ``category_name`` is the
        first category whose descendant set intersects ``mondo_ids``;
        ``all_matching`` is the full list of matched categories (used
        for the audit trail when more than one matches).
    """
    case_ids = set(mondo_ids)
    matched: list[str] = []
    for name, descendant_set in category_sets:
        if case_ids & descendant_set:
            matched.append(name)
    return (matched[0] if matched else None), matched


def parse_args() -> argparse.Namespace:
    """CLI args."""
    tc_dir = os.environ.get("TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases"))
    onto_dir = os.environ.get("ONTOLOGY_DIR", str(PROJECT_ROOT / "data" / "ontologies"))
    p = argparse.ArgumentParser(description="MONDO-based disease categorization (Phase 1B step 3).")
    p.add_argument("--input", type=Path,
                   default=Path(tc_dir) / "02_eligible.jsonl")
    p.add_argument("--output", type=Path,
                   default=Path(tc_dir) / "03_categorized.jsonl")
    p.add_argument("--mondo-obo", type=Path,
                   default=Path(onto_dir) / "mondo" / "mondo.obo")
    return p.parse_args()


def main() -> int:
    """Read eligible JSONL, assign categories, write categorized JSONL."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        logger.error("Run 14_apply_inclusion_exclusion.py first.")
        return 1
    if not args.mondo_obo.exists():
        logger.error(f"MONDO obo not found: {args.mondo_obo}")
        return 1

    logger.info(f"Loading MONDO from {args.mondo_obo}")
    mondo = pronto.Ontology(str(args.mondo_obo))
    logger.info(f"  MONDO terms loaded: {sum(1 for _ in mondo.terms()):,}")

    category_sets: list[tuple[str, set[str]]] = []
    for name, roots in CATEGORY_ROOTS:
        s = descendants(mondo, roots)
        category_sets.append((name, s))
        logger.info(f"  category '{name}': {len(s):,} MONDO descendants")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {name: 0 for name, _ in CATEGORY_ROOTS}
    counts["unmatched"] = 0
    overlap_counts: dict[str, int] = {}  # comma-joined matched-list -> count
    n_in = n_out = 0

    n_total = sum(1 for _ in args.input.open("r", encoding="utf-8"))
    with args.input.open("r", encoding="utf-8") as fin, \
         args.output.open("w", encoding="utf-8") as fout:
        for line in tqdm(fin, total=n_total, desc="categorizing"):
            n_in += 1
            rec = json.loads(line)
            assigned, matched = assign_category(
                rec.get("mondo_ids", []), category_sets,
            )
            if assigned is None:
                counts["unmatched"] += 1
                continue
            rec["category"] = assigned
            rec["category_resolution"] = (
                f"priority-first; matched=[{','.join(matched)}]"
            )
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            counts[assigned] += 1
            overlap_counts[",".join(matched)] = (
                overlap_counts.get(",".join(matched), 0) + 1
            )
            n_out += 1

    logger.info("=== Categorization summary ===")
    logger.info(f"  input cases:      {n_in:,}")
    logger.info(f"  categorized:      {n_out:,} ({100*n_out/max(n_in,1):.1f}%)")
    logger.info(f"  unmatched dropped:{counts['unmatched']:,}")
    logger.info("  by category (after priority resolution):")
    for name, _ in CATEGORY_ROOTS:
        logger.info(f"    {name:14s} {counts[name]:,}")
    logger.info("  overlap groups (cases matching multiple categories):")
    multi = {k: v for k, v in overlap_counts.items() if "," in k}
    if not multi:
        logger.info("    (none — all cases matched exactly one category)")
    else:
        for k, v in sorted(multi.items(), key=lambda kv: -kv[1])[:10]:
            logger.info(f"    {k:40s} {v:,}")
    logger.info(f"  output:           {args.output}")

    return 0 if n_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
