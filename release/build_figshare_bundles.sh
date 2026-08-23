#!/usr/bin/env bash
# Build a code-only Figshare zip for one paper from its git tag, plus a sha256
# checksum. Reads the paper's code_paths.txt pathspecs; excludes data, caches,
# .git, and AI-tooling config. Outputs to ../figshare_uploads/ (gitignored).
#
# Usage:
#   bash release/build_figshare_bundles.sh paper-methods-v1.4
#   bash release/build_figshare_bundles.sh paper-genoagent-v1.8
#
# The data/resource artifacts (cohort, eval results, figures) are NOT included
# here — they are listed in each paper's artifacts_manifest.tsv and assembled
# separately because many are on-disk-only (gitignored) and license-variable.
set -euo pipefail

TAG="${1:?usage: build_figshare_bundles.sh <git-tag>}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

case "$TAG" in
  paper-methods-*)   PAPER="paper-methods" ;;
  paper-genoagent-*) PAPER="paper-genoagent" ;;
  *) echo "ERROR: unknown tag prefix '$TAG'"; exit 1 ;;
esac

PATHS_FILE="release/$PAPER/code_paths.txt"
[ -f "$PATHS_FILE" ] || { echo "ERROR: missing $PATHS_FILE"; exit 1; }

# Confirm the tag exists (resolve to a commit).
if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "ERROR: tag '$TAG' does not exist yet. Create it first, e.g.:"
  echo "  git tag -a $TAG -m '<snapshot description + target journal>'"
  exit 1
fi
# Dereference to the underlying commit (annotated tags resolve to a tag object).
COMMIT="$(git rev-parse --short "${TAG}^{commit}")"

OUT_DIR="$ROOT/figshare_uploads"
mkdir -p "$OUT_DIR"
ZIP="$OUT_DIR/${TAG}_code_${COMMIT}.zip"

# Collect non-comment, non-blank pathspecs.
mapfile -t PATHSPECS < <(grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$PATHS_FILE")
[ "${#PATHSPECS[@]}" -gt 0 ] || { echo "ERROR: no pathspecs in $PATHS_FILE"; exit 1; }

echo "Building $ZIP"
echo "  tag=$TAG commit=$COMMIT, ${#PATHSPECS[@]} pathspecs"

# git archive emits only tracked files at the tagged commit, so caches / .env /
# data dumps that are gitignored can never leak in.
git archive --format=zip \
  --prefix="${TAG}/" \
  -o "$ZIP" \
  "$TAG" -- "${PATHSPECS[@]}"

( cd "$OUT_DIR" && sha256sum "$(basename "$ZIP")" > "$(basename "$ZIP").sha256" )

echo "Done:"
echo "  $ZIP"
echo "  $ZIP.sha256"
echo "Listing (first 40 entries):"
unzip -l "$ZIP" | head -45
