# Lab meeting plan: local coding models on the lab's GPUs

Old deck: `~/Downloads/20260921_localmodels.pdf` (19 slides). The PC results are dropped; the story is now "can the lab run its own coding assistant on tassan, for everyone".

Target: ~15 slides, ~12 min. Slides marked **[quick]** are 20 to 30 s each. Slides marked **[if ready]** depend on the tassan runs (another session); each has a fallback.

| # | Slide | Source | Time |
|---|---|---|---|
| 1 | Title | old 1, retitled | 10 s |
| 2 | Where we left off | old 2 | 30 s |
| 3 | Poll: which AI | old 3 | 20 s |
| 4 | Poll: what for | old 4 | 20 s |
| 5 | Open source is closing the gap | old 6 | 20 s |
| 6 | SWE-rebench | old 7 | 20 s |
| 7 | Benchmarks contradict each other | old 8 | 20 s |
| 8 | Our own tasks | old 12, reworked | 45 s |
| 9 | The lab's GPUs | old 17/18, merged | 45 s |
| 10 | The stack on the cluster | new, replaces old 9 | 1 min |
| 11 | The harness: OpenCode vs Claude Code | new, replaces old 10 | 1 min |
| 12 | Models compared | old 11, reworked | 45 s |
| 13 | Results on our tasks | new, replaces old 13/14 | 1.5 min |
| 14 | Multi-user: one server for the whole lab | new | 1 min |
| 15 | Scalability | new | 1 min |
| 16 | Takeaways and what we need to decide | new, replaces old 15/16/19 | 1 min |

Removed: old 5 ("The ?"), 9 (PC stack), 10 (how aider works), 13 to 16 (PC results), 19 (how can we make it work, now answered by 10, 14, 15).

---

## 1. Title

Retitle to put the lab angle up front, e.g. **"Can the lab run its own coding assistant?"**, with the new date.

Talking points:
- Follow-up of the talk from a few weeks ago, short version.

## 2. Where we left off [quick]

Keep as is.

Talking points:
- Thomas' survey: almost everyone uses AI, mostly for coding.
- Two options on the table: a shared subscription, or our own models. Privacy is the open question.

## 3. Poll: which AI [quick]

Keep. Point at Claude 80 %, ChatGPT and Gemini ~48 %.

## 4. Poll: what for [quick]

Keep. Point at code writing (88 %) and code analysis (84 %): this is why the talk focuses on coding.

## 5. Open source is closing the gap [quick]

Keep the Aider leaderboard table.

Talking points:
- Open models are now within reach of the closed ones on some benchmarks.
- One line: this is what made the question worth testing.

## 6. SWE-rebench [quick]

Keep the chart.

Talking points:
- It compares models *and* agents. The agent around the model matters, which is the point of slide 11.

## 7. Benchmarks contradict each other [quick]

Keep.

Talking points:
- Different task sizes, different harnesses, so the rankings don't agree.
- 90 % on a benchmark doesn't mean "it'll solve my problems". So I tested on our own tasks.

## 8. Our own tasks

Rework old slide 12: keep the 5 custom tasks, drop or shrink the Exercism line.

Talking points:
- These are real AxonDeepSeg tasks, things I actually do every week:
  - add a CLI flag
  - write a pytest module
  - explain the morphometrics pipeline to a newcomer
  - find a real bug from a bug report
  - a refactor across 5 files
- Each one starts from a pinned commit, the agent gets the prompt once, and I review the diff by hand.
- They range from easy (explain) to hard (multi-file refactor), on purpose.
- Last time on my PC, small models couldn't do most of them. Hardware was the limit (16 GB of VRAM). Say it in one sentence, without showing the PC results.

## 9. The lab's GPUs

Merge old 17 and 18 (the GPU cluster page plus the "in theory" bullets).

Talking points:
- Four stations; tassan is the one that matters: 2 x RTX PRO 6000, 96 GB each (2025).
- One tassan card holds an 80B coding model entirely, and the other card stays free for training.
- Already measured: Qwen3-Coder-Next 80B on one card at 54 tok/s, 64k context, 100 % on the GPU.
- Fallback stations: romane (4 x A6000), and rosenberg only with llama.cpp, slow.

## 10. The stack on the cluster [if ready]

Figure: `slides/cluster_setup.png`. Regenerate with `python make_cluster_figures.py` if the setup changes, e.g. which harness or model.

Talking points:
- **vLLM** serves the model on card 0. It speaks both the OpenAI and the Anthropic API, so any agent can plug in.
- Each person keeps their agent on their laptop, with an SSH tunnel using their own tassan login.
- The agent works on your local files and runs your tests. Only the prompts go to tassan.
- Privacy: everything stays inside Poly's network. The server listens on localhost only, so nothing is exposed.
- Footprint: no root, one folder in my home directory, removable in one command.
- Variant: run the agent on tassan itself, so it sees the cluster files and nothing crosses the network.

Fallback if vLLM isn't up: same diagram with Ollama (already working on tassan). Say vLLM is the next step because of slide 14.

## 11. The harness: OpenCode vs Claude Code

Replaces "how aider works". I'm assuming "open router" meant **OpenCode** (the open-source agent). OpenRouter is a cloud API that resells models, which is the opposite of keeping things local; if that's actually what you meant, this slide changes.

Talking points:
- The harness is the program around the model: it gives the model tools (read file, edit, run a command, search), applies the edits and loops until it's done.
- Last time's harness, Aider, parsed edits out of plain text. Many failures came from that, not from the model.
- **OpenCode**: open source (MIT), the most used open agent. It works with any model, and it does what Claude Code does: explores the repo, edits several files, runs the tests, plans.
- How close to Claude Code: same kind of loop and the same tools. Claude Code is more polished (sub-agents, hooks, very good defaults), and some local models don't use all its features (Qwen3-Coder-Next ignores the sub-agent tool).
- Claude Code itself can also point at our server, with no Anthropic account needed for that.
- With the model fixed, comparing the two harnesses on our tasks isolates the effect of the harness (slide 13).

Figure idea: a small table of the two side by side (license, works with our server, tools, sub-agents, IDE/desktop).

## 12. Models compared [depends on what gets tested]

Talking points, depending on the models that end up tested:
- **Qwen3-Coder-Next 80B** (default): a coding model built for agents, answers fast (no thinking step), 256k context, 4-bit NVFP4 at ~45 GB.
- **Qwen3.6 35B-A3B** (option): smaller and leaves most of the card free, but it thinks before answering, so it's slower per answer. Same family as last time's best model.
- **Claude Sonnet** as the reference ceiling.
- One line on quantization: 4-bit float with fine scaling, about a quarter of the original size, small loss, native on Blackwell. FP8 exists if precision matters.

Fallback: if only the 80B gets tested, cut this slide and give the model its own line on slide 10 or 13.

## 13. Results on our tasks [if ready]

The main results slide. `make_cluster_figures.py` prints the raw table (time, turns, files changed); success comes from reviewing the diffs.

Suggested table: rows = the 5 tasks, columns = 80B + OpenCode, 80B + Claude Code, Claude Sonnet (reference). Last row: score and total time.

Talking points:
- The headline: how many of the 5 tasks the cluster model solves, and how that compares to Claude.
- Harness effect: same model, OpenCode vs Claude Code, does it change anything?
- What still fails, e.g. silent regressions on the refactor. Be honest about it.
- Time per task, vs Claude.

Fallback if not run in time: show that it works end to end (a screenshot of an agent editing a repo through the tunnel and the test passing, from `smoke-test.ps1`), and present the task comparison as the next step.

## 14. Multi-user: one server for the whole lab

Talking points:
- Key message: **multi-user is a server problem, not a harness problem.** Everyone runs their own agent, all agents send requests to one server, and the server decides how they share the GPU.
- Ollama (default): one request at a time, so person B waits until person A's answer is done. Agents make dozens of calls per task, so two people working at once will feel it.
- vLLM: built for this. Requests join the running batch at every step (continuous batching), memory is allocated as needed rather than reserved per user, and long system prompts that agents resend on every call get reused.
- Access: your tassan login (SSH) plus a shared lab key.
- What a lab member needs to start: VPN, tassan login, the client folder, about 5 minutes (`USER_GUIDE.md`).

Figure idea: two small timelines, "Ollama: users served one after another" vs "vLLM: users served together".

## 15. Scalability [if ready]

Figure: `slides/concurrency.png` (generated from the tassan load test).

Talking points:
- The two numbers that matter:
  - **wait before the first word** at 4 and 8 simultaneous users (what people feel)
  - **total tokens/s** (how much work one card does)
- Read the curve: up to N users it stays comfortable, beyond that it degrades. Give the actual N.
- What limits it: the memory left for users' context (~40 GB with the 4-bit 80B). A smaller model or shorter context means more users.
- Realistic load: lab members don't all send requests at the same second. The random-arrival run (8 users) is closer to real life.
- If we outgrow one card: the second tassan card (taking it from training), romane as a second server, or a smaller model.
- Later: per-user keys and usage tracking (a LiteLLM proxy in front), and a web chat UI for non-coders (Open WebUI).

Fallback if not measured: show the setup, say what will be measured (these two numbers at 1 to 16 users) and give the external reference point (Jarvislabs: a 35B on one RTX PRO 6000 stays ~0.5 s for 1 user and ~1.4 s at 64 users).

## 16. Takeaways and what we need to decide

Talking points:
- The hardware question is solved: one tassan card runs an 80B coding model.
- `<result line from 13>` / `<scaling line from 15>`
- Privacy: code and data never leave Poly's network, at no per-seat cost.
- Same rule as before: work on a branch and read the diff.
- To decide as a lab:
  - who owns the server
  - does it run permanently on card 0 or on demand
  - which model
  - a shared key or per-user keys
- Who wants to try it?

---

## What to get from the session running tassan, and which slide needs it

| Needed | For slide |
|---|---|
| vLLM up, which checkpoint loaded (NVFP4 or FP8 fallback), start-up time | 10, 12 |
| Screenshot of OpenCode / Claude Code editing a repo through the tunnel | 10 or 13 fallback |
| `custom_*_opencode-tassan-vllm.json`, `custom_*_claude-tassan-vllm.json`, diffs reviewed | 13 |
| `conc_vllm.json`, `conc_vllm_poisson.json`, `conc_ollama_p1.json`, `conc_ollama_p4.json` | 15 |
| CPU and RAM use during the load test (`top`), `nvidia-smi` memory | 15, for questions |
