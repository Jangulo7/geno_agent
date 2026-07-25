"""Index-level retrieval-substrate validation for the P1 resource paper.

The cohort half of the resource has an SHA-256-verified end-to-end regeneration.
The index half establishes that the indexed content is *regenerable* but says
nothing about whether it is *useful*. This script supplies two index-level
characterisations that close that gap:

**Check A --- source-article recall.** Each benchmark case was curated from a
specific publication, so that publication is ground truth for "should be
retrievable". For every case whose source article is actually in the index, we
issue two queries --- the causal gene symbol, and the space-joined HPO term
labels --- and report the fraction of cases whose source PMCID appears among the
parent articles of the top-k retrieved chunks, for k in {10, 50, 100}.

**Check B --- symbol grounding.** For 100 causal genes sampled with the cohort's
BLAKE2b-derived seed convention, we query the index with the gene symbol and
report the fraction of the top-100 retrieved chunks whose text matches the symbol
under a case-sensitive word-boundary regex.

Both checks are properties of the corpus and the retrieval configuration alone.
No ranking model, language model or prioritisation tool is involved, and neither
constitutes a tool-comparison result or a performance claim for any system built
on the substrate.

The retrieval configuration is the one used to compute the released
``pmc_article_count`` descriptor (``scripts/cases/17_validate_pmc_coverage.py``):
dense PubMedBERT prefetch and BM25 sparse prefetch, each at limit k, fused with
Reciprocal Rank Fusion (k = 60), matching the parameters tabulated in the paper.

Prerequisites: a running Qdrant v1.14.1 with the ``geno_agent_pmc_oa_v1``
collection, and network access to the NCBI ID Converter API.

Output: ``release/index_fingerprint/retrieval_substrate_validation.json``

Run from project root:
``python scripts/eval/validate_retrieval_substrate.py [--workers 8]``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

import requests
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("retrieval_substrate")

# ---------------------------------------------------------------- config
QDRANT_HOST: Final[str] = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: Final[int] = int(os.environ.get("QDRANT_PORT", "6533"))
COLLECTION: Final[str] = os.environ.get("QDRANT_COLLECTION", "geno_agent_pmc_oa_v1")
DENSE_MODEL: Final[str] = os.environ.get(
    "EMBED_MODEL_NAME",
    "/home/hana77/rare-disease-rag/models/pubmedbert-base-embeddings",
)
SPARSE_MODEL: Final[str] = "Qdrant/bm25"
TOP_K: Final[int] = 100
RECALL_KS: Final[tuple[int, ...]] = (10, 50, 100)
N_SYMBOL_GROUNDING: Final[int] = 100

CASES_PATH: Final[Path] = PROJECT_ROOT / "data/test_cases_1050/test_cases.jsonl"
RETAINED_PATH: Final[Path] = PROJECT_ROOT / "release/cohort/retained_pmcids.txt"
HPO_OBO: Final[Path] = PROJECT_ROOT / "data/Human_Phenotype_Ontology/hp.obo"
OUT_PATH: Final[Path] = (
    PROJECT_ROOT / "release/index_fingerprint/retrieval_substrate_validation.json"
)
CACHE_DIR: Final[Path] = PROJECT_ROOT / "logs" / "_retrieval_validation_cache"
IDCONV_URL: Final[str] = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"

_PMID_RE: Final[re.Pattern[str]] = re.compile(r"PMID_(\d+)")
_local = threading.local()


# ---------------------------------------------------------------- inputs
def load_cases() -> list[dict]:
    """Load the released standard-variant cohort."""
    return [json.loads(line) for line in CASES_PATH.read_text().splitlines() if line.strip()]


def parse_hpo_labels() -> dict[str, str]:
    """Map HPO term id -> primary label from the pinned ``hp.obo``.

    Returns:
        Mapping of ``HP:NNNNNNN`` to its ``name:`` field. Obsolete-term
        ``alt_id`` entries are also mapped to the primary term's label so a case
        carrying a legacy identifier still contributes its label.
    """
    labels: dict[str, str] = {}
    tid: str | None = None
    name: str | None = None
    alts: list[str] = []
    for line in HPO_OBO.read_text(encoding="utf-8").splitlines():
        if line == "[Term]":
            if tid and name:
                labels[tid] = name
                for a in alts:
                    labels[a] = name
            tid, name, alts = None, None, []
        elif line.startswith("id: HP:"):
            tid = line[4:].strip()
        elif line.startswith("name: "):
            name = line[6:].strip()
        elif line.startswith("alt_id: HP:"):
            alts.append(line[8:].strip())
    if tid and name:
        labels[tid] = name
        for a in alts:
            labels[a] = name
    return labels


def pmid_to_pmcid(pmids: list[str]) -> dict[str, str]:
    """Map PubMed identifiers to PMC identifiers via the NCBI ID Converter API.

    Args:
        pmids: PubMed identifiers as digit strings.

    Returns:
        Mapping of PMID -> ``PMCxxxxxxx`` for those with a PMC record. PMIDs
        with no PMC record are absent from the mapping.
    """
    out: dict[str, str] = {}
    for i in range(0, len(pmids), 200):
        batch = pmids[i : i + 200]
        r = requests.get(
            IDCONV_URL,
            params={
                "ids": ",".join(batch),
                "format": "json",
                "tool": "geno_agent_p1_retrieval_validation",
                "email": "224F2279@live.uem.es",
            },
            timeout=60,
        )
        r.raise_for_status()
        for rec in r.json().get("records", []):
            if rec.get("pmcid") and rec.get("pmid"):
                out[str(rec["pmid"])] = rec["pmcid"]
        log.info("id-converter: %d/%d PMIDs processed", min(i + 200, len(pmids)), len(pmids))
        time.sleep(0.4)  # stay well inside the NCBI rate limit
    return out


# ---------------------------------------------------------------- retrieval
def client() -> QdrantClient:
    """Return this thread's Qdrant client, creating it on first use."""
    if not hasattr(_local, "client"):
        _local.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=600)
    return _local.client


def query(dense_vec: list[float], sparse, with_text: bool, attempts: int = 6) -> list[dict]:
    """Run one hybrid RRF query and return the ranked payloads.

    The collection is 323 GB with on-disk HNSW and payload, and long
    multi-term HPO-label queries can exceed Qdrant's internal read timeout under
    load. Such a failure is transient and says nothing about retrievability, so
    it is retried with exponential backoff rather than being scored as a miss ---
    counting it as a miss would silently bias recall downwards.

    Args:
        dense_vec: L2-normalised PubMedBERT query embedding.
        sparse: fastembed BM25 query embedding (term-frequency only; IDF is
            applied server-side by the collection's ``Modifier.IDF``).
        with_text: Whether to pull chunk text (needed only by Check B).
        attempts: Maximum tries before giving up.

    Returns:
        Up to ``TOP_K`` payload dicts in fused-rank order.

    Raises:
        RuntimeError: If every attempt fails, so the run aborts loudly instead
            of writing a silently incomplete result.
    """
    fields = ["pmcid", "text"] if with_text else ["pmcid"]
    last: Exception | None = None
    for i in range(attempts):
        try:
            res = client().query_points(
                collection_name=COLLECTION,
                prefetch=[
                    models.Prefetch(query=dense_vec, using="dense", limit=TOP_K),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse.indices.tolist(),
                            values=sparse.values.tolist(),
                        ),
                        using="bm25",
                        limit=TOP_K,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=TOP_K,
                with_payload=fields,
            )
            return [p.payload for p in res.points]
        except Exception as e:
            last = e
            # Drop the client so the next attempt reconnects cleanly.
            if hasattr(_local, "client"):
                del _local.client
            if i < attempts - 1:
                time.sleep(2**i)
    raise RuntimeError(f"query failed after {attempts} attempts: {last}")


def encode_all(
    texts: list[str], dense_model: SentenceTransformer, bm25_model: SparseTextEmbedding
) -> tuple[list, list]:
    """Batch-encode every query once, so the parallel phase is pure I/O."""
    dense = dense_model.encode(
        texts, normalize_embeddings=True, batch_size=128, show_progress_bar=False
    )
    sparse = list(bm25_model.query_embed(texts))
    return [v.tolist() for v in dense], sparse


def run_queries(
    texts: list[str],
    dense_model: SentenceTransformer,
    bm25_model: SparseTextEmbedding,
    workers: int,
    with_text: bool,
    label: str,
) -> list[list[dict]]:
    """Encode and execute a batch of queries with a bounded thread pool.

    Each completed phase is cached under ``CACHE_DIR`` keyed by its label and
    query list, so a crash part-way through the run does not force the earlier
    phases (thousands of seconds of retrieval) to be repeated.
    """
    key = hashlib.blake2b(
        (label + "\x00" + "\x00".join(texts)).encode(), digest_size=16
    ).hexdigest()
    cache = CACHE_DIR / f"{label.replace('/', '_')}.{key}.json"
    if cache.exists():
        log.info("%s: reusing cached results (%s)", label, cache.name)
        return json.loads(cache.read_text())

    log.info("%s: encoding %d queries", label, len(texts))
    dvecs, svecs = encode_all(texts, dense_model, bm25_model)
    log.info("%s: querying with %d workers", label, workers)
    done = [0]
    lock = threading.Lock()

    def one(i: int) -> list[dict]:
        r = query(dvecs[i], svecs[i], with_text)
        with lock:
            done[0] += 1
            if done[0] % 50 == 0:
                log.info("%s: %d/%d", label, done[0], len(texts))
        return r

    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(one, range(len(texts))))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    log.info("%s: cached to %s", label, cache.name)
    return out


# ---------------------------------------------------------------- checks
def recall_at_k(payloads: list[dict], target_pmcid: str) -> dict[int, bool]:
    """Whether ``target_pmcid`` is a parent article of the top-k chunks."""
    seen: list[str] = [p.get("pmcid", "") for p in payloads]
    return {k: target_pmcid in seen[:k] for k in RECALL_KS}


def main() -> int:
    """Run both checks and write the results JSON."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    cases = load_cases()
    log.info("cohort: %d cases", len(cases))

    for c in cases:
        m = _PMID_RE.search(c["case_id"])
        if m is None:
            raise ValueError(f"no PMID in case_id {c['case_id']!r}")
        c["_pmid"] = m.group(1)

    unique_pmids = sorted({c["_pmid"] for c in cases})
    log.info("unique source PMIDs: %d", len(unique_pmids))

    log.info("mapping PMID -> PMCID via NCBI ID Converter")
    pmid2pmcid = pmid_to_pmcid(unique_pmids)
    log.info("PMIDs with a PMC record: %d/%d", len(pmid2pmcid), len(unique_pmids))

    log.info("loading retained PMCID set")
    retained = set(RETAINED_PATH.read_text().split())
    log.info("retained PMCIDs in index: %d", len(retained))

    in_index = {p: m for p, m in pmid2pmcid.items() if m in retained}
    ceiling = len(in_index)
    log.info(
        "CEILING: %d/%d unique source PMIDs are in the index (%.1f%%)",
        ceiling,
        len(unique_pmids),
        100 * ceiling / len(unique_pmids),
    )

    eligible = [c for c in cases if c["_pmid"] in in_index]
    log.info("eligible cases (source article in index): %d", len(eligible))

    log.info("loading models")
    dense_model = SentenceTransformer(DENSE_MODEL)
    bm25_model = SparseTextEmbedding(model_name=SPARSE_MODEL)
    hpo_labels = parse_hpo_labels()

    # ---- Check A ---------------------------------------------------------
    gene_q = [c["causal_gene"] for c in eligible]
    hpo_q = [" ".join(hpo_labels[t] for t in c["hpo_terms"] if t in hpo_labels) for c in eligible]
    n_empty_hpo = sum(1 for q in hpo_q if not q.strip())
    if n_empty_hpo:
        log.warning("%d eligible cases have no resolvable HPO labels", n_empty_hpo)

    gene_res = run_queries(gene_q, dense_model, bm25_model, args.workers, False, "checkA/gene")
    hpo_res = run_queries(hpo_q, dense_model, bm25_model, args.workers, False, "checkA/hpo")

    check_a: dict[str, dict] = {}
    for qname, results in (("causal_gene_symbol", gene_res), ("hpo_term_labels", hpo_res)):
        hits = dict.fromkeys(RECALL_KS, 0)
        for c, payloads in zip(eligible, results, strict=True):
            r = recall_at_k(payloads, in_index[c["_pmid"]])
            for k in RECALL_KS:
                hits[k] += int(r[k])
        check_a[qname] = {
            "n_eligible_cases": len(eligible),
            "hits": {str(k): hits[k] for k in RECALL_KS},
            "recall": {str(k): round(hits[k] / len(eligible), 4) for k in RECALL_KS},
        }
        log.info("Check A [%s]: %s", qname, check_a[qname]["recall"])

    # ---- Check B ---------------------------------------------------------
    genes = sorted({c["causal_gene"] for c in cases})
    seed = int.from_bytes(
        hashlib.blake2b(b"42|retrieval_substrate_symbol_grounding", digest_size=8).digest(),
        "big",
    )
    sample = random.Random(seed).sample(genes, min(N_SYMBOL_GROUNDING, len(genes)))
    sample.sort()

    b_res = run_queries(sample, dense_model, bm25_model, args.workers, True, "checkB/symbol")
    fractions: list[float] = []
    per_gene: dict[str, float] = {}
    for sym, payloads in zip(sample, b_res, strict=True):
        pat = re.compile(r"\b" + re.escape(sym) + r"\b")
        n = len(payloads)
        frac = sum(1 for p in payloads if pat.search(p.get("text") or "")) / n if n else 0.0
        fractions.append(frac)
        per_gene[sym] = round(frac, 4)
    fractions.sort()
    mid = len(fractions) // 2
    median = fractions[mid] if len(fractions) % 2 else (fractions[mid - 1] + fractions[mid]) / 2
    check_b = {
        "n_genes": len(sample),
        "seed_convention": (
            "BLAKE2b-64 of b'42|retrieval_substrate_symbol_grounding', "
            "big-endian, seeding random.Random; sampled from the sorted set of "
            "unique causal genes"
        ),
        "regex": r"\bSYMBOL\b (case-sensitive)",
        "mean_fraction_top100_containing_symbol": round(sum(fractions) / len(fractions), 4),
        "median_fraction_top100_containing_symbol": round(median, 4),
        "per_gene": per_gene,
    }
    log.info(
        "Check B: mean %.4f median %.4f",
        check_b["mean_fraction_top100_containing_symbol"],
        check_b["median_fraction_top100_containing_symbol"],
    )

    out = {
        "meta": {
            "collection": COLLECTION,
            "engine": "Qdrant v1.14.1",
            "retrieval": (
                "hybrid: dense PubMedBERT prefetch (limit 100) + BM25 sparse "
                "prefetch (limit 100), fused by Reciprocal Rank Fusion (k=60); "
                "identical to the configuration used for pmc_article_count"
            ),
            "dense_model": "NeuML/pubmedbert-base-embeddings@b79526d6ef3645e0df4530322e266f24c829f5ef",
            "sparse_model": SPARSE_MODEL,
            "top_k": TOP_K,
            "hpo_version": "v2026-02-16",
            "note": (
                "Properties of the corpus and the retrieval configuration alone. "
                "No ranking model, language model or prioritisation tool is "
                "involved; these are not tool-comparison results."
            ),
        },
        "coverage": {
            "unique_source_pmids": len(unique_pmids),
            "pmids_with_pmc_record": len(pmid2pmcid),
            "pmids_in_index": ceiling,
            "fraction_in_index": round(ceiling / len(unique_pmids), 4),
            "eligible_cases": len(eligible),
            "total_cases": len(cases),
        },
        "check_a_source_article_recall": check_a,
        "check_b_symbol_grounding": check_b,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    log.info("wrote %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
