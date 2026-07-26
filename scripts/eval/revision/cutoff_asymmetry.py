"""WP9-C --- quantify the knowledge-cutoff asymmetry between the two tool classes.

The curated baselines consume ``phenotype.hpoa`` v2026-02-16. GenoAgent retrieves
from a PMC OA snapshot that runs to 2026-05, a roughly three-month information
advantage. Whether that advantage is doing any work is an empirical question: it
matters only if articles published after the annotation pin are actually being
retrieved for cohort cases.

This resolves the publication date of every distinct PMC article that appears in
any case's retrieved evidence (from the cached ``cell_S_responses`` payloads) via
NCBI E-utilities, and reports how many postdate the pin, both by article and
weighted by how often each article is actually retrieved.

Outputs ``reports/p2_revision/wp9c_cutoff_asymmetry.json``.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import EVAL_STD, OUT_DIR, load_cases, write_json

PIN = "2026-02-16"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
BATCH = 200
CACHE = OUT_DIR / "wp9c_pmcid_dates.json"


def collect_retrievals() -> tuple[Counter, dict[str, set[str]]]:
    """PMCID -> number of retrieved chunks, and PMCID -> set of case_ids."""
    counts: Counter = Counter()
    by_case: dict[str, set[str]] = {}
    for case in load_cases():
        path = EVAL_STD / "cell_S_responses" / f"{case.case_id}.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        for chunks in doc.get("retrieved_per_gene", {}).values():
            for ch in chunks:
                pmc = ch.get("source_pmcid")
                if not pmc:
                    continue
                counts[pmc] += 1
                by_case.setdefault(pmc, set()).add(case.case_id)
    return counts, by_case


def fetch_dates(pmcids: list[str]) -> dict[str, str]:
    """PMCID -> publication date string, via esummary (db=pmc)."""
    cached: dict[str, str] = {}
    if CACHE.exists():
        cached = json.loads(CACHE.read_text())

    todo = [p for p in pmcids if p not in cached]
    print(f"{len(cached)} dates cached, {len(todo)} to fetch")

    for i in range(0, len(todo), BATCH):
        chunk = todo[i : i + BATCH]
        ids = ",".join(c.removeprefix("PMC") for c in chunk)
        try:
            r = requests.get(
                ESUMMARY,
                params={"db": "pmc", "id": ids, "retmode": "json"},
                timeout=60,
            )
            r.raise_for_status()
            res = r.json().get("result", {})
            for uid in res.get("uids", []):
                rec = res.get(uid, {})
                date = rec.get("epubdate") or rec.get("pubdate") or rec.get("sortdate") or ""
                cached[f"PMC{uid}"] = date
        except Exception as exc:
            print(f"  batch {i // BATCH}: {type(exc).__name__}: {exc}")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cached, indent=0))
        if (i // BATCH) % 10 == 0:
            print(f"  fetched {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
        time.sleep(0.4)  # NCBI courtesy rate limit
    return cached


def normalise(date: str) -> str | None:
    """'2019 Apr 10' / '2019-04-10' / '2019 Apr' -> ISO-ish 'YYYY-MM-DD'."""
    if not date:
        return None
    d = date.strip().replace("/", "-")
    months = {
        m: f"{i:02d}"
        for i, m in enumerate(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            start=1,
        )
    }
    parts = d.replace("-", " ").split()
    if not parts or not parts[0].isdigit():
        return None
    year = parts[0]
    month = "01"
    day = "01"
    if len(parts) > 1:
        month = months.get(parts[1][:3].title(), parts[1] if parts[1].isdigit() else "01")
        month = f"{int(month):02d}" if str(month).isdigit() else "01"
    if len(parts) > 2 and parts[2].isdigit():
        day = f"{int(parts[2]):02d}"
    return f"{year}-{month}-{day}"


def main() -> None:
    counts, by_case = collect_retrievals()
    pmcids = sorted(counts)
    print(f"{len(pmcids)} distinct PMC articles retrieved across the cohort")

    dates = fetch_dates(pmcids)

    resolved, unresolved = {}, []
    for p in pmcids:
        iso = normalise(dates.get(p, ""))
        if iso:
            resolved[p] = iso
        else:
            unresolved.append(p)

    after = {p: d for p, d in resolved.items() if d > PIN}
    chunks_after = sum(counts[p] for p in after)
    chunks_total = sum(counts.values())
    cases_touched = set()
    for p in after:
        cases_touched |= by_case.get(p, set())

    by_year = Counter(d[:4] for d in resolved.values())

    payload = {
        "work_package": "WP9-C",
        "description": (
            "Do articles postdating the curated tools' annotation release actually "
            "reach GenoAgent's retrieved evidence for cohort cases?"
        ),
        "annotation_pin": PIN,
        "index_snapshot": "PMC OA to 2026-05",
        "n_distinct_articles_retrieved": len(pmcids),
        "n_dates_resolved": len(resolved),
        "n_dates_unresolved": len(unresolved),
        "n_articles_after_pin": len(after),
        "share_articles_after_pin": round(len(after) / len(resolved), 5) if resolved else None,
        "n_retrieved_chunks_total": chunks_total,
        "n_retrieved_chunks_from_after_pin_articles": chunks_after,
        "share_retrieved_chunks_after_pin": round(chunks_after / chunks_total, 5)
        if chunks_total
        else None,
        "n_cases_touching_an_after_pin_article": len(cases_touched),
        "share_cases_touching_an_after_pin_article": round(
            len(cases_touched) / len(load_cases()), 4
        ),
        "articles_after_pin": sorted(after.items(), key=lambda kv: kv[1], reverse=True)[:50],
        "retrieved_articles_by_year": dict(sorted(by_year.items())),
    }
    p = write_json("wp9c_cutoff_asymmetry.json", payload)
    print(f"wrote {p}")
    print(
        f"\n  articles after {PIN}: {payload['n_articles_after_pin']} / "
        f"{payload['n_dates_resolved']} resolved "
        f"({payload['share_articles_after_pin']:.4%})"
    )
    print(
        f"  retrieved chunks from those: {chunks_after} / {chunks_total} "
        f"({payload['share_retrieved_chunks_after_pin']:.4%})"
    )
    print(f"  cases touching one: {len(cases_touched)} / {len(load_cases())}")
    print(f"  unresolved dates: {len(unresolved)}")


if __name__ == "__main__":
    main()
