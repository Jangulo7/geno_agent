"""Run the 2x2 factorial evaluation per master plan §11.5.

Four cells (Exomiser Cell E deferred — requires separate Java install):

    | Architecture | Retrieval | Cell |
    |--------------|-----------|------|
    | single-agent | dense     | A    |  one-shot retrieve+score, dense-only
    | single-agent | hybrid    | B    |  one-shot retrieve+score, hybrid (RRF)
    | multi-agent  | dense     | C    |  Planner→Retriever→Critic→Synthesizer, dense
    | multi-agent  | hybrid    | D    |  Planner→Retriever→Critic→Synthesizer, hybrid

For each test case in ``test_cases.jsonl``, all 4 cells produce a ranked
list of the 50 ``candidate_genes`` (1 causal + 49 distractors, seed=42
from Phase 1B). Per-case results are written one JSON per (cell, case)
to ``data/eval/<cell>/<case_id>.json``.

Master plan §11.5 also specifies:
  - Top-1, Top-5, Top-10 accuracy
  - MRR
  - NDCG@10
  - Paired bootstrap 95% CI (1000 resamples) over cases

These are computed by ``scripts/eval/aggregate_metrics.py`` from the
per-case outputs.

Single-agent design (Cells A/B): for each candidate gene g, run a
Qdrant query for ``"{gene_symbol} {HPO labels joined}"`` and take top-K
chunks. Gene score = sum of chunk scores. Rank candidates by total
score (zero scores → tail in deterministic order). This isolates the
"multi-agent architecture" contribution from the "retrieval mode"
contribution as specified in §11.5.

Multi-agent (Cells C/D): use the existing LangGraph state graph from
``src/agents/graph.py`` with the matching ``retriever_mode``. All four
agents (Query Planner, Retriever, Critic, Synthesizer) run
deterministically — the LLM-prompted variants C7b/C7c are deferred.

Run::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/eval/run_factorial.py [--cells ABCD] [--limit N]
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
from typing import Final, Literal

import pronto
from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402
from src.agents.graph import build_graph  # noqa: E402
from src.agents.state import AgentState, GeneCandidate  # noqa: E402
from src.tools.hgnc import load_hgnc  # noqa: E402
from src.tools.qdrant_search import SearchConfig, hybrid_search  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "logs" / "factorial_eval.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("factorial")

# ---------------------------------------------------------------- defaults
QDRANT_HOST: Final[str] = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: Final[int] = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION: Final[str] = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL_PATH: Final[str] = os.environ.get(
    "EMBED_MODEL_NAME",
    "/home/hana77/rare-disease-rag/models/pubmedbert-base-embeddings",
)
SPARSE_MODEL_NAME: Final[str] = "Qdrant/bm25"
HPO_PATH: Final[Path] = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"
HGNC_PATH: Final[Path] = PROJECT_ROOT / "data" / "HGNC" / "hgnc_complete_set_2026-04-07.txt"
TEST_CASES_PATH: Final[Path] = PROJECT_ROOT / "data" / "test_cases" / "test_cases.jsonl"
OUT_ROOT: Final[Path] = PROJECT_ROOT / "data" / "eval"

# Per-gene retrieval budget for single-agent runs.
SINGLE_AGENT_TOP_K: Final[int] = 10
# Multi-agent per-gene budget defaults from build_graph().
MULTI_AGENT_TOP_K: Final[int] = 10


# ---------------------------------------------------------------- cell map
CellId = Literal["A", "B", "C", "D"]
CELL_NAMES: dict[CellId, str] = {
    "A": "cell_A_single_dense",
    "B": "cell_B_single_hybrid",
    "C": "cell_C_multi_dense",
    "D": "cell_D_multi_hybrid",
}


# ---------------------------------------------------------------- HPO label lookup
def hpo_term_labels(ontology: pronto.Ontology, hpo_ids: list[str]) -> list[str]:
    """Look up the human-readable name for each HPO ID."""
    out: list[str] = []
    for tid in hpo_ids:
        term = ontology.get(tid)
        if term is not None and term.name:
            out.append(term.name)
    return out


# ---------------------------------------------------------------- single-agent
def run_single_agent_cell(
    *,
    case: dict,
    retrieval_mode: Literal["dense", "hybrid"],
    search_cfg: SearchConfig,
    hpo_ontology: pronto.Ontology,
    top_k: int = SINGLE_AGENT_TOP_K,
) -> list[GeneCandidate]:
    """Cell A/B: per-gene query, sum of chunk scores, rank.

    Query per gene is ``"<gene_symbol> <hpo labels joined>"``. This keeps
    the query gene-specific (matches the multi-agent per-gene retrieval
    in Cells C/D) while skipping the Planner→Critic loop and the
    aggregation heuristics in the Synthesizer.
    """
    hpo_labels = hpo_term_labels(hpo_ontology, case["hpo_terms"])
    hpo_str = " ".join(hpo_labels)

    gene_scores: dict[str, tuple[float, list[str]]] = {}
    for gene in case["candidate_genes"]:
        query = f"{gene} {hpo_str}".strip()
        chunks = hybrid_search(
            cfg=search_cfg,
            query=query,
            top_k=top_k,
            mode=retrieval_mode,
        )
        # Score = sum over top-K chunk scores in the relevant channel.
        score = 0.0
        supporting: list[str] = []
        for c in chunks:
            if retrieval_mode == "dense":
                s = c.score_dense or 0.0
            else:  # hybrid
                s = c.score_rrf or c.score_dense or 0.0
            score += s
            supporting.append(c.chunk_id)
        gene_scores[gene] = (score, supporting)

    # Rank by score desc; deterministic tiebreaker: input order of candidate_genes.
    causal = case["causal_gene"]
    ranked_pairs = sorted(
        enumerate(case["candidate_genes"]),
        key=lambda iv: (-gene_scores[iv[1]][0], iv[0]),
    )
    return [
        GeneCandidate(
            symbol=gene,
            is_causal=(gene == causal),
            aggregate_confidence=gene_scores[gene][0],
            supporting_chunks=gene_scores[gene][1],
            final_rank=rank + 1,
        )
        for rank, (_orig_idx, gene) in enumerate(ranked_pairs)
    ]


# ---------------------------------------------------------------- multi-agent
def run_multi_agent_cell(
    *,
    case: dict,
    retrieval_mode: Literal["dense", "hybrid"],
    search_cfg: SearchConfig,
    hpo_ontology: pronto.Ontology,
    hgnc_index,
) -> list[GeneCandidate]:
    """Cell C/D: full Planner→Retriever→Critic→Synthesizer graph."""
    graph = build_graph(
        hpo_ontology=hpo_ontology,
        search_cfg=search_cfg,
        hgnc_index=hgnc_index,
        retriever_top_k=MULTI_AGENT_TOP_K,
        retriever_mode=retrieval_mode,
    )
    initial = AgentState(
        case_id=case["case_id"],
        hpo_terms=case["hpo_terms"],
        candidate_genes=case["candidate_genes"],
    )
    final_state = graph.invoke(initial)
    # LangGraph returns a dict-shaped result; convert back to AgentState if needed.
    ranked = final_state.get("ranked", []) if isinstance(final_state, dict) else final_state.ranked

    # Mark is_causal post-hoc using ground truth (deterministic agents don't know it).
    causal = case["causal_gene"]
    out: list[GeneCandidate] = []
    for gc in ranked:
        if isinstance(gc, dict):
            gc = GeneCandidate(**gc)
        gc.is_causal = gc.symbol == causal
        out.append(gc)
    return out


# ---------------------------------------------------------------- per-case I/O
def write_result(out_path: Path, ranked: list[GeneCandidate]) -> None:
    """Persist a per-case ranked list as JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(g) for g in ranked]
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def already_done(out_path: Path) -> bool:
    """Return True if a non-empty result for this (cell, case) is on disk."""
    return out_path.exists() and out_path.stat().st_size > 0


# ---------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--cells",
        type=str,
        default="ABCD",
        help="Cells to run, any subset of A/B/C/D (default: all four).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N test cases (debug).",
    )
    parser.add_argument("--test-cases", type=Path, default=TEST_CASES_PATH)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run cells whose output JSON already exists.",
    )
    args = parser.parse_args()

    cells = sorted({c.upper() for c in args.cells if c.upper() in "ABCD"})
    if not cells:
        log.error("No valid cells in --cells %s; pick from A B C D", args.cells)
        return 1

    # Load all the dependencies once.
    log.info("Loading test cases from %s", args.test_cases)
    cases = [json.loads(ln) for ln in args.test_cases.read_text().splitlines() if ln]
    if args.limit:
        cases = cases[: args.limit]
    log.info("Loaded %d cases", len(cases))

    log.info("Loading HPO ontology from %s", HPO_PATH)
    hpo = pronto.Ontology(str(HPO_PATH))
    log.info("HPO loaded (%d terms)", len(hpo))

    log.info("Loading HGNC index from %s", HGNC_PATH)
    hgnc = load_hgnc(HGNC_PATH)
    log.info("HGNC loaded (%d canonical symbols)", len(hgnc.by_symbol))

    log.info("Loading dense model: %s", DENSE_MODEL_PATH)
    dense_model = SentenceTransformer(DENSE_MODEL_PATH)
    log.info("Loading sparse model: %s", SPARSE_MODEL_NAME)
    bm25_model = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)

    qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)
    search_cfg = SearchConfig(
        client=qdrant_client,
        collection_name=COLLECTION,
        dense_model=dense_model,
        bm25_model=bm25_model,
    )
    log.info("Qdrant connection: %s:%d / %s", QDRANT_HOST, QDRANT_PORT, COLLECTION)

    # Dispatch table: cell -> runner function (kwargs-only, returns list[GeneCandidate])
    runners = {
        "A": lambda case: run_single_agent_cell(
            case=case, retrieval_mode="dense", search_cfg=search_cfg, hpo_ontology=hpo
        ),
        "B": lambda case: run_single_agent_cell(
            case=case, retrieval_mode="hybrid", search_cfg=search_cfg, hpo_ontology=hpo
        ),
        "C": lambda case: run_multi_agent_cell(
            case=case,
            retrieval_mode="dense",
            search_cfg=search_cfg,
            hpo_ontology=hpo,
            hgnc_index=hgnc,
        ),
        "D": lambda case: run_multi_agent_cell(
            case=case,
            retrieval_mode="hybrid",
            search_cfg=search_cfg,
            hpo_ontology=hpo,
            hgnc_index=hgnc,
        ),
    }

    overall_start = time.monotonic()
    for cell in cells:
        cell_dir = args.out_root / CELL_NAMES[cell]
        cell_dir.mkdir(parents=True, exist_ok=True)
        log.info("=== Cell %s: %s ===", cell, CELL_NAMES[cell])
        cell_start = time.monotonic()
        n_done = n_skip = n_err = 0
        for i, case in enumerate(cases, 1):
            out_path = cell_dir / f"{case['case_id']}.json"
            if not args.force and already_done(out_path):
                n_skip += 1
                continue
            t0 = time.monotonic()
            try:
                ranked = runners[cell](case)
            except Exception as e:
                log.exception("Cell %s case %s failed: %s", cell, case["case_id"], e)
                n_err += 1
                continue
            write_result(out_path, ranked)
            dt = time.monotonic() - t0
            n_done += 1
            # Find the rank of the causal gene
            causal_rank = next((g.final_rank for g in ranked if g.is_causal), None)
            log.info(
                "  [%d/%d] %s causal_rank=%s (%.2fs)",
                i,
                len(cases),
                case["case_id"],
                causal_rank,
                dt,
            )
        cell_dt = time.monotonic() - cell_start
        log.info(
            "Cell %s done in %.1fmin: done=%d skipped=%d errors=%d",
            cell,
            cell_dt / 60,
            n_done,
            n_skip,
            n_err,
        )

    total_dt = time.monotonic() - overall_start
    log.info("=== Factorial run complete in %.1fmin ===", total_dt / 60)
    log.info("Outputs in: %s", args.out_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
