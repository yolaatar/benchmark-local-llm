#!/usr/bin/env bash
# SSH tunnel to the lab servers on tassan (macOS/Linux version of tassan-tunnel.ps1). Leave it open.
#   vLLM   tassan 127.0.0.1:8000  -> here 127.0.0.1:8001
#   Ollama tassan 127.0.0.1:11434 -> here 127.0.0.1:11435
# Usage: TASSAN_USER=you@ge.polymtl.ca ./tassan-tunnel.sh
set -euo pipefail
USER_AT=${TASSAN_USER:?set TASSAN_USER to your tassan login, e.g. you@ge.polymtl.ca}
HOST=${TASSAN_HOST:-tassan.neuro.polymtl.ca}
echo "Tunnel to $HOST open (vLLM on 127.0.0.1:8001, Ollama on 127.0.0.1:11435). Ctrl+C to close."
exec ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -l "$USER_AT" \
    -L 8001:127.0.0.1:8000 -L 11435:127.0.0.1:11434 "$HOST"
