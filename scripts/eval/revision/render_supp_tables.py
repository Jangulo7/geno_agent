"""Generate Supplementary Tables S2 and S3 from the revision JSON.

S2  Multiplicity correction for all three test families, on BOTH the case-level
    and the publication-clustered p-values, so a reader can see exactly which
    conclusions depend on the inference model.
S3  Design-weighted (Horvitz-Thompson) estimates for every system and subset,
    against the unweighted and equal-weight figures.

Both are standalone documents that compile on their own with pdfLaTeX, matching
the style of Supplementary Table S1.

Usage:
    python scripts/eval/revision/render_supp_tables.py \
        --out reports/_local/GenoAgent_P2_System/P2-correction
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import CELL_NAMES, OUT_DIR, REPO

PREAMBLE = r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=2cm]{geometry}
\usepackage{amssymb}
\usepackage{amsmath}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{siunitx}
\usepackage[hidelinks]{hyperref}
\usepackage{ragged2e}

\renewcommand{\arraystretch}{1.15}
\setlength{\LTcapwidth}{\textwidth}
\newcommand{\sig}{\textsuperscript{$\star$}}

\begin{document}
"""

SUBSET_LABEL = {
    "full": "Full cohort",
    "overlap_present": "Overlap-present",
    "overlap_absent": "Overlap-absent",
    "pre2020": "Pre-2020",
    "post2020": "Post-2020",
    "post2020_overlap_absent": "Post-2020 $\\times$ overlap-absent",
}

FAMILY_LABEL = {
    "primary": (
        "Primary family --- top-1 superiority of GenoAgent over each curated "
        "baseline on the overlap-absent subset"
    ),
    "supportive": "Supportive family --- full-cohort and post-2020 GenoAgent vs Exomiser",
    "supportive_hard": "Supportive family --- hard cohort, overlap-absent",
}


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, adj, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adj[k] = running
    return adj


def bh(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, adj, prev = len(items), {}, 1.0
    for i in range(m - 1, -1, -1):
        k, p = items[i]
        prev = min(prev, p * m / (i + 1))
        adj[k] = prev
    return adj


def fmt_p(p: float) -> str:
    if p < 1e-4:
        return "$<10^{-4}$"
    if p < 0.001:
        return f"{p:.5f}".rstrip("0")
    return f"{p:.4f}".rstrip("0").rstrip(".")


def star(p: float) -> str:
    return "\\sig" if p < 0.05 else ""


# ---------------------------------------------------------------------------
def table_s2() -> str:
    w4 = json.loads((OUT_DIR / "wp4_cluster_inference.json").read_text())
    contrasts = w4["contrasts"]

    fams: dict[str, list[dict]] = {}
    for c in contrasts:
        if c["family"] in FAMILY_LABEL:
            fams.setdefault(c["family"], []).append(c)

    rows = []
    for fam in ("primary", "supportive", "supportive_hard"):
        cs = fams.get(fam, [])
        if not cs:
            continue
        keys = [f"{c['cohort']}/{c['subset']}/{c['label']}" for c in cs]
        p_case = {k: c["p_mcnemar_exact_case_level"] for k, c in zip(keys, cs, strict=True)}
        p_clu = {k: c["p_cluster_permutation"] for k, c in zip(keys, cs, strict=True)}
        h_case, b_case = holm(p_case), bh(p_case)
        h_clu, b_clu = holm(p_clu), bh(p_clu)

        rows.append(f"\\multicolumn{{8}}{{@{{}}l}}{{\\textbf{{{FAMILY_LABEL[fam]}}}}}\\\\[2pt]")
        for k, c in zip(keys, cs, strict=True):
            # The subset is part of the identity of a contrast: the supportive
            # family contains the same pair of systems on two different subsets.
            label = (
                f"{c['system_a']} vs {c['system_b']} "
                f"({CELL_NAMES[c['system_b']].split(' (')[0]}), "
                f"{SUBSET_LABEL[c['subset']].lower()}"
            )
            rows.append(
                " & ".join(
                    [
                        label,
                        f"{c['n_cases']} ({c['n_publications']})",
                        f"${c['delta']:+.3f}$",
                        fmt_p(p_case[k]),
                        fmt_p(h_case[k]) + star(h_case[k]),
                        fmt_p(b_case[k]),
                        fmt_p(p_clu[k]),
                        fmt_p(h_clu[k]) + star(h_clu[k]),
                    ]
                )
                + " \\\\"
            )
            _ = b_clu  # BH on clustered p reported in the JSON, omitted here for width
        rows.append("\\addlinespace")

    body = "\n".join(rows)

    return (
        PREAMBLE
        + r"""
\begin{center}
{\large\bfseries Supplementary Table S2 --- Multiplicity correction}
\end{center}

\noindent This table gives every hypothesis test in the manuscript's three
pre-specified families under \emph{both} inference models, so that the effect of
respecting the clustering of cases within source publications is visible test by
test rather than asserted.\\[4pt]
\textbf{Families.} The primary family is the two contrasts fixed in the
version-controlled analysis plan (\texttt{paper\_extension\_plan\_v3.md} \S3b,
commit \texttt{8ebf6f4}, 2026-05-17) before the annotation-overlap flag was
computed (commit \texttt{308fb2e}, 2026-05-23). The hard-cohort family could not
have belonged to it: the hard candidate lists were not built until commit
\texttt{8b8f76a} (2026-06-28). Each family is corrected separately.\\[4pt]
\textbf{Inference.} Case-level $p$ is the exact McNemar test on per-case top-1
correctness. Clustered $p$ is a cluster-level sign permutation test
(\num{10000} permutations, seed 42) in which the sign of a discordance is flipped
one whole publication at a time, because cases from the same publication share a
source, frequently a causal gene, and by construction the overlap flag.
The \num{1047} cases derive from 415 publications; the overlap-absent subset
carries 282 cases from only 93.\\[4pt]
\textbf{Legend.} $n$ (pub) is cases (unique source publications).
$\Delta$ is GenoAgent $-$ comparator in top-1 accuracy.
\sig~marks survival of Holm correction at $\alpha = 0.05$ within the family.
Benjamini--Hochberg values on the clustered $p$ are in
\texttt{reports/p2\_revision/wp4\_cluster\_inference.json}.\\[6pt]

\footnotesize
\begin{longtable}{@{}>{\RaggedRight\arraybackslash}p{3.6cm} r r r r r r r@{}}
\toprule
 & & & \multicolumn{3}{c}{\textbf{Case-level}} &
 \multicolumn{2}{c}{\textbf{Publication-clustered}} \\
\cmidrule(lr){4-6}\cmidrule(lr){7-8}
\textbf{Contrast} & \textbf{$n$ (pub)} & \textbf{$\Delta$} &
\textbf{raw $p$} & \textbf{Holm} & \textbf{BH} &
\textbf{raw $p$} & \textbf{Holm} \\
\midrule
\endhead
"""
        + body
        + r"""
\bottomrule
\end{longtable}

\normalsize
\vspace{1em}
\noindent\textbf{Reading this table.} The primary family is significant at case
level and not under clustered inference. The manuscript reports the clustered
result as authoritative and states plainly that GenoAgent \emph{matches} rather
than exceeds the curated baselines on the standard candidate lists: of the 22 net
discordances favouring GenoAgent over Exomiser on the overlap-absent subset, 20
originate in a single publication (PMID 30968594, contributing 20 \emph{CYP21A2}
cases that GenoAgent ranks first 20 times and Exomiser none). Three
cluster-robust procedures beyond the permutation test agree: the publication-level
bootstrap CI includes zero, a publication-level paired $t$-test gives $p = 0.51$,
and a Wilcoxon signed-rank test on publication-level rates gives $p = 0.49$.

\medskip
\noindent Both supportive families retain a Holm-significant contrast against
Exomiser under clustering (post-2020, and the hard cohort), and the mechanistic
contrast against the LLM-only no-retrieval control is unaffected by the choice of
inference model.

\medskip
\noindent\emph{Generated by} \texttt{scripts/eval/revision/render\_supp\_tables.py}
\emph{from} \texttt{reports/p2\_revision/wp4\_cluster\_inference.json}.

\end{document}
"""
    )


# ---------------------------------------------------------------------------
def table_s3() -> str:
    w5 = json.loads((OUT_DIR / "wp5_design_weighted.json").read_text())

    wrows = []
    for cat, v in w5["weights"].items():
        wrows.append(
            f"{cat.capitalize()} & {v['eligible_pool']} & {v['analytic_cohort']} & "
            f"{v['inclusion_probability']:.4f} & {v['design_weight']:.2f} & "
            f"{w5['eligible_pool_composition'][cat] * 100:.1f}\\% \\\\"
        )

    order = ["K", "M", "D", "L", "S", "N", "O"]
    est = {(e["cell"], e["subset"]): e for e in w5["estimates"]}
    erows = []
    for sub in ("full", "overlap_present", "overlap_absent"):
        erows.append(
            f"\\multicolumn{{6}}{{@{{}}l}}{{\\textbf{{{SUBSET_LABEL[sub]}}} "
            f"($n = {est[('S', sub)]['n_cases']}$)}}\\\\[2pt]"
        )
        for cell in order:
            e = est.get((cell, sub))
            if e is None:
                continue
            lo, hi = e["design_weighted_ci95_cluster"]
            name = CELL_NAMES[cell]
            if cell == "S":
                name = f"\\textbf{{{name}}}"
            erows.append(
                f"{cell} --- {name} & {e['unweighted_top1']:.3f} & "
                f"{e['equal_weight_top1']:.3f} & {e['design_weighted_top1']:.3f} & "
                f"({lo:.3f}, {hi:.3f}) & "
                f"${e['design_weighted_top1'] - e['unweighted_top1']:+.3f}$ \\\\"
            )
        erows.append("\\addlinespace")

    drows = []
    for d in w5["paired_deltas"]:
        ulo, uhi = d["unweighted_ci95_cluster"]
        lo, hi = d["design_weighted_ci95_cluster"]
        excl = "yes" if d["design_weighted_ci_excludes_zero"] else "no"
        drows.append(
            f"{d['label']} & {SUBSET_LABEL[d['subset']]} & "
            f"${d['unweighted_delta']:+.3f}$ & ({ulo:+.3f}, {uhi:+.3f}) & "
            f"${d['design_weighted_delta']:+.3f}$ & ({lo:+.3f}, {hi:+.3f}) & {excl} \\\\"
        )

    return (
        PREAMBLE
        + r"""
\begin{center}
{\large\bfseries Supplementary Table S3 --- Design-weighted estimates for the
eligible population}
\end{center}

\noindent The analytic cohort is a \emph{disproportionate} stratified sample: the
four MONDO strata were drawn at rates from \SI{77}{\percent} of the eligible
immunological pool down to \SI{7.9}{\percent} of the neurological pool. An
unweighted cohort mean therefore estimates a quantity defined by the sampling
design, not by the eligible population, which is \SI{67.3}{\percent}
neurological. The companion resource paper releases the inclusion probabilities
precisely so that either quantity can be computed deliberately.\\[4pt]
This table reports, for every system and subset, the unweighted estimate (which
describes the sampled cohort), the equal-weight estimate (25\% per stratum, the
sensitivity analysis used in the previous version of this manuscript), and the
Horvitz--Thompson design-weighted estimate (which describes the eligible
population), each with a publication-clustered bootstrap interval
(\num{10000} resamples, seed 42).\\[6pt]

\textbf{Panel A. Sampling design and weights.}\\[4pt]
\footnotesize
\begin{tabular}{@{}l r r r r r@{}}
\toprule
\textbf{Category} & \textbf{Eligible pool} & \textbf{Analytic cohort} &
\textbf{Inclusion prob.} & \textbf{Design weight} & \textbf{Share of pool} \\
\midrule
"""
        + "\n".join(wrows)
        + r"""
\bottomrule
\end{tabular}

\normalsize
\vspace{1em}
\textbf{Panel B. Top-1 accuracy under three weighting schemes.}\\[4pt]
\footnotesize
\begin{longtable}{@{}>{\RaggedRight\arraybackslash}p{5.2cm} r r r r r@{}}
\toprule
\textbf{System} & \textbf{Unweighted} & \textbf{Equal-weight} &
\textbf{Design-weighted} & \textbf{95\% CI (clustered)} & \textbf{Shift} \\
\midrule
\endhead
"""
        + "\n".join(erows)
        + r"""
\bottomrule
\end{longtable}

\normalsize
\vspace{1em}
\textbf{Panel C. Paired differences, unweighted vs design-weighted.}\\[4pt]
\footnotesize
\begin{longtable}{@{}l >{\RaggedRight\arraybackslash}p{3.0cm} r r r r c@{}}
\toprule
 & & \multicolumn{2}{c}{\textbf{Unweighted}} &
 \multicolumn{2}{c}{\textbf{Design-weighted}} & \\
\cmidrule(lr){3-4}\cmidrule(lr){5-6}
\textbf{Contrast} & \textbf{Subset} & \textbf{$\Delta$} & \textbf{95\% CI} &
\textbf{$\Delta$} & \textbf{95\% CI} & \textbf{CI excl.\ 0} \\
\midrule
\endhead
"""
        + "\n".join(drows)
        + r"""
\bottomrule
\end{longtable}

\normalsize
\vspace{1em}
\noindent\textbf{Reading this table.} Design weighting attenuates GenoAgent's
margins over the curated baselines on the overlap-absent subset, from $+0.078$ to
$+0.045$ against Exomiser and from $+0.082$ to $+0.048$ against LIRICAL, with
both clustered intervals including zero. This is expected and was anticipated
before the analysis was run: the eligible pool is dominated by neurological
cases, and the overlap-absent neurological result is a three-way tie at 0.780.
The design-weighted contrast that does hold is GenoAgent against the LLM-only
no-retrieval control ($+0.129$, CI $[+0.008, +0.339]$), i.e.\ the contribution of
retrieval and the agentic workflow.

\medskip
\noindent The annotation-overlap signature is if anything stronger under design
weighting: LIRICAL's advantage over Exomiser is $+0.411$ on the overlap-present
subset and $-0.004$ on the overlap-absent one.

\medskip
\noindent The unweighted figures answer ``how do these systems compare on this
deliberately balanced benchmark''; the design-weighted figures answer ``how would
they compare on the eligible Phenopacket Store population''. The manuscript's
claim is about architecture classes rather than prevalence-weighted clinical
yield, and both are reported.

\medskip
\noindent\emph{Generated by} \texttt{scripts/eval/revision/render\_supp\_tables.py}
\emph{from} \texttt{reports/p2\_revision/wp5\_design\_weighted.json}.

\end{document}
"""
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/_local/GenoAgent_P2_System/P2-correction")
    args = ap.parse_args()
    out = (REPO / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "supp_table2_multiplicity.tex").write_text(table_s2())
    print(f"wrote {out / 'supp_table2_multiplicity.tex'}")
    (out / "supp_table3_design_weighted.tex").write_text(table_s3())
    print(f"wrote {out / 'supp_table3_design_weighted.tex'}")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
