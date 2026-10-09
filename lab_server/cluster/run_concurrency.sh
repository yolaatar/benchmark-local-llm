#!/usr/bin/env bash
# Phase 3: multi-user load test on tassan, same prompts and sizes for every server setting.
# Results: ~/llm-bench/results/conc_*.json (fetch them with deploy-tassan.ps1 -Fetch).
# Usage: bash run_concurrency.sh [all|vllm|ollama]      (default all; inside tmux, it takes ~1-2 h)
#   NUM_CTX=32768 bash run_concurrency.sh ollama       if Ollama can't fit 4 x 64k with NUM_PARALLEL=4
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/vllm.env"
WHAT=${1:-all}
NUM_CTX=${NUM_CTX:-65536}
LEVELS=${LEVELS:-1,2,4,8,16}
OLLAMA_MODEL=${OLLAMA_MODEL:-qwen3-coder-next}
BENCH="python3 $LLMBENCH/concurrency_bench.py"
OUT=$LLMBENCH/results
mkdir -p "$OUT"
[ -f "$LLMBENCH/concurrency_bench.py" ] || { echo "missing $LLMBENCH/concurrency_bench.py, run deploy-tassan.ps1"; exit 1; }

# Whatever happens (Ctrl+C, an error, a dropped SSH), stop the servers this run started and close
# their tmux sessions. Only a completed "vllm" run leaves vLLM up, on purpose.
KEEP_VLLM=0
cleanup() {
    [ "$KEEP_VLLM" = 1 ] || bash "$HERE/stop_vllm.sh"
    bash "$HERE/stop_ollama.sh"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

vllm_up() { curl -sf -H "Authorization: Bearer $(cat "$LLMBENCH/vllm.key")" "http://127.0.0.1:$PORT/v1/models" -o /dev/null; }

run_vllm() {
    bash "$HERE/stop_ollama.sh"
    vllm_up || bash "$HERE/serve_vllm.sh"
    local key; key=$(cat "$LLMBENCH/vllm.key")
    echo "##### vLLM burst sweep ($LEVELS users)"
    $BENCH --api openai --url "http://127.0.0.1:$PORT" --api-key "$key" --model "$SERVED_NAME" \
        --users "$LEVELS" --gpu --gpu-index "$GPU" --label vllm --out "$OUT/conc_vllm.json"
    echo "##### vLLM realistic arrivals (8 users, poisson)"
    $BENCH --api openai --url "http://127.0.0.1:$PORT" --api-key "$key" --model "$SERVED_NAME" \
        --users 8 --arrival poisson --rate 0.5 --think-time 10 --requests-per-user 4 \
        --gpu --gpu-index "$GPU" --label vllm-poisson --out "$OUT/conc_vllm_poisson.json"
}

run_ollama() {
    bash "$HERE/stop_vllm.sh"
    for P in 1 4; do
        bash "$HERE/stop_ollama.sh"
        bash "$HERE/serve_ollama.sh" "$P"
        echo "##### Ollama NUM_PARALLEL=$P ($LEVELS users, num_ctx $NUM_CTX)"
        $BENCH --model "$OLLAMA_MODEL" --num-ctx "$NUM_CTX" --users "$LEVELS" \
            --gpu --gpu-index "$GPU" --label "ollama-p$P" --out "$OUT/conc_ollama_p$P.json"
    done
    bash "$HERE/stop_ollama.sh"
}

case $WHAT in
    vllm) run_vllm; KEEP_VLLM=1 ;;
    ollama) run_ollama ;;
    all) run_vllm; run_ollama ;;
    *) echo "usage: $0 [all|vllm|ollama]"; exit 1 ;;
esac
echo "Done. Results:"
ls -l "$OUT"/conc_*.json
