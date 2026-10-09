r"""Multi-user load test for a model served by Ollama (or any OpenAI-compatible server, e.g. vLLM).

Simulates N users hitting the same loaded model at the same time and measures how the
server shares it: time to first token (includes queueing), end-to-end latency, per-request
decode speed, aggregate throughput, and rejected requests (Ollama answers 503 once its
queue is full).

Standalone, stdlib only: copy it to the cluster and run it with any python3.

Usage:
  python concurrency_bench.py --model qwen3-coder-next --users 1,2,4,8,16
  python concurrency_bench.py --model qwen3-coder-next --users 8 --arrival poisson --rate 0.5
  python concurrency_bench.py --api openai --url http://127.0.0.1:8000 --model qwen3-coder-next \
      --api-key "$(cat ~/llm-bench/vllm.key)" --users 1,4,16

The server-side concurrency is configured when the server starts, not here. For Ollama:
  OLLAMA_NUM_PARALLEL=4 OLLAMA_MAX_QUEUE=512 ollama serve
Run the same sweep once per OLLAMA_NUM_PARALLEL value and pass --label to tell runs apart.
"""

import argparse
import json
import random
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

FILLER = (
    "def process(records):\n"
    "    out = []\n"
    "    for r in records:\n"
    "        if r.get('active') and r['score'] > 0.5:\n"
    "            out.append({'id': r['id'], 'score': round(r['score'], 3)})\n"
    "    return sorted(out, key=lambda x: -x['score'])\n\n"
)

TASKS = [
    "Review the code above and list three concrete improvements.",
    "Write pytest tests for the function above.",
    "Explain what the code above does, step by step.",
    "Rewrite the function above with type hints and a docstring.",
]


def build_prompt(user, i, prompt_tokens):
    # Unique header per request so the server cannot reuse another user's prompt cache.
    header = f"# session {user}-{i}-{random.randrange(10**9)}\n"
    body = FILLER * max(1, prompt_tokens // 80)  # ~80 tokens per FILLER block
    return header + body + TASKS[(user + i) % len(TASKS)]


def stream_request(args, prompt):
    """Send one streaming request. Returns a dict of timings, never raises."""
    if args.api == "ollama":
        path = "/api/chat"
        payload = {
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "keep_alive": "30m",
            "options": {"num_ctx": args.num_ctx, "num_predict": args.max_tokens},
        }
        if args.no_think:
            payload["think"] = False
    else:
        path = "/v1/chat/completions"
        payload = {
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": args.max_tokens,
            "stream_options": {"include_usage": True},
        }
    req = urllib.request.Request(
        args.url.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {args.api_key}"},
    )
    rec = {"t_submit": time.perf_counter(), "t_first": None, "t_end": None,
           "out_tokens": 0, "prompt_tokens": None, "status": None, "error": None}
    chunks = 0
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            rec["status"] = resp.status
            for raw in resp:
                line = raw.decode().strip()
                if not line:
                    continue
                if args.api == "openai":
                    if not line.startswith("data:"):
                        continue
                    line = line[5:].strip()
                    if line == "[DONE]":
                        break
                msg = json.loads(line)
                if args.api == "ollama":
                    m = msg.get("message", {})
                    if m.get("content") or m.get("thinking"):
                        chunks += 1
                        if rec["t_first"] is None:
                            rec["t_first"] = time.perf_counter()
                    if msg.get("done"):
                        rec["out_tokens"] = msg.get("eval_count", chunks)
                        rec["prompt_tokens"] = msg.get("prompt_eval_count")
                else:
                    for c in msg.get("choices", []):
                        d = c.get("delta", {})
                        # thinking models: recent vLLM streams it as "reasoning", older as "reasoning_content"
                        if d.get("content") or d.get("reasoning") or d.get("reasoning_content"):
                            chunks += 1
                            if rec["t_first"] is None:
                                rec["t_first"] = time.perf_counter()
                    if msg.get("usage"):
                        rec["out_tokens"] = msg["usage"].get("completion_tokens", chunks)
                        rec["prompt_tokens"] = msg["usage"].get("prompt_tokens")
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = e.read().decode(errors="replace")[:200]
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"[:200]
    rec["t_end"] = time.perf_counter()
    if not rec["out_tokens"]:
        rec["out_tokens"] = chunks
    return rec


class GpuSampler(threading.Thread):
    """Peak VRAM and mean utilization from nvidia-smi while a level runs."""

    def __init__(self, index=None):
        super().__init__(daemon=True)
        self.index = index
        self.stop_evt = threading.Event()
        self.mem_peak = 0
        self.util = []

    def run(self):
        while not self.stop_evt.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                     "--format=csv,noheader,nounits"]
                    + (["-i", str(self.index)] if self.index is not None else []),
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip().splitlines()
                mem = sum(int(l.split(",")[0]) for l in out)
                self.mem_peak = max(self.mem_peak, mem)
                self.util.append(max(int(l.split(",")[1]) for l in out))
            except Exception:
                return
            self.stop_evt.wait(0.5)


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, round(p / 100 * (len(s) - 1)))]


def run_level(args, n_users):
    """n_users each send --requests-per-user requests back to back (closed loop)."""
    records, lock = [], threading.Lock()
    t0 = time.perf_counter()

    def user_loop(u):
        if args.arrival == "poisson":
            time.sleep(random.expovariate(args.rate) if u else 0)
        elif args.arrival == "stagger":
            time.sleep(u * args.stagger)
        for i in range(args.requests_per_user):
            rec = stream_request(args, build_prompt(u, i, args.prompt_tokens))
            rec["user"] = u
            with lock:
                records.append(rec)
            if args.think_time:
                time.sleep(random.expovariate(1 / args.think_time))

    gpu = GpuSampler(args.gpu_index) if args.gpu else None
    if gpu:
        gpu.start()
    threads = [threading.Thread(target=user_loop, args=(u,)) for u in range(n_users)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0
    if gpu:
        gpu.stop_evt.set()

    ok = [r for r in records if r["error"] is None and r["t_first"] is not None]
    ttft = [r["t_first"] - r["t_submit"] for r in ok]
    e2e = [r["t_end"] - r["t_submit"] for r in ok]
    decode = [r["out_tokens"] / (r["t_end"] - r["t_first"])
              for r in ok if r["t_end"] > r["t_first"] and r["out_tokens"] > 1]
    total_out = sum(r["out_tokens"] for r in ok)
    for r in records:  # relative times for the raw dump
        for k in ("t_submit", "t_first", "t_end"):
            if r[k] is not None:
                r[k] = round(r[k] - t0, 3)
    return {
        "users": n_users,
        "requests": len(records),
        "ok": len(ok),
        "errors": len(records) - len(ok),
        "error_samples": sorted({f"{r['status']} {r['error']}" for r in records if r["error"]})[:5],
        "wall_s": round(wall, 2),
        "ttft_p50_s": pct(ttft, 50), "ttft_p95_s": pct(ttft, 95), "ttft_max_s": max(ttft, default=None),
        "e2e_p50_s": pct(e2e, 50), "e2e_p95_s": pct(e2e, 95),
        "decode_tok_s_per_req_p50": pct(decode, 50),
        "aggregate_out_tok_s": round(total_out / wall, 1) if wall else None,
        "gpu_mem_peak_mib": gpu.mem_peak if gpu else None,
        "gpu_util_mean": round(statistics.mean(gpu.util), 1) if gpu and gpu.util else None,
        "records": records,
    }


def server_info(args):
    if args.api != "ollama":
        return {}
    try:
        with urllib.request.urlopen(args.url.rstrip("/") + "/api/ps", timeout=10) as r:
            return {"loaded": [{k: m.get(k) for k in ("name", "size", "size_vram", "context_length")}
                               for m in json.load(r).get("models", [])]}
    except Exception as e:
        return {"error": str(e)}


def fmt(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--api", choices=["ollama", "openai"], default="ollama")
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default="none", help="bearer token (vLLM: content of ~/llm-bench/vllm.key)")
    ap.add_argument("--users", default="1,2,4,8", help="comma-separated concurrency levels to sweep")
    ap.add_argument("--requests-per-user", type=int, default=2)
    ap.add_argument("--arrival", choices=["burst", "stagger", "poisson"], default="burst",
                    help="burst: everyone at t=0; stagger: user k starts at k*--stagger s; "
                         "poisson: random start times with --rate users/s")
    ap.add_argument("--stagger", type=float, default=1.0)
    ap.add_argument("--rate", type=float, default=0.5)
    ap.add_argument("--think-time", type=float, default=0.0, help="mean pause between a user's requests (s)")
    ap.add_argument("--prompt-tokens", type=int, default=1500, help="approximate prompt size")
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--num-ctx", type=int, default=8192, help="Ollama only; must match across runs")
    ap.add_argument("--no-think", action="store_true", help="disable reasoning for thinking models (Ollama)")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--gpu", action="store_true", help="sample nvidia-smi during each level")
    ap.add_argument("--gpu-index", type=int, default=None,
                    help="only sample this card (nvidia-smi index); default: all cards summed")
    ap.add_argument("--label", default="", help="free text stored in the output, e.g. 'NUM_PARALLEL=4'")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    levels = [int(x) for x in args.users.split(",")]
    print(f"warmup: loading {args.model} ...", flush=True)
    w = stream_request(args, build_prompt(0, 0, 50))
    if w["error"]:
        raise SystemExit(f"warmup failed: {w['status']} {w['error']}")
    info = server_info(args)

    results = []
    head = f"{'users':>5} {'ok/req':>7} {'wall s':>7} {'TTFT p50':>9} {'TTFT p95':>9} " \
           f"{'E2E p50':>8} {'E2E p95':>8} {'tok/s/req':>9} {'agg tok/s':>9} {'VRAM MiB':>9}"
    print(head)
    for n in levels:
        r = run_level(args, n)
        results.append(r)
        print(f"{n:>5} {r['ok']:>3}/{r['requests']:<3} {fmt(r['wall_s']):>7} {fmt(r['ttft_p50_s'], 2):>9} "
              f"{fmt(r['ttft_p95_s'], 2):>9} {fmt(r['e2e_p50_s']):>8} {fmt(r['e2e_p95_s']):>8} "
              f"{fmt(r['decode_tok_s_per_req_p50']):>9} {fmt(r['aggregate_out_tok_s']):>9} "
              f"{r['gpu_mem_peak_mib'] or '-':>9}", flush=True)
        for e in r["error_samples"]:
            print(f"      error: {e}")

    out = Path(args.out) if args.out else Path(__file__).parent / "results" / (
        f"concurrency_{args.model.replace('/', '_').replace(':', '-')}"
        f"{'_' + args.label.replace('=', '').replace(' ', '_') if args.label else ''}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = {k: v for k, v in vars(args).items() if k not in ("out", "api_key")}   # never save the key
    out.write_text(json.dumps({"config": cfg, "server": info, "levels": results}, indent=1))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
