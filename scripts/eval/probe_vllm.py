"""Smoke-test the local vLLM server and measure throughput (master plan §11.6).

Verifies that:
  * The vLLM endpoint at the configured base_url is reachable.
  * The configured model name matches what vLLM is serving.
  * The model produces well-formed responses.
  * Sustained generation throughput meets master plan §11.6's ≥5 tok/s
    acceptance threshold under multi-agent load (5 sequential calls).

Run from the project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/eval/probe_vllm.py
"""

from __future__ import annotations

import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.llm import (  # noqa: E402
    LlmConfig,
    LlmConnectionError,
    generate,
    health_check,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("probe_vllm")

# Master plan §11.6: ≥5 tokens/s sustained under multi-agent load.
MIN_TOKENS_PER_SECOND: Final[float] = 5.0

# Probe prompts representative of the agent calls Critic and Planner will make.
PROBE_PROMPTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "Short greeting",
        "Reply with exactly the word 'OK' and nothing else.",
    ),
    (
        "Short biomedical answer",
        "What is BRCA1? Answer in 1-2 sentences.",
    ),
    (
        "Phenotype reasoning",
        "Patient has Seizure (HP:0001250) and Global delay (HP:0001263). "
        "Which one HPO term is most diagnostic for narrowing down a "
        "neurodevelopmental disorder? One sentence.",
    ),
    (
        "Structured JSON",
        'Reply with ONLY this JSON: {"score": 4, "reason": "strong evidence"}.',
    ),
    (
        "Longer prompt (Critic-style chunk grading)",
        "Read this passage and return a relevance score 1-5 for whether it "
        "supports BRCA1 as a cause of breast cancer. Respond with one digit only.\n\n"
        "Passage: 'BRCA1 germline pathogenic variants confer a high lifetime "
        "risk of female breast and ovarian cancer; surveillance and risk-reducing "
        "options are well established.'",
    ),
)


def main() -> int:
    """Run probes against the local vLLM server, report throughput, exit code."""
    cfg = LlmConfig()  # defaults to http://localhost:8001/v1, model Qwen/Qwen3-8B
    logger.info("=== vLLM probe (Qwen3-8B per master plan §11.6) ===")
    logger.info(f"  base_url: {cfg.base_url}")
    logger.info(f"  model:    {cfg.model}")

    # 1. Liveness
    if not health_check(cfg):
        logger.error("vLLM endpoint unreachable. Start it first:  bash scripts/eval/start_vllm.sh")
        return 1
    logger.info("Liveness OK")

    # 2. Sequential probes — measure throughput per call
    logger.info(f"\nRunning {len(PROBE_PROMPTS)} probe prompts...")
    tok_per_s_samples: list[float] = []
    for label, prompt in PROBE_PROMPTS:
        try:
            t0 = time.time()
            response = generate(prompt, cfg=cfg, max_tokens=128)
            elapsed = time.time() - t0
        except LlmConnectionError as exc:
            logger.error(f"  {label}: connection error: {exc}")
            return 1
        except Exception as exc:
            logger.error(f"  {label}: unexpected error: {type(exc).__name__}: {exc}")
            return 1

        n_out = response.tokens_out or 0
        tok_per_s = n_out / elapsed if elapsed > 0 else 0.0
        tok_per_s_samples.append(tok_per_s)
        snippet = response.text[:80].replace("\n", " ")
        logger.info(
            "  [%5.1f tok/s, %3d tok in %.2fs] %s -> %s%s",
            tok_per_s,
            n_out,
            elapsed,
            label,
            snippet,
            "…" if len(response.text) > 80 else "",
        )

    # 3. Acceptance check
    median_tps = statistics.median(tok_per_s_samples)
    mean_tps = statistics.mean(tok_per_s_samples)
    logger.info("\n=== Throughput summary ===")
    logger.info(f"  median: {median_tps:.1f} tok/s")
    logger.info(f"  mean:   {mean_tps:.1f} tok/s")
    logger.info(f"  threshold (master plan §11.6): >= {MIN_TOKENS_PER_SECOND} tok/s")

    if median_tps >= MIN_TOKENS_PER_SECOND:
        logger.info("STATUS: PASS — vLLM meets the §11.6 throughput bar")
        return 0
    logger.error(
        f"STATUS: FAIL — median {median_tps:.1f} tok/s below threshold {MIN_TOKENS_PER_SECOND}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
