"""Export tidy CSVs for the P1 figures so they can be rendered in R.

The science stays in Python. Figure 4 in particular needs Resnik best-match-average
similarity scored against the pinned HPO release, which is what
``18b_build_hard_candidates.py`` already does and what the deposit archives — it is
not something to reimplement in a plotting language. This script runs that
computation once and writes plain CSVs; ``render_p1_figures.R`` reads them and does
the drawing.

Outputs (into --out, default reports/figures/P1_figures/data/):

    fig1_funnel.csv        stage, n, dropped, reason        CONSORT flow
    fig3a_categories.csv   category, n, oversampled         disease-category counts
    fig3b_overlap.csv      category, stratum, n             overlap-present / absent
    fig3c_years.csv        year, n                          source-publication years
    fig3d_hpo.csv          n_terms, n_cases                 HPO terms per case
    fig4a_similarity.csv   variant, bma                     distractor similarity
    fig4b_separability.csv variant, causal, hardest         per-case separability
    figure_notes.json      the derived numbers the captions quote

Run from the project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/manuscript/export_figure_data.py
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CATS = ["developmental", "immunological", "metabolic", "neurological"]
# Immunological was oversampled to protect subgroup precision; the figure marks it.
OVERSAMPLED = "immunological"
# Verified stage-14 drop breakdown (9,588 -> 6,382; 3,206 dropped).
DROP = {
    "Fewer than 3 HPO terms": 1155,
    "No single ascertained causal gene": 69,
    "Chromosomal or mitochondrial disease": 1982,
}


def _resolve(env: str, candidates: list[Path], needed: str) -> Path:
    override = os.environ.get(env)
    if override:
        if not (Path(override) / needed).exists():
            raise SystemExit(f"{env}={override} does not contain {needed}.")
        return Path(override)
    for c in candidates:
        if (c / needed).exists():
            return c
    raise SystemExit(f"Could not locate {needed}. Set {env}=<directory>.")


def _write(path: Path, header: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {path.relative_to(ROOT)}  ({len(rows)} rows)")


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _wc(p: Path) -> int:
    return sum(1 for line in p.open(encoding="utf-8") if line.strip())


def _pmid(case_id: str) -> str:
    m = re.search(r"PMID[_:](\d+)", case_id)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Export tidy CSVs for the P1 figures.")
    ap.add_argument("--out", type=Path, default=ROOT / "reports/figures/P1_figures/data")
    args = ap.parse_args()
    out = args.out

    stage = _resolve(
        "COHORT_DIR",
        [
            ROOT / "figshare_uploads/_staging/genoagent-cohort-n1047-v1.0",
            ROOT / "data/test_cases_1050",
        ],
        "test_cases.jsonl",
    )
    hard = _resolve(
        "COHORT_HARD_DIR",
        [
            ROOT / "figshare_uploads/_staging/genoagent-cohort-hard-n1047-v1.0",
            ROOT / "data/test_cases_hard",
        ],
        "test_cases_hard.jsonl",
    )
    print(f"cohort      : {stage}\nhard variant: {hard}\noutput      : {out}\n")

    recs = _jsonl(stage / "test_cases.jsonl")
    overlap = {
        r["case_id"]: r["overlap"]
        for r in json.loads((stage / "annotation_overlap.json").read_text(encoding="utf-8"))[
            "records"
        ]
    }
    # pmid_dates.json wraps the mapping in a "dates" key alongside meta;
    # read that rather than the envelope, or every year lookup silently misses.
    _pd = json.loads((stage / "pmid_dates.json").read_text(encoding="utf-8"))
    dates = _pd.get("dates", _pd)
    final = len(recs)

    # ---- Figure 1: CONSORT funnel -------------------------------------------
    loaded = _wc(stage / "01_all_phenopackets.jsonl")
    elig = _wc(stage / "02_eligible.jsonl")
    categ = _wc(stage / "03_categorized.jsonl")
    drawn = _wc(stage / "04_sampled.jsonl")
    rows = [
        ("Phenopackets loaded", loaded, 0, ""),
        (
            "Passed inclusion criteria",
            elig,
            loaded - elig,
            "; ".join(f"{k}: {v:,}" for k, v in DROP.items()),
        ),
        ("Mapped to a MONDO stratum", categ, elig - categ, "No matching MONDO root"),
        ("Stratified sample drawn", drawn, 0, ""),
        ("Analytic cohort", final, drawn - final, "Causal gene not protein-coding"),
    ]
    _write(out / "fig1_funnel.csv", ["stage", "n", "dropped", "reason"], rows)

    # ---- Figure 3 ------------------------------------------------------------
    cat = Counter(r["category"] for r in recs)
    _write(
        out / "fig3a_categories.csv",
        ["category", "n", "oversampled"],
        [(c.capitalize(), cat[c], int(c == OVERSAMPLED)) for c in CATS],
    )

    rows = []
    for c in CATS:
        ids = [r["case_id"] for r in recs if r["category"] == c]
        present = sum(overlap.get(i, 0) for i in ids)
        rows.append((c.capitalize(), "Overlap-present", present))
        rows.append((c.capitalize(), "Overlap-absent", len(ids) - present))
    _write(out / "fig3b_overlap.csv", ["category", "stratum", "n"], rows)

    years = Counter(
        int(dates[_pmid(r["case_id"])][:4]) for r in recs if _pmid(r["case_id"]) in dates
    )
    _write(out / "fig3c_years.csv", ["year", "n"], sorted(years.items()))

    hpo = Counter(len(r["hpo_terms"]) for r in recs)
    _write(out / "fig3d_hpo.csv", ["n_terms", "n_cases"], sorted(hpo.items()))

    # ---- Figure 4: needs Resnik BMA, so reuse the deposited implementation ----
    spec = importlib.util.spec_from_file_location(
        "hb", ROOT / "scripts/cases/18b_build_hard_candidates.py"
    )
    hb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hb)

    # Mirror exactly what render_p1_figures.py does, so the two renderers cannot
    # drift: parse the pinned HPO release, build the ancestor closure, load the
    # gene annotations, compute information content, and make the Resnik scorer.
    parents, alt = hb.parse_hpo_obo(hb.HPO_DIR / "hp.obo")
    valid = frozenset(parents)
    anc = hb.build_ancestors(parents)
    gene_hpo, _ = hb.load_gene_annotations(hb.HPO_DIR / "genes_to_phenotype.txt", alt, valid)
    ic = hb.compute_ic(gene_hpo, anc)
    resnik = hb.make_similarity(anc, ic)

    hard_lists = {
        r["case_id"]: r["candidate_genes"] for r in _jsonl(hard / "test_cases_hard.jsonl")
    }

    sim_rows: list[tuple] = []
    sep_rows: list[tuple] = []
    for r in recs:
        ct = frozenset(r["hpo_terms"])
        causal = hb.bma(ct, gene_hpo.get(r["causal_gene"], frozenset()), resnik)
        rnd = [
            hb.bma(ct, gene_hpo.get(g, frozenset()), resnik)
            for g in r["candidate_genes"]
            if g != r["causal_gene"]
        ]
        hrd = [
            hb.bma(ct, gene_hpo.get(g, frozenset()), resnik)
            for g in hard_lists.get(r["case_id"], [])
            if g != r["causal_gene"]
        ]
        sim_rows += [("Random", round(x, 4)) for x in rnd]
        sim_rows += [("Hard", round(x, 4)) for x in hrd]
        if rnd:
            sep_rows.append(("Random", round(causal, 4), round(max(rnd), 4)))
        if hrd:
            sep_rows.append(("Hard", round(causal, 4), round(max(hrd), 4)))

    _write(out / "fig4a_similarity.csv", ["variant", "bma"], sim_rows)
    _write(out / "fig4b_separability.csv", ["variant", "causal", "hardest"], sep_rows)

    causal_all = [c for _, c, _ in sep_rows if _ == "Random"] or [c for _, c, _ in sep_rows]
    notes = {
        "n_cases": final,
        "category_counts": {c: cat[c] for c in CATS},
        "overlap_present": sum(overlap.values()),
        "overlap_absent": final - sum(overlap.values()),
        "median_causal_bma": round(sorted(causal_all)[len(causal_all) // 2], 2),
        "ties_random_pct": round(
            100
            * sum(1 for v, c, h in sep_rows if v == "Random" and h >= c)
            / max(1, sum(1 for v, _, _ in sep_rows if v == "Random")),
            1,
        ),
        "ties_hard_pct": round(
            100
            * sum(1 for v, c, h in sep_rows if v == "Hard" and h >= c)
            / max(1, sum(1 for v, _, _ in sep_rows if v == "Hard")),
            1,
        ),
    }
    (out / "figure_notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
    print(f"  {(out / 'figure_notes.json').relative_to(ROOT)}")
    print("\nNow render with:  Rscript scripts/manuscript/render_p1_figures.R")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
