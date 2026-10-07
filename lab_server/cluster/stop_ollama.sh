#!/usr/bin/env bash
# Stop the Ollama server and give the GPU memory back.
if ! tmux has-session -t ollama 2>/dev/null; then echo "Ollama is not running"; exit 0; fi
tmux kill-session -t ollama
for i in $(seq 1 15); do
    curl -sf http://127.0.0.1:11434/api/version >/dev/null || { echo "Ollama stopped"; exit 0; }
    sleep 1
done
echo "Ollama still answering on 11434 after 15 s (started outside tmux?)"; exit 1
