#!/usr/bin/env bash
#
# Full-cohort (n=1,047) Cell S leave-one-paper-out run, end to end:
#   1. start local vLLM (Qwen3-8B), wait until ready
#   2. run_lopo.py --all --use-lea  (control + LOPO arms, resumable)
#   3. stop vLLM (always, via trap)
#   4. aggregate_lopo.py -> stratified fair-cohort + overlap cross-tabs
#
# No cloud API. Resumable: re-running skips cases already on disk.
#
# Usage (inside tmux recommended):
#   bash scripts/eval/run_lopo_full_overnight.sh

set -uo pipefail
cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"

OUT_ROOT="${OUT_ROOT:-${PROJECT_ROOT}/data/eval_1050_lopo_full}"
PYTORCH_PY="${PYTORCH_PY:-/home/hana77/pytorch-env/bin/python}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LOG="${PROJECT_ROOT}/logs/lopo_full_S_${TS}.log"
VLLM_LOG="${PROJECT_ROOT}/logs/vllm_lopo_full_${TS}.log"
PORT="${VLLM_PORT:-8001}"
mkdir -p "${PROJECT_ROOT}/logs" "$OUT_ROOT"

exec > >(tee -a "$RUN_LOG") 2>&1
log() { printf '%s [%s] %s\n' "$(date -u +%H:%M:%SZ)" "$1" "$2"; }

VLLM_PID=""
cleanup() {
    if [[ -n "$VLLM_PID" ]] && ps -p "$VLLM_PID" >/dev/null 2>&1; then
        log INFO "Stopping vLLM (pid $VLLM_PID) ..."
        kill "$VLLM_PID" 2>/dev/null || true
        sleep 3
    fi
    pkill -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
    log INFO "vLLM stopped; GPU released."
}
trap cleanup EXIT INT TERM

# ---- 1. start vLLM ----------------------------------------------------------
if curl -s -m 2 "http://localhost:${PORT}/v1/models" 2>/dev/null | grep -q "Qwen3-8B"; then
    log INFO "vLLM already serving on :${PORT}; reusing it."
else
    log INFO "Starting vLLM (log: $VLLM_LOG) ..."
    nohup bash scripts/eval/start_vllm.sh > "$VLLM_LOG" 2>&1 &
    VLLM_PID=$!
    log INFO "vLLM pid $VLLM_PID; waiting for readiness (<= 10 min) ..."
    ready=0
    for _ in $(seq 1 120); do
        if curl -s -m 2 "http://localhost:${PORT}/v1/models" 2>/dev/null | grep -q "Qwen3-8B"; then ready=1; break; fi
        if [[ -n "$VLLM_PID" ]] && ! ps -p "$VLLM_PID" >/dev/null 2>&1; then
            log ERROR "vLLM process died during startup. Tail of vLLM log:"; tail -25 "$VLLM_LOG"; exit 1
        fi
        sleep 5
    done
    if [[ "$ready" -ne 1 ]]; then log ERROR "vLLM did not become ready in time."; exit 1; fi
    log INFO "vLLM ready."
fi

# ---- 2. full-cohort LOPO (resumable) ---------------------------------------
log INFO "Running full-cohort Cell S LOPO -> $OUT_ROOT"
PYTHONPATH=. "$PYTORCH_PY" scripts/eval/run_lopo.py \
    --all --use-lea --out-root "$OUT_ROOT"
RC=$?
log INFO "run_lopo.py exit code: $RC"
[[ "$RC" -ne 0 ]] && { log ERROR "run_lopo failed; leaving vLLM teardown to trap."; exit "$RC"; }

# ---- 3. vLLM teardown happens in trap; 4. aggregate ------------------------
cleanup; trap - EXIT INT TERM   # free GPU before the (CPU-only) aggregation
log INFO "Aggregating stratified + fair-cohort cross-tabs ..."
PYTHONPATH=. "$PYTORCH_PY" scripts/eval/aggregate_lopo.py \
    --lopo-root "$OUT_ROOT" --cell S
log INFO "=== DONE. Results in $OUT_ROOT/_lopo_full_results_cell_S.{md,json} ==="
