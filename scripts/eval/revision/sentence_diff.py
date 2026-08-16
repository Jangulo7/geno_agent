"""Sentence-level diff between the submitted P2 manuscript and the current one.

Line-based diff is useless here because most of the file has been re-wrapped. This
normalises whitespace, splits into sentences (and keeps LaTeX structure lines whole),
aligns the two documents, and prints only what actually changed -- with a word-level
marking of the change inside each altered sentence.

The bibliography is handled separately: its entries were reordered wholesale, which
would otherwise swamp the output with 36 spurious moves.
"""

from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

OLD = Path(sys.argv[1])
NEW = Path(sys.argv[2])
OUT = Path(sys.argv[3])

ABBREV = r"(?<!\bvs)(?<!\bcf)(?<!\be\.g)(?<!\bi\.e)(?<!\bal)(?<!\bFig)(?<!\bEq)(?<!\bSec)(?<!\bNo)(?<!\bapprox)(?<!\bDr)(?<!\betc)(?<!\bResp)(?<!\bv)"


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


def split_bibliography(tex: str) -> tuple[str, str]:
    m = re.search(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", tex, re.S)
    if not m:
        return tex, ""
    return tex[: m.start()] + "\n<<BIBLIOGRAPHY>>\n" + tex[m.end() :], m.group(0)


STRUCTURAL = re.compile(
    r"^\s*\\(section|subsection|subsubsection|paragraph|title|author|caption|label|"
    r"begin|end|item|bibitem|includegraphics|input|newcommand|setlength|"
    r"toprule|midrule|bottomrule|cmidrule|multicolumn)"
)


def segment(tex: str) -> list[str]:
    """Split into comparable units: structure lines and table rows stay whole,
    prose is split into sentences."""
    units: list[str] = []
    for block in re.split(r"\n\s*\n", tex):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            # table rows and structural commands are their own unit
            if line.endswith("\\\\") or STRUCTURAL.match(line):
                units.append(re.sub(r"\s+", " ", line))
            else:
                units.append("\x00" + re.sub(r"\s+", " ", line))
    # re-join consecutive prose fragments (they were wrapped lines), then sentence-split
    merged: list[str] = []
    buf: list[str] = []
    for u in units:
        if u.startswith("\x00"):
            buf.append(u[1:])
        else:
            if buf:
                merged.extend(sentences(" ".join(buf)))
                buf = []
            merged.append(u)
    if buf:
        merged.extend(sentences(" ".join(buf)))
    return [m for m in merged if m.strip()]


def sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(rf"(?<=[.!?])(?<!\d\.){ABBREV}\s+(?=[A-Z\\(])", text)
    return [p.strip() for p in parts if p.strip()]


def worddiff(a: str, b: str) -> str:
    aw, bw = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, aw, bw, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(" ".join(aw[i1:i2]))
        elif tag == "delete":
            out.append("[-" + " ".join(aw[i1:i2]) + "-]")
        elif tag == "insert":
            out.append("{+" + " ".join(bw[j1:j2]) + "+}")
        else:
            out.append("[-" + " ".join(aw[i1:i2]) + "-]{+" + " ".join(bw[j1:j2]) + "+}")
    return " ".join(out)


def heading_of(units: list[str], idx: int) -> str:
    for k in range(idx, -1, -1):
        m = re.match(r"\\(section|subsection|subsubsection)\*?\{(.+?)\}", units[k])
        if m:
            return m.group(2)
    return "(front matter)"


old_raw, new_raw = strip_comments(OLD.read_text()), strip_comments(NEW.read_text())
old_body, old_bib = split_bibliography(old_raw)
new_body, new_bib = split_bibliography(new_raw)
A, B = segment(old_body), segment(new_body)

sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
changes = []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal":
        continue
    changes.append(
        (tag, A[i1:i2], B[j1:j2], heading_of(B, j1) if j1 < len(B) else heading_of(A, i1))
    )

# pair up replacements sentence-by-sentence where the counts allow a sensible match
lines = []
n_mod = n_add = n_del = 0
for tag, olds, news, head in changes:
    if tag == "replace":
        # Pair each old sentence with its closest surviving rewrite, in order.
        # Anything below the similarity floor is a genuine insertion/deletion.
        FLOOR = 0.45
        remaining = list(news)
        used = set()
        for a in olds:
            best, best_r = None, FLOOR
            for k, b in enumerate(remaining):
                if k in used:
                    continue
                r = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
                if r > best_r:
                    best, best_r = k, r
            if best is None:
                lines.append(("del", head, a, ""))
                n_del += 1
            else:
                used.add(best)
                lines.append(("mod", head, a, remaining[best]))
                n_mod += 1
        for k, b in enumerate(remaining):
            if k not in used:
                lines.append(("add", head, "", b))
                n_add += 1
    elif tag == "delete":
        for a in olds:
            lines.append(("del", head, a, ""))
            n_del += 1
    elif tag == "insert":
        for b in news:
            lines.append(("add", head, "", b))
            n_add += 1

with OUT.open("w") as fh:
    fh.write("# What changed between the submitted manuscript and the current one\n\n")
    fh.write(f"- **Sent for feedback:** `{OLD.name}` ({len(A)} sentences/structure lines)\n")
    fh.write(f"- **Current:** `{NEW.name}` ({len(B)} sentences/structure lines)\n\n")
    fh.write(
        f"**{n_mod} rewritten, {n_add} added, {n_del} removed.** "
        "Comments and line re-wrapping are ignored; only real text changes appear.\n\n"
        "In the word diff, `[-...-]` is text that was removed and `{+...+}` text that "
        "was added.\n\n"
    )
    if old_bib and new_bib:
        oldkeys = re.findall(r"\\bibitem\{([^}]+)\}", old_bib)
        newkeys = re.findall(r"\\bibitem\{([^}]+)\}", new_bib)
        same = {k: old_bib.split(k, 1)[1][:200] for k in oldkeys}
        fh.write("## Bibliography\n\n")
        fh.write(
            f"Handled separately: {len(oldkeys)} entries before, {len(newkeys)} after. "
            f"{'Same entries, reordered.' if sorted(oldkeys) == sorted(newkeys) else 'ENTRY SET CHANGED.'} "
            "See the I5 section of `P2_verification_and_changes.md`.\n\n"
        )
    current = None
    for kind, head, a, b in lines:
        if head != current:
            fh.write(f"\n## {head}\n\n")
            current = head
        if kind == "mod":
            fh.write("**Changed**\n\n")
            fh.write(f"- *Sent:* {a}\n")
            fh.write(f"- *Now:* {b}\n")
            fh.write(f"- *Diff:* `{worddiff(a, b)}`\n\n")
        elif kind == "add":
            fh.write(f"**Added** — {b}\n\n")
        else:
            fh.write(f"**Removed** — {a}\n\n")

print(f"{n_mod} modified, {n_add} added, {n_del} removed -> {OUT}")
