# Lab brief: self-hosted coding agents on NeuroPoly GPUs

Source material for the second lab presentation. The first presentation covered "local LLMs on a 16 GB PC vs Claude Code". This one answers: **can the lab run its own coding assistant on its own GPUs, for several people at once, and what is ready to use today?**

Written 2026-10-06. Detailed history: `RAPPORT.md` (in French, results of round 1), `NOTES.md` (how to run the bench). Deployment scripts and runbook: `lab_server/`.

Status legend used below: **[measured]** = we ran it and have numbers, **[verified]** = we ran it once and it worked, **[ready, untested]** = scripts written, not yet run on tassan, **[external]** = from published sources, not reproduced here.

---

## 1. One-slide summary

- Round 1 (PC, RTX 5060 Ti 16 GB): the best local model (35B MoE) scored 60 % on the Aider polyglot benchmark vs 96 % for Claude Sonnet 5, and 1 clean result out of 5 real ADS tasks vs 5/5. Small local models failed mostly on tooling (edit formats, empty files, truncated answers), not only on code quality.
- Round 2 (lab station tassan, 2 x RTX PRO 6000 Blackwell 96 GB): an 80B coding model (`qwen3-coder-next`) runs **entirely on one of the two cards**, at 54 tok/s, with 64k context, the second card untouched. **[measured]**
- The remaining questions are no longer "does it fit" but "which harness" and "how do several people share it".
- Proposed setup: **vLLM** serving one coding model on one tassan card, reached by each lab member through their own **SSH tunnel**, used from **OpenCode** (open-source agent, MIT) or **Claude Code** pointed at the lab server. No data leaves Polytechnique's network, no root access needed, no per-user cost.

## 2. Hardware available at NeuroPoly

| Station | GPUs | Verdict for serving a coding model |
|---|---|---|
| bireli | 2 x GTX TITAN X (2014) | Not worth it, slower than a recent consumer card |
| rosenberg | 8 x Tesla P100 16 GB (2016) | Possible with llama.cpp only (vLLM needs compute capability 7.0+), would take half the machine for an 80B, slow on long prompts |
| romane | 4 x RTX A6000 48 GB (2020) | Good fallback: an 80B fits on 1 to 2 cards |
| **tassan** | **2 x RTX PRO 6000 Blackwell Max-Q 96 GB (2025)** | **Best choice: one card holds an 80B model, native FP8/FP4, the other card stays free** |

Tassan inventory (2026-09-28) **[measured]**: 125 GB RAM, 48 cores, driver 580.95, CUDA 13.0, Ubuntu (glibc 2.39), both cards idle at the time, home quota 500 GB (172 GB used before our install), no HTTP proxy, docker and podman binaries present (group access not checked), no root needed for anything below.

## 3. What was measured on tassan (round 2)

Install: Ollama 0.34.4 unpacked in `~/llm-bench` (no system install, no `.bashrc` change, environment in `~/llm-bench/env.sh`), server in a tmux session, bound to `127.0.0.1` only, pinned to card 0 (`CUDA_VISIBLE_DEVICES=0`, and `OLLAMA_VULKAN=0`, otherwise Ollama also sees card 1 through Vulkan).

| | qwen3.6 35B-A3B on the PC (round 1) | qwen3-coder-next 80B-A3B on tassan |
|---|---|---|
| Size (Q4) | 22 GB | 54 GB |
| Placement | 59 % GPU, 41 % in system RAM | **100 % GPU** |
| Generation | 68 to 89 tok/s | **54 tok/s** |
| Context used | 32k to 64k (fought for it) | 64k, plenty of room left |
| First load | ~1 min | 104 s (cold read from encrypted home; cached afterwards) |
| Other card | n/a | untouched (15 MiB used) |

Not measured yet: prompt processing speed at long context (the one test run had a 20-token prompt, the "1 tok/s" it printed is a warm-up artifact), the 25-exercise benchmark with the 80B, the 5 ADS tasks with the 80B, and any agent run (Claude Code or OpenCode) against tassan.

## 4. How a shared GPU handles several users

Key point for the audience: **the harness (the agent on your laptop) has nothing to do with multi-user. The inference server does.** Each person runs their own agent; all agents send requests to one server; the server decides how they share the GPU.

**Ollama** (what we use today):
- `OLLAMA_NUM_PARALLEL` = number of requests decoded together. On tassan the log shows it at **1**, so requests are strictly sequential: user B waits until user A's whole answer is generated. With agents that make dozens of calls per task, two people working at once will feel it.
- Raising it to N lets N requests share each GPU pass (more total throughput, slower per user), but every slot reserves its own full context window, so memory grows N x context.
- Requests beyond the active slots wait in a queue (`OLLAMA_MAX_QUEUE`, default 512); beyond that, Ollama returns HTTP 503 "server busy".
- Fine for one person, or a few with patience.

**vLLM** (recommended for the lab):
- Built for many concurrent users: continuous batching (new requests join the running batch at every step) and paged KV cache (memory allocated as needed, not reserved per slot). Prefix caching reuses the long system prompts that agents resend on every call.
- Speaks both the OpenAI API (for OpenCode and most tools) and the Anthropic Messages API (for Claude Code), so one server feeds every harness.
- Published reference point **[external]**: on one RTX PRO 6000, Qwen3.6-35B-A3B FP8 in vLLM keeps time-to-first-token around 0.5 s for one user and ~1.4 s with 64 concurrent users (Jarvislabs, June 2026).

Our own measuring tool: `concurrency_bench.py` simulates N users (all at once, staggered, or random arrivals) against Ollama or vLLM and reports time to first token (p50/p95, this is where queueing shows), end-to-end latency, tokens/s per user, total tokens/s, rejected requests and peak VRAM. **[verified against a simulated server only]**: with one slot, time to first token went 0.3 s -> 3.7 s -> 4.8 s for 1 -> 4 -> 8 users and 6 of 16 requests got 503; with 4 slots total throughput went up ~4x. Real numbers on tassan are the next measurement.

## 5. Harness comparison (single user)

What a harness is: the program around the model that builds the prompt, gives it tools (read file, edit, run shell, search), applies its edits, and loops until done. Round 1 showed it matters a lot: Aider has no tool calling (it parses edit blocks out of plain text), so a model that writes its code in the wrong format produces an empty file. Official Aider leaderboard **[external]**: the same Qwen2.5-Coder-32B scores 16.4 % with the `whole` edit format and 8.0 % with `diff`, a factor of 2 from the format alone.

| Harness | Type | License | Works with lab server | Notes |
|---|---|---|---|---|
| Aider | Fixed loop, text edit formats, human picks files | Apache 2.0 | yes | What round 1 used. Keep only to replay the benchmark. |
| **Claude Code** pointed at the lab server | Full agent: explores repo, edits, runs tests, sub-agents | Proprietary client, free to run against your own server | yes (Anthropic API, native in Ollama and vLLM) | **[verified]** on the PC with the 35B (read a file and added a correct function in 49 s; the 7B said "Done." without calling any tool). Same loop as the Sonnet runs of round 1, so it isolates the model. Known limit: Qwen3-Coder-Next does not use Claude Code's sub-agent (Task) tool. |
| **OpenCode** | Full agent, terminal + desktop/IDE | MIT | yes (OpenAI-compatible API) | Most used open-source agent (~200k GitHub stars). Provider-agnostic. **Recommended open default for the lab.** Config ready, not yet run against tassan. |
| OpenHands | Full agent in a Docker sandbox, web UI | MIT | yes | Best published local result **[external]**: Qwen3-Coder reaches 69.6 % on SWE-bench Verified with OpenHands (500 turns). Heavier to deploy (Docker runtime). Interesting for a shared web interface later. |
| Qwen Code | Qwen's own CLI (Gemini CLI fork) | Apache 2.0 | yes | Tuned to Qwen's tool-call format. Fallback if tool calling misbehaves in OpenCode. |
| Goose, Cline | General MCP agent / VS Code agent | Apache 2.0 | yes | Secondary options. |

### About Odysseus (PewDiePie's project)

Real and well made: MIT, ~81k GitHub stars, Docker install, works with vLLM / llama.cpp / Ollama / cloud APIs. It is a **personal AI workspace**: chat with memory, deep research, RAG, notes, calendar, email, browser automation, and agents with file, shell and MCP access. Its companion model Ajax is a fine-tuned Qwen 3.5 9B aimed at browsing, email and calendar, not code. It has login (`AUTH_ENABLED`), but no documented team or concurrency features. **Verdict: not a coding harness on the level of Claude Code / OpenCode, not a multi-user platform. Nice personal front-end, could sit on top of the lab server.** For a shared chat UI, Open WebUI is the established option (multi-user accounts, history, document Q&A).

### Does a better harness close the gap with Claude Code?

Partly. The model sets the ceiling, mostly through how reliably it calls tools. But the tassan models are a different class from what round 1 tested on the PC (80B vs 7-35B, full context, no RAM spill), and even round 1's best model (35B) handled tool calls and formats reasonably. The honest framing for the talk: **round 3 measures exactly this**, same 5 ADS tasks, same model on tassan, different harnesses.

## 6. Model choice for the lab server

Constraint: one 96 GB card, leaving room for the KV cache of several users.

| Model | Format | Weights | Fits one card | Notes |
|---|---|---|---|---|
| **Qwen3-Coder-Next 80B-A3B** | NVFP4 (`RedHatAI/Qwen3-Coder-Next-NVFP4`) | ~45 GB | yes, ~40 GB left for users | **Default.** Coding/agent model, non-thinking (fast answers), 256k context, `qwen3_coder` tool parser. Blackwell runs FP4 natively. Red Hat reports quality on par with the original on SWE-bench Lite **[external]**. |
| Qwen3-Coder-Next 80B-A3B | FP8 (`unsloth/Qwen3-Coder-Next-FP8-Dynamic`) | ~80 GB | barely, ~10 GB left | Near-lossless, but little room for concurrent users. |
| Qwen3.6-35B-A3B | FP8 (`Qwen/Qwen3.6-35B-A3B`) | ~35 GB | yes, lots of room | Jarvislabs' pick for one RTX PRO 6000 **[external]**. Thinking model (slower per answer). Same family as round 1's best model, so a clean "same model, better hardware" point. |
| Qwen3-Coder-Next | Q4 GGUF via Ollama (current) | 54 GB | yes | What runs today. **[measured]** |

Qwen3-Coder-Next published scores **[external]**: 42.8 % SWE-bench Verified, 44.3 % SWE-bench Pro (Qwen technical report, harness-dependent).

## 7. The proposed lab setup ("key in hand")

```
 lab member's laptop (VPN Poly)                      tassan (card 0)
 ┌───────────────────────────────┐   SSH tunnel    ┌──────────────────────────────┐
 │ OpenCode  or  Claude Code      │ ──────────────► │ vLLM  127.0.0.1:8000         │
 │ works on the laptop's files    │  own lab login  │ qwen3-coder-next (NVFP4)     │
 └───────────────────────────────┘                 │ OpenAI + Anthropic APIs      │
                                                   │ API key shared with the lab  │
 or: run the agent ON tassan, it then sees the     └──────────────────────────────┘
 cluster filesystem with the user's own Unix permissions (nothing crosses the network)
```

- **Access control**: the server listens on localhost only, so you need a tassan login to reach it (the SSH tunnel uses your own lab account), plus a shared API key. Nothing exposed on the network.
- **Data**: prompts and code never leave Polytechnique's network. With the agent running on tassan itself, they never leave the machine.
- **Cost**: zero per use. The cost is one GPU of tassan while the server runs.
- **Footprint**: everything in one folder of one user's home (`~/llm-bench`), removable with `rm -rf`. No root, no system service, no `.bashrc` change. Server runs in tmux; it does not restart on its own after a reboot (deliberate on a shared station).
- **Lab-side decisions needed**: who owns the server, which card it may occupy and when (permanent vs on-demand), whether to share one API key or add per-user keys (LiteLLM gateway, phase 3).

Files (all in `lab_server/`): `PLAN.md` (step-by-step runbook with checkpoints), `USER_GUIDE.md` (one page for lab members), `cluster/*.sh` (install, start, stop, status on tassan), `client/*.ps1` + `client/opencode.json` (tunnel and agents on a Windows laptop).

## 8. What is ready vs what remains to run (be honest on the slides)

| Item | Status |
|---|---|
| Ollama + 80B model on tassan, card 0 only | **[measured]** |
| Claude Code on a local backend (PC) | **[verified]** |
| SSH tunnel from laptop to tassan | commands given in round 2, not confirmed run |
| vLLM install + serve scripts for tassan | **[ready, untested]** |
| OpenCode config + launchers for tassan (Ollama and vLLM) | OpenCode 1.18.35 installed on the laptop, loads the config (only the tassan models visible, sharing disabled); check script validated against a mock server. Not yet run against tassan |
| Multi-user load test tool | **[verified on a simulated server]**, one-command sweep for tassan (`run_concurrency.sh`) |
| 25-exercise benchmark and 5 ADS tasks with the 80B | not run |
| Harness comparison (Claude Code vs OpenCode, same model) on the 5 ADS tasks | runner written (`run_tassan_tasks.py`, OpenCode output format checked against a mock server), not run |

If the presentation must show "tested" solutions, the minimum to run first is: `PLAN.md` phases 1 to 3 (tunnel + OpenCode on the current Ollama server, then vLLM, then the concurrency sweep). Roughly half a day including model download.

## 9. Key messages for the talk

1. The hardware question is solved: one tassan card runs an 80B coding model fully in VRAM, faster than our PC ran a 35B, with the other card free.
2. Multi-user is a server problem, not a harness problem. Ollama queues people one by one by default; vLLM is built to serve many at once. We have a tool to measure it on our own machine.
3. The harness is the other half of the result. Aider lost work on formatting; agentic harnesses (Claude Code, OpenCode, OpenHands) give the model real tools. Odysseus is a nice personal workspace, not the answer to this question.
4. Privacy is the strongest argument for the lab: medical imaging code and data never leave Poly's network, with no per-seat cost.
5. Still, round 1 showed local models make confident mistakes and silent regressions. Same rule as before: use it for work you will read line by line, or with tests you trust.

## Sources

- Round 1 results: `RAPPORT.md`, `results/*.json`
- Aider polyglot benchmark: https://aider.chat/2024/12/21/polyglot.html, leaderboard https://aider.chat/docs/leaderboards/
- Qwen3-Coder-Next: https://unsloth.ai/docs/models/qwen3-coder-next, technical report https://arxiv.org/html/2603.00729v1
- NVFP4 checkpoint: https://huggingface.co/RedHatAI/Qwen3-Coder-Next-NVFP4
- Coding model on one RTX PRO 6000 (Jarvislabs, 2026-06-25): https://jarvislabs.ai/blog/coding-model-rtx-pro-6000
- vLLM with Claude Code: https://docs.vllm.ai/en/latest/serving/integrations/claude_code/
- OpenCode providers: https://opencode.ai/docs/providers/
- OpenHands + Qwen3-Coder: https://qwenlm.github.io/blog/qwen3-coder/
- Open-source coding agents overview: https://www.morphllm.com/ai-coding-assistant-open-source
- Odysseus: https://github.com/pewdiepie-archdaemon/odysseus, https://www.makeuseof.com/pewdiepie-open-sourced-his-personal-llm-workspace/
- Ajax model: https://www.popularai.org/p/pewdiepie-ajax-ai-model
- Team LLM stacks (vLLM + Open WebUI + LiteLLM): https://www.spheron.network/blog/self-host-open-webui-librechat-gpu-cloud/
