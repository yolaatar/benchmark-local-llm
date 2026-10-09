# Shared by the macOS/Linux client scripts (claude-tassan.sh, opencode-tassan.sh, check-tassan.sh).
# Sets base, token, model and window for the backend chosen with TASSAN_BACKEND (vllm by default),
# through the ports of tassan-tunnel.sh.
#   key:   TASSAN_VLLM_KEY, else the file ~/.tassan_vllm_key
#   model: TASSAN_MODEL, else whatever the server serves (so a model change on tassan needs no client change)

if [ "${TASSAN_BACKEND:-vllm}" = ollama ]; then
    base=http://127.0.0.1:11435; token=ollama; window=65536
else
    base=http://127.0.0.1:8001; window=131072   # = MAX_MODEL_LEN in lab_server/cluster/vllm.env
    token=${TASSAN_VLLM_KEY:-$(cat "$HOME/.tassan_vllm_key" 2>/dev/null || true)}
    [ -n "$token" ] || { echo "No lab key: save it once with  (umask 077; printf '%s' '<key>' > ~/.tassan_vllm_key)"; exit 1; }
fi

models=$(curl -sf --max-time 10 -H "Authorization: Bearer $token" "$base/v1/models") || {
    echo "No answer on $base. Is tassan-tunnel.sh running (and the VPN on)? Is the server up on tassan?"; exit 1; }
model=${TASSAN_MODEL:-$(printf '%s' "$models" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])')}
