"""Post-hoc rerank diagnostic: does a cross-encoder change Cell D's top-1?

For each test case, re-runs Cell D's retrieval, applies a cross-encoder
reranker over the per-gene top-K chunks, then ranks genes by the
reranker score (skipping the deterministic Critic / Synthesiser).

Output: ``data/eval/cell_D_reranked/<case_id>.json`` in the same shape
as cells A-K, consumed by the existing aggregator.

This is a directional diagnostic — NOT a faithful reproduction of the
proposed Phase 2e Cell L/M (which would keep the Critic step). The
point is to see whether a cross-encoder over Cell D's retrieved chunks
produces materially different gene rankings. If yes -> Phase 2e is
worth 3 days of dev. If no -> skip Phase 2e and invest in LEA / other.

Usage::

    PYTHONPATH=. python scripts/eval/rerank_diagnostic.py [--limit N]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Final

import torch
from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder, SentenceTransformer

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pronto  # noqa: E402

from src.agents.query_planner import build_mesh_queries  # noqa: E402
from src.agents.retriever import retrieve_for_gene  # noqa: E402
from src.agents.state import AgentState  # noqa: E402
from src.tools.qdrant_search import SearchConfig  # noqa: E402

HPO_OBO_PATH: Final[Path] = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"

load_dotenv(PROJECT_ROOT / ".env")

log = logging.getLogger("rerank_diag")

CASES_JSONL = PROJECT_ROOT / "data" / "test_cases" / "test_cases.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "eval" / "cell_D_reranked"

# Default biomedical cross-encoder. PubMed-fine-tuned, 440 MB.
CROSS_ENCODER_MODEL = "ncbi/MedCPT-Cross-Encoder"

# Per-gene retrieval budget matches Cell D.
RETRIEVAL_TOP_K = 10

# Qdrant / model config (mirror run_factorial.py).
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL_PATH = os.environ.get(
    "DENSE_MODEL_PATH",
    "NeuML/pubmedbert-base-embeddings",
)
SPARSE_MODEL_NAME = "Qdrant/bm25"


def _build_state(case: dict) -> AgentState:
    """Build a minimal AgentState from a Phase 1B test case."""
    return AgentState(
        case_id=case["case_id"],
        hpo_terms=case["hpo_terms"],
        candidate_genes=case["candidate_genes"],
    )


def _payload_from_reranked(
    case: dict,
    gene_to_max_score: dict[str, float],
) -> list[dict]:
    """Build the cell-format payload, ranking candidates by reranker score."""
    causal_gene = case["causal_gene"]
    candidate_genes: list[str] = list(case["candidate_genes"])
    scored = sorted(
        candidate_genes,
        key=lambda g: (-gene_to_max_score.get(g, -1e9), g),
    )
    return [
        {
            "symbol": symbol,
            "is_causal": symbol == causal_gene,
            "aggregate_confidence": float(gene_to_max_score.get(symbol, 0.0)),
            "supporting_chunks": [],
            "final_rank": rank,
        }
        for rank, symbol in enumerate(scored, start=1)
    ]


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases (smoke).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-rerank even if output already exists.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    with CASES_JSONL.open() as f:
        for line in f:
            cases.append(json.loads(line))
    if args.limit:
        cases = cases[: args.limit]

    log.info("Loading cross-encoder %s ...", CROSS_ENCODER_MODEL)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL, device=device, max_length=512)
    log.info("Cross-encoder loaded on %s", device)

    log.info("Loading HPO ontology %s ...", HPO_OBO_PATH)
    hpo_ontology = pronto.Ontology(str(HPO_OBO_PATH))
    log.info("Loading dense + sparse models ...")
    dense_model = SentenceTransformer(DENSE_MODEL_PATH)
    bm25_model = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)
    log.info("Connecting Qdrant %s:%d / %s", QDRANT_HOST, QDRANT_PORT, COLLECTION)
    qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)
    cfg = SearchConfig(
        client=qdrant_client,
        collection_name=COLLECTION,
        dense_model=dense_model,
        bm25_model=bm25_model,
    )

    done = 0
    cell_t0 = time.time()
    for i, case in enumerate(cases, start=1):
        out_path = OUTPUT_DIR / f"{case['case_id']}.json"
        if out_path.is_file() and not args.overwrite:
            log.info("  [%d/%d] %s SKIP (exists)", i, len(cases), case["case_id"])
            continue

        t0 = time.time()
        state = _build_state(case)
        state.mesh_queries = build_mesh_queries(state, hpo_ontology)

        # 1. Retrieve top-K chunks per gene (same as Cell D).
        per_gene_chunks: dict[str, list] = {}
        for j, gene in enumerate(state.candidate_genes):
            query = state.mesh_queries[j] if j < len(state.mesh_queries) else gene
            per_gene_chunks[gene] = retrieve_for_gene(
                cfg, query, gene=gene, top_k=RETRIEVAL_TOP_K, mode="hybrid"
            )

        # 2. Build per-gene query strings (gene-aware so the cross-encoder
        # scores chunks against the specific gene+phenotype pairing, not a
        # generic case-level phenotype query). Reuses the same query shape
        # the Planner builds: "{gene_symbol} {HPO labels}".
        # The mesh_queries are already in candidate-gene order.
        gene_to_query: dict[str, str] = {
            gene: state.mesh_queries[i] if i < len(state.mesh_queries) else gene
            for i, gene in enumerate(state.candidate_genes)
        }

        # 3. Score each (per-gene query, chunk) pair with the cross-encoder.
        # Batch all chunks across all genes into one forward pass.
        pairs: list[tuple[str, str]] = []
        pair_owners: list[str] = []
        for gene, chunks in per_gene_chunks.items():
            q = gene_to_query[gene]
            for ch in chunks:
                pairs.append((q, ch.text or ""))
                pair_owners.append(gene)
        if not pairs:
            log.warning("  [%d/%d] %s no chunks retrieved", i, len(cases), case["case_id"])
            continue

        scores = cross_encoder.predict(pairs, batch_size=64, show_progress_bar=False)

        # 4. Per gene: take max chunk score as the gene's reranker score.
        gene_to_max_score: dict[str, float] = {}
        for gene, score in zip(pair_owners, scores, strict=True):
            prev = gene_to_max_score.get(gene, -1e9)
            if score > prev:
                gene_to_max_score[gene] = float(score)

        payload = _payload_from_reranked(case, gene_to_max_score)
        with out_path.open("w") as f:
            json.dump(payload, f, indent=2)
        done += 1

        causal_rank = next((p["final_rank"] for p in payload if p["is_causal"]), None)
        log.info(
            "  [%d/%d] %s causal_rank=%s (%.1fs)",
            i,
            len(cases),
            case["case_id"],
            causal_rank,
            time.time() - t0,
        )

    cell_dt = (time.time() - cell_t0) / 60.0
    log.info(
        "=== Rerank diagnostic done in %.1fmin: %d cases ===",
        cell_dt,
        done,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
