r"""Run the same polyglot Python subset with Claude Code (headless) instead of aider.

Same protocol as run_aider_benchmark.py: same 25 exercises (seed 42), same instructions as
aider's harness, 2 tries (the second one sees the pytest output), tests run by this script.

Differences to keep in mind when comparing with the aider numbers (see NOTES.md):
  - Claude Code is an agent with its own tools, not aider's edit formats.
  - It runs on Anthropic's servers through your normal Claude Code login (plan quota),
    so no local GPU/RAM and no per-token bill.
  - Test files are hidden while the model works (restored to score), so it cannot read the
    expected answers. The local models never saw them either.

Usage:
  .venv\Scripts\python.exe run_claude_code_benchmark.py --model sonnet
  .venv\Scripts\python.exe run_claude_code_benchmark.py --model opus --num-exercises 3
"""

import argparse
import datetime
import json
import shutil
import subprocess
import sys
import time

from bench_config import RESULTS_DIR, ROOT, VENDOR_DIR
from run_aider_benchmark import POLYGLOT_PY, select_exercises
from run_claude_code_tasks import CLAUDE, claude_env

WORK_DIR = ROOT / "work_benchmark"
LOG_DIR = RESULTS_DIR / "logs"
TEST_TIMEOUT_S = 180  # same as aider's harness
RUN_TIMEOUT_S = 15 * 60

# No Bash(pytest): the model must not run the hidden tests. Plain python is allowed so it can
# sanity-check its own code, which is what aider's models could do through their own output.
ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write", "Bash(python:*)"]

sys.path.insert(0, str(VENDOR_DIR / "aider" / "benchmark"))
import prompts  # noqa: E402  (aider's own benchmark prompts)


def build_instructions(exercise_dir, solution_files):
    """Same instructions aider's harness sends: the exercise docs plus its addendum."""
    text = ""
    intro = exercise_dir / ".docs" / "introduction.md"
    if intro.exists():
        text += intro.read_text(encoding="utf-8")
    text += (exercise_dir / ".docs" / "instructions.md").read_text(encoding="utf-8")
    append = exercise_dir / ".docs" / "instructions.append.md"
    if append.exists():
        text += append.read_text(encoding="utf-8")
    text += prompts.instructions_addendum.format(file_list=" ".join(solution_files))
    return text


def read_config(exercise_dir):
    config = json.loads((exercise_dir / ".meta" / "config.json").read_text(encoding="utf-8"))
    files = config.get("files", {})
    return files.get("solution", []), files.get("test", [])


def hide_tests(exercise_dir, test_files):
    """Move test files out of the exercise while the model works."""
    stash = exercise_dir.parent / (exercise_dir.name + "__tests")
    if stash.exists():
        shutil.rmtree(stash)
    stash.mkdir(parents=True)
    for rel in test_files:
        src = exercise_dir / rel
        if src.exists():
            dst = stash / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    return stash


def restore_tests(exercise_dir, stash, test_files):
    for rel in test_files:
        src = stash / rel
        if src.exists():
            dst = exercise_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(src), str(dst))


def remove_tests(exercise_dir, test_files):
    for rel in test_files:
        (exercise_dir / rel).unlink(missing_ok=True)


def run_tests(exercise_dir):
    """Run pytest on the restored test files. Returns (passed, output)."""
    try:
        res = subprocess.run(
            [str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "pytest", "-q",
             "-p", "no:cacheprovider"],
            cwd=exercise_dir, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TEST_TIMEOUT_S,
        )
        return res.returncode == 0, res.stdout + res.stderr
    except subprocess.TimeoutExpired:
        return False, "Tests timed out!"


def call_claude(exercise_dir, prompt, model, log_handle):
    cmd = [
        CLAUDE, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
        "--setting-sources", "project,local",
        "--allowedTools", *ALLOWED_TOOLS,
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=exercise_dir, env=claude_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
        stdout, timed_out = proc.stdout, False
    except subprocess.TimeoutExpired as e:
        stdout, timed_out = (e.stdout or ""), True
    elapsed = time.time() - t0
    log_handle.write(stdout + "\n")
    log_handle.flush()
    try:
        out = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        out = {}
    return {
        "seconds": round(elapsed, 1),
        "timed_out": timed_out,
        "turns": out.get("num_turns"),
        "cost_usd": out.get("total_cost_usd"),
        "is_error": out.get("is_error"),
        "answer": out.get("result", ""),
    }


def run_exercise(name, model, label, tries):
    src = POLYGLOT_PY / name
    dest = WORK_DIR / label / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)

    solution_files, test_files = read_config(src)
    stash = hide_tests(dest, test_files)
    instructions = build_instructions(dest, solution_files)

    attempts, outcomes = [], []
    log_path = LOG_DIR / f"claude_benchmark_{label}.log"
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n\n##### {datetime.datetime.now().isoformat()} {name}\n")
        prompt = instructions
        for attempt in range(tries):
            info = call_claude(dest, prompt, model, log)
            remove_tests(dest, test_files)  # the model must not leave a copy behind
            restore_tests(dest, stash, test_files)
            passed, output = run_tests(dest)
            remove_tests(dest, test_files)
            info["passed"] = passed
            attempts.append(info)
            outcomes.append(passed)
            log.write(f"--- attempt {attempt + 1}: passed={passed}\n{output[-3000:]}\n")
            if passed or attempt == tries - 1:
                break
            errors = output.splitlines()
            prompt = "\n".join(errors[-100:]) + prompts.test_failures.format(
                file_list=" ".join(solution_files)
            )

    restore_tests(dest, stash, test_files)
    shutil.rmtree(stash, ignore_errors=True)
    return {
        "testcase": name,
        "tests_outcomes": outcomes,
        "attempts": attempts,
        "duration": round(sum(a["seconds"] for a in attempts), 1),
        "cost_usd": round(sum(a["cost_usd"] or 0 for a in attempts), 4),
        "turns": sum(a["turns"] or 0 for a in attempts),
        "testdir": str(dest),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--label", help="default claude-<model>")
    parser.add_argument("--num-exercises", type=int, default=25)
    parser.add_argument("--tries", type=int, default=2)
    args = parser.parse_args()
    label = args.label or f"claude-{args.model}"

    exercises = select_exercises(args.num_exercises)
    RESULTS_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{len(exercises)} Python exercises, model {args.model}, {args.tries} tries")
    print("Test files are hidden while the model works, restored to score.")

    per_ex, t0 = [], time.time()
    for i, name in enumerate(exercises, 1):
        res = run_exercise(name, args.model, label, args.tries)
        per_ex.append(res)
        mark = "PASS" if any(res["tests_outcomes"]) else "fail"
        print(f"   [{i}/{len(exercises)}] {name:<26} {mark} "
              f"({res['duration']:.0f}s, {res['turns']} turns, ${res['cost_usd']:.2f})", flush=True)

    def pass_rate(i):
        return round(100 * sum(1 for r in per_ex if any(r["tests_outcomes"][: i + 1])) / len(per_ex), 1)

    summary = {
        "model": label,
        "claude_model_arg": args.model,
        "runner": "claude-code (headless)",
        "tries": args.tries,
        "exercises_total": len(exercises),
        **{f"pass_rate_{i + 1}": pass_rate(i) for i in range(args.tries)},
        "passed_first_try": sorted(r["testcase"] for r in per_ex if r["tests_outcomes"][:1] == [True]),
        "passed_after_retry": sorted(
            r["testcase"] for r in per_ex
            if r["tests_outcomes"][:1] == [False] and any(r["tests_outcomes"])
        ),
        "failed": sorted(r["testcase"] for r in per_ex if not any(r["tests_outcomes"])),
        "cost_usd": round(sum(r["cost_usd"] for r in per_ex), 4),
        "turns_total": sum(r["turns"] for r in per_ex),
        "seconds_per_case": round(sum(r["duration"] for r in per_ex) / len(per_ex), 1),
        "wall_seconds": round(time.time() - t0, 1),
        "tests_hidden_from_model": True,
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "per_exercise": per_ex,
    }
    out = RESULTS_DIR / f"claude_benchmark_{label}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    rates = ", ".join(f"pass@{i + 1}={summary[f'pass_rate_{i + 1}']}%" for i in range(args.tries))
    print(f"\n{label}: {rates}  {summary['seconds_per_case']}s/case  "
          f"${summary['cost_usd']:.2f} equivalent -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
