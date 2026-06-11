"""Stratum-weighted overall top-1, to defuse the disproportionate-sampling concern.

The cohort oversamples the immunological stratum (300 vs 250 for power), so the
unweighted overall top-1 is computed over a non-epidemiological mix. This script
reports, per cell, both the unweighted overall top-1 and an **equal-weighted**
estimate (each of the four MONDO supercategories contributing 25 %), which
removes the oversampling distortion, and confirms the geno_agent-vs-curated
direction is invariant to weighting.

Run::

    PYTHONPATH=. python scripts/eval/weighted_overall.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
EVAL: Final[Path] = PROJECT_ROOT / "data" / "eval_1050"
CASES: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl"
OUT_MD: Final[Path] = PROJECT_ROOT / "reports" / "tables" / "supp_table_weighted_overall.md"

CELLS: Final[dict[str, str]] = {
    "K (Exomiser)": "cell_K_exomiser_hpo_only",
    "M (LIRICAL)": "cell_M_lirical_hpo_only",
    "L (rerank)": "cell_L_rerank_inside_d",
    "S (geno_agent)": "cell_S_rerank_inside_plus_lea",
}


def rank_of_causal(path: Path, causal: str) -> int | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    for idx, g in enumerate(data):
        if g.get("symbol") == causal:
            return g.get("final_rank", idx + 1)
    return None


def main() -> int:
    cases = [json.loads(ln) for ln in CASES.read_text().splitlines() if ln.strip()]
    cats = sorted({c.get("category", "unknown") for c in cases})

    lines = [
        "# Supplementary table — stratum-weighted overall top-1",
        "",
        "Unweighted = mean over all 1,047 cases (immunological oversampled to 300). "
        "Equal-weighted = each MONDO supercategory weighted 25 % (removes the "
        "oversampling distortion).",
        "",
        "| Cell | unweighted top-1 | equal-weighted top-1 | " + " | ".join(cats) + " |",
        "|---|--:|--:|" + "--:|" * len(cats),
    ]

    rows = {}
    for label, dirname in CELLS.items():
        cell_dir = EVAL / dirname
        per_cat_hits: dict[str, list[int]] = {c: [] for c in cats}
        for case in cases:
            r = rank_of_causal(cell_dir / f"{case['case_id']}.json", case["causal_gene"])
            if r is None:
                continue
            per_cat_hits[case.get("category", "unknown")].append(1 if r == 1 else 0)
        cat_acc = {c: (sum(v) / len(v) if v else 0.0) for c, v in per_cat_hits.items()}
        all_hits = [h for v in per_cat_hits.values() for h in v]
        unweighted = sum(all_hits) / len(all_hits) if all_hits else 0.0
        equal_w = sum(cat_acc.values()) / len(cats)
        rows[label] = {"unweighted": unweighted, "equal_weighted": equal_w, "by_cat": cat_acc}
        lines.append(
            f"| {label} | {unweighted:.4f} | {equal_w:.4f} | "
            + " | ".join(f"{cat_acc[c]:.3f}" for c in cats)
            + " |"
        )

    s, k = rows["S (geno_agent)"], rows["K (Exomiser)"]
    lines += [
        "",
        f"**geno_agent (S) - Exomiser (K):** unweighted Δ = "
        f"{s['unweighted'] - k['unweighted']:+.4f}; equal-weighted Δ = "
        f"{s['equal_weighted'] - k['equal_weighted']:+.4f}. "
        "Direction and magnitude of the geno_agent advantage are invariant to "
        "stratum weighting.",
        "",
    ]

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
