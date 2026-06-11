"""Proper rerank-inside-D diagnostic.

Faithfully simulates the Phase 2e architecture on a small subset of
cases. Pipeline per case:

    HPO + candidates -> Planner -> Retrieve(top_k=50) -> CrossEncoderRerank(-> top_k=10)
                                       -> Critic -> Synth -> ranked output

Compared to ``rerank_diagnostic.py`` (which replaced the entire Critic +
Synth stack with a max-CE-score gene ranking), this version preserves
the deterministic Critic and Synth so any lift observed is the
*additional* value of cross-encoder reranking on top of Cell D.

Output: ``data/eval/cell_D_rerankInside/<case_id>.json``.

Usage::

    PYTHONPATH=. python scripts/eval/rerank_inside_d.py [--limit 20]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict
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

from src.agents.critic import critic_node  # noqa: E402
from src.agents.query_planner import build_mesh_queries  # noqa: E402
from src.agents.retriever import retrieve_for_gene  # noqa: E402
from src.agents.state import AgentState, GeneCandidate  # noqa: E402
from src.agents.synthesizer import synthesizer_node  # noqa: E402
from src.agents.synthesizer_lea import lea_synthesizer_node  # noqa: E402
from src.tools.hgnc import load_hgnc  # noqa: E402
from src.tools.qdrant_search import SearchConfig  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

log = logging.getLogger("rerank_inside_d")

CASES_JSONL = PROJECT_ROOT / "data" / "test_cases" / "test_cases.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "eval" / "cell_D_rerankInside"

CROSS_ENCODER_MODEL = "ncbi/MedCPT-Cross-Encoder"
RETRIEVAL_TOP_K = 50
RERANK_KEEP_TOP_K = 10

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL_PATH = os.environ.get(
    "DENSE_MODEL_PATH",
    "NeuML/pubmedbert-base-embeddings",
)
SPARSE_MODEL_NAME = "Qdrant/bm25"
HPO_OBO_PATH: Final[Path] = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"
HGNC_PATH: Final[Path] = PROJECT_ROOT / "data" / "HGNC" / "hgnc_complete_set_2026-04-07.txt"


def main() -> int:
    """Driver entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Run only the first N cases (default 20 for subset diagnostic).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-run even if output already exists.",
    )
    parser.add_argument(
        "--use-lea",
        action="store_true",
        help="Use the LEA (LLM-as-Evidence-Aggregator) Synthesiser instead "
        "of the deterministic one. Cell S = rerank-inside + LEA.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Override the output directory. Default = cell_L_rerank_inside_d "
        "(without --use-lea) or cell_S_rerank_inside_plus_lea (with --use-lea).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Resolve output directory based on flags.
    if args.out_dir:
        out_dir = Path(args.out_dir)
    elif args.use_lea:
        out_dir = PROJECT_ROOT / "data" / "eval" / "cell_S_rerank_inside_plus_lea"
    else:
        out_dir = OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output dir: %s  (use_lea=%s)", out_dir, args.use_lea)
    cases: list[dict] = []
    with CASES_JSONL.open() as f:
        for line in f:
            cases.append(json.loads(line))
    if args.limit:
        cases = cases[: args.limit]

    log.info("Loading cross-encoder %s ...", CROSS_ENCODER_MODEL)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL, device=device, max_length=512)
    log.info("Loading HPO ontology + HGNC index ...")
    hpo_ontology = pronto.Ontology(str(HPO_OBO_PATH))
    hgnc = load_hgnc(HGNC_PATH)
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
        out_path = out_dir / f"{case['case_id']}.json"
        if out_path.is_file() and not args.overwrite:
            log.info("  [%d/%d] %s SKIP (exists)", i, len(cases), case["case_id"])
            continue

        t0 = time.time()
        state = AgentState(
            case_id=case["case_id"],
            hpo_terms=case["hpo_terms"],
            candidate_genes=case["candidate_genes"],
        )
        state.mesh_queries = build_mesh_queries(state, hpo_ontology)

        # 1. Retrieve TOP_K=50 per gene (Cell D uses 10; we go deeper so the
        # reranker has more candidates to choose from).
        for j, gene in enumerate(state.candidate_genes):
            query = state.mesh_queries[j] if j < len(state.mesh_queries) else gene
            state.retrieved[gene] = retrieve_for_gene(
                cfg, query, gene=gene, top_k=RETRIEVAL_TOP_K, mode="hybrid"
            )

        # 2. Cross-encoder rerank: per gene, score 50 chunks, keep top-10.
        for j, gene in enumerate(state.candidate_genes):
            chunks = state.retrieved[gene]
            if not chunks:
                continue
            query = state.mesh_queries[j] if j < len(state.mesh_queries) else gene
            pairs = [(query, ch.text or "") for ch in chunks]
            scores = cross_encoder.predict(pairs, batch_size=64, show_progress_bar=False)
            # Sort chunks by CE score descending, keep top-10.
            paired = sorted(
                zip(chunks, scores, strict=True),
                key=lambda t: -float(t[1]),
            )
            state.retrieved[gene] = [ch for ch, _ in paired[:RERANK_KEEP_TOP_K]]

        # 3. Critic + Synth (deterministic, same as Cell D).
        state = critic_node(state, hpo_ontology, hgnc)
        if args.use_lea:
            state = lea_synthesizer_node(state, hpo_ontology)
        else:
            state = synthesizer_node(state)

        # 4. Apply ground-truth is_causal post-hoc (the agent does not see
        # the answer key) -- mirrors run_factorial.py:229-230.
        causal = case["causal_gene"]
        payload = []
        for c in state.ranked:
            entry = asdict(c)
            entry["is_causal"] = entry["symbol"] == causal
            payload.append(entry)
        with out_path.open("w") as f:
            json.dump(payload, f, indent=2)
        done += 1

        causal_rank = next(
            (p["final_rank"] for p in payload if p["is_causal"]),
            None,
        )
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
        "=== rerank-inside-D done in %.1fmin: %d cases ===",
        cell_dt,
        done,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


def _patch_dataclass_to_dict(_obj: GeneCandidate) -> dict:
    """Keep mypy from complaining about asdict on slotted dataclass."""
    return asdict(_obj)
