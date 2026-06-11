"""Leave-one-paper-out (LOPO) robustness pilot — literature-redundancy analysis.

Tests whether geno_agent's accuracy depends on retrieving each case's *own*
source publication (the case report the Phenopacket was transcribed from). For
each sampled case we run two arms that differ ONLY in retrieval:

  * **control** — retrieval exactly as in the paper (Cell L / Cell S pipeline).
  * **lopo**    — identical, but chunks whose payload ``pmid`` equals the case's
    source PMID are dropped from each gene's candidate pool *before* reranking.
    The article is NOT removed from Qdrant; it is excluded only for this case's
    inference. This is the geno_agent-side counterpart to the LIRICAL
    annotation-overlap stratification (Thread D).

Both arms share the same retrieval call (we fetch ``RETRIEVAL_TOP_K + BUFFER``
once per gene, then form the two candidate pools), so the comparison is a clean
paired test isolating the source-paper contribution.

Reads:  data/test_cases_1050/test_cases.jsonl
        data/test_cases_1050/annotation_overlap.json   (case_id -> source_pmid)
Writes: <out-root>/cell_<L|S>_control_pilot/<case>.json
        <out-root>/cell_<L|S>_lopo_pilot/<case>.json
        <out-root>/_lopo_pilot_summary.json            (paired deltas + leak rates)

Cell L (deterministic; no vLLM):
    PYTHONPATH=. python scripts/eval/run_lopo.py --n 100

Cell S (adds LEA; requires a local vLLM server serving Qwen3-8B):
    PYTHONPATH=. python scripts/eval/run_lopo.py --n 100 --use-lea
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Final

import pronto
import torch
from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder, SentenceTransformer

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.critic import critic_node  # noqa: E402
from src.agents.query_planner import build_mesh_queries  # noqa: E402
from src.agents.retriever import retrieve_for_gene  # noqa: E402
from src.agents.state import AgentState, RetrievedChunk  # noqa: E402
from src.agents.synthesizer import synthesizer_node  # noqa: E402
from src.agents.synthesizer_lea import lea_synthesizer_node  # noqa: E402
from src.tools.hgnc import load_hgnc  # noqa: E402
from src.tools.qdrant_search import SearchConfig  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lopo")

# --- pipeline constants (must mirror rerank_inside_d.py for a faithful control)
CROSS_ENCODER_MODEL: Final[str] = "ncbi/MedCPT-Cross-Encoder"
RETRIEVAL_TOP_K: Final[int] = 50
RERANK_KEEP_TOP_K: Final[int] = 10
DEFAULT_BUFFER: Final[int] = 30  # extra chunks fetched so LOPO can backfill drops

QDRANT_HOST: Final[str] = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: Final[int] = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION: Final[str] = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL_PATH: Final[str] = os.environ.get(
    "DENSE_MODEL_PATH", "NeuML/pubmedbert-base-embeddings"
)
SPARSE_MODEL_NAME: Final[str] = "Qdrant/bm25"

HPO_OBO_PATH: Final[Path] = PROJECT_ROOT / "data" / "Human_Phenotype_Ontology" / "hp.obo"
HGNC_PATH: Final[Path] = PROJECT_ROOT / "data" / "HGNC" / "hgnc_complete_set_2026-04-07.txt"
DEFAULT_CASES: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "test_cases.jsonl"
DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
DEFAULT_OUT_ROOT: Final[Path] = PROJECT_ROOT / "data" / "eval_1050_lopo"


def strip_pmid(raw: str | None) -> str:
    """Normalise ``"PMID:24573067"`` (or ``"24573067"``) to bare digits ``"24573067"``."""
    if not raw:
        return ""
    return raw.split(":", 1)[1].strip() if raw.upper().startswith("PMID:") else raw.strip()


def load_source_pmids(overlap_path: Path) -> dict[str, str]:
    """Return ``{case_id: source_pmid_digits}`` from annotation_overlap.json."""
    data = json.loads(overlap_path.read_text())
    out: dict[str, str] = {}
    for rec in data["records"]:
        out[rec["case_id"]] = strip_pmid(rec.get("source_pmid"))
    return out


def stratified_sample(cases: list[dict], n: int, seed: int) -> list[dict]:
    """Pick ``n`` cases, allocated across MONDO categories proportional to the cohort.

    Largest-remainder apportionment keeps the sample's category mix equal to the
    full cohort's; sampling within each stratum is seeded for reproducibility.
    """
    by_cat: dict[str, list[dict]] = {}
    for c in cases:
        by_cat.setdefault(c.get("category", "unknown"), []).append(c)
    total = len(cases)
    # largest-remainder apportionment of n across categories
    raw = {cat: n * len(v) / total for cat, v in by_cat.items()}
    alloc = {cat: math.floor(x) for cat, x in raw.items()}
    remainder = n - sum(alloc.values())
    for cat in sorted(by_cat, key=lambda k: raw[k] - alloc[k], reverse=True)[:remainder]:
        alloc[cat] += 1
    rng = random.Random(seed)
    picked: list[dict] = []
    for cat in sorted(by_cat):
        pool = sorted(by_cat[cat], key=lambda c: c["case_id"])
        k = min(alloc.get(cat, 0), len(pool))
        picked.extend(rng.sample(pool, k))
    picked.sort(key=lambda c: c["case_id"])
    return picked


def causal_rank(ranked: list[dict]) -> int | None:
    """Return the 1-based final_rank of the causal gene, or None."""
    return next((p["final_rank"] for p in ranked if p["is_causal"]), None)


def run_arm(
    *,
    case: dict,
    pooled: dict[str, list[RetrievedChunk]],
    source_pmid: str,
    drop_source: bool,
    cross_encoder: CrossEncoder,
    hpo_ontology: pronto.Ontology,
    hgnc,
    mesh_queries: list[str],
    use_lea: bool,
) -> tuple[list[dict], int]:
    """Run one arm (control or LOPO) from a shared retrieval pool.

    Returns ``(ranked_payload, n_source_chunks_dropped)``.
    """
    state = AgentState(
        case_id=case["case_id"],
        hpo_terms=case["hpo_terms"],
        candidate_genes=case["candidate_genes"],
    )
    state.mesh_queries = mesh_queries
    n_dropped = 0
    for j, gene in enumerate(state.candidate_genes):
        chunks = pooled[gene]
        if drop_source and source_pmid:
            kept = [c for c in chunks if c.pmid != source_pmid]
            n_dropped += len(chunks) - len(kept)
            chunks = kept
        # Trim to the paper's per-gene candidate budget before reranking.
        chunks = chunks[:RETRIEVAL_TOP_K]
        if not chunks:
            state.retrieved[gene] = []
            continue
        query = mesh_queries[j] if j < len(mesh_queries) else gene
        pairs = [(query, c.text or "") for c in chunks]
        scores = cross_encoder.predict(pairs, batch_size=64, show_progress_bar=False)
        paired = sorted(zip(chunks, scores, strict=True), key=lambda t: -float(t[1]))
        state.retrieved[gene] = [c for c, _ in paired[:RERANK_KEEP_TOP_K]]

    state = critic_node(state, hpo_ontology, hgnc)
    state = lea_synthesizer_node(state, hpo_ontology) if use_lea else synthesizer_node(state)

    causal = case["causal_gene"]
    payload = []
    for c in state.ranked:
        entry = asdict(c)
        entry["is_causal"] = entry["symbol"] == causal
        payload.append(entry)
    return payload, n_dropped


def measure_leak(case: dict, pooled: dict[str, list[RetrievedChunk]], source_pmid: str) -> dict:
    """Quantify how strongly the source paper appears in retrieval for this case."""
    causal = case["causal_gene"]
    causal_pool = pooled.get(causal, [])
    src_positions = [i for i, c in enumerate(causal_pool) if c.pmid and c.pmid == source_pmid]
    n_src_all_genes = sum(
        1 for chunks in pooled.values() for c in chunks if c.pmid and c.pmid == source_pmid
    )
    return {
        "case_id": case["case_id"],
        "source_pmid": source_pmid,
        "source_in_causal_pool": bool(src_positions),
        "source_best_pos_in_causal_pool": (min(src_positions) if src_positions else None),
        "source_chunks_in_causal_pool": len(src_positions),
        "source_chunks_all_genes": n_src_all_genes,
    }


def mcnemar(control: list[int | None], lopo: list[int | None]) -> dict:
    """Paired top-1 McNemar over (control, lopo) causal ranks. Exact binomial p."""
    c_top1 = [1 if r == 1 else 0 for r in control]
    l_top1 = [1 if r == 1 else 0 for r in lopo]
    b = sum(1 for a, x in zip(c_top1, l_top1, strict=True) if a == 1 and x == 0)  # ctrl-only
    c = sum(1 for a, x in zip(c_top1, l_top1, strict=True) if a == 0 and x == 1)  # lopo-only
    n = b + c
    # exact two-sided binomial p (p=0.5)
    if n == 0:
        p = 1.0
    else:
        k = min(b, c)
        tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
        p = min(1.0, 2 * tail)
    return {
        "control_top1": sum(c_top1),
        "lopo_top1": sum(l_top1),
        "n": len(control),
        "control_top1_acc": round(sum(c_top1) / len(control), 4),
        "lopo_top1_acc": round(sum(l_top1) / len(lopo), 4),
        "delta_top1": round((sum(l_top1) - sum(c_top1)) / len(control), 4),
        "discordant_control_only": b,
        "discordant_lopo_only": c,
        "mcnemar_p": round(p, 5),
    }


def topk_acc(ranks: list[int | None], k: int) -> float:
    return round(sum(1 for r in ranks if r is not None and r <= k) / len(ranks), 4)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--n", type=int, default=100, help="Stratified sample size (default 100).")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Run every case in the cohort (in file order), bypassing --n sampling.",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--use-lea", action="store_true", help="Cell S (adds LEA; needs vLLM).")
    ap.add_argument("--buffer", type=int, default=DEFAULT_BUFFER)
    ap.add_argument("--test-cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    cell = "S" if args.use_lea else "L"
    ctrl_dir = args.out_root / f"cell_{cell}_control"
    lopo_dir = args.out_root / f"cell_{cell}_lopo"
    leak_dir = args.out_root / f"leak_{cell}"
    for d in (ctrl_dir, lopo_dir, leak_dir):
        d.mkdir(parents=True, exist_ok=True)

    all_cases = [json.loads(ln) for ln in args.test_cases.read_text().splitlines() if ln.strip()]
    src_map = load_source_pmids(args.overlap)
    if args.all:
        sample = sorted(all_cases, key=lambda c: c["case_id"])
        log.info("Running ALL %d cases (cell %s)", len(sample), cell)
    else:
        sample = stratified_sample(all_cases, args.n, args.seed)
        log.info(
            "Sampled %d/%d cases (cell %s, seed %d)", len(sample), len(all_cases), cell, args.seed
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("Loading models on %s ...", device)
    cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL, device=device, max_length=512)
    hpo_ontology = pronto.Ontology(str(HPO_OBO_PATH))
    hgnc = load_hgnc(HGNC_PATH)
    dense_model = SentenceTransformer(DENSE_MODEL_PATH, device=device)
    bm25_model = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)
    qclient = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)
    cfg = SearchConfig(
        client=qclient, collection_name=COLLECTION, dense_model=dense_model, bm25_model=bm25_model
    )
    log.info("Qdrant %s:%d / %s", QDRANT_HOST, QDRANT_PORT, COLLECTION)

    fetch_k = RETRIEVAL_TOP_K + args.buffer
    t0 = time.time()
    n_run = n_skip = 0

    for i, case in enumerate(sample, 1):
        cid = case["case_id"]
        cpath = ctrl_dir / f"{cid}.json"
        lpath = lopo_dir / f"{cid}.json"
        kpath = leak_dir / f"{cid}.json"
        if not args.overwrite and cpath.exists() and lpath.exists() and kpath.exists():
            n_skip += 1
            continue

        source_pmid = src_map.get(cid, "")
        state = AgentState(
            case_id=cid, hpo_terms=case["hpo_terms"], candidate_genes=case["candidate_genes"]
        )
        mesh_queries = build_mesh_queries(state, hpo_ontology)

        # Shared retrieval pool: fetch once per gene, reuse for both arms.
        pooled: dict[str, list[RetrievedChunk]] = {}
        for j, gene in enumerate(case["candidate_genes"]):
            q = mesh_queries[j] if j < len(mesh_queries) else gene
            pooled[gene] = retrieve_for_gene(cfg, q, gene=gene, top_k=fetch_k, mode="hybrid")

        leak = measure_leak(case, pooled, source_pmid)
        leak["category"] = case.get("category", "unknown")

        ctrl_payload, _ = run_arm(
            case=case,
            pooled=pooled,
            source_pmid=source_pmid,
            drop_source=False,
            cross_encoder=cross_encoder,
            hpo_ontology=hpo_ontology,
            hgnc=hgnc,
            mesh_queries=mesh_queries,
            use_lea=args.use_lea,
        )
        lopo_payload, n_dropped = run_arm(
            case=case,
            pooled=pooled,
            source_pmid=source_pmid,
            drop_source=True,
            cross_encoder=cross_encoder,
            hpo_ontology=hpo_ontology,
            hgnc=hgnc,
            mesh_queries=mesh_queries,
            use_lea=args.use_lea,
        )
        leak["n_source_chunks_dropped"] = n_dropped

        cpath.write_text(json.dumps(ctrl_payload, indent=2))
        lpath.write_text(json.dumps(lopo_payload, indent=2))
        kpath.write_text(json.dumps(leak, indent=2))
        n_run += 1

        cr, lr = causal_rank(ctrl_payload), causal_rank(lopo_payload)
        flip = "" if cr == lr else f"  <-- RANK CHANGE {cr}->{lr}"
        log.info(
            "[%d/%d] %s ctrl_rank=%s lopo_rank=%s (src_in_causal=%s, dropped=%d)%s",
            i,
            len(sample),
            cid,
            cr,
            lr,
            leak["source_in_causal_pool"],
            n_dropped,
            flip,
        )

    log.info("Processed %d, skipped %d already-done.", n_run, n_skip)

    # ---- summary (rebuilt from disk so it is correct even after a resumed run)
    ctrl_ranks: list[int | None] = []
    lopo_ranks: list[int | None] = []
    leak_records: list[dict] = []
    for case in sample:
        cid = case["case_id"]
        cpath, lpath, kpath = (
            ctrl_dir / f"{cid}.json",
            lopo_dir / f"{cid}.json",
            leak_dir / f"{cid}.json",
        )
        if not (cpath.exists() and lpath.exists() and kpath.exists()):
            continue
        ctrl_ranks.append(causal_rank(json.loads(cpath.read_text())))
        lopo_ranks.append(causal_rank(json.loads(lpath.read_text())))
        leak_records.append(json.loads(kpath.read_text()))
    mc = mcnemar(ctrl_ranks, lopo_ranks)
    n = len(ctrl_ranks)
    summary = {
        "cell": cell,
        "n": n,
        "seed": args.seed,
        "fetch_k": fetch_k,
        "paired_top1": mc,
        "control_topk": {f"top{k}": topk_acc(ctrl_ranks, k) for k in (1, 5, 10)},
        "lopo_topk": {f"top{k}": topk_acc(lopo_ranks, k) for k in (1, 5, 10)},
        "leak": {
            "source_in_causal_pool_rate": round(
                sum(1 for r in leak_records if r["source_in_causal_pool"]) / n, 4
            ),
            "source_top_of_causal_pool_rate": round(
                sum(1 for r in leak_records if r["source_best_pos_in_causal_pool"] == 0) / n, 4
            ),
            "mean_source_chunks_in_causal_pool": round(
                sum(r["source_chunks_in_causal_pool"] for r in leak_records) / n, 3
            ),
        },
        "wallclock_min": round((time.time() - t0) / 60, 1),
    }
    summary_path = args.out_root / f"_lopo_cell_{cell}_summary.json"
    summary_path.write_text(
        json.dumps({"summary": summary, "leak_records": leak_records}, indent=2)
    )

    print("\n" + "=" * 64)
    print(f"  LOPO — Cell {cell}  (n={n}, all={args.all}, seed={args.seed})")
    print("=" * 64)
    print(f"  control top-1 : {mc['control_top1_acc']:.4f}  ({mc['control_top1']}/{n})")
    print(f"  LOPO    top-1 : {mc['lopo_top1_acc']:.4f}  ({mc['lopo_top1']}/{n})")
    print(f"  delta top-1   : {mc['delta_top1']:+.4f}")
    print(
        f"  discordant    : control-only={mc['discordant_control_only']}  "
        f"lopo-only={mc['discordant_lopo_only']}  McNemar p={mc['mcnemar_p']}"
    )
    print(
        f"  control top-5/10: {summary['control_topk']['top5']:.3f} / "
        f"{summary['control_topk']['top10']:.3f}"
    )
    print(
        f"  LOPO    top-5/10: {summary['lopo_topk']['top5']:.3f} / "
        f"{summary['lopo_topk']['top10']:.3f}"
    )
    print("  --- leak (how often the source paper is in retrieval) ---")
    print(
        f"  source paper in causal-gene pool : {summary['leak']['source_in_causal_pool_rate']:.3f}"
    )
    print(
        f"  source paper top of causal pool  : {summary['leak']['source_top_of_causal_pool_rate']:.3f}"
    )
    print(
        f"  mean source chunks / causal pool : {summary['leak']['mean_source_chunks_in_causal_pool']:.2f}"
    )
    print(f"  wallclock: {summary['wallclock_min']} min   ->  {summary_path}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
