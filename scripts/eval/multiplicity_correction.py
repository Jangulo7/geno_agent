"""Multiplicity correction for the paper's primary efficacy comparisons.

Genome Medicine reviewers will (rightly) ask whether the headline p-values
survive correction for multiple testing. This script reads the already-computed
paired McNemar p-values from the stratified + recency aggregations and applies
Holm (FWER) and Benjamini-Hochberg (FDR) corrections to a *pre-declared*
family of primary comparisons, writing a supplementary table.

Pre-declared primary endpoint (this study): **top-1 accuracy of geno_agent
(Cell S) versus each curated baseline (Exomiser Cell K, LIRICAL Cell M) on the
deconfounded fair cohort (overlap-absent)** — 2 tests. A broader supportive
family adds the full-cohort and post-2020 geno_agent-vs-Exomiser comparisons.

Run::

    PYTHONPATH=. python scripts/eval/multiplicity_correction.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
STRAT: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "_results_stratified.json"
RECENCY: Final[Path] = PROJECT_ROOT / "data" / "eval_1050" / "_results_recency.json"
OUT_MD: Final[Path] = PROJECT_ROOT / "reports" / "tables" / "supp_table_multiplicity.md"
OUT_JSON: Final[Path] = PROJECT_ROOT / "reports" / "tables" / "supp_table_multiplicity.json"


def get_p(doc: dict, subset: str, comp: str, metric: str = "top1") -> float | None:
    """Fetch a McNemar p-value from a stratified/recency aggregation document."""
    try:
        return doc["paired"][subset][comp]["metrics"][metric]["mcnemar_p"]
    except KeyError:
        return None


def holm(pvals: list[float]) -> list[float]:
    """Holm step-down adjusted p-values (order matches input)."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        val = (m - rank) * pvals[idx]
        running = max(running, val)
        adj[idx] = min(1.0, running)
    return adj


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR adjusted p-values (order matches input)."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        idx = order[rank]
        val = pvals[idx] * m / (rank + 1)
        prev = min(prev, val)
        adj[idx] = min(1.0, prev)
    return adj


def main() -> int:
    strat = json.loads(STRAT.read_text())
    recency = json.loads(RECENCY.read_text()) if RECENCY.exists() else {"paired": {}}

    # (label, raw p-value). M_vs_S carries the S-vs-M comparison (symmetric McNemar p).
    family: list[tuple[str, float | None]] = [
        (
            "geno_agent (S) vs Exomiser (K), top-1, FAIR cohort",
            get_p(strat, "overlap_absent", "S_vs_K"),
        ),
        (
            "geno_agent (S) vs LIRICAL (M), top-1, FAIR cohort",
            get_p(strat, "overlap_absent", "M_vs_S"),
        ),
    ]
    supportive: list[tuple[str, float | None]] = [
        ("geno_agent (S) vs Exomiser (K), top-1, full cohort", get_p(strat, "__all__", "S_vs_K")),
        (
            "geno_agent (S) vs Exomiser (K), top-1, post-2020",
            get_p(recency, "post_2020", "S_vs_K") or get_p(recency, "post2020", "S_vs_K"),
        ),
    ]

    def block(name: str, items: list[tuple[str, float | None]]) -> tuple[list[str], list[dict]]:
        pres = [(lbl, p) for lbl, p in items if p is not None]
        ps = [p for _, p in pres]
        h = holm(ps)
        bh = benjamini_hochberg(ps)
        lines = [
            f"### {name} ({len(pres)} tests)",
            "",
            "| Comparison | raw p | Holm p | BH p | survives alpha=0.05 (Holm) |",
            "|---|--:|--:|--:|:--:|",
        ]
        recs = []
        for (lbl, p), hp, bp in zip(pres, h, bh, strict=True):
            ok = "yes" if hp < 0.05 else "no"
            lines.append(f"| {lbl} | {p:.5f} | {hp:.5f} | {bp:.5f} | {ok} |")
            recs.append(
                {
                    "comparison": lbl,
                    "raw_p": p,
                    "holm_p": round(hp, 5),
                    "bh_p": round(bp, 5),
                    "survives_holm_0.05": hp < 0.05,
                }
            )
        lines.append("")
        return lines, recs

    lines = [
        "# Supplementary table — multiplicity correction",
        "",
        "Pre-declared primary endpoint: top-1 accuracy of geno_agent (Cell S) "
        "vs each curated baseline on the deconfounded fair cohort. Holm controls "
        "family-wise error; Benjamini-Hochberg controls FDR.",
        "",
    ]
    primary_lines, primary_recs = block("Primary family — fair-cohort top-1", family)
    supp_lines, supp_recs = block("Supportive family — full-cohort + recency top-1", supportive)
    lines += primary_lines + supp_lines

    all_primary_survive = all(r["survives_holm_0.05"] for r in primary_recs)
    verdict = (
        "All primary comparisons remain significant after Holm correction."
        if all_primary_survive
        else "At least one primary comparison does NOT survive Holm correction — revise claims."
    )
    lines += [f"**Verdict:** {verdict}", ""]

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    OUT_JSON.write_text(
        json.dumps(
            {
                "primary": primary_recs,
                "supportive": supp_recs,
                "all_primary_survive_holm": all_primary_survive,
            },
            indent=2,
        )
    )
    print("\n".join(lines))
    print(f"Wrote {OUT_MD}\n      {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
