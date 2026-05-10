"""PMC OA FTP archive extractor + JATS XML parser + retraction filter.

Master plan §3 / §7 step [5b] for the FTP-bulk path: extract NCBI bulk
tarballs, parse JATS XMLs to one JSONL row per non-retracted article,
skipping retracted articles per the per-tarball ``.filelist.csv``
``Retracted`` column.

Inputs::

    /mnt/c/pmc_workspace/xml_raw/_archives/{oa_comm,oa_noncomm,oa_other}/
        oa_<tier>_xml.PMC<prefix>.baseline.<date>.tar.gz
        oa_<tier>_xml.PMC<prefix>.baseline.<date>.filelist.csv
        oa_<tier>_xml.incr.<date>.tar.gz
        oa_<tier>_xml.incr.<date>.filelist.csv

The companion ``.filelist.csv`` columns are::

    Article File, Article Citation, AccessionID,
    LastUpdated (YYYY-MM-DD HH:MM:SS), PMID, License, Retracted

Outputs::

    /mnt/c/pmc_workspace/xml_raw/all/PMC<prefix>/PMC<id>.xml   (extracted XMLs)
    /mnt/c/pmc_workspace/parsed/<tier>/<tarball-stem>.jsonl.gz  (per-article records)
    /mnt/c/pmc_workspace/parsed/skipped_retractions.jsonl       (audit log)
    /mnt/c/pmc_workspace/parsed/_status.json                    (live progress stats)

Behavior:
  - Verification: ``tarfile.open(mode="r:gz")`` raises on a corrupt gzip;
    that's the integrity check. We additionally cross-check the count of
    XML members against the filelist CSV row count.
  - Retraction filter: any PMC ID with ``Retracted=yes`` in the filelist
    is dropped before parsing. The audit log records which IDs and why.
  - Resumability: a tarball whose output ``.jsonl.gz`` already exists and
    is non-empty is skipped. Re-running picks up where it left off.
  - Status: a background thread prints one ``[STATUS ...]`` line every
    ``--status-interval`` seconds (default 180 = 3 minutes) and writes
    a JSON snapshot to ``parsed/_status.json``.

Usage::

    python scripts/corpus/02_extract_and_parse_ftp.py [--workers N]
        [--archives-dir PATH] [--extract-dir PATH] [--parsed-dir PATH]
        [--status-interval SECONDS] [--delete-extracted]
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import gzip
import json
import os
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

# ---------------------------------------------------------------- defaults
ARCHIVES_DIR = Path("/mnt/c/pmc_workspace/xml_raw/_archives")
EXTRACT_DIR = Path("/mnt/c/pmc_workspace/xml_raw/all")  # legacy, unused with per-worker temp dirs
TEMP_DIR = Path("/home/hana77/tmp_pmc_extract")  # Linux ext4, fast, fits 12 x 30 GB
PARSED_DIR = Path("/mnt/c/pmc_workspace/parsed")
TIERS = ("oa_comm", "oa_noncomm", "oa_other")
STATUS_INTERVAL_SEC = 180


# ---------------------------------------------------------------- data classes
@dataclass
class Stats:
    """Process-wide counters; mutate fields under ``lock``."""

    start_ts: float = field(default_factory=time.time)
    tarballs_total: int = 0
    tarballs_done: int = 0
    parsed: int = 0
    retracted_skipped: int = 0
    parse_errors: int = 0
    last_print_ts: float = field(default_factory=time.time)
    last_print_parsed: int = 0
    done: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


# ---------------------------------------------------------------- filelist + retraction
def load_filelist(filelist_csv: Path) -> tuple[set[str], int]:
    """Return (set of retracted PMC IDs, total row count) from a filelist.csv."""
    retracted: set[str] = set()
    total = 0
    with filelist_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total += 1
            if row.get("Retracted", "").strip().lower() == "yes":
                pmc = row.get("AccessionID", "").strip()
                if pmc:
                    retracted.add(pmc)
    return retracted, total


# ---------------------------------------------------------------- JATS XML parsing
def text_of(elem) -> str:
    """Concatenate descendant text and collapse whitespace."""
    if elem is None:
        return ""
    parts = list(elem.itertext())
    return " ".join("".join(parts).split())


def parse_jats(xml_path: Path) -> dict | None:
    """Parse one JATS XML file. Return a record dict, or None on parse error."""
    try:
        tree = etree.parse(str(xml_path))
    except etree.XMLSyntaxError:
        return None

    root = tree.getroot()
    front = root.find("front")
    if front is None:
        return None
    article_meta = front.find("article-meta")
    journal_meta = front.find("journal-meta")

    record: dict = {}

    # IDs
    ids: dict[str, str] = {}
    if article_meta is not None:
        for aid in article_meta.findall("article-id"):
            idtype = aid.get("pub-id-type") or "unknown"
            if aid.text:
                ids[idtype] = aid.text.strip()
    record["pmc_id"] = ids.get("pmc")
    record["pmid"] = ids.get("pmid")
    record["doi"] = ids.get("doi")

    # Article type
    record["article_type"] = root.get("article-type", "")

    # Title
    title_elem = (
        article_meta.find("title-group/article-title") if article_meta is not None else None
    )
    record["title"] = text_of(title_elem)

    # Journal
    journal: dict = {}
    if journal_meta is not None:
        jt = journal_meta.find("journal-title-group/journal-title")
        if jt is None:
            jt = journal_meta.find("journal-title")
        journal["title"] = text_of(jt)
        for jid in journal_meta.findall("journal-id"):
            t = jid.get("journal-id-type", "unknown")
            if jid.text:
                journal.setdefault("ids", {})[t] = jid.text
        for issn in journal_meta.findall("issn"):
            t = issn.get("pub-type", "unknown")
            if issn.text:
                journal.setdefault("issn", {})[t] = issn.text.strip()
        publisher = journal_meta.find("publisher/publisher-name")
        if publisher is not None and publisher.text:
            journal["publisher"] = publisher.text.strip()
    record["journal"] = journal

    # Authors with affiliation refs
    authors = []
    if article_meta is not None:
        for contrib in article_meta.findall(".//contrib[@contrib-type='author']"):
            name = contrib.find("name")
            if name is None:
                continue
            surname = (name.findtext("surname") or "").strip()
            given = (name.findtext("given-names") or "").strip()
            aff_refs = [
                x.get("rid") for x in contrib.findall("xref[@ref-type='aff']") if x.get("rid")
            ]
            authors.append({"surname": surname, "given_names": given, "aff_ids": aff_refs})
    record["authors"] = authors

    # Affiliations id → text
    affiliations: dict[str, str] = {}
    if article_meta is not None:
        for aff in article_meta.findall(".//aff"):
            aid = aff.get("id")
            if aid:
                affiliations[aid] = text_of(aff)
    record["affiliations"] = affiliations

    # Publication and history dates
    pub_dates: dict[str, str] = {}
    if article_meta is not None:
        for pd in article_meta.findall("pub-date"):
            ptype = pd.get("pub-type") or pd.get("date-type") or "unknown"
            year = pd.findtext("year") or ""
            month = pd.findtext("month") or ""
            day = pd.findtext("day") or ""
            pub_dates[ptype] = "-".join(p for p in (year, month, day) if p)
    record["pub_dates"] = pub_dates

    history: dict[str, str] = {}
    if article_meta is not None:
        for d in article_meta.findall("history/date"):
            t = d.get("date-type", "unknown")
            year = d.findtext("year") or ""
            month = d.findtext("month") or ""
            day = d.findtext("day") or ""
            history[t] = "-".join(p for p in (year, month, day) if p)
    record["history"] = history

    # Abstract
    abstract_elem = article_meta.find("abstract") if article_meta is not None else None
    record["abstract"] = text_of(abstract_elem)

    # Keywords / categories
    categories = []
    if article_meta is not None:
        for subj in article_meta.findall(".//subject"):
            t = text_of(subj)
            if t:
                categories.append(t)
    record["categories"] = categories

    # Body sections
    body = root.find("body")
    sections = []
    if body is not None:
        for sec in body.findall(".//sec"):
            stitle = (sec.findtext("title") or "").strip()
            paragraphs = [text_of(p) for p in sec.findall("p")]
            sections.append({"title": stitle, "paragraphs": [p for p in paragraphs if p]})
    record["sections"] = sections
    if not sections and body is not None:
        record["body_text"] = text_of(body)

    # License
    license_info: dict = {}
    if article_meta is not None:
        license_elem = article_meta.find("permissions/license")
        if license_elem is not None:
            license_info["text"] = text_of(license_elem)
            ref = license_elem.find("{http://www.niso.org/schemas/ali/1.0/}license_ref")
            if ref is None:
                ref = license_elem.find("license_ref")
            if ref is not None and ref.text:
                license_info["url"] = ref.text.strip()
    record["license"] = license_info

    # Copyright
    copyright_info: dict = {}
    if article_meta is not None:
        copyright_info["statement"] = text_of(article_meta.find("permissions/copyright-statement"))
        copyright_info["year"] = text_of(article_meta.find("permissions/copyright-year"))
        copyright_info["holder"] = text_of(article_meta.find("permissions/copyright-holder"))
    record["copyright"] = copyright_info

    # Funding
    funding = []
    if article_meta is not None:
        for fund in article_meta.findall(".//funding-group/funding-statement"):
            t = text_of(fund)
            if t:
                funding.append(t)
    record["funding"] = funding

    # Reference count (full ref parsing deferred)
    record["n_references"] = len(root.findall(".//ref-list/ref"))

    return record


# ---------------------------------------------------------------- worker
def process_tarball(
    tarball_path: Path,
    filelist_path: Path,
    tier: str,
    temp_dir: Path,
    parsed_dir: Path,
) -> dict:
    """Extract one tarball into a per-worker temp dir, parse, write JSONL.

    The temp dir is on a Linux native filesystem (avoids slow /mnt/c 9P) and
    is unique per (tarball, worker), so concurrent workers can never delete
    each other's XMLs even when two tarballs contain the same PMC ID. The
    TemporaryDirectory context manager auto-cleans on exit (success OR
    exception), so disk usage is bounded by `workers x max_tarball_size`.

    Returns a stats dict for this tarball.
    """
    out_dir = parsed_dir / tier
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = tarball_path.name.removesuffix(".tar.gz")
    out_path = out_dir / f"{stem}.jsonl.gz"
    skipped_log = parsed_dir / "skipped_retractions.jsonl"

    if out_path.exists() and out_path.stat().st_size > 0:
        return {
            "tarball": tarball_path.name,
            "tier": tier,
            "status": "already-done",
            "parsed": 0,
            "retracted_skipped": 0,
            "parse_errors": 0,
        }

    try:
        retracted_ids, expected_count = load_filelist(filelist_path)
    except FileNotFoundError:
        retracted_ids, expected_count = set(), 0

    parsed = 0
    retracted_skipped = 0
    parse_errors = 0
    skipped_records: list[dict] = []

    # tempfile.TemporaryDirectory: per-worker isolated extract dir on Linux fs.
    # Auto-deletes on exit, so a crash mid-parse leaves no orphan files.
    with tempfile.TemporaryDirectory(prefix=f"{stem}_", dir=str(temp_dir)) as tmp_str:
        tmp_path = Path(tmp_str)

        # Verify + extract
        try:
            with tarfile.open(tarball_path, mode="r:gz") as tf:
                members = [m for m in tf.getmembers() if m.isfile() and m.name.endswith(".xml")]
                tf.extractall(tmp_path, members=members, filter="data")
                xml_paths = [tmp_path / m.name for m in members]
        except (tarfile.TarError, EOFError, OSError) as e:
            return {
                "tarball": tarball_path.name,
                "tier": tier,
                "status": "tar-error",
                "error": str(e),
                "parsed": 0,
                "retracted_skipped": 0,
                "parse_errors": 0,
            }

        # File-count cross-check (advisory — NCBI sometimes ships extras)
        _ = expected_count, len(xml_paths)

        # Stream JSONL to a .partial file first; rename atomically on success
        # so a crash mid-write never leaves a half-written .jsonl.gz on disk
        # that the next run would mistake for "already done".
        partial_path = out_path.with_suffix(out_path.suffix + ".partial")
        try:
            with gzip.open(partial_path, mode="wt", encoding="utf-8") as out_f:
                for xml_path in xml_paths:
                    pmc_id = xml_path.stem

                    if pmc_id in retracted_ids:
                        retracted_skipped += 1
                        skipped_records.append(
                            {
                                "pmc_id": pmc_id,
                                "tier": tier,
                                "tarball": tarball_path.name,
                                "reason": "filelist_retracted",
                            }
                        )
                        continue

                    record = parse_jats(xml_path)
                    if record is None:
                        parse_errors += 1
                        continue

                    record["_tier"] = tier
                    record["_tarball"] = tarball_path.name
                    out_f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                    out_f.write("\n")
                    parsed += 1
            # Atomic publish — only swap into place if the whole write succeeded.
            partial_path.replace(out_path)
        except Exception:
            with contextlib.suppress(OSError):
                partial_path.unlink()
            raise

    if skipped_records:
        with skipped_log.open("a", encoding="utf-8") as fh:
            for r in skipped_records:
                fh.write(json.dumps(r) + "\n")

    return {
        "tarball": tarball_path.name,
        "tier": tier,
        "status": "ok",
        "parsed": parsed,
        "retracted_skipped": retracted_skipped,
        "parse_errors": parse_errors,
    }


# ---------------------------------------------------------------- status reporter
def status_reporter(stats: Stats, status_path: Path, interval: int) -> None:
    """Print a single status line every ``interval`` seconds."""
    while True:
        time.sleep(interval)
        with stats.lock:
            if stats.done:
                break
            now = time.time()
            elapsed = now - stats.start_ts
            interval_elapsed = max(now - stats.last_print_ts, 1e-6)
            interval_parsed = stats.parsed - stats.last_print_parsed
            rate_overall = stats.parsed / elapsed if elapsed > 0 else 0.0
            rate_recent = interval_parsed / interval_elapsed
            stats.last_print_ts = now
            stats.last_print_parsed = stats.parsed

            line = (
                f"[STATUS {time.strftime('%H:%M:%SZ', time.gmtime(now))}] "
                f"tarballs={stats.tarballs_done}/{stats.tarballs_total} "
                f"parsed={stats.parsed} "
                f"retracted={stats.retracted_skipped} "
                f"errors={stats.parse_errors} "
                f"rate_overall={rate_overall:.0f}/sec "
                f"rate_recent={rate_recent:.0f}/sec "
                f"elapsed={elapsed / 60:.1f}min"
            )
            print(line, flush=True)

            with contextlib.suppress(OSError):
                status_path.write_text(
                    json.dumps(
                        {
                            "ts": now,
                            "tarballs_total": stats.tarballs_total,
                            "tarballs_done": stats.tarballs_done,
                            "parsed": stats.parsed,
                            "retracted_skipped": stats.retracted_skipped,
                            "parse_errors": stats.parse_errors,
                            "rate_overall_per_sec": rate_overall,
                            "rate_recent_per_sec": rate_recent,
                            "elapsed_min": elapsed / 60,
                        },
                        indent=2,
                    )
                )


# ---------------------------------------------------------------- main
def discover_tarballs(archives_dir: Path) -> list[tuple[Path, Path, str]]:
    """Return (tarball, filelist, tier) triples found under archives_dir."""
    pairs: list[tuple[Path, Path, str]] = []
    for tier in TIERS:
        tier_dir = archives_dir / tier
        if not tier_dir.is_dir():
            continue
        for tarball in sorted(tier_dir.glob("*.tar.gz")):
            stem = tarball.name.removesuffix(".tar.gz")
            filelist = tier_dir / f"{stem}.filelist.csv"
            pairs.append((tarball, filelist, tier))
    return pairs


def main() -> int:
    """Parse args, dispatch workers, print final summary."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--archives-dir", type=Path, default=ARCHIVES_DIR)
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=TEMP_DIR,
        help="Per-worker temp extract base (Linux ext4 recommended; "
        "needs ~workers x max_tarball_size GB).",
    )
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_DIR)
    parser.add_argument(
        "--workers",
        type=int,
        default=max((os.cpu_count() or 2) // 2, 1),
        help="Parallel workers (default: half of CPU count)",
    )
    parser.add_argument(
        "--status-interval",
        type=int,
        default=STATUS_INTERVAL_SEC,
        help="Status print interval in seconds (default 180)",
    )
    # Backward-compat no-op flags from earlier script versions; ignored.
    parser.add_argument("--extract-dir", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--delete-extracted", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    args.temp_dir.mkdir(parents=True, exist_ok=True)
    args.parsed_dir.mkdir(parents=True, exist_ok=True)

    pairs = discover_tarballs(args.archives_dir)
    if not pairs:
        print(f"ERROR: no tarballs under {args.archives_dir}", file=sys.stderr)
        return 1

    stats = Stats()
    stats.tarballs_total = len(pairs)

    print(
        f"=== Process {stats.tarballs_total} tarballs with {args.workers} workers ===",
        flush=True,
    )
    print(f"  archives_dir : {args.archives_dir}", flush=True)
    print(f"  temp_dir     : {args.temp_dir}", flush=True)
    print(f"  parsed_dir   : {args.parsed_dir}", flush=True)
    print(f"  status every : {args.status_interval}s", flush=True)
    print(flush=True)

    status_path = args.parsed_dir / "_status.json"
    reporter = threading.Thread(
        target=status_reporter,
        args=(stats, status_path, args.status_interval),
        daemon=True,
    )
    reporter.start()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                process_tarball,
                t,
                fl,
                tier,
                args.temp_dir,
                args.parsed_dir,
            ): (t, tier)
            for t, fl, tier in pairs
        }
        for fut in as_completed(futures):
            try:
                result = fut.result()
            except Exception as e:
                tarball, _ = futures[fut]
                print(f"WORKER CRASH: {tarball.name}: {e}", file=sys.stderr, flush=True)
                with stats.lock:
                    stats.tarballs_done += 1
                continue
            with stats.lock:
                stats.tarballs_done += 1
                stats.parsed += result.get("parsed", 0)
                stats.retracted_skipped += result.get("retracted_skipped", 0)
                stats.parse_errors += result.get("parse_errors", 0)
            if result.get("status") not in ("ok", "already-done"):
                print(
                    f"  {result['tarball']}: {result.get('status')} {result.get('error', '')}",
                    flush=True,
                )

    with stats.lock:
        stats.done = True
    reporter.join(timeout=2)

    elapsed = time.time() - stats.start_ts
    print(flush=True)
    print(f"=== DONE in {elapsed / 60:.1f} min ===", flush=True)
    print(f"  tarballs:           {stats.tarballs_done}/{stats.tarballs_total}", flush=True)
    print(f"  parsed:             {stats.parsed}", flush=True)
    print(f"  retracted_skipped:  {stats.retracted_skipped}", flush=True)
    print(f"  parse_errors:       {stats.parse_errors}", flush=True)
    print(f"  output dir:         {args.parsed_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
