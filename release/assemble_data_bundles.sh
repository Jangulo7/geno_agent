#!/usr/bin/env bash
# Assemble the per-paper DATA/RESOURCE bundles for Figshare and checksum them.
# Code zips come from build_figshare_bundles.sh; this handles everything that is
# NOT code: the cohort (P1) and eval results / figures / tables / rationale
# derivative (P2), for both the standard and hard cohorts. License-unsafe and
# regenerable artifacts are excluded by construction (tracked-only selection +
# text-stripped derivative). Manuscript drafts and internal reports are privatised
# (local-only) and never bundled.
#
# Usage: bash release/assemble_data_bundles.sh
set -euo pipefail

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

# Write per-file SHA-256 for every file in a staged bundle (excluding the
# manifest itself), so each bundle is self-verifiable after download with
# `sha256sum -c CHECKSUMS.sha256`.
gen_checksums() { ( cd "$1" && find . -type f ! -name CHECKSUMS.sha256 -printf '%P\n' | sort | xargs sha256sum > CHECKSUMS.sha256 ); }

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
cp "$CCBY" "$COHD/LICENSE"   # machine-discoverable dataset license (CC BY 4.0)
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
  gen_checksums "$COHHD"
  zip_dir "$COHH"
else
  echo "SKIP hard cohort: data/test_cases_hard/test_cases_hard.jsonl absent "\
"(run scripts/cases/18b_build_hard_candidates.py to regenerate, then re-run this script)."
fi

# ---------- P2: GenoAgent results (standard + hard cohorts) + figures/tables ----------
P2="paper-genoagent-v1.1_data"
P2D="$STAGE/$P2"
mkdir -p "$P2D"
# Tracked-only selection (git archive auto-excludes gitignored raw response dumps).
# Standard (eval_1050) + hard (eval_hard) per-cell rankings, aggregates, and judge
# summaries; LOPO summaries; and the publication figures/tables. Manuscript drafts
# and internal reports are privatised (local-only) and deliberately excluded — the
# README (in the code bundle) is the explanatory document.
git archive --format=tar HEAD -- \
  data/eval_1050 data/eval_1050_lopo_full data/eval_hard \
  reports/figures reports/tables \
  | tar -x -C "$P2D"
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
