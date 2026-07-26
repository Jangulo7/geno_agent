"""Shared loaders for the P2 revision re-analysis.

Every script under ``scripts/eval/revision/`` builds its numbers from the saved
per-case artefacts through this module, so that a single definition of
"the causal gene's rank under system X on cohort Y" is used everywhere.

No model inference happens here: the ranked candidate lists were produced by the
original evaluation runs and are read as-is.

Seed 42 throughout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

SEED = 42

REPO = Path(__file__).resolve().parents[3]
COHORT_DIR = REPO / "data" / "test_cases_1050"
EVAL_STD = REPO / "data" / "eval_1050"
EVAL_HARD = REPO / "data" / "eval_hard"
OUT_DIR = REPO / "reports" / "p2_revision"

# Cell label -> artefact sub-directory. Cell O (LLM-only control) exists only for
# the standard cohort; the hard cohort was never run through it.
CELL_DIRS = {
    "D": "cell_D_multi_hybrid",
    "K": "cell_K_exomiser_hpo_only",
    "L": "cell_L_rerank_inside_d",
    "M": "cell_M_lirical_hpo_only",
    "N": "cell_N_rrf_m_s",
    "O": "cell_O_llm_only",
    "S": "cell_S_rerank_inside_plus_lea",
    # Cell R: bare Resnik/BMA phenotype-similarity ranker, produced by
    # scripts/eval/revision/resnik_ranker.py (C2).
    "R": "cell_R_resnik",
}

CELL_NAMES = {
    "D": "Multi-agent baseline",
    "K": "Exomiser (HPO-only)",
    "L": "+ CE-rerank (inside)",
    "M": "LIRICAL (HPO-only)",
    "N": "RRF ensemble (M+S)",
    "O": "LLM-only (no retrieval)",
    "S": "GenoAgent",
    "R": "Resnik BMA (similarity floor)",
}

# P1 Table "Sampling design by disease category": eligible pool, analytic cohort,
# inclusion probability and design weight (reciprocal). Authoritative source is
# the P1 data descriptor; reproduced here so the weighting is auditable.
DESIGN = {
    "developmental": {"eligible": 464, "analytic": 250},
    "immunological": {"eligible": 390, "analytic": 300},
    "metabolic": {"eligible": 672, "analytic": 250},
    "neurological": {"eligible": 3144, "analytic": 247},
}

CATEGORIES = ("developmental", "immunological", "metabolic", "neurological")


def design_weights() -> dict[str, float]:
    """Design weight = 1 / inclusion probability, inclusion prob = analytic/eligible."""
    return {c: v["eligible"] / v["analytic"] for c, v in DESIGN.items()}


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    source_pmid: str
    causal_gene: str
    overlap: int
    omim_ids: tuple[str, ...]
    year: int | None

    @property
    def post2020(self) -> bool:
        return self.year is not None and self.year >= 2020


@lru_cache(maxsize=1)
def load_cases() -> list[Case]:
    """The n=1,047 analytic cohort with its P1 metadata layers attached."""
    overlap_doc = json.loads((COHORT_DIR / "annotation_overlap.json").read_text())
    overlap_by_id = {r["case_id"]: r for r in overlap_doc["records"]}

    dates = json.loads((COHORT_DIR / "pmid_dates.json").read_text())["dates"]

    cases: list[Case] = []
    with (COHORT_DIR / "test_cases.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            cid = rec["case_id"]
            ov = overlap_by_id[cid]
            pmid = ov["source_pmid"].removeprefix("PMID:")
            date = dates.get(pmid)
            cases.append(
                Case(
                    case_id=cid,
                    category=rec["category"],
                    source_pmid=pmid,
                    causal_gene=rec["causal_gene"],
                    overlap=int(ov["overlap"]),
                    omim_ids=tuple(ov["omim_ids"]),
                    year=int(date[:4]) if date else None,
                )
            )
    return cases


def _causal_rank(path: Path) -> int | None:
    """1-based rank of the causal gene in a saved per-case ranking, or None.

    Artefacts are a list of ``{symbol, is_causal, final_rank, ...}`` dicts.
    """
    payload = json.loads(path.read_text())
    for entry in payload:
        if entry.get("is_causal"):
            return int(entry["final_rank"])
    return None


@lru_cache(maxsize=32)
def load_ranks(cell: str, cohort: str = "standard") -> dict[str, int | None]:
    """causal-gene rank per case_id for one evaluation cell.

    cohort: "standard" (49 random distractors) or "hard" (49 phenotype-similar).
    """
    root = EVAL_STD if cohort == "standard" else EVAL_HARD
    cell_dir = root / CELL_DIRS[cell]
    if not cell_dir.is_dir():
        raise FileNotFoundError(f"no artefacts for cell {cell} on {cohort}: {cell_dir}")
    out: dict[str, int | None] = {}
    for case in load_cases():
        # case_id contains ':' which is a legal filename character here.
        path = cell_dir / f"{case.case_id}.json"
        out[case.case_id] = _causal_rank(path) if path.exists() else None
    return out


def available_cells(cohort: str = "standard") -> list[str]:
    root = EVAL_STD if cohort == "standard" else EVAL_HARD
    return [c for c, d in CELL_DIRS.items() if (root / d).is_dir()]


def hit_matrix(cohort: str = "standard", k: int = 1) -> dict[str, dict[str, int]]:
    """cell -> case_id -> 1/0 indicator that the causal gene is in the top k."""
    out = {}
    for cell in available_cells(cohort):
        ranks = load_ranks(cell, cohort)
        out[cell] = {cid: int(r is not None and r <= k) for cid, r in ranks.items()}
    return out


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def metrics_for(ranks: dict[str, int | None], case_ids) -> dict[str, float]:
    """top-1/5/10, MRR and NDCG@10 over a subset of cases.

    NDCG@10 with a single binary-relevant item reduces to 1/log2(rank+1) for
    rank<=10 and 0 otherwise (ideal DCG = 1), matching the original aggregation.
    """
    case_ids = list(case_ids)
    n = len(case_ids)
    if n == 0:
        return {m: float("nan") for m in ("top1", "top5", "top10", "mrr", "ndcg10")}
    rs = [ranks.get(c) for c in case_ids]
    top1 = sum(r is not None and r <= 1 for r in rs) / n
    top5 = sum(r is not None and r <= 5 for r in rs) / n
    top10 = sum(r is not None and r <= 10 for r in rs) / n
    mrr = sum((1.0 / r) if r is not None else 0.0 for r in rs) / n
    ndcg = sum((1.0 / np.log2(r + 1)) if (r is not None and r <= 10) else 0.0 for r in rs) / n
    return {"top1": top1, "top5": top5, "top10": top10, "mrr": mrr, "ndcg10": ndcg}


# --------------------------------------------------------------------------
# Cohort subsets
# --------------------------------------------------------------------------


def subset(name: str) -> list[Case]:
    cases = load_cases()
    if name == "full":
        return cases
    if name == "overlap_present":
        return [c for c in cases if c.overlap == 1]
    if name == "overlap_absent":
        return [c for c in cases if c.overlap == 0]
    if name == "pre2020":
        return [c for c in cases if not c.post2020]
    if name == "post2020":
        return [c for c in cases if c.post2020]
    if name == "post2020_overlap_absent":
        return [c for c in cases if c.post2020 and c.overlap == 0]
    raise KeyError(name)


SUBSETS = (
    "full",
    "overlap_present",
    "overlap_absent",
    "pre2020",
    "post2020",
    "post2020_overlap_absent",
)


# --------------------------------------------------------------------------
# Cluster bootstrap on source publication (P1 Usage Notes recommendation)
# --------------------------------------------------------------------------


def cluster_bootstrap(
    cases: list[Case],
    statistic,
    n_boot: int = 10_000,
    seed: int = SEED,
) -> tuple[float, float, float]:
    """Percentile CI for `statistic` under resampling of source publications.

    Publications are resampled with replacement; every case belonging to a drawn
    publication is retained, which is the publication-level bootstrap P1's Usage
    Notes recommend in place of resampling cases.

    Returns (point_estimate, lo, hi).
    """
    rng = np.random.default_rng(seed)
    by_pmid: dict[str, list[Case]] = {}
    for c in cases:
        by_pmid.setdefault(c.source_pmid, []).append(c)
    pmids = list(by_pmid)
    point = statistic(cases)

    draws = np.empty(n_boot)
    n_clusters = len(pmids)
    idx_all = np.arange(n_clusters)
    for b in range(n_boot):
        picks = rng.choice(idx_all, size=n_clusters, replace=True)
        resampled: list[Case] = []
        for i in picks:
            resampled.extend(by_pmid[pmids[i]])
        draws[b] = statistic(resampled)
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    return float(point), float(lo), float(hi)


def case_bootstrap(
    cases: list[Case], statistic, n_boot: int = 10_000, seed: int = SEED
) -> tuple[float, float, float]:
    """Case-level percentile bootstrap, retained for transparency alongside the
    cluster bootstrap (this is what the original analysis reported)."""
    rng = np.random.default_rng(seed)
    point = statistic(cases)
    n = len(cases)
    arr = np.array(cases, dtype=object)
    draws = np.empty(n_boot)
    for b in range(n_boot):
        picks = rng.integers(0, n, size=n)
        draws[b] = statistic(list(arr[picks]))
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    return float(point), float(lo), float(hi)


def write_json(name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return path
