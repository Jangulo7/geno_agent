#!/usr/bin/env bash
#
# Recovery launcher: run only Cell S after D and L already completed.
#
# The main sequencer (run_paper_extension.sh) crashed during vLLM startup
# because start_vllm.sh searched for vllm in pytorch-env, which doesn't
# have it — vllm lives in /home/hana77/vllm-env/. start_vllm.sh has been
# patched to use VLLM_PYTHON. This script reuses the same lifecycle
# (start vLLM, wait for ready, run S, teardown) but skips D and L.
#
# Usage (inside a tmux session with pytorch-env active, since the eval
# script imports torch/sentence-transformers/qdrant-client from there):
#   tmux new -s paper_s
#   source /home/hana77/pytorch-env/bin/activate
#   bash scripts/eval/run_paper_extension_S_only.sh

set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"

TEST_CASES="${TEST_CASES:-${PROJECT_ROOT}/data/test_cases_500/test_cases.jsonl}"
OUT_ROOT="${OUT_ROOT:-${PROJECT_ROOT}/data/eval_500}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs}"
PAPER_LOG="${LOG_DIR}/paper_extension_S_$(date -u +%Y%m%dT%H%M%SZ).log"
VLLM_LOG="${LOG_DIR}/vllm_paper.log"

MIN_FREE_MIB="${MIN_FREE_MIB:-6000}"
VLLM_READY_TIMEOUT="${VLLM_READY_TIMEOUT:-900}"

mkdir -p "$LOG_DIR" "$OUT_ROOT"
exec > >(tee -a "$PAPER_LOG") 2>&1

log() { printf '%s [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"; }

gpu_free_mib() {
    nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' '
}

assert_gpu_free() {
    local stage="$1"
    local free
    free=$(gpu_free_mib)
    log INFO "[$stage] nvidia-smi: free=${free} MiB  threshold=${MIN_FREE_MIB} MiB"
    if (( free < MIN_FREE_MIB )); then
        log ERROR "[$stage] only ${free} MiB GPU free. Aborting."
        exit 11
    fi
}

vllm_health() {
    curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:8001/v1/models" 2>/dev/null || echo "000"
}

wait_for_vllm_ready() {
    local elapsed=0
    while (( elapsed < VLLM_READY_TIMEOUT )); do
        if [[ "$(vllm_health)" == "200" ]]; then
            log INFO "vLLM ready (after ${elapsed}s)"
            return 0
        fi
        # Surface the wrapper exiting early
        if [[ -f "$vllm_pid_file" ]] && ! kill -0 "$(cat "$vllm_pid_file")" 2>/dev/null; then
            log ERROR "vLLM wrapper process exited prematurely. See ${VLLM_LOG}."
            tail -30 "${VLLM_LOG}" >&2 || true
            return 13
        fi
        sleep 5
        elapsed=$(( elapsed + 5 ))
    done
    log ERROR "vLLM did not become ready within ${VLLM_READY_TIMEOUT}s"
    tail -30 "${VLLM_LOG}" >&2 || true
    return 12
}

vllm_pid_file="${LOG_DIR}/vllm_paper.pid"

start_vllm_capped() {
    log INFO "Starting vLLM (util=0.55, max-len=16384, swap=4)..."
    bash "${PROJECT_ROOT}/scripts/eval/start_vllm.sh" >"${VLLM_LOG}" 2>&1 &
    echo $! > "$vllm_pid_file"
    log INFO "vLLM wrapper pid=$(cat "$vllm_pid_file") (log: ${VLLM_LOG})"
    wait_for_vllm_ready
}

kill_vllm() {
    log INFO "Tearing down vLLM..."
    if [[ -f "$vllm_pid_file" ]]; then
        local wrapper_pid
        wrapper_pid=$(cat "$vllm_pid_file")
        pkill -TERM -P "$wrapper_pid" 2>/dev/null || true
        kill -TERM "$wrapper_pid" 2>/dev/null || true
        sleep 3
        pkill -KILL -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
        rm -f "$vllm_pid_file"
    fi
    pkill -KILL -f "vllm.entrypoints" 2>/dev/null || true
    sleep 5
    log INFO "vLLM down. nvidia-smi free=$(gpu_free_mib) MiB"
}

cleanup_on_exit() {
    local rc=$?
    if [[ -f "$vllm_pid_file" ]]; then
        kill_vllm
    fi
    log INFO "Exit rc=${rc}"
    exit $rc
}
trap cleanup_on_exit EXIT INT TERM

log INFO "============================================================"
log INFO "Cell S recovery (n=460) — vLLM up -> S -> vLLM down"
log INFO "  test_cases:  ${TEST_CASES}"
log INFO "  out_root:    ${OUT_ROOT}"
log INFO "  paper log:   ${PAPER_LOG}"
log INFO "  vllm log:    ${VLLM_LOG}"
log INFO "============================================================"

if [[ ! -f "$TEST_CASES" ]]; then
    log ERROR "test cases not found: $TEST_CASES"
    exit 2
fi
if [[ "$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:6533/collections || echo 000)" != "200" ]]; then
    log ERROR "Qdrant not reachable on 6533"
    exit 3
fi
if [[ "$(vllm_health)" == "200" ]]; then
    log ERROR "vLLM already running. Stop it; the sequencer manages its lifecycle."
    exit 4
fi

assert_gpu_free "before-vllm"
start_vllm_capped
sleep 2
assert_gpu_free "after-vllm-loaded"

log INFO ">>> Cell S - rerank + LEA"
PYTHONPATH=. python scripts/eval/rerank_inside_d.py \
    --test-cases "$TEST_CASES" \
    --out-dir "$OUT_ROOT/cell_S_rerank_inside_plus_lea" \
    --responses-dir "$OUT_ROOT/cell_S_responses" \
    --use-lea \
    --overwrite \
    --limit 0 \
    2>&1 | sed -u 's/^/    [S] /'
log INFO "<<< Cell S done"

kill_vllm

log INFO "============================================================"
n=$(ls "$OUT_ROOT/cell_S_rerank_inside_plus_lea"/*.json 2>/dev/null | wc -l)
log INFO "Cell S case JSONs: ${n}/459"
log INFO "============================================================"
