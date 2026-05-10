#!/usr/bin/env bash
#
# Production PMC OA S3 sync (master plan §3.1 / §7 step [5a]).
#
# DEVIATION FROM MASTER PLAN §3.1 (recorded in §10):
# - The s3://pmc-oa-opendata/ bucket layout changed since master plan v2.1
#   was authored. As of 2026-05-09 the bucket is FLAT — articles live at
#   s3://pmc-oa-opendata/PMC<id>.<version>/ with no oa_comm/oa_noncomm/oa_other
#   tier directories. License tier is recorded only inside each article's
#   per-article PMC<id>.<version>.json metadata file.
# - The NCBI HTTPS bulk archives at https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/
#   (the master plan's documented fallback) also returned 404 on 2026-05-09 —
#   they were deprecated earlier than the August 2026 date the master plan cites.
# - The full-corpus sync uses `s5cmd` (Go-native parallel S3 client) instead
#   of `aws s3 sync`. Empirical throughput on this host with `aws s3 sync`
#   was ~12k files/hour (sequential, default 10 concurrent requests),
#   projecting ~12-15 days for the ~4-5M article corpus. s5cmd at default
#   256 workers runs 5-10x faster on many-small-files workloads, cutting
#   that to ~2-3 days. License-tier classification is done downstream by
#   reading per-article JSON metadata.
#
# Usage (from project root, inside tmux/screen):
#   bash scripts/corpus/01_download_pmc_oa.sh                  # full sync (s5cmd)
#   bash scripts/corpus/01_download_pmc_oa.sh --limit 1000     # first 1000 PMC dirs (aws CLI)
#   bash scripts/corpus/01_download_pmc_oa.sh --dry-run        # preview only
#
# Resumable: re-running the script picks up where a partial sync left off
# (s5cmd cp --if-size-differ skips files already on disk with matching size).

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
S5CMD="${S5CMD:-$HOME/.local/bin/s5cmd}"
if [[ -z "$LIMIT" ]] && [[ ! -x "$S5CMD" ]]; then
    cat >&2 <<EOF
ERROR: s5cmd not found at $S5CMD (required for full-corpus sync).
Install with:
    mkdir -p ~/.local/bin && cd /tmp \\
      && curl -sL https://github.com/peak/s5cmd/releases/download/v2.3.0/s5cmd_2.3.0_Linux-64bit.tar.gz | tar -xz s5cmd \\
      && mv s5cmd ~/.local/bin/s5cmd && chmod +x ~/.local/bin/s5cmd
Or override the path: S5CMD=/path/to/s5cmd bash $0
EOF
    exit 1
fi

if [[ -n "$LIMIT" ]] && ! command -v aws &> /dev/null; then
    cat >&2 <<EOF
ERROR: aws CLI not found (required for --limit mode).
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
  mode:      ${LIMIT:+limited to first $LIMIT PMC dirs (aws CLI)}${LIMIT:-full corpus (s5cmd, 256 workers)}${DRY_RUN:+ (DRY RUN)}
============================================================

NOTE: the S3 client must list every object in the bucket before the
      *.xml filter can act on it. With s5cmd (parallel, default 256
      workers) listing + downloads overlap, so progress is visible
      almost immediately and the ~150 GB transfer is bandwidth-bound
      from then on.

      Run inside tmux/screen so a disconnect cannot kill the sync.
      The sync is resumable — rerunning skips files already on disk
      (s5cmd cp --if-size-differ).

----- IF KILLED (BIOS reboot, WSL crash, host shutdown) RESUME WITH -----
   tmux new -d -s pmc_dl 'bash $(realpath "$0" 2>/dev/null || echo "scripts/corpus/01_download_pmc_oa.sh")'
   tmux attach -t pmc_dl       # detach with Ctrl+b d
   tail -f ${LOG}              # follow log without attaching
   grep '^\[STATUS' ${LOG} | tail   # see recent status lines
-------------------------------------------------------------------------

EOF

date -u +"Started: %Y-%m-%dT%H:%M:%SZ" | tee -a "$LOG"
START=$(date +%s)

# ---------------------------------------------------------------- status loop
# Background loop that prints a progress line every 5 minutes by counting
# the cumulative `cp ...` lines s5cmd has emitted to the log. Lightweight —
# uses grep on the log file rather than re-scanning /mnt/c (which would
# take ~30-60s per pass on hundreds of thousands of subdirs).
status_loop() {
    local INTERVAL=300
    local LAST_TS LAST_COUNT NOW_TS NOW_COUNT DELTA RATE_HR RUN_MIN
    local LOOP_START
    LOOP_START=$(date +%s)
    LAST_TS=$LOOP_START
    LAST_COUNT=0
    while true; do
        sleep "$INTERVAL"
        NOW_TS=$(date +%s)
        # grep -c prints "0" AND exits 1 when no matches found; the `||` must
        # be outside the $() so we don't end up with NOW_COUNT="0\n0" tripping
        # arithmetic on the next line.
        NOW_COUNT=$(grep -c '^cp ' "$LOG" 2>/dev/null) || NOW_COUNT=0
        DELTA=$((NOW_COUNT - LAST_COUNT))
        local INTV=$((NOW_TS - LAST_TS))
        if (( INTV > 0 )); then
            RATE_HR=$(( DELTA * 3600 / INTV ))
        else
            RATE_HR=0
        fi
        RUN_MIN=$(( (NOW_TS - LOOP_START) / 60 ))
        printf '[STATUS %s] new_this_run=%d Δ%dmin=%d ≈%d/hr run=%dmin\n' \
            "$(date -u +%H:%M:%SZ)" "$NOW_COUNT" "$((INTERVAL/60))" "$DELTA" "$RATE_HR" "$RUN_MIN" \
            | tee -a "$LOG"
        LAST_TS=$NOW_TS
        LAST_COUNT=$NOW_COUNT
    done
}

status_loop &
STATUS_PID=$!
trap 'kill $STATUS_PID 2>/dev/null || true' EXIT INT TERM

# ---------------------------------------------------------------- the sync
if [[ -n "$LIMIT" ]]; then
    # Limited mode: enumerate the first N PMC<id>/ prefixes individually,
    # then sync each via aws CLI. Avoids the full-bucket listing pass.
    # Used for dev/smoke testing only; production sync uses s5cmd full mode.
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
    # Full sync via s5cmd cp --if-size-differ.
    #
    # Why cp instead of `s5cmd sync`: `sync` does both source AND destination
    # listing upfront, then computes a diff, then starts downloads. With ~5M
    # source objects + ~700k existing files on the slow /mnt/c (Windows mount,
    # ~1ms per stat), that pre-flight takes 30-90 minutes during which zero
    # downloads happen. Empirically this OOM'd toward 1+ GB and gave no
    # progress for 39 minutes in run 2026-05-10T10:42:58Z.
    #
    # `cp --if-size-differ` walks the S3 source in parallel and dispatches
    # each match to a worker, which checks destination and either skips
    # (size matches) or downloads. Listing/skip/download all overlap, so
    # downloads start within minutes. Idempotency is preserved: existing
    # files are skipped silently when their on-disk size matches S3.
    #
    # Glob 's3://bucket/*/*.xml' selects PMC<id>.<v>/<id>.<v>.xml only,
    # excluding JSON/PDF/TXT/figures at the same depth.
    S5CMD_ARGS=(--no-sign-request)
    CP_ARGS=(--if-size-differ)
    [[ -n "$DRY_RUN" ]] && CP_ARGS+=(--dry-run)
    "$S5CMD" "${S5CMD_ARGS[@]}" cp "${CP_ARGS[@]}" \
        "s3://${BUCKET}/*/*.xml" \
        "${DEST}/" 2>&1 | tee -a "$LOG"
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
