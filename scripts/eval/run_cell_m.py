"""Run Cell M — LIRICAL HPO-only baseline — over n=1047 (paper extension v3).

LIRICAL ranks diseases (not genes) so the runner maps disease IDs to
gene symbols via OMIM/Orphanet xrefs. Each case spawns one LIRICAL JVM
(~5-10 s warmup + ~1-5 s computation). We parallelize with a worker
pool to keep wall-clock reasonable.

Defaults:
  - 8 parallel workers (each JVM at -Xmx4g → 32 GB total cap)
  - Output to data/eval_1050/cell_M_lirical_hpo_only/
  - Test cases from data/test_cases_1050/test_cases.jsonl

Usage::

    source /home/hana77/pytorch-env/bin/activate
    PYTHONPATH=. python scripts/eval/run_cell_m.py [--workers 8] [--limit N]

Outputs land in `data/eval_1050/cell_M_lirical_hpo_only/<case_id>.json` in
the same schema as cells K, D, L, S — directly aggregatable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import sys
import time
from pathlib import Path

from src.baselines.lirical_runner import LiricalPaths, LiricalRunner, load_disease_to_genes

log = logging.getLogger("cell_M")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_JSONL = PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "eval_1050" / "cell_M_lirical_hpo_only"


def _load_cases(cases_path: Path) -> list[dict]:
    """Read Phase 1B test cases from a JSONL file."""
    cases: list[dict] = []
    with cases_path.open() as f:
        for line in f:
            cases.append(json.loads(line))
    return cases


# Worker-side disease-to-gene map: loaded once per process and reused
# across cases in that worker. Avoids re-parsing en_product6.xml /
# mim2gene_medgen on every invocation.
_WORKER_RUNNER: LiricalRunner | None = None


def _worker_init(xmx: str = "4g") -> None:
    """Initialize a LiricalRunner per worker process."""
    global _WORKER_RUNNER
    paths = LiricalPaths.from_default()
    d2g = load_disease_to_genes(paths)
    _WORKER_RUNNER = LiricalRunner(paths, disease_to_genes=d2g, java_xmx=xmx)


def _process_one_case(
    payload: tuple[dict, Path, bool],
) -> tuple[str, str | None, int | None, float]:
    """Run LIRICAL on one case and write its JSON.

    Returns:
        (case_id, error_msg_or_None, causal_rank_or_None, elapsed_seconds)
    """
    case, out_dir, overwrite = payload
    out_path = out_dir / f"{case['case_id']}.json"
    if out_path.is_file() and not overwrite:
        return (case["case_id"], None, None, 0.0)  # skip

    t0 = time.time()
    try:
        assert _WORKER_RUNNER is not None
        result = _WORKER_RUNNER.run_case(case, timeout=180)
        with out_path.open("w") as f:
            json.dump(result, f, indent=2)
        elapsed = time.time() - t0
        causal_rank = next(
            (p["final_rank"] for p in result if p["is_causal"]),
            None,
        )
        return (case["case_id"], None, causal_rank, elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        return (case["case_id"], f"{type(e).__name__}: {str(e)[:200]}", None, elapsed)


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-cases",
        type=Path,
        default=DEFAULT_CASES_JSONL,
        help="Path to test cases JSONL (default: data/test_cases_1050/test_cases.jsonl)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output dir for cell_M case JSONs (default: data/eval_1050/cell_M_lirical_hpo_only/)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel LIRICAL JVMs (default 8; each at -Xmx4g → ~32 GB cap)",
    )
    parser.add_argument(
        "--xmx",
        type=str,
        default="4g",
        help="Java heap cap per LIRICAL worker (default 4g)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases (smoke/debug)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-run cases even if their JSON already exists",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = _load_cases(args.test_cases)
    if args.limit:
        cases = cases[: args.limit]

    log.info(
        "=== Cell M: LIRICAL HPO-only over %d cases (workers=%d, xmx=%s) ===",
        len(cases),
        args.workers,
        args.xmx,
    )
    log.info("Test cases: %s", args.test_cases)
    log.info("Output dir: %s", out_dir)

    work_items = [(case, out_dir, args.overwrite) for case in cases]

    done = 0
    skipped = 0
    errors: list[tuple[str, str]] = []
    causal_ranks: list[int | None] = []
    cell_t0 = time.time()

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_worker_init,
        initargs=(args.xmx,),
    ) as executor:
        for i, (cid, err, causal_rank, elapsed) in enumerate(
            executor.map(_process_one_case, work_items, chunksize=1),
            start=1,
        ):
            if err:
                log.error("  [%d/%d] %s FAIL (%s, %.1fs)", i, len(cases), cid, err, elapsed)
                errors.append((cid, err))
            elif elapsed == 0.0:
                log.info("  [%d/%d] %s SKIP (exists)", i, len(cases), cid)
                skipped += 1
            else:
                done += 1
                causal_ranks.append(causal_rank)
                log.info(
                    "  [%d/%d] %s causal_rank=%s (%.1fs)",
                    i,
                    len(cases),
                    cid,
                    causal_rank,
                    elapsed,
                )

    cell_dt = (time.time() - cell_t0) / 60.0
    log.info(
        "=== Cell M done in %.1fmin: done=%d skipped=%d errors=%d ===",
        cell_dt,
        done,
        skipped,
        len(errors),
    )
    if causal_ranks:
        n_top1 = sum(1 for r in causal_ranks if r == 1)
        log.info("  top-1: %d/%d (%.3f)", n_top1, len(causal_ranks), n_top1 / len(causal_ranks))
    if errors:
        log.warning("Errors (first 10):")
        for cid, msg in errors[:10]:
            log.warning("  %s: %s", cid, msg)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
