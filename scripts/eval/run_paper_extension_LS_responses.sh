#!/usr/bin/env bash
#
# Re-run Cell L + Cell S with --responses-dir to capture per-case sidecars
# needed for RAGAS / DeepEval evaluation (paper extension v3, Thread B).
#
# Cell D and Cell K are NOT re-run (D is deterministic + identical;
# K is Exomiser CLI which doesn't produce RAG sidecars).
#
# Lanes:
#   1. Backup existing v2 L+S case JSONs to .v2_backup_<timestamp>/
#   2. Cell L (GPU, no vLLM)     — re-runs with --responses-dir
#   3. Start vLLM (util=0.75, max-len=32768, max-num-seqs=1)
#   4. Cell S (GPU + vLLM + LEA) — re-runs with --use-lea + --responses-dir
#   5. Kill vLLM
#
# Expected wall: ~14 hours (L ~6h, S ~8h).
#
# Outputs:
#   data/eval_1050/cell_L_rerank_inside_d/                 (overwritten — v3)
#   data/eval_1050/cell_S_rerank_inside_plus_lea/          (overwritten — v3)
#   data/eval_1050/cell_L_responses/                       (NEW — RAGAS sidecars)
#   data/eval_1050/cell_S_responses/                       (NEW — RAGAS + DeepEval sidecars)
#   data/eval_1050/cell_L_rerank_inside_d.v2_backup_<ts>/  (frozen v2)
#   data/eval_1050/cell_S_rerank_inside_plus_lea.v2_backup_<ts>/
#
# Usage (in a tmux session):
#   tmux new -ds paper_ls_v3 'cd /home/hana77/ia_jo/uax_tfm/geno_agent &&
#       source /home/hana77/pytorch-env/bin/activate &&
#       MIN_FREE_MIB=4000 bash scripts/eval/run_paper_extension_LS_responses.sh'

set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"

TEST_CASES="${TEST_CASES:-${PROJECT_ROOT}/data/test_cases_1050/test_cases.jsonl}"
OUT_ROOT="${OUT_ROOT:-${PROJECT_ROOT}/data/eval_1050}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs}"
PAPER_LOG="${LOG_DIR}/paper_v3_LS_$(date -u +%Y%m%dT%H%M%SZ).log"
VLLM_LOG="${LOG_DIR}/vllm_paper_v3.log"

MIN_FREE_MIB="${MIN_FREE_MIB:-4000}"
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
        log ERROR "[$stage] only ${free} MiB GPU free - below threshold. Aborting."
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
        if [[ -f "$vllm_pid_file" ]] && ! kill -0 "$(cat "$vllm_pid_file")" 2>/dev/null; then
            log ERROR "vLLM wrapper exited prematurely. See ${VLLM_LOG}."
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

vllm_pid_file="${LOG_DIR}/vllm_paper_v3.pid"

start_vllm_capped() {
    log INFO "Starting vLLM (util=0.75, max-len=32768, max-num-seqs=1)..."
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

# ---------- pre-flight -------------------------------------------------------

log INFO "============================================================"
log INFO "Paper extension v3 - Cell L + Cell S re-run with response sidecars"
log INFO "  test cases:   ${TEST_CASES}"
log INFO "  out root:     ${OUT_ROOT}"
log INFO "  paper log:    ${PAPER_LOG}"
log INFO "  vllm log:     ${VLLM_LOG}"
log INFO "  min free:     ${MIN_FREE_MIB} MiB"
log INFO "============================================================"

if [[ ! -f "$TEST_CASES" ]]; then
    log ERROR "test cases not found: $TEST_CASES"
    exit 2
fi
n_cases=$(wc -l < "$TEST_CASES")
log INFO "Test cases: ${n_cases}"

if [[ "$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:6533/collections || echo 000)" != "200" ]]; then
    log ERROR "Qdrant (port 6533) not reachable."
    exit 3
fi
log INFO "Qdrant: UP"

if [[ "$(vllm_health)" == "200" ]]; then
    log ERROR "vLLM is already running. Stop it; this script manages its lifecycle."
    exit 4
fi

# ---------- backup v2 dirs ---------------------------------------------------

BACKUP_TS=$(date -u +%Y%m%dT%H%M%SZ)
for cell in cell_L_rerank_inside_d cell_S_rerank_inside_plus_lea; do
    src="${OUT_ROOT}/${cell}"
    if [[ -d "$src" ]] && [[ -n "$(ls -A "$src" 2>/dev/null)" ]]; then
        backup="${OUT_ROOT}/${cell}.v2_backup_${BACKUP_TS}"
        log INFO "Backing up ${src} -> ${backup}"
        cp -r "$src" "$backup"
    fi
done

# ---------- Stage L ----------------------------------------------------------

assert_gpu_free "before-L"
log INFO ">>> Cell L (re-run with --responses-dir)"
PYTHONPATH=. python scripts/eval/rerank_inside_d.py \
    --test-cases "$TEST_CASES" \
    --out-dir "$OUT_ROOT/cell_L_rerank_inside_d" \
    --responses-dir "$OUT_ROOT/cell_L_responses" \
    --overwrite \
    --limit 0 \
    2>&1 | sed -u 's/^/    [L] /'
log INFO "<<< Cell L done"

# ---------- Stage S ----------------------------------------------------------

assert_gpu_free "before-vllm"
start_vllm_capped
sleep 2
assert_gpu_free "after-vllm-loaded"

log INFO ">>> Cell S (re-run with --use-lea + --responses-dir)"
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

# ---------- summary ----------------------------------------------------------

log INFO "============================================================"
log INFO "v3 re-run complete."
for cell in cell_L_rerank_inside_d cell_S_rerank_inside_plus_lea; do
    n=$(ls "$OUT_ROOT/$cell"/*.json 2>/dev/null | wc -l)
    log INFO "  ${cell}: ${n} case JSONs"
done
for sidecar in cell_L_responses cell_S_responses; do
    n=$(ls "$OUT_ROOT/$sidecar"/*.json 2>/dev/null | wc -l)
    log INFO "  ${sidecar}: ${n} sidecar JSONs"
done
log INFO "Next: re-aggregate (K + D + L + S + M) and run RAGAS/DeepEval."
log INFO "============================================================"
