#!/usr/bin/env bash
#
# Start vLLM serving Qwen3-8B locally on port 8001 (master plan §11.4).
#
# IMPORTANT — driver compatibility (recorded in master plan §10):
#   vLLM 0.20.1 (the only version on PyPI as of 2026-05-09) requires
#   torch==2.11+cu130 (CUDA 13). The host's NVIDIA driver currently
#   reports CUDA 12.9, so vLLM 0.20.1 cannot launch the engine.
#   Resolution paths (any one):
#     (a) Upgrade the NVIDIA driver to a CUDA-13-capable build (>=545.x).
#     (b) Install vLLM into a dedicated venv that pins torch 2.11+cu130
#         while keeping pytorch-env on the cu128 nightly that PubMedBERT,
#         qdrant-client, and the rest of the project depend on.
#     (c) Use Ollama as a development fallback per §11.1; it speaks the
#         same OpenAI-compatible API used by src/tools/llm.py.
#
# This script is intentionally simple — it runs vLLM in the foreground via
# `python -m vllm.entrypoints.openai.api_server`. For unattended runs use
# tmux, screen, or systemd:
#
#   tmux new -s vllm
#   bash scripts/eval/start_vllm.sh
#   # detach: Ctrl+b then d
#
# Once started, verify with:
#   python scripts/eval/probe_vllm.py
#
# Hardware: Qwen3-8B in FP16 needs ~16 GB VRAM + KV cache (~8 GB).
# Fits in the host's RTX 5090 (32 GB) with headroom for PubMedBERT
# embedding + Qdrant queries (master plan §11.4 budget).

set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT_ROOT="$(pwd)"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

MODEL_DIR="${HOME}/rare-disease-rag/models/Qwen3-8B"
PORT="${VLLM_PORT:-8001}"
HOST="${VLLM_HOST:-127.0.0.1}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs}"
LOG="${LOG_DIR}/vllm_qwen3_8b.log"

mkdir -p "$LOG_DIR"

if [[ ! -d "$MODEL_DIR" ]]; then
    cat >&2 <<EOF
ERROR: Qwen3-8B weights not found at $MODEL_DIR
Download with:
    source /home/hana77/pytorch-env/bin/activate
    huggingface-cli download Qwen/Qwen3-8B --local-dir $MODEL_DIR
EOF
    exit 1
fi

if ! command -v python &> /dev/null; then
    echo "ERROR: python not on PATH. Activate pytorch-env first." >&2
    exit 1
fi

# Verify vllm is importable
if ! python -c "import vllm" 2>/dev/null; then
    cat >&2 <<EOF
ERROR: vllm not installed in current Python env.
Install with:
    source /home/hana77/pytorch-env/bin/activate
    pip install vllm
EOF
    exit 1
fi

echo "============================================================"
echo "Starting vLLM (Qwen3-8B)"
echo "  model:      ${MODEL_DIR}"
echo "  endpoint:   http://${HOST}:${PORT}/v1"
echo "  log:        ${LOG}"
echo "  served name: Qwen/Qwen3-8B  (must match LlmConfig.model)"
echo "============================================================"
echo
echo "VRAM budget: ~16 GB FP16 weights + ~8-12 GB KV cache (RTX 5090 has 32 GB)."
echo "Probe with:  python scripts/eval/probe_vllm.py"
echo "Stop with:   Ctrl+C  (or kill the python process)"
echo

# --enable-prefix-caching: vLLM reuses the KV cache for any prompt
# whose first K tokens match an already-cached prefix. The Critic
# batches all share an identical long system prompt (~80 tokens),
# so caching reduces per-batch prefill cost dramatically. Empirically
# Cell H smoke without caching took ~13 min/case; expected ~2-4 min
# with caching, making the full LLM-Critic ablation overnight-feasible.
exec python -m vllm.entrypoints.openai.api_server \
    --model "${MODEL_DIR}" \
    --served-model-name "Qwen/Qwen3-8B" \
    --host "${HOST}" \
    --port "${PORT}" \
    --dtype float16 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.85 \
    --reasoning-parser qwen3 \
    --enable-prefix-caching \
    2>&1 | tee "${LOG}"
