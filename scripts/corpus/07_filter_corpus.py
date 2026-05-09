"""Filter parsed PMC articles for genetics / rare disease relevance.

Implements master plan §4 step 2. Reads the JSONL output of
``06_parse_jats_xml.py`` and retains articles that match at least one of:

  1. MeSH term in the genetics/rare-disease term whitelist;
  2. Keyword (``<kwd>``) in the same whitelist;
  3. Genetics-related regex match in the title or abstract.

The full Phase 1A run (§7 step [5c]) hard-asserts the retention count falls in
``[MIN_PMC_FILTERED, MAX_PMC_FILTERED]`` (default 100,000-600,000); outside
that range almost always indicates a regex regression. The demo path runs on
~100 pre-curated articles where ~100% retention is expected, so the assertion
is gated behind ``--strict`` and is skipped by default.

Run from project root::

    python scripts/corpus/07_filter_corpus.py --input  /mnt/c/pmc_workspace/parsed/demo.jsonl \\
                                              --output /mnt/c/pmc_workspace/filtered/demo.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Final

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
logger = logging.getLogger("filter_corpus")

# MeSH/keyword whitelist (case-insensitive substring match).
GENETICS_VOCAB: Final[frozenset[str]] = frozenset(
    s.lower() for s in (
        "genetics", "genetic", "genomics", "genomic", "genome",
        "mutation", "mutations", "variant", "variants",
        "rare disease", "rare diseases", "orphan disease",
        "mendelian", "monogenic", "hereditary",
        "phenotype", "genotype", "exome", "next-generation sequencing",
        "whole genome", "whole-genome", "whole exome", "whole-exome",
        "cystic fibrosis", "huntington", "marfan", "noonan", "digeorge",
        "rett syndrome", "phenylketonuria", "fabry", "niemann-pick",
        "agammaglobulinemia", "immunodeficiency", "duchenne",
        "charcot-marie-tooth", "muscular dystrophy",
    )
)

# Title/abstract genetics regex (MeSH-fallback for un-indexed recent articles).
TITLE_ABSTRACT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.I) for p in (
        r"\b(genetic|genomic|hereditary|mendelian|monogenic|inborn)\b",
        r"\b(mutation|variant|deletion|duplication|insertion|polymorphism)s?\b",
        r"\b(HPO|OMIM|Orphanet|GeneReviews|MONDO|HGNC|ClinVar)\b",
        r"\bphenotyp(e|ic)\b",
        r"\b(rare|orphan)\s+(disease|disorder|condition|syndrome)s?\b",
        r"\b(exome|genome|RNA-seq|transcriptome)\s+sequencing\b",
        r"\b(autosomal\s+(dominant|recessive)|X-linked)\b",
    )
)
DEFAULT_MIN_RETAINED: Final[int] = 100_000
DEFAULT_MAX_RETAINED: Final[int] = 600_000


def vocab_hit(strings: list[str]) -> bool:
    """Return True if any string in ``strings`` contains a vocab term."""
    for s in strings:
        if not s:
            continue
        s_low = s.lower()
        for term in GENETICS_VOCAB:
            if term in s_low:
                return True
    return False


def regex_hit(text: str) -> bool:
    """Return True if ``text`` matches any genetics title/abstract pattern."""
    if not text:
        return False
    return any(p.search(text) for p in TITLE_ABSTRACT_PATTERNS)


def is_relevant(record: dict) -> tuple[bool, list[str]]:
    """Decide whether a parsed article is genetics/rare-disease relevant.

    Args:
        record: One JSONL record produced by ``06_parse_jats_xml.py``.

    Returns:
        ``(passes, reasons)`` — ``passes`` is the boolean retention decision;
        ``reasons`` is the non-empty list of filter rules that fired,
        suitable for traceability and per-article audit.
    """
    reasons: list[str] = []
    if vocab_hit(record.get("mesh_terms", [])):
        reasons.append("mesh")
    if vocab_hit(record.get("keywords", [])):
        reasons.append("keyword")
    title_abs = (record.get("title") or "") + " " + (record.get("abstract") or "")
    if regex_hit(title_abs):
        reasons.append("title_abstract_regex")
    return bool(reasons), reasons


def parse_args() -> argparse.Namespace:
    """CLI argument parsing."""
    workspace = os.environ.get("PMC_WORKSPACE", "/mnt/c/pmc_workspace")
    p = argparse.ArgumentParser(description="Filter parsed JSONL for genetics relevance.")
    p.add_argument("--input", type=Path,
                   default=Path(workspace) / "parsed" / "demo.jsonl")
    p.add_argument("--output", type=Path,
                   default=Path(workspace) / "filtered" / "demo.jsonl")
    p.add_argument("--rejects", type=Path,
                   default=Path(workspace) / "filtered" / "demo_rejects.jsonl")
    p.add_argument("--strict", action="store_true",
                   help=f"Abort if retained count not in "
                        f"[{DEFAULT_MIN_RETAINED:,}, {DEFAULT_MAX_RETAINED:,}].")
    return p.parse_args()


def main() -> int:
    """Filter the input JSONL and write retained / rejected records."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.rejects.parent.mkdir(parents=True, exist_ok=True)

    n_total = sum(1 for _ in args.input.open("r", encoding="utf-8"))
    n_kept = n_drop = 0
    reasons_counter: dict[str, int] = {"mesh": 0, "keyword": 0, "title_abstract_regex": 0}

    with args.input.open("r", encoding="utf-8") as fin, \
         args.output.open("w", encoding="utf-8") as fout, \
         args.rejects.open("w", encoding="utf-8") as frej:
        for line in tqdm(fin, total=n_total, desc="filtering"):
            record = json.loads(line)
            ok, reasons = is_relevant(record)
            if ok:
                for r in reasons:
                    reasons_counter[r] += 1
                fout.write(json.dumps({**record, "_filter_reasons": reasons},
                                       ensure_ascii=False) + "\n")
                n_kept += 1
            else:
                frej.write(line)
                n_drop += 1

    pct = (n_kept / n_total * 100) if n_total else 0.0
    logger.info("=== Filter summary ===")
    logger.info(f"  total in:  {n_total:,}")
    logger.info(f"  retained:  {n_kept:,} ({pct:.1f}%)")
    logger.info(f"  rejected:  {n_drop:,}")
    logger.info(f"  rule hits: {reasons_counter}")
    logger.info(f"  output:    {args.output}")

    if args.strict and not (DEFAULT_MIN_RETAINED <= n_kept <= DEFAULT_MAX_RETAINED):
        logger.error(
            f"--strict: retained {n_kept:,} outside "
            f"[{DEFAULT_MIN_RETAINED:,}, {DEFAULT_MAX_RETAINED:,}]; aborting."
        )
        return 1
    return 0 if n_kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
