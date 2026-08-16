"""Render every figure and generated table the revised P2 manuscript needs.

Figures are built from the machine-readable outputs in ``reports/p2_revision/``
and the saved per-case artefacts, so the manuscript, the figures and the JSON all
derive from one computation.

Palette note. The previous P2 palette placed the LLM-only control (magenta
#b83280) next to GenoAgent (green #2f855a); under deuteranopia those two separate
by only DeltaE 5.2, and that pair carries the paper's most important robust
contrast. The palette below is an Okabe-Ito-derived set validated with the
dataviz palette validator: all six categorical checks pass, and the
GenoAgent-vs-control pair separates by DeltaE 11.3 (protan) and 25.7 (normal
vision). The one remaining pair inside the 6--8 CVD band (GenoAgent vs
+CE-rerank) is always accompanied by direct value labels, which is the secondary
encoding that band requires.

Usage:
    python scripts/eval/revision/render_revision_figures.py \
        --out reports/_local/P2_latest_version/GenoAgent_P2_System/fig
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CATEGORIES,
    EVAL_STD,
    OUT_DIR,
    REPO,
    load_cases,
    load_ranks,
    subset,
)


def d3(x: float) -> str:
    """3 dp, rounded half-up by value, so bar labels agree with the tables.

    ``f"{x:.3f}"`` rounds half-to-even and resolves the tie on the float's binary
    representation; the tables now round by value, and a figure label that
    disagreed with its table by one unit is the defect class this avoids.
    """
    return str(Decimal(str(float(x))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


# --- validated categorical palette -----------------------------------------
CELL_COLORS = {
    "K": "#0072B2",  # Exomiser        -- blue
    "M": "#E69F00",  # LIRICAL         -- orange
    "D": "#56B4E9",  # multi-agent     -- sky
    "L": "#D55E00",  # + CE-rerank     -- vermillion
    "S": "#2f855a",  # GenoAgent       -- signature green (retained)
    "O": "#CC79A7",  # LLM-only        -- reddish purple
}
CELL_LABELS = {
    "K": "Exomiser (HPO-only)",
    "M": "LIRICAL (HPO-only)",
    "D": "Multi-agent baseline",
    "L": "+ CE-rerank (inside)",
    "S": "GenoAgent",
    "O": "LLM-only (no retrieval)",
}
PRESENT = "#8c8c8c"  # overlap-present -- neutral grey
ABSENT = "#2f855a"  # overlap-absent  -- signature green
INK = "#2d3748"
GRID = "#d9d9d9"

plt.rcParams.update(
    {
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.size": 10,
        "font.family": "DejaVu Sans",
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#9aa0a6",
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
    }
)


def load_json(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text())


def grid(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# Figure 3 -- per-MONDO top-1
# ---------------------------------------------------------------------------
def fig_per_mondo(out: Path) -> None:
    cells = ["K", "M", "D", "L", "S", "O"]
    cases = load_cases()
    hits = {
        c: {cid: int(r is not None and r <= 1) for cid, r in load_ranks(c).items()} for c in cells
    }

    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    width = 0.13
    x = np.arange(len(CATEGORIES))

    for i, cell in enumerate(cells):
        vals, ns = [], []
        for cat in CATEGORIES:
            sub = [c for c in cases if c.category == cat]
            vals.append(float(np.mean([hits[cell][c.case_id] for c in sub])))
            ns.append(len(sub))
        pos = x + (i - (len(cells) - 1) / 2) * width
        ax.bar(pos, vals, width * 0.88, color=CELL_COLORS[cell], label=CELL_LABELS[cell], zorder=3)
        for p, v in zip(pos, vals, strict=True):
            ax.text(
                p,
                v + 0.012,
                f"{v:.2f}",
                ha="center",
                va="bottom",
                fontsize=6.0,
                color=INK,
                rotation=90,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{c.capitalize()}\n(n={sum(1 for k in cases if k.category == c)})" for c in CATEGORIES]
    )
    ax.set_ylabel("Top-1 accuracy")
    ax.set_ylim(0, 1.08)
    ax.set_title("Per-MONDO-supercategory top-1 accuracy (full cohort, n = 1,047)")
    grid(ax)
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16))
    fig.savefig(out / "fig3_per_mondo_top1.png")
    plt.close(fig)
    print("  fig3_per_mondo_top1.png")


# ---------------------------------------------------------------------------
# Figure 4 -- hard cohort, overlap-present vs overlap-absent
#
# This plotted full-vs-absent until the presubmission check: the caption and the
# main text both quote LIRICAL "collapses from 0.774 to 0.284", but 0.774 is the
# overlap-PRESENT value and the full-cohort bar reads 0.642, so the number a
# reader was sent here to find was not on the chart. The claim being made -- that
# the overlap signature is preserved and amplified -- is about the gap between the
# two strata, which a full-vs-absent chart cannot show at all, because the full
# cohort is a mixture of both.
# ---------------------------------------------------------------------------
def fig_hard(out: Path) -> None:
    cells = ["K", "M", "D", "L", "S"]
    present = [c.case_id for c in subset("overlap_present")]
    absent = [c.case_id for c in subset("overlap_absent")]

    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    x = np.arange(len(cells))
    w = 0.36

    pr, ab = [], []
    for cell in cells:
        ranks = load_ranks(cell, "hard")
        pr.append(float(np.mean([1 if (ranks[i] and ranks[i] <= 1) else 0 for i in present])))
        ab.append(float(np.mean([1 if (ranks[i] and ranks[i] <= 1) else 0 for i in absent])))

    ax.bar(x - w / 2, pr, w * 0.92, color=PRESENT, label="Overlap-present (n = 765)", zorder=3)
    ax.bar(x + w / 2, ab, w * 0.92, color=ABSENT, label="Overlap-absent (n = 282)", zorder=3)
    for xi, (a, b) in enumerate(zip(pr, ab, strict=True)):
        ax.text(xi - w / 2, a + 0.012, d3(a), ha="center", va="bottom", fontsize=8)
        ax.text(xi + w / 2, b + 0.012, d3(b), ha="center", va="bottom", fontsize=8)
        ax.annotate(
            "",
            xy=(xi + w / 2, b),
            xytext=(xi - w / 2, a),
            arrowprops={
                "arrowstyle": "->",
                "color": "#b0b0b0",
                "lw": 0.9,
                "connectionstyle": "arc3,rad=-0.25",
            },
            zorder=2,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [CELL_LABELS[c].replace(" (HPO-only)", "") for c in cells], rotation=12, ha="right"
    )
    ax.set_ylabel("Top-1 accuracy")
    # 0.86, not 0.78: LIRICAL's overlap-present bar is 0.774 and its value label
    # sits 0.012 above it, which the old limit clipped.
    ax.set_ylim(0, 0.86)
    ax.set_title(
        "Hard cohort (49 phenotype-similar distractors): overlap-present vs overlap-absent"
    )
    grid(ax)
    ax.legend(frameon=False, loc="upper right")
    fig.savefig(out / "fig4_hard_difficulty.png")
    plt.close(fig)
    print("  fig4_hard_difficulty.png")


# ---------------------------------------------------------------------------
# Figure 5 -- faithfulness vs correctness (RAGAS only; DeepEval withdrawn)
# ---------------------------------------------------------------------------
def fig_faithfulness(out: Path) -> None:
    from sklearn.metrics import roc_curve

    top1 = {cid: int(r is not None and r <= 1) for cid, r in load_ranks("S").items()}

    def load(path: Path):
        doc = json.loads(path.read_text())
        pairs = [
            (c["case_id"], c["faithfulness"])
            for c in doc["per_case"]
            if c.get("faithfulness") is not None and c["case_id"] in top1
        ]
        s = np.array([p[1] for p in pairs], dtype=float)
        y = np.array([top1[p[0]] for p in pairs], dtype=int)
        return s, y

    s100, y100 = load(EVAL_STD / "ragas_top1only_cell_S_n100.json")
    s600, y600 = load(EVAL_STD / "ragas_cell_S_n600.json")

    fig, axes = plt.subplots(1, 3, figsize=(12.4, 3.9))

    # panel 1: distribution by outcome (rank-1 run)
    ax = axes[0]
    bins = np.linspace(0, 1, 11)
    ax.hist(
        [s100[y100 == 1], s100[y100 == 0]],
        bins=bins,
        stacked=False,
        color=[ABSENT, "#b0b0b0"],
        label=["Top-1 correct", "Top-1 incorrect"],
        zorder=3,
        edgecolor="white",
        linewidth=0.6,
    )
    ax.set_xlabel("RAGAS faithfulness (rank-1 rationale)")
    ax.set_ylabel("Cases")
    ax.set_title(f"Faithfulness by outcome (n = {len(s100)})")
    grid(ax)
    ax.legend(frameon=False, fontsize=8)

    # panel 2: ROC on the larger run
    ax = axes[1]
    fpr, tpr, _ = roc_curve(y600, s600)
    tri = load_json("wp8_judge_provenance.json")["triage"]["ragas_full_n600_standard"]
    ax.plot(fpr, tpr, color=ABSENT, lw=2, zorder=3)
    ax.plot([0, 1], [0, 1], color="#b0b0b0", ls="--", lw=1, zorder=2)
    ax.set_xlabel("False-positive rate")
    ax.set_ylabel("True-positive rate")
    lo, hi = tri["auroc_ci95_cluster_bootstrap"]
    ax.set_title(f"ROC, full-response run (n = {len(s600)})")
    ax.text(
        0.96,
        0.08,
        f"AUROC {tri['auroc']:.3f}\n95% CI [{lo:.2f}, {hi:.2f}]",
        ha="right",
        va="bottom",
        fontsize=9,
        color=INK,
    )
    grid(ax, axis="both")

    # panel 3: observed accuracy across equal-count faithfulness quartiles.
    # Deliberately NOT drawn against an identity line: faithfulness is a grounding
    # score, not a predicted probability of correctness, so a 45-degree
    # "perfect calibration" reference would be meaningless. The cohort base rate
    # is the correct reference and is drawn instead.
    ax = axes[2]
    calib = tri["calibration_quartiles"]
    xs = np.arange(len(calib))
    ys = [c["observed_top1"] for c in calib]
    base = tri["prevalence_top1"]
    ax.axhline(base, color="#b0b0b0", ls="--", lw=1.2, zorder=2)
    ax.text(
        -0.42,
        base + 0.018,
        f"base rate {base:.2f}",
        ha="left",
        va="bottom",
        fontsize=8,
        color="#6b7280",
    )
    ax.bar(xs, ys, 0.62, color=ABSENT, zorder=3)
    for x_, c in zip(xs, calib, strict=True):
        ax.text(
            x_,
            c["observed_top1"] + 0.015,
            f"{c['observed_top1']:.2f}",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )
        ax.text(x_, 0.03, f"n={c['n']}", ha="center", va="bottom", fontsize=7.5, color="white")
    ax.set_xticks(xs)
    ax.set_xticklabels(
        [
            f"Q{c['quintile'] if 'quintile' in c else c['bin']}\n({c['mean_faithfulness']:.2f})"
            for c in calib
        ]
    )
    ax.set_xlabel("Faithfulness quartile (mean score)")
    ax.set_ylabel("Observed top-1 accuracy")
    ax.set_ylim(0, 1.0)
    ax.set_title("Accuracy by faithfulness quartile")
    grid(ax)

    fig.tight_layout()
    fig.savefig(out / "fig5_faithfulness_vs_correctness.png")
    plt.close(fig)
    print("  fig5_faithfulness_vs_correctness.png")


# ---------------------------------------------------------------------------
# Figure 7 -- annotation density
# ---------------------------------------------------------------------------
def fig_density(out: Path) -> None:
    import csv

    rows = list(csv.DictReader((OUT_DIR / "wp6_case_density.csv").open()))
    dens_p = np.array([float(r["annotation_density"]) for r in rows if r["overlap"] == "1"])
    dens_a = np.array([float(r["annotation_density"]) for r in rows if r["overlap"] == "0"])
    w6 = load_json("wp6_annotation_density.json")

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.2))

    # panel 1: density distribution by stratum.
    # Plotted as within-stratum percentages, not counts: the strata differ 765 vs
    # 282, so raw counts would not be comparable. The top bin is a clipped
    # pile-up and is labelled as such.
    ax = axes[0]
    cap = 120
    bins = np.linspace(0, cap, 25)
    for vals, colour, lbl in (
        (dens_p, PRESENT, f"Overlap-present (n = {len(dens_p)})"),
        (dens_a, ABSENT, f"Overlap-absent (n = {len(dens_a)})"),
    ):
        w = np.full(len(vals), 100.0 / len(vals))
        ax.hist(
            np.clip(vals, 0, cap),
            bins=bins,
            weights=w,
            color=colour,
            alpha=0.62,
            label=lbl,
            zorder=3,
            edgecolor="white",
            linewidth=0.5,
        )
    ax.axvline(float(np.median(dens_p)), color=PRESENT, ls="--", lw=1.4, zorder=4)
    ax.axvline(float(np.median(dens_a)), color=ABSENT, ls="--", lw=1.4, zorder=4)
    ax.text(
        cap,
        ax.get_ylim()[1] * 0.02,
        f"$\\geq${cap}  ",
        ha="right",
        va="bottom",
        fontsize=7.5,
        color="#6b7280",
    )
    ax.set_xlabel("Annotation rows for the case's disease(s)\n(own source publication excluded)")
    ax.set_ylabel("% of stratum")
    ax.set_title("Curation depth differs by overlap stratum")
    ax.text(
        0.97,
        0.62,
        f"median {np.median(dens_p):.0f} vs {np.median(dens_a):.0f}\n"
        f"{int((dens_p == 0).sum())} overlap-present cases\nhave zero; none absent",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        color=INK,
    )
    grid(ax)
    ax.legend(frameon=False, fontsize=8.5)

    # panel 2: crude vs density-adjusted overlap coefficient per system
    ax = axes[1]
    models = w6["adjusted_models"]
    order = ["M", "K", "S", "O"]
    models = sorted(models, key=lambda m: order.index(m["cell"]))
    y = np.arange(len(models))
    h = 0.34
    for i, m in enumerate(models):
        ax.barh(
            i - h / 2,
            m["crude_overlap_effect"],
            h * 0.9,
            color=CELL_COLORS[m["cell"]],
            alpha=0.45,
            zorder=3,
        )
        ax.barh(
            i + h / 2, m["adjusted_overlap_effect"], h * 0.9, color=CELL_COLORS[m["cell"]], zorder=3
        )
        ax.text(
            m["crude_overlap_effect"] + (0.008 if m["crude_overlap_effect"] >= 0 else -0.008),
            i - h / 2,
            f"{m['crude_overlap_effect']:+.3f}",
            va="center",
            fontsize=8,
            ha="left" if m["crude_overlap_effect"] >= 0 else "right",
            color=INK,
        )
        ax.text(
            m["adjusted_overlap_effect"] + (0.008 if m["adjusted_overlap_effect"] >= 0 else -0.008),
            i + h / 2,
            f"{m['adjusted_overlap_effect']:+.3f}",
            va="center",
            fontsize=8,
            ha="left" if m["adjusted_overlap_effect"] >= 0 else "right",
            color=INK,
            fontweight="bold",
        )
    ax.axvline(0, color="#6b7280", lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels([CELL_LABELS[m["cell"]] for m in models])
    ax.invert_yaxis()
    ax.set_xlabel("Overlap-absent effect on top-1 (percentage points / 100)")
    ax.set_xlim(-0.28, 0.30)
    ax.set_title("Pale = crude;  solid = adjusted for log annotation density")
    grid(ax, axis="x")

    fig.tight_layout()
    fig.savefig(out / "fig7_annotation_density.png")
    plt.close(fig)
    print("  fig7_annotation_density.png")


# ---------------------------------------------------------------------------
# Generated LaTeX: prompt-sensitivity table + macros
# ---------------------------------------------------------------------------
def table_prompt_sensitivity(out: Path) -> None:
    path = OUT_DIR / "wp8d_prompt_sensitivity.json"
    if not path.exists():
        (out / "tab_prompt_sensitivity.tex").write_text(
            "% wp8d_prompt_sensitivity.json not present when figures were rendered.\n"
            "\\begin{center}\\emph{Prompt-sensitivity table pending.}\\end{center}\n"
        )
        print("  tab_prompt_sensitivity.tex (placeholder -- WP8-D not finished)")
        return

    d = json.loads(path.read_text())
    pretty = {
        "production": "Production prompt (replayed)",
        "paraphrase_a": "Paraphrase A",
        "paraphrase_b": "Paraphrase B",
    }
    lines = [
        "\\begin{table}[H]",
        "\\centering",
        "\\caption{Prompt-sensitivity replay of the LEA stage "
        f"($n = {d['n_cases']}$, {d['n_cases'] // 4} per MONDO category, seed 42). "
        "Retrieval, rerank, evidence and decoding are bit-identical across variants; "
        "only the instruction wording differs. Produced by "
        "\\texttt{scripts/eval/revision/prompt\\_sensitivity.py} "
        "(\\texttt{reports/p2\\_revision/wp8d\\_prompt\\_sensitivity.json}).}",
        "\\label{tab:prompt}",
        "\\footnotesize",
        "\\begin{tabularx}{\\textwidth}{@{}L R R R R@{}}",
        "\\toprule",
        "\\textbf{Prompt variant} & \\textbf{Overall top-1} & "
        "\\textbf{Overlap-absent top-1} & \\textbf{No parseable ranking} & "
        "\\textbf{Agreement with published run} \\\\",
        "\\midrule",
    ]
    agree = {a["variant"]: a for a in d["agreement"]}
    for v in d["variants"]:
        a = agree.get(v["variant"], {})
        fair = v["top1_overlap_absent"]
        lines.append(
            f"{pretty.get(v['variant'], v['variant'])} & "
            f"{v['top1_overall']:.3f} & "
            f"{fair:.3f} ($n = {v['n_fair']}$) & "
            f"{v['n_parse_failures']} / {v['n']} & "
            f"{a.get('agreement_with_published_cell_S', float('nan')):.3f} \\\\"
        )
    lines += [
        "\\midrule",
        f"\\textbf{{Range across variants}} & "
        f"\\textbf{{{d['range_top1_overall_pp']:.1f}~pp}} & "
        f"\\textbf{{{d['range_top1_overlap_absent_pp']:.1f}~pp}} & --- & --- \\\\",
        "\\bottomrule",
        "\\end{tabularx}",
        "\\end{table}",
        "",
    ]
    (out / "tab_prompt_sensitivity.tex").write_text("\n".join(lines))
    print("  tab_prompt_sensitivity.tex")

    macros = (
        "% auto-generated by scripts/eval/revision/render_revision_figures.py\n"
        f"\\newcommand{{\\PROMPTRANGEALL}}{{{d['range_top1_overall_pp']:.1f}}}\n"
        f"\\newcommand{{\\PROMPTRANGEFAIR}}{{{d['range_top1_overlap_absent_pp']:.1f}}}\n"
    )
    (out / "prompt_macros.tex").write_text(macros)
    print("  prompt_macros.tex")


def copy_static(out: Path) -> None:
    src = REPO / "reports" / "_local" / "P2_latest_version" / "GenoAgent_P2_System" / "fig"
    for name in ("fig1_consort_flow.png", "fig2_architecture.png", "fig6_landscape_quadrant.png"):
        s = src / name
        if not s.exists():
            print(f"  MISSING {name}")
        elif s.resolve() == (out / name).resolve():
            # Rendering into the manuscript's own fig/ is now the default, so the
            # hand-made figures are already in place; copying would be a no-op
            # that raises SameFileError.
            print(f"  {name} (already in place)")
        else:
            shutil.copy2(s, out / name)
            print(f"  {name} (copied unchanged)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        # The P2-correction tree was retired to reports/_local/old/; figures
        # written there would land beside superseded sources and never reach
        # the manuscript.
        default="reports/_local/P2_latest_version/GenoAgent_P2_System/fig",
    )
    args = ap.parse_args()
    out = (REPO / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"rendering into {out}")

    copy_static(out)
    fig_per_mondo(out)
    fig_hard(out)
    fig_faithfulness(out)
    fig_density(out)
    table_prompt_sensitivity(out)


if __name__ == "__main__":
    main()
