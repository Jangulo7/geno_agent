"""C2 --- a bare Resnik/BMA phenotype-similarity ranker (Cell R).

This baseline does one thing: score each of a case's 50 candidates by the
symmetric best-match-average Resnik similarity between the case's HPO profile and
the gene's HPO annotations in ``genes_to_phenotype``, and rank by that score. No
knowledge base beyond the annotation file, no model, no retrieval.

It earns its place twice.

*On the standard cohort* it is a phenotype-similarity floor: whatever a system
achieves above this is attributable to something other than raw HPO similarity.

*On the hard cohort* it is the adversarially-optimal baseline, and this is the
point of the exercise. The hard distractors were selected as the 49 genes with the
highest Resnik BMA similarity to each case, using this very measure. A ranker that
scores by that measure therefore faces a candidate list constructed to defeat it,
and its hard-cohort accuracy bounds how much of the hard-variant difficulty is
construction bias rather than genuine discrimination difficulty. The manuscript
currently has to hedge about that quantity; this measures it.

Tie-handling matches the curated baselines: descending score, ties broken by the
case's seeded candidate-list order, so no positional information about the causal
gene leaks in.

Outputs ``reports/p2_revision/wp_c2_resnik_ranker.json`` and per-case rankings
under ``data/eval_1050/cell_R_resnik/`` and ``data/eval_hard/cell_R_resnik/``,
in the same schema as the other cells.

Seed 42. CPU only; no model inference.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    EVAL_HARD,
    EVAL_STD,
    REPO,
    SEED,
    cluster_bootstrap,
    metrics_for,
    subset,
    write_json,
)

HPO_DIR = REPO / "data" / "Human_Phenotype_Ontology"
COHORT = REPO / "data" / "test_cases_1050" / "test_cases.jsonl"
COHORT_HARD = REPO / "data" / "test_cases_hard" / "test_cases_hard.jsonl"


def _load_18b():
    """Import the hard-variant builder for its Resnik/BMA machinery.

    Reusing it rather than reimplementing guarantees the ranker scores with the
    identical similarity function that selected the hard distractors --- which is
    what makes the hard-cohort number an adversarial bound rather than an
    approximation of one.
    """
    path = REPO / "scripts" / "cases" / "18b_build_hard_candidates.py"
    spec = importlib.util.spec_from_file_location("hard18b", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hard18b"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_scorer():
    m = _load_18b()
    parents, alt_to_primary = m.parse_hpo_obo(HPO_DIR / "hp.obo")
    ancestors = m.build_ancestors(parents)
    gene_hpo, _ = m.load_gene_annotations(
        HPO_DIR / "genes_to_phenotype.txt", alt_to_primary, set(ancestors)
    )
    ic = m.compute_ic(gene_hpo, ancestors)
    resnik = m.make_similarity(ancestors, ic)

    def score(case_terms: list[str], gene: str) -> float:
        terms = [alt_to_primary.get(t, t) for t in case_terms]
        terms = [t for t in terms if t in ancestors]
        return m.bma(terms, gene_hpo.get(gene, frozenset()), resnik)

    return score, gene_hpo


def rank_cohort(jsonl: Path, out_dir: Path, score) -> dict[str, int | None]:
    """Write per-case rankings in the standard cell schema; return causal ranks."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ranks: dict[str, int | None] = {}
    for line in jsonl.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        cands = list(rec["candidate_genes"])
        causal = rec["causal_gene"]
        terms = rec["hpo_terms"]
        scored = [(score(terms, g), i, g) for i, g in enumerate(cands)]
        # descending score; ties by the case's seeded candidate order
        scored.sort(key=lambda x: (-x[0], x[1]))
        payload = [
            {
                "symbol": g,
                "is_causal": g == causal,
                "aggregate_confidence": round(float(s), 6),
                "supporting_chunks": [],
                "final_rank": r,
            }
            for r, (s, _, g) in enumerate(scored, start=1)
        ]
        (out_dir / f"{rec['case_id']}.json").write_text(json.dumps(payload))
        ranks[rec["case_id"]] = next(e["final_rank"] for e in payload if e["is_causal"])
    return ranks


def main() -> None:
    score, gene_hpo = build_scorer()
    print(f"HPO annotations loaded for {len(gene_hpo)} genes")

    results = {}
    for label, jsonl, out_dir in (
        ("standard", COHORT, EVAL_STD / "cell_R_resnik"),
        ("hard", COHORT_HARD, EVAL_HARD / "cell_R_resnik"),
    ):
        if not jsonl.exists():
            print(f"  {label}: cohort file missing at {jsonl}; skipped")
            continue
        print(f"  scoring {label} cohort ...", flush=True)
        ranks = rank_cohort(jsonl, out_dir, score)

        block = {}
        for sub in ("full", "overlap_present", "overlap_absent"):
            cases = subset(sub)
            ids = [c.case_id for c in cases if c.case_id in ranks]
            m = metrics_for(ranks, ids)

            def stat(cs, _r=ranks):
                v = [1 if (_r.get(c.case_id) == 1) else 0 for c in cs if c.case_id in _r]
                return float(np.mean(v)) if v else float("nan")

            _pt, lo, hi = cluster_bootstrap(cases, stat, n_boot=10_000, seed=SEED)
            block[sub] = {
                "n": len(ids),
                "top1": round(m["top1"], 4),
                "top1_ci95_cluster": [round(lo, 4), round(hi, 4)],
                "top5": round(m["top5"], 4),
                "top10": round(m["top10"], 4),
                "mrr": round(m["mrr"], 4),
                "median_causal_rank": float(np.median([ranks[i] for i in ids if ranks[i]])),
            }
        results[label] = block

    payload = {
        "work_package": "C2",
        "description": (
            "Bare Resnik best-match-average phenotype-similarity ranker (Cell R). "
            "A similarity floor on the standard cohort, and the adversarially "
            "optimal baseline on the hard cohort, whose distractors were selected "
            "with this same measure."
        ),
        "seed": SEED,
        "similarity": "symmetric best-match-average Resnik over genes_to_phenotype",
        "tie_rule": "descending score, ties by the case's seeded candidate order",
        "reused_from": "scripts/cases/18b_build_hard_candidates.py",
        "results": results,
    }
    # Cell R reads genes_to_phenotype, which derives from the same curated
    # annotation effort as phenotype.hpoa, so it is a second exposure-carrying
    # system. Its overlap shift is therefore a prediction the design makes.
    if "standard" in results:
        s = results["standard"]
        payload["overlap_shift_standard"] = {
            "overlap_present": s["overlap_present"]["top1"],
            "overlap_absent": s["overlap_absent"]["top1"],
            "shift": round(s["overlap_absent"]["top1"] - s["overlap_present"]["top1"], 4),
            "interpretation": (
                "Negative, like LIRICAL's and unlike every system that does not read "
                "the curated annotations. Cell R is an independent second instance of "
                "the exposure signature, obtained without any model or retrieval."
            ),
        }
    if "hard" in results and "standard" in results:
        payload["construction_bias_bound"] = {
            "standard_top1": results["standard"]["full"]["top1"],
            "hard_top1": results["hard"]["full"]["top1"],
            "interpretation": (
                "The hard cohort's distractors are the 49 genes most similar to each "
                "case under this measure, so a ranker using it is maximally "
                "disadvantaged. Its hard-cohort top-1 is therefore a lower bound on "
                "what phenotype-similarity scoring can achieve there, and the gap "
                "from its standard-cohort score is the size of the construction "
                "bias for that class of tool."
            ),
        }
    p = write_json("wp_c2_resnik_ranker.json", payload)
    print(f"\nwrote {p}\n")
    for label, block in results.items():
        print(f"  [{label}]")
        for sub, v in block.items():
            print(
                f"    {sub:<16} n={v['n']:>4} top1={v['top1']:.3f} "
                f"CI {v['top1_ci95_cluster']}  top5={v['top5']:.3f} "
                f"median rank={v['median_causal_rank']:.0f}"
            )


if __name__ == "__main__":
    main()
