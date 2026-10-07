"""Thin wrapper around vendor/aider/benchmark/benchmark.py.

It only forces aider's chat language to English: on Windows aider picks the system locale
(French here) and adds "Reply in French" to every prompt, which would make our numbers
incomparable with published aider results. Everything else is the upstream harness as-is.
"""

import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent / "vendor" / "aider" / "benchmark"
sys.path.insert(0, str(HARNESS_DIR))

from aider.coders import base_coder  # noqa: E402

base_coder.Coder.get_user_language = lambda self: "English"

import benchmark  # noqa: E402

if __name__ == "__main__":
    benchmark.app()
