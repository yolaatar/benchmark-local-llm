r"""Measure real VRAM usage and throughput of each benchmark model during a generation.

Usage: .venv\Scripts\python.exe measure_vram.py [--num-ctx 16384] [ollama_tag ...]
Writes results/vram_<model>.json.
"""

import argparse
import json
import subprocess
import threading
import time
import urllib.request

from bench_config import MODELS, OLLAMA_API_BASE, RESULTS_DIR

PROMPT = (
    "Write a Python module implementing a thread-safe LRU cache class with get, put, "
    "delete and resize methods, full type hints, docstrings, and a pytest test suite "
    "covering eviction order and concurrency."
)


def api(path, payload=None, timeout=1800):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        OLLAMA_API_BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def gpu_used_mib():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    used, total = (int(x) for x in out.split(","))
    return used, total


def unload_all():
    for m in api("/api/ps").get("models", []):
        api("/api/generate", {"model": m["name"], "keep_alive": 0})
    time.sleep(3)


def measure(tag, num_ctx):
    unload_all()
    baseline, total = gpu_used_mib()

    peak = [baseline]
    stop = threading.Event()

    def poll():
        while not stop.is_set():
            peak[0] = max(peak[0], gpu_used_mib()[0])
            time.sleep(0.5)

    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    t0 = time.time()
    resp = api(
        "/api/generate",
        {
            "model": tag,
            "prompt": PROMPT,
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {"num_ctx": num_ctx, "num_predict": 1024, "temperature": 0},
        },
    )
    wall = time.time() - t0
    ps = next((m for m in api("/api/ps")["models"] if m["name"] == tag), {})
    stop.set()
    poller.join()

    size, size_vram = ps.get("size", 0), ps.get("size_vram", 0)
    result = {
        "model": tag,
        "num_ctx": num_ctx,
        "gpu_total_mib": total,
        "gpu_baseline_mib": baseline,
        "gpu_peak_mib": peak[0],
        "gpu_used_by_model_mib": peak[0] - baseline,
        "ollama_size_gb": round(size / 1e9, 2),
        "ollama_size_vram_gb": round(size_vram / 1e9, 2),
        "gpu_fraction": round(size_vram / size, 3) if size else None,
        "load_s": round(resp.get("load_duration", 0) / 1e9, 1),
        "prompt_tok_s": round(
            resp.get("prompt_eval_count", 0) / max(resp.get("prompt_eval_duration", 1) / 1e9, 1e-9), 1
        ),
        "gen_tokens": resp.get("eval_count"),
        "gen_tok_s": round(resp.get("eval_count", 0) / max(resp.get("eval_duration", 1) / 1e9, 1e-9), 1),
        "wall_s": round(wall, 1),
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="*", default=list(MODELS))
    parser.add_argument("--num-ctx", type=int, default=16384)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    for tag in args.models:
        print(f"== {tag} (num_ctx={args.num_ctx})", flush=True)
        res = measure(tag, args.num_ctx)
        print(json.dumps(res, indent=2), flush=True)
        label = MODELS.get(tag, tag.replace(":", "-").replace("/", "-"))
        (RESULTS_DIR / f"vram_{label}_ctx{args.num_ctx}.json").write_text(json.dumps(res, indent=2))
    unload_all()


if __name__ == "__main__":
    main()
