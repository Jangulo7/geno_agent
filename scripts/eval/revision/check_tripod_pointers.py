"""Verify that every section named in the TRIPOD-LLM checklist actually exists.

The checklist's location column is prose, not \\ref, so neither latex_lint.py nor
consistency_check.py can see it -- and TRIPOD reviewers read the checklist as a map
and follow it. Thirteen entries once named sections the manuscript did not contain
(\\S Index construction, \\S Prompt design, \\S Reproducibility, \\S RAG-quality,
\\S Explainability, Results \\S Cohort setup, \\S Ablation, \\S Methodological
contribution, \\S Recency) and two of those promised content that was nowhere in
the paper.

Checks, over both the typeset checklist (Table S1) and its deposited CSV twin:
  1. every "S Name" pointer resolves to a real \\section/\\subsection title
  2. every "SS 4.x--4.y" span lies inside the Results subsection range
  3. the two files agree on which sections each item points at

Exit status is 1 on any failure, so this can gate a build.

Usage:
  python check_tripod_pointers.py --tex main.tex --supp p2_supplementary.tex \\
      --csv reports/p2_revision/tripod_llm_checklist.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Pointers that name a document part rather than a numbered heading. These are
# real locations in the submission, just not \section titles in main.tex.
FRONT_BACK_MATTER = {
    "Title",
    "Abstract",
    "Declarations",
    "Ethics",
    "Funding",
    "Competing interests",
    "Availability",
    "Data availability",
    "Code availability",
    "Supplementary material",
}

HEADING = re.compile(r"^\\(?:sub)?section\{([^}]*)\}", re.M)
# "\S Name" / "§ Name" up to the next delimiter that ends a pointer phrase.
# A pointer ends at the next LaTeX escape, bracket or separator. The char class
# excludes "\" so the lazy match stops there; without the "\\" lookahead a name
# containing an escape (geno\_agent) would fail to match at all rather than
# resolve, silently dropping the pointer from the check.
POINTER = re.compile(r"(?:\\S|§)\s*([A-Z][^+;()\\§]*?)(?=\s*(?:\\|[+;()]|§|$))")
SPAN = re.compile(r"(?:\\S\\S|§§)\s*(\d)\.(\d)\s*(?:--|-)\s*(\d)\.(\d)")
# A pointer may carry a trailing gloss: "\S Ethics --- exemption granted by ..."
# or "\S Comparator systems, Cell S (...)". The section name is what precedes it.
# The CSV twin spells the em-dash as a plain hyphen, so accept both.
GLOSS = re.compile(r"\s*(?:---|--|—|-|,)\s")


def normalise(s: str) -> str:
    """LaTeX and plain-text spellings of the same name compare equal."""
    s = s.replace("~", " ").replace("---", "-").replace("--", "-")
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    return re.sub(r"\s+", " ", s).strip().rstrip(".")


def section_name(pointer: str, known: set[str] | None = None) -> str:
    """The section title a pointer names, with any trailing gloss removed.

    Splitting blindly at the first gloss delimiter is wrong: a real title can
    contain a comma ("What each tool is for, and what the results support",
    "Stratification, judging and ablations"), and blind splitting truncated those
    to a prefix, which then reported as an abbreviation of itself. So try the whole
    string first and only strip a gloss if the whole string names no section.
    """
    whole = normalise(pointer)
    if known is not None and whole in known:
        return whole
    stripped = normalise(GLOSS.split(pointer, 1)[0])
    # Neither form is an exact title; prefer the longer one if it uniquely
    # prefixes a heading, so the caller reports the more informative name.
    if (
        known is not None
        and stripped not in known
        and sum(1 for k in known if k.startswith(whole)) == 1
    ):
        return whole
    return stripped


def resolves(name: str, known: set[str]) -> tuple[bool, bool]:
    """Return (resolves, is_exact).

    Exact match is the property worth having: a cell that names its section in
    full cannot drift when the section is renamed, and cannot be read as pointing
    somewhere else. Shorthand is still accepted when it is an unambiguous prefix of
    exactly one heading -- "\\S What each tool is for" for the full Discussion
    title -- because rejecting it would fail cells that are not wrong. Those are
    reported as NOTE rather than FAIL, so abbreviation stays visible instead of
    silently accumulating.
    """
    if name in known:
        return True, True
    return sum(1 for k in known if k.startswith(name)) == 1, False


def headings(tex: str) -> set[str]:
    return {normalise(h) for h in HEADING.findall(tex)}


def results_range(tex: str) -> tuple[int, int]:
    """(first, last) index of the Results subsections, 1-based."""
    order = HEADING.findall(tex)
    body = tex
    in_results, n = False, 0
    for m in re.finditer(r"^\\(section|subsection)\{([^}]*)\}", body, re.M):
        kind, title = m.group(1), m.group(2).strip()
        if kind == "section":
            if title == "Results":
                in_results, n = True, 0
            elif in_results:
                break
        elif in_results:
            n += 1
    del order
    return 1, n


def pointers_from_tex(supp: str, known: set[str]) -> dict[str, list[str]]:
    """item number -> section names it points at, from the Table S1 longtable."""
    block = supp.split(r"\label{tab:tripod}", 1)[1].split(r"\end{longtable}", 1)[0]
    out: dict[str, list[str]] = {}
    for line in block.split("\n"):
        m = re.match(r"\s*(\d+[a-z]?)\s*&", line)
        if not m:
            continue
        out[m.group(1)] = [section_name(p, known) for p in POINTER.findall(line)]
    return out


def pointers_from_csv(path: str, known: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            loc = row["manuscript_location_or_rationale"]
            out[row["item"]] = [section_name(p, known) for p in POINTER.findall(loc)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tex", required=True)
    ap.add_argument("--supp", required=True)
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()

    main_tex = Path(args.tex).read_text()
    supp_tex = Path(args.supp).read_text()
    csv_text = Path(args.csv).read_text()
    known = headings(main_tex) | {normalise(x) for x in FRONT_BACK_MATTER}
    _, n_results = results_range(main_tex)

    tex_ptrs = pointers_from_tex(supp_tex, known)
    csv_ptrs = pointers_from_csv(args.csv, known)

    fails: list[str] = []
    notes: list[str] = []

    # 1. pointers resolve
    for label, ptrs in (("Table S1", tex_ptrs), ("checklist CSV", csv_ptrs)):
        for item, names in sorted(ptrs.items()):
            for name in names:
                if not name:
                    continue
                found, exact = resolves(name, known)
                if not found:
                    fails.append(f"{label} item {item}: no section titled '{name}'")
                elif not exact:
                    match = next(k for k in known if k.startswith(name))
                    notes.append(f"{label} item {item}: '{name}' abbreviates '{match}'")

    # 2. subsection spans lie inside Results
    for label, text in (("Table S1", supp_tex), ("checklist CSV", csv_text)):
        for a1, a2, b1, b2 in SPAN.findall(text):
            if int(a1) != 4 or int(b1) != 4:
                continue
            if int(b2) > n_results:
                fails.append(
                    f"{label}: span 4.{a2}--4.{b2} exceeds Results, which has "
                    f"{n_results} subsections (4.1--4.{n_results})"
                )

    # 3. the two copies agree
    for item in sorted(set(tex_ptrs) | set(csv_ptrs)):
        a, b = tex_ptrs.get(item, []), csv_ptrs.get(item, [])
        if a != b:
            fails.append(f"item {item}: Table S1 points at {a}, CSV points at {b}")

    n_ptrs = sum(len(v) for v in tex_ptrs.values())
    print(f"TRIPOD pointer gate: {len(tex_ptrs)} items, {n_ptrs} section pointers")
    print(
        f"  Results has {n_results} subsections; main.tex defines {len(headings(main_tex))} headings"
    )
    for n in notes:
        print(f"  NOTE  {n}")
    for f in fails:
        print(f"  FAIL  {f}")
    if fails:
        print(f"\n{len(fails)} failures")
        return 1
    print("\n  all pointers resolve; Table S1 and the CSV agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
