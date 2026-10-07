r"""Render the slide diagram of the benchmark stack to stack.png (16:9).

Usage: .venv\Scripts\python.exe make_stack_diagram.py
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

INK = "#1f2933"
MUTED = "#6b7785"
LOCAL = "#1f6feb"
CLOUD = "#8250df"
NEUTRAL = "#3d4852"
PAPER = "#ffffff"

fig, ax = plt.subplots(figsize=(16, 9), dpi=220)
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")
fig.patch.set_facecolor(PAPER)

LX, RX, CW = 4.0, 52.0, 44.0


def box(x, top, w, h, title, lines, edge, title_size=15, line_size=12.5, fill=PAPER):
    ax.add_patch(
        FancyBboxPatch((x, top - h), w, h, boxstyle="round,pad=0.7,rounding_size=1.4",
                       linewidth=2.0, edgecolor=edge, facecolor=fill, zorder=2)
    )
    ax.text(x + w / 2, top - 4.2, title, ha="center", va="center", fontsize=title_size,
            color=edge if edge != NEUTRAL else INK, fontweight="bold", zorder=3)
    y = top - 9.0
    for line in lines:
        ax.text(x + w / 2, y, line, ha="center", va="center", fontsize=line_size,
                color=INK, zorder=3)
        y -= 4.6


def arrow(x1, y1, x2, y2, color, style="-"):
    ax.add_patch(
        FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=20,
                        linewidth=2.2, color=color, linestyle=style, zorder=4,
                        shrinkA=1, shrinkB=1)
    )


# --------------------------------------------------------------- title
ax.text(50, 96, "Same tasks, same protocol, four models", fontsize=23, color=INK,
        fontweight="bold", ha="center", va="center")

# --------------------------------------------------------------- workloads
box(22, 91, 56, 14, "The workload", [
    "25 Exercism coding exercises  (standard benchmark)",
    "5 real AxonDeepSeg tasks  (feature, test, explain, bug, refactor)",
], NEUTRAL)

# --------------------------------------------------------------- agents
ax.text(LX, 74.3, "AGENTIC HARNESS", ha="left", va="center", fontsize=11,
        color=MUTED, fontweight="bold")
box(LX, 72, CW, 16, "Aider", [
    "agentic harness for the local models",
    "fixed loop: prompt, apply edits, retry on failure",
], LOCAL)
box(RX, 72, CW, 16, "Claude Code", [
    "agentic harness on the Anthropic backend",
    "explores the repo, edits, runs the tests itself",
], CLOUD)

# --------------------------------------------------------------- models
box(LX, 51, CW, 20, "Ollama  (local inference server)", [
    "Qwen coder models: 7B, 14B, 35B mixture-of-experts",
    "quantized, 5 to 13 GB of VRAM",
    "the 35B also spills ~9 GB into system RAM",
], LOCAL)
box(RX, 51, CW, 20, "Anthropic API", [
    "Claude Sonnet 5",
    "runs on Anthropic's servers",
    "billed against the subscription quota",
], CLOUD)

# --------------------------------------------------------------- hardware
box(LX, 27, CW, 15, "One desktop GPU", [
    "RTX 5060 Ti 16 GB  +  32 GB RAM",
    "busy for the whole run, hours per model",
], NEUTRAL, title_size=14, line_size=12)
box(RX, 27, CW, 15, "No local resources", [
    "no GPU, no VRAM, machine stays free",
    "minutes per model",
], NEUTRAL, title_size=14, line_size=12)

# --------------------------------------------------------------- results
box(22, 10.5, 56, 10.0, "Same measurements for every model", [
    "success rate  |  time  |  diffs reviewed by hand  |  cost",
], NEUTRAL, title_size=14, line_size=12.5)

# --------------------------------------------------------------- arrows
lc, rc = LX + CW / 2, RX + CW / 2
arrow(36, 77, lc + 3, 72.4, LOCAL)
arrow(64, 77, rc - 3, 72.4, CLOUD)
arrow(lc, 56, lc, 51.4, LOCAL)
arrow(rc, 56, rc, 51.4, CLOUD)
arrow(lc, 31, lc, 27.4, NEUTRAL)
arrow(rc, 31, rc, 27.4, NEUTRAL)

# optional path: Claude Code on a local model
arrow(RX, 63, LX + CW, 46, CLOUD, style=(0, (4, 2.5)))
ax.text(2.5, 6.0,
        "dashed: Claude Code can also\ndrive the local models\n(Ollama speaks the same API)",
        ha="left", va="center", fontsize=10.5, color=CLOUD)

fig.savefig("stack.png", facecolor=PAPER, bbox_inches="tight", pad_inches=0.3)
print("wrote stack.png")
