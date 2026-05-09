#!/usr/bin/env bash
#
# Production PMC OA AWS S3 sync (master plan §3.1 / §7 step [5a]).
#
# DEVIATION FROM MASTER PLAN §3.1 (recorded in §10):
# The s3://pmc-oa-opendata/ bucket layout changed since master plan v2.1
# was authored. As of 2026-05-09 the bucket is FLAT — articles live at
# s3://pmc-oa-opendata/PMC<id>.<version>/ with no oa_comm/oa_noncomm/oa_other
# tier directories. License tier is recorded only inside each article's
# per-article PMC<id>.<version>.json metadata file.
#
# The NCBI HTTPS bulk archives at https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/
# (the master plan's documented fallback) also returned 404 on 2026-05-09 —
# they were deprecated earlier than the August 2026 date the master plan cites.
#
# Consequence: the master plan §7 "tier-by-tier streaming" strategy
# (download oa_comm → process → delete → download oa_noncomm → ...) is
# replaced by a SINGLE FULL-CORPUS sync filtered to XML files only.
# License-tier classification, if needed, is done downstream by reading
# the per-article JSON metadata. Total disk impact is the same (~150 GB
# of XML), just in one directory rather than three.
#
# Usage (from project root, inside tmux/screen):
#   bash scripts/corpus/01_download_pmc_oa.sh                  # full sync
#   bash scripts/corpus/01_download_pmc_oa.sh --limit 1000     # first 1000 PMC dirs
#   bash scripts/corpus/01_download_pmc_oa.sh --dry-run        # preview only
#
# Resumable: re-running the script picks up where a partial sync left off
# (aws s3 sync compares S3 ETags against local files and skips unchanged).

set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"

# Load .env so PMC_WORKSPACE / LOG_DIR are honored
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

PMC_WORKSPACE="${PMC_WORKSPACE:-/mnt/c/pmc_workspace}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
DEST="$PMC_WORKSPACE/xml_raw/all"
LOG="$LOG_DIR/download_pmc_oa.log"
BUCKET="pmc-oa-opendata"

# ---------------------------------------------------------------- arg parsing
DRY_RUN=""
LIMIT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN="--dryrun"
            shift ;;
        --limit)
            LIMIT="${2:?--limit requires a value}"
            shift 2 ;;
        -h|--help)
            sed -n '3,32p' "$0"
            exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            echo "Run with --help for usage." >&2
            exit 2 ;;
    esac
done

# ---------------------------------------------------------------- pre-flight
if ! command -v aws &> /dev/null; then
    cat >&2 <<EOF
ERROR: aws CLI not found.
Install into the project Python env:
    source /home/hana77/pytorch-env/bin/activate && pip install awscli
EOF
    exit 1
fi

mkdir -p "$DEST" "$LOG_DIR"

AVAIL_GB=$(df -BG "$DEST" 2>/dev/null | awk 'NR==2 {print $4+0}' || echo 0)
echo "Available disk at $DEST: ${AVAIL_GB} GB"
if [[ -z "$LIMIT" && "$AVAIL_GB" -lt 200 ]]; then
    cat >&2 <<EOF

WARNING: full sync needs ~150 GB compressed XML; you have ${AVAIL_GB} GB free.
Consider --limit N for a partial sync, or extend disk first.

EOF
fi

# ---------------------------------------------------------------- banner
cat <<EOF

============================================================
PMC OA full-corpus XML sync
  bucket:    s3://${BUCKET}/  (anonymous via --no-sign-request)
  dest:      ${DEST}
  filter:    *.xml only (excludes JSON metadata, PDFs, txt, figures)
  log:       ${LOG}
  mode:      ${LIMIT:+limited to first $LIMIT PMC dirs}${LIMIT:-full corpus}${DRY_RUN:+ (DRY RUN)}
============================================================

NOTE: the AWS CLI must enumerate every object in the bucket before
      the filter can act on it. Expect 30-60 minutes of listing
      latency BEFORE downloads visibly start. Once started, the
      ~150 GB transfer runs at your network bandwidth.

      Run inside tmux/screen so a disconnect cannot kill the sync.
      The sync is resumable — rerunning skips files already on disk.

EOF

date -u +"Started: %Y-%m-%dT%H:%M:%SZ" | tee -a "$LOG"
START=$(date +%s)

# ---------------------------------------------------------------- the sync
if [[ -n "$LIMIT" ]]; then
    # Limited mode: enumerate the first N PMC<id>/ prefixes individually,
    # then sync each. Avoids the slow full-bucket listing pass.
    echo "LIMITED MODE: enumerating first $LIMIT PMC directories" | tee -a "$LOG"
    mapfile -t PMCS < <(aws s3api list-objects-v2 \
        --no-sign-request \
        --bucket "$BUCKET" \
        --delimiter / \
        --max-keys "$LIMIT" \
        --query 'CommonPrefixes[].Prefix' \
        --output text | tr '\t' '\n')
    echo "Got ${#PMCS[@]} PMC prefixes; syncing XML for each" | tee -a "$LOG"
    for pmc in "${PMCS[@]}"; do
        aws s3 sync \
            --no-sign-request \
            $DRY_RUN \
            --exclude '*' --include '*.xml' \
            "s3://${BUCKET}/${pmc}" \
            "${DEST}/${pmc}" \
            --only-show-errors 2>&1 | tee -a "$LOG"
    done
else
    # Full sync: list every object, filter to *.xml client-side.
    aws s3 sync \
        --no-sign-request \
        $DRY_RUN \
        --exclude '*' --include '*/*.xml' \
        "s3://${BUCKET}/" \
        "${DEST}/" \
        --only-show-errors 2>&1 | tee -a "$LOG"
fi

END=$(date +%s)
ELAPSED=$((END - START))
N_XML=$(find "$DEST" -name '*.xml' 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$DEST" 2>/dev/null | cut -f1)

{
    date -u +"Completed: %Y-%m-%dT%H:%M:%SZ"
    echo "Elapsed:        ${ELAPSED}s ($((ELAPSED / 60)) min)"
    echo "Total XML files: ${N_XML}"
    echo "Total size:      ${TOTAL_SIZE}"
} | tee -a "$LOG"

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$DEST/.acquired_at"

cat <<EOF

============================================================
Next steps per master plan §7 steps [5b-5f]:

  python scripts/corpus/06_parse_jats_xml.py --input-dir ${DEST}
  python scripts/corpus/07_filter_corpus.py
  python scripts/corpus/08_section_aware_chunking.py
  python scripts/embedding/09_generate_embeddings.py
  python scripts/indexing/10_create_qdrant_index.py --upload
  python scripts/indexing/11_validate_index.py

After 5f completes, append PMC OA SHA-256 to data/MANIFEST.tsv (§7 step [7]).
============================================================
EOF
