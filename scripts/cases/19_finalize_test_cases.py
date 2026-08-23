"""Persist the canonical Phase 1B test-case JSONL + provenance manifest.

Implements master plan §6 step 7 / §7 step [15]. Reads the candidate-list
output from B7 (``06_with_candidates.jsonl``) and emits two artifacts:

  * ``test_cases.jsonl`` — single canonical file consumed by every Phase 2
    experimental condition (cells A-D + Exomiser baseline E). Sorted by
    ``case_id`` for deterministic ordering. Schema is projected to ONLY
    the fields the downstream evaluation harness needs.
  * ``test_cases_manifest.json`` — provenance record: version pins, RNG
    seed, N cases, category distribution, SHA-256 of the canonical file,
    and creation timestamp.

The manifest is the contract surface between Phase 1B and Phase 2:
anything Phase 2 depends on must be reflected here.

Run from project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/19_finalize_test_cases.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("finalize_test_cases")

# Canonical schema fields — KEEP STABLE. Phase 2 evaluation depends on these.
CANONICAL_FIELDS: Final[tuple[str, ...]] = (
    "case_id",
    "category",
    "hpo_terms",
    "diseases",
    "causal_gene",
    "candidate_genes",
    "causal_gene_index_in_candidates",
    "pmc_article_count",
    "source_phenopacket",
)


def project_to_canonical(rec: dict) -> dict:
    """Project a raw B7 record onto the canonical Phase 2 schema.

    Maps ``source_path`` (from B2) → ``source_phenopacket``. Sets
    ``pmc_article_count`` to ``None`` if the record predates B6 (the
    PMC coverage validation step).

    Args:
        rec: One record from ``06_with_candidates.jsonl``.

    Returns:
        Dict containing only the canonical fields, with explicit ``None``
        for any field the upstream pipeline didn't populate.
    """
    return {
        "case_id": rec["case_id"],
        "category": rec.get("category"),
        "hpo_terms": rec.get("hpo_terms", []),
        "diseases": rec.get("diseases", []),
        "causal_gene": rec["causal_gene"],
        "candidate_genes": rec["candidate_genes"],
        "causal_gene_index_in_candidates": rec.get("causal_gene_index_in_candidates"),
        "pmc_article_count": rec.get("pmc_article_count"),
        "source_phenopacket": rec.get("source_path"),
    }


# Fields excluded from the core digest because they are derived from the live
# retrieval index rather than from the pinned inputs. FP16 embeddings differ in
# their last bits across GPUs, so a rebuilt index can return a slightly
# different top-100 and hence a different pmc_article_count -- which would break
# a full-file digest comparison even though every field that defines the
# benchmark reproduced exactly.
INDEX_DERIVED_FIELDS: Final[frozenset[str]] = frozenset({"pmc_article_count"})


def core_digest(records: list[dict]) -> str:
    """Return the SHA-256 over the canonical records minus index-derived fields.

    This is the digest a third party rebuilding from the pinned files alone
    should verify against. It is computed over exactly the same serialization
    as the canonical file, so the two differ only by the omitted fields.
    """
    h = hashlib.sha256()
    for rec in sorted(records, key=lambda r: r["case_id"]):
        projected = {k: v for k, v in rec.items() if k not in INDEX_DERIVED_FIELDS}
        h.update((json.dumps(projected, ensure_ascii=False) + "\n").encode("utf-8"))
    return h.hexdigest()


def write_canonical_jsonl(records: list[dict], out_path: Path) -> str:
    """Write records to ``out_path`` and return the SHA-256 of the file.

    Records are sorted by ``case_id`` for deterministic byte-stable
    output. The hash is computed AFTER write.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_records = sorted(records, key=lambda r: r["case_id"])
    with out_path.open("w", encoding="utf-8") as f:
        for rec in sorted_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return hashlib.sha256(out_path.read_bytes()).hexdigest()


def _output_path_repr(canonical_path: Path) -> str:
    """Return a project-relative path when possible, else absolute."""
    try:
        return str(canonical_path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(canonical_path)


def _required_env(name: str) -> str:
    """Return ``os.environ[name]``, failing with an actionable message if unset."""
    try:
        return os.environ[name]
    except KeyError:
        raise SystemExit(
            f"{name} is not set. Provenance pins must come from .env, not from a "
            f"hard-coded default -- see .env.example."
        ) from None


def build_manifest(records: list[dict], canonical_path: Path, sha: str) -> dict[str, Any]:
    """Build the provenance manifest dict for the canonical file."""
    cat_dist = Counter(r.get("category") for r in records)
    n_with_pmc = sum(1 for r in records if r.get("pmc_article_count") is not None)
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        # Read, never default. A silent fallback here writes the WRONG upstream
        # version into the one file whose entire purpose is provenance, and the
        # error is invisible in the output. The previous default was "0.1.19",
        # a superseded pin; the released cohort is built on v0.1.26.
        "phenopacket_store_version": _required_env("PHENOPACKET_STORE_VERSION"),
        "mondo_version": _required_env("MONDO_VERSION"),
        "hgnc_snapshot": _required_env("HGNC_SNAPSHOT"),
        "hpo_version": _required_env("HPO_VERSION"),
        "random_seed": int(os.environ.get("RANDOM_SEED", "42")),
        "n_cases": len(records),
        "category_distribution": dict(cat_dist),
        "min_hpo_terms": int(os.environ.get("MIN_HPO_TERMS", "3")),
        "min_pmc_articles_per_gene": int(os.environ.get("MIN_PMC_ARTICLES_PER_GENE", "5")),
        "n_distractors_per_case": int(os.environ.get("N_DISTRACTORS", "49")),
        "n_cases_with_pmc_coverage": n_with_pmc,
        "pmc_coverage_validated": n_with_pmc == len(records),
        "output_path": _output_path_repr(canonical_path),
        "sha256": sha,
        "sha256_core": core_digest(records),
        "sha256_core_note": (
            "SHA-256 over the same canonical records with the index-derived "
            "pmc_article_count field removed. A rebuild from the pinned files "
            "alone reproduces this digest; the full-file sha256 above "
            "reproduces only against the same retrieval index."
        ),
        "bytes": canonical_path.stat().st_size,
    }


def parse_args() -> argparse.Namespace:
    """CLI args."""
    tc_dir = os.environ.get("TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases"))
    p = argparse.ArgumentParser(description="Finalize Phase 1B canonical test cases.")
    p.add_argument("--input", type=Path, default=Path(tc_dir) / "06_with_candidates.jsonl")
    p.add_argument("--output", type=Path, default=Path(tc_dir) / "test_cases.jsonl")
    p.add_argument("--manifest", type=Path, default=Path(tc_dir) / "test_cases_manifest.json")
    return p.parse_args()


def main() -> int:
    """Read B7 output, project to canonical schema, write JSONL + manifest."""
    args = parse_args()
    if not args.input.exists():
        logger.error(f"Input not found: {args.input}")
        logger.error("Run 18_build_candidate_lists.py (B7) first.")
        return 1

    raw_records = [json.loads(line) for line in args.input.open("r", encoding="utf-8")]
    canonical_records = [project_to_canonical(r) for r in raw_records]

    sha = write_canonical_jsonl(canonical_records, args.output)
    manifest = build_manifest(canonical_records, args.output, sha)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    logger.info("=== Phase 1B finalize summary ===")
    logger.info(f"  cases written:               {manifest['n_cases']:,}")
    logger.info(f"  category distribution:       {manifest['category_distribution']}")
    logger.info(
        f"  PMC coverage validated:      {manifest['pmc_coverage_validated']} "
        f"({manifest['n_cases_with_pmc_coverage']}/{manifest['n_cases']})"
    )
    logger.info(f"  output:                      {args.output}")
    logger.info(f"  output sha256:               {sha[:16]}…")
    logger.info(f"  core sha256 (index-free):    {manifest['sha256_core'][:16]}…")
    logger.info(f"  output bytes:                {manifest['bytes']:,}")
    logger.info(f"  manifest:                    {args.manifest}")

    if not manifest["pmc_coverage_validated"]:
        logger.warning(
            "PMC coverage NOT validated — re-run after B6 (17_validate_pmc_coverage.py) "
            "completes against the Phase 1A production index."
        )

    return 0 if manifest["n_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
