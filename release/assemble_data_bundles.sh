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

# ---------- Standalone cohort dataset (own DOI; Figshare "Dataset" item) ----------
# The n=1,047 benchmark cohort is published as its own citable dataset, separate
# from the methods/foundation code (which references this dataset's DOI). The
# methods item is the code zip only — it already carries MANIFEST.tsv — so there
# is no separate paper-methods data bundle and no duplicate cohort copy.
COH="genoagent-cohort-n1047-v1.0"
COHD="$STAGE/$COH"
mkdir -p "$COHD"
# full cohort + sidecars + staged provenance (gitignored on disk — copied explicitly)
cp data/test_cases_1050/*.jsonl data/test_cases_1050/*.json "$COHD/"
cp data/MANIFEST.tsv "$COHD/"
cp release/cohort/README_FIGSHARE.md "$COHD/"
# per-file SHA-256 inside the bundle (good-practice integrity for a citable dataset)
( cd "$COHD" && find . -type f ! -name CHECKSUMS.sha256 -printf '%P\n' | sort \
    | xargs sha256sum > CHECKSUMS.sha256 )
zip_dir "$COH"

# ---------- P2: GenoAgent results / manuscript / derivative ----------
P2="paper-genoagent-v1.0_data"
P2D="$STAGE/$P2"
mkdir -p "$P2D"
# Tracked-only selection (git archive auto-excludes gitignored raw response dumps)
git archive --format=tar HEAD -- \
  data/eval_1050 data/eval_1050_lopo_full \
  reports/figures reports/tables \
  reports/paper_extension_results.md \
  reports/manuscript_q1_draft.md reports/manuscript_q1_draft_apa.md \
  reports/explainability_report.md reports/tripod_llm_compliance.md \
  reports/deeprare_comparability_analysis.md \
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
