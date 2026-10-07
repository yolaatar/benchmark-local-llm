# Using the lab coding assistant (tassan)

A coding model (Qwen3-Coder-Next, 80B) runs on one GPU of tassan. You use it from your laptop with an AI coding agent, OpenCode or Claude Code, which reads and edits your files and runs your commands. Prompts and code stay inside Polytechnique's network. It's free to use, but it shares one GPU with the rest of the lab.

## You need

- The Polytechnique VPN, and a login on tassan (the same one you use for training jobs).
- The `client` folder (ask Youssef), and the lab API key (ask Youssef, don't post it anywhere).
- One of the two agents:
  - **OpenCode** (open source): install Node.js, then `npm install -g opencode-ai`.
  - **Claude Code**: see https://claude.com/claude-code. No Anthropic account needed for this use.

## Every time

1. Connect the VPN.
2. Open a PowerShell window in the `client` folder and leave it open:
   ```powershell
   .\tassan-tunnel.ps1 -User "<your tassan login>"
   ```
3. In a second window, set the key (once per window) and check that everything answers:
   ```powershell
   $env:TASSAN_VLLM_KEY = "<lab key>"
   .\check-tassan.ps1
   ```
4. Go to your project folder and start an agent:
   ```powershell
   cd C:\path\to\your\repo
   & "<path to client>\opencode-tassan.ps1"
   # or
   & "<path to client>\claude-tassan.ps1"
   ```
   The Claude Code launcher only redirects that one session. Typing plain `claude` elsewhere still uses your normal account.

## Good to know

- **It's shared.** When several people use it at once, everyone gets slower answers. A long wait before the first word usually means others are using it, not that it's broken.
- **Check what it writes.** Our tests showed local models can sound confident while being wrong, and can make changes that pass the existing tests but quietly change behaviour. Work in a git branch and read the diff before committing.
- **Use a clone, not your only copy**, for big refactors.
- **Problems:** first run `.\check-tassan.ps1`. "No answer" means the tunnel is closed or the server is stopped. If it's the server, tell Youssef.
