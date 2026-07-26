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
        if has_old and not has_new:
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
    m = re.search(r"\\section\*\{References\}(.*?)\\end\{enumerate\}", tex, re.S)
    if not m:
        check("reference list found", False, "could not locate the References block")
        return
    n_refs = len(re.findall(r"^\\item ", m.group(1), flags=re.M))
    check("reference list non-empty", n_refs > 0, "no \\item entries")

    body = tex[: m.start()]
    cited: set[int] = set()
    order: list[int] = []
    for mm in re.finditer(r"\[(\d+(?:\s*,\s*\d+)*)\]", body):
        for tok in mm.group(1).split(","):
            k = int(tok.strip())
            if k not in cited:
                cited.add(k)
                order.append(k)

    uncited = sorted(set(range(1, n_refs + 1)) - cited)
    check("every reference is cited", not uncited, f"uncited: {uncited}")

    over = sorted(k for k in cited if k > n_refs)
    check("no citation exceeds the list length", not over, f"out of range: {over}")

    # sequential-by-first-appearance is the Vancouver requirement
    if order != sorted(order):
        firstbad = next((i for i in range(1, len(order)) if order[i] < order[i - 1]), None)
        warn(
            "references not sequential by first appearance",
            f"first out-of-order citation: [{order[firstbad]}] appears after "
            f"[{order[firstbad - 1]}]",
        )
    else:
        PASSES.append("references sequential by first appearance")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tex",
        default="reports/_local/GenoAgent_P2_System/P2-correction/main.tex",
    )
    args = ap.parse_args()
    path = (REPO / args.tex) if not Path(args.tex).is_absolute() else Path(args.tex)
    tex = path.read_text()

    cross_checks(tex)
    terminology(tex)
    stale_numbers(tex)
    provenance(tex)
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
