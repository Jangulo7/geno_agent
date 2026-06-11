"""Run Cell P — D + K ensemble (Reciprocal Rank Fusion).

For each Phase 1B test case where both Cell D and Cell K have a
result JSON, fuse the two ranked lists via RRF and write the result
to ``data/eval/cell_P_ensemble_d_k/<case_id>.json`` in the same
shape consumed by ``aggregate_metrics.py``.

This is CPU-only, runs in seconds, and has no GPU dependency — safe
to run alongside any other cells.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from src.baselines.ensemble import RRF_K, ensemble_two_cells

log = logging.getLogger("cell_P")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CELL_D_DIR = PROJECT_ROOT / "data" / "eval" / "cell_D_multi_hybrid"
CELL_K_DIR = PROJECT_ROOT / "data" / "eval" / "cell_K_exomiser_hpo_only"
CELL_P_DIR = PROJECT_ROOT / "data" / "eval" / "cell_P_ensemble_d_k"


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--k",
        type=int,
        default=RRF_K,
        help=f"RRF damping constant (default {RRF_K}).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-fuse cases even if Cell P output already exists.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    CELL_P_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Cell D dir: %s", CELL_D_DIR)
    log.info("Cell K dir: %s", CELL_K_DIR)
    log.info("Cell P dir: %s  (RRF k=%d)", CELL_P_DIR, args.k)

    d_files = sorted(CELL_D_DIR.glob("*.json"))
    if not d_files:
        log.error("No Cell D results found at %s", CELL_D_DIR)
        return 1

    done = 0
    skipped = 0
    missing_k: list[str] = []
    rank1_count = 0

    for d_path in d_files:
        case_id = d_path.stem
        k_path = CELL_K_DIR / d_path.name
        out_path = CELL_P_DIR / d_path.name

        if not k_path.is_file():
            missing_k.append(case_id)
            continue
        if out_path.is_file() and not args.overwrite:
            skipped += 1
            continue

        with d_path.open() as f:
            case_d = json.load(f)
        with k_path.open() as f:
            case_k = json.load(f)

        fused = ensemble_two_cells(case_d, case_k, k=args.k)
        with out_path.open("w") as f:
            json.dump(fused, f, indent=2)
        done += 1

        causal_rank = next(
            (p["final_rank"] for p in fused if p["is_causal"]),
            None,
        )
        if causal_rank == 1:
            rank1_count += 1
        log.info("  %s causal_rank=%s", case_id, causal_rank)

    log.info(
        "=== Cell P done: fused=%d skipped=%d missing_K=%d rank1=%d/%d ===",
        done,
        skipped,
        len(missing_k),
        rank1_count,
        done + skipped,
    )
    if missing_k:
        log.warning("Cases missing Cell K JSON: %s", missing_k[:5])
    return 0


if __name__ == "__main__":
    sys.exit(main())
