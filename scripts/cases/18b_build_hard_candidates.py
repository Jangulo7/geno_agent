"""Build a *hard* 50-gene candidate list per case (phenotype-similar distractors).

Sibling of ``18_build_candidate_lists.py``. Where stage 18 draws 49 distractors
**uniformly at random** from the HGNC protein-coding pool, this stage draws the
49 distractors that are **phenotypically most similar to the case**, so the
benchmark stresses differential-diagnosis behaviour rather than genome-wide
separability.

Distractor selection (deterministic, version-pinned):
  * Phenotypic similarity = HPO **Resnik** term similarity (information content of
    the most-informative common ancestor) aggregated by **best-match-average
    (BMA)** between the case HPO profile and each gene's known HPO annotations.
    This is the Phenomizer/Exomiser-standard symmetric phenotypic-similarity
    measure.
  * Information content is computed from the gene->HPO annotation corpus
    (``genes_to_phenotype.txt``), frequencies propagated over the ``hp.obo``
    is-a DAG; IC(t) = -ln(P(t)).
  * Candidate pool = HGNC protein-coding genes (same pool as stage 18) that have
    HPO annotations, **excluding** the causal gene and **excluding any gene
    annotated to the case's own causal disease(s)** so a distractor can never be
    a genuine alternative cause (clean hard negatives, no label ambiguity).
  * The top-49 by BMA are taken; ties broken by gene symbol (ascending) for
    determinism. If a case has < 49 scored candidates (not observed in practice),
    the remainder is filled with the per-case-seeded random draw of stage 18.

Everything else is identical to stage 18 / the published cohort: same cases,
same ``case_id``/``causal_gene``/``hpo_terms``/``diseases``, same per-case
``BLAKE2b(global_seed | case_id)`` seed for the final 50-gene shuffle. Only
``candidate_genes`` and ``causal_gene_index_in_candidates`` differ. The result is
a drop-in *hard* sibling of the published ``test_cases.jsonl`` (DOI
10.6084/m9.figshare.32814449) suitable for its own Figshare item.

Pinned inputs (provenance): HPO v2026-02-16 (hp.obo + genes_to_phenotype.txt),
HGNC snapshot 2026-04-07, GA4GH Phenopacket Store v0.1.26 cohort.

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/18b_build_hard_candidates.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import random
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Final

import pandas as pd
from tqdm import tqdm

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_hard_candidates")

N_DISTRACTORS: Final[int] = int(os.environ.get("N_DISTRACTORS", "49"))
GLOBAL_SEED: Final[int] = int(os.environ.get("RANDOM_SEED", "42"))
HPO_DIR: Final[Path] = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology"
HGNC_TSV: Final[Path] = PROJECT_ROOT / "data" / "HGNC" / "hgnc_complete_set_2026-04-07.txt"


# ---------------------------------------------------------------------------
# per-case seed -- identical scheme to stage 18 (BLAKE2b over global|case_id)
# ---------------------------------------------------------------------------
def per_case_seed(case_id: str, global_seed: int = GLOBAL_SEED) -> int:
    h = hashlib.blake2b(f"{global_seed}|{case_id}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big")


# ---------------------------------------------------------------------------
# HPO ontology + information content
# ---------------------------------------------------------------------------
def parse_hpo_obo(obo_path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Parse hp.obo -> (is_a parents per term, alt_id -> primary id), skipping obsoletes."""
    parents: dict[str, list[str]] = {}
    alt_to_primary: dict[str, str] = {}
    cur: str | None = None
    cur_parents: list[str] = []
    cur_alts: list[str] = []
    obsolete = False
    in_term = False

    def flush() -> None:
        if cur and in_term and not obsolete:
            parents[cur] = cur_parents
            for a in cur_alts:
                alt_to_primary[a] = cur

    with obo_path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line == "[Term]":
                flush()
                cur, cur_parents, cur_alts, obsolete, in_term = None, [], [], False, True
            elif line.startswith("[") and line.endswith("]"):
                flush()
                in_term = False
            elif in_term:
                if line.startswith("id: HP:"):
                    cur = line[4:].strip()
                elif line.startswith("is_a: HP:"):
                    cur_parents.append(line[6:].split("!")[0].strip())
                elif line.startswith("alt_id: HP:"):
                    cur_alts.append(line[8:].strip())
                elif line.startswith("is_obsolete: true"):
                    obsolete = True
    flush()
    return parents, alt_to_primary


def build_ancestors(parents: dict[str, list[str]]) -> dict[str, frozenset[str]]:
    """Ancestor closure (including the term itself) for every term, memoised."""
    cache: dict[str, frozenset[str]] = {}

    def anc(t: str) -> frozenset[str]:
        if t in cache:
            return cache[t]
        acc = {t}
        for p in parents.get(t, ()):  # parent must exist as a term
            if p in parents:
                acc |= anc(p)
        fs = frozenset(acc)
        cache[t] = fs
        return fs

    for term in parents:
        anc(term)
    return cache


def load_gene_annotations(
    g2p_path: Path, alt_to_primary: dict[str, str], valid_terms: set[str]
) -> tuple[dict[str, frozenset[str]], dict[str, set[str]]]:
    """Return (gene -> direct HPO term set, gene -> disease-id set) from genes_to_phenotype."""
    gene_hpo: dict[str, set[str]] = defaultdict(set)
    gene_dis: dict[str, set[str]] = defaultdict(set)
    with g2p_path.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh, delimiter="\t")
        for row in rdr:
            g = row["gene_symbol"]
            hpo = alt_to_primary.get(row["hpo_id"], row["hpo_id"])
            if hpo in valid_terms:
                gene_hpo[g].add(hpo)
            if row["disease_id"]:
                gene_dis[g].add(row["disease_id"])
    return {g: frozenset(v) for g, v in gene_hpo.items()}, dict(gene_dis)


def compute_ic(
    gene_hpo: dict[str, frozenset[str]], ancestors: dict[str, frozenset[str]]
) -> dict[str, float]:
    """Information content per term: IC(t) = -ln(freq), freq over genes, ancestor-propagated."""
    term_gene_count: dict[str, int] = defaultdict(int)
    n_genes = len(gene_hpo)
    for terms in gene_hpo.values():
        propagated: set[str] = set()
        for t in terms:
            propagated |= ancestors.get(t, frozenset({t}))
        for t in propagated:
            term_gene_count[t] += 1
    ic: dict[str, float] = {}
    for t, c in term_gene_count.items():
        ic[t] = -math.log(c / n_genes)
    return ic


# ---------------------------------------------------------------------------
# Resnik + best-match-average
# ---------------------------------------------------------------------------
def make_similarity(ancestors: dict[str, frozenset[str]], ic: dict[str, float]):
    """Return memoised resnik(t1,t2) = IC of most-informative common ancestor."""

    @lru_cache(maxsize=4_000_000)
    def resnik(t1: str, t2: str) -> float:
        a1, a2 = ancestors.get(t1), ancestors.get(t2)
        if a1 is None or a2 is None:
            return 0.0
        common = a1 & a2
        if not common:
            return 0.0
        return max((ic.get(c, 0.0) for c in common), default=0.0)

    return resnik


def bma(case_terms: list[str], gene_terms: frozenset[str], resnik) -> float:
    """Symmetric best-match-average Resnik similarity between two HPO term sets."""
    if not case_terms or not gene_terms:
        return 0.0
    fwd = sum(max(resnik(c, g) for g in gene_terms) for c in case_terms) / len(case_terms)
    rev = sum(max(resnik(c, g) for c in case_terms) for g in gene_terms) / len(gene_terms)
    return 0.5 * (fwd + rev)


# ---------------------------------------------------------------------------
def load_protein_coding_symbols(hgnc_path: Path) -> list[str]:
    df = pd.read_csv(hgnc_path, sep="\t", low_memory=False)
    pc = df[df["locus_group"] == "protein-coding gene"]
    return sorted(pc["symbol"].dropna().unique().tolist())


def main() -> int:
    ap = argparse.ArgumentParser(description="Build hard (phenotype-similar) candidate lists.")
    ap.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT
        / "figshare_uploads/_staging/genoagent-cohort-n1047-v1.0/test_cases.jsonl",
        help="Published n=1,047 cohort (same cases as DOI .449).",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/test_cases_hard/test_cases_hard.jsonl",
    )
    ap.add_argument(
        "--stats",
        type=Path,
        default=PROJECT_ROOT / "data/test_cases_hard/hard_candidates_stats.json",
    )
    ap.add_argument("--n-distractors", type=int, default=N_DISTRACTORS)
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Parsing hp.obo ...")
    parents, alt_to_primary = parse_hpo_obo(HPO_DIR / "hp.obo")
    valid_terms = set(parents)
    ancestors = build_ancestors(parents)
    logger.info(f"  {len(valid_terms):,} terms; ancestor closures built")

    logger.info("Loading gene->HPO annotations ...")
    gene_hpo, gene_dis = load_gene_annotations(
        HPO_DIR / "genes_to_phenotype.txt", alt_to_primary, valid_terms
    )
    ic = compute_ic(gene_hpo, ancestors)
    logger.info(f"  {len(gene_hpo):,} annotated genes; IC for {len(ic):,} terms")

    pc_symbols = set(load_protein_coding_symbols(HGNC_TSV))
    logger.info(f"  {len(pc_symbols):,} HGNC protein-coding symbols")
    # candidate distractor pool: protein-coding AND HPO-annotated
    pool_genes = sorted(g for g in gene_hpo if g in pc_symbols)
    logger.info(f"  {len(pool_genes):,} genes in scored pool (protein-coding ∩ annotated)")

    # inverted index: ancestor term -> genes whose propagated annotations include it
    # (restricted to IC>0 terms so we only gather genes that can score > 0)
    gene_prop: dict[str, frozenset[str]] = {}
    inverted: dict[str, set[str]] = defaultdict(set)
    for g in pool_genes:
        prop: set[str] = set()
        for t in gene_hpo[g]:
            prop |= ancestors.get(t, frozenset({t}))
        gene_prop[g] = frozenset(prop)
        for t in prop:
            if ic.get(t, 0.0) > 0.0:
                inverted[t].add(g)

    resnik = make_similarity(ancestors, ic)
    all_pc = sorted(pc_symbols)  # fallback pool for the (unlikely) <49 case

    n_out = 0
    n_short = 0
    stats: dict[str, dict] = {}
    cases = [json.loads(line) for line in args.input.open(encoding="utf-8")]

    with args.output.open("w", encoding="utf-8") as fout:
        for rec in tqdm(cases, desc="hard-candidates"):
            cid = rec["case_id"]
            causal = rec["causal_gene"]
            case_terms = [alt_to_primary.get(t, t) for t in rec["hpo_terms"]]
            case_terms = [t for t in case_terms if t in valid_terms]
            case_diseases = {d["id"] for d in rec.get("diseases", [])}

            # gather scoring candidates via shared IC>0 ancestors
            case_anc: set[str] = set()
            for t in case_terms:
                case_anc |= {a for a in ancestors.get(t, frozenset({t})) if ic.get(a, 0.0) > 0.0}
            cand: set[str] = set()
            for a in case_anc:
                cand |= inverted.get(a, set())
            # exclusions: causal gene + any gene sharing the case's causal disease(s)
            cand.discard(causal)
            cand = {g for g in cand if not (gene_dis.get(g, set()) & case_diseases)}

            scored = sorted(
                ((bma(case_terms, gene_hpo[g], resnik), g) for g in cand),
                key=lambda sg: (-sg[0], sg[1]),  # score desc, symbol asc (deterministic)
            )
            scored = [sg for sg in scored if sg[0] > 0.0]
            distractors = [g for _, g in scored[: args.n_distractors]]

            if len(distractors) < args.n_distractors:  # fill deterministically (unobserved)
                n_short += 1
                rng = random.Random(per_case_seed(cid))
                taken = set(distractors) | {causal}
                fill_pool = [g for g in all_pc if g not in taken]
                distractors += rng.sample(fill_pool, args.n_distractors - len(distractors))

            candidates = [causal, *distractors]
            random.Random(per_case_seed(cid)).shuffle(candidates)

            out = {
                "case_id": cid,
                "category": rec["category"],
                "hpo_terms": rec["hpo_terms"],
                "diseases": rec["diseases"],
                "causal_gene": causal,
                "candidate_genes": candidates,
                "causal_gene_index_in_candidates": candidates.index(causal),
                "pmc_article_count": rec.get("pmc_article_count"),
                "source_phenopacket": rec.get("source_phenopacket"),
                "candidate_difficulty": "hard",
            }
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            n_out += 1

            causal_bma = bma(case_terms, gene_hpo.get(causal, frozenset()), resnik)
            dist_bmas = [s for s, _ in scored[: args.n_distractors]]
            stats[cid] = {
                "causal_bma": round(causal_bma, 4),
                "distractor_bma_max": round(max(dist_bmas), 4) if dist_bmas else 0.0,
                "distractor_bma_min": round(min(dist_bmas), 4) if dist_bmas else 0.0,
                "distractor_bma_median": round(sorted(dist_bmas)[len(dist_bmas) // 2], 4)
                if dist_bmas
                else 0.0,
                "n_scored_candidates": len(scored),
            }

    meta = {
        "n_cases": n_out,
        "n_distractors": args.n_distractors,
        "selection": "resnik_bma_top49_excluding_same_disease",
        "ic_basis": "gene_annotation_frequency_propagated",
        "global_seed": GLOBAL_SEED,
        "hpo_version": "v2026-02-16",
        "hgnc_snapshot": "2026-04-07",
        "phenopacket_store_version": "0.1.26",
        "base_cohort_doi": "10.6084/m9.figshare.32814449",
        "n_cases_short_filled": n_short,
    }
    args.stats.write_text(json.dumps({"meta": meta, "records": stats}, indent=2))
    logger.info(f"Wrote {n_out:,} hard cases -> {args.output}")
    logger.info(f"  cases needing random fill (<49 scored): {n_short}")
    logger.info(f"  stats -> {args.stats}")
    return 0 if n_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
