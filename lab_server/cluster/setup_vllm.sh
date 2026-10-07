#!/usr/bin/env bash
# One-time install of vLLM + model weights under ~/llm-bench. No root, no .bashrc change.
# Usage: bash setup_vllm.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/vllm.env"
mkdir -p "$LLMBENCH"/{bin,logs,hf}
export PATH=$LLMBENCH/bin:$PATH

if ! command -v uv >/dev/null; then
    echo "== installing uv into $LLMBENCH/bin"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$LLMBENCH/bin" UV_NO_MODIFY_PATH=1 sh
fi

VENV=$LLMBENCH/vllm-venv
if [ ! -x "$VENV/bin/vllm" ]; then
    echo "== creating $VENV and installing vllm${VLLM_VERSION:+==$VLLM_VERSION} (several GB, a few minutes)"
    uv venv --python 3.12 "$VENV"
    uv pip install --python "$VENV/bin/python" "vllm${VLLM_VERSION:+==$VLLM_VERSION}" --torch-backend=auto
fi
"$VENV/bin/python" -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__, '| cuda ok:', torch.cuda.is_available())"

echo "== downloading $MODEL into $HF_HOME"
time "$VENV/bin/hf" download "$MODEL"

KEY=$LLMBENCH/vllm.key
if [ ! -s "$KEY" ]; then
    (umask 077; python3 -c 'import secrets; print("lab-" + secrets.token_urlsafe(24))' > "$KEY")
    echo "== API key created in $KEY (share it with lab members, not publicly)"
fi

echo "== disk"
df -h "$HOME" | tail -1
quota -s 2>/dev/null | tail -1 || true
echo "Done. Next: bash $HERE/serve_vllm.sh"
