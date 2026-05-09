"""Apply Phase 1B inclusion/exclusion criteria to ingested phenopackets.

Implements master plan §6 step 2 (Phase 1B / §7 step [10]) per
methodology §4.2.1.

Inclusion (all required):
  * >= ``MIN_HPO_TERMS`` (default 3) observed HPO terms.
  * Exactly one ascertained causal gene across all genomic interpretations.

Exclusion (any disqualifies):
  * Disease whose MONDO term is a descendant of ``MONDO:0019042``
    (chromosomal disorder).
  * Disease whose MONDO term is a descendant of ``MONDO:0044970``
    (mitochondrial disease).

Each retained record is augmented with two new fields:
  * ``causal_gene``  — the single gene symbol (HGNC-canonical preferred).
  * ``mondo_ids``    — list of MONDO IDs resolved from each disease entry
                       (via direct ID or OMIM/Orphanet xref).

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/14_apply_inclusion_exclusion.py
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inclusion_exclusion")

MIN_HPO_TERMS: Final[int] = int(os.environ.get("MIN_HPO_TERMS", "3"))
EXCLUDE_MONDO_ROOTS: Final[tuple[str, ...]] = (
    "MONDO:0019042",  # chromosomal disorder
    "MONDO:0044970",  # mitochondrial disease
)


def build_exclude_descendant_set(mondo: pronto.Ontology) -> set[str]:
    """Return every MONDO ID under any exclusion root (roots themselves included).

    Args:
        mondo: Loaded MONDO ontology.

    Returns:
        Set of MONDO IDs (strings). Missing roots emit a WARNING and are
        silently skipped — they cannot contribute descendants.
    """
    excluded: set[str] = set()
    for root_id in EXCLUDE_MONDO_ROOTS:
        root = mondo.get(root_id)
        if root is None:
            logger.warning(f"MONDO root {root_id} not found in ontology; check MONDO_VERSION.")
            continue
        for term in root.subclasses(with_self=True):
            excluded.add(term.id)
    return excluded


def build_xref_to_mondo_map(mondo: pronto.Ontology) -> dict[str, str]:
    """Build a once-per-process map ``OMIM/Orphanet/etc. ID -> MONDO ID``.

    Phenopackets often cite diseases via OMIM IDs (``OMIM:154700``).
    MONDO records cross-references back to those source vocabularies in
    each term's ``xref`` attribute. Inverting that index lets the filter
    resolve a disease ID to MONDO in O(1).

    Args:
        mondo: Loaded MONDO ontology.

    Returns:
        Dict mapping any ``xref`` ID to the MONDO ID that declares it.
        First-seen wins (``setdefault``); MONDO occasionally has multiple
        terms claiming the same xref but the first walk-order entry is
        deterministic.
    """
    out: dict[str, str] = {}
    for term in mondo.terms():
        for x in term.xrefs:
            out.setdefault(x.id, term.id)
    return out


def resolve_mondo_ids(diseases: list[dict], xref_map: dict[str, str]) -> list[str]:
    """Resolve every disease entry's ID to a MONDO ID where possible."""
    resolved: list[str] = []
    for d in diseases:
        did = d.get("id")
        if not did:
            continue
        if did.startswith("MONDO:"):
            resolved.append(did)
        else:
            mapped = xref_map.get(did)
            if mapped:
                resolved.append(mapped)
    return resolved


def passes_filters(
    rec: dict,
    excluded_ids: set[str],
    xref_map: dict[str, str],
) -> tuple[bool, str | None, str | None, list[str]]:
    """Apply inclusion/exclusion to one record.

    Args:
        rec: Phenopacket record from ``01_all_phenopackets.jsonl``.
        excluded_ids: MONDO descendants-of-roots set.
        xref_map: OMIM/Orphanet -> MONDO map.

    Returns:
        ``(ok, reason, causal_gene, mondo_ids)`` — ``reason`` is set only
        when ``ok`` is False, identifying which rule fired.
    """
    if len(rec.get("hpo_terms", [])) < MIN_HPO_TERMS:
        return False, "few_hpo", None, []

    asc = [
        g for g in rec.get("interpretations", []) if g.get("ascertained") and g.get("gene_symbol")
    ]
    unique_genes = {g["gene_symbol"] for g in asc}
    if len(unique_genes) == 0:
        return False, "no_single_gene", None, []
    if len(unique_genes) > 1:
        return False, "multi_gene", None, []
    causal_gene = next(iter(unique_genes))

    diseases = rec.get("diseases", [])
    if not diseases:
        return False, "no_disease", causal_gene, []

    mondo_ids = resolve_mondo_ids(diseases, xref_map)
    if any(m in excluded_ids for m in mondo_ids):
        return False, "excluded_disease", causal_gene, mondo_ids

    return True, None, causal_gene, mondo_ids


def parse_args() -> argparse.Namespace:
    """CLI args."""
    tc_dir = os.environ.get("TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases"))
    onto_dir = os.environ.get("ONTOLOGY_DIR", str(PROJECT_ROOT / "data" / "ontologies"))
    p = argparse.ArgumentParser(description="Phase 1B inclusion/exclusion filter.")
    p.add_argument("--input", type=Path, default=Path(tc_dir) / "01_all_phenopackets.jsonl")
    p.add_argument("--output", type=Path, default=Path(tc_dir) / "02_eligible.jsonl")
    p.add_argument("--mondo-obo", type=Path, default=Path(onto_dir) / "mondo" / "mondo.obo")
    return p.parse_args()


def main() -> int:
    """Read input JSONL, apply filters, write retained records as JSONL."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        logger.error("Run 13_load_phenopackets.py first.")
        return 1
    if not args.mondo_obo.exists():
        logger.error(f"MONDO obo not found: {args.mondo_obo}")
        return 1

    logger.info(f"Loading MONDO from {args.mondo_obo}")
    mondo = pronto.Ontology(str(args.mondo_obo))
    logger.info(f"  MONDO terms loaded: {sum(1 for _ in mondo.terms()):,}")

    excluded_ids = build_exclude_descendant_set(mondo)
    logger.info(
        f"  exclusion-root descendants: {len(excluded_ids):,} MONDO terms "
        f"(under {', '.join(EXCLUDE_MONDO_ROOTS)})"
    )

    xref_map = build_xref_to_mondo_map(mondo)
    logger.info(f"  xref index: {len(xref_map):,} (OMIM/Orphanet/... -> MONDO)")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_in = n_kept = 0
    drop_reasons = {
        "few_hpo": 0,
        "no_single_gene": 0,
        "multi_gene": 0,
        "no_disease": 0,
        "excluded_disease": 0,
    }

    n_total = sum(1 for _ in args.input.open("r", encoding="utf-8"))
    with (
        args.input.open("r", encoding="utf-8") as fin,
        args.output.open("w", encoding="utf-8") as fout,
    ):
        for line in tqdm(fin, total=n_total, desc="filtering"):
            n_in += 1
            rec = json.loads(line)
            ok, reason, causal_gene, mondo_ids = passes_filters(
                rec,
                excluded_ids,
                xref_map,
            )
            if not ok:
                drop_reasons[reason] += 1
                continue
            rec["causal_gene"] = causal_gene
            rec["mondo_ids"] = mondo_ids
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_kept += 1

    logger.info("=== Filter summary ===")
    logger.info(f"  input cases:    {n_in:,}")
    logger.info(f"  eligible cases: {n_kept:,} ({100 * n_kept / max(n_in, 1):.1f}%)")
    logger.info(f"  dropped:        {n_in - n_kept:,}")
    for reason, count in drop_reasons.items():
        logger.info(f"    {reason:18s} {count:,}")
    logger.info(f"  output:         {args.output}")

    return 0 if n_kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
