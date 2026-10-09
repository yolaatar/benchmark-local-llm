# Using the lab coding assistant (tassan)

A coding model runs on GPU 1 of tassan, and you use it from your laptop with an AI coding agent (Claude Code or OpenCode) that reads and edits your files and runs your commands. Prompts and code stay inside Polytechnique's network, and it costs nothing per use. The GPU is shared with the rest of the lab.

**The model:** Qwen3.6-27B, a "thinking" model (it reasons before answering). On our 5 test tasks on the AxonDeepSeg codebase (add a feature, fix a bug, refactor across 5 files, write a test module, explain a pipeline), it did as well as Claude Sonnet: all tests passing, no regressions. It is slower than a cloud model: expect **2 to 12 minutes for a real task**, and it writes about 45 tokens per second (a token is a word or a piece of one).

## One-time setup

1. **Access:** the Polytechnique VPN and a login on tassan (the same one you use for training jobs).
2. **The `client` folder and the lab key:** ask Youssef. Keep the key private, don't commit or post it.
3. **Save the key once**, so you never have to type it again:
   - macOS / Linux: `(umask 077; printf '%s' '<lab key>' > ~/.tassan_vllm_key)`
   - Windows (PowerShell): `Set-Content -NoNewline "$HOME\.tassan_vllm_key" '<lab key>'`
4. **Install an agent** (one is enough, both work):
   - **Claude Code**: see https://claude.com/claude-code. No Anthropic account or subscription is used with the lab launcher.
   - **OpenCode** (open source): `brew install opencode` on macOS, or install Node.js then `npm install -g opencode-ai`.
5. **Optional, saves typing your password:** an SSH key for tassan (`ssh-keygen -t ed25519`, then add the `.pub` file to `~/.ssh/authorized_keys` on tassan).
6. **Windows only:** if PowerShell refuses to run the scripts, run once `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Every time

1. **Connect the VPN.**
2. **Open the tunnel** in a terminal and leave it open while you work:
   - macOS / Linux: `TASSAN_USER=<your tassan login> /path/to/client/tassan-tunnel.sh`
   - Windows: `.\tassan-tunnel.ps1 -User "<your tassan login>"` (from the `client` folder)
3. **Check** that it answers, in a second terminal (optional, but it saves guessing when something is off):
   - macOS / Linux: `/path/to/client/check-tassan.sh`
   - Windows: `.\check-tassan.ps1`

   You should see the model name, then `Tool call OK in N s`.
4. **Go to your project and start an agent:**
   ```bash
   cd /path/to/your/repo
   /path/to/client/claude-tassan.sh        # or opencode-tassan.sh
   ```
   On Windows: `& "<path to client>\claude-tassan.ps1"` (or `opencode-tassan.ps1`).

The launchers only change settings for that one session. Typing plain `claude` or `opencode` elsewhere still uses your usual setup.

## Which agent?

Both did well on our tests with this model. In short:

- **Claude Code** keeps your repo clean and is a bit faster.
- **OpenCode** is fully open source and followed instructions a bit more literally. With weaker models it tended to leave scratch scripts behind, so check `git status` before committing.

Always start them with the lab launchers: the plain commands don't know the server's context limit, and long tasks then fail with a `400 ... maximum context length` error.

## Using the model from your own code (no agent)

The server speaks the OpenAI API, so any OpenAI-compatible client works. You only need the VPN, the key, and a tunnel (the `client` folder is optional here):

```bash
ssh -N -L 8001:127.0.0.1:8000 <your tassan login>@tassan.neuro.polymtl.ca   # leave it open
```

Then, from another terminal:

```bash
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Authorization: Bearer $(cat ~/.tassan_vllm_key)" -H "Content-Type: application/json" \
  -d '{"model": "qwen3.6-27b", "messages": [{"role": "user", "content": "Explain numpy broadcasting in 3 lines."}],
       "max_tokens": 2000}'
```

In Python (`pip install openai`):

```python
from pathlib import Path
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8001/v1",
                api_key=Path.home().joinpath(".tassan_vllm_key").read_text().strip())
model = client.models.list().data[0].id          # the model the server runs right now

r = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Write a function that checks if a string is a palindrome."}],
    max_tokens=4000,
)
print(r.choices[0].message.content)
```

- **Thinking:** by default the model reasons first (the reasoning comes back separately, in `message.reasoning`) and only then answers. For quick or simple requests, turn it off: much faster, fewer tokens.
  - Python: add `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`
  - curl: add `"chat_template_kwargs": {"enable_thinking": false}` to the JSON
- **`max_tokens`:** leave room for the reasoning (a few thousand) when thinking is on, or the answer can be cut off before it starts.
- **Streaming:** pass `stream=True` and print `chunk.choices[0].delta.content` as it arrives.
- **Batch jobs** (hundreds of requests): send them a few at a time (4 to 8 in parallel), not all at once, so others keep a usable server.

## Good practices

- **Work on a branch and read the diff** before committing. The model is good, not infallible: it can claim something works when it doesn't, or quietly change behavior.
- **Run `git status`** at the end: agents sometimes create helper files you don't want to commit.
- **Give it the whole task in one message**, with the files involved and how to check the result (for example "the tests in test/morphometrics must pass"). It works through it on its own.
- **Be patient on the first answer of a session:** it reads your files and thinks first. Several minutes on a real task is normal.
- **Use a clone, not your only copy,** for big refactors.

## Sharing the GPU

- Several people can use it at the same time. In our tests, with 8 simultaneous users, each one kept about 90% of their writing speed and the first word arrived within 2 seconds. With 3 agents working on real tasks at once, each task took about twice as long as alone (up to 5x for one of them), with the same quality of result.
- A longer wait than usual before the first word usually means others are using it, not that it's broken.
- The server runs on GPU 1 only. Don't start your own jobs on that card while the server is up; it reserves most of its memory.

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| `No answer on http://127.0.0.1:8001` | the tunnel is closed, the VPN is off, or the server is stopped | reopen the tunnel; if it still fails, tell Youssef |
| `No lab key` | the key file is missing | redo step 3 of the one-time setup |
| The tunnel says `Address already in use` | a tunnel is already open (maybe in another window) | use that one, or close it first |
| `400 ... maximum context length` | the agent was started without the lab launcher | quit and restart it with `claude-tassan` / `opencode-tassan` |
| The agent answers in text but never edits files | the model didn't make a tool call | run the check script; if it shows no tool call, tell Youssef |
| Very slow, even for short answers | many people are using it, or a long task is running | wait, or try again later |
