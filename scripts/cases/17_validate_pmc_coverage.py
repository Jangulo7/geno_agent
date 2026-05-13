"""Validate that each test case's causal gene has ≥5 PMC articles in the index.

Master plan §6 step 5 / Phase 1B [5]. Reads the stratified sample from
``04_sampled.jsonl`` and the eligible pool from ``03_categorized.jsonl``.
For each case, runs a hybrid (dense + BM25) query against the live
``geno_agent_pmc_oa_v1`` Qdrant collection using the causal gene symbol
as the query string. Counts distinct PMCIDs returned in top-K.

Decision rule per master plan §4.2.1:
  - If distinct PMCID count ≥ ``MIN_PMC_ARTICLES_PER_GENE`` (default 5):
    keep the case in the validated set.
  - Else: drop the case and try to replace it with a fresh case from
    the same MONDO category in the eligible pool, deterministically
    shuffled with seed=42. The first eligible-pool candidate whose
    causal gene also passes the ≥5 threshold becomes the replacement.

Inputs::

    data/test_cases/04_sampled.jsonl     (75 stratified cases)
    data/test_cases/03_categorized.jsonl (2,971-row replacement pool)

Output::

    data/test_cases/05_validated.jsonl

Determinism:
  * Cases are processed in input order (same as sampling order).
  * Replacement candidates are pulled from a per-category list
    shuffled once with ``random.Random(RANDOM_SEED)``; first passing
    candidate wins. This makes the validated set fully reproducible
    given identical Qdrant index state.

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/17_validate_pmc_coverage.py
"""

from __future__ import annotations

import json
import logging
import os
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "logs" / "phase1b_pmc_coverage.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("pmc_coverage")

# ---------------------------------------------------------------- defaults
QDRANT_HOST: Final[str] = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: Final[int] = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION: Final[str] = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL: Final[str] = os.environ.get(
    "EMBED_MODEL_NAME",
    "/home/hana77/rare-disease-rag/models/pubmedbert-base-embeddings",
)
SPARSE_MODEL: Final[str] = "Qdrant/bm25"
MIN_PMC: Final[int] = int(os.environ.get("MIN_PMC_ARTICLES_PER_GENE", "5"))
TOP_K: Final[int] = int(os.environ.get("PMC_COVERAGE_TOP_K", "100"))
RANDOM_SEED: Final[int] = int(os.environ.get("RANDOM_SEED", "42"))

TC_DIR: Final[Path] = PROJECT_ROOT / "data" / "test_cases"
SAMPLE_PATH: Final[Path] = TC_DIR / "04_sampled.jsonl"
POOL_PATH: Final[Path] = TC_DIR / "03_categorized.jsonl"
OUT_PATH: Final[Path] = TC_DIR / "05_validated.jsonl"
STATS_PATH: Final[Path] = TC_DIR / "05_validated_stats.json"


# ---------------------------------------------------------------- query
def gene_pmc_count(
    client: QdrantClient,
    dense_model: SentenceTransformer,
    bm25_model: SparseTextEmbedding,
    gene_symbol: str,
    k: int = TOP_K,
) -> tuple[int, list[str]]:
    """Return (distinct_pmcid_count, distinct_pmcids) for a hybrid query.

    Hybrid retrieval: dense PubMedBERT prefetch (k) + BM25 sparse prefetch (k),
    fused with RRF, top-k returned. Distinct PMCIDs counted from the payload.
    BM25 query uses ``.query_embed()`` (TF only, IDF lives on server).
    """
    q_dense = dense_model.encode(gene_symbol, normalize_embeddings=True).tolist()
    q_sparse = next(iter(bm25_model.query_embed([gene_symbol])))
    res = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(query=q_dense, using="dense", limit=k),
            models.Prefetch(
                query=models.SparseVector(
                    indices=q_sparse.indices.tolist(),
                    values=q_sparse.values.tolist(),
                ),
                using="bm25",
                limit=k,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k,
        with_payload=["pmcid"],
    )
    pmcids = [p.payload.get("pmcid") for p in res.points if p.payload.get("pmcid")]
    distinct = list(dict.fromkeys(pmcids))  # preserve order, dedupe
    return len(distinct), distinct


# ---------------------------------------------------------------- main
def main() -> int:
    """Validate the sample, replace failures, write 05_validated.jsonl."""
    log.info(
        "Qdrant: %s:%d / %s | dense=%s | sparse=%s | MIN_PMC=%d | top_k=%d",
        QDRANT_HOST,
        QDRANT_PORT,
        COLLECTION,
        DENSE_MODEL,
        SPARSE_MODEL,
        MIN_PMC,
        TOP_K,
    )

    if not SAMPLE_PATH.exists():
        log.error("Sample missing: %s", SAMPLE_PATH)
        return 1
    if not POOL_PATH.exists():
        log.error("Pool missing: %s", POOL_PATH)
        return 1

    sample = [json.loads(line) for line in SAMPLE_PATH.read_text().splitlines() if line]
    pool_by_cat: dict[str, list[dict]] = defaultdict(list)
    for line in POOL_PATH.read_text().splitlines():
        if not line:
            continue
        r = json.loads(line)
        pool_by_cat[r["category"]].append(r)

    sample_ids = {r["case_id"] for r in sample}
    log.info(
        "Loaded sample=%d cases, pool=%d cases across %d categories",
        len(sample),
        sum(len(v) for v in pool_by_cat.values()),
        len(pool_by_cat),
    )

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)
    log.info("Loading dense model...")
    dense_model = SentenceTransformer(DENSE_MODEL)
    log.info("Loading sparse model...")
    bm25_model = SparseTextEmbedding(model_name=SPARSE_MODEL)
    log.info("Models ready.")

    rng = random.Random(RANDOM_SEED)

    # First pass — score the initial sample
    validated: list[dict] = []
    rejected: list[dict] = []

    for i, case in enumerate(sample, 1):
        gene = case["causal_gene"]
        n_pmc, _ = gene_pmc_count(client, dense_model, bm25_model, gene)
        case["pmc_article_count"] = n_pmc
        if n_pmc >= MIN_PMC:
            validated.append(case)
            log.info(
                "[%2d/%d] PASS  %s  causal=%s  pmcids=%d",
                i,
                len(sample),
                case["case_id"],
                gene,
                n_pmc,
            )
        else:
            rejected.append(case)
            log.info(
                "[%2d/%d] REJECT %s  causal=%s  pmcids=%d",
                i,
                len(sample),
                case["case_id"],
                gene,
                n_pmc,
            )

    # Replacement loop — try eligible-pool candidates in same category
    replacements_made = 0
    unreplaced: list[dict] = []
    for rej in rejected:
        cat = rej["category"]
        candidates = [c for c in pool_by_cat[cat] if c["case_id"] not in sample_ids]
        rng.shuffle(candidates)
        replaced = False
        for cand in candidates:
            n_pmc, _ = gene_pmc_count(client, dense_model, bm25_model, cand["causal_gene"])
            cand["pmc_article_count"] = n_pmc
            if n_pmc >= MIN_PMC:
                cand["replacement_for"] = rej["case_id"]
                validated.append(cand)
                sample_ids.add(cand["case_id"])
                log.info(
                    "REPLACE %s -> %s (causal=%s pmcids=%d)",
                    rej["case_id"],
                    cand["case_id"],
                    cand["causal_gene"],
                    n_pmc,
                )
                replacements_made += 1
                replaced = True
                break
        if not replaced:
            unreplaced.append(rej)
            log.warning("NO REPLACEMENT for %s (category=%s)", rej["case_id"], cat)

    # Write output
    with OUT_PATH.open("w", encoding="utf-8") as fh:
        for r in validated:
            fh.write(json.dumps(r, ensure_ascii=False))
            fh.write("\n")

    # Stats summary
    by_cat_validated: dict[str, int] = defaultdict(int)
    for r in validated:
        by_cat_validated[r["category"]] += 1
    summary = {
        "initial_sample_size": len(sample),
        "initial_pass": len(validated) - replacements_made,
        "initial_fail": len(rejected),
        "replacements_made": replacements_made,
        "unreplaced": len(unreplaced),
        "unreplaced_case_ids": [r["case_id"] for r in unreplaced],
        "final_validated_size": len(validated),
        "by_category_validated": dict(by_cat_validated),
        "min_pmc_threshold": MIN_PMC,
        "top_k": TOP_K,
        "qdrant_collection": COLLECTION,
        "random_seed": RANDOM_SEED,
    }
    STATS_PATH.write_text(json.dumps(summary, indent=2))

    log.info("=== PMC coverage validation summary ===")
    log.info("  initial pass:        %d / %d", summary["initial_pass"], len(sample))
    log.info("  initial fail:        %d", summary["initial_fail"])
    log.info("  replacements made:   %d", summary["replacements_made"])
    log.info("  unreplaced:          %d", summary["unreplaced"])
    log.info("  final validated:     %d", summary["final_validated_size"])
    log.info("  by category:         %s", summary["by_category_validated"])
    log.info("  output:              %s", OUT_PATH)
    log.info("  stats:               %s", STATS_PATH)
    return 0 if not unreplaced else 2  # exit 2 if any category had no replacement


if __name__ == "__main__":
    raise SystemExit(main())
