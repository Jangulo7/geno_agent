"""Emit the Table 1 block of metric_audit.CLAIMED by parsing the printed table.

The audit's premise is that CLAIMED mirrors what the *manuscript prints*. Deriving
it from the recomputation instead would make the check tautological, so this reads
main.tex. Run it after editing Table 1 and paste the output over the Table 1 block
of CLAIMED; metric_audit.py then re-derives each value from the per-case artefacts
and flags any that no longer agree.

Partial coverage is what let two defects through review: Cell R's full-cohort top-1
and six of the seven overlap-absent MRR values sat in rows no CLAIMED entry pointed
at. Regenerating keeps the grid complete.

Usage:
  python gen_claimed_from_table1.py path/to/main.tex
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Table 1 prints top-1 for three subsets, then top-5/top-10/MRR for the
# overlap-absent subset only.
PRIMARY = re.compile(r"([01]\.\d{3})\}?\\cnt(?:bf)?\{(\d+)\}")
SUBSETS = ("full", "overlap_present", "overlap_absent")
SECONDARY = ("top5", "top10", "mrr")
BLOCK_LABEL = {"standard": "standard cohort", "hard": "hard cohort"}


def table1_rows(tex: str):
    """Yield the body rows of Table 1, tagged with their candidate-list block."""
    body = tex.split(r"\label{tab:centrepiece}", 1)[1].split(r"\end{tabularx}", 1)[0]
    cohort = "standard"
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("%"):
            # The table carries layout commentary that names \cnt and \exact.
            continue
        if "Hard candidate lists" in stripped:
            cohort = "hard"
        if r"\cnt" in stripped and stripped.endswith(r"\\"):
            yield cohort, line


def claimed_for(line: str, cohort: str):
    fields = [x.strip() for x in line.split("&")]
    cell = fields[0]
    for subset, (value, _count) in zip(SUBSETS, PRIMARY.findall(line), strict=True):
        yield cohort, subset, cell, "top1", value
    printed = (fields[5], fields[6], fields[7].replace("\\\\", "").strip())
    for metric, value in zip(SECONDARY, printed, strict=True):
        # \exact marks a cell that is exactly 1.000 rather than rounded to it.
        yield cohort, "overlap_absent", cell, metric, value.replace("\\exact", "").strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tex", help="path to main.tex")
    args = ap.parse_args()

    tex = Path(args.tex).read_text()
    seen_block, n = None, 0
    for cohort, line in table1_rows(tex):
        if cohort != seen_block:
            seen_block = cohort
            print(f"    # --- Table 1, {BLOCK_LABEL[cohort]} ---")
        for cohort_, subset, cell, metric, value in claimed_for(line, cohort):
            print(f'    ("{cohort_}", "{subset}", "{cell}", "{metric}", {value}),')
            n += 1
    print(f"    # {n} entries")


if __name__ == "__main__":
    main()
