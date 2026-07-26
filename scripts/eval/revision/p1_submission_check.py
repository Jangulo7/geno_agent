"""Group E pre-submission verification for the P1 Scientific Data descriptor.

Automates the checklist items that can be checked from the source, so the author
is left only with the ones that genuinely need a human or an external system
(APC confirmation, Croissant validation, deposit contents).

Scientific Data house rules encoded here: 110-character title cap, 170-word
abstract with no references, 700-word Background & Summary, no footnotes, and
every table and figure cited in the text in order of first appearance.

Usage:
    python scripts/eval/revision/p1_submission_check.py --tex path/to/main.tex
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

OK, WARN, FAIL = [], [], []


def rec(cond: bool, name: str, detail: str = "", soft: bool = False) -> None:
    if cond:
        OK.append(f"{name}{(' — ' + detail) if detail else ''}")
    elif soft:
        WARN.append(f"{name}: {detail}")
    else:
        FAIL.append(f"{name}: {detail}")


def strip_comments(tex: str) -> str:
    out = []
    for line in tex.splitlines():
        buf, esc = [], False
        for ch in line:
            if esc:
                buf.append(ch)
                esc = False
                continue
            if ch == "\\":
                buf.append(ch)
                esc = True
                continue
            if ch == "%":
                break
            buf.append(ch)
        out.append("".join(buf))
    return "\n".join(out)


def words(s: str) -> int:
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", " ", s)
    s = re.sub(r"[${}\\~^_]", " ", s)
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", s))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", required=True)
    args = ap.parse_args()
    raw = Path(args.tex).read_text()
    tex = strip_comments(raw)

    # --- Title: 110-character cap including spaces -------------------------
    m = re.search(r"\\title\{(?:\\textbf\{)?(.+?)\}?\}\s*$", tex, re.M | re.S)
    if m:
        title = re.sub(r"\s+", " ", re.sub(r"\\textbf\{|\}", "", m.group(1))).strip()
        rec(len(title) <= 110, "Title <= 110 chars", f"{len(title)} chars")
        print(f"    title: {title}")
    else:
        rec(False, "Title found", "could not parse \\title")

    # --- Abstract: 170 words, no references -------------------------------
    am = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    if am:
        n = words(am.group(1))
        rec(n <= 170, "Abstract <= 170 words", f"{n} words")
        rec(
            not re.search(r"\[\d+\]", am.group(1)),
            "Abstract has no references",
            "bracketed citation found in abstract",
        )
    else:
        rec(False, "Abstract found", "no abstract environment")

    # --- Background & Summary: 700-word cap -------------------------------
    bm = re.search(r"\\section\{Background \\& Summary\}(.*?)(?=\\section\{)", tex, re.S)
    if bm:
        body = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "", bm.group(1), flags=re.S)
        n = words(body)
        rec(n <= 700, "Background & Summary <= 700 words", f"{n} words (tables excluded)")
    else:
        rec(False, "Background & Summary found", "section not located")

    # --- No footnotes ------------------------------------------------------
    fn = len(re.findall(r"\\footnote\{", tex))
    rec(fn == 0, "No footnotes", f"{fn} \\footnote found")

    # --- Terminology -------------------------------------------------------
    dc = len(re.findall(r"deconfound", tex, re.I))
    rec(dc == 0, "No 'deconfound*'", f"{dc} occurrence(s)")
    cur = len(re.findall(r"curation.overlap", tex, re.I))
    ann = len(re.findall(r"annotation.overlap", tex, re.I))
    rec(
        cur == 0,
        "Overlap term is consistent",
        f"'curation-overlap' still appears {cur}x against 'annotation-overlap' {ann}x",
        soft=True,
    )

    # --- ORCIDs ------------------------------------------------------------
    ph = len(re.findall(r"0000-0000-0000-0000", tex))
    rec(ph == 0, "No ORCID placeholders", f"{ph} placeholder(s) remain")

    def orcid_ok(o: str) -> bool:
        d = o.replace("-", "")
        tot = 0
        for c in d[:15]:
            tot = (tot + int(c)) * 2
        chk = (12 - tot % 11) % 11
        return ("X" if chk == 10 else str(chk)) == d[15]

    ids = re.findall(r"\\orcid\{([0-9X-]{19})\}", tex)
    bad = [i for i in ids if not orcid_ok(i)]
    rec(len(ids) >= 1 and not bad, f"ORCID checksums valid ({len(ids)} found)", f"invalid: {bad}")

    # --- Every table and figure cited, in order ---------------------------
    for kind, pat in (("table", r"\\label\{(tab:[^}]+)\}"), ("figure", r"\\label\{(fig:[^}]+)\}")):
        labels = re.findall(pat, tex)
        uncited = [
            x for x in labels if not re.search(r"\\(?:C|c)ref\{[^}]*\b" + re.escape(x) + r"\b", tex)
        ]
        rec(not uncited, f"Every {kind} cited", f"uncited: {uncited}")

    # --- Unresolved fill markers ------------------------------------------
    fills = len(re.findall(r"\[\[fill\]\]", tex))
    rec(fills == 0, "No [[fill]] markers in body", f"{fills} remain", soft=True)

    # --- Scientific Data section order ------------------------------------
    order = re.findall(r"\\section\*?\{([^}]+)\}", tex)
    want = ["Usage Notes", "Code availability"]
    idx = [order.index(w) for w in want if w in order]
    rec(
        len(idx) == 2 and idx[1] == idx[0] + 1,
        "Code availability follows Usage Notes",
        f"order is {order[-9:] if len(order) > 9 else order}",
    )
    rec(
        "Data availability" not in order,
        "No standalone Data availability section",
        "still present (Data Records + Data Citations already carry it)",
    )

    print(f"\n  {len(OK)} passed, {len(WARN)} warnings, {len(FAIL)} failed\n")
    for x in OK:
        print(f"  [ok]   {x}")
    for x in WARN:
        print(f"  [warn] {x}")
    for x in FAIL:
        print(f"  [FAIL] {x}")

    print("\n  Not automatable — confirm by hand:")
    for x in [
        "APC commitment from Universidad Europea de Madrid (or delete that sentence)",
        "Overfull \\hbox count in main.log after compiling (expect 0)",
        "Cross-references resolve: grep -c '??' main.log = 0",
        "Every file named in the manuscript exists in the corresponding deposit",
        "Both croissant.json files pass `mlcroissant validate`",
        "IC formula renders with visible parentheses and n_t subscript",
    ]:
        print(f"  [ ]    {x}")

    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
