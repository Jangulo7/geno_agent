"""Stratified random sampling of categorized cases (Phase 1B step 4).

Implements master plan §6 step 4 / §7 step [12]. Reads the categorized
JSONL produced by ``15_categorize_by_mondo.py`` and emits a deterministic
``SAMPLE_TARGET_SIZE``-record sample (default 75) stratified equally across
the four disease categories.

Allocation strategy:
  * Within each category, sort by ``case_id`` for deterministic ordering.
  * ``ceil(SAMPLE_TARGET_SIZE / 4)`` per category, capped by availability.
  * If total over-shoots the target, shuffle and truncate to target size.

All randomness uses ``RANDOM_SEED`` (default 42) so the sample is
byte-identical across runs and machines.

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/16_stratified_sample.py
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("stratified_sample")

CATEGORIES: Final[tuple[str, ...]] = (
    "neurological",
    "metabolic",
    "immunological",
    "developmental",
)
SAMPLE_TARGET_SIZE: Final[int] = int(os.environ.get("SAMPLE_TARGET_SIZE", "75"))
RANDOM_SEED: Final[int] = int(os.environ.get("RANDOM_SEED", "42"))


def load_by_category(path: Path) -> dict[str, list[dict]]:
    """Load categorized JSONL and return cases grouped by category, sorted.

    Args:
        path: Path to the categorized JSONL file.

    Returns:
        Dict mapping category name to list of case records, sorted by
        ``case_id`` within each category for deterministic sampling.
    """
    by_cat: dict[str, list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            by_cat[rec["category"]].append(rec)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda r: r["case_id"])
    return dict(by_cat)


def sample_stratified(
    by_cat: dict[str, list[dict]],
    target: int,
    rng: random.Random,
) -> list[dict]:
    """Draw ``target`` cases stratified across CATEGORIES.

    Args:
        by_cat: Sorted by-category pool from :func:`load_by_category`.
        target: Total target sample size (e.g., 75).
        rng: Seeded ``random.Random`` instance for reproducibility.

    Returns:
        List of sampled case records (one record per element). Sorted
        deterministically by (category, case_id) for reviewability.
    """
    per_cat = math.ceil(target / len(CATEGORIES))
    out: list[dict] = []
    for cat in CATEGORIES:
        pool = by_cat.get(cat, [])
        n = min(per_cat, len(pool))
        chosen = rng.sample(pool, n)
        out.extend(chosen)
        logger.info(f"  sampled {n}/{len(pool)} from '{cat}'")

    # Trim to exact target if ceil() overshot
    if len(out) > target:
        rng.shuffle(out)
        out = out[:target]
        logger.info(f"  trimmed to target size {target} (was {len(out) + 1})")

    out.sort(key=lambda r: (r["category"], r["case_id"]))
    return out


def parse_args() -> argparse.Namespace:
    """CLI args."""
    tc_dir = os.environ.get(
        "TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases")
    )
    p = argparse.ArgumentParser(description="Stratified random sampling.")
    p.add_argument("--input", type=Path,
                   default=Path(tc_dir) / "03_categorized.jsonl")
    p.add_argument("--output", type=Path,
                   default=Path(tc_dir) / "04_sampled.jsonl")
    p.add_argument("--target-size", type=int, default=SAMPLE_TARGET_SIZE,
                   help=f"Total sample size (default: {SAMPLE_TARGET_SIZE})")
    p.add_argument("--seed", type=int, default=RANDOM_SEED,
                   help=f"RNG seed (default: {RANDOM_SEED})")
    return p.parse_args()


def main() -> int:
    """Read categorized JSONL, draw stratified sample, write JSONL."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        logger.error("Run 15_categorize_by_mondo.py first.")
        return 1

    by_cat = load_by_category(args.input)
    logger.info(f"Loaded {sum(len(v) for v in by_cat.values()):,} cases:")
    for cat in CATEGORIES:
        logger.info(f"  '{cat}': {len(by_cat.get(cat, []))} available")

    rng = random.Random(args.seed)
    sample = sample_stratified(by_cat, args.target_size, rng)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for r in sample:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    counts: dict[str, int] = defaultdict(int)
    for r in sample:
        counts[r["category"]] += 1
    logger.info("=== Sampling summary ===")
    logger.info(f"  target size:  {args.target_size}")
    logger.info(f"  actual size:  {len(sample)}")
    logger.info(f"  RNG seed:     {args.seed} (fully reproducible)")
    logger.info("  by category:")
    for cat in CATEGORIES:
        logger.info(f"    {cat:14s} {counts[cat]}")
    logger.info(f"  output:       {args.output}")
    return 0 if sample else 1


if __name__ == "__main__":
    raise SystemExit(main())
