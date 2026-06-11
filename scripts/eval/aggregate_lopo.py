"""Aggregate the full-cohort LOPO run into the paper's stratified tables.

Reads the per-case control/LOPO outputs + leak records produced by
``run_lopo.py --all`` and joins them against the annotation-overlap flag and
the existing Exomiser (Cell K) / LIRICAL (Cell M) baselines. Produces:

  1. Control vs LOPO (paired) on full / overlap-present / overlap-absent cohorts
     — top-1/5/10 + exact-McNemar. (Does removing the source paper change geno_agent?)
  2. LOPO Cell S vs Exomiser (K) and vs LIRICAL (M) on the fair cohort
     (overlap-absent) — does geno_agent's advantage survive source-paper removal?
  3. Source-paper-in-retrieval leak rate cross-tabulated by overlap status.
  4. Per-MONDO control-vs-LOPO top-1.

Run::

    PYTHONPATH=. python scripts/eval/aggregate_lopo.py \
        --lopo-root data/eval_1050_lopo_full --cell S
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
DEFAULT_CASES: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl"
K_DIR: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_K_exomiser_hpo_only"
M_DIR: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "cell_M_lirical_hpo_only"


def rank_of_causal(path: Path, causal: str) -> int | None:
    """Return the 1-based rank of ``causal`` in a per-case ranked-gene JSON.

    Robust to either an explicit ``final_rank`` field or list order, and matches
    by gene symbol rather than an ``is_causal`` flag.
    """
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        return None
    for idx, g in enumerate(data):
        if g.get("symbol") == causal:
            return g.get("final_rank", idx + 1)
    return None


def exact_mcnemar(a: list[int], b: list[int]) -> tuple[int, int, float]:
    """Two-sided exact-binomial McNemar over paired binary indicators a vs b."""
    disc_a = sum(1 for x, y in zip(a, b, strict=True) if x == 1 and y == 0)
    disc_b = sum(1 for x, y in zip(a, b, strict=True) if x == 0 and y == 1)
    n = disc_a + disc_b
    if n == 0:
        return disc_a, disc_b, 1.0
    k = min(disc_a, disc_b)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2**n))
    return disc_a, disc_b, p


def topk(ranks: list[int | None], k: int) -> float:
    valid = [r for r in ranks if r is not None]
    return round(sum(1 for r in valid if r <= k) / len(valid), 4) if valid else 0.0


def paired_top1(ranks_a: list[int | None], ranks_b: list[int | None]) -> dict:
    """Paired top-1 comparison over cases where both arms have a rank."""
    a = [
        1 if x == 1 else 0
        for x, y in zip(ranks_a, ranks_b, strict=True)
        if x is not None and y is not None
    ]
    b = [
        1 if y == 1 else 0
        for x, y in zip(ranks_a, ranks_b, strict=True)
        if x is not None and y is not None
    ]
    da, db, p = exact_mcnemar(a, b)
    n = len(a)
    return {
        "n": n,
        "acc_a": round(sum(a) / n, 4) if n else 0.0,
        "acc_b": round(sum(b) / n, 4) if n else 0.0,
        "delta": round((sum(a) - sum(b)) / n, 4) if n else 0.0,
        "discordant_a_only": da,
        "discordant_b_only": db,
        "mcnemar_p": round(p, 5),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lopo-root", type=Path, required=True)
    ap.add_argument("--cell", default="S", choices=["S", "L"])
    ap.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = ap.parse_args()

    ctrl_dir = args.lopo_root / f"cell_{args.cell}_control"
    lopo_dir = args.lopo_root / f"cell_{args.cell}_lopo"
    leak_dir = args.lopo_root / f"leak_{args.cell}"

    cases = {
        json.loads(ln)["case_id"]: json.loads(ln)
        for ln in args.cases.read_text().splitlines()
        if ln.strip()
    }
    overlap_data = json.loads(args.overlap.read_text())
    overlap = {r["case_id"]: r["overlap"] for r in overlap_data["records"]}

    rows: list[dict] = []
    for cid, case in cases.items():
        cp, lp, kp = ctrl_dir / f"{cid}.json", lopo_dir / f"{cid}.json", leak_dir / f"{cid}.json"
        if not (cp.exists() and lp.exists()):
            continue
        causal = case["causal_gene"]
        leak = json.loads(kp.read_text()) if kp.exists() else {}
        rows.append(
            {
                "case_id": cid,
                "category": case.get("category", "unknown"),
                "overlap": overlap.get(cid),
                "ctrl": rank_of_causal(cp, causal),
                "lopo": rank_of_causal(lp, causal),
                "k": rank_of_causal(K_DIR / f"{cid}.json", causal),
                "m": rank_of_causal(M_DIR / f"{cid}.json", causal),
                "src_in_pool": bool(leak.get("source_in_causal_pool", False)),
            }
        )

    def subset(pred) -> list[dict]:
        return [r for r in rows if pred(r)]

    strata = {
        "full": rows,
        "overlap_present": subset(lambda r: r["overlap"] == 1),
        "overlap_absent (FAIR)": subset(lambda r: r["overlap"] == 0),
    }

    out: dict = {
        "lopo_root": str(args.lopo_root),
        "cell": args.cell,
        "n_cases": len(rows),
        "strata": {},
    }
    lines: list[str] = [
        f"# LOPO full-cohort results — Cell {args.cell}",
        "",
        f"Cases with both arms present: **{len(rows)}**",
        "",
    ]

    # 1. control vs LOPO, per stratum
    lines.append("## 1. Control vs LOPO (paired, geno_agent against itself)\n")
    lines.append(
        "| Cohort | n | control top-1 | LOPO top-1 | Δ | discordant (ctrl-only/lopo-only) | McNemar p | ctrl top-5/10 | lopo top-5/10 |"
    )
    lines.append("|---|--:|--:|--:|--:|:--:|--:|--:|--:|")
    for name, sub in strata.items():
        cr = [r["ctrl"] for r in sub]
        lr = [r["lopo"] for r in sub]
        pt = paired_top1(cr, lr)
        rec = {
            "n": pt["n"],
            "control_top1": pt["acc_a"],
            "lopo_top1": pt["acc_b"],
            "delta": pt["delta"],
            "mcnemar_p": pt["mcnemar_p"],
            "discordant_ctrl_only": pt["discordant_a_only"],
            "discordant_lopo_only": pt["discordant_b_only"],
            "control_top5": topk(cr, 5),
            "control_top10": topk(cr, 10),
            "lopo_top5": topk(lr, 5),
            "lopo_top10": topk(lr, 10),
        }
        out["strata"].setdefault(name, {})["control_vs_lopo"] = rec
        lines.append(
            f"| {name} | {pt['n']} | {pt['acc_a']:.3f} | {pt['acc_b']:.3f} | {pt['delta']:+.3f} "
            f"| {pt['discordant_a_only']}/{pt['discordant_b_only']} | {pt['mcnemar_p']} "
            f"| {topk(cr, 5):.3f}/{topk(cr, 10):.3f} | {topk(lr, 5):.3f}/{topk(lr, 10):.3f} |"
        )

    # 2. LOPO Cell S vs K and vs M, full + fair cohort
    lines.append(
        "\n## 2. Does geno_agent's advantage survive source-paper removal? (LOPO vs curated tools)\n"
    )
    lines.append(
        "| Cohort | n | LOPO top-1 | Exomiser K top-1 | Δ(S-K) | p(S-K) | LIRICAL M top-1 | Δ(S-M) | p(S-M) |"
    )
    lines.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
    for name in ("full", "overlap_absent (FAIR)"):
        sub = strata[name]
        lr = [r["lopo"] for r in sub]
        kk = [r["k"] for r in sub]
        mm = [r["m"] for r in sub]
        sk = paired_top1(lr, kk)
        sm = paired_top1(lr, mm)
        out["strata"].setdefault(name, {})["lopo_vs_K"] = sk
        out["strata"][name]["lopo_vs_M"] = sm
        lines.append(
            f"| {name} | {sk['n']} | {sk['acc_a']:.3f} | {sk['acc_b']:.3f} | {sk['delta']:+.3f} | {sk['mcnemar_p']} "
            f"| {sm['acc_b']:.3f} | {sm['delta']:+.3f} | {sm['mcnemar_p']} |"
        )

    # 3. leak cross-tab by overlap status
    lines.append("\n## 3. Source-paper-in-retrieval leak, by annotation-overlap status\n")
    lines.append("| Cohort | n | source-in-causal-pool rate |")
    lines.append("|---|--:|--:|")
    for name, sub in strata.items():
        rate = round(sum(1 for r in sub if r["src_in_pool"]) / len(sub), 4) if sub else 0.0
        out["strata"].setdefault(name, {})["source_in_pool_rate"] = rate
        lines.append(f"| {name} | {len(sub)} | {rate:.3f} |")

    # 4. per-MONDO control vs LOPO top-1
    lines.append("\n## 4. Per-MONDO control vs LOPO top-1\n")
    lines.append("| MONDO | n | control | LOPO | Δ |")
    lines.append("|---|--:|--:|--:|--:|")
    cats = sorted({r["category"] for r in rows})
    out["per_mondo"] = {}
    for cat in cats:
        sub = subset(lambda r, c=cat: r["category"] == c)
        cr = [r["ctrl"] for r in sub]
        lr = [r["lopo"] for r in sub]
        pt = paired_top1(cr, lr)
        out["per_mondo"][cat] = {
            "n": pt["n"],
            "control_top1": pt["acc_a"],
            "lopo_top1": pt["acc_b"],
            "delta": pt["delta"],
        }
        lines.append(
            f"| {cat} | {pt['n']} | {pt['acc_a']:.3f} | {pt['acc_b']:.3f} | {pt['delta']:+.3f} |"
        )

    md_path = args.lopo_root / f"_lopo_full_results_cell_{args.cell}.md"
    json_path = args.lopo_root / f"_lopo_full_results_cell_{args.cell}.json"
    md_path.write_text("\n".join(lines) + "\n")
    json_path.write_text(json.dumps(out, indent=2))
    print("\n".join(lines))
    print(f"\nWrote {md_path}\n      {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
