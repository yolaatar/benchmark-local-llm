#!/usr/bin/env bash
# Start the Ollama server installed in round 2 (~/llm-bench) in tmux "ollama", pinned to our card,
# and make sure the 64k-context variant used by the agents exists.
# Usage: bash serve_ollama.sh [NUM_PARALLEL]      (default 1; Phase 3 also runs it with 4)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/vllm.env"
PARALLEL=${1:-1}
BASE_MODEL=${OLLAMA_MODEL:-qwen3-coder-next}
CC_MODEL=$BASE_MODEL-cc
LOG=$LLMBENCH/logs/ollama.log

[ -f "$LLMBENCH/env.sh" ] || { echo "missing $LLMBENCH/env.sh (Ollama install from round 2)"; exit 1; }
source "$LLMBENCH/env.sh"
mkdir -p "$LLMBENCH/logs"

if tmux has-session -t ollama 2>/dev/null; then
    echo "Ollama already running (tmux 'ollama'). To change NUM_PARALLEL: bash $HERE/stop_ollama.sh first"
else
    if tmux has-session -t vllm 2>/dev/null; then
        echo "vLLM is running on card $GPU, stop it first: bash $HERE/stop_vllm.sh"; exit 1
    fi
    echo "=== $(date -Is) start ollama NUM_PARALLEL=$PARALLEL on GPU $GPU" >> "$LOG"
    # OLLAMA_VULKAN=0: otherwise Ollama also sees the other card through Vulkan
    tmux new-session -d -s ollama "source $LLMBENCH/env.sh; export CUDA_VISIBLE_DEVICES=$GPU OLLAMA_VULKAN=0 \
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=$PARALLEL; exec ollama serve 2>&1 | tee -a $LOG"
    for i in $(seq 1 30); do
        curl -sf http://127.0.0.1:11434/api/version >/dev/null && break
        tmux has-session -t ollama 2>/dev/null || { echo "Ollama exited:"; tail -n 20 "$LOG"; exit 1; }
        sleep 1
    done
    curl -sf http://127.0.0.1:11434/api/version >/dev/null || { echo "Ollama not answering, see $LOG"; exit 1; }
    echo "Ollama up on 127.0.0.1:11434, NUM_PARALLEL=$PARALLEL"
fi

# The OpenAI and Anthropic endpoints can't pass num_ctx per request, so bake 64k into a variant.
if ! ollama show "$CC_MODEL" >/dev/null 2>&1; then
    printf 'FROM %s\nPARAMETER num_ctx 65536\n' "$BASE_MODEL" > "$LLMBENCH/Modelfile.cc"
    ollama create "$CC_MODEL" -f "$LLMBENCH/Modelfile.cc"
fi
ollama list
