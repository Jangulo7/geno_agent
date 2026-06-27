#!/usr/bin/env bash
# Assemble the per-paper DATA/RESOURCE bundles for Figshare and checksum them.
# Code zips come from build_figshare_bundles.sh; this handles everything that is
# NOT code: the cohort (P1) and eval results / figures / manuscript / rationale
# derivative (P2). License-unsafe and regenerable artifacts are excluded by
# construction (tracked-only selection + text-stripped derivative).
#
# Usage: bash release/assemble_data_bundles.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
OUT="$ROOT/figshare_uploads"
STAGE="$OUT/_staging"
rm -rf "$STAGE"
mkdir -p "$STAGE"

# Use Python's zipfile so no external `zip` binary is required.
zip_dir() { ( cd "$STAGE" && python3 -m zipfile -c "$OUT/$1.zip" "$1" ) && ( cd "$OUT" && sha256sum "$1.zip" > "$1.zip.sha256" ); }

# ---------- P1: methods / shared foundation data ----------
P1="paper-methods-v1.0_data"
P1D="$STAGE/$P1"
mkdir -p "$P1D/data"
# n=1,047 cohort (gitignored on disk — copied explicitly) + provenance manifest
cp -r data/test_cases_1050 "$P1D/data/"
cp data/MANIFEST.tsv "$P1D/data/"
cp release/paper-methods/README_FIGSHARE.md release/paper-methods/REPRODUCE.md \
   release/paper-methods/artifacts_manifest.tsv "$P1D/"
zip_dir "$P1"

# ---------- P2: GenoAgent results / manuscript / derivative ----------
P2="paper-genoagent-v1.0_data"
P2D="$STAGE/$P2"
mkdir -p "$P2D"
# Tracked-only selection (git archive auto-excludes gitignored raw response dumps)
git archive --format=tar HEAD -- \
  data/eval_1050 data/eval_1050_lopo_full \
  reports/figures reports/tables \
  reports/manuscript_q1_draft.md reports/manuscript_q1_draft_apa.md \
  reports/explainability_report.md reports/tripod_llm_compliance.md \
  reports/wallclock_cost_table.md reports/deeprare_comparability_analysis.md \
  | tar -x -C "$P2D"
# License-clean rationale derivative (verbatim PMC text stripped) for the champion cell
python scripts/eval/strip_responses_for_release.py \
  --input data/eval_1050/cell_S_responses \
  --output "$P2D/data/eval_1050/cell_S_rationale_derivative"
cp release/paper-genoagent/README_FIGSHARE.md release/paper-genoagent/REPRODUCE.md \
   release/paper-genoagent/artifacts_manifest.tsv "$P2D/"
zip_dir "$P2"

echo "Assembled:"
ls -la "$OUT"/*_data.zip
echo "Staging kept at $STAGE for inspection (gitignored)."
