"""Structural checks on the manuscript .tex without compiling it.

The manuscript is compiled in Overleaf, so this performs the checks a local
pdflatex run would otherwise catch: balanced environments and braces, every
\\includegraphics target present on disk, every \\Cref/\\ref resolving to a
declared \\label, no duplicate labels, and no unresolved \\input targets.

Usage:
    python scripts/eval/revision/latex_lint.py --tex path/to/main.tex
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROBLEMS: list[str] = []
NOTES: list[str] = []


def strip_comments(tex: str) -> str:
    """Drop % comments, honouring \\% escapes."""
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


def check_environments(tex: str) -> None:
    stack: list[tuple[str, int]] = []
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", tex):
        kind, name = m.group(1), m.group(2)
        line = tex[: m.start()].count("\n") + 1
        if kind == "begin":
            stack.append((name, line))
        else:
            if not stack:
                PROBLEMS.append(f"line {line}: \\end{{{name}}} with no matching \\begin")
            elif stack[-1][0] != name:
                PROBLEMS.append(
                    f"line {line}: \\end{{{name}}} closes \\begin{{{stack[-1][0]}}} "
                    f"opened at line {stack[-1][1]}"
                )
                stack.pop()
            else:
                stack.pop()
    for name, line in stack:
        PROBLEMS.append(f"line {line}: \\begin{{{name}}} never closed")
    if not PROBLEMS:
        NOTES.append("all environments balanced")


def check_braces(tex: str) -> None:
    depth, esc = 0, False
    line = 1
    for ch in tex:
        if ch == "\n":
            line += 1
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                PROBLEMS.append(f"line {line}: unmatched closing brace")
                depth = 0
    if depth:
        PROBLEMS.append(f"{depth} unclosed brace(s) at end of document")
    else:
        NOTES.append("braces balanced")


def check_graphics(tex: str, root: Path) -> None:
    """Resolve \\includegraphics against \\graphicspath, as LaTeX itself does."""
    search = [root]
    for gm in re.finditer(r"\\graphicspath\{(.+?)\}\s*$", tex, re.M):
        search += [root / d for d in re.findall(r"\{([^}]*)\}", gm.group(1)) if d]

    for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex):
        target = m.group(1)
        line = tex[: m.start()].count("\n") + 1
        candidates = [d / target for d in search]
        if not Path(target).suffix:
            candidates += [d / f"{target}{ext}" for d in search for ext in (".png", ".pdf", ".jpg")]
        if not any(c.exists() for c in candidates):
            PROBLEMS.append(f"line {line}: missing figure file '{target}'")
    NOTES.append("graphics targets checked")


def check_inputs(tex: str, root: Path) -> None:
    for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", tex):
        target = m.group(1)
        line = tex[: m.start()].count("\n") + 1
        cands = [root / target, root / f"{target}.tex"]
        if not any(c.exists() for c in cands):
            PROBLEMS.append(f"line {line}: missing \\input target '{target}'")
    NOTES.append("input targets checked")


def check_labels(tex: str, root: Path | None = None) -> None:
    """Labels may be defined inside \\input files, so those are pulled in first."""
    if root is not None:
        for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", tex):
            for cand in (root / m.group(1), root / f"{m.group(1)}.tex"):
                if cand.exists():
                    tex += "\n" + strip_comments(cand.read_text())
                    break

    labels: dict[str, int] = {}
    for m in re.finditer(r"\\label\{([^}]+)\}", tex):
        line = tex[: m.start()].count("\n") + 1
        if m.group(1) in labels:
            PROBLEMS.append(
                f"line {line}: duplicate \\label{{{m.group(1)}}} "
                f"(first at line {labels[m.group(1)]})"
            )
        else:
            labels[m.group(1)] = line

    refs: set[str] = set()
    for m in re.finditer(r"\\(?:Cref|cref|ref|autoref|pageref)\{([^}]+)\}", tex):
        for key in m.group(1).split(","):
            refs.add(key.strip())

    dangling = sorted(r for r in refs if r and r not in labels)
    for d in dangling:
        PROBLEMS.append(f"reference to undefined label '{d}'")

    unused = sorted(k for k in labels if k not in refs)
    if unused:
        NOTES.append(f"labels defined but never referenced: {', '.join(unused)}")
    NOTES.append(f"{len(labels)} labels, {len(refs)} distinct references")


def check_undefined_macros(tex: str) -> None:
    """Catch \\FOO{} style macros used but never \\newcommand-ed in this file."""
    defined = set(re.findall(r"\\newcommand\{?\\([A-Za-z]+)", tex))
    defined |= set(re.findall(r"\\renewcommand\{?\\([A-Za-z]+)", tex))
    # only flag all-caps custom macros, which is the convention used here
    used = set(re.findall(r"\\([A-Z]{4,})\{\}", tex))
    for name in sorted(used - defined):
        NOTES.append(
            f"macro \\{name} used but not defined in this file "
            f"(expected from an \\input); verify it resolves"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", required=True)
    args = ap.parse_args()
    path = Path(args.tex)
    raw = path.read_text()
    tex = strip_comments(raw)
    root = path.parent

    check_environments(tex)
    check_braces(tex)
    check_graphics(tex, root)
    check_inputs(tex, root)
    check_labels(tex, root)
    check_undefined_macros(raw)

    words = len(re.findall(r"\b[A-Za-z][A-Za-z'-]+\b", tex))
    NOTES.append(f"~{words} words including tables, captions and references")

    print(f"latex structural lint: {path}")
    for n in NOTES:
        print(f"  . {n}")
    if PROBLEMS:
        print(f"\n  {len(PROBLEMS)} problem(s):")
        for p in PROBLEMS:
            print(f"  X {p}")
        sys.exit(1)
    print("\n  no structural problems found")


if __name__ == "__main__":
    main()
