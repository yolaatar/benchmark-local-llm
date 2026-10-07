r"""Run a Python subset of aider's polyglot benchmark against each local Ollama model.

For every model in bench_config.MODELS this script:
  1. prepares a copy of the seeded 25-exercise Python subset,
  2. preloads the model in Ollama (so load time is not charged to the first exercise),
  3. runs aider's own harness (vendor/aider/benchmark/benchmark.py),
  4. aggregates the per-exercise .aider.results.json into results/aider_benchmark_<model>.json.

Usage:
  .venv\Scripts\python.exe run_aider_benchmark.py                   # all models
  .venv\Scripts\python.exe run_aider_benchmark.py --models qwen2.5-coder:7b
  .venv\Scripts\python.exe run_aider_benchmark.py --resume          # continue the latest runs
  .venv\Scripts\python.exe run_aider_benchmark.py --num-exercises 3 # quick smoke test

Warning: aider's harness executes LLM-written Python (pytest on the generated code).
Upstream recommends Docker; here it runs natively on Windows (see NOTES.md).
"""

import argparse
import datetime
import json
import random
import shutil
import subprocess
import sys
import time
import urllib.request

import yaml

from bench_config import (
    BENCH_NUM_EXERCISES,
    BENCH_SEED,
    BENCH_TRIES,
    MODEL_SETTINGS,
    MODELS,
    OLLAMA_API_BASE,
    PYTHON,
    RESULTS_DIR,
    ROOT,
    VENDOR_DIR,
    aider_model_name,
    base_env,
)

POLYGLOT_PY = VENDOR_DIR / "polyglot-benchmark" / "python" / "exercises" / "practice"
BENCH_DIR = ROOT / "tmp.benchmarks"
LOG_DIR = RESULTS_DIR / "logs"


def select_exercises(n):
    names = sorted(p.name for p in POLYGLOT_PY.iterdir() if p.is_dir())
    if n >= len(names):
        return names
    return sorted(random.Random(BENCH_SEED).sample(names, n))


def prepare_exercises_dir(exercises):
    """Copy only the selected exercises, so the harness never sees the others."""
    subset_name = f"polyglot-py{len(exercises)}"
    dest = BENCH_DIR / subset_name / "python" / "exercises" / "practice"
    if dest.exists() and sorted(p.name for p in dest.iterdir()) == exercises:
        return subset_name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in exercises:
        shutil.copytree(POLYGLOT_PY / name, dest / name)
    return subset_name


def ollama(path, payload=None, timeout=1800):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        OLLAMA_API_BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def check_ollama(tags):
    try:
        available = {m["name"] for m in ollama("/api/tags")["models"]}
    except OSError as e:
        sys.exit(f"Ollama is not reachable at {OLLAMA_API_BASE}: {e}")
    missing = [t for t in tags if t not in available]
    if missing:
        sys.exit(f"Missing Ollama models, run `ollama pull` first: {missing}")


def model_settings(tag):
    for entry in yaml.safe_load(MODEL_SETTINGS.read_text()):
        if entry["name"] == aider_model_name(tag):
            return entry
    return {}


def preload(tag, num_ctx):
    """Unload every other model, then load `tag` with the context size aider will request."""
    for m in ollama("/api/ps").get("models", []):
        if m["name"] != tag:
            ollama("/api/generate", {"model": m["name"], "keep_alive": 0})
    t0 = time.time()
    ollama(
        "/api/generate",
        {"model": tag, "prompt": "", "keep_alive": "30m", "options": {"num_ctx": num_ctx}},
    )
    ps = next((m for m in ollama("/api/ps")["models"] if m["name"] == tag), {})
    size, vram = ps.get("size", 0), ps.get("size_vram", 0)
    print(
        f"   loaded {tag} in {time.time() - t0:.1f}s, "
        f"{vram / 1e9:.1f}/{size / 1e9:.1f} GB on GPU (num_ctx={num_ctx})",
        flush=True,
    )
    return {"num_ctx": num_ctx, "size_gb": round(size / 1e9, 2), "size_vram_gb": round(vram / 1e9, 2)}


def find_latest_run(label):
    runs = sorted(BENCH_DIR.glob(f"*--bench-{label}"))
    return runs[-1] if runs else None


def aggregate(run_dir, tag, label, exercises, edit_format, tries, wall_s, load_info):
    per_ex = []
    for res_file in sorted(run_dir.glob("python/exercises/practice/*/.aider.results.json")):
        res = json.loads(res_file.read_text(encoding="utf-8"))
        res.pop("chat_hashes", None)
        res["testcase"] = res.get("testcase", res_file.parent.name)
        per_ex.append(res)

    n_total = len(exercises)
    ok = [r for r in per_ex if "exception" not in r]

    def outcomes(r):
        return r.get("tests_outcomes") or []

    def pass_rate(i):
        passed = sum(1 for r in ok if any(outcomes(r)[: i + 1]))
        return round(100 * passed / n_total, 1) if n_total else None

    def total(key):
        return sum(r.get(key) or 0 for r in ok)

    duration = total("duration")
    summary = {
        "model": tag,
        "aider_model": aider_model_name(tag),
        "edit_format": edit_format,
        "tries": tries,
        "exercises_total": n_total,
        "exercises_completed": len(per_ex),
        "exercises_with_exception": len(per_ex) - len(ok),
        **{f"pass_rate_{i + 1}": pass_rate(i) for i in range(tries)},
        "passed_first_try": sorted(r["testcase"] for r in ok if outcomes(r)[:1] == [True]),
        "passed_after_retry": sorted(
            r["testcase"] for r in ok if outcomes(r)[:1] == [False] and any(outcomes(r))
        ),
        "failed": sorted(r["testcase"] for r in ok if not any(outcomes(r))),
        "not_run": sorted(set(exercises) - {r["testcase"] for r in per_ex}),
        "percent_cases_well_formed": round(
            100 * sum(1 for r in ok if not r.get("num_malformed_responses")) / len(ok), 1
        )
        if ok
        else None,
        "num_malformed_responses": total("num_malformed_responses"),
        "num_exhausted_context_windows": total("num_exhausted_context_windows"),
        "syntax_errors": total("syntax_errors"),
        "indentation_errors": total("indentation_errors"),
        "lazy_comments": total("lazy_comments"),
        "test_timeouts": total("test_timeouts"),
        "prompt_tokens": total("prompt_tokens"),
        "completion_tokens": total("completion_tokens"),
        "cost_usd": round(total("cost"), 4),  # 0 for local models, kept for comparison
        "model_seconds_total": round(duration, 1),
        "seconds_per_case": round(duration / len(ok), 1) if ok else None,
        "wall_seconds": round(wall_s, 1),
        "completion_tokens_per_second": round(total("completion_tokens") / duration, 1)
        if duration
        else None,
        "ollama_load": load_info,
        "run_dir": str(run_dir),
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "per_exercise": per_ex,
    }
    out = RESULTS_DIR / f"aider_benchmark_{label}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out, summary


def run_model(tag, args, exercises, subset_name):
    label = MODELS.get(tag, tag.replace(":", "-"))
    run_dir = find_latest_run(label) if args.resume else None
    if run_dir is None:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        run_dir = BENCH_DIR / f"{stamp}--bench-{label}"
    print(f"\n=== {tag} -> {run_dir.name}", flush=True)

    num_ctx = model_settings(tag).get("extra_params", {}).get("num_ctx", 16384)
    load_info = preload(tag, num_ctx)

    env = base_env()
    env["AIDER_DOCKER"] = "1"  # the harness refuses to run without it, see NOTES.md
    env["AIDER_BENCHMARK_DIR"] = str(BENCH_DIR)

    cmd = [
        str(PYTHON),
        str(ROOT / "bench_harness.py"),
        run_dir.name,
        "--model", aider_model_name(tag),
        "--edit-format", args.edit_format,
        "--threads", "1",
        "--tries", str(args.tries),
        "--exercises-dir", subset_name,
        "--languages", "python",
        "--read-model-settings", str(MODEL_SETTINGS),
    ]
    if run_dir.exists():
        cmd.append("--cont")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"aider_benchmark_{label}.log"
    t0 = time.time()
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n\n##### {datetime.datetime.now().isoformat()} {' '.join(cmd)}\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=VENDOR_DIR / "aider",  # the harness reads its git hash from here
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        done = 0
        for line in proc.stdout:
            log.write(line)
            log.flush()
            # Only echo progress, the full transcript goes to the log
            if line.startswith("fnames:"):
                done += 1
                name = line.strip().split("\\")[-2] if "\\" in line else line.strip()
                print(f"   [{done}/{len(exercises)}] {name}", flush=True)
            elif line.strip() == "Test failed":  # harness crash on an exercise (model errors are normal)
                print("   " + line.rstrip(), flush=True)
        proc.wait()
    wall = time.time() - t0

    out, summary = aggregate(
        run_dir, tag, label, exercises, args.edit_format, args.tries, wall, load_info
    )
    rates = ", ".join(f"pass@{i + 1}={summary[f'pass_rate_{i + 1}']}%" for i in range(args.tries))
    print(
        f"   done in {wall / 60:.1f} min ({summary['exercises_completed']}/"
        f"{summary['exercises_total']} exercises): {rates} -> {out.relative_to(ROOT)}",
        flush=True,
    )
    if proc.returncode != 0:
        print(f"   WARNING: harness exited with code {proc.returncode}, see {log_path}", flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", nargs="*", default=list(MODELS), help="Ollama tags")
    parser.add_argument("--num-exercises", type=int, default=BENCH_NUM_EXERCISES)
    parser.add_argument("--tries", type=int, default=BENCH_TRIES)
    parser.add_argument(
        "--edit-format",
        default="whole",
        help="aider edit format (whole is aider's advice for local/experimental models)",
    )
    parser.add_argument("--resume", action="store_true", help="continue the latest run per model")
    args = parser.parse_args()

    if not POLYGLOT_PY.exists():
        sys.exit("vendor/polyglot-benchmark missing, see NOTES.md setup section")
    check_ollama(args.models)
    RESULTS_DIR.mkdir(exist_ok=True)
    BENCH_DIR.mkdir(exist_ok=True)

    exercises = select_exercises(args.num_exercises)
    subset_name = prepare_exercises_dir(exercises)
    print(f"{len(exercises)} Python exercises (seed {BENCH_SEED}): {', '.join(exercises)}")
    print("WARNING: running LLM-generated code natively (no Docker), see NOTES.md.")

    summaries = [run_model(tag, args, exercises, subset_name) for tag in args.models]

    print("\n=== Summary")
    for s in summaries:
        rates = "  ".join(f"pass@{i + 1}={s[f'pass_rate_{i + 1}']:>5}%" for i in range(args.tries))
        print(f"{s['model']:<26} {rates}  {s['seconds_per_case']}s/case")


if __name__ == "__main__":
    main()
