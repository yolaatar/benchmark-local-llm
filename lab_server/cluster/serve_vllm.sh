#!/usr/bin/env bash
# Start the vLLM server in a detached tmux session named "vllm", then wait until it answers.
# Usage: bash serve_vllm.sh        (logs: ~/llm-bench/logs/vllm.log, attach: tmux attach -t vllm)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/vllm.env"
SESSION=vllm
KEY=$LLMBENCH/vllm.key
LOG=$LLMBENCH/logs/vllm.log

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "vLLM already running (tmux session '$SESSION'). Stop it first: bash $HERE/stop_vllm.sh"
    exit 0
fi
[ -x "$LLMBENCH/vllm-venv/bin/vllm" ] || { echo "vLLM not installed, run setup_vllm.sh first"; exit 1; }
[ -s "$KEY" ] || { echo "missing $KEY, run setup_vllm.sh first"; exit 1; }

# vLLM grabs GPU_UTIL of the whole card at start-up and fails if that much is not free.
read -r free total < <(nvidia-smi -i "$GPU" --query-gpu=memory.free,memory.total --format=csv,noheader,nounits | tr -d ',')
need=$(python3 -c "print(int($GPU_UTIL * $total))")
if [ "$free" -lt "$need" ]; then
    echo "Card $GPU has $free MiB free, vLLM needs $need MiB (GPU_UTIL=$GPU_UTIL). Processes on it:"
    nvidia-smi -i "$GPU" --query-compute-apps=pid,process_name,used_memory --format=csv
    echo "If it is our Ollama server: tmux kill-session -t ollama   (or lower GPU_UTIL in vllm.env)"
    exit 1
fi

CMD="export CUDA_VISIBLE_DEVICES=$GPU HF_HOME=$HF_HOME VLLM_API_KEY=\$(cat $KEY);
exec $LLMBENCH/vllm-venv/bin/vllm serve $MODEL \
  --served-model-name $SERVED_NAME \
  --host 127.0.0.1 --port $PORT \
  --max-model-len $MAX_MODEL_LEN \
  --gpu-memory-utilization $GPU_UTIL \
  --max-num-seqs $MAX_NUM_SEQS \
  --enable-prefix-caching \
  --enable-auto-tool-choice --tool-call-parser $TOOL_PARSER \
  $EXTRA_ARGS 2>&1 | tee -a $LOG"
echo "=== $(date -Is) start $MODEL as $SERVED_NAME on GPU $GPU" >> "$LOG"
tmux new-session -d -s "$SESSION" "bash -c '$CMD'"

echo "Starting $MODEL on GPU $GPU, port $PORT (first start: weight loading + compilation, several minutes)"
for i in $(seq 1 180); do
    if curl -sf -H "Authorization: Bearer $(cat "$KEY")" "http://127.0.0.1:$PORT/v1/models" >/dev/null; then
        echo "Ready after $((i * 5)) s:"
        curl -s -H "Authorization: Bearer $(cat "$KEY")" "http://127.0.0.1:$PORT/v1/models"; echo
        nvidia-smi -i "$GPU" --query-gpu=index,memory.used,memory.total --format=csv
        exit 0
    fi
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "vLLM exited during start-up. Last log lines:"; tail -n 40 "$LOG"; exit 1
    fi
    sleep 5
done
echo "Still not ready after 15 min. Check: tail -f $LOG"
exit 1
