"""Renumber a Vancouver-style reference list to first-appearance order.

Elsevier's numbered style requires references to be numbered in the order of
first citation in the text. Editing a manuscript almost always breaks that
ordering, and removing a reference silently shifts every later number.

This rewrites both the in-text ``[n]`` / ``[n,m]`` citations and the reference
list itself so that the two agree and the ordering is correct. It is
idempotent: running it on an already-correct file changes nothing.

Usage:
    python scripts/eval/revision/renumber_references.py --tex path/to/main.tex
    python scripts/eval/revision/renumber_references.py --tex path/to/main.tex --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CITE = re.compile("\\[(\\d+(?:\\s*[,\u2013-]\\s*\\d+)*)\\]")


def split_document(tex: str) -> tuple[str, str, str, list[str]]:
    """Return (head, refs_open, tail, items) around the References enumerate."""
    m = re.search(
        r"(\\section\*\{References\}.*?\\begin\{enumerate\}[^\n]*\n)(.*?)(\\end\{enumerate\})",
        tex,
        re.S,
    )
    if not m:
        raise SystemExit("could not locate the References enumerate block")
    body = m.group(2)
    # split on \item at line start, keeping the text that follows each
    parts = re.split(r"(?m)^\\item\s", body)
    preamble = parts[0]
    items = [p.rstrip() for p in parts[1:]]
    if preamble.strip():
        raise SystemExit("unexpected text before the first \\item in the reference list")
    # tail starts AT \end{enumerate} so the environment is preserved
    return tex[: m.start()], m.group(1), tex[m.start(3) :], items


def parse_citation(token: str) -> list[int]:
    """'14,15' -> [14, 15]; ranges are expanded."""
    out: list[int] = []
    for chunk in token.split(","):
        chunk = chunk.strip()
        rng = re.match("^(\\d+)\\s*[\u2013-]\\s*(\\d+)$", chunk)
        if rng:
            out.extend(range(int(rng.group(1)), int(rng.group(2)) + 1))
        elif chunk.isdigit():
            out.append(int(chunk))
    return out


def first_appearance_order(head: str, n_items: int) -> list[int]:
    """Old indices in order of first citation in the body text."""
    seen: set[int] = set()
    order: list[int] = []
    for m in CITE.finditer(head):
        for k in parse_citation(m.group(1)):
            if 1 <= k <= n_items and k not in seen:
                seen.add(k)
                order.append(k)
    return order


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", required=True)
    ap.add_argument("--check", action="store_true", help="report only; do not modify the file")
    args = ap.parse_args()

    path = Path(args.tex)
    tex = path.read_text()
    head, refs_open, tail, items = split_document(tex)
    n = len(items)

    order = first_appearance_order(head, n)
    uncited = sorted(set(range(1, n + 1)) - set(order))

    print(f"{n} reference entries; {len(order)} cited; {len(uncited)} uncited")
    if uncited:
        print("  uncited entries (will be dropped if you renumber):")
        for k in uncited:
            print(f"    [{k}] {items[k - 1][:78]}...")

    over = sorted({k for m in CITE.finditer(head) for k in parse_citation(m.group(1)) if k > n})
    if over:
        print(f"  ERROR: citations beyond the list length: {over}")
        sys.exit(1)

    already = order == sorted(order) and not uncited
    if already:
        print("  already sequential by first appearance and fully cited -- no change")
        return
    if args.check:
        print("  NOT sequential by first appearance (run without --check to fix)")
        sys.exit(1)

    # old index -> new index
    mapping = {old: i + 1 for i, old in enumerate(order)}
    # keep uncited entries at the end rather than silently deleting them
    for k in uncited:
        mapping[k] = len(mapping) + 1

    def rewrite(m: re.Match) -> str:
        ks = parse_citation(m.group(1))
        if not ks or any(k not in mapping for k in ks):
            return m.group(0)
        return "[" + ",".join(str(mapping[k]) for k in ks) + "]"

    new_head = CITE.sub(rewrite, head)

    new_items = [""] * len(mapping)
    for old, new in mapping.items():
        new_items[new - 1] = items[old - 1]

    new_body = "".join(f"\\item {it}\n" for it in new_items)
    path.write_text(new_head + refs_open + new_body + tail)

    moved = sum(1 for old, new in mapping.items() if old != new)
    print(f"  renumbered: {moved} of {n} entries changed position")
    if uncited:
        print(f"  {len(uncited)} uncited entries were moved to the end -- cite or delete them")


if __name__ == "__main__":
    main()
