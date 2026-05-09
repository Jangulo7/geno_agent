"""Parse PMC JATS XML files into structured JSONL article records.

Implements master plan §4 step 1. Reads every ``PMC<id>.xml`` under
``$PMC_WORKSPACE/xml_raw/<tier>/`` (or a single ``--input-dir``) and
emits one JSON record per line containing the PMC ID, bibliographic
metadata, abstract, and section-segmented body text.

Output schema (one record per article)::

    {
      "pmcid": "PMC10258773",
      "pmid": "37306896",
      "doi": "10.1007/s10875-023-01526-3",
      "title": "...",
      "journal": "J Clin Immunol",
      "pub_year": 2023,
      "authors": ["Doe J", "Smith A"],
      "mesh_terms": [],
      "keywords": ["..."],
      "abstract": "...",
      "sections": [
        {"section_type": "introduction", "heading": "Introduction", "text": "..."},
        ...
      ]
    }

Section type is classified from the section heading text into
``introduction|methods|results|discussion|conclusion|case|other`` so
downstream chunkers can preserve scientific section boundaries.

Run from project root::

    python scripts/corpus/06_parse_jats_xml.py --input-dir /mnt/c/pmc_workspace/xml_raw/demo \\
                                               --output     /mnt/c/pmc_workspace/parsed/demo.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from lxml import etree
from tqdm import tqdm

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("parse_jats")

SECTION_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("introduction", re.compile(r"\b(introduction|background)\b", re.I)),
    ("methods", re.compile(r"\b(methods?|materials\s+and\s+methods|patients\s+and\s+methods)\b", re.I)),
    ("results", re.compile(r"\b(results?|findings|outcomes?)\b", re.I)),
    ("case", re.compile(r"\b(case\s+(report|description|presentation|series))\b", re.I)),
    ("discussion", re.compile(r"\b(discussion)\b", re.I)),
    ("conclusion", re.compile(r"\b(conclusions?)\b", re.I)),
)


def classify_section(heading: str, sec_type_attr: str | None) -> str:
    """Classify a section heading into a standardized section type.

    Args:
        heading: Section heading text (the ``<title>`` of the ``<sec>`` element).
        sec_type_attr: Value of the ``sec-type`` attribute, if any. JATS files
            often leave it blank, in which case the heading regex is used.

    Returns:
        One of ``introduction|methods|results|case|discussion|conclusion|other``.
    """
    if sec_type_attr:
        st = sec_type_attr.lower()
        if st in {"intro", "introduction"}:
            return "introduction"
        if st in {"methods", "materials"}:
            return "methods"
        if st in {"results"}:
            return "results"
        if st in {"discussion", "discuss"}:
            return "discussion"
        if st in {"conclusions", "conclusion"}:
            return "conclusion"
        if st in {"cases"}:
            return "case"
    for label, pat in SECTION_PATTERNS:
        if pat.search(heading):
            return label
    return "other"


def _text(el: etree._Element | None) -> str:
    """Return concatenated text content of an element, stripped, or empty."""
    if el is None:
        return ""
    return " ".join(t.strip() for t in el.itertext() if t.strip())


def _parse_pub_year(meta: etree._Element) -> int | None:
    """Pick the canonical publication year, preferring epub then ppub."""
    for kind in ("epub", "ppub", "pub", "collection"):
        years = meta.xpath(f'.//pub-date[@pub-type="{kind}"]/year/text()')
        if years:
            try:
                return int(years[0])
            except ValueError:
                continue
    years = meta.xpath(".//pub-date/year/text()")
    if years:
        try:
            return int(years[0])
        except ValueError:
            pass
    return None


def _parse_authors(meta: etree._Element) -> list[str]:
    """Extract a list of "Surname Initials" author strings."""
    authors: list[str] = []
    for c in meta.xpath('.//contrib-group/contrib[@contrib-type="author"]'):
        surname = "".join(c.xpath(".//surname/text()"))
        given = "".join(c.xpath(".//given-names/text()"))
        if surname:
            initials = "".join(part[0] for part in given.split() if part)
            authors.append(f"{surname} {initials}".strip())
    return authors


def _parse_sections(body: etree._Element | None) -> list[dict[str, str]]:
    """Walk the body and return a list of {section_type, heading, text} dicts."""
    if body is None:
        return []
    sections: list[dict[str, str]] = []
    for sec in body.xpath("./sec"):
        title_el = sec.find("title")
        heading = _text(title_el)
        sec_type = sec.get("sec-type") or ""
        paras = [_text(p) for p in sec.xpath(".//p")]
        text = "\n".join(p for p in paras if p)
        if not text:
            continue
        sections.append(
            {
                "section_type": classify_section(heading, sec_type),
                "heading": heading,
                "text": text,
            }
        )
    return sections


def parse_article(xml_path: Path) -> dict | None:
    """Parse one JATS XML file into the structured record schema."""
    try:
        tree = etree.parse(str(xml_path))
    except etree.XMLSyntaxError as exc:
        logger.warning(f"  {xml_path.name}: XML syntax error: {exc}")
        return None

    art = tree.find(".//article")
    if art is None:
        return None
    front = art.find("front")
    body = art.find("body")
    if front is None:
        return None

    meta = front.find("article-meta")
    if meta is None:
        return None

    pmcid_el = meta.xpath('.//article-id[@pub-id-type="pmcid"]/text()')
    pmid_el = meta.xpath('.//article-id[@pub-id-type="pmid"]/text()')
    doi_el = meta.xpath('.//article-id[@pub-id-type="doi"]/text()')
    title_el = meta.find(".//title-group/article-title")
    abstract_el = meta.find(".//abstract")
    journal_el = front.find(".//journal-meta//journal-title")

    pmcid = pmcid_el[0] if pmcid_el else xml_path.stem
    if not pmcid.startswith("PMC"):
        pmcid = f"PMC{pmcid}"

    return {
        "pmcid": pmcid,
        "pmid": pmid_el[0] if pmid_el else None,
        "doi": doi_el[0] if doi_el else None,
        "title": _text(title_el),
        "journal": _text(journal_el),
        "pub_year": _parse_pub_year(meta),
        "authors": _parse_authors(meta),
        "mesh_terms": meta.xpath(".//mesh-heading//descriptor/text()"),
        "keywords": [_text(k) for k in meta.xpath(".//kwd")],
        "abstract": _text(abstract_el),
        "sections": _parse_sections(body),
    }


def parse_args() -> argparse.Namespace:
    """CLI argument parsing."""
    p = argparse.ArgumentParser(description="Parse PMC JATS XML to JSONL.")
    workspace = os.environ.get("PMC_WORKSPACE", "/mnt/c/pmc_workspace")
    p.add_argument(
        "--input-dir", type=Path,
        default=Path(workspace) / "xml_raw" / "demo",
        help="Directory containing PMC<id>.xml files (default: demo dir).",
    )
    p.add_argument(
        "--output", type=Path,
        default=Path(workspace) / "parsed" / "demo.jsonl",
        help="Output JSONL path (default: parsed/demo.jsonl).",
    )
    return p.parse_args()


def main() -> int:
    """Read every XML in --input-dir, parse, write JSONL to --output."""
    args = parse_args()
    xmls = sorted(args.input_dir.glob("PMC*.xml"))
    if not xmls:
        logger.error(f"No PMC*.xml found under {args.input_dir}")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_ok, n_skip, n_chars, n_secs = 0, 0, 0, 0
    with args.output.open("w", encoding="utf-8") as out:
        for xml_path in tqdm(xmls, desc="parsing"):
            rec = parse_article(xml_path)
            if rec is None:
                n_skip += 1
                continue
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_ok += 1
            n_chars += len(rec["abstract"]) + sum(len(s["text"]) for s in rec["sections"])
            n_secs += len(rec["sections"])

    logger.info("=== Parse summary ===")
    logger.info(f"  parsed:        {n_ok}/{len(xmls)}  (skipped {n_skip})")
    logger.info(f"  total sections:{n_secs}")
    logger.info(f"  total chars:   {n_chars:,}")
    logger.info(f"  output:        {args.output}")
    return 0 if n_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
