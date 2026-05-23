"""Cell N — RRF ensemble of Cell M (LIRICAL) and Cell S (geno_agent).

Thread F (scoped, per 2026-05-23 decision after Thread D + E):
Single concrete number for the reviewer question "did you try ensembling
LIRICAL with geno_agent?" — no model retraining, no API calls. Pure
Reciprocal Rank Fusion over existing per-case rankings.

For each case in ``data/eval_1050/cell_{M,S}_*/`` we compute::

    rrf_score(g) = 1 / (k + rank_M(g)) + 1 / (k + rank_S(g))

with the standard ``k = 60`` (Cormack et al., SIGIR 2009). Genes are
re-ranked by descending RRF score and written out with the same schema
as every other cell so the existing aggregation toolchain
(``aggregate_metrics.py``, ``paired_diff.py``,
``aggregate_stratified.py``, ``aggregate_recency.py``) can pick Cell N
up by name.

Expected outcome (per §13 + §14 analysis): RRF is bounded above by the
better of M and S on each subset, so the ensemble:
  - cannot beat S on the overlap-absent / post-2020 cohorts
  - cannot beat M on the overlap-present cohort
The headline test is whether RRF gives ANY non-trivial lift on any
subset; if not, the paper Discussion notes "ensembling does not provide
complementary signal beyond what overlap status already explains."

Run::

    PYTHONPATH=. python scripts/eval/build_cell_n_rrf.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rrf_n")

DEFAULT_M_DIR: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_M_lirical_hpo_only"
DEFAULT_S_DIR: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_S_rerank_inside_plus_lea"
DEFAULT_OUT: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_N_rrf_m_s"
RRF_K: Final[int] = 60


def rrf_one_case(m_payload: list[dict], s_payload: list[dict], k: int = RRF_K) -> list[dict]:
    """Combine two ranked lists for the same case via RRF.

    Both inputs are lists of 50 dicts with at least ``symbol``,
    ``is_causal``, and ``final_rank``. We compute a per-gene
    ``rrf_score = 1/(k + rank_M) + 1/(k + rank_S)``, re-rank by descending
    RRF score (ties broken by the M score then S score), and return the
    same schema as every other cell so ``aggregate_metrics`` works.
    """
    m_rank: dict[str, int] = {e["symbol"]: int(e["final_rank"]) for e in m_payload}
    s_rank: dict[str, int] = {e["symbol"]: int(e["final_rank"]) for e in s_payload}
    causal: dict[str, bool] = {e["symbol"]: bool(e["is_causal"]) for e in m_payload}
    # union of symbols (should be identical, but be defensive)
    symbols = sorted(set(m_rank) | set(s_rank))
    scored: list[tuple[float, int, int, str, bool]] = []
    for sym in symbols:
        rm = m_rank.get(sym, len(symbols) + 1)
        rs = s_rank.get(sym, len(symbols) + 1)
        score = 1.0 / (k + rm) + 1.0 / (k + rs)
        scored.append((score, rm, rs, sym, causal.get(sym, False)))
    # Descending RRF, ascending M rank, ascending S rank
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    out: list[dict] = []
    for new_rank, (score, rm, rs, sym, is_causal) in enumerate(scored, start=1):
        out.append(
            {
                "symbol": sym,
                "is_causal": is_causal,
                "aggregate_confidence": round(score, 6),
                "supporting_chunks": [],
                "final_rank": new_rank,
                "_rrf_m_rank": rm,
                "_rrf_s_rank": rs,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m-dir", type=Path, default=DEFAULT_M_DIR)
    parser.add_argument("--s-dir", type=Path, default=DEFAULT_S_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--k", type=int, default=RRF_K, help="RRF constant (default 60)")
    args = parser.parse_args()

    m_cases = {p.stem: p for p in args.m_dir.glob("*.json")}
    s_cases = {p.stem: p for p in args.s_dir.glob("*.json")}
    common = sorted(set(m_cases) & set(s_cases))
    log.info("M cases: %d, S cases: %d, common: %d", len(m_cases), len(s_cases), len(common))
    if len(common) != len(m_cases) or len(common) != len(s_cases):
        log.warning(
            "Case mismatch — M-only %d, S-only %d",
            len(set(m_cases) - set(s_cases)),
            len(set(s_cases) - set(m_cases)),
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    n_written = 0
    n_top1_changes_vs_s = 0
    n_top1_changes_vs_m = 0
    for case_id in common:
        m_payload = json.loads(m_cases[case_id].read_text())
        s_payload = json.loads(s_cases[case_id].read_text())
        rrf = rrf_one_case(m_payload, s_payload, k=args.k)
        out_path = args.out_dir / f"{case_id}.json"
        out_path.write_text(json.dumps(rrf, indent=2))
        n_written += 1
        # Quick sanity: did RRF move the causal gene's top-1 status?
        causal_rank_m = next((e["final_rank"] for e in m_payload if e["is_causal"]), None)
        causal_rank_s = next((e["final_rank"] for e in s_payload if e["is_causal"]), None)
        causal_rank_n = next((e["final_rank"] for e in rrf if e["is_causal"]), None)
        top1_m = causal_rank_m == 1
        top1_s = causal_rank_s == 1
        top1_n = causal_rank_n == 1
        if top1_n != top1_s:
            n_top1_changes_vs_s += 1
        if top1_n != top1_m:
            n_top1_changes_vs_m += 1
    log.info("Wrote %d Cell N JSONs to %s", n_written, args.out_dir)
    log.info("Top-1 flips vs S: %d / %d", n_top1_changes_vs_s, n_written)
    log.info("Top-1 flips vs M: %d / %d", n_top1_changes_vs_m, n_written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
