#!/usr/bin/env bash
# Pre-deposit check for the P1 Software DOI (10.6084/m9.figshare.32814491).
#
# The P1 manuscript names specific scripts and validation records as released.
# This script asserts that a bundle built from <tag> actually contains them, that
# the tag carries the corrected RRF label, and that no manuscript source leaks in.
# Run it before archiving a tag to Figshare.
#
# Usage: bash release/verify_p1_deposit.sh paper-methods-v1.4
set -uo pipefail

TAG="${1:?usage: verify_p1_deposit.sh <git-tag>}"
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT"
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "FAIL: tag '$TAG' does not exist"; exit 1; }

mapfile -t PATHSPECS < <(grep -vE '^[[:space:]]*#|^[[:space:]]*$' release/paper-methods/code_paths.txt)
LIST="$(git archive --format=tar "$TAG" -- "${PATHSPECS[@]}" | tar -t)"
fail=0

# 1. Everything the manuscript cites by name must be in the bundle.
REQUIRED=(
  scripts/corpus/02_extract_and_parse_ftp.py
  scripts/corpus/03_normalize_dedupe_filter.py
  scripts/corpus/04_chunk_normalized.py
  scripts/corpus/compute_chunk_fingerprint.sh
  scripts/embedding/05_embed_chunks.py
  scripts/indexing/06_upload_to_qdrant.py
  scripts/indexing/10_create_qdrant_index.py
  scripts/cases/18b_build_hard_candidates.py
  scripts/eval/compute_annotation_overlap.py
  scripts/eval/compute_clustering_stats.py
  scripts/eval/validate_retrieval_substrate.py
  scripts/manuscript/render_p1_figures.py
  scripts/utils/seed.py
  release/index_fingerprint/chunk_id_fingerprint.txt
  release/index_fingerprint/chunk_counts_by_pmcid.sha256
  release/index_fingerprint/chunk_counts_by_pmcid.tsv
  release/index_fingerprint/retrieval_substrate_validation.json
  release/cohort/retained_pmcids.txt
  release/cohort/clustering_stats.json
  release/cohort/difficulty_tie_split.json
  data/MANIFEST.tsv
)
echo "== files the manuscript cites =="
for f in "${REQUIRED[@]}"; do
  if grep -qx "$f" <<<"$LIST"; then echo "  ok      $f"
  else echo "  MISSING $f"; fail=1; fi
done

# 2. No manuscript source may be deposited.
echo "== no manuscript sources =="
if LEAK="$(grep -iE '\.tex$|\.docx$|\.pdf$|cover_letter|manuscript_methods|_apa\.md' <<<"$LIST")"; then
  echo "$LEAK" | sed 's/^/  LEAKED /'; fail=1
else echo "  ok      none"; fi

# 3. The tag must carry the corrected fusion label, not the superseded k=60.
#    A deposit that says k=60 while the paper says k=2 is the exact contradiction
#    the B2 correction exists to prevent.
echo "== RRF label at the tag =="
for f in scripts/eval/validate_retrieval_substrate.py \
         release/index_fingerprint/retrieval_substrate_validation.json; do
  if git show "$TAG:$f" 2>/dev/null | grep -qE 'Rank Fusion \(k ?= ?60\)'; then
    echo "  STALE   $f still says k=60"; fail=1
  else echo "  ok      $f"; fi
done

# 4. The filter literals the paper calls normative must be reachable at the tag.
echo "== normative filter definition =="
if git show "$TAG:scripts/corpus/03_normalize_dedupe_filter.py" 2>/dev/null \
     | grep -q 'GENETICS_VOCAB'; then echo "  ok      GENETICS_VOCAB present"
else echo "  MISSING GENETICS_VOCAB"; fail=1; fi

# 5. The two large released artefacts must match the checksums the paper quotes.
#    Both are tracked from 2026-08-23 so that this bundle can carry them.
echo "== large artefact checksums vs data/MANIFEST.tsv =="
for f in release/cohort/retained_pmcids.txt \
         release/index_fingerprint/chunk_counts_by_pmcid.tsv; do
  if [ ! -f "$f" ]; then echo "  MISSING $f absent on disk"; fail=1; continue; fi
  want="$(awk -F'\t' -v p="$f" '$1==p {print $2}' data/MANIFEST.tsv)"
  got="$(sha256sum "$f" | cut -d' ' -f1)"
  if [ -z "$want" ]; then echo "  NO ROW  $f is not listed in data/MANIFEST.tsv"; fail=1
  elif [ "$want" != "$got" ]; then echo "  DIGEST  $f differs from MANIFEST.tsv"; fail=1
  else echo "  ok      $f ($(wc -l < "$f") lines, digest matches)"; fi
done

echo
[ "$fail" -eq 0 ] && echo "PASS: bundle from $TAG matches what the manuscript claims." \
                  || echo "FAIL: fix the items above before archiving $TAG."
exit "$fail"
