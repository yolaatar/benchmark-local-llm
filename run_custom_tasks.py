r"""Run the custom tasks (custom_tasks/*/task.yaml) with aider against each local Ollama model.

For every (task, model) pair this script:
  1. clones the task's repo at its pinned base_ref into work/<task>/<model>/repo,
  2. runs aider non-interactively with the task prompt (--message-file, --yes-always),
  3. records the diff vs base_ref, elapsed time, number of LLM calls, tokens,
     and (for mode: ask) the model's answer,
  4. saves everything to results/custom_<task>_<model>.json.

No grading: success/failure is reviewed by hand afterwards.

Usage:
  .venv\Scripts\python.exe run_custom_tasks.py                          # all ready tasks x all models
  .venv\Scripts\python.exe run_custom_tasks.py --tasks task_04_find_bug --models qwen2.5-coder:7b
  .venv\Scripts\python.exe run_custom_tasks.py --list                   # show tasks and their status

Manual replay with Claude Code (same starting state, same output format):
  .venv\Scripts\python.exe run_custom_tasks.py --prepare-manual claude-sonnet --tasks task_01_add_feature
  ... run Claude Code in the printed directory, paste the printed prompt ...
  .venv\Scripts\python.exe run_custom_tasks.py --collect-manual claude-sonnet --tasks task_01_add_feature --elapsed 312 --messages 4
"""

import argparse
import datetime
import json
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import yaml

from bench_config import (
    AIDER,
    MODELS,
    RESULTS_DIR,
    ROOT,
    TASKS_DIR,
    aider_model_name,
    base_env,
)

WORK_DIR = ROOT / "work"
CUSTOM_SETTINGS = ROOT / "aider_model_settings_custom.yml"
DEFAULT_TIMEOUT_S = 30 * 60
REQUIRED_KEYS = ("repo", "base_ref", "mode", "prompt")


# ---------------------------------------------------------------- tasks


def load_tasks(tasks_dir, only=None):
    tasks = []
    for spec_file in sorted(Path(tasks_dir).glob("*/task.yaml")):
        spec = yaml.safe_load(spec_file.read_text(encoding="utf-8")) or {}
        spec["id"] = spec_file.parent.name
        spec["dir"] = spec_file.parent
        missing = [k for k in REQUIRED_KEYS if not spec.get(k)]
        spec["ready"] = not missing and spec.get("status", "ready") != "todo"
        spec["missing"] = missing
        if only and spec["id"] not in only:
            continue
        tasks.append(spec)
    return tasks


def git(*args, cwd=None, check=True):
    res = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def _force_remove(func, path, _exc):
    # git marks pack files read-only on Windows
    Path(path).chmod(stat.S_IWRITE)
    func(path)


def checkout_task_repo(task, dest):
    """Fresh clone of the task repo at base_ref. Local paths and URLs both work."""
    if dest.exists():
        shutil.rmtree(dest, onerror=_force_remove)
    dest.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "-q", "--no-checkout", str(task["repo"]), str(dest))
    git("checkout", "-q", "--detach", str(task["base_ref"]), cwd=dest)
    for cmd in task.get("setup_cmds") or []:
        subprocess.run(cmd, cwd=dest, shell=True, check=True)
    return git("rev-parse", "HEAD", cwd=dest).strip()


def collect_diff(repo_dir, base_ref):
    """Diff of everything changed since base_ref, including new files, excluding aider's caches."""
    git("add", "-A", "--", ".", ":(exclude).aider*", cwd=repo_dir)
    diff = git("diff", "--cached", base_ref, "--", ".", ":(exclude).aider*", cwd=repo_dir)
    stat_out = git("diff", "--cached", "--numstat", base_ref, "--", ".", ":(exclude).aider*", cwd=repo_dir)
    files = []
    for line in stat_out.splitlines():
        added, removed, path = line.split("\t", 2)
        files.append({"path": path, "added": added, "removed": removed})
    return diff, files


# ---------------------------------------------------------------- aider output parsing


def _tok(value, unit):
    return int(float(value) * {"": 1, "k": 1e3, "m": 1e6}[unit.lower()])


def parse_aider_output(stdout, llm_history):
    tokens_sent = tokens_received = 0
    for m in re.finditer(r"Tokens: ([\d.]+)([kKmM]?) sent, ([\d.]+)([kKmM]?) received", stdout):
        tokens_sent += _tok(m.group(1), m.group(2))
        tokens_received += _tok(m.group(3), m.group(4))

    responses = re.split(r"^LLM RESPONSE \S+\n", llm_history, flags=re.M)[1:]
    responses = [re.split(r"^TO LLM \S+\n", r, flags=re.M)[0].strip() for r in responses]
    last = responses[-1] if responses else ""
    # aider prefixes every line of the logged answer with "ASSISTANT "
    last = re.sub(r"^ASSISTANT ?", "", last, flags=re.M)

    return {
        "llm_calls": len(responses),
        "user_messages": 1,  # a single prompt per run, the rest are aider's own retries
        "auto_retries": max(len(responses) - 1, 0),  # edit-format errors, lint or test fix loops
        "applied_edits": sorted(set(re.findall(r"^Applied edit to (.+)$", stdout, flags=re.M))),
        "edit_format_errors": len(re.findall(r"did not conform to the edit format", stdout)),
        "search_replace_failures": len(re.findall(r"SearchReplaceNoExactMatch", stdout)),
        "reflection_limit_hit": "reflections allowed, stopping" in stdout,
        "context_window_exhausted": bool(re.search(r"exceeds the [\d,]+ token limit", stdout)),
        "tokens_sent": tokens_sent,
        "tokens_received": tokens_received,
        "final_answer": last,
    }


# ---------------------------------------------------------------- runs


def run_one(task, tag, timeout_s, edit_format=None):
    label = MODELS.get(tag, tag.replace(":", "-"))
    if edit_format:
        label += f"-{edit_format}"  # keep override runs apart from the main protocol
    run_dir = WORK_DIR / task["id"] / label
    repo_dir = run_dir / "repo"
    print(f"\n=== {task['id']} x {tag}", flush=True)

    head = checkout_task_repo(task, repo_dir)
    prompt_file = run_dir / "prompt.md"
    prompt_file.write_text(task["prompt"].strip() + "\n", encoding="utf-8")
    llm_history = run_dir / "llm_history.txt"
    chat_history = run_dir / "chat_history.md"
    aider_log = run_dir / "aider_stdout.txt"
    for f in (llm_history, chat_history):
        f.unlink(missing_ok=True)

    cmd = [
        str(AIDER),
        "--model", aider_model_name(tag),
        "--model-settings-file", str(CUSTOM_SETTINGS),
        "--message-file", str(prompt_file),
        "--yes-always",
        "--no-auto-commits",
        "--no-dirty-commits",
        "--no-gitignore",
        "--no-pretty",
        "--no-stream",
        "--no-fancy-input",
        "--no-check-update",
        "--no-show-release-notes",
        "--no-show-model-warnings",
        "--no-analytics",
        "--no-detect-urls",
        "--no-suggest-shell-commands",
        "--chat-language", "English",
        # litellm's default 600s request timeout cuts off slow long-context answers (14B at ~13 tok/s)
        "--timeout", str(timeout_s),
        "--llm-history-file", str(llm_history),
        "--chat-history-file", str(chat_history),
        "--input-history-file", str(run_dir / "input_history.txt"),
    ]
    if edit_format and task["mode"] != "ask":
        cmd += ["--edit-format", edit_format]
    if task["mode"] == "ask":
        cmd += ["--chat-mode", "ask"]
    if task.get("map_tokens") is not None:
        cmd += ["--map-tokens", str(task["map_tokens"])]
    if task.get("test_cmd"):
        cmd += ["--test-cmd", task["test_cmd"], "--auto-test"]
    for f in task.get("read_only") or []:
        cmd += ["--read", f]
    cmd += list(task.get("files") or [])

    t0 = time.time()
    timed_out = False
    proc = subprocess.Popen(
        cmd,
        cwd=repo_dir,
        env=base_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        stdout, _ = proc.communicate()
    elapsed = time.time() - t0
    aider_log.write_text(stdout, encoding="utf-8")

    diff, files = collect_diff(repo_dir, head)
    history = llm_history.read_text(encoding="utf-8") if llm_history.exists() else ""
    metrics = parse_aider_output(stdout, history)

    result = {
        "task": task["id"],
        "title": task.get("title"),
        "category": task.get("category"),
        "mode": task["mode"],
        "model": tag,
        "runner": "aider",
        "aider_model": aider_model_name(tag),
        "edit_format_override": edit_format,
        "repo": str(task["repo"]),
        "base_ref": head,
        "prompt": task["prompt"].strip(),
        "elapsed_seconds": round(elapsed, 1),
        "timed_out": timed_out,
        "exit_code": proc.returncode,
        **metrics,
        "files_changed": files,
        "diff": diff,
        "review": {"success": None, "notes": ""},  # filled in by hand
        "artifacts": {
            "repo": str(repo_dir),
            "aider_stdout": str(aider_log),
            "llm_history": str(llm_history),
            "chat_history": str(chat_history),
        },
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    out = RESULTS_DIR / f"custom_{task['id']}_{label}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"   {elapsed:.0f}s, {metrics['llm_calls']} LLM calls, {len(files)} files changed"
        f"{', TIMEOUT' if timed_out else ''} -> {out.relative_to(ROOT)}",
        flush=True,
    )
    return result


def prepare_manual(task, label):
    run_dir = WORK_DIR / task["id"] / label
    head = checkout_task_repo(task, run_dir / "repo")
    (run_dir / "prompt.md").write_text(task["prompt"].strip() + "\n", encoding="utf-8")
    (run_dir / "base_ref.txt").write_text(head + "\n")
    files = " ".join(task.get("files") or []) or "(none)"
    print(f"\n=== {task['id']} ready for {label}")
    print(f"   cd {run_dir / 'repo'}")
    print(f"   prompt: {run_dir / 'prompt.md'}")
    print(f"   files the prompt is about: {files}")
    print("   ---- prompt ----")
    print(task["prompt"].strip())


def collect_manual(task, label, elapsed, messages, answer_file):
    run_dir = WORK_DIR / task["id"] / label
    repo_dir = run_dir / "repo"
    if not repo_dir.exists():
        sys.exit(f"{repo_dir} missing, run --prepare-manual first")
    head = (run_dir / "base_ref.txt").read_text().strip()
    diff, files = collect_diff(repo_dir, head)
    answer = Path(answer_file).read_text(encoding="utf-8") if answer_file else ""
    result = {
        "task": task["id"],
        "title": task.get("title"),
        "category": task.get("category"),
        "mode": task["mode"],
        "model": label,
        "runner": "claude-code (manual)",
        "repo": str(task["repo"]),
        "base_ref": head,
        "prompt": task["prompt"].strip(),
        "elapsed_seconds": elapsed,
        "user_messages": messages,
        "final_answer": answer,
        "files_changed": files,
        "diff": diff,
        "review": {"success": None, "notes": ""},
        "artifacts": {"repo": str(repo_dir)},
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    out = RESULTS_DIR / f"custom_{task['id']}_{label}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   {len(files)} files changed -> {out.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tasks", nargs="*", help="task ids (folder names), default: all ready")
    parser.add_argument("--models", nargs="*", default=list(MODELS), help="Ollama tags")
    parser.add_argument("--tasks-dir", default=str(TASKS_DIR))
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="seconds per run")
    parser.add_argument(
        "--edit-format",
        help="override aider edit format (e.g. whole); results get a -<format> label suffix",
    )
    parser.add_argument("--list", action="store_true", help="list tasks and exit")
    parser.add_argument("--prepare-manual", metavar="LABEL", help="set up a workspace, e.g. claude-opus")
    parser.add_argument("--collect-manual", metavar="LABEL", help="save the diff of a manual run")
    parser.add_argument("--elapsed", type=float, help="--collect-manual: wall time in seconds")
    parser.add_argument("--messages", type=int, help="--collect-manual: prompts you sent")
    parser.add_argument("--answer-file", help="--collect-manual: file with the answer (ask tasks)")
    args = parser.parse_args()

    tasks = load_tasks(args.tasks_dir, args.tasks)
    if args.list or not tasks:
        for t in tasks:
            state = "ready" if t["ready"] else f"TODO (missing: {', '.join(t['missing']) or 'status'})"
            print(f"{t['id']:<28} {t.get('mode', '?'):<5} {state}")
        if not tasks:
            print("no task found")
        return

    not_ready = [t["id"] for t in tasks if not t["ready"]]
    if not_ready:
        print(f"Skipping tasks not specified yet: {', '.join(not_ready)}")
    tasks = [t for t in tasks if t["ready"]]

    if args.prepare_manual:
        for t in tasks:
            prepare_manual(t, args.prepare_manual)
        return
    if args.collect_manual:
        for t in tasks:
            collect_manual(t, args.collect_manual, args.elapsed, args.messages, args.answer_file)
        return

    RESULTS_DIR.mkdir(exist_ok=True)
    rows = []
    for tag in args.models:  # model-major order: each model is loaded once
        for t in tasks:
            r = run_one(t, tag, args.timeout, args.edit_format)
            rows.append((t["id"], tag, r["elapsed_seconds"], r["llm_calls"], len(r["files_changed"])))

    print("\n=== Summary (review success by hand in results/custom_*.json)")
    for task_id, tag, secs, calls, nfiles in rows:
        print(f"{task_id:<26} {tag:<26} {secs:>7.0f}s  {calls:>2} LLM calls  {nfiles:>2} files")


if __name__ == "__main__":
    main()
