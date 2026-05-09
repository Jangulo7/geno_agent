"""Phase 1B acceptance gate — verifies the canonical test set is publish-ready.

Implements master plan §6 step 8 / §7 step [16] per methodology §4.11.5
(acceptance criteria 1B + 1C). Five independent checks, each
of which surfaces ALL failing cases (not just the first):

  1. Every case has ``>= MIN_HPO_TERMS`` (default 3) observed HPO terms.
  2. Every case has exactly ``N_DISTRACTORS + 1`` (default 50) UNIQUE
     candidate gene symbols.
  3. Every case's ``causal_gene`` appears in its ``candidate_genes``.
  4. Every case's causal gene has ``>= MIN_PMC_ARTICLES_PER_GENE``
     (default 5) PMC articles in the Phase 1A corpus. Gated by ``--skip-pmc``
     for development against pre-B6 outputs.
  5. Sample is balanced across the 4 MONDO categories — each category
     within ``CATEGORY_TOLERANCE`` (default 20 %) of the equal-share count.

Exit code:
  * ``0`` if all enabled checks pass.
  * ``1`` if any check fails.

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/20_validate_test_cases.py

For pre-B6 development (no PMC coverage data yet)::

    python scripts/cases/20_validate_test_cases.py --skip-pmc
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_test_cases")

CATEGORIES: Final[tuple[str, ...]] = (
    "neurological",
    "metabolic",
    "immunological",
    "developmental",
)
CATEGORY_TOLERANCE: Final[float] = 0.20  # within ±20% of equal share
MAX_FAILURES_TO_LOG: Final[int] = 50


def check_hpo_terms(case: dict, min_hpo: int) -> list[str]:
    """Verify the case has at least ``min_hpo`` observed HPO terms."""
    n = len(case.get("hpo_terms", []))
    if n < min_hpo:
        return [f"{case['case_id']}: only {n} HPO terms (need >= {min_hpo})"]
    return []


def check_candidate_count(case: dict, expected: int) -> list[str]:
    """Verify the candidate list has exactly ``expected`` unique gene symbols."""
    cands = case.get("candidate_genes", [])
    n_unique = len(set(cands))
    if n_unique != expected:
        return [f"{case['case_id']}: {n_unique} unique candidates (expected exactly {expected})"]
    return []


def check_causal_in_candidates(case: dict) -> list[str]:
    """Verify the causal gene is present in ``candidate_genes``."""
    causal = case.get("causal_gene")
    if causal is None:
        return [f"{case['case_id']}: missing causal_gene field"]
    if causal not in case.get("candidate_genes", []):
        return [f"{case['case_id']}: causal gene '{causal}' not in candidate_genes"]
    return []


def check_pmc_coverage(case: dict, min_pmc: int) -> list[str]:
    """Verify the causal gene has at least ``min_pmc`` PMC articles."""
    n = case.get("pmc_article_count")
    if n is None:
        return [
            f"{case['case_id']}: pmc_article_count is null (B6 must run first, or use --skip-pmc)"
        ]
    if n < min_pmc:
        return [f"{case['case_id']}: causal gene has only {n} PMC articles (need >= {min_pmc})"]
    return []


def check_category_balance(
    cases: list[dict], categories: tuple[str, ...], tolerance: float
) -> list[str]:
    """Verify each category's count is within ``tolerance`` of the equal share."""
    counts = Counter(c.get("category") for c in cases)
    expected = len(cases) / len(categories)
    tol_count = tolerance * expected
    failures: list[str] = []
    for cat in categories:
        actual = counts.get(cat, 0)
        if abs(actual - expected) > tol_count:
            failures.append(
                f"category '{cat}': {actual} cases (expected {expected:.0f} ± {tol_count:.0f})"
            )
    return failures


def run_all_checks(
    cases: list[dict],
    min_hpo: int,
    expected_candidates: int,
    min_pmc: int,
    skip_pmc: bool,
) -> list[str]:
    """Apply all per-case + corpus-wide checks; return aggregated failure list."""
    failures: list[str] = []
    for case in cases:
        failures.extend(check_hpo_terms(case, min_hpo))
        failures.extend(check_candidate_count(case, expected_candidates))
        failures.extend(check_causal_in_candidates(case))
        if not skip_pmc:
            failures.extend(check_pmc_coverage(case, min_pmc))
    failures.extend(check_category_balance(cases, CATEGORIES, CATEGORY_TOLERANCE))
    return failures


def parse_args() -> argparse.Namespace:
    """CLI args."""
    tc_dir = os.environ.get("TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases"))
    p = argparse.ArgumentParser(description="Phase 1B acceptance gate (master plan §6 step 8).")
    p.add_argument("--input", type=Path, default=Path(tc_dir) / "test_cases.jsonl")
    p.add_argument(
        "--skip-pmc",
        action="store_true",
        help=(
            "Downgrade the PMC coverage check to a warning. Use only for pre-B6 "
            "development against the demo collection; production gate must run "
            "without this flag."
        ),
    )
    p.add_argument(
        "--min-hpo-terms",
        type=int,
        default=int(os.environ.get("MIN_HPO_TERMS", "3")),
    )
    p.add_argument(
        "--min-pmc-articles",
        type=int,
        default=int(os.environ.get("MIN_PMC_ARTICLES_PER_GENE", "5")),
    )
    p.add_argument(
        "--n-distractors",
        type=int,
        default=int(os.environ.get("N_DISTRACTORS", "49")),
    )
    return p.parse_args()


def main() -> int:
    """Read canonical JSONL, run checks, return 0 if all pass else 1."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        logger.error("Run 19_finalize_test_cases.py (B8) first.")
        return 1

    cases = [json.loads(line) for line in args.input.open("r", encoding="utf-8")]
    expected_candidates = args.n_distractors + 1
    cat_counts = Counter(c.get("category") for c in cases)

    logger.info(f"Validating {len(cases):,} cases from {args.input}")
    logger.info(f"  category distribution: {dict(cat_counts)}")
    logger.info(
        f"  thresholds: min_hpo={args.min_hpo_terms}, "
        f"expected_candidates={expected_candidates}, "
        f"min_pmc={args.min_pmc_articles}, "
        f"category_tol=±{int(CATEGORY_TOLERANCE * 100)}%"
    )

    if args.skip_pmc:
        logger.warning(
            "--skip-pmc: PMC coverage check disabled. "
            "This is acceptable for pre-B6 development only."
        )

    failures = run_all_checks(
        cases,
        args.min_hpo_terms,
        expected_candidates,
        args.min_pmc_articles,
        args.skip_pmc,
    )

    if failures:
        logger.error(f"FAILED — {len(failures):,} issue(s):")
        for f in failures[:MAX_FAILURES_TO_LOG]:
            logger.error(f"  - {f}")
        if len(failures) > MAX_FAILURES_TO_LOG:
            logger.error(f"  ... and {len(failures) - MAX_FAILURES_TO_LOG} more")
        logger.error("STATUS: FAIL — Phase 1B test set is NOT ready for Phase 2.")
        return 1

    logger.info(f"STATUS: PASS — Phase 1B test set ({len(cases)} cases) ready for Phase 2.")
    if args.skip_pmc:
        logger.warning(
            "Reminder: production gate must rerun without --skip-pmc once "
            "the Phase 1A corpus is indexed and B6 has run."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
