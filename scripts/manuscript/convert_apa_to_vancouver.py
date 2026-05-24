"""Convert manuscript references from APA to Springer Vancouver style.

This script reads the manuscript draft files (manuscript_q1_draft.md and
manuscript_methods_draft.md), parses the APA-style numbered reference list
at the end of the main manuscript, scans both files for in-text APA
citations (e.g. ``[Smedley et al., 2015]``), and produces Vancouver-style
outputs:

  * a Vancouver-formatted reference list (re-numbered by order of first
    appearance in the manuscript text),
  * converted manuscript files with in-text citations rewritten to
    bracketed integer form (e.g. ``[12]``, ``[3, 7]``),
  * a citation-remapping audit TSV.

By default the script runs in *dry-run* mode: it writes preview files to
``reports/_vancouver_preview/`` and reports unmatched citations. Pass
``--apply`` to overwrite the source manuscripts in place (a timestamped
backup is created first).

Springer Vancouver formatting decisions used here:

  * Up to 6 authors are listed in full; with 7 or more authors, list the
    first 6 followed by ``et al.``.
  * Journal names are kept as written in the APA entry. The user should
    consult NLM / ISO 4 abbreviations at submission time and run a
    final sed-style pass; this script does not auto-abbreviate to avoid
    silent errors.
  * Volume(Issue):Pages formatted as ``Vol(Issue):Pages``; missing issue
    is rendered as ``Vol:Pages``.
  * DOI rendered as ``doi:10.xxxx/...`` (no ``https://doi.org/`` prefix,
    per BMC/Springer Vancouver guidance).
  * For preprints, books, software, and conference proceedings, the
    available metadata is rendered in the order: Authors. Title. Venue
    / Publisher. Year[;Volume:Pages]. doi/URL.

Usage::

    python scripts/manuscript/convert_apa_to_vancouver.py [--apply]

Outputs (dry-run by default), all under ``reports/_vancouver_preview/``:

  * ``manuscript_q1_draft.md`` (main, citations rewritten + refs replaced)
  * ``manuscript_methods_draft.md`` (Methods, citations rewritten)
  * ``references_vancouver.md`` (standalone Vancouver reference list)
  * ``citation_remapping.tsv`` (audit trail: APA num -> Vancouver num)
  * ``side_by_side_audit.md`` (per-entry comparison; manual-review flags)
  * ``unmatched_citations.txt`` (any in-text citation that did not resolve)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "reports"
MANUSCRIPT_MAIN = REPORTS_DIR / "manuscript_q1_draft.md"
MANUSCRIPT_METHODS = REPORTS_DIR / "manuscript_methods_draft.md"
PREVIEW_DIR = REPORTS_DIR / "_vancouver_preview"

REFERENCE_ENTRY_RE = re.compile(
    r"^(?P<num>\d{1,3})\.\s+(?P<body>.+?)(?=^\d{1,3}\.\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
YEAR_IN_ENTRY_RE = re.compile(r"\((?P<year>\d{4}[a-z]?)\)")
DOI_IN_ENTRY_RE = re.compile(r"https?://doi\.org/(?P<doi>\S+)")
ARXIV_IN_ENTRY_RE = re.compile(r"arxiv\.org/abs/(?P<arxiv>\S+)", re.IGNORECASE)
URL_IN_ENTRY_RE = re.compile(r"https?://\S+")
_EN_DASH = chr(0x2013)  # EN DASH; chr() form avoids RUF001 in source
ITALIC_JOURNAL_RE = re.compile(
    r"\*(?P<journal>[^*]+?),\s*(?P<volume>\d+[A-Za-z]?)\*"
    r"(?:\((?P<issue>[^)]+)\))?,\s*"
    rf"(?P<pages>[\dA-Za-z]+(?:[-{_EN_DASH}][\dA-Za-z]+)?)"
)
ITALIC_TITLE_OR_VENUE_RE = re.compile(r"\*(?P<text>[^*]+?)\*")

CITATION_RE = re.compile(
    r"\[(?P<inner>(?:[A-Z][^\[\]]{1,180}?,\s*\d{4}[a-z]?"
    r"(?:\s*;\s*[A-Z][^\[\]]{1,180}?,\s*\d{4}[a-z]?)*"
    r"|[A-Z][^\[\]]{1,180}?,\s*\*[^*]+\*\s*\d{4}[a-z]?))\]"
)
NARRATIVE_CITATION_RE = re.compile(
    r"(?P<full>\b(?P<surname>[A-Z][\w'-]+)"
    r"(?:\s+(?P<initial>[A-Z])\.)?"
    r"(?:\s+et\s+al\.|\s+&\s+[A-Z][\w'-]+)?)"
    r"\s+\[(?P<year>\d{4}[a-z]?)\]"
)
SINGLE_CITE_RE = re.compile(
    r"^(?P<author>.+?),\s*(?:\*(?P<embedded_venue>[^*]+)\*\s*)?"
    r"(?P<year>\d{4}[a-z]?)$"
)
AUTHOR_FIRSTNAME_INITIAL_RE = re.compile(
    r"^(?P<surname>[A-Z][\w' -]+?)\s+(?P<initial>[A-Z])\.\s+et\s+al\.$"
)
AUTHOR_ETAL_RE = re.compile(r"^(?P<surname>[A-Z][\w' -]+?)\s+et\s+al\.$")
AUTHOR_AMP_RE = re.compile(r"^(?P<a>[A-Z][\w' -]+?)\s*&\s*(?P<b>[A-Z][\w' -]+?)$")


@dataclass
class Reference:
    """A parsed APA reference entry."""

    original_num: int
    raw_body: str
    authors: list[str] = field(default_factory=list)
    year: str = ""
    title: str = ""
    journal_or_venue: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    is_truncated_authors: bool = False
    new_num: int | None = None

    @property
    def first_author_surname(self) -> str:
        """Return the surname of the first listed author, normalised lowercase."""
        if not self.authors:
            return ""
        first = self.authors[0]
        return first.split(",")[0].strip().lower()

    @property
    def first_author_first_initial(self) -> str:
        """First initial of the first author, used for disambiguation."""
        if not self.authors:
            return ""
        first = self.authors[0]
        parts = first.split(",")
        if len(parts) < 2:
            return ""
        return parts[1].strip()[:1].upper()


def looks_like_initials(token: str) -> bool:
    """Heuristic: a token consisting only of capitals, periods, hyphens, spaces."""
    if not token or len(token) > 12:
        return False
    return bool(re.fullmatch(r"[A-Z\.\-\s]+", token))


def parse_authors(authors_blob: str) -> tuple[list[str], bool]:
    """Split an APA author block into individual ``Surname, Initials`` entries.

    APA truncates long lists with an ellipsis ``…`` before the final author.
    Returns the parsed list plus a flag indicating whether truncation was
    present.
    """
    truncated = "…" in authors_blob or "..." in authors_blob
    cleaned = authors_blob.replace("…", ",").replace("...", ",")
    cleaned = re.sub(r",?\s*&\s*", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".,")

    raw_tokens = [t.strip().rstrip(".") for t in cleaned.split(",")]
    raw_tokens = [t for t in raw_tokens if t]
    raw_tokens = [t for t in raw_tokens if not t.lower().startswith("on behalf")]

    authors: list[str] = []
    i = 0
    while i < len(raw_tokens):
        surname = raw_tokens[i]
        if i + 1 < len(raw_tokens) and looks_like_initials(raw_tokens[i + 1]):
            authors.append(f"{surname}, {raw_tokens[i + 1]}")
            i += 2
        else:
            authors.append(surname)
            i += 1
    return authors, truncated


def parse_reference(num: int, body: str) -> Reference:
    """Parse a single APA reference entry into structured form."""
    body = body.strip()
    ref = Reference(original_num=num, raw_body=body)

    year_match = YEAR_IN_ENTRY_RE.search(body)
    if not year_match:
        return ref
    ref.year = year_match.group("year")
    authors_blob = body[: year_match.start()].rstrip(" .,")
    ref.authors, ref.is_truncated_authors = parse_authors(authors_blob)

    after_year = body[year_match.end() :].lstrip(" .")

    journal_match = ITALIC_JOURNAL_RE.search(after_year)
    if journal_match:
        title_blob = after_year[: journal_match.start()].rstrip(" .,")
        ref.title = title_blob.strip()
        ref.journal_or_venue = journal_match.group("journal").strip()
        ref.volume = journal_match.group("volume").strip()
        ref.issue = (journal_match.group("issue") or "").strip()
        ref.pages = journal_match.group("pages").strip().replace(_EN_DASH, "-")
    else:
        italic_match = ITALIC_TITLE_OR_VENUE_RE.search(after_year)
        if italic_match:
            title_or_venue = italic_match.group("text").strip()
            preceding = after_year[: italic_match.start()].rstrip(" .,")
            if preceding:
                ref.title = preceding.strip()
                ref.journal_or_venue = title_or_venue
            else:
                ref.title = title_or_venue
                tail = after_year[italic_match.end() :].strip(" .,")
                ref.journal_or_venue = tail.split(".")[0] if tail else ""
        else:
            ref.title = after_year.split(".")[0].strip()

    doi_match = DOI_IN_ENTRY_RE.search(body)
    if doi_match:
        ref.doi = doi_match.group("doi").rstrip(".,)")
    else:
        arxiv_match = ARXIV_IN_ENTRY_RE.search(body)
        if arxiv_match:
            ref.url = f"https://arxiv.org/abs/{arxiv_match.group('arxiv').rstrip('.,)')}"
        else:
            url_match = URL_IN_ENTRY_RE.search(body)
            if url_match:
                ref.url = url_match.group(0).rstrip(".,)")

    return ref


def load_reference_list(text: str) -> list[Reference]:
    """Extract the references section and parse every numbered entry."""
    section_match = re.search(r"^##\s+References.*?$", text, re.MULTILINE | re.IGNORECASE)
    if not section_match:
        raise RuntimeError("Could not locate '## References' header in main manuscript.")
    refs_blob = text[section_match.end() :]
    entries: list[Reference] = []
    for match in REFERENCE_ENTRY_RE.finditer(refs_blob):
        num = int(match.group("num"))
        ref = parse_reference(num, match.group("body"))
        entries.append(ref)
    return entries


def build_lookup(refs: list[Reference]) -> dict[tuple[str, str, str], Reference]:
    """Return a (surname, year, initial) -> Reference index, initial may be ''."""
    index: dict[tuple[str, str, str], Reference] = {}
    for ref in refs:
        surname = ref.first_author_surname
        if not surname or not ref.year:
            continue
        initial = ref.first_author_first_initial
        index[(surname, ref.year, "")] = ref
        if initial:
            index[(surname, ref.year, initial)] = ref
    return index


def normalise_single_citation(inner: str) -> tuple[str, str, str] | None:
    """Map a single citation token to a (surname, year, initial) lookup key.

    Examples accepted::

        Smedley et al., 2015
        Yang A. et al., 2025
        Jacobsen et al., 2022a
        Kapoor & Narayanan, 2023
        Zhao W. et al., *Nature* 2026
        OpenAI, 2024
    """
    inner = inner.strip()
    match = SINGLE_CITE_RE.match(inner)
    if not match:
        return None
    author_part = match.group("author").strip()
    year = match.group("year")

    initial_match = AUTHOR_FIRSTNAME_INITIAL_RE.match(author_part)
    if initial_match:
        return (
            initial_match.group("surname").strip().lower(),
            year,
            initial_match.group("initial").upper(),
        )
    etal_match = AUTHOR_ETAL_RE.match(author_part)
    if etal_match:
        return (etal_match.group("surname").strip().lower(), year, "")
    amp_match = AUTHOR_AMP_RE.match(author_part)
    if amp_match:
        return (amp_match.group("a").strip().lower(), year, "")
    return (author_part.lower(), year, "")


def split_compound_citation(inner: str) -> list[str]:
    """Split a citation body on semicolons, normalising internal whitespace.

    Citations may wrap across source lines in the manuscript Markdown; we
    flatten whitespace before splitting so the per-token regex can match.
    """
    flat = re.sub(r"\s+", " ", inner).strip()
    parts = [p.strip() for p in flat.split(";")]
    return [p for p in parts if p]


def resolve_citation_token(
    token: str, lookup: dict[tuple[str, str, str], Reference]
) -> Reference | None:
    """Look up a parsed single-citation key with disambiguation fallback."""
    key = normalise_single_citation(token)
    if key is None:
        return None
    if key in lookup:
        return lookup[key]
    if key[2]:
        return lookup.get((key[0], key[1], ""))
    return None


def assign_numbers_by_first_appearance(
    text_in_order: str, lookup: dict[tuple[str, str, str], Reference]
) -> tuple[list[Reference], list[str]]:
    """Walk the text in source order and assign Vancouver numbers.

    Picks up both bracketed citations (``[Smedley et al., 2015]``) and
    narrative citations (``Smedley et al. [2015]``) in a single ordered
    pass over the source text.
    """
    ordered: list[Reference] = []
    seen_ids: set[int] = set()
    unmatched: list[str] = []
    next_num = 1
    citation_iter = sorted(
        (
            list(CITATION_RE.finditer(text_in_order))
            + list(NARRATIVE_CITATION_RE.finditer(text_in_order))
        ),
        key=lambda m: m.start(),
    )
    for match in citation_iter:
        groupdict = match.groupdict()
        if "inner" in groupdict and groupdict.get("inner") is not None:
            tokens = split_compound_citation(groupdict["inner"])
            refs_to_add = [(token, resolve_citation_token(token, lookup)) for token in tokens]
        else:
            surname = groupdict["surname"]
            initial = groupdict.get("initial") or ""
            year = groupdict["year"]
            key = (surname.lower(), year, initial)
            ref = lookup.get(key) or lookup.get((surname.lower(), year, ""))
            refs_to_add = [(groupdict["full"], ref)]
        for token, ref in refs_to_add:
            if ref is None:
                unmatched.append(token)
                continue
            if id(ref) in seen_ids:
                continue
            ref.new_num = next_num
            next_num += 1
            seen_ids.add(id(ref))
            ordered.append(ref)
    return ordered, unmatched


def format_vancouver_authors(authors: list[str], truncated: bool) -> str:
    """Render an APA-parsed author list as Springer Vancouver.

    Up to 6 authors are listed in full; with 7+ authors (or truncation in
    the source APA list) the first 6 are followed by ``et al.``.
    """
    if not authors:
        return ""

    def to_vancouver(name: str) -> str:
        if "," not in name:
            return name.strip()
        surname, initials_blob = (p.strip() for p in name.split(",", 1))
        initials = re.findall(r"[A-Z]", initials_blob)
        if not initials:
            return surname
        return f"{surname} {''.join(initials)}"

    rendered = [to_vancouver(a) for a in authors]
    if truncated or len(rendered) > 6:
        head = rendered[:6]
        return ", ".join(head) + ", et al"
    return ", ".join(rendered)


def format_vancouver_entry(ref: Reference) -> str:
    """Render a parsed reference as a Springer Vancouver entry.

    Returns the entry body without the leading number. Entries that did
    not cleanly parse into a journal+volume+pages shape (books, software,
    web resources, preprints) are rendered in a best-effort form and
    flagged in the audit TSV for manual review.
    """
    parts: list[str] = []
    authors_str = format_vancouver_authors(ref.authors, ref.is_truncated_authors)
    if authors_str:
        parts.append(f"{authors_str}.")
    if ref.title:
        parts.append(ref.title.rstrip(".") + ".")
    if ref.journal_or_venue:
        if ref.volume and ref.pages:
            issue_part = f"({ref.issue})" if ref.issue else ""
            parts.append(
                f"{ref.journal_or_venue}. {ref.year};{ref.volume}{issue_part}:{ref.pages}."
            )
        else:
            parts.append(f"{ref.journal_or_venue}. {ref.year}.")
    else:
        parts.append(f"{ref.year}.")
    if ref.doi:
        parts.append(f"doi:{ref.doi}.")
    elif ref.url:
        parts.append(f"{ref.url}.")
    rendered = " ".join(parts)
    rendered = re.sub(r"\.{2,}", ".", rendered)
    rendered = re.sub(r"\s+\.", ".", rendered)
    return rendered


def render_vancouver_reference_list(ordered_refs: list[Reference]) -> str:
    """Produce the final numbered Vancouver reference list as Markdown."""
    lines = ["## References", ""]
    for ref in ordered_refs:
        entry = format_vancouver_entry(ref)
        lines.append(f"{ref.new_num}. {entry}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def rewrite_inline_citations(
    text: str, lookup: dict[tuple[str, str, str], Reference]
) -> tuple[str, list[str]]:
    """Replace APA citations with Vancouver-style integer tokens.

    Handles both bracketed citations (``[Smedley et al., 2015]`` →
    ``[N]``) and narrative citations (``Smedley et al. [2015]`` →
    ``Smedley et al. [N]``, preserving the author run-in).
    """
    unmatched_local: list[str] = []

    def replace_bracketed(match: re.Match[str]) -> str:
        inner = match.group("inner")
        nums: list[int] = []
        for token in split_compound_citation(inner):
            ref = resolve_citation_token(token, lookup)
            if ref is None or ref.new_num is None:
                unmatched_local.append(token)
                return match.group(0)
            nums.append(ref.new_num)
        nums = sorted(set(nums))
        return "[" + ", ".join(str(n) for n in nums) + "]"

    def replace_narrative(match: re.Match[str]) -> str:
        full = match.group("full")
        surname = match.group("surname")
        initial = match.group("initial") or ""
        year = match.group("year")
        key = (surname.lower(), year, initial)
        ref = lookup.get(key) or lookup.get((surname.lower(), year, ""))
        if ref is None or ref.new_num is None:
            unmatched_local.append(f"{full} [{year}]")
            return match.group(0)
        return f"{full} [{ref.new_num}]"

    rewritten = CITATION_RE.sub(replace_bracketed, text)
    rewritten = NARRATIVE_CITATION_RE.sub(replace_narrative, rewritten)
    return rewritten, unmatched_local


def replace_reference_section(text: str, new_refs_md: str) -> str:
    """Swap the APA references block with the Vancouver list, preserving tail.

    The References section runs until the next top-level ``## `` heading
    (typically ``## Tables and figures``) or end-of-file. Anything after
    the References section is preserved verbatim.
    """
    start_match = re.search(r"^##\s+References.*?$", text, re.MULTILINE | re.IGNORECASE)
    if not start_match:
        return text
    after_refs = text[start_match.end() :]
    next_heading = re.search(r"^##\s", after_refs, re.MULTILINE)
    tail = "" if next_heading is None else after_refs[next_heading.start() :]
    head = text[: start_match.start()]
    body = new_refs_md.rstrip() + "\n"
    if tail:
        body += "\n---\n\n" + tail
    return head + body


def write_outputs(
    *,
    main_text: str,
    methods_text: str,
    references_md: str,
    remap_tsv: str,
    side_by_side_md: str,
    unmatched: list[str],
    target_dir: Path,
) -> None:
    """Write the preview artefacts to *target_dir*."""
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "manuscript_q1_draft.md").write_text(main_text, encoding="utf-8")
    (target_dir / "manuscript_methods_draft.md").write_text(methods_text, encoding="utf-8")
    (target_dir / "references_vancouver.md").write_text(references_md, encoding="utf-8")
    (target_dir / "citation_remapping.tsv").write_text(remap_tsv, encoding="utf-8")
    (target_dir / "side_by_side_audit.md").write_text(side_by_side_md, encoding="utf-8")
    (target_dir / "unmatched_citations.txt").write_text(
        "\n".join(sorted(set(unmatched))) + "\n", encoding="utf-8"
    )


def build_remap_tsv(refs: list[Reference]) -> str:
    """Produce the audit-trail TSV mapping APA number to Vancouver number."""
    rows = ["original_apa_num\tnew_vancouver_num\tfirst_author\tyear\ttitle"]
    for ref in refs:
        if ref.new_num is None:
            continue
        first_author = ref.authors[0] if ref.authors else ""
        title = ref.title.replace("\t", " ")
        rows.append(f"{ref.original_num}\t{ref.new_num}\t{first_author}\t{ref.year}\t{title}")
    rows.append("")
    return "\n".join(rows)


def build_side_by_side_audit(refs: list[Reference]) -> str:
    """Produce a side-by-side Markdown audit of APA original vs Vancouver output.

    Cited references (ordered by Vancouver number) appear first; uncited
    references appear under a separate heading at the end.
    """
    cited = sorted(
        [r for r in refs if r.new_num is not None],
        key=lambda r: r.new_num,
    )
    uncited = [r for r in refs if r.new_num is None]
    lines = [
        "# APA -> Vancouver conversion audit",
        "",
        (
            "Side-by-side comparison of each parsed APA entry and its rendered "
            "Springer Vancouver form. Review each row before running with "
            "`--apply`; entries flagged for manual review have incomplete "
            "Volume / Pages metadata in the parsed APA source."
        ),
        "",
        "## Cited references (in Vancouver order)",
        "",
        "| # (Van) | # (APA) | First author | Year | APA original | Vancouver rendered | Manual review? |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for ref in cited:
        first_author = (ref.authors[0] if ref.authors else "").replace("|", "\\|")
        original = ref.raw_body.replace("\n", " ").replace("|", "\\|").strip()
        rendered = format_vancouver_entry(ref).replace("|", "\\|")
        flag = "yes" if not (ref.volume and ref.pages and ref.doi) else ""
        lines.append(
            f"| {ref.new_num} | {ref.original_num} | {first_author} | {ref.year} | "
            f"{original} | {rendered} | {flag} |"
        )
    if uncited:
        lines.extend(
            [
                "",
                "## Parsed but never cited in text",
                "",
                (
                    "These references were in the APA list but no matching in-text "
                    "citation resolved to them. Confirm they really are unused, "
                    "then delete them from the manuscript reference list."
                ),
                "",
                "| # (APA) | First author | Year | Title |",
                "|---:|---|---|---|",
            ]
        )
        for ref in uncited:
            first_author = (ref.authors[0] if ref.authors else "").replace("|", "\\|")
            title = ref.title.replace("|", "\\|")
            lines.append(f"| {ref.original_num} | {first_author} | {ref.year} | {title} |")
    lines.append("")
    return "\n".join(lines)


def backup_file(path: Path) -> Path:
    """Copy *path* to a timestamped sibling and return the backup's path."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_suffix(path.suffix + f".apa_backup_{stamp}")
    shutil.copy2(path, backup)
    return backup


def run(apply_changes: bool) -> int:
    """Top-level entry point. Returns a process exit code."""
    if not MANUSCRIPT_MAIN.exists() or not MANUSCRIPT_METHODS.exists():
        print("Manuscript files not found at expected paths.", file=sys.stderr)
        return 2

    main_text = MANUSCRIPT_MAIN.read_text(encoding="utf-8")
    methods_text = MANUSCRIPT_METHODS.read_text(encoding="utf-8")

    refs = load_reference_list(main_text)
    if not refs:
        print("No references parsed; aborting.", file=sys.stderr)
        return 2
    lookup = build_lookup(refs)

    combined_for_ordering = main_text + "\n" + methods_text
    ordered_refs, unmatched_ordering = assign_numbers_by_first_appearance(
        combined_for_ordering, lookup
    )

    rewritten_main, unmatched_main = rewrite_inline_citations(main_text, lookup)
    rewritten_methods, unmatched_methods = rewrite_inline_citations(methods_text, lookup)
    references_md = render_vancouver_reference_list(ordered_refs)
    rewritten_main_with_refs = replace_reference_section(rewritten_main, references_md)

    unmatched = unmatched_ordering + unmatched_main + unmatched_methods
    remap_tsv = build_remap_tsv(refs)
    side_by_side_md = build_side_by_side_audit(refs)

    uncited = [r for r in refs if r.new_num is None]

    write_outputs(
        main_text=rewritten_main_with_refs,
        methods_text=rewritten_methods,
        references_md=references_md,
        remap_tsv=remap_tsv,
        side_by_side_md=side_by_side_md,
        unmatched=unmatched,
        target_dir=PREVIEW_DIR,
    )

    print(f"Parsed {len(refs)} APA references.")
    print(f"Renumbered {len(ordered_refs)} references by first appearance.")
    if uncited:
        print(
            f"WARNING: {len(uncited)} references parsed but never cited in text:",
            file=sys.stderr,
        )
        for r in uncited:
            label = r.authors[0] if r.authors else "(no authors)"
            print(f"  - [{r.original_num}] {label} ({r.year})", file=sys.stderr)
    if unmatched:
        print(
            f"WARNING: {len(set(unmatched))} unique in-text citations did not resolve "
            "to any reference; see unmatched_citations.txt.",
            file=sys.stderr,
        )
    print(f"Preview written to {PREVIEW_DIR.relative_to(PROJECT_ROOT)}/")

    if apply_changes:
        if unmatched:
            print(
                "Refusing --apply with unmatched citations; resolve them and re-run.",
                file=sys.stderr,
            )
            return 1
        backup_main = backup_file(MANUSCRIPT_MAIN)
        backup_methods = backup_file(MANUSCRIPT_METHODS)
        MANUSCRIPT_MAIN.write_text(rewritten_main_with_refs, encoding="utf-8")
        MANUSCRIPT_METHODS.write_text(rewritten_methods, encoding="utf-8")
        print(
            f"Applied changes. Backups: "
            f"{backup_main.relative_to(PROJECT_ROOT)}, "
            f"{backup_methods.relative_to(PROJECT_ROOT)}"
        )
    return 0


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Overwrite the manuscript files in place (creates timestamped backups).",
    )
    args = parser.parse_args()
    sys.exit(run(apply_changes=args.apply))


if __name__ == "__main__":
    main()
