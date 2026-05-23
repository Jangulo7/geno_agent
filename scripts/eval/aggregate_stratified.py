"""Stratified aggregation by LIRICAL annotation overlap (Thread D).

For each cell in {D, K, L, M, S} computes overall metrics + per-MONDO metrics
on three subsets:

  - __all__         all 1,047 cases (matches aggregate_metrics.py)
  - overlap_present cases whose source PMID is cited by phenotype.hpoa for the
                    causal OMIM disease (LIRICAL has annotation-overlap advantage)
  - overlap_absent  cases without such citation (LIRICAL has no overlap edge)

The "overlap-absent" numbers are the fair comparison cohort. The expected
finding (plan v3 §3b.4):
  - LIRICAL top-1 drops materially on overlap-absent (~0.95 -> ~0.65-0.75)
  - Cell S top-1 is roughly stable across subsets
  - On overlap-absent, geno_agent's relative position improves substantially

Also computes paired Δ + bootstrap CI + McNemar on the canonical comparisons
(S vs K, S vs L, L vs D, M vs K, M vs S) on each subset and reports a single
combined JSON/markdown.

Inputs:
  data/test_cases_1050/test_cases.jsonl     (cohort + categories)
  data/test_cases_1050/annotation_overlap.json   (from compute_annotation_overlap.py)
  data/eval_1050/cell_{D,K,L,M,S}_*/*.json  (per-case ranked lists)

Outputs:
  data/eval_1050/_results_stratified.json   (full programmatic dump)
  data/eval_1050/_results_stratified.md     (paper-ready tables)

Run::

    PYTHONPATH=. python scripts/eval/aggregate_stratified.py
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

from scripts.eval.aggregate_metrics import (  # noqa: E402
    CELLS,
    causal_rank_from_payload,
    ndcg_at_10,
    reciprocal_rank,
    top_k_hit,
)
from scripts.eval.paired_diff import (  # noqa: E402
    mcnemar_exact_p,
    paired_bootstrap_diff,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("stratified")

DEFAULT_EVAL_ROOT: Final[Path] = PROJECT_ROOT / "data" / "eval_1050"
DEFAULT_TEST_CASES: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl"
DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
CELL_IDS: Final[tuple[str, ...]] = ("D", "K", "L", "M", "S")
COMPARISONS: Final[tuple[tuple[str, str], ...]] = (
    ("S", "K"),  # paper headline
    ("S", "L"),  # LEA effect
    ("L", "D"),  # CE-rerank effect
    ("M", "K"),  # LIRICAL vs Exomiser
    ("M", "S"),  # LIRICAL vs geno_agent
)


def load_cell(cell_dir: Path) -> dict[str, dict[str, float]]:
    """Return ``{case_id: {top1, top5, top10, mrr, ndcg10, rank}}`` for a cell."""
    out: dict[str, dict[str, float]] = {}
    for path in sorted(cell_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            log.warning("Bad JSON: %s", path)
            continue
        rank = causal_rank_from_payload(payload)
        out[path.stem] = {
            "top1": float(top_k_hit(rank, 1)),
            "top5": float(top_k_hit(rank, 5)),
            "top10": float(top_k_hit(rank, 10)),
            "mrr": reciprocal_rank(rank),
            "ndcg10": ndcg_at_10(rank),
            "rank": -1 if rank is None else rank,
        }
    return out


def per_cell_means(values: dict[str, dict[str, float]], case_ids: list[str]) -> dict[str, float]:
    """Mean of each metric over the given subset of case_ids."""
    out: dict[str, float] = {}
    n = len(case_ids)
    if n == 0:
        return dict.fromkeys(("top1", "top5", "top10", "mrr", "ndcg10"), 0.0)
    for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
        out[metric] = sum(values[c][metric] for c in case_ids if c in values) / n
    return out


def per_cell_bootstrap(
    values: dict[str, dict[str, float]], case_ids: list[str]
) -> dict[str, tuple[float, float, float]]:
    """Single-cell mean + 95 % CI via bootstrap on cases in ``case_ids``."""
    import math
    import random

    out: dict[str, tuple[float, float, float]] = {}
    n_resamples = 1000
    seed = 42
    n = len(case_ids)
    if n == 0:
        return dict.fromkeys(("top1", "top5", "top10", "mrr", "ndcg10"), (0.0, 0.0, 0.0))
    rng = random.Random(seed)
    for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
        vec = [values[c][metric] for c in case_ids if c in values]
        point = sum(vec) / n
        means = []
        for _ in range(n_resamples):
            s = 0.0
            for _ in range(n):
                s += vec[rng.randrange(n)]
            means.append(s / n)
        means.sort()
        lo = means[max(0, math.floor(0.025 * n_resamples))]
        hi = means[min(n_resamples - 1, math.ceil(0.975 * n_resamples) - 1)]
        out[metric] = (round(point, 4), round(lo, 4), round(hi, 4))
    return out


def paired_compare(a_vals: dict, b_vals: dict, case_ids: list[str]) -> dict:
    """Paired Δ + bootstrap CI + McNemar for A vs B on case_ids."""
    common = [c for c in case_ids if c in a_vals and c in b_vals]
    n = len(common)
    out: dict = {"n": n, "metrics": {}}
    for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
        diffs = [a_vals[c][metric] - b_vals[c][metric] for c in common]
        point, lo, hi = paired_bootstrap_diff(diffs)
        sig = lo > 0 or hi < 0
        d = {
            "point": round(point, 4),
            "ci_lo": round(lo, 4),
            "ci_hi": round(hi, 4),
            "significant": sig,
        }
        if metric in ("top1", "top5", "top10"):
            a_wins = sum(1 for c in common if a_vals[c][metric] > b_vals[c][metric])
            b_wins = sum(1 for c in common if a_vals[c][metric] < b_vals[c][metric])
            d["a_wins"] = a_wins
            d["b_wins"] = b_wins
            d["mcnemar_p"] = round(mcnemar_exact_p(a_wins, b_wins), 5)
        out["metrics"][metric] = d
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=Path, default=DEFAULT_EVAL_ROOT)
    parser.add_argument("--test-cases", type=Path, default=DEFAULT_TEST_CASES)
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument(
        "--out-json", type=Path, default=DEFAULT_EVAL_ROOT / "_results_stratified.json"
    )
    parser.add_argument("--out-md", type=Path, default=DEFAULT_EVAL_ROOT / "_results_stratified.md")
    args = parser.parse_args()

    # ---- load overlap flags + categories
    overlap_records: list[dict] = json.loads(args.overlap.read_text())["records"]
    category_of: dict[str, str] = {r["case_id"]: r["category"] for r in overlap_records}
    overlap_of: dict[str, int] = {r["case_id"]: r["overlap"] for r in overlap_records}
    all_ids = [r["case_id"] for r in overlap_records]
    present_ids = [c for c in all_ids if overlap_of[c] == 1]
    absent_ids = [c for c in all_ids if overlap_of[c] == 0]
    log.info(
        "all=%d  overlap_present=%d  overlap_absent=%d",
        len(all_ids),
        len(present_ids),
        len(absent_ids),
    )

    # per-category subsets
    cats = sorted(set(category_of.values()))
    cat_ids: dict[str, list[str]] = {
        c: [cid for cid in all_ids if category_of[cid] == c] for c in cats
    }

    subsets = {
        "__all__": all_ids,
        "overlap_present": present_ids,
        "overlap_absent": absent_ids,
    }
    for c in cats:
        subsets[f"cat_{c}"] = cat_ids[c]
        subsets[f"cat_{c}_overlap_present"] = [cid for cid in cat_ids[c] if overlap_of[cid] == 1]
        subsets[f"cat_{c}_overlap_absent"] = [cid for cid in cat_ids[c] if overlap_of[cid] == 0]

    # ---- load cells
    cell_vals: dict[str, dict[str, dict[str, float]]] = {}
    for cid in CELL_IDS:
        meta = CELLS[cid]
        cell_dir = args.eval_root / meta["dir"]
        if not cell_dir.is_dir():
            log.warning("Skipping %s: dir missing %s", cid, cell_dir)
            continue
        cell_vals[cid] = load_cell(cell_dir)
        log.info("Cell %s: %d cases", cid, len(cell_vals[cid]))

    # ---- per-cell metrics on each subset
    per_cell: dict[str, dict[str, dict]] = {}
    for subset_name, case_ids in subsets.items():
        per_cell[subset_name] = {}
        for cid in CELL_IDS:
            if cid not in cell_vals:
                continue
            per_cell[subset_name][cid] = per_cell_bootstrap(cell_vals[cid], case_ids)

    # ---- paired comparisons on each subset (only top-level subsets)
    paired: dict[str, dict[str, dict]] = {}
    for subset_name in ("__all__", "overlap_present", "overlap_absent"):
        paired[subset_name] = {}
        for a, b in COMPARISONS:
            if a in cell_vals and b in cell_vals:
                paired[subset_name][f"{a}_vs_{b}"] = paired_compare(
                    cell_vals[a], cell_vals[b], subsets[subset_name]
                )

    # ---- write JSON
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(
            {
                "subsets": {k: len(v) for k, v in subsets.items()},
                "per_cell": per_cell,
                "paired": paired,
            },
            indent=2,
            default=list,
        )
    )
    log.info("Wrote %s", args.out_json)

    # ---- write markdown
    lines: list[str] = []
    lines.append("# Stratified results (overlap-present vs overlap-absent) — Thread D")
    lines.append("")
    lines.append(
        f"Cohort: n = {len(all_ids)} | overlap-present = {len(present_ids)} "
        f"({100 * len(present_ids) / len(all_ids):.1f} %) | "
        f"overlap-absent = {len(absent_ids)} ({100 * len(absent_ids) / len(all_ids):.1f} %)"
    )
    lines.append("")
    lines.append(
        "Overlap = case's source PMID is referenced by phenotype.hpoa for "
        "the causal OMIM disease. LIRICAL (Cell M) has annotation-overlap "
        "advantage on the *present* subset; the *absent* subset is the fair "
        "comparison cohort."
    )
    lines.append("")

    def fmt_cell_row(cid: str, mp: dict) -> str:
        def f(metric: str) -> str:
            p, lo, hi = mp[cid][metric]
            return f"{p:.3f} [{lo:.3f}, {hi:.3f}]"

        label = CELLS[cid]["label"]
        return (
            f"| {cid} | {label} | {f('top1')} | {f('top5')} | "
            f"{f('top10')} | {f('mrr')} | {f('ndcg10')} |"
        )

    for subset_name in ("__all__", "overlap_present", "overlap_absent"):
        n_sub = len(subsets[subset_name])
        lines.append(f"## {subset_name} (n = {n_sub})")
        lines.append("")
        lines.append("| Cell | Label | top-1 | top-5 | top-10 | MRR | NDCG@10 |")
        lines.append("|---|---|---|---|---|---|---|")
        for cid in CELL_IDS:
            if cid in per_cell[subset_name]:
                lines.append(fmt_cell_row(cid, per_cell[subset_name]))
        lines.append("")
        lines.append("### Paired comparisons")
        lines.append("")
        lines.append("| A vs B | metric | Δ (A-B) | 95 % CI | A>B | B>A | McNemar p | sig |")
        lines.append("|---|---|---:|---|---:|---:|---:|---:|")
        for a, b in COMPARISONS:
            key = f"{a}_vs_{b}"
            if key not in paired[subset_name]:
                continue
            for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
                m = paired[subset_name][key]["metrics"][metric]
                sig = "★" if m["significant"] else ""
                ci = f"[{m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}]"
                aw = m.get("a_wins", "")
                bw = m.get("b_wins", "")
                mp = f"{m['mcnemar_p']:.5f}" if "mcnemar_p" in m else ""
                lines.append(
                    f"| {a} vs {b} | {metric} | {m['point']:+.4f} | {ci} | "
                    f"{aw} | {bw} | {mp} | {sig} |"
                )
        lines.append("")

    # Per-category x overlap-absent (the fair-comparison cell table)
    lines.append("## Per-MONDO x overlap-absent — fair-comparison detail")
    lines.append("")
    for cat in cats:
        sub = f"cat_{cat}_overlap_absent"
        n_sub = len(subsets[sub])
        lines.append(f"### {cat} | overlap-absent | n = {n_sub}")
        lines.append("")
        lines.append("| Cell | top-1 | top-5 | top-10 | MRR | NDCG@10 |")
        lines.append("|---|---|---|---|---|---|")
        for cid in CELL_IDS:
            if cid in per_cell[sub]:
                p1 = per_cell[sub][cid]["top1"][0]
                p5 = per_cell[sub][cid]["top5"][0]
                p10 = per_cell[sub][cid]["top10"][0]
                mrr = per_cell[sub][cid]["mrr"][0]
                ndcg = per_cell[sub][cid]["ndcg10"][0]
                lines.append(
                    f"| {cid} | {p1:.3f} | {p5:.3f} | {p10:.3f} | {mrr:.3f} | {ndcg:.3f} |"
                )
        lines.append("")

    args.out_md.write_text("\n".join(lines))
    log.info("Wrote %s", args.out_md)

    # ---- console summary
    print()
    print("=== STRATIFIED TOP-1 SUMMARY ===")
    for subset_name in ("__all__", "overlap_present", "overlap_absent"):
        n_sub = len(subsets[subset_name])
        print(f"\n  {subset_name} (n={n_sub}):")
        for cid in CELL_IDS:
            if cid in per_cell[subset_name]:
                p, lo, hi = per_cell[subset_name][cid]["top1"]
                print(f"    {cid}  top-1 = {p:.3f}  [{lo:.3f}, {hi:.3f}]")
    print()
    print("=== HEADLINE PAIRED Δ TOP-1 ===")
    for subset_name in ("__all__", "overlap_present", "overlap_absent"):
        n_sub = len(subsets[subset_name])
        print(f"\n  {subset_name} (n={n_sub}):")
        for a, b in COMPARISONS:
            key = f"{a}_vs_{b}"
            if key in paired[subset_name]:
                m = paired[subset_name][key]["metrics"]["top1"]
                sig = "★" if m["significant"] else " "
                print(
                    f"    {a} vs {b}  Δ={m['point']:+.4f}  CI=[{m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}]  "
                    f"McNemar p={m.get('mcnemar_p', float('nan')):.5f}  {sig}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
