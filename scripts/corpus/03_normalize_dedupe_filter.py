"""Normalize, dedupe, and genetics-filter the FTP-bulk parser output.

Master plan §4 step 2 + the schema bridge between
``02_extract_and_parse_ftp.py`` (FTP-bulk parser) and
``08_section_aware_chunking.py`` (chunker).

Three things in one pass:

1. **Dedupe by PMC ID.** Baselines plus daily incrementals both contain
   the same article whenever it was updated. We iterate JSONLs in
   reverse chronological order (newest tarball first) and emit each
   PMC ID only once — so the latest version wins. Memory cost is
   one ``set`` of ~3 M PMC IDs (~50 MB).

2. **Genetics relevance filter.** Same vocabulary + regex as the
   original ``07_filter_corpus.py`` (master plan §4 step 2). Drops
   articles unrelated to genetics / genomics / rare disease, since
   downstream queries never touch them.

3. **Schema normalization** for the chunker. Converts::

       {pmc_id, pub_dates, categories, abstract, sections: [{title, paragraphs}]}

   to::

       {pmcid, pub_year, mesh_terms, sections: [{section_type, heading, text}]}

   The abstract becomes the first section with ``section_type="abstract"``;
   subsequent sections inherit a ``section_type`` derived from the heading
   (``introduction`` / ``methods`` / ``results`` / ``discussion`` / ``other``).
   All metadata fields the chunker doesn't use (DOI, authors, journal,
   license, copyright, funding) are kept for downstream Qdrant payload.

Inputs::

    /mnt/c/pmc_workspace/parsed/{oa_comm,oa_noncomm,oa_other}/*.jsonl.gz

Output::

    /mnt/c/pmc_workspace/parsed/all_articles.normalized.jsonl.gz
    /mnt/c/pmc_workspace/parsed/_normalize_stats.json

Usage::

    python scripts/corpus/03_normalize_dedupe_filter.py [--no-filter]

The ``--no-filter`` flag skips the genetics filter (writes all deduped
articles), useful for sanity checks. Default is to filter.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------- defaults
PARSED_DIR: Final[Path] = Path("/mnt/c/pmc_workspace/parsed")
ARCHIVES_DIR: Final[Path] = Path("/mnt/c/pmc_workspace/xml_raw/_archives")
OUT_PATH: Final[Path] = PARSED_DIR / "all_articles.normalized.jsonl.gz"
STATS_PATH: Final[Path] = PARSED_DIR / "_normalize_stats.json"
TIERS: Final[tuple[str, ...]] = ("oa_comm", "oa_noncomm", "oa_other")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("normalize")


# ---------------------------------------------------------------- genetics filter
GENETICS_VOCAB: Final[frozenset[str]] = frozenset(
    s.lower()
    for s in (
        "genetics",
        "genetic",
        "genomics",
        "genomic",
        "genome",
        "mutation",
        "mutations",
        "variant",
        "variants",
        "rare disease",
        "rare diseases",
        "orphan disease",
        "mendelian",
        "monogenic",
        "hereditary",
        "phenotype",
        "genotype",
        "exome",
        "next-generation sequencing",
        "whole genome",
        "whole-genome",
        "whole exome",
        "whole-exome",
        "cystic fibrosis",
        "huntington",
        "marfan",
        "noonan",
        "digeorge",
        "rett syndrome",
        "phenylketonuria",
        "duchenne",
        "fragile x",
        "mitochondrial",
        "chromosome",
        "chromosomal",
        "aneuploidy",
        "deletion",
        "duplication",
        "copy number",
        "cnv",
        "snp",
        "single nucleotide polymorphism",
        "gwas",
        "genome-wide association",
        "polymorphism",
        "allele",
        "alleles",
        "heterozygous",
        "homozygous",
        "compound heterozygous",
        "autosomal",
        "x-linked",
        "y-linked",
        "dominant inheritance",
        "recessive inheritance",
        "de novo",
        "germline",
        "somatic",
        "founder mutation",
        "splice",
        "missense",
        "nonsense",
        "frameshift",
        "indel",
        "trinucleotide repeat",
        "expansion",
        "imprinting",
        "epigenetic",
        "epigenome",
        "epigenomic",
        "rna-seq",
        "rnaseq",
        "transcriptome",
        "transcriptomic",
        "methylation",
        "histone",
        "chromatin",
    )
)

GENETICS_REGEX: Final[re.Pattern] = re.compile(
    r"\b(?:gene|genes|allele|locus|loci|exon|intron|codon|protein|amino\s+acid|"
    r"sequencing|sanger|illumina|nanopore|crispr|cas9|tale[ns]?|zfn|"
    r"omim:?\s*\d+|hgnc:?\s*\d+|orphanet:?\s*\d+|mondo:?\s*\d+|hpo:?\s*\d+|"
    r"chr\s*\d+[pq]?\d*|"
    r"\d+\s*kb|\d+\s*mb|\d+\s*bp"
    r")\b",
    re.IGNORECASE,
)


def is_genetics_article(record: dict) -> bool:
    """True if title/abstract/categories suggest genetics relevance."""
    haystack_parts = [
        record.get("title", "") or "",
        record.get("abstract", "") or "",
        " ".join(record.get("categories") or []),
    ]
    haystack = " ".join(haystack_parts).lower()
    if not haystack.strip():
        return False

    for term in GENETICS_VOCAB:
        if term in haystack:
            return True
    return bool(GENETICS_REGEX.search(haystack))


# ---------------------------------------------------------------- schema normalization
SECTION_TYPE_PATTERNS: Final[tuple[tuple[re.Pattern, str], ...]] = (
    (re.compile(r"\babstract\b", re.I), "abstract"),
    (re.compile(r"\b(introduction|background)\b", re.I), "introduction"),
    (re.compile(r"\b(materials?\s+and\s+methods?|methods?|procedures?)\b", re.I), "methods"),
    (re.compile(r"\bresults?\b", re.I), "results"),
    (re.compile(r"\b(discussion|conclusions?)\b", re.I), "discussion"),
    (re.compile(r"\b(case\s+report|case\s+presentation)\b", re.I), "case_report"),
    (re.compile(r"\b(references?|bibliography)\b", re.I), "references"),
    (re.compile(r"\backnowledg(e?ments?|e?ements?)\b", re.I), "acknowledgements"),
)


def classify_section_type(heading: str) -> str:
    """Map a section heading to a standardized section_type."""
    h = heading or ""
    for pattern, label in SECTION_TYPE_PATTERNS:
        if pattern.search(h):
            return label
    return "other"


def parse_pub_year(record: dict) -> int | None:
    """Extract publication year from any pub_dates entry."""
    for key in ("epub", "ppub", "collection", "pub", "epreprint"):
        date_str = (record.get("pub_dates") or {}).get(key, "")
        if date_str:
            year_part = date_str.split("-", 1)[0]
            if year_part.isdigit():
                return int(year_part)
    return None


def normalize_record(record: dict) -> dict | None:
    """Convert parser-output schema to chunker-expected schema.

    Returns None if the record is unusable (no PMC ID).
    """
    pmcid = record.get("pmc_id")
    if not pmcid:
        return None

    sections_out: list[dict] = []

    # Abstract -> first section
    abstract = (record.get("abstract") or "").strip()
    if abstract:
        sections_out.append({"section_type": "abstract", "heading": "Abstract", "text": abstract})

    # Body sections: flatten paragraphs into one text per section
    for sec in record.get("sections") or []:
        heading = (sec.get("title") or "").strip()
        paragraphs = sec.get("paragraphs") or []
        text = "\n\n".join(p for p in paragraphs if p)
        if not text:
            continue
        sections_out.append(
            {
                "section_type": classify_section_type(heading),
                "heading": heading or None,
                "text": text,
            }
        )

    # Body fallback (no <sec> children — rare)
    body_text = (record.get("body_text") or "").strip()
    if not sections_out and body_text:
        sections_out.append({"section_type": "other", "heading": None, "text": body_text})

    return {
        "pmcid": pmcid,
        "pmid": record.get("pmid"),
        "doi": record.get("doi"),
        "article_type": record.get("article_type"),
        "title": (record.get("title") or "").strip(),
        "pub_year": parse_pub_year(record),
        "mesh_terms": record.get("categories") or [],
        "authors": record.get("authors") or [],
        "affiliations": record.get("affiliations") or {},
        "journal": record.get("journal") or {},
        "license": record.get("license") or {},
        "copyright": record.get("copyright") or {},
        "funding": record.get("funding") or [],
        "n_references": record.get("n_references") or 0,
        "tier": record.get("_tier"),
        "source_tarball": record.get("_tarball"),
        "sections": sections_out,
    }


# ---------------------------------------------------------------- iteration order
TARBALL_DATE_RE: Final[re.Pattern] = re.compile(r"\.(\d{4}-\d{2}-\d{2})\.tar\.gz$")


def jsonl_sort_key(path: Path) -> tuple:
    """Sort key for JSONLs in REVERSE chronological order.

    Newer date first; baselines are dated 2026-01-23 (the earliest), so they
    end up LAST in this order. That guarantees newer incrementals win on
    PMC-ID collision (they're seen first in the dedupe sweep).
    """
    name = path.name  # e.g. oa_comm_xml.incr.2026-04-15.jsonl.gz
    m = TARBALL_DATE_RE.search(name.replace(".jsonl.gz", ".tar.gz"))
    date_str = m.group(1) if m else "0000-00-00"
    is_baseline = ".baseline." in name
    # Sort: newer date first (descending), baselines last
    return (date_str, not is_baseline)


# ---------------------------------------------------------------- main
def main() -> int:
    """Iterate parser JSONLs newest-first, dedupe by PMC ID, filter, write output."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_DIR)
    parser.add_argument("--out-path", type=Path, default=OUT_PATH)
    parser.add_argument("--stats-path", type=Path, default=STATS_PATH)
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Skip the genetics relevance filter (write all deduped articles).",
    )
    parser.add_argument(
        "--status-interval",
        type=int,
        default=60,
        help="Print one progress line every N seconds (default 60).",
    )
    args = parser.parse_args()

    # Discover all parser JSONLs across tiers
    jsonl_paths: list[Path] = []
    for tier in TIERS:
        tier_dir = args.parsed_dir / tier
        if tier_dir.is_dir():
            jsonl_paths.extend(sorted(tier_dir.glob("*.jsonl.gz")))
    if not jsonl_paths:
        log.error("No parser JSONLs under %s — nothing to do", args.parsed_dir)
        return 1

    # Sort REVERSE chronological — newest tarball processed first
    jsonl_paths.sort(key=jsonl_sort_key, reverse=True)

    log.info(
        "Found %d parser JSONLs across %s tiers",
        len(jsonl_paths),
        ",".join(TIERS),
    )
    log.info("Output: %s", args.out_path)
    log.info("Apply genetics filter: %s", not args.no_filter)

    seen: set[str] = set()
    total_in = 0
    deduped = 0
    filtered_out_genetics = 0
    no_pmcid = 0
    written = 0

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    args.out_path.with_suffix(args.out_path.suffix + ".partial").unlink(missing_ok=True)
    partial_path = args.out_path.with_suffix(args.out_path.suffix + ".partial")

    start = time.time()
    last_print = start

    broken_files: list[str] = []
    try:
        with gzip.open(partial_path, mode="wt", encoding="utf-8") as out_f:
            for idx, path in enumerate(jsonl_paths, 1):
                # Per-file try so a corrupted gzip from a previous killed run
                # doesn't tank the whole pass — just skip and log.
                try:
                    with gzip.open(path, mode="rt", encoding="utf-8") as in_f:
                        for line in in_f:
                            total_in += 1
                            try:
                                rec = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            pmcid = rec.get("pmc_id")
                            if not pmcid:
                                no_pmcid += 1
                                continue

                            # Dedupe — newest tarball seen first
                            if pmcid in seen:
                                deduped += 1
                                continue
                            seen.add(pmcid)

                            # Genetics relevance
                            if not args.no_filter and not is_genetics_article(rec):
                                filtered_out_genetics += 1
                                continue

                            # Normalize for chunker
                            normalized = normalize_record(rec)
                            if normalized is None:
                                continue

                            out_f.write(
                                json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
                            )
                            out_f.write("\n")
                            written += 1
                except (EOFError, gzip.BadGzipFile, OSError) as e:
                    log.error("Broken JSONL skipped: %s (%s)", path.name, e)
                    broken_files.append(str(path))

                # Per-file progress
                now = time.time()
                if now - last_print >= args.status_interval:
                    elapsed = now - start
                    log.info(
                        "[%d/%d] %s — in=%d unique=%d dropped_genetics=%d "
                        "written=%d elapsed=%.1fmin",
                        idx,
                        len(jsonl_paths),
                        path.name,
                        total_in,
                        len(seen),
                        filtered_out_genetics,
                        written,
                        elapsed / 60,
                    )
                    last_print = now

        # Atomic publish
        partial_path.replace(args.out_path)
    except Exception:
        with contextlib.suppress(OSError):
            partial_path.unlink()
        raise

    elapsed = time.time() - start
    summary = {
        "elapsed_min": elapsed / 60,
        "input_jsonls": len(jsonl_paths),
        "input_records": total_in,
        "no_pmcid": no_pmcid,
        "unique_pmcids": len(seen),
        "duplicates_dropped": deduped,
        "filtered_out_genetics": filtered_out_genetics,
        "written": written,
        "filter_applied": not args.no_filter,
        "broken_files_skipped": broken_files,
        "output_path": str(args.out_path),
        "output_size_bytes": args.out_path.stat().st_size,
    }
    args.stats_path.write_text(json.dumps(summary, indent=2))

    print()
    print(f"=== DONE in {elapsed / 60:.1f} min ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
