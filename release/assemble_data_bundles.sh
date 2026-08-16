#!/usr/bin/env bash
# Assemble the per-paper DATA/RESOURCE bundles for Figshare and checksum them.
# Code zips come from build_figshare_bundles.sh; this handles everything that is
# NOT code: the cohort (P1) and eval results / figures / tables / rationale
# derivative (P2), for both the standard and hard cohorts. License-unsafe and
# regenerable artifacts are excluded by construction (tracked-only selection +
# text-stripped derivative). Manuscript drafts and internal reports are privatised
# (local-only) and never bundled.
#
# Usage:
#   bash release/assemble_data_bundles.sh              # P2 data bundle only (default)
#   bash release/assemble_data_bundles.sh --with-cohorts   # also rebuild records 1 and 2
#
# The default is deliberately narrow. Records 1 and 2 (the two cohort datasets) are
# PUBLISHED and frozen; records 3 and 4 are still drafts. This script used to rebuild
# all four unconditionally, so anyone refreshing the P2 data bundle silently rewrote
# two live deposits. That happened on 2026-08-16, and the rebuilds were not
# equivalent: the standard cohort differed in README_FIGSHARE.md, MANIFEST.tsv and
# their CHECKSUMS.sha256, and the hard cohort dropped test_cases_hard_manifest.json.
# Both had to be re-downloaded from Figshare and restored.
#
# So the safe path is now the one you get by typing nothing. --with-cohorts still
# works, but says what it is about to touch first.
set -euo pipefail

WITH_COHORTS=0
for arg in "$@"; do
  case "$arg" in
    --with-cohorts) WITH_COHORTS=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg (expected --with-cohorts)"; exit 2 ;;
  esac
done
if [ "$WITH_COHORTS" -eq 1 ]; then
  echo "NOTE --with-cohorts: records 1 and 2 are PUBLISHED. Rebuilt zips will not"
  echo "     byte-match the live deposits. Do not upload them without checking"
  echo "     figshare_uploads/UPLOAD_MAP.md first."
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
OUT="$ROOT/figshare_uploads"
STAGE="$OUT/_staging"
CCBY="$ROOT/release/licenses/LICENSE-CC-BY-4.0.txt"  # dataset license (cohorts)
AGPL="$ROOT/LICENSE"                                 # AGPL-3.0 (P2 result artifacts)
rm -rf "$STAGE"
mkdir -p "$STAGE"

# Use Python's zipfile so no external `zip` binary is required.
zip_dir() { ( cd "$STAGE" && python3 -m zipfile -c "$OUT/$1.zip" "$1" ) && ( cd "$OUT" && sha256sum "$1.zip" > "$1.zip.sha256" ); }

# Croissant descriptors are authored by hand and live next to the zips in
# figshare_uploads/ (they are also uploaded standalone, beside the zip). They are
# NOT regenerated here, so a rebuild must copy the existing descriptor in or the
# bundle silently loses it — which is what happened before this guard existed.
copy_croissant() { # $1 = bundle name, $2 = staging dir
  if [ -f "$OUT/$1.croissant.json" ]; then
    cp "$OUT/$1.croissant.json" "$2/croissant.json"
  else
    echo "WARN $1: no $1.croissant.json in figshare_uploads/ — bundle will ship WITHOUT its Croissant descriptor."
  fi
}

# Write per-file SHA-256 for every file in a staged bundle (excluding the
# manifest itself), so each bundle is self-verifiable after download with
# `sha256sum -c CHECKSUMS.sha256`.
gen_checksums() { ( cd "$1" && find . -type f ! -name CHECKSUMS.sha256 -printf '%P\n' | sort | xargs sha256sum > CHECKSUMS.sha256 ); }

if [ "$WITH_COHORTS" -eq 1 ]; then
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
# clustering statistics are a property of this cohort and are referenced by its
# README, so they ship with the dataset (also included in the methods artefacts).
cp release/cohort/clustering_stats.json "$COHD/"
cp release/cohort/README_FIGSHARE.md "$COHD/"
cp "$CCBY" "$COHD/LICENSE"   # machine-discoverable dataset license (CC BY 4.0)
copy_croissant "$COH" "$COHD"
# per-file SHA-256 inside the bundle (good-practice integrity for a citable dataset)
gen_checksums "$COHD"
zip_dir "$COH"

# ---------- Hard cohort (own DOI; case-paired phenotype-similar distractors) ----------
# Scripted here for reproducibility (previously assembled by hand). Sources are
# the regenerable 18b outputs in data/test_cases_hard/; guarded so the build
# still succeeds when the hard cohort has not been regenerated locally.
COHH="genoagent-cohort-hard-n1047-v1.0"
COHHD="$STAGE/$COHH"
if compgen -G "data/test_cases_hard/test_cases_hard.jsonl" >/dev/null; then
  mkdir -p "$COHHD"
  cp data/test_cases_hard/*.jsonl data/test_cases_hard/*.json "$COHHD/"
  cp release/cohort/README_FIGSHARE_hard.md "$COHHD/README_FIGSHARE.md"
  cp "$CCBY" "$COHHD/LICENSE"
  copy_croissant "$COHH" "$COHHD"
  # test_cases_hard_manifest.json is in the deposited bundle but no longer exists
  # on disk; a rebuild cannot reproduce it until 18b_build_hard_candidates.py is
  # re-run to emit it. Do not re-upload a rebuilt hard bundle without checking.
  [ -f "$COHHD/test_cases_hard_manifest.json" ] || \
    echo "WARN $COHH: test_cases_hard_manifest.json absent — the deposited bundle has it; rebuild is NOT equivalent."
  gen_checksums "$COHHD"
  zip_dir "$COHH"
else
  echo "SKIP hard cohort: data/test_cases_hard/test_cases_hard.jsonl absent "\
"(run scripts/cases/18b_build_hard_candidates.py to regenerate, then re-run this script)."
fi

else
  echo "SKIP records 1 and 2 (published cohorts). Pass --with-cohorts to rebuild them."
fi

# ---------- P2: GenoAgent results (standard + hard cohorts) + figures/tables ----------
# v1.7, matching the code zip. The data bundle carries reports/figures/, which was
# split into P1_figures/ and P2_figures/ and whose fig2_architecture.png and
# fig4_hard_difficulty.png both changed, so it is no longer v1.3 content.
P2="paper-genoagent-v1.7_data"
P2D="$STAGE/$P2"
mkdir -p "$P2D"
# Tracked-only selection (git archive auto-excludes gitignored raw response dumps);
# the one deliberate exception is Cell R, copied explicitly below.
# Standard (eval_1050) + hard (eval_hard) per-cell rankings, aggregates, and judge
# summaries; LOPO summaries; and the publication figures/tables. Manuscript drafts
# and internal reports are privatised (local-only) and deliberately excluded — the
# README (in the code bundle) is the explanatory document.
git archive --format=tar HEAD -- \
  data/eval_1050 data/eval_1050_lopo_full data/eval_hard \
  reports/figures reports/tables \
  | tar -x -C "$P2D"
# Cell R (Resnik BMA similarity floor) per-case rankings are gitignored on disk —
# regenerable in ~30 s, so they are kept out of git — but they back printed Table 1
# rows in both cohorts and are what verify_perfect_cells.py reads, so the deposit
# carries them explicitly. 8.3 MB per cohort; gene symbols and scores only, no PMC text.
for COHORT in eval_1050 eval_hard; do
  if compgen -G "data/$COHORT/cell_R_resnik/*.json" >/dev/null; then
    mkdir -p "$P2D/data/$COHORT/cell_R_resnik"
    cp data/"$COHORT"/cell_R_resnik/*.json "$P2D/data/$COHORT/cell_R_resnik/"
  else
    echo "SKIP data/$COHORT/cell_R_resnik: absent "\
"(regenerate with scripts/eval/revision/resnik_ranker.py, then re-run this script)."
  fi
done
# License-clean rationale derivatives (verbatim PMC text stripped) for the champion
# cell, both cohorts.
python scripts/eval/strip_responses_for_release.py \
  --input data/eval_1050/cell_S_responses \
  --output "$P2D/data/eval_1050/cell_S_rationale_derivative"
python scripts/eval/strip_responses_for_release.py \
  --input data/eval_hard/cell_S_responses \
  --output "$P2D/data/eval_hard/cell_S_rationale_derivative"
cp release/paper-genoagent/README_FIGSHARE.md release/paper-genoagent/REPRODUCE.md \
   release/paper-genoagent/artifacts_manifest.tsv "$P2D/"
cp "$AGPL" "$P2D/LICENSE"   # AGPL-3.0 — result artifacts (matches README + manifest)
# per-file SHA-256 inside the bundle: the data bundle has ~15k files, so an in-zip
# manifest lets downloaders verify integrity beyond the single outer .zip hash.
gen_checksums "$P2D"
zip_dir "$P2"

echo "Assembled:"
ls -la "$OUT"/*_data.zip
echo "Staging kept at $STAGE for inspection (gitignored)."
