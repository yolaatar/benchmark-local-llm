#!/usr/bin/env bash
# Stop the vLLM server and give the GPU memory back.
SESSION=vllm
if ! tmux has-session -t "$SESSION" 2>/dev/null; then echo "vLLM is not running"; exit 0; fi
tmux send-keys -t "$SESSION" C-c
for i in $(seq 1 30); do
    tmux has-session -t "$SESSION" 2>/dev/null || { echo "vLLM stopped"; exit 0; }
    sleep 1
done
tmux kill-session -t "$SESSION" && echo "vLLM killed"
