#!/usr/bin/env bash
# Chunk-set fingerprint for the P1 resource paper.
#
# Definition: the fingerprint is the SHA-256 over the byte-sorted (LC_ALL=C),
# DEDUPLICATED list of chunk_id values -- a fingerprint of the chunk *set*, which
# is what the Qdrant collection holds. Deduplication is load-bearing: chunk_id is
# a content-addressed UUID5, so a re-emitted record (e.g. the overlap region of a
# resumed chunking run) carries an identical id and is collapsed by idempotent
# upsert. For the released build the raw chunk JSONL holds 52,782,789 records but
# only 52,777,395 distinct ids, which is exactly the collection point count.
#
# LC_ALL=C is mandatory: locale-dependent collation would produce a different
# digest on a different machine, destroying the point of the fingerprint.
#
# Usage:
#   CHUNKFILE=/path/to/all_chunks.jsonl.gz \
#   OUT=release/index_fingerprint \
#   scripts/corpus/compute_chunk_fingerprint.sh
set -euo pipefail
CHUNKFILE=${CHUNKFILE:-/home/hana77/chunks/all_chunks.jsonl.gz}
OUT=${OUT:-release/index_fingerprint}
TMP=${TMP:-$(dirname "$CHUNKFILE")/_fp_tmp}
mkdir -p "$OUT" "$TMP"

echo "[$(date -u +%FT%TZ)] pass 1: extracting (chunk_id, pmcid) pairs"
zcat "$CHUNKFILE" | jq -r '[.chunk_id,.pmcid]|@tsv' > "$TMP/pairs.raw"
RAW=$(wc -l < "$TMP/pairs.raw")
echo "[$(date -u +%FT%TZ)] raw chunk records: $RAW"

echo "[$(date -u +%FT%TZ)] pass 2: byte-sort + deduplicate"
LC_ALL=C sort -S 2G -T "$TMP" -u "$TMP/pairs.raw" > "$TMP/pairs.sorted"
UNIQ=$(wc -l < "$TMP/pairs.sorted")
echo "[$(date -u +%FT%TZ)] distinct chunk ids: $UNIQ (duplicates collapsed: $((RAW - UNIQ)))"

# Headline fingerprint: digest over the sorted, deduplicated chunk_id column.
cut -f1 "$TMP/pairs.sorted" \
  | tee >(wc -l | tr -d ' ' > "$OUT/chunk_id_count.txt") \
  | sha256sum | awk '{print $1}' > "$OUT/chunk_id_fingerprint.txt"

# Sanity gate: chunk_id must be a key. If one id mapped to two pmcids the
# deduplicated pair count would exceed the distinct-id count.
IDS=$(cut -f1 "$TMP/pairs.sorted" | LC_ALL=C uniq | wc -l)
if [[ "$IDS" != "$UNIQ" ]]; then
  echo "FATAL: chunk_id is not a key ($IDS distinct ids vs $UNIQ distinct pairs)" >&2
  exit 1
fi

echo "[$(date -u +%FT%TZ)] pass 3: per-PMCID chunk-count manifest"
cut -f2 "$TMP/pairs.sorted" | LC_ALL=C sort -S 2G -T "$TMP" | uniq -c \
  | awk '{print $2"\t"$1}' > "$OUT/chunk_counts_by_pmcid.tsv"
sha256sum "$OUT/chunk_counts_by_pmcid.tsv" | awk '{print $1}' \
  > "$OUT/chunk_counts_by_pmcid.sha256"
PMCIDS=$(wc -l < "$OUT/chunk_counts_by_pmcid.tsv")

echo "[$(date -u +%FT%TZ)] DONE"
echo "raw records         : $RAW"
echo "distinct chunk ids  : $(cat "$OUT/chunk_id_count.txt")"
echo "chunk_id_fingerprint: $(cat "$OUT/chunk_id_fingerprint.txt")"
echo "pmcid rows          : $PMCIDS"
echo "manifest sha256     : $(cat "$OUT/chunk_counts_by_pmcid.sha256")"
