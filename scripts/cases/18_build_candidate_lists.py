"""Build a 50-gene candidate list per case (1 causal + 49 HGNC distractors).

Implements master plan §6 step 6 / §7 step [14]. For each test case, draws
``N_DISTRACTORS`` (default 49) protein-coding gene symbols from the pinned
HGNC snapshot, excluding the causal gene. The final 50-gene list is shuffled
to remove any positional cue an RNG-aware downstream system could exploit;
the original index of the causal gene is recorded as
``causal_gene_index_in_candidates``.

Per master plan §10 ("per-case derived seed"): the RNG is seeded by
``blake2b(GLOBAL_SEED | case_id)`` so any single case can be regenerated
in isolation without resampling the others.

Input precedence:
  1. ``05_validated.jsonl`` (B6 output) — the production-corpus-validated cases
  2. ``04_sampled.jsonl`` (B5 output) — fallback when the corpus is not yet built

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/18_build_candidate_lists.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Final

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_candidates")

N_DISTRACTORS: Final[int] = int(os.environ.get("N_DISTRACTORS", "49"))
GLOBAL_SEED: Final[int] = int(os.environ.get("RANDOM_SEED", "42"))


def per_case_seed(case_id: str, global_seed: int = GLOBAL_SEED) -> int:
    """Derive a deterministic per-case RNG seed.

    Uses BLAKE2b over ``f"{global_seed}|{case_id}"`` so any single case
    can be re-sampled in isolation while remaining bit-stable across runs
    and machines (master plan §10 "per-case derived seed" requirement).

    Args:
        case_id: Unique case identifier (typically ``"<cohort>:<file_stem>"``).
        global_seed: Project-wide deterministic seed (default ``RANDOM_SEED``).

    Returns:
        Non-negative 64-bit integer suitable for ``random.Random()``.
    """
    h = hashlib.blake2b(f"{global_seed}|{case_id}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big")


def load_protein_coding_symbols(hgnc_path: Path) -> list[str]:
    """Load HGNC TSV and return sorted unique protein-coding gene symbols.

    Sorted output is required for byte-stable distractor sampling: the same
    seed must yield the same draw across runs, which means the candidate
    pool's iteration order must also be stable.

    Args:
        hgnc_path: Path to ``hgnc_complete_set.txt`` (TSV).

    Returns:
        Sorted list of unique HGNC-approved protein-coding gene symbols.
    """
    df = pd.read_csv(hgnc_path, sep="\t", low_memory=False)
    pc = df[df["locus_group"] == "protein-coding gene"]
    return sorted(pc["symbol"].dropna().unique().tolist())


def build_candidate_list(
    causal_gene: str, case_id: str, all_symbols: list[str], n_distractors: int
) -> tuple[list[str], int]:
    """Draw distractors and return the shuffled 50-gene list + causal index.

    Args:
        causal_gene: HGNC symbol of the true causal gene for this case.
        case_id: Case identifier (drives the per-case RNG seed).
        all_symbols: Sorted pool of HGNC protein-coding symbols.
        n_distractors: Number of distractors to draw (default 49).

    Returns:
        ``(candidates, causal_index)`` where ``candidates`` is the
        shuffled 50-gene list and ``causal_index`` is ``candidates.index(causal_gene)``.
    """
    pool = [s for s in all_symbols if s != causal_gene]
    rng = random.Random(per_case_seed(case_id))
    distractors = rng.sample(pool, n_distractors)
    candidates = [causal_gene, *distractors]
    rng.shuffle(candidates)
    return candidates, candidates.index(causal_gene)


def resolve_input(args: argparse.Namespace, tc_dir: Path) -> Path:
    """Choose ``05_validated.jsonl`` if present, else fall back to ``04_sampled.jsonl``."""
    if args.input is not None:
        return args.input
    validated = tc_dir / "05_validated.jsonl"
    sampled = tc_dir / "04_sampled.jsonl"
    if validated.exists():
        logger.info(f"Using B6-validated input: {validated}")
        return validated
    if sampled.exists():
        logger.warning(
            f"B6 output ({validated}) not found; falling back to B5 sample ({sampled}). "
            f"Re-run after Phase 1A production corpus is indexed for the validated subset."
        )
        return sampled
    logger.error(f"Neither {validated} nor {sampled} exists; run B5 first.")
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    """CLI args."""
    tc_dir = os.environ.get("TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases"))
    hgnc_dir = os.environ.get("HGNC_DIR", str(PROJECT_ROOT / "data" / "hgnc"))
    p = argparse.ArgumentParser(description="Build 50-gene candidate lists (Phase 1B step 6).")
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Override input JSONL path (default: 05_validated.jsonl, fallback 04_sampled.jsonl).",
    )
    p.add_argument("--output", type=Path, default=Path(tc_dir) / "06_with_candidates.jsonl")
    p.add_argument("--hgnc-tsv", type=Path, default=Path(hgnc_dir) / "hgnc_complete_set.txt")
    p.add_argument(
        "--n-distractors",
        type=int,
        default=N_DISTRACTORS,
        help=f"Distractors per case (default: {N_DISTRACTORS})",
    )
    return p.parse_args()


def main() -> int:
    """Read validated/sampled JSONL, build candidate lists, write output JSONL."""
    args = parse_args()
    tc_dir = args.output.parent
    input_path = resolve_input(args, tc_dir)

    if not args.hgnc_tsv.exists():
        logger.error(f"HGNC TSV not found: {args.hgnc_tsv}")
        return 1

    logger.info(f"Loading HGNC protein-coding symbols from {args.hgnc_tsv}")
    all_symbols = load_protein_coding_symbols(args.hgnc_tsv)
    logger.info(f"  {len(all_symbols):,} HGNC protein-coding symbols available")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_in = n_out = 0
    causal_in_pool = causal_not_in_hgnc = 0

    n_total = sum(1 for _ in input_path.open("r", encoding="utf-8"))
    with (
        input_path.open("r", encoding="utf-8") as fin,
        args.output.open("w", encoding="utf-8") as fout,
    ):
        for line in tqdm(fin, total=n_total, desc="building"):
            n_in += 1
            rec = json.loads(line)
            causal = rec.get("causal_gene")
            if not causal:
                logger.warning(f"  case {rec.get('case_id')} has no causal_gene; skipping")
                continue
            if causal not in all_symbols:
                causal_not_in_hgnc += 1
                logger.warning(
                    f"  case {rec.get('case_id')}: causal gene '{causal}' not in HGNC "
                    f"protein-coding set; skipping"
                )
                continue
            causal_in_pool += 1
            candidates, causal_idx = build_candidate_list(
                causal, rec["case_id"], all_symbols, args.n_distractors
            )
            rec["candidate_genes"] = candidates
            rec["n_candidates"] = len(candidates)
            rec["causal_gene_index_in_candidates"] = causal_idx
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_out += 1

    logger.info("=== Candidate-list summary ===")
    logger.info(f"  input cases:                 {n_in:,}")
    logger.info(f"  cases with HGNC-valid causal:{causal_in_pool:,}")
    logger.info(f"  cases dropped (causal not in HGNC): {causal_not_in_hgnc:,}")
    logger.info(f"  cases written:               {n_out:,}")
    logger.info(f"  each candidate list:         1 causal + {args.n_distractors} distractors")
    logger.info(f"  output:                      {args.output}")
    return 0 if n_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
