"""Run Cell O — LLM-only (no-retrieval) baseline — over the n=1,047 test cases.

Isolates the joint value of retrieval + the agentic workflow: the same locally
served Qwen3-8B that Cell S uses ranks each case's 50 candidate genes from its
parametric knowledge alone (no PMC retrieval, no Critic, no evidence chunks).
Produces ``data/eval_1050/cell_O_llm_only/<case_id>.json`` in the format consumed
by ``aggregate_metrics.py`` / ``aggregate_stratified.py``.

Requires the local vLLM server (Qwen3-8B on :8001) — the same one used for
Cell S. No new dependencies and no GPU beyond what Cell S already needs.

Usage::

    source /home/hana77/pytorch-env/bin/activate
    scripts/eval/start_vllm.sh              # if not already running
    PYTHONPATH=. python scripts/eval/run_cell_o.py [--limit N] [--overwrite]

Then aggregate (Cell O is registered as "O", compared against S):

    PYTHONPATH=. python scripts/eval/aggregate_stratified.py \
        --eval-root data/eval_1050 \
        --out-json data/eval_1050/_results_stratified.json \
        --out-md   data/eval_1050/_results_stratified.md
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402
from src.baselines.llm_only import rank_llm_only  # noqa: E402
from src.tools.hpo import load_hpo, lookup_term  # noqa: E402
from src.tools.llm import LlmConfig, health_check  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

log = logging.getLogger("cell_O")

DEFAULT_CASES_JSONL: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl"
DEFAULT_OUTPUT_DIR: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_O_llm_only"
DEFAULT_HPO_OBO: Final[Path] = Path(
    os.environ.get(
        "HPO_OBO",
        str(PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"),
    )
)


def _load_cases(cases_path: Path) -> list[dict]:
    """Read the test cases from a JSONL file."""
    with cases_path.open() as f:
        return [json.loads(line) for line in f]


def _hpo_labels(case: dict, ontology) -> list[str]:
    """Resolve a case's HPO IDs to display labels (same source as Cell S's LEA)."""
    labels: list[str] = []
    for hpo_id in case.get("hpo_terms", []):
        term = lookup_term(hpo_id, ontology)
        if term is not None and term.name:
            labels.append(term.name)
    return labels


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-cases", type=Path, default=DEFAULT_CASES_JSONL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--hpo-obo", type=Path, default=DEFAULT_HPO_OBO)
    parser.add_argument("--base-url", type=str, default=None, help="Override vLLM base URL.")
    parser.add_argument("--model", type=str, default=None, help="Override model id.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N cases.")
    parser.add_argument("--overwrite", action="store_true", help="Re-run existing cases.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    llm_cfg = LlmConfig()
    if args.base_url:
        llm_cfg = LlmConfig(base_url=args.base_url, model=args.model or llm_cfg.model)
    elif args.model:
        llm_cfg = LlmConfig(model=args.model)

    if not health_check(llm_cfg):
        log.error(
            "vLLM server not reachable at %s. Start it with scripts/eval/start_vllm.sh "
            "(Qwen3-8B on :8001) before running Cell O.",
            llm_cfg.base_url,
        )
        return 2

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = _load_cases(args.test_cases)
    if args.limit:
        cases = cases[: args.limit]

    log.info("=== Cell O: LLM-only (no retrieval) over %d cases ===", len(cases))
    log.info("Model: %s @ %s", llm_cfg.model, llm_cfg.base_url)
    log.info("HPO ontology: %s", args.hpo_obo)
    log.info("Output dir: %s", out_dir)

    ontology = load_hpo(args.hpo_obo)

    done = skipped = 0
    errors: list[tuple[str, str]] = []
    cell_t0 = time.time()

    for i, case in enumerate(cases, start=1):
        out_path = out_dir / f"{case['case_id']}.json"
        if out_path.is_file() and not args.overwrite:
            skipped += 1
            continue
        t0 = time.time()
        try:
            payload = rank_llm_only(case, hpo_labels=_hpo_labels(case, ontology), llm_cfg=llm_cfg)
        except Exception as e:  # one bad case must not abort the whole sweep
            log.error("  [%d/%d] %s FAIL (%s)", i, len(cases), case["case_id"], type(e).__name__)
            errors.append((case["case_id"], str(e)[:200]))
            continue
        causal_rank = next((p["final_rank"] for p in payload if p["is_causal"]), None)
        with out_path.open("w") as f:
            json.dump(payload, f, indent=2)
        done += 1
        dt = time.time() - t0
        log.info(
            "  [%d/%d] %s causal_rank=%s (%.1fs)", i, len(cases), case["case_id"], causal_rank, dt
        )

    log.info(
        "=== Cell O done in %.1fmin: done=%d skipped=%d errors=%d ===",
        (time.time() - cell_t0) / 60.0,
        done,
        skipped,
        len(errors),
    )
    for cid, msg in errors[:10]:
        log.warning("  %s: %s", cid, msg)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
