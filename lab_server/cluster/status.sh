#!/usr/bin/env bash
# What is running on tassan right now: servers, GPU memory, and vLLM's live request counts.
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/vllm.env"
echo "== tmux sessions"; tmux ls 2>/dev/null || echo "none"
echo "== GPUs"; nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv
echo "== GPU processes"; nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader
echo "== vLLM"
if [ -s "$LLMBENCH/vllm.key" ] && curl -sf -H "Authorization: Bearer $(cat "$LLMBENCH/vllm.key")" "http://127.0.0.1:$PORT/v1/models" -o /dev/null; then
    echo "up on 127.0.0.1:$PORT"
    curl -s "http://127.0.0.1:$PORT/metrics" | grep -E '^vllm:(num_requests_running|num_requests_waiting|kv_cache_usage_perc|gpu_cache_usage_perc)' || true
else
    echo "down"
fi
echo "== Ollama"
curl -sf http://127.0.0.1:11434/api/ps 2>/dev/null || echo "down"
