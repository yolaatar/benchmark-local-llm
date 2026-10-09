r"""Round 3: run the custom tasks with an agent harness against the lab model on tassan.

Same protocol as run_claude_code_tasks.py (fresh clone at base_ref, same prompt, one message, then
the diff, elapsed time and turns saved to results/custom_<task>_<label>.json), but the model is
qwen3-coder-next served on tassan and the harness varies: OpenCode or Claude Code.
Needs the SSH tunnel open (lab_server/client/tassan-tunnel.ps1 or .sh) and, for vLLM, TASSAN_VLLM_KEY.
Other machines than the round-1 Windows laptop: ADS_REPO (local ADS clone with the task commits, used
when a task's repo path doesn't exist here) and ADS_ENV (Python env with AxonDeepSeg, put first on PATH).

Usage:
  .venv\Scripts\python.exe run_tassan_tasks.py --harness opencode
  .venv\Scripts\python.exe run_tassan_tasks.py --harness claude --tasks task_04_find_bug
  .venv\Scripts\python.exe run_tassan_tasks.py --harness opencode --backend ollama
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from bench_config import RESULTS_DIR, ROOT, TASKS_DIR
from run_claude_code_tasks import ADS_ENV as ADS_ENV_WIN, ALLOWED_TOOLS, CLAUDE as CLAUDE_WIN
from run_custom_tasks import WORK_DIR, checkout_task_repo, collect_diff, load_tasks

# Clones outside this repo: an agent that loses its way (OpenCode did, see PWD below) then can't
# wander into other runs' clones under work/ and edit them.
WORK_DIR = Path(os.environ.get("TASSAN_WORK_DIR", Path.home() / "llm-bench-work"))

CLIENT_DIR = ROOT / "lab_server" / "client"
CLAUDE = CLAUDE_WIN if os.path.exists(CLAUDE_WIN) else (shutil.which("claude") or CLAUDE_WIN)
ADS_ENV = os.environ.get("ADS_ENV", ADS_ENV_WIN)
DEFAULT_TIMEOUT_S = 45 * 60

# Must match MAX_MODEL_LEN in lab_server/cluster/vllm.env and the limits in opencode.json.
CLAUDE_WINDOW_ENV = {
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "131072",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "131072",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16384",
}

# Ports of tassan-tunnel.ps1 on the laptop side.
BACKENDS = {
    # TASSAN_MODEL: the SERVED_NAME in lab_server/cluster/vllm.env (default: the 80B coder)
    "vllm": {"base": "http://127.0.0.1:8001", "model": os.environ.get("TASSAN_MODEL", "qwen3-coder-next"),
             "opencode": "tassan/" + os.environ.get("TASSAN_MODEL", "qwen3-coder-next")},
    "ollama": {"base": "http://127.0.0.1:11435", "model": "qwen3-coder-next-cc",
               "opencode": "tassan-ollama/qwen3-coder-next-cc"},
}


def backend_token(backend):
    if backend == "ollama":
        return "ollama"
    key = os.environ.get("TASSAN_VLLM_KEY")
    if not key:
        sys.exit("Set TASSAN_VLLM_KEY first (content of ~/llm-bench/vllm.key on tassan).")
    return key


def check_server(backend):
    cfg = BACKENDS[backend]
    req = urllib.request.Request(cfg["base"] + "/v1/models",
                                 headers={"Authorization": f"Bearer {backend_token(backend)}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ids = [m["id"] for m in json.loads(resp.read())["data"]]
    except OSError as e:
        sys.exit(f"No answer from {cfg['base']} ({e}). Tunnel open? {backend} running on tassan?")
    if cfg["model"] not in ids:
        sys.exit(f"{cfg['model']} not served by {backend}, got {ids}")


def opencode_exe():
    # call the native binary, not the npm .cmd shim: cmd.exe cuts multi-line arguments
    shim = shutil.which("opencode")
    if not shim:
        sys.exit("OpenCode is not installed: npm install -g opencode-ai")
    exe = Path(shim).parent / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    return str(exe if exe.exists() else shim)


def harness_env(harness, backend):
    env = os.environ.copy()
    cfg = BACKENDS[backend]
    if harness == "opencode":
        env["OPENCODE_CONFIG"] = str(CLIENT_DIR / "opencode.bench.json")
    else:
        env.pop("ANTHROPIC_API_KEY", None)
        env.update({
            "ANTHROPIC_BASE_URL": cfg["base"],
            "ANTHROPIC_AUTH_TOKEN": backend_token(backend),
            "ANTHROPIC_MODEL": cfg["model"],
            "ANTHROPIC_DEFAULT_OPUS_MODEL": cfg["model"],
            "ANTHROPIC_DEFAULT_SONNET_MODEL": cfg["model"],
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": cfg["model"],
            "CLAUDE_CODE_SUBAGENT_MODEL": cfg["model"],
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
            # Claude Code doesn't know this model's window: without these it reserves 32k output tokens
            # and never compacts, so long tasks die on a 400 once the prompt passes ~99k tokens.
            **CLAUDE_WINDOW_ENV,
        })
    # the ADS conda env first on PATH, like a dev with the env activated
    env_dirs = ([ADS_ENV, os.path.join(ADS_ENV, "Scripts"), os.path.join(ADS_ENV, "Library", "bin")]
                if os.name == "nt" else [os.path.join(ADS_ENV, "bin")])
    env["PATH"] = os.pathsep.join(env_dirs + [env["PATH"]])
    return env


def harness_cmd(harness, backend, prompt):
    if harness == "opencode":
        return [opencode_exe(), "run", prompt, "--model", BACKENDS[backend]["opencode"], "--format", "json"]
    return [
        CLAUDE, "-p", prompt,
        "--model", BACKENDS[backend]["model"],
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
        "--setting-sources", "project,local",
        "--allowedTools", *ALLOWED_TOOLS,
    ]


def parse_opencode(stdout):
    """`opencode run --format json` prints one JSON event per line. Kept loose on purpose:
    the raw events are saved next to the result anyway."""
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    texts, tools, steps, tokens = [], 0, 0, {}
    for ev in events:
        kind = str(ev.get("type", ""))
        part = ev.get("part") or {}
        if kind == "text" and part.get("text"):
            texts.append(part["text"])
        elif "tool" in kind:
            tools += 1
        elif kind == "step_finish":
            steps += 1
            for k, v in (part.get("tokens") or {}).items():
                if isinstance(v, (int, float)):
                    tokens[k] = tokens.get(k, 0) + v
    errors = [ev for ev in events if "error" in str(ev.get("type", ""))]
    return {
        "num_turns": steps or None,
        "tool_calls": tools,
        "usage": tokens or None,
        "is_error": bool(errors) or None,
        "final_answer": texts[-1] if texts else "",
        "num_events": len(events),
    }


def parse_claude(stdout):
    try:
        out = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        out = {}
    return {
        "num_turns": out.get("num_turns"),
        "tool_calls": None,
        "usage": out.get("usage"),
        "is_error": out.get("is_error"),
        "final_answer": out.get("result", ""),
    }


def run_one(task, harness, backend, label, timeout_s):
    run_dir = WORK_DIR / task["id"] / label
    repo_dir = run_dir / "repo"
    print(f"\n=== {task['id']} x {label}", flush=True)
    head = checkout_task_repo(task, repo_dir)
    prompt = task["prompt"].strip()
    (run_dir / "prompt.md").write_text(prompt + "\n", encoding="utf-8")

    t0 = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            # PWD too: OpenCode takes its project directory from $PWD, not from the process cwd
            harness_cmd(harness, backend, prompt), cwd=repo_dir, env={**harness_env(harness, backend), "PWD": str(repo_dir)},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s, stdin=subprocess.DEVNULL,
        )
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout, stderr, code = e.stdout or "", e.stderr or "", None
        stdout = stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    elapsed = time.time() - t0
    raw_out = run_dir / f"{harness}_stdout.{'jsonl' if harness == 'opencode' else 'json'}"
    raw_out.write_text(stdout, encoding="utf-8")
    (run_dir / f"{harness}_stderr.txt").write_text(stderr, encoding="utf-8")

    parsed = parse_opencode(stdout) if harness == "opencode" else parse_claude(stdout)
    diff, files = collect_diff(repo_dir, head)

    result = {
        "task": task["id"],
        "title": task.get("title"),
        "category": task.get("category"),
        "mode": task["mode"],
        "model": label,
        "runner": f"{harness} (headless) -> tassan {backend}",
        "served_model": BACKENDS[backend]["model"],
        "repo": str(task["repo"]),
        "base_ref": head,
        "prompt": prompt,
        "elapsed_seconds": round(elapsed, 1),
        "timed_out": timed_out,
        "exit_code": code,
        "user_messages": 1,
        "cost_usd": 0.0,
        **parsed,
        "files_changed": files,
        "diff": diff,
        "review": {"success": None, "notes": ""},
        "artifacts": {"repo": str(repo_dir), "stdout": str(raw_out)},
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    path = RESULTS_DIR / f"custom_{task['id']}_{label}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"   {elapsed:.0f}s, {result['num_turns']} turns, {len(files)} files changed"
        f"{', TIMEOUT' if timed_out else ''}{', ERROR' if result['is_error'] or code else ''}"
        f" -> {path.relative_to(ROOT)}",
        flush=True,
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--harness", choices=["opencode", "claude"], required=True)
    parser.add_argument("--backend", choices=list(BACKENDS), default="vllm")
    parser.add_argument("--label", help="result label, default <harness>-tassan-<backend>")
    parser.add_argument("--tasks", nargs="*", help="task ids, default: all ready")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args()
    label = args.label or f"{args.harness}-tassan-{args.backend}"

    check_server(args.backend)
    tasks = [t for t in load_tasks(TASKS_DIR, args.tasks) if t["ready"]]
    for t in tasks:
        if not Path(t["repo"]).exists() and os.environ.get("ADS_REPO"):
            t["repo"] = os.environ["ADS_REPO"]
    results = [run_one(t, args.harness, args.backend, label, args.timeout) for t in tasks]

    print("\n=== Summary")
    for r in results:
        print(f"{r['task']:<26} {r['elapsed_seconds']:>6.0f}s  {r['num_turns']} turns  "
              f"{len(r['files_changed'])} files")


if __name__ == "__main__":
    main()
