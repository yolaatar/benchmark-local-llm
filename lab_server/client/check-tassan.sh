#!/usr/bin/env bash
# Through the open tunnel: which model answers, and does it make a real tool call (macOS/Linux version
# of check-tassan.ps1). Usage: ./check-tassan.sh        (Ollama server: TASSAN_BACKEND=ollama)
set -euo pipefail
source "$(dirname "$0")/tassan_lib.sh"
echo "Server answers, model: $model"
# Tool-calling smoke test: a usable agent model answers with a structured call, not with prose.
# max_tokens leaves room for a thinking model to reason before calling the tool.
body=$(python3 -c 'import json,sys; print(json.dumps({"model": sys.argv[1], "max_tokens": 2000,
  "messages": [{"role": "user", "content": "What is in the file stats.py? Use the tool."}],
  "tools": [{"type": "function", "function": {"name": "read_file", "description": "Read a file from the project",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]}))' "$model")
start=$(date +%s)
resp=$(curl -sf --max-time 600 -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    -d "$body" "$base/v1/chat/completions") || { echo "The chat request failed (server overloaded or restarting?)"; exit 1; }
printf '%s' "$resp" | python3 -c '
import json, sys
m = json.load(sys.stdin)["choices"][0]["message"]
calls = m.get("tool_calls")
if calls:
    f = calls[0]["function"]; print("Tool call OK in", sys.argv[1], "s:", f["name"] + "(" + f["arguments"] + ")")
else:
    print("No tool call. The model answered:", m.get("content")); sys.exit(1)' "$(( $(date +%s) - start ))"
