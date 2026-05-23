"""Recency-stratified aggregation (Thread E, pivoted).

The original Thread E premise (cases with source PMID > phenotype.hpoa pin
date 2026-02-16) yields an empty subset because Phenopacket Store v0.1.26
is curated from already-published literature, all of which predates the
hpoa pin. This module replaces that with a publication-recency split:

    pre_2020       cases whose source PMID was published < 2020-01-01
    post_2020      cases whose source PMID was published >= 2020-01-01

and a strictest-novel cross with Thread D's overlap flag:

    post_2020_overlap_absent  recent papers AND not cited in hpoa for the
                              causal disease — the most genuinely novel
                              subset our cohort admits.

For each subset, computes per-cell bootstrap CIs and paired Δ + McNemar
on the five canonical comparisons (S vs K, S vs L, L vs D, M vs K, M vs S).

Inputs:
  data/test_cases_1050/annotation_overlap.json   (Thread D)
  data/test_cases_1050/pmid_dates.json           (pubmed_date_lookup.py)
  data/eval_1050/cell_{D,K,L,M,S}_*/*.json

Outputs:
  data/eval_1050/_results_recency.json
  data/eval_1050/_results_recency.md

Run::

    PYTHONPATH=. python scripts/eval/aggregate_recency.py
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

from scripts.eval.aggregate_metrics import CELLS  # noqa: E402
from scripts.eval.aggregate_stratified import (  # noqa: E402
    CELL_IDS,
    COMPARISONS,
    load_cell,
    paired_compare,
    per_cell_bootstrap,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("recency")

DEFAULT_EVAL_ROOT: Final[Path] = PROJECT_ROOT / "data" / "eval_1050"
DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
DEFAULT_DATES: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "pmid_dates.json"
RECENCY_CUTOFF: Final[str] = "2020-01-01"  # pre_2020 vs post_2020


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=Path, default=DEFAULT_EVAL_ROOT)
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--dates", type=Path, default=DEFAULT_DATES)
    parser.add_argument("--cutoff", default=RECENCY_CUTOFF)
    parser.add_argument(
        "--out-json", type=Path, default=DEFAULT_EVAL_ROOT / "_results_recency.json"
    )
    parser.add_argument("--out-md", type=Path, default=DEFAULT_EVAL_ROOT / "_results_recency.md")
    args = parser.parse_args()

    # ---- load overlap + dates
    overlap_records = json.loads(args.overlap.read_text())["records"]
    overlap_of = {r["case_id"]: r["overlap"] for r in overlap_records}
    pmid_of = {
        r["case_id"]: r["source_pmid"].replace("PMID:", "")
        for r in overlap_records
        if r.get("source_pmid")
    }
    category_of = {r["case_id"]: r["category"] for r in overlap_records}

    dates = json.loads(args.dates.read_text())["dates"]

    case_date: dict[str, str] = {}
    for cid, pmid in pmid_of.items():
        d = dates.get(pmid)
        if d:
            case_date[cid] = d

    all_ids = [r["case_id"] for r in overlap_records]
    pre_2020 = [cid for cid in all_ids if case_date.get(cid, "9999") < args.cutoff]
    post_2020 = [cid for cid in all_ids if case_date.get(cid, "0000") >= args.cutoff]
    post_2020_overlap_absent = [cid for cid in post_2020 if overlap_of[cid] == 0]
    pre_2020_overlap_absent = [cid for cid in pre_2020 if overlap_of[cid] == 0]

    log.info(
        "all=%d  pre_2020=%d  post_2020=%d  post_2020_oa=%d  pre_2020_oa=%d",
        len(all_ids),
        len(pre_2020),
        len(post_2020),
        len(post_2020_overlap_absent),
        len(pre_2020_overlap_absent),
    )

    cats = sorted(set(category_of.values()))
    subsets: dict[str, list[str]] = {
        "__all__": all_ids,
        "pre_2020": pre_2020,
        "post_2020": post_2020,
        "post_2020_overlap_absent": post_2020_overlap_absent,
        "pre_2020_overlap_absent": pre_2020_overlap_absent,
    }
    for c in cats:
        subsets[f"cat_{c}_post_2020"] = [cid for cid in post_2020 if category_of[cid] == c]

    # ---- load cells
    cell_vals: dict[str, dict] = {}
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

    # ---- paired comparisons on top-level subsets
    paired: dict[str, dict[str, dict]] = {}
    for subset_name in (
        "__all__",
        "pre_2020",
        "post_2020",
        "post_2020_overlap_absent",
        "pre_2020_overlap_absent",
    ):
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
                "meta": {"cutoff": args.cutoff},
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
    def fmt_cell_row(cid: str, mp: dict) -> str:
        def f(metric: str) -> str:
            p, lo, hi = mp[cid][metric]
            return f"{p:.3f} [{lo:.3f}, {hi:.3f}]"

        return (
            f"| {cid} | {CELLS[cid]['label']} | {f('top1')} | {f('top5')} | "
            f"{f('top10')} | {f('mrr')} | {f('ndcg10')} |"
        )

    lines: list[str] = []
    lines.append("# Recency-stratified results (Thread E, pivoted)")
    lines.append("")
    lines.append(f"Cutoff: source PMID publication date {args.cutoff}.")
    lines.append("")
    lines.append(
        f"Cohort sizes: __all__ = {len(all_ids)} | pre_2020 = {len(pre_2020)} "
        f"({100 * len(pre_2020) / len(all_ids):.1f} %) | post_2020 = {len(post_2020)} "
        f"({100 * len(post_2020) / len(all_ids):.1f} %) | "
        f"post_2020_overlap_absent = {len(post_2020_overlap_absent)} "
        f"({100 * len(post_2020_overlap_absent) / len(all_ids):.1f} %)"
    )
    lines.append("")
    lines.append(
        "Strictest novel cohort = post_2020_overlap_absent: source PMID is "
        "recent AND the paper is not cited in phenotype.hpoa for the causal "
        "OMIM disease. The closest substitute for the empty PMID-after-hpoa-pin "
        "subset originally specified in plan v3 §3c.3."
    )
    lines.append("")
    for subset_name in (
        "__all__",
        "pre_2020",
        "post_2020",
        "pre_2020_overlap_absent",
        "post_2020_overlap_absent",
    ):
        n_sub = len(subsets[subset_name])
        lines.append(f"## {subset_name} (n = {n_sub})")
        lines.append("")
        lines.append("| Cell | Label | top-1 | top-5 | top-10 | MRR | NDCG@10 |")
        lines.append("|---|---|---|---|---|---|---|")
        for cid in CELL_IDS:
            if cid in per_cell[subset_name]:
                lines.append(fmt_cell_row(cid, per_cell[subset_name]))
        lines.append("")
        if subset_name in paired:
            lines.append("### Paired comparisons")
            lines.append("")
            lines.append(
                "| A vs B | metric | Delta (A-B) | 95 % CI | A>B | B>A | McNemar p | sig |"
            )
            lines.append("|---|---|---:|---|---:|---:|---:|---:|")
            for a, b in COMPARISONS:
                key = f"{a}_vs_{b}"
                if key not in paired[subset_name]:
                    continue
                for metric in ("top1", "top5", "top10", "mrr", "ndcg10"):
                    m = paired[subset_name][key]["metrics"][metric]
                    sig = "star" if m["significant"] else ""
                    ci = f"[{m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}]"
                    aw = m.get("a_wins", "")
                    bw = m.get("b_wins", "")
                    mp = f"{m['mcnemar_p']:.5f}" if "mcnemar_p" in m else ""
                    lines.append(
                        f"| {a} vs {b} | {metric} | {m['point']:+.4f} | {ci} | "
                        f"{aw} | {bw} | {mp} | {sig} |"
                    )
            lines.append("")

    # Per-MONDO x post_2020 table (recency-only subgroup detail)
    lines.append("## Per-MONDO x post_2020 — recent-cases subgroup detail")
    lines.append("")
    for cat in cats:
        sub = f"cat_{cat}_post_2020"
        n_sub = len(subsets[sub])
        lines.append(f"### {cat} | post_2020 | n = {n_sub}")
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
    print("=== RECENCY TOP-1 SUMMARY ===")
    for subset_name in (
        "__all__",
        "pre_2020",
        "post_2020",
        "pre_2020_overlap_absent",
        "post_2020_overlap_absent",
    ):
        n_sub = len(subsets[subset_name])
        print(f"\n  {subset_name} (n={n_sub}):")
        for cid in CELL_IDS:
            if cid in per_cell[subset_name]:
                p, lo, hi = per_cell[subset_name][cid]["top1"]
                print(f"    {cid}  top-1 = {p:.3f}  [{lo:.3f}, {hi:.3f}]")

    print()
    print("=== HEADLINE PAIRED Δ TOP-1 ===")
    for subset_name in (
        "__all__",
        "pre_2020",
        "post_2020",
        "pre_2020_overlap_absent",
        "post_2020_overlap_absent",
    ):
        n_sub = len(subsets[subset_name])
        print(f"\n  {subset_name} (n={n_sub}):")
        for a, b in COMPARISONS:
            key = f"{a}_vs_{b}"
            if key in paired[subset_name]:
                m = paired[subset_name][key]["metrics"]["top1"]
                sig = "star" if m["significant"] else " "
                print(
                    f"    {a} vs {b}  D={m['point']:+.4f}  "
                    f"CI=[{m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}]  "
                    f"McNemar p={m.get('mcnemar_p', float('nan')):.5f}  {sig}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
