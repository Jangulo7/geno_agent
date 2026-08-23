#!/usr/bin/env python3
"""Render the four figures of the P1 Data Descriptor from the released cohort.

This is the generator that produced the published figures. It supersedes
``P1_figures.ipynb``, which drifted out of date (its Figure 2 still described a
MeSH filter over ~3.4M articles; the corpus gate is lexical and the indexed set is
2.25M). Provenance check when this script was promoted into the repository:
re-running it reproduced ``fig4_hard_vs_random_separability.png`` byte-for-byte
against the deployed file, and left fig2 and fig3 unchanged.

Figures produced:

- ``fig1_consort_flow.png`` --- CONSORT-style cohort selection flow
- ``fig2_index_pipeline.png`` --- deterministic index-build pipeline schematic
- ``fig3_cohort_characterisation.png`` --- category, overlap, recency, HPO depth
- ``fig4_hard_vs_random_separability.png`` --- standard vs hard candidate lists

It also writes ``release/cohort/difficulty_tie_split.json``, decomposing the
"a distractor matches or exceeds the causal gene" figure into strict exceedances
and ties, since that number is quoted in Technical Validation.

Inputs. The cohort files are **not** carried in this repository --- they are
deposited on Figshare under CC BY 4.0. The script resolves them from, in order:
``$COHORT_DIR`` / ``$COHORT_HARD_DIR``; the local Figshare staging folders; the
local pipeline output under ``data/``. Download the two deposits and point
``COHORT_DIR``/``COHORT_HARD_DIR`` at them if you have neither:

- standard cohort  doi:10.6084/m9.figshare.32814449
- hard variant     doi:10.6084/m9.figshare.32816468

Figure 4 additionally imports the Resnik/BMA machinery from
``scripts/cases/18b_build_hard_candidates.py`` and reads the pinned HPO release
under ``data/Human_Phenotype_Ontology/``.

Run from anywhere::

    python scripts/manuscript/render_p1_figures.py [--out DIR]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[2]


def _resolve(env: str, candidates: list[Path], needed: str, doi: str) -> Path:
    """Return the first readable cohort directory, or explain how to get one."""
    override = os.environ.get(env)
    if override:
        # An explicit override that does not resolve must fail loudly. Falling
        # through to a default would silently render figures from a different
        # cohort than the one the caller asked for.
        if not (Path(override) / needed).exists():
            raise SystemExit(f"{env}={override} does not contain {needed}.")
        return Path(override)
    for c in candidates:
        if (c / needed).exists():
            return c
    raise SystemExit(
        f"Could not locate {needed}.\n"
        f"Looked in: {', '.join(str(c) for c in candidates)}\n"
        f"The cohort is deposited on Figshare, not carried in this repository.\n"
        f"Download https://doi.org/{doi} and set {env}=<extracted directory>."
    )


STAGE = _resolve(
    "COHORT_DIR",
    [ROOT / "figshare_uploads/_staging/genoagent-cohort-n1047-v1.0", ROOT / "data/test_cases_1050"],
    "test_cases.jsonl",
    "10.6084/m9.figshare.32814449",
)
HARD = _resolve(
    "COHORT_HARD_DIR",
    [
        ROOT / "figshare_uploads/_staging/genoagent-cohort-hard-n1047-v1.0",
        ROOT / "data/test_cases_hard",
    ],
    "test_cases_hard.jsonl",
    "10.6084/m9.figshare.32816468",
)

_ap = argparse.ArgumentParser(description="Render the four P1 Data Descriptor figures.")
_ap.add_argument(
    "--out",
    type=Path,
    default=ROOT / "reports" / "figures",
    help="output directory (default: reports/figures)",
)
_ap.add_argument(
    "--consort-title",
    default="Figure 1 - CONSORT-style cohort selection flow",
    help=(
        "title drawn inside fig1. The figure number is settable because the same "
        "flow is numbered differently in different manuscripts; hard-coding it "
        "would make a caption disagree with the figure it labels."
    ),
)
_args = _ap.parse_args()
OUT = _args.out
OUT.mkdir(parents=True, exist_ok=True)
print(f"cohort     : {STAGE}\nhard variant: {HARD}\noutput      : {OUT}\n")

# verified stage-14 drop breakdown (9,588 -> 6,382; 3,206 dropped)
DROP = {
    "few_hpo": 1155,
    "no_single_gene": 69,
    "multi_gene": 0,
    "no_disease": 0,
    "excluded_disease": 1982,
}

recs = [
    json.loads(line)
    for line in (STAGE / "test_cases.jsonl").read_text().splitlines()
    if line.strip()
]
ov = {
    r["case_id"]: r["overlap"]
    for r in json.loads((STAGE / "annotation_overlap.json").read_text())["records"]
}
dates = json.loads((STAGE / "pmid_dates.json").read_text())["dates"]


def pmid_of(cid):
    return re.search(r"PMID_(\d+)", cid).group(1)


CATS = ["developmental", "immunological", "metabolic", "neurological"]

plt.rcParams.update(
    {
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.family": "DejaVu Sans",
    }
)

cat = Counter(r["category"] for r in recs)
n_overlap = sum(ov.values())
years = np.array([int(dates[pmid_of(r["case_id"])][:4]) for r in recs])
hpo_n = np.array([len(r["hpo_terms"]) for r in recs])


def wc(p):
    """Count lines in a staged provenance file."""
    with open(p) as fh:
        return sum(1 for _ in fh)


loaded = wc(STAGE / "01_all_phenopackets.jsonl")
elig_ii = wc(STAGE / "02_eligible.jsonl")
categ = wc(STAGE / "03_categorized.jsonl")
sampled = wc(STAGE / "04_sampled.jsonl")
final = len(recs)
cat_pool = Counter(
    json.loads(line)["category"]
    for line in (STAGE / "03_categorized.jsonl").read_text().splitlines()
    if line.strip()
)

# =============================================================================
# FIGURE 1 — CONSORT flow
# =============================================================================
fig, ax = plt.subplots(figsize=(9.6, 12.6))
ax.set_xlim(0, 12)
ax.set_ylim(0, 15)
ax.axis("off")
BLUE = {
    "boxstyle": "round,pad=0.5",
    "facecolor": "#eaf1f9",
    "edgecolor": "#2b6cb0",
    "linewidth": 1.5,
}
EXCL = {
    "boxstyle": "round,pad=0.45",
    "facecolor": "#fef5e7",
    "edgecolor": "#dd6b20",
    "linewidth": 1.3,
}
GREEN = {
    "boxstyle": "round,pad=0.6",
    "facecolor": "#cdeccf",
    "edgecolor": "#2f855a",
    "linewidth": 1.8,
}
TAN = {
    "boxstyle": "round,pad=0.6",
    "facecolor": "#fdf3e3",
    "edgecolor": "#c05621",
    "linewidth": 1.8,
}
MX = 3.5


def tb(x, y, t, style, fs=9.0, w="normal"):
    ax.text(x, y, t, ha="center", va="center", fontsize=fs, bbox=style, weight=w, zorder=3)


def down(y1, y2, x=MX):
    ax.annotate(
        "",
        xy=(x, y2),
        xytext=(x, y1),
        arrowprops={"arrowstyle": "-|>", "color": "#2b6cb0", "lw": 1.6},
    )


def side(y, n, fs=7.6):
    ax.annotate(
        "",
        xy=(7.0, y),
        xytext=(6.1, y),
        arrowprops={"arrowstyle": "-|>", "color": "#dd6b20", "lw": 1.2},
    )
    ax.text(9.3, y, n, ha="center", va="center", fontsize=fs, bbox=EXCL, zorder=3)


tb(
    MX,
    14.2,
    "GA4GH Phenopacket Store v0.1.26\n(public; literature-curated, gene-level SOLVED)\n"
    f"N = {loaded:,} phenopackets loaded",
    BLUE,
)
down(13.5, 12.85)
tb(
    MX,
    12.05,
    "Inclusion (i)-(ii) + disease-scope exclusions\n"
    "exactly 1 ascertained causal gene; >=3 HPO terms;\n"
    "disease annotated; not chromosomal / mitochondrial\n"
    f"N = {elig_ii:,}",
    BLUE,
    fs=8.4,
)
side(
    12.05,
    f"Excluded (N = {loaded - elig_ii:,}):\n"
    f"<3 HPO terms: {DROP['few_hpo']:,}\n"
    f"no single ascertained gene: {DROP['no_single_gene']}\n"
    f"multi-gene: {DROP['multi_gene']};  no disease: {DROP['no_disease']}\n"
    f"chromosomal / mitochondrial: {DROP['excluded_disease']:,}",
)
down(11.25, 10.55)
tb(
    MX,
    9.85,
    "Categorise into 4 MONDO supercategories (iii)\n"
    f"Eligible pool  N = {categ:,}\n"
    f"({cat_pool['developmental']} dev / {cat_pool['immunological']} imm / "
    f"{cat_pool['metabolic']} met / {cat_pool['neurological']:,} neu)",
    BLUE,
    fs=8.6,
)
side(9.85, f"Excluded:\nother MONDO\ncategories\n(N = {elig_ii - categ:,})")
down(9.05, 8.35)
tb(
    MX,
    7.55,
    "Disproportionate stratified sample (seed 42)\ntarget 250 / 300 / 250 / 250\n"
    f"Drawn  N = {sampled:,}",
    BLUE,
    fs=8.4,
)
side(7.55, f"Not drawn by\nstratified sampling\n(N = {categ - sampled:,})")
down(6.75, 6.05)
tb(
    MX,
    5.4,
    "Remove 3 non-protein-coding RNA causal genes\n(2x RNU4-2, 1x RNU2-2) at candidate-list stage",
    BLUE,
    fs=8.6,
)
down(4.95, 4.25)
tb(
    MX,
    3.6,
    f"ANALYTIC COHORT   n = {final:,}\n(250 dev / 300 imm / 250 met / 247 neu)",
    GREEN,
    fs=9.5,
    w="bold",
)
down(2.95, 2.3)
tb(
    MX,
    1.5,
    "Annotation-overlap stratification (per-PMID vs phenotype.hpoa)\n"
    f"Overlap-present  n = {n_overlap} ({100 * n_overlap / final:.1f}%)\n"
    f"Overlap-absent subset  n = {final - n_overlap} ({100 * (final - n_overlap) / final:.1f}%)",
    TAN,
    fs=8.6,
)
ax.set_title(_args.consort_title, fontsize=12, fontweight="bold", pad=8)
fig.savefig(OUT / "fig1_consort_flow.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("fig1 done | funnel", loaded, elig_ii, categ, sampled, final, "| drops", sum(DROP.values()))

# =============================================================================
# FIGURE 2 — index pipeline
# =============================================================================
fig, ax = plt.subplots(figsize=(11, 3.6))
ax.set_xlim(0, 12)
ax.set_ylim(0, 4)
ax.axis("off")
PB = {
    "boxstyle": "round,pad=0.45",
    "facecolor": "#eaf1f9",
    "edgecolor": "#2b6cb0",
    "linewidth": 1.5,
}
PG = {
    "boxstyle": "round,pad=0.45",
    "facecolor": "#cdeccf",
    "edgecolor": "#2f855a",
    "linewidth": 1.6,
}


def pb(x, y, t, style, fs=8.6):
    ax.text(x, y, t, ha="center", va="center", fontsize=fs, bbox=style, zorder=3)


def ar(x1, y1, x2, y2, c="#2b6cb0"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1), arrowprops={"arrowstyle": "-|>", "color": c, "lw": 1.6}
    )


pb(1.5, 2.6, "PMC OA full text\ngenetics relevance filter\n(~2.25M articles)", PB)
pb(4.2, 2.6, "Section-aware chunking\n512 tok / 50 overlap", PB)
pb(7.0, 2.6, "PubMedBERT dense (768-d)\n+ BM25 sparse", PB)
pb(9.9, 2.6, "Qdrant index\n52,777,395 chunks\nHNSW . cosine", PG)
pb(7.0, 0.8, "UUID5 content IDs\n(deterministic)", PB)
pb(9.9, 0.8, "Hybrid retrieval\n(RRF, Qdrant default)", PG)
ar(2.55, 2.6, 3.15, 2.6)
ar(5.3, 2.6, 5.85, 2.6)
ar(8.1, 2.6, 8.9, 2.6)
ar(7.0, 1.25, 9.3, 2.2)
ar(9.9, 2.2, 9.9, 1.25)
ax.text(
    6.0,
    3.7,
    "deterministic, version-pinned; regenerable chunk set + content identifiers",
    ha="center",
    va="center",
    fontsize=8.5,
    style="italic",
    color="#555",
)
ax.set_title(
    "Figure 2 - Deterministic PMC OA hybrid-index build pipeline",
    fontsize=12,
    fontweight="bold",
    pad=6,
)
fig.savefig(OUT / "fig2_index_pipeline.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("fig2 done")

# =============================================================================
# FIGURE 3 — cohort characterisation
# =============================================================================
C = {
    "developmental": "#4C72B0",
    "immunological": "#DD8452",
    "metabolic": "#55A868",
    "neurological": "#C44E52",
}
PRESENT, ABSENT = "#B0B0B0", "#2C7FB8"
fig, ax = plt.subplots(2, 2, figsize=(10.5, 8.4))
vals = [cat[c] for c in CATS]
bars = ax[0, 0].bar(range(4), vals, color=[C[c] for c in CATS], width=0.68)
ax[0, 0].set_xticks(range(4))
ax[0, 0].set_xticklabels([c.capitalize() for c in CATS], rotation=20, ha="right")
ax[0, 0].set_ylabel("Cases")
ax[0, 0].set_title("(a) Disease-category balance")
ax[0, 0].set_ylim(0, 345)
for b, v in zip(bars, vals, strict=False):
    ax[0, 0].text(b.get_x() + b.get_width() / 2, v + 6, str(v), ha="center", fontsize=9)

absent = [sum(1 for r in recs if r["category"] == c and ov[r["case_id"]] == 0) for c in CATS]
present = [sum(1 for r in recs if r["category"] == c and ov[r["case_id"]] == 1) for c in CATS]
tot_p, tot_a = sum(present), sum(absent)
ax[0, 1].bar(
    range(4),
    present,
    color=PRESENT,
    width=0.68,
    label=f"Overlap-present - leakage risk  ({tot_p}, {100 * tot_p / final:.1f}%)",
)
ax[0, 1].bar(
    range(4),
    absent,
    bottom=present,
    color=ABSENT,
    width=0.68,
    label=f"Overlap-absent subset  ({tot_a}, {100 * tot_a / final:.1f}%)",
)
ax[0, 1].set_xticks(range(4))
ax[0, 1].set_xticklabels([c[:5].capitalize() for c in CATS], rotation=20, ha="right")
ax[0, 1].set_ylabel("Cases")
ax[0, 1].set_title("(b) Annotation-overlap split")
ax[0, 1].set_ylim(0, 380)
ax[0, 1].legend(fontsize=7.2, loc="upper center", frameon=False)

ax[1, 0].hist(
    years,
    bins=np.arange(years.min(), years.max() + 2),
    color="#7A7A7A",
    edgecolor="white",
    linewidth=0.4,
)
ax[1, 0].axvline(2020, color="#C44E52", ls="--", lw=1.4)
ax[1, 0].text(
    0.02,
    0.95,
    f"2020 split:  pre {(years < 2020).sum()} / post {(years >= 2020).sum()}",
    transform=ax[1, 0].transAxes,
    ha="left",
    va="top",
    color="#C44E52",
    fontsize=8.5,
)
ax[1, 0].set_xlabel("Source-publication year")
ax[1, 0].set_ylabel("Cases")
ax[1, 0].set_title("(c) Publication-recency distribution")
ax[1, 0].xaxis.set_major_locator(MaxNLocator(integer=True, nbins=8))

ax[1, 1].hist(
    hpo_n,
    bins=np.arange(hpo_n.min(), hpo_n.max() + 2),
    color="#4C72B0",
    edgecolor="white",
    linewidth=0.4,
)
med = int(np.median(hpo_n))
ax[1, 1].axvline(med, color="#DD8452", ls="--", lw=1.4)
ax[1, 1].text(
    0.97,
    0.95,
    f"median {med}\n(range {hpo_n.min()}-{hpo_n.max()})",
    transform=ax[1, 1].transAxes,
    ha="right",
    va="top",
    color="#DD8452",
    fontsize=8.5,
)
ax[1, 1].set_xlabel("HPO terms per case")
ax[1, 1].set_ylabel("Cases")
ax[1, 1].set_title("(d) Phenotype-annotation depth")
fig.tight_layout(pad=1.5)
fig.savefig(OUT / "fig3_cohort_characterisation.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("fig3 done | overlap present/absent", tot_p, tot_a)

# =============================================================================
# FIGURE 4 — candidate-list difficulty (standard vs hard)
# =============================================================================
spec = importlib.util.spec_from_file_location(
    "hb", ROOT / "scripts/cases/18b_build_hard_candidates.py"
)
hb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hb)
parents, alt = hb.parse_hpo_obo(hb.HPO_DIR / "hp.obo")
valid = set(parents)
anc = hb.build_ancestors(parents)
gene_hpo, _ = hb.load_gene_annotations(hb.HPO_DIR / "genes_to_phenotype.txt", alt, valid)
ic = hb.compute_ic(gene_hpo, anc)
resnik = hb.make_similarity(anc, ic)


def ct_of(r):
    return [t for t in (alt.get(x, x) for x in r["hpo_terms"]) if t in valid]


std = {r["case_id"]: r for r in recs}
hard = {
    json.loads(line)["case_id"]: json.loads(line)
    for line in (HARD / "test_cases_hard.jsonl").read_text().splitlines()
    if line.strip()
}
causal_bma, rand_all, hard_all, rand_hardest, hard_hardest = [], [], [], [], []
for cid, r in std.items():
    ct = ct_of(r)
    causal = r["causal_gene"]
    causal_bma.append(hb.bma(ct, gene_hpo.get(causal, frozenset()), resnik))
    rb = [
        hb.bma(ct, gene_hpo.get(g, frozenset()), resnik)
        for g in r["candidate_genes"]
        if g != causal
    ]
    hbm = [
        hb.bma(ct, gene_hpo.get(g, frozenset()), resnik)
        for g in hard[cid]["candidate_genes"]
        if g != causal
    ]
    rand_all += rb
    hard_all += hbm
    rand_hardest.append(max(rb))
    hard_hardest.append(max(hbm))
causal_bma, rand_all, hard_all = map(np.array, (causal_bma, rand_all, hard_all))
rand_hardest, hard_hardest = np.array(rand_hardest), np.array(hard_hardest)
rand_frac = float((rand_hardest >= causal_bma).mean())
hard_frac = float((hard_hardest >= causal_bma).mean())

fig, ax = plt.subplots(1, 2, figsize=(10, 4.3))
hi = max(hard_all.max(), causal_bma.max())
b = np.linspace(0, hi, 40)
ax[0].hist(
    rand_all,
    bins=b,
    density=True,
    color="#9E9E9E",
    alpha=0.8,
    label="Random distractors (standard variant)",
)
ax[0].hist(
    hard_all,
    bins=b,
    density=True,
    color="#DD8452",
    alpha=0.65,
    label="Hard distractors (phenotype-similar)",
)
ax[0].axvline(
    np.median(causal_bma),
    color="#C44E52",
    ls="--",
    lw=1.6,
    label=f"Causal gene (median {np.median(causal_bma):.2f})",
)
ax[0].set_xlabel("Case-gene phenotypic similarity (Resnik BMA)")
ax[0].set_ylabel("Density")
ax[0].set_title("(a) Distractor phenotypic similarity")
ax[0].legend(fontsize=7.6, frameon=False, loc="upper right")
ax[1].scatter(
    rand_hardest,
    causal_bma,
    s=7,
    alpha=0.30,
    color="#9E9E9E",
    edgecolors="none",
    label=f"Random (ties causal: {100 * rand_frac:.1f}%)",
)
ax[1].scatter(
    hard_hardest,
    causal_bma,
    s=7,
    alpha=0.30,
    color="#DD8452",
    edgecolors="none",
    label=f"Hard (ties causal: {100 * hard_frac:.1f}%)",
)
lim = max(hard_hardest.max(), causal_bma.max()) * 1.05
ax[1].plot([0, lim], [0, lim], color="0.35", ls="--", lw=1)
ax[1].set_xlim(0, lim)
ax[1].set_ylim(0, lim)
ax[1].set_xlabel("Hardest distractor similarity (max BMA)")
ax[1].set_ylabel("Causal-gene similarity (BMA)")
ax[1].set_title("(b) Per-case separability")
ax[1].legend(fontsize=8, frameon=False, loc="lower right")
fig.tight_layout(pad=1.2)
fig.savefig(OUT / "fig4_hard_vs_random_separability.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"fig4 done | ties causal: random {100 * rand_frac:.1f}% vs hard {100 * hard_frac:.1f}%")

# =============================================================================
# Task H4 — decompose the "matches or exceeds" fraction.
# A tie at BMA 0.00 = 0.00 means the causal gene itself has no informative HPO
# annotation, which is qualitatively different from a genuinely competitive
# distractor. Report the split so the headline percentage is not over-read.
# =============================================================================
EPS = 1e-9
h4 = {}
for name, hardest in (("standard", rand_hardest), ("hard", hard_hardest)):
    strict = hardest > causal_bma + EPS
    tie = np.abs(hardest - causal_bma) <= EPS
    tie_zero = tie & (causal_bma <= EPS)
    tie_pos = tie & (causal_bma > EPS)
    n = len(causal_bma)
    h4[name] = {
        "n_cases": int(n),
        "matches_or_exceeds_n": int((strict | tie).sum()),
        "matches_or_exceeds_pct": round(100 * float((strict | tie).mean()), 2),
        "strict_exceeds_n": int(strict.sum()),
        "strict_exceeds_pct": round(100 * float(strict.mean()), 2),
        "tie_at_zero_n": int(tie_zero.sum()),
        "tie_at_zero_pct": round(100 * float(tie_zero.mean()), 2),
        "tie_above_zero_n": int(tie_pos.sum()),
        "tie_above_zero_pct": round(100 * float(tie_pos.mean()), 2),
        "causal_bma_is_zero_n": int((causal_bma <= EPS).sum()),
    }
    d = h4[name]
    print(
        f"H4 {name:<9} matches-or-exceeds {d['matches_or_exceeds_n']} "
        f"({d['matches_or_exceeds_pct']}%) = strict {d['strict_exceeds_n']} "
        f"({d['strict_exceeds_pct']}%) + tie@0 {d['tie_at_zero_n']} "
        f"({d['tie_at_zero_pct']}%) + tie>0 {d['tie_above_zero_n']} "
        f"({d['tie_above_zero_pct']}%)"
    )

h4_out = ROOT / "release" / "cohort" / "difficulty_tie_split.json"
h4_out.parent.mkdir(parents=True, exist_ok=True)
h4_out.write_text(
    json.dumps(
        {
            "meta": {
                "metric": "case-to-gene Resnik best-match-average (BMA) phenotypic similarity",
                "comparison": "hardest distractor vs causal gene, per case",
                "hpo_version": "v2026-02-16",
                "annotation_source": "genes_to_phenotype.txt",
                "tie_tolerance": EPS,
                "note": (
                    "tie_at_zero counts cases where BOTH the causal gene and the hardest "
                    "distractor score 0.00, i.e. the causal gene carries no informative "
                    "HPO annotation -- not a competitive distractor."
                ),
            },
            "variants": h4,
        },
        indent=2,
    )
    + "\n"
)
print("wrote", h4_out)
print("ALL FIGURES WRITTEN TO", OUT)
