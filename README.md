# Self-hosted coding assistant for NeuroPoly

Can the lab run its own AI coding assistant on its own GPUs, for several people at once? This repo holds the answer: a model server running on the lab station **tassan**, the scripts to use it from your laptop with **Claude Code** or **OpenCode**, and the benchmarks that led there.

Prompts and code stay inside Polytechnique's network, and there is no per-use cost.

## I want to use it

Read **[`lab_server/USER_GUIDE.md`](lab_server/USER_GUIDE.md)**. In short:

1. You need the Polytechnique VPN, a tassan login, and the lab key (ask Youssef, privately).
2. Open an SSH tunnel to tassan with `lab_server/client/tassan-tunnel.sh` (or `.ps1` on Windows).
3. Start an agent in your project with `lab_server/client/claude-tassan.sh` or `opencode-tassan.sh`.

The guide also shows how to call the model directly from Python or curl (OpenAI-compatible API).

## I run the server

Read **[`lab_server/ADMIN_GUIDE.md`](lab_server/ADMIN_GUIDE.md)**: start, stop, status, changing the model, the key, troubleshooting. The server scripts are in `lab_server/cluster/`, their settings in `lab_server/cluster/vllm.env`.

The full setup history (phases, decisions, what broke and why) is in [`lab_server/PLAN.md`](lab_server/PLAN.md).

## What runs today

- **Model:** Qwen3.6-27B (FP8), served by vLLM on GPU 1 of tassan (RTX PRO 6000 Blackwell, 96 GB).
- **Quality:** on 5 real tasks from the AxonDeepSeg codebase (feature, bug fix, 5-file refactor, test module, code explanation), it matched Claude Sonnet: all tests passing, no regressions, with both Claude Code and OpenCode.
- **Speed:** about 45 tokens/s per user; a real task takes 2 to 12 minutes.
- **Several users:** with 8 simultaneous users each keeps about 90% of their speed; 3 agents working at once each took about twice as long, with the same quality.

## The benchmarks

| Round | Where | What | Details |
|---|---|---|---|
| 1 | a 16 GB PC | small local models (7B to 35B, Ollama + Aider) vs Claude Code: Aider polyglot benchmark and the 5 ADS tasks | [`RAPPORT.md`](RAPPORT.md) (French), how to run: [`NOTES.md`](NOTES.md) |
| 2 | tassan | does an 80B coding model fit on one card | [`LAB_BRIEF.md`](LAB_BRIEF.md) |
| 3 | tassan | the 5 ADS tasks with Claude Code and OpenCode on the lab server: Qwen3-Coder-Next 80B vs Qwen3.6-27B, plus multi-user load tests | `results/custom_*_{claude,opencode}-tassan-*.json`, `results/conc_*.json` |

Round 3 runner: `run_tassan_tasks.py`. Load test: `concurrency_bench.py`. The task definitions and reference solutions are in `custom_tasks/`.
