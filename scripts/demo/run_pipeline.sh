#!/usr/bin/env bash
#
# End-to-end demo pipeline orchestrator (§7 steps 5a-5f + 6).
# Chains every Phase 1A script in order and captures the full stdout
# of each step into reports/run_logs/ so the report has reproducible,
# byte-stable evidence of the pipeline run.
#
# Usage (from project root):
#   bash scripts/demo/run_pipeline.sh
#
# Idempotent: chunk_ids are deterministic (UUID5) so re-running upserts
# the same Qdrant points; nothing is duplicated.

set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"
PYTORCH_ENV="/home/hana77/pytorch-env"

# shellcheck disable=SC1091
source "$PYTORCH_ENV/bin/activate"

LOGS_DIR="$PROJECT_ROOT/reports/run_logs"
mkdir -p "$LOGS_DIR"

# ANSI: bold green for headers, dim for metadata
hdr() { printf "\n\033[1;32m=== [%s] %s ===\033[0m\n" "$1" "$2"; }
end() { printf "\033[2m    finished in %ss\033[0m\n" "$1"; }

run_step() {
    local id=$1; local desc=$2; shift 2
    hdr "$id" "$desc"
    local start; start=$(date +%s)
    # Tee preserves console output AND captures to log file.
    "$@" 2>&1 | tee "$LOGS_DIR/${id}.log"
    end "$(( $(date +%s) - start ))"
}

PIPELINE_START=$(date +%s)
date -u +"Pipeline start: %Y-%m-%dT%H:%M:%SZ" | tee "$LOGS_DIR/pipeline_meta.log"

run_step 01_fetch    "Fetch demo corpus (NCBI esearch + efetch)" \
    python scripts/corpus/01_demo_fetch_pmc.py
run_step 06_parse    "Parse JATS XML (lxml)" \
    python scripts/corpus/06_parse_jats_xml.py
run_step 07_filter   "Filter for genetics / rare disease relevance" \
    python scripts/corpus/07_filter_corpus.py
run_step 08_chunk    "Section-aware chunking (UUID5 deterministic IDs)" \
    python scripts/corpus/08_section_aware_chunking.py
run_step 09_embed    "PubMedBERT embedding (RTX 5090, cu128)" \
    python scripts/embedding/09_generate_embeddings.py
run_step 10_upload   "Upload to Qdrant (dense + BM25 sparse + payload)" \
    python scripts/indexing/10_create_qdrant_index.py --upload
run_step 11_validate "Hybrid retrieval probes (dense / BM25 / RRF fusion)" \
    python scripts/indexing/11_validate_index.py

PIPELINE_END=$(date +%s)
TOTAL=$(( PIPELINE_END - PIPELINE_START ))
{
    date -u +"Pipeline end:   %Y-%m-%dT%H:%M:%SZ"
    echo "Total wall-clock: ${TOTAL}s"
} | tee -a "$LOGS_DIR/pipeline_meta.log"

hdr DONE "Pipeline finished in ${TOTAL}s — see $LOGS_DIR"
echo "Next: python scripts/demo/collect_stats.py && python scripts/demo/make_visualizations.py"
