"""Post-download sanity checks for HPO, MONDO, GO, and HGNC.

Implements master plan §5 — runs after §3.2 and §3.3 acquisition to confirm that
every downloaded ontology file parses with `pronto`/`pandas`, that the embedded
``data-version`` matches the pin in ``.env``, and that a handful of well-known
ontology IDs and gene symbols round-trip correctly. This is intentionally NOT a
full integrity test; it is a tripwire that fails fast if a file is truncated,
mis-pinned, or in an unexpected format before any downstream step depends on it.

Run from the project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/ontology/12_verify_ontologies.py

Exits 0 on success, 1 on any verification failure. Logs to stdout.
"""

from __future__ import annotations

import gzip
import logging
import os
import sys
from pathlib import Path
from typing import Final

import pandas as pd
import pronto
from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_ontologies")


def _ontology_dir() -> Path:
    """Return the resolved ontology directory.

    Honors ``$ONTOLOGY_DIR`` if set, otherwise defaults to
    ``$PROJECT_ROOT/data/ontologies`` (the master-plan-style path-alias
    symlinks created in §7 step [3]).
    """
    raw = os.environ.get("ONTOLOGY_DIR") or str(PROJECT_ROOT / "data" / "ontologies")
    return Path(raw).resolve()


def _hgnc_dir() -> Path:
    """Return the resolved HGNC directory (env override or default alias)."""
    raw = os.environ.get("HGNC_DIR") or str(PROJECT_ROOT / "data" / "hgnc")
    return Path(raw).resolve()


def verify_hpo() -> int:
    """Verify HPO ontology and gene-phenotype association files.

    Loads ``hp.obo`` with `pronto`, asserts the embedded ``data-version``
    matches ``$HPO_VERSION``, looks up a known term (``HP:0001250``, Seizure)
    and walks one parent hop, and counts rows in
    ``genes_to_phenotype.txt`` and ``phenotype_to_genes.txt``.

    Returns:
        Number of HP-prefixed terms loaded. Raises on any failure.
    """
    logger.info("=== HPO ===")
    d = _ontology_dir() / "hpo"
    hpo = pronto.Ontology(str(d / "hp.obo"))
    expected = os.environ.get("HPO_VERSION", "v2026-02-16").lstrip("v")
    actual = (hpo.metadata.data_version or "").rsplit("/", 1)[-1]
    assert actual == expected, f"HPO data-version mismatch: {actual} vs {expected}"

    terms = [t for t in hpo.terms() if t.id.startswith("HP:")]
    seizure = hpo["HP:0001250"]
    parents = list(seizure.superclasses(distance=1, with_self=False))[:3]
    g2p = pd.read_csv(d / "genes_to_phenotype.txt", sep="\t", comment="#")
    p2g = pd.read_csv(d / "phenotype_to_genes.txt", sep="\t", comment="#")

    logger.info(f"  data_version: {actual} (matches pin)")
    logger.info(f"  HP terms: {len(terms):,}")
    logger.info(f"  HP:0001250 -> {seizure.name}")
    logger.info(f"  parents: {[f'{p.id} ({p.name})' for p in parents]}")
    logger.info(f"  genes_to_phenotype: {len(g2p):,} rows")
    logger.info(f"  phenotype_to_genes: {len(p2g):,} rows")
    return len(terms)


def verify_mondo() -> int:
    """Verify MONDO disease ontology.

    Asserts pin match against ``$MONDO_VERSION`` and resolves four
    disease-category root IDs that Phase 1B (§6 step 3) will use for
    case categorization.

    Returns:
        Number of MONDO-prefixed terms loaded.
    """
    logger.info("=== MONDO ===")
    f = _ontology_dir() / "mondo" / "mondo.obo"
    mondo = pronto.Ontology(str(f))
    expected = os.environ.get("MONDO_VERSION", "v2026-03-03").lstrip("v")
    actual = (mondo.metadata.data_version or "").rsplit("/", 1)[-1]
    assert actual == expected, f"MONDO data-version mismatch: {actual} vs {expected}"

    terms = [t for t in mondo.terms() if t.id.startswith("MONDO:")]
    logger.info(f"  data_version: {actual} (matches pin)")
    logger.info(f"  MONDO terms: {len(terms):,}")
    for tid in ("MONDO:0007947", "MONDO:0005071", "MONDO:0005066", "MONDO:0005046"):
        t = mondo.get(tid)
        if t is not None:
            logger.info(f"  {t.id} -> {t.name}")
        else:
            logger.warning(f"  {tid} not found in MONDO {actual}")
    return len(terms)


def verify_go() -> int:
    """Verify Gene Ontology and the gzipped human GAF annotation file.

    Pandas reads ``goa_human.gaf.gz`` directly via inferred gzip
    decompression — the master plan reference assumed the file would be
    gunzipped, but we keep it compressed to save ~50 MB.

    Returns:
        Number of GO terms loaded.
    """
    logger.info("=== GO ===")
    d = _ontology_dir() / "go"
    go = pronto.Ontology(str(d / "go.obo"))
    expected = os.environ.get("GO_VERSION", "2026-03-25")
    actual = (go.metadata.data_version or "").rsplit("/", 1)[-1]
    assert actual == expected, f"GO data-version mismatch: {actual} vs {expected}"

    n_terms = sum(1 for _ in go.terms())
    gaf_path = d / "goa_human.gaf.gz"
    cols = [
        "DB",
        "DB_Object_ID",
        "DB_Object_Symbol",
        "Qualifier",
        "GO_ID",
        "DB_Reference",
        "Evidence_Code",
        "With_From",
        "Aspect",
        "DB_Object_Name",
        "DB_Object_Synonym",
        "DB_Object_Type",
        "Taxon",
        "Date",
        "Assigned_By",
        "Annotation_Extension",
        "Gene_Product_Form_ID",
    ]
    gaf = pd.read_csv(
        gaf_path,
        sep="\t",
        comment="!",
        header=None,
        names=cols,
        low_memory=False,
    )
    logger.info(f"  data_version: {actual} (matches pin)")
    logger.info(f"  GO terms: {n_terms:,}")
    logger.info(
        f"  human GAF: {len(gaf):,} annotations across "
        f"{gaf['DB_Object_Symbol'].nunique():,} gene symbols"
    )
    with gzip.open(gaf_path, "rt") as fh:
        first_meta = next((line for line in fh if line.startswith("!")), "")
    logger.info(f"  GAF header: {first_meta.strip()}")
    return n_terms


def verify_hgnc() -> int:
    """Verify HGNC complete gene set.

    Loads the pinned snapshot, separates protein-coding genes (the eligible
    pool for distractor sampling in §6 step 6), and prints a small sample.

    Returns:
        Number of protein-coding gene rows.
    """
    logger.info("=== HGNC ===")
    f = _hgnc_dir() / "hgnc_complete_set.txt"
    hgnc = pd.read_csv(f, sep="\t", low_memory=False)
    pc = hgnc[hgnc["locus_group"] == "protein-coding gene"]
    sample = list(pc["symbol"].head(10))
    logger.info(f"  total entries: {len(hgnc):,}")
    logger.info(f"  protein-coding genes: {len(pc):,}")
    logger.info(f"  sample symbols: {sample}")
    for must_have in ("BRCA1", "TP53", "TTN"):
        assert must_have in pc["symbol"].values, f"{must_have} missing from HGNC"
    logger.info("  spot-check OK: BRCA1, TP53, TTN all present in protein-coding set")
    return len(pc)


def main() -> int:
    """Run every verification in order; return 0 on full success, 1 otherwise."""
    try:
        verify_hpo()
        verify_mondo()
        verify_go()
        verify_hgnc()
    except (AssertionError, FileNotFoundError, KeyError) as exc:
        logger.error(f"Verification failed: {type(exc).__name__}: {exc}")
        return 1
    logger.info("=== All ontology verifications passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
