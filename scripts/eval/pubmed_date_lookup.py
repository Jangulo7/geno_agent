"""Look up publication dates for the cohort's source PMIDs (Thread E).

For each unique PMID in ``data/test_cases_1050/annotation_overlap.json``,
fetch the PubMed record via NCBI E-utils efetch and extract the
publication date. We use ``<PubMedPubDate PubStatus="pubmed">`` (the
date the record became available on PubMed) as the canonical "earliest
public availability" date — this is what determines whether a paper
could possibly have been considered for inclusion in phenotype.hpoa
v2026-02-16.

Output: ``data/test_cases_1050/pmid_dates.json`` mapping each PMID
to its publication date in ISO ``YYYY-MM-DD`` form, plus the cohort
breakdown by year and the count of PMIDs published after the hpoa
pin date (= candidate Thread E novel-cases subset).

Network budget: 415 unique PMIDs, batched ≤ 100 per request, ≤ 3
requests/sec without API key. Total wall: < 15 s with one retry.

Run::

    PYTHONPATH=. python scripts/eval/pubmed_date_lookup.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Final
from xml.etree import ElementTree as ET

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pmid_dates")

DEFAULT_OVERLAP: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "annotation_overlap.json"
DEFAULT_OUT: Final[Path] = PROJECT_ROOT / "data" / "test_cases_1050" / "pmid_dates.json"
EFETCH_URL: Final[str] = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
HPOA_PIN_DATE: Final[str] = "2026-02-16"  # Project's pinned phenotype.hpoa release
BATCH_SIZE: Final[int] = 100
SLEEP_BETWEEN: Final[float] = 0.34  # ≤ 3 req/s without API key


def fetch_pmid_batch(pmids: list[str], retries: int = 3) -> bytes:
    """Fetch a batch of PMIDs from E-utils efetch as XML bytes."""
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    url = f"{EFETCH_URL}?{urllib.parse.urlencode(params)}"
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            log.warning(
                "attempt %d/%d failed for batch[0..%d]: %s", attempt, retries, len(pmids), e
            )
            time.sleep(2**attempt)
    raise RuntimeError(f"efetch failed after {retries} attempts: {last_err}")


def extract_pubmed_date(article: ET.Element) -> str | None:
    """Return ISO YYYY-MM-DD from ``<PubMedPubDate PubStatus='pubmed'>`` or None.

    Falls back to JournalIssue/PubDate if the pubmed PubMedPubDate is missing
    (rare; some legacy records).
    """
    # Preferred: PubMedPubDate PubStatus="pubmed"
    for el in article.iter("PubMedPubDate"):
        if el.get("PubStatus") == "pubmed":
            y = el.findtext("Year")
            m = el.findtext("Month")
            d = el.findtext("Day")
            if y and m and d:
                return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    # Fallback: JournalIssue/PubDate (Year[/Month/Day])
    issue_date = article.find(".//JournalIssue/PubDate")
    if issue_date is not None:
        y = issue_date.findtext("Year")
        m = issue_date.findtext("Month")
        # Month can be alphabetic ("Jan") or numeric
        month_map = {
            "Jan": 1,
            "Feb": 2,
            "Mar": 3,
            "Apr": 4,
            "May": 5,
            "Jun": 6,
            "Jul": 7,
            "Aug": 8,
            "Sep": 9,
            "Oct": 10,
            "Nov": 11,
            "Dec": 12,
        }
        if y:
            mn = 1
            if m:
                try:
                    mn = int(m)
                except ValueError:
                    mn = month_map.get(m[:3], 1)
            return f"{int(y):04d}-{mn:02d}-01"
    return None


def parse_efetch_response(xml_bytes: bytes) -> dict[str, str | None]:
    """Parse efetch XML returning ``{pmid: date_str_or_None}``."""
    root = ET.fromstring(xml_bytes)
    out: dict[str, str | None] = {}
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//MedlineCitation/PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        pmid = pmid_el.text.strip()
        out[pmid] = extract_pubmed_date(article)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--pin-date", default=HPOA_PIN_DATE)
    args = parser.parse_args()

    # Load PMIDs from overlap records (already canonicalised by Thread D)
    records = json.loads(args.overlap.read_text())["records"]
    pmids = sorted({r["source_pmid"].replace("PMID:", "") for r in records if r.get("source_pmid")})
    log.info("Unique PMIDs to fetch: %d (across %d cases)", len(pmids), len(records))

    # Resume from existing cache if present (allows incremental top-up)
    cache: dict[str, str | None] = {}
    if args.out.exists():
        cache = json.loads(args.out.read_text()).get("dates", {})
        log.info("Loaded existing cache: %d PMIDs", len(cache))
    todo = [p for p in pmids if p not in cache]
    log.info("PMIDs to fetch from NCBI: %d", len(todo))

    # Fetch in batches
    for i in range(0, len(todo), BATCH_SIZE):
        chunk = todo[i : i + BATCH_SIZE]
        log.info("Fetching batch %d-%d / %d", i, i + len(chunk), len(todo))
        xml_bytes = fetch_pmid_batch(chunk)
        parsed = parse_efetch_response(xml_bytes)
        for p in chunk:
            cache[p] = parsed.get(p)
        time.sleep(SLEEP_BETWEEN)

    # Audit + summarise
    n_no_date = sum(1 for v in cache.values() if v is None)
    log.info("PMIDs with no date: %d / %d", n_no_date, len(cache))

    year_counter: Counter[int] = Counter()
    after_pin: list[str] = []
    for p, d in cache.items():
        if d is None:
            continue
        year_counter[int(d.split("-")[0])] += 1
        if d > args.pin_date:
            after_pin.append(p)

    # Map back to cases: any case whose PMID is in after_pin is a Thread E candidate
    pmid_to_cases: dict[str, list[str]] = {}
    for r in records:
        if not r.get("source_pmid"):
            continue
        p = r["source_pmid"].replace("PMID:", "")
        pmid_to_cases.setdefault(p, []).append(r["case_id"])
    novel_case_ids = sorted({cid for p in after_pin for cid in pmid_to_cases.get(p, [])})

    print("\n=== PMID date summary ===")
    print(f"  Unique PMIDs:                   {len(pmids):>5d}")
    print(f"  PMIDs with date resolved:       {len(cache) - n_no_date:>5d}")
    print(f"  PMIDs with no date:             {n_no_date:>5d}")
    print(f"  PMIDs published after {args.pin_date}: {len(after_pin):>5d}")
    print("\n  Case-level novel-subset candidates (Thread E):")
    print(f"    cases whose PMID date > pin:  {len(novel_case_ids):>5d} of {len(records)}")
    print(f"    ({100 * len(novel_case_ids) / len(records):.1f} % of cohort)")

    print("\n=== Pub-year distribution (top 10 years) ===")
    for yr, n in year_counter.most_common(10):
        bar = "#" * (n // 5)
        print(f"  {yr}: {n:>4d}  {bar}")

    # Write cache + derived novel subset
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "meta": {
                    "pin_date": args.pin_date,
                    "n_pmids": len(pmids),
                    "n_pmids_no_date": n_no_date,
                    "n_pmids_after_pin": len(after_pin),
                    "n_cases_novel": len(novel_case_ids),
                    "n_cases_total": len(records),
                },
                "dates": cache,
                "novel_case_ids": novel_case_ids,
            },
            indent=2,
        )
    )
    log.info("Wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
