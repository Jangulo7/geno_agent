#!/usr/bin/env bash
#
# Paper extension (n=460) — sequenced GPU launcher.
#
# Lanes:
#   CPU lane:  Cell K (Exomiser HPO-only)            — runs in parallel via tmux
#   GPU lane:  D  →  L  →  [start vLLM]  →  S  →  [kill vLLM]
#
# Why sequencing matters: the n=75 thesis run ran vLLM at
# --gpu-memory-utilization 0.85 (~27 GB) with CE + dense alongside,
# leaving only ~5 GB headroom. At n=460 scale, a single allocation
# spike can crash the driver. This script never overlaps GPU-resident
# consumers in time:
#   D = Qdrant + dense PubMedBERT only          (~3 GB peak)
#   L = D + MedCPT-Cross-Encoder                (~5 GB peak)
#   S = CE + vLLM (with capped --gpu-memory-utilization 0.55) (~24 GB peak)
# vLLM is only alive during S, then explicitly killed.
#
# Pre-flight nvidia-smi check before each stage; abort if free < 6 GB.
#
# Usage (intended to be invoked inside a tmux session):
#   tmux new -s paper_gpu
#   source /home/hana77/pytorch-env/bin/activate
#   bash scripts/eval/run_paper_extension.sh
#
# Outputs land under data/eval_500/cell_<X>_*/.

set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"

TEST_CASES="${TEST_CASES:-${PROJECT_ROOT}/data/test_cases_500/test_cases.jsonl}"
OUT_ROOT="${OUT_ROOT:-${PROJECT_ROOT}/data/eval_500}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs}"
PAPER_LOG="${LOG_DIR}/paper_extension_$(date -u +%Y%m%dT%H%M%SZ).log"
VLLM_LOG="${LOG_DIR}/vllm_paper.log"

MIN_FREE_MIB="${MIN_FREE_MIB:-6000}"     # abort if GPU free < this
VLLM_READY_TIMEOUT="${VLLM_READY_TIMEOUT:-600}"   # seconds

mkdir -p "$LOG_DIR" "$OUT_ROOT"

# Mirror stdout/stderr to a session log
exec > >(tee -a "$PAPER_LOG") 2>&1

log() { printf '%s [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"; }

# ---------- helpers ----------------------------------------------------------

gpu_free_mib() {
    nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' '
}

gpu_used_mib() {
    nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' '
}

assert_gpu_free() {
    local stage="$1"
    local free
    free=$(gpu_free_mib)
    log INFO "[$stage] nvidia-smi: free=${free} MiB  used=$(gpu_used_mib) MiB  threshold=${MIN_FREE_MIB} MiB"
    if (( free < MIN_FREE_MIB )); then
        log ERROR "[$stage] only ${free} MiB GPU free — below safety threshold (${MIN_FREE_MIB}). Aborting."
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
        sleep 5
        elapsed=$(( elapsed + 5 ))
    done
    log ERROR "vLLM did not become ready within ${VLLM_READY_TIMEOUT}s"
    return 12
}

vllm_pid_file="${LOG_DIR}/vllm_paper.pid"

start_vllm_capped() {
    log INFO "Starting vLLM with capped budget (util=0.55, max-len=16384, swap=4)..."
    # Background; capture pid.
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
        # Kill the api_server children (vLLM forks engine subprocesses).
        pkill -TERM -P "$wrapper_pid" 2>/dev/null || true
        kill -TERM "$wrapper_pid" 2>/dev/null || true
        sleep 3
        pkill -KILL -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
        rm -f "$vllm_pid_file"
    fi
    # Belt-and-braces: anything left holding GPU?
    pkill -KILL -f "vllm" 2>/dev/null || true
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
log INFO "Paper extension (n=460) — sequenced GPU launcher"
log INFO "  test_cases:  ${TEST_CASES}"
log INFO "  out_root:    ${OUT_ROOT}"
log INFO "  paper log:   ${PAPER_LOG}"
log INFO "  vllm log:    ${VLLM_LOG}"
log INFO "  min free:    ${MIN_FREE_MIB} MiB"
log INFO "============================================================"

if [[ ! -f "$TEST_CASES" ]]; then
    log ERROR "test cases not found: $TEST_CASES"
    exit 2
fi
n_cases=$(wc -l < "$TEST_CASES")
log INFO "Test cases: ${n_cases}"

# Qdrant must be up
if [[ "$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:6533/collections || echo 000)" != "200" ]]; then
    log ERROR "Qdrant (port 6533) is not reachable."
    exit 3
fi
log INFO "Qdrant: UP"

# vLLM must NOT be running yet (D and L don't need it; would waste VRAM)
if [[ "$(vllm_health)" == "200" ]]; then
    log ERROR "vLLM is already running. Stop it first; the sequencer manages its lifecycle."
    exit 4
fi

# ---------- Stage D ----------------------------------------------------------

assert_gpu_free "before-D"
log INFO ">>> Cell D — multi-agent · hybrid (deterministic)"
PYTHONPATH=. python scripts/eval/run_factorial.py \
    --cells D \
    --test-cases "$TEST_CASES" \
    --out-root "$OUT_ROOT" \
    2>&1 | sed -u 's/^/    [D] /'
log INFO "<<< Cell D done"

# ---------- Stage L ----------------------------------------------------------

assert_gpu_free "before-L"
log INFO ">>> Cell L — rerank-inside-D"
PYTHONPATH=. python scripts/eval/rerank_inside_d.py \
    --test-cases "$TEST_CASES" \
    --out-dir "$OUT_ROOT/cell_L_rerank_inside_d" \
    --limit 0 \
    2>&1 | sed -u 's/^/    [L] /' || true
# Tolerate --limit 0 (older script versions); fall back to no --limit
if [[ ! -d "$OUT_ROOT/cell_L_rerank_inside_d" ]] || [[ -z "$(ls -A "$OUT_ROOT/cell_L_rerank_inside_d" 2>/dev/null)" ]]; then
    log WARN "Cell L produced no output with --limit 0 — retrying without --limit"
    PYTHONPATH=. python scripts/eval/rerank_inside_d.py \
        --test-cases "$TEST_CASES" \
        --out-dir "$OUT_ROOT/cell_L_rerank_inside_d" \
        2>&1 | sed -u 's/^/    [L] /'
fi
log INFO "<<< Cell L done"

# ---------- Stage S (start vLLM, run S, tear vLLM down) ----------------------

assert_gpu_free "before-vllm"
start_vllm_capped
sleep 2
assert_gpu_free "after-vllm-loaded"

log INFO ">>> Cell S — rerank + LEA"
PYTHONPATH=. python scripts/eval/rerank_inside_d.py \
    --test-cases "$TEST_CASES" \
    --out-dir "$OUT_ROOT/cell_S_rerank_inside_plus_lea" \
    --use-lea \
    2>&1 | sed -u 's/^/    [S] /'
log INFO "<<< Cell S done"

kill_vllm

# ---------- summary ----------------------------------------------------------

log INFO "============================================================"
log INFO "All GPU stages complete."
for cell in cell_D_multi_hybrid cell_L_rerank_inside_d cell_S_rerank_inside_plus_lea; do
    n=$(ls "$OUT_ROOT/$cell"/*.json 2>/dev/null | wc -l)
    log INFO "  ${cell}: ${n} case JSONs"
done
log INFO "Next: run aggregate_metrics.py over $OUT_ROOT and write paper-extension report."
log INFO "============================================================"
