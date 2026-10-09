#!/usr/bin/env bash
# Stop the Ollama server, close its tmux session, and make sure no Ollama process still holds the GPU.
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/vllm.env"
source "$HERE/tmux_lib.sh"
stop_session ollama 'ollama (serve|runner)'
if curl -sf http://127.0.0.1:11434/api/version >/dev/null; then
    echo "Something still answers on 11434 (another user's Ollama?)"; exit 1
fi
echo "Ollama stopped. GPU $GPU:"
nvidia-smi -i "$GPU" --query-gpu=index,memory.used,memory.total --format=csv,noheader
