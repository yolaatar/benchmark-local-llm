# Lab meeting version of the local models talk

Target: 11 slides plus 1 backup, about 10 to 12 min. Old deck: 19 slides (`~/Downloads/20260921_localmodels.pdf`).
Roughly a third recap of round 1 (PC), two thirds the new part (tassan).

Figures: `python make_cluster_figures.py` writes `slides/cluster_setup.png`, and once results are fetched into `results/` it also writes `slides/concurrency.png` and prints the tables below as markdown.

## What happens to the old slides

| Old slide | Fate |
|---|---|
| 1 Title | keep, retitle |
| 2 Where we left off | merge with 3/4 into one "why" slide |
| 3, 4 Poll results | keep one chart (the "what do you use" one), small |
| 5 The ? | cut (the title already asks it) |
| 6, 7 Open source closing the gap, swe rebench | cut |
| 8 Benchmarks contradict each other | cut, one line survives on slide 2 |
| 9 Stack under test | cut (replaced by the new setup diagram) |
| 10 How aider works | cut, one bullet survives on slide 4 |
| 11 Models compared | cut, model names go in the table header |
| 12 Tasks tested | cut, task names are the table rows |
| 13 Results, polyglot | fold into slide 3 as one line |
| 14 Results, ADS tasks | **keep**, it's the round 1 slide |
| 15, 16 Why it's failing, is it viable | merge into slide 4 |
| 17, 18 But we have GPU clusters | merge into slide 5 |
| 19 How can we make it work | replaced by slides 6 to 9 |

---

## Slide 1: title

**Can the lab run its own coding assistant?**
Local models, round 2: from my PC to tassan
Youssef Laatar, lab meeting, <date>

## Slide 2: why we're looking at this

- Thomas' survey: almost everyone uses AI, mostly coding (22/25) and writing
- Open question: a shared subscription, or our own models, for privacy and sensitive data?
- Public benchmarks disagree with each other, so I tested on our own tasks
- (small) the "what do you use AI for" poll chart

Say: last time I showed this on my PC, today the follow-up on the lab's GPUs.

## Slide 3: round 1, a 16 GB PC vs Claude

Keep old slide 14 (ADS tasks table) as is. Add one line above it:

> 25 standard exercises: best local model 60 %, Claude Sonnet 5 96 %.

## Slide 4: round 1 takeaways

- Small models mostly failed on **tooling**, not code: malformed edits, empty files, truncated answers (Aider parses edits out of plain text)
- The 35B was usable but made **silent regressions** on the refactor
- Good for: explaining code, finding a bug, sensitive data. Not for: features, multi-file refactors
- Bottleneck: 16 GB of VRAM. The 35B spilled into system RAM, context capped

Transition: "but we have GPU clusters".

## Slide 5: the lab's GPUs

| Station | GPUs | For a coding model |
|---|---|---|
| bireli | 2 x GTX TITAN X (2014) | no |
| rosenberg | 8 x P100 16 GB (2016) | possible, half the machine, slow |
| romane | 4 x RTX A6000 48 GB (2020) | good fallback |
| **tassan** | **2 x RTX PRO 6000 96 GB (2025)** | **one card holds an 80B model** |

Measured on tassan (Ollama, Qwen3-Coder-Next 80B, Q4):

| | 35B on my PC | 80B on tassan |
|---|---|---|
| Placement | 59 % GPU, rest in RAM | 100 % on one card |
| Speed | 68 to 89 tok/s | 54 tok/s |
| Context | 32k, fought for it | 64k, room left |
| Other card | n/a | untouched |

## Slide 6: the setup

Image: `slides/cluster_setup.png`

- vLLM serves the model on card 0, card 1 stays free for training
- Each person: SSH tunnel with their own tassan login, then OpenCode (open source) or Claude Code pointed at tassan
- No root, nothing exposed on the network, everything in one folder, `rm -rf` to remove

## Slide 7: it works (demo)

Screenshot or 30 s screen recording: OpenCode (or Claude Code) on a laptop, through the tunnel, editing a scratch repo and the test passing. `smoke-test.ps1` does exactly this.

Caption: `<agent>` + Qwen3-Coder-Next 80B on tassan, `<N>` tool calls, `<time>` s, test passes.

Fallback if no screenshot: the `check-tassan.ps1` / `smoke-test.ps1` output ("Tool call OK", "median PASS").

## Slide 8: sharing one GPU

Title: **Several people at once: the server matters, not the agent**

Image: `slides/concurrency.png` (real data only, the current one is from a fake run and was deleted)

One line under it, filled from the printed table:
> At 8 simultaneous users: vLLM `<x>` s before the first word, Ollama (default) `<y>` s. vLLM does `<k>`x more total work on the same card.

Say: Ollama answers people one by one by default; vLLM batches everyone together.

## Slide 9: round 3, same 5 ADS tasks on tassan

| Task | 35B, PC, Aider | 80B, tassan, OpenCode | 80B, tassan, Claude Code | Sonnet 5 |
|---|---|---|---|---|
| Add a CLI feature | passed | `<>` | `<>` | passed |
| Write a test suite | 12 of 15 passed | `<>` | `<>` | passed |
| Explain a module | passed | `<>` | `<>` | passed |
| Find a real bug | passed | `<>` | `<>` | passed |
| Refactor across 5 files | 2 silent regressions | `<>` | `<>` | passed |
| Score, total time | 4/5, 22 min | `<>` | `<>` | 5/5, 11.8 min |

`make_cluster_figures.py` prints the raw run table (time, turns, files changed); success comes from reviewing the diffs by hand (`review.success`).

If round 3 isn't done: drop this slide and say it's the next step, slide 7 already shows it works.

## Slide 10: takeaways

1. Hardware is solved: one tassan card runs an 80B coding model fully in VRAM, the other card stays free
2. With vLLM, several people can share it: `<one number from slide 8>`
3. Real agents (OpenCode, Claude Code) instead of Aider: `<one line from slide 9>`
4. Privacy: code and data never leave Poly's network, no per-seat cost
5. Same rule as before: read the diff, work on a branch

## Slide 11: what we need to decide as a lab

- Who owns the server, and does it run permanently on card 0 or on demand?
- Which model: the 80B coder, or a smaller 35B that leaves most of the card free?
- One shared key, or per-user keys and usage logs (later)?
- Want to try it? Ask me for the client folder, it's a 1-page guide

## Backup: how to use it

From `lab_server/USER_GUIDE.md`: VPN, `tassan-tunnel.ps1`, `check-tassan.ps1`, then `opencode-tassan.ps1` or `claude-tassan.ps1` in your repo.

---

## What to ask the session running tassan to bring back

- `results/conc_vllm.json`, `conc_ollama_p1.json`, `conc_ollama_p4.json` (`deploy-tassan.ps1 -Fetch`)
- `results/custom_*_opencode-tassan-vllm.json` and `custom_*_claude-tassan-vllm.json`, with `review.success` filled
- A screenshot of an agent session on tassan (slide 7), and the `status.sh` output with `nvidia-smi` memory
- vLLM start-up time and which checkpoint actually loaded (NVFP4 or the FP8 fallback), since slide 5/6 say 80B
