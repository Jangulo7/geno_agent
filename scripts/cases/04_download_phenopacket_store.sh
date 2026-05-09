#!/usr/bin/env bash
#
# Download GA4GH Phenopacket-Store v0.1.19 release tarball
# (master plan §3.4 / §7 step [8]).
#
# The release ships a single zip of all phenopackets organized by cohort.
# This script downloads it and extracts into a versioned subdirectory so
# repeat runs do not collide.
#
# Usage (from project root):
#   bash scripts/cases/04_download_phenopacket_store.sh
#
# Idempotent: re-running skips download/unzip if outputs already exist.

set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

VER="${PHENOPACKET_STORE_VERSION:-0.1.19}"
DEST="${PHENOPACKET_DIR:-$PROJECT_ROOT/data/phenopackets}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
LOG="$LOG_DIR/download_phenopackets.log"

ZIP="$DEST/all_phenopackets.zip"
EXTRACTED_DIR="$DEST/v${VER}"
RELEASE_URL="https://github.com/monarch-initiative/phenopacket-store/releases/download/${VER}/all_phenopackets.zip"

mkdir -p "$DEST" "$LOG_DIR"

echo "============================================================"
echo "Phenopacket-Store v${VER} download"
echo "  source:    ${RELEASE_URL}"
echo "  zip:       ${ZIP}"
echo "  extract:   ${EXTRACTED_DIR}"
echo "  log:       ${LOG}"
echo "============================================================"

# 1. Download the tarball if not already present
if [[ -f "$ZIP" && -s "$ZIP" ]]; then
    echo "[skip] Zip already present at $ZIP ($(du -h "$ZIP" | cut -f1))" | tee -a "$LOG"
else
    echo "[download] Fetching release tarball..." | tee -a "$LOG"
    date -u +"Started:   %Y-%m-%dT%H:%M:%SZ" | tee -a "$LOG"
    wget --tries=3 --timeout=120 \
         -O "$ZIP" "$RELEASE_URL" 2>&1 | tee -a "$LOG"
    date -u +"Completed: %Y-%m-%dT%H:%M:%SZ" | tee -a "$LOG"
    echo "  size: $(du -h "$ZIP" | cut -f1)" | tee -a "$LOG"
fi

# 2. Extract into a versioned directory
if [[ -d "$EXTRACTED_DIR" ]]; then
    EXISTING=$(find "$EXTRACTED_DIR" -name '*.json' 2>/dev/null | wc -l)
    if [[ "$EXISTING" -gt 0 ]]; then
        echo "[skip] Already extracted at $EXTRACTED_DIR ($EXISTING json files)" | tee -a "$LOG"
    fi
else
    echo "[extract] Unzipping into $EXTRACTED_DIR..." | tee -a "$LOG"
    unzip -q "$ZIP" -d "$EXTRACTED_DIR" 2>&1 | tee -a "$LOG"
fi

# 3. Sanity check: expected ~6,668 phenopackets per master plan §3.4
NUM_JSON=$(find "$EXTRACTED_DIR" -name '*.json' 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$EXTRACTED_DIR" | cut -f1)

{
    echo
    echo "=== Phenopacket-Store v${VER} summary ==="
    echo "  json files: ${NUM_JSON}"
    echo "  total size: ${TOTAL_SIZE}"
} | tee -a "$LOG"

if [[ "$NUM_JSON" -lt 6000 || "$NUM_JSON" -gt 7500 ]]; then
    echo
    echo "WARNING: phenopacket count ${NUM_JSON} is far from the methodology's expected 6,668 (master plan §3.4)." | tee -a "$LOG"
    echo "         Verify the release URL and the unzip target before continuing to Phase 1B step [9]." | tee -a "$LOG"
fi

# 4. Acquired-at stamp + SHA-256 of the zip for the manifest
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$EXTRACTED_DIR/.acquired_at"
ZIP_SHA=$(sha256sum "$ZIP" | awk '{print $1}')
echo
echo "  zip sha256: ${ZIP_SHA}"
echo "  TODO: append to data/MANIFEST.tsv with row:"
echo "    data/phenopackets/all_phenopackets.zip\t${ZIP_SHA}\t$(stat -c%s "$ZIP")\t$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo
echo "============================================================"
echo "Next step (master plan §7 step [9]):"
echo "  python scripts/cases/13_load_phenopackets.py \\"
echo "         --input-dir ${EXTRACTED_DIR} \\"
echo "         --output    data/test_cases/01_all_phenopackets.jsonl"
echo "============================================================"
