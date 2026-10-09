#!/usr/bin/env bash
# Stop the vLLM server, close its tmux session, and make sure no vLLM process still holds the GPU.
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/vllm.env"
source "$HERE/tmux_lib.sh"
stop_session vllm 'vllm serve|VLLM::EngineCore'
echo "vLLM stopped. GPU $GPU:"
nvidia-smi -i "$GPU" --query-gpu=index,memory.used,memory.total --format=csv,noheader
