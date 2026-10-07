r"""Run the custom tasks with Claude Code (Anthropic backend) in headless mode.

Same protocol as run_custom_tasks.py for the local models: fresh clone at base_ref, same prompt,
one message, then the diff, elapsed time, number of turns and cost are saved to
results/custom_<task>_<label>.json. The model runs on Anthropic's servers: no local GPU/RAM needed.

Usage:
  .venv\Scripts\python.exe run_claude_code_tasks.py --model sonnet            # label claude-sonnet
  .venv\Scripts\python.exe run_claude_code_tasks.py --model opus --tasks task_04_find_bug

Uses your normal Claude Code login (claude.ai plan quota) or ANTHROPIC_API_KEY if set.
"""

import argparse
import datetime
import json
import os
import subprocess
import time

from bench_config import RESULTS_DIR, ROOT, TASKS_DIR
from run_custom_tasks import WORK_DIR, checkout_task_repo, collect_diff, load_tasks

CLAUDE = os.path.expanduser(r"~\.local\bin\claude.exe")
ADS_ENV = r"C:\Users\Youssef\miniconda3\envs\ads"
DEFAULT_TIMEOUT_S = 30 * 60

# Edits are auto-accepted; shell access is limited to what a dev needs to check their work.
ALLOWED_TOOLS = [
    "Read", "Glob", "Grep", "Edit", "Write",
    "Bash(python:*)", "Bash(pytest:*)", "Bash(git diff:*)", "Bash(git status:*)",
    "Bash(git log:*)", "Bash(git show:*)", "Bash(ls:*)", "Bash(cat:*)",
]


def claude_env():
    env = os.environ.copy()
    # make sure we hit the real Anthropic backend, not a leftover local-model setup
    for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
                 "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                 "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"):
        env.pop(name, None)
    # the ADS conda env first on PATH, like a dev with the env activated
    env["PATH"] = os.pathsep.join(
        [ADS_ENV, os.path.join(ADS_ENV, "Scripts"), os.path.join(ADS_ENV, "Library", "bin"), env["PATH"]]
    )
    return env


def run_one(task, model, label, timeout_s):
    run_dir = WORK_DIR / task["id"] / label
    repo_dir = run_dir / "repo"
    print(f"\n=== {task['id']} x {label}", flush=True)
    head = checkout_task_repo(task, repo_dir)
    prompt = task["prompt"].strip()
    (run_dir / "prompt.md").write_text(prompt + "\n", encoding="utf-8")

    cmd = [
        CLAUDE, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
        # project/local settings only: the user's global CLAUDE.md and settings stay out of the test
        "--setting-sources", "project,local",
        "--allowedTools", *ALLOWED_TOOLS,
    ]
    t0 = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd, cwd=repo_dir, env=claude_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s, stdin=subprocess.DEVNULL,
        )
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout, stderr, code = e.stdout or "", e.stderr or "", None
    elapsed = time.time() - t0
    (run_dir / "claude_stdout.json").write_text(stdout if isinstance(stdout, str) else "", encoding="utf-8")
    (run_dir / "claude_stderr.txt").write_text(stderr if isinstance(stderr, str) else "", encoding="utf-8")

    try:
        out = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        out = {}
    diff, files = collect_diff(repo_dir, head)

    result = {
        "task": task["id"],
        "title": task.get("title"),
        "category": task.get("category"),
        "mode": task["mode"],
        "model": label,
        "runner": "claude-code (headless)",
        "claude_model_arg": model,
        "models_used": sorted((out.get("modelUsage") or {}).keys()),
        "repo": str(task["repo"]),
        "base_ref": head,
        "prompt": prompt,
        "elapsed_seconds": round(elapsed, 1),
        "timed_out": timed_out,
        "exit_code": code,
        "is_error": out.get("is_error"),
        "num_turns": out.get("num_turns"),
        "user_messages": 1,
        "cost_usd": out.get("total_cost_usd"),
        "usage": out.get("usage"),
        "final_answer": out.get("result", ""),
        "files_changed": files,
        "diff": diff,
        "review": {"success": None, "notes": ""},
        "artifacts": {"repo": str(repo_dir), "claude_stdout": str(run_dir / "claude_stdout.json")},
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    path = RESULTS_DIR / f"custom_{task['id']}_{label}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    cost = f"${result['cost_usd']:.2f}" if result["cost_usd"] is not None else "cost n/a"
    print(
        f"   {elapsed:.0f}s, {result['num_turns']} turns, {cost}, {len(files)} files changed"
        f"{', TIMEOUT' if timed_out else ''}{', ERROR' if result['is_error'] or code else ''}"
        f" -> {path.relative_to(ROOT)}",
        flush=True,
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="sonnet", help="claude --model value (sonnet, opus, ...)")
    parser.add_argument("--label", help="result label, default claude-<model>")
    parser.add_argument("--tasks", nargs="*", help="task ids, default: all ready")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args()
    label = args.label or f"claude-{args.model}"

    tasks = [t for t in load_tasks(TASKS_DIR, args.tasks) if t["ready"]]
    results = [run_one(t, args.model, label, args.timeout) for t in tasks]

    print("\n=== Summary")
    for r in results:
        cost = f"${r['cost_usd']:.2f}" if r["cost_usd"] is not None else "n/a"
        print(f"{r['task']:<26} {r['elapsed_seconds']:>6.0f}s  {r['num_turns']} turns  {cost:>7}  "
              f"{len(r['files_changed'])} files")


if __name__ == "__main__":
    main()
