"""Fetch a small curated PMC OA sample via NCBI E-utilities (demo path).

Master plan §3.1 / §7 step 5a specifies bulk download of ~150 GB from the
public PMC OA S3 bucket via ``aws s3 sync``. That path is correct for the
final 5-9 day Phase 1A build, but it is not appropriate for the 4-day TFM
demo because (a) it requires an `aws` CLI install, (b) it fetches an
arbitrary article slice with no rare-disease enrichment, and (c) the
demo only needs ~100 articles total.

This script uses NCBI E-utilities (``esearch`` + ``efetch``, plain HTTPS)
to discover and download a stratified sample of rare-disease open-access
articles directly. It writes JATS XML files to
``$PMC_WORKSPACE/xml_raw/demo/`` matching the directory layout that
``06_parse_jats_xml.py`` expects.

Run from the project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/corpus/01_demo_fetch_pmc.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Final

import requests
from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("demo_fetch_pmc")

EUTILS_BASE: Final[str] = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_RATE_LIMIT_S: Final[float] = 0.34  # ~3 req/s without an API key
HTTP_TIMEOUT_S: Final[int] = 30
MAX_RETRIES: Final[int] = 3

# Stratified rare-disease query set — one per planned MONDO category for the
# Phase 1B test cases (master plan §6 step 3). Top-N PMC IDs per category are
# fetched, deduplicated, and downloaded. Queries restrict to open access and
# English language articles.
DEMO_QUERIES: Final[OrderedDict[str, str]] = OrderedDict(
    {
        "neurological": (
            '("Huntington Disease"[MeSH Terms] OR '
            '"Charcot-Marie-Tooth Disease"[MeSH Terms] OR '
            '"Rett Syndrome"[MeSH Terms]) AND open_access[filter] AND english[la]'
        ),
        "metabolic": (
            '("Phenylketonurias"[MeSH Terms] OR '
            '"Fabry Disease"[MeSH Terms] OR '
            '"Niemann-Pick Diseases"[MeSH Terms]) AND open_access[filter] AND english[la]'
        ),
        "immunological": (
            '("Agammaglobulinemia"[MeSH Terms] OR '
            '"Common Variable Immunodeficiency"[MeSH Terms] OR '
            '"Severe Combined Immunodeficiency"[MeSH Terms]) AND open_access[filter] AND english[la]'
        ),
        "developmental": (
            '("Marfan Syndrome"[MeSH Terms] OR '
            '"Noonan Syndrome"[MeSH Terms] OR '
            '"DiGeorge Syndrome"[MeSH Terms]) AND open_access[filter] AND english[la]'
        ),
    }
)
PER_CATEGORY: Final[int] = 25  # 4 categories x 25 = 100 article target


def demo_dir() -> Path:
    """Return the absolute output directory under ``$PMC_WORKSPACE``."""
    workspace = os.environ.get("PMC_WORKSPACE", "/mnt/c/pmc_workspace")
    out = Path(workspace) / "xml_raw" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _http_get(url: str, params: dict[str, str]) -> requests.Response:
    """Issue a GET with retries and a polite user agent.

    Raises:
        requests.HTTPError: After exhausting retries.
    """
    headers = {"User-Agent": "geno_agent-tfm/0.1"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT_S)
            r.raise_for_status()
            return r
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2**attempt
            logger.warning(f"  retry {attempt}/{MAX_RETRIES} in {wait}s ({exc})")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def esearch_pmc(query: str, retmax: int) -> list[str]:
    """Run an esearch query against PMC, return PMC IDs (numeric, no prefix)."""
    r = _http_get(
        f"{EUTILS_BASE}/esearch.fcgi",
        {"db": "pmc", "term": query, "retmax": str(retmax), "retmode": "json", "sort": "relevance"},
    )
    return r.json()["esearchresult"].get("idlist", [])


def efetch_jats(pmc_id: str) -> bytes:
    """Download JATS XML for one PMC ID; returns raw bytes."""
    r = _http_get(
        f"{EUTILS_BASE}/efetch.fcgi",
        {"db": "pmc", "id": pmc_id, "rettype": "xml", "retmode": "xml"},
    )
    return r.content


def fetch_demo_corpus() -> dict[str, int]:
    """Fetch the stratified demo corpus, return per-category download counts."""
    out = demo_dir()
    seen: set[str] = set()
    counts: dict[str, int] = {}

    for category, query in DEMO_QUERIES.items():
        logger.info(f"=== {category} ({PER_CATEGORY} target) ===")
        ids = esearch_pmc(query, PER_CATEGORY)
        new_ids = [i for i in ids if i not in seen]
        seen.update(new_ids)
        logger.info(f"  esearch returned {len(ids)}; {len(new_ids)} new after dedup")

        downloaded = 0
        for pmc_id in new_ids:
            target = out / f"PMC{pmc_id}.xml"
            if target.exists():
                downloaded += 1
                continue
            try:
                xml = efetch_jats(pmc_id)
            except requests.HTTPError as exc:
                logger.warning(f"  PMC{pmc_id}: HTTP {exc.response.status_code}; skipping")
                continue
            target.write_bytes(xml)
            downloaded += 1
            time.sleep(NCBI_RATE_LIMIT_S)
        counts[category] = downloaded
        logger.info(f"  {category}: downloaded {downloaded}")
    return counts


def main() -> int:
    """Entry point — fetch the corpus, log a summary."""
    counts = fetch_demo_corpus()
    out = demo_dir()
    files = sorted(out.glob("PMC*.xml"))
    total_bytes = sum(f.stat().st_size for f in files)
    logger.info("=== Demo corpus summary ===")
    logger.info(f"  output dir:   {out}")
    logger.info(f"  per-category: {counts}")
    logger.info(f"  total files:  {len(files)}")
    logger.info(f"  total size:   {total_bytes / 1024 / 1024:.1f} MB")
    return 0 if files else 1


if __name__ == "__main__":
    raise SystemExit(main())
