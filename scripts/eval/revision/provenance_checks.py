"""WP1 + WP9-B --- provenance assertions and baseline scoring mechanics.

WP1-A  Assert that the >=5-article corpus-coverage check never gated cohort
       membership. P1 states the retrieval index is not used to determine
       membership; P2 currently describes the check as an eligibility criterion.
       If any case had failed or been replaced, the two cohorts would differ and
       every evaluation cell would need re-running, so this is asserted rather
       than assumed.

WP1-D  Record the baseline data-bundle versions and, critically, verify that the
       ``phenotype.hpoa`` release LIRICAL actually consumed is the same release
       the annotation-overlap flag is computed against. If those differ, the flag
       indexes a different annotation set than the tool read, and the whole
       overlap argument collapses.

WP9-B  Extract, from the runner code and the saved rankings, how each baseline
       turns a genome-wide score into a rank over the 50 candidates, and how ties
       are broken. The two baselines do not use the same rule, which is material
       for likelihood-ratio outputs with many tied candidates.

Outputs wp1a_coverage_check.json, wp1d_baseline_versions.json,
wp9b_tie_handling.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    COHORT_DIR,
    EVAL_STD,
    REPO,
    load_cases,
    write_json,
)

HPOA_PINNED = REPO / "data" / "Human_Phenotype_Ontology" / "phenotype.hpoa"
LIRICAL_DATA = Path.home() / "rare-disease-rag" / "lirical" / "data"
EXOMISER_DATA = Path.home() / "rare-disease-rag" / "exomiser"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def wp1a() -> dict:
    stats = json.loads((COHORT_DIR / "05_validated_stats.json").read_text())
    cases = load_cases()

    counts = [
        json.loads(line)["pmc_article_count"]
        for line in (COHORT_DIR / "test_cases.jsonl").read_text().splitlines()
        if line.strip()
    ]
    gated = stats["initial_fail"] == 0 and stats["replacements_made"] == 0

    payload = {
        "work_package": "WP1-A",
        "question": (
            "Did the >=5-article corpus-coverage check ever exclude or replace a "
            "case, i.e. did the retrieval index gate cohort membership?"
        ),
        "source": "data/test_cases_1050/05_validated_stats.json",
        "initial_sample_size": stats["initial_sample_size"],
        "initial_pass": stats["initial_pass"],
        "initial_fail": stats["initial_fail"],
        "replacements_made": stats["replacements_made"],
        "unreplaced": stats["unreplaced"],
        "min_pmc_threshold": stats["min_pmc_threshold"],
        "top_k": stats["top_k"],
        "no_case_was_gated": bool(gated),
        "verdict": (
            "CONFIRMED: no case failed and none was replaced, so the check never "
            "altered cohort membership. P2 may remove it as an eligibility "
            "criterion with no re-run; pmc_article_count is a released descriptor "
            "of retrieval-result diversity, bounded above by the top-100 cut."
        )
        if gated
        else "FAILED: cohort differs from P1 --- escalate, all five cells need re-running.",
        "pmc_article_count_distribution": {
            "n": len(counts),
            "min": min(counts),
            "max": max(counts),
            "median": sorted(counts)[len(counts) // 2],
            "n_at_ceiling_100": sum(1 for c in counts if c >= 100),
            "n_below_5": sum(1 for c in counts if c < 5),
        },
        "analytic_cohort_n": len(cases),
    }
    return payload


def wp1d() -> dict:
    pinned_hash = sha256(HPOA_PINNED)
    lirical_hpoa = LIRICAL_DATA / "phenotype.hpoa"
    lirical_hash = sha256(lirical_hpoa) if lirical_hpoa.exists() else None

    version = "unknown"
    with HPOA_PINNED.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#version:"):
                version = line.split(":", 1)[1].strip()
                break
            if not line.startswith("#"):
                break

    bundles = (
        sorted(p.name for p in EXOMISER_DATA.glob("data/*") if p.is_dir())
        if (EXOMISER_DATA / "data").is_dir()
        else []
    )

    matches = bool(lirical_hash and lirical_hash == pinned_hash)
    return {
        "work_package": "WP1-D",
        "question": (
            "Did LIRICAL consume the same phenotype.hpoa release that the "
            "annotation-overlap flag is computed against?"
        ),
        "exomiser": {
            "version": "14.0.2",
            "data_bundle_default": "2402",
            "bundles_present": bundles,
            "prioritiser": "hiPhive via --preset phenotype-only (HPO-only, no variants)",
            "hp_release_declared_in_job_yaml": "hp/releases/2026-02-16",
        },
        "lirical": {
            "version": "2.4.0",
            "data_dir": str(LIRICAL_DATA),
            "phenotype_hpoa_sha256": lirical_hash,
            "data_files_required": [
                "hp.json",
                "phenotype.hpoa",
                "mim2gene_medgen",
                "en_product6.xml",
                "hgnc_complete_set.txt",
            ],
        },
        "pinned_flag_release": {
            "path": str(HPOA_PINNED.relative_to(REPO)),
            "sha256": pinned_hash,
            "version_header": version,
        },
        "hpoa_matches_flag_release": matches,
        "verdict": (
            "CONFIRMED: the phenotype.hpoa LIRICAL read is byte-identical to the "
            "release the overlap flag is computed against, so the flag indexes "
            "exactly the annotation set the tool consumed. No re-run required."
        )
        if matches
        else "MISMATCH: escalate --- LIRICAL must be re-run against the pinned release.",
    }


def wp9b() -> dict:
    """Tie structure at rank 1 for each baseline, from the saved rankings."""
    out = {}
    for cell, dirname, rule in (
        (
            "K",
            "cell_K_exomiser_hpo_only",
            "sorted by (-hiPhive phenotype score, gene symbol): ties broken "
            "ALPHABETICALLY by HGNC symbol",
        ),
        (
            "M",
            "cell_M_lirical_hpo_only",
            "sorted by (-best posttest probability over diseases mapping to the "
            "gene, candidate-list input index): ties broken by the per-case "
            "seeded candidate order",
        ),
        (
            "S",
            "cell_S_rerank_inside_plus_lea",
            "LEA confidence, then cross-encoder order for genes the LEA did not "
            "rank; deterministic fallback to cross-encoder order on parse failure",
        ),
    ):
        tie_sizes, flat, causal_in_tie, causal_lost = [], 0, 0, 0
        for case in load_cases():
            p = EVAL_STD / dirname / f"{case.case_id}.json"
            if not p.exists():
                continue
            payload = json.loads(p.read_text())
            scores = [e.get("aggregate_confidence") for e in payload]
            if not scores or scores[0] is None:
                continue
            top = scores[0]
            tied = [e for e, s in zip(payload, scores, strict=True) if s == top]
            tie_sizes.append(len(tied))
            if len(tied) == len(payload):
                flat += 1
            if any(e.get("is_causal") for e in tied):
                causal_in_tie += 1
                if not payload[0].get("is_causal"):
                    causal_lost += 1
        n = len(tie_sizes)
        hist = Counter(min(t, 10) for t in tie_sizes)
        out[cell] = {
            "tie_break_rule": rule,
            "candidate_restriction": (
                "the tool ranks genome-wide, then the ranking is restricted post hoc "
                "to the case's 50 candidates preserving relative order; unscored "
                "candidates take score 0.0 and fall to the end"
            )
            if cell in ("K", "M")
            else "the tool scores only the case's candidates",
            "n_cases": n,
            "mean_tied_at_rank1": round(sum(tie_sizes) / n, 2) if n else None,
            "share_fully_flat": round(flat / n, 4) if n else None,
            "share_5_or_more_tied": round(sum(1 for t in tie_sizes if t >= 5) / n, 4)
            if n
            else None,
            "causal_inside_rank1_tie_group": causal_in_tie,
            "causal_lost_the_tie_break": causal_lost,
            "share_causal_lost_tie_break": round(causal_lost / n, 4) if n else None,
            "tie_size_histogram_capped_at_10": dict(sorted(hist.items())),
        }

    out["_note"] = (
        "The two curated baselines do not share a tie-break rule: Exomiser's is "
        "alphabetical by gene symbol, which is deterministic but systematic, while "
        "LIRICAL's follows the per-case seeded candidate order, which is "
        "deterministic and arbitrary with respect to the causal gene. Neither rule "
        "was tuned. The asymmetry matters only where ties occur at rank 1."
    )
    return out


def main() -> None:
    a = wp1a()
    print(write_json("wp1a_coverage_check.json", a))
    print(f"  WP1-A: {a['verdict'][:80]}...")
    print(
        f"  pmc_article_count: min={a['pmc_article_count_distribution']['min']} "
        f"median={a['pmc_article_count_distribution']['median']} "
        f"at-ceiling={a['pmc_article_count_distribution']['n_at_ceiling_100']} "
        f"below-5={a['pmc_article_count_distribution']['n_below_5']}"
    )

    d = wp1d()
    print(write_json("wp1d_baseline_versions.json", d))
    print(f"  WP1-D: hpoa_matches_flag_release = {d['hpoa_matches_flag_release']}")
    print(f"         exomiser bundles: {d['exomiser']['bundles_present']}")

    b = wp9b()
    print(write_json("wp9b_tie_handling.json", b))
    for cell in ("K", "M", "S"):
        v = b[cell]
        print(
            f"  WP9-B {cell}: mean tied at rank1 = {v['mean_tied_at_rank1']}, "
            f"fully flat {v['share_fully_flat']}, "
            f"causal lost tie-break {v['causal_lost_the_tie_break']}"
        )


if __name__ == "__main__":
    main()
