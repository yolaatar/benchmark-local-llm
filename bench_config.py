"""Shared configuration for the local LLM benchmark."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_SCRIPTS = ROOT / ".venv" / "Scripts"
PYTHON = VENV_SCRIPTS / "python.exe"
AIDER = VENV_SCRIPTS / "aider.exe"
RESULTS_DIR = ROOT / "results"
TASKS_DIR = ROOT / "custom_tasks"
VENDOR_DIR = ROOT / "vendor"
AIDER_REPO = VENDOR_DIR / "aider"
MODEL_SETTINGS = ROOT / "aider_model_settings.yml"
MODEL_METADATA = ROOT / "aider_model_metadata.json"

OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")

# One model per size tier. Keys are the Ollama tags, values are short labels used in filenames.
MODELS = {
    "qwen2.5-coder:7b": "qwen2.5-coder-7b",
    "qwen2.5-coder:14b": "qwen2.5-coder-14b",
    "qwen3.6:35b-a3b-coding": "qwen3.6-35b-a3b-coding",
}

# Aider provider prefix. "ollama_chat/" uses Ollama's /api/chat endpoint (recommended by aider docs).
AIDER_PREFIX = "ollama_chat/"

# Polyglot benchmark subset: 25 of the 34 Python exercises, sampled with random.Random(42).
BENCH_SEED = 42
BENCH_NUM_EXERCISES = 25
BENCH_TRIES = 2


def aider_model_name(ollama_tag: str) -> str:
    return AIDER_PREFIX + ollama_tag


def base_env() -> dict:
    env = os.environ.copy()
    env["OLLAMA_API_BASE"] = OLLAMA_API_BASE
    env["PATH"] = str(VENV_SCRIPTS) + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"  # live progress from the harness subprocess
    # Keep aider from phoning home or prompting during unattended runs
    env["AIDER_ANALYTICS"] = "false"
    env["AIDER_CHECK_UPDATE"] = "false"
    env["AIDER_SHOW_RELEASE_NOTES"] = "false"
    return env
