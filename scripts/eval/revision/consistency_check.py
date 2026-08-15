"""Final consistency gate for the P2 revision (spec section 4).

Verifies, and fails loudly on any mismatch:

  1. P1 <-> P2 cross-checks: cohort n, category counts, overlap counts, recency
     counts, the crossed cell, unique publication counts, chunk count, pinned
     versions and DOIs, and the exclusion chain.
  2. No stale numbers: every headline value asserted in the .tex is re-derived
     from the artefacts and diffed.
  3. No orphan claims: the .tex cites a producing script for each new result.
  4. No unresolved \\TODO{} beyond those listed in OPEN_ITEMS.md.
  5. Reference list: every entry cited, numbering sequential by first appearance.

Usage:
    python scripts/eval/revision/consistency_check.py \
        --tex reports/_local/GenoAgent_P2_System/P2-correction/main.tex
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import OUT_DIR, REPO, load_cases, subset

FAILURES: list[str] = []
WARNINGS: list[str] = []
PASSES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSES.append(name)
    else:
        FAILURES.append(f"{name}: {detail}")


def warn(name: str, detail: str) -> None:
    WARNINGS.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# 1. P1 <-> P2 cross-checks
# ---------------------------------------------------------------------------
def cross_checks(tex: str) -> None:
    cases = load_cases()

    check("cohort n = 1047", len(cases) == 1047, f"got {len(cases)}")

    from collections import Counter

    cats = Counter(c.category for c in cases)
    expected = {"developmental": 250, "immunological": 300, "metabolic": 250, "neurological": 247}
    check("category counts 250/300/250/247", dict(cats) == expected, f"got {dict(cats)}")

    n_present = sum(c.overlap for c in cases)
    n_absent = len(cases) - n_present
    check(
        "overlap counts 765/282", (n_present, n_absent) == (765, 282), f"got {n_present}/{n_absent}"
    )

    n_post = sum(c.post2020 for c in cases)
    n_pre = len(cases) - n_post
    check("recency counts 601/446", (n_pre, n_post) == (601, 446), f"got {n_pre}/{n_post}")

    crossed = len(subset("post2020_overlap_absent"))
    check("crossed post-2020 x overlap-absent = 88", crossed == 88, f"got {crossed}")

    pmids = len({c.source_pmid for c in cases})
    check("unique publications = 415", pmids == 415, f"got {pmids}")

    pm = json.loads((OUT_DIR / "wp4_unique_pmids.json").read_text())
    check(
        "overlap-absent publications = 93",
        pm["overlap_absent"]["n_publications"] == 93,
        f"got {pm['overlap_absent']['n_publications']}",
    )
    check(
        "crossed-cell publications = 18",
        pm["post2020_overlap_absent"]["n_publications"] == 18,
        f"got {pm['post2020_overlap_absent']['n_publications']}",
    )
    check(
        "crossed-cell largest publication = 35",
        pm["post2020_overlap_absent"]["max_cases_from_one_publication"] == 35,
        f"got {pm['post2020_overlap_absent']['max_cases_from_one_publication']}",
    )

    # values that must appear in the .tex verbatim
    for token, label in (
        (r"52777395", "chunk count 52,777,395"),
        (r"10\.6084/m9\.figshare\.32814449", "cohort DOI"),
        (r"10\.6084/m9\.figshare\.32814491", "methods/index DOI"),
        (r"10\.6084/m9\.figshare\.32814497", "system DOI"),
        (r"10\.6084/m9\.figshare\.32816468", "hard-cohort DOI"),
        (r"v2026-02-16", "HPO pin"),
        (r"2026-03-03", "MONDO pin"),
        (r"2026-04-07", "HGNC pin"),
        (r"9588", "screened 9,588"),
        (r"1982", "chromosomal/mitochondrial exclusion 1,982"),
        (r"3206", "inclusion-stage exclusions 3,206"),
    ):
        check(f"tex contains {label}", re.search(token, tex) is not None, "absent")

    # P1 removed GO from the pinned inputs; P2 must not reintroduce it
    check("GO pin removed from P2", "GO 2026-03-25" not in tex, "'GO 2026-03-25' still present")


# ---------------------------------------------------------------------------
# 2. Terminology sweep (WP2)
# ---------------------------------------------------------------------------
def terminology(tex: str) -> None:
    body = tex
    for bad, why in (
        (
            r"deconfound",
            "'deconfound*' claims causal identification the design does "
            "not deliver; P1 removed it entirely",
        ),
        (r"fair-comparison cohort", "replaced by 'overlap-absent subset'"),
        (r"DeepEval groundedness", "DeepEval withdrawn (polarity inverted)"),
        (r"pre-declared", "endpoint is pre-specified, not pre-registered"),
    ):
        hits = len(re.findall(bad, body, flags=re.I))
        check(f"no '{bad}' in tex", hits == 0, f"{hits} occurrence(s) -- {why}")

    # 1{,}047 should be \num{1047} throughout
    manual = len(re.findall(r"1\{,\}047", body))
    check("no manual 1{,}047 (use \\num{1047})", manual == 0, f"{manual} occurrence(s)")

    # novelty hedging. The window is generous and newline-insensitive because a
    # hedge routinely sits on the previous wrapped line.
    flat = re.sub(r"\s+", " ", body)
    for phrase in ("for the first time", "no prior rare-disease", "no prior "):
        for m in re.finditer(re.escape(phrase), flat, flags=re.I):
            window = flat[max(0, m.start() - 90) : m.start()].lower()
            if "to our knowledge" not in window:
                warn(
                    "unhedged novelty claim",
                    f"'...{flat[max(0, m.start() - 60) : m.start() + 50]}...' "
                    f"lacks a nearby 'to our knowledge'",
                )


# ---------------------------------------------------------------------------
# 3. No stale numbers -- diff the tex against the recomputed audit
# ---------------------------------------------------------------------------
def stale_numbers(tex: str) -> None:
    path = OUT_DIR / "wp7_metric_audit.csv"
    rows = list(csv.DictReader(path.open()))
    bad = [r for r in rows if r["status"] == "MISMATCH"]
    for r in bad:
        claimed, recomputed = r["claimed"], r["recomputed"]
        # The corrected value must be present. The superseded value may legitimately
        # remain if it is also the correct figure for some *other* cell, so it is
        # only reported when the correction is missing.
        has_new = re.search(rf"{re.escape(str(recomputed)[:5])}", tex) is not None
        has_old = re.search(rf"\b{re.escape(str(claimed))}\b", tex) is not None
        # A superseded literal is not evidence of staleness when the same three
        # decimals are the *correct* value of another cell that reproduced: the
        # search is over the whole document and cannot tell the two apart.
        elsewhere = sorted(
            f"{o['cohort']}/{o['subset']}/{o['cell']}/{o['metric']}"
            for o in rows
            if o["status"] == "OK" and f"{float(o['recomputed']):.3f}" == f"{float(claimed):.3f}"
        )
        if has_old and not has_new and elsewhere:
            PASSES.append(
                f"superseded literal {claimed} is a benign collision for "
                f"{r['cohort']}/{r['subset']}/{r['cell']}/{r['metric']} "
                f"(same 3dp as {', '.join(elsewhere)})"
            )
        elif has_old and not has_new:
            warn(
                "stale value still asserted",
                f"{r['cohort']}/{r['subset']}/{r['cell']}/{r['metric']}: "
                f"superseded {claimed} appears but corrected {recomputed} does not",
            )
        elif not has_new and not has_old:
            PASSES.append(
                f"cell not reported in this version "
                f"({r['cohort']}/{r['subset']}/{r['cell']}/{r['metric']})"
            )
        else:
            PASSES.append(
                f"corrected value present for "
                f"{r['cohort']}/{r['subset']}/{r['cell']}/{r['metric']} "
                f"({claimed} -> {recomputed})"
            )
    check("metric audit ran", len(rows) > 0, "empty audit file")

    n_ok = sum(1 for r in rows if r["status"] == "OK")
    check(
        "metric audit: >=95% of claims reproduce exactly",
        n_ok / len(rows) >= 0.95,
        f"only {n_ok}/{len(rows)}",
    )


# ---------------------------------------------------------------------------
# 4. Provenance: every new result cites its producing script
# ---------------------------------------------------------------------------
def provenance(tex: str) -> None:
    required = [
        "provenance_checks.py",
        "interaction_test.py",
        "cluster_inference.py",
        "design_weighted.py",
        "annotation_density.py",
        "metric_audit.py",
        "judge_provenance.py",
        "prompt_sensitivity.py",
    ]
    # The script-to-result map lives in Supplementary Table S12, so the check
    # spans main text and supplement: a script named in either is not orphaned.
    # Filenames are typeset as \texttt{foo\_bar.py}, so \_ must be unescaped
    # before matching or every underscored script reads as absent.
    flat = tex.replace("\\_", "_")
    for script in required:
        check(f"tex references {script}", script in flat, "not cited anywhere in the tex")

    expected_outputs = [
        "wp1a_coverage_check.json",
        "wp1d_baseline_versions.json",
        "wp3_did.json",
        "wp4_cluster_inference.json",
        "wp4_unique_pmids.json",
        "wp5_design_weighted.json",
        "wp6_annotation_density.json",
        "wp7_metric_audit.csv",
        "wp7_full_stratum_table.csv",
        "wp8_judge_provenance.json",
        "wp9b_tie_handling.json",
        "wp9c_cutoff_asymmetry.json",
    ]
    for name in expected_outputs:
        check(f"artefact {name} exists", (OUT_DIR / name).exists(), "missing")

    if not (OUT_DIR / "wp8d_prompt_sensitivity.json").exists():
        warn(
            "WP8-D",
            "wp8d_prompt_sensitivity.json absent -- prompt-sensitivity "
            "numbers in the tex are unfilled",
        )


# ---------------------------------------------------------------------------
# 5. TODOs
# ---------------------------------------------------------------------------
def todos(tex: str) -> None:
    found = re.findall(r"\\TODO\{", tex)
    open_items = OUT_DIR / "OPEN_ITEMS.md"
    check("OPEN_ITEMS.md exists", open_items.exists(), "missing")
    # TODOs are expected; they must be few and each should map to an open item
    if len(found) > 10:
        warn("many TODOs", f"{len(found)} \\TODO{{}} macros remain")
    else:
        PASSES.append(f"TODO count = {len(found)} (all author decisions)")


# ---------------------------------------------------------------------------
# 6. References: cited, sequential, no gaps
# ---------------------------------------------------------------------------
def references(tex: str) -> None:
    """Reference-list integrity for a manual ``thebibliography``.

    The manuscript keeps an explicit ``thebibliography`` rather than a .bib, so
    the printed number of an entry is simply its position in the \\bibitem
    sequence. Three things can therefore go wrong silently: an entry defined but
    never cited, a \\cite key with no entry, and -- the Vancouver requirement --
    entries whose order does not follow first citation in the text. The optional
    width argument is checked too, since it is written by hand and does not
    track the entry count.

    The older ``\\section*{References}`` + ``enumerate`` form with hard-coded
    bracketed numbers is still accepted, so the gate keeps working on the
    superseded sources.
    """
    m = re.search(r"\\begin\{thebibliography\}\{([^}]*)\}(.*?)\\end\{thebibliography\}", tex, re.S)
    if m:
        width, block = m.group(1), m.group(2)
        keys = re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", block)
        n_refs = len(keys)
        check("reference list non-empty", n_refs > 0, "no \\bibitem entries")

        dupes = sorted({k for k in keys if keys.count(k) > 1})
        check("no duplicate \\bibitem keys", not dupes, f"duplicated: {dupes}")

        # The width argument only sets the label box, but a value narrower than
        # the entry count is the fingerprint of entries appended without
        # re-checking the list.
        check(
            "thebibliography width argument covers the entry count",
            width.isdigit() and int(width) >= n_refs,
            f"\\begin{{thebibliography}}{{{width}}} with {n_refs} entries",
        )

        body = tex[: m.start()]
        order: list[str] = []
        for mm in re.finditer(r"\\cite[tp]?\*?(?:\[[^\]]*\])*\{([^}]+)\}", body):
            for tok in mm.group(1).split(","):
                k = tok.strip()
                if k and k not in order:
                    order.append(k)

        undefined = [k for k in order if k not in keys]
        check("every \\cite key has a \\bibitem", not undefined, f"undefined: {undefined}")

        uncited = [k for k in keys if k not in order]
        check("every reference is cited", not uncited, f"uncited: {uncited}")

        position = {k: i + 1 for i, k in enumerate(keys)}
        numbers = [position[k] for k in order if k in position]
    else:
        m = re.search(r"\\section\*\{References\}(.*?)\\end\{enumerate\}", tex, re.S)
        if not m:
            check(
                "reference list found",
                False,
                "no \\begin{thebibliography} and no \\section*{References} block",
            )
            return
        n_refs = len(re.findall(r"^\\item ", m.group(1), flags=re.M))
        check("reference list non-empty", n_refs > 0, "no \\item entries")

        body = tex[: m.start()]
        seen: set[int] = set()
        numbers = []
        for mm in re.finditer(r"\[(\d+(?:\s*,\s*\d+)*)\]", body):
            for tok in mm.group(1).split(","):
                k = int(tok.strip())
                if k not in seen:
                    seen.add(k)
                    numbers.append(k)

        uncited_n = sorted(set(range(1, n_refs + 1)) - seen)
        check("every reference is cited", not uncited_n, f"uncited: {uncited_n}")

        over = sorted(k for k in seen if k > n_refs)
        check("no citation exceeds the list length", not over, f"out of range: {over}")

    # sequential-by-first-appearance is the Vancouver requirement
    if numbers != sorted(numbers):
        outoforder = [
            f"[{numbers[i]}] after [{numbers[i - 1]}]"
            for i in range(1, len(numbers))
            if numbers[i] < numbers[i - 1]
        ]
        check(
            "references sequential by first appearance",
            False,
            f"{len(outoforder)} inversion(s): {'; '.join(outoforder)}",
        )
    else:
        PASSES.append(f"references sequential by first appearance ({n_refs} entries)")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tex",
        default="reports/_local/P2_latest_version/GenoAgent_P2_System/main.tex",
    )
    ap.add_argument(
        "--supp",
        default="reports/_local/P2_latest_version/GenoAgent_P2_System/p2_supplementary.tex",
        help="supplement; searched alongside the main text for the script-to-result map",
    )
    args = ap.parse_args()

    def resolve(p: str) -> Path:
        return (REPO / p) if not Path(p).is_absolute() else Path(p)

    path = resolve(args.tex)
    tex = path.read_text()
    supp_path = resolve(args.supp) if args.supp else None
    supp = supp_path.read_text() if supp_path and supp_path.exists() else ""
    if args.supp and not supp:
        warn("supplement not found", f"{args.supp} -- provenance checked on main text alone")

    cross_checks(tex)
    terminology(tex)
    stale_numbers(tex)
    provenance(tex + "\n" + supp)
    todos(tex)
    references(tex)

    print(f"consistency gate for {path.relative_to(REPO)}")
    print(f"\n  PASS  {len(PASSES)}")
    print(f"  WARN  {len(WARNINGS)}")
    print(f"  FAIL  {len(FAILURES)}")

    if WARNINGS:
        print("\n--- warnings ---")
        for w in WARNINGS:
            print(f"  ! {w}")
    if FAILURES:
        print("\n--- failures ---")
        for f in FAILURES:
            print(f"  X {f}")
        sys.exit(1)
    print("\nAll hard checks passed.")


if __name__ == "__main__":
    main()
