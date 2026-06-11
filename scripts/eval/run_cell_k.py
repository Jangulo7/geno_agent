"""Run Cell K — Exomiser HPO-only baseline — over the 75 test cases.

Standalone driver (separate from ``run_factorial.py`` because Exomiser is
a CPU-only Java subprocess, doesn't share the GPU constraints of cells
A-J). Produces ``data/eval/cell_K_exomiser_hpo_only/<case_id>.json`` in
the same format consumed by ``aggregate_metrics.py``.

Usage::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/eval/run_cell_K.py [--limit N] [--overwrite]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from src.baselines.exomiser_runner import ExomiserRunner

log = logging.getLogger("cell_K")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_JSONL = PROJECT_ROOT / "data" / "test_cases" / "test_cases.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "eval" / "cell_K_exomiser_hpo_only"


def _load_cases() -> list[dict]:
    """Read the 75 Phase 1B test cases from the JSONL."""
    cases: list[dict] = []
    with CASES_JSONL.open() as f:
        for line in f:
            cases.append(json.loads(line))
    return cases


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases (smoke / debug).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-run cases even if their JSON already exists.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = _load_cases()
    if args.limit:
        cases = cases[: args.limit]

    log.info("=== Cell K: Exomiser HPO-only over %d cases ===", len(cases))
    log.info("Output dir: %s", OUTPUT_DIR)

    runner = ExomiserRunner.from_default()
    log.info("Exomiser jar: %s", runner.paths.jar)
    log.info("Exomiser data: %s", runner.paths.data_dir)

    done = 0
    skipped = 0
    errors: list[tuple[str, str]] = []
    cell_t0 = time.time()

    for i, case in enumerate(cases, start=1):
        out_path = OUTPUT_DIR / f"{case['case_id']}.json"
        if out_path.is_file() and not args.overwrite:
            log.info("  [%d/%d] %s SKIP (exists)", i, len(cases), case["case_id"])
            skipped += 1
            continue
        t0 = time.time()
        try:
            payload = runner.run_case(case, timeout=300)
        except Exception as e:
            dt = time.time() - t0
            log.error(
                "  [%d/%d] %s FAIL (%s, %.1fs)",
                i,
                len(cases),
                case["case_id"],
                type(e).__name__,
                dt,
            )
            errors.append((case["case_id"], str(e)[:200]))
            continue
        dt = time.time() - t0
        causal_rank = next(
            (p["final_rank"] for p in payload if p["is_causal"]),
            None,
        )
        with out_path.open("w") as f:
            json.dump(payload, f, indent=2)
        done += 1
        log.info(
            "  [%d/%d] %s causal_rank=%s (%.1fs)",
            i,
            len(cases),
            case["case_id"],
            causal_rank,
            dt,
        )

    cell_dt = (time.time() - cell_t0) / 60.0
    log.info(
        "=== Cell K done in %.1fmin: done=%d skipped=%d errors=%d ===",
        cell_dt,
        done,
        skipped,
        len(errors),
    )
    if errors:
        log.warning("Errors:")
        for cid, msg in errors[:10]:
            log.warning("  %s: %s", cid, msg)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
