r"""Figures for the lab-meeting slides on the tassan server (16:9 PNGs in slides/).

  cluster_setup.png   always: laptop -> SSH tunnel -> vLLM on tassan card 0
  concurrency.png     if results/conc_*.json exist (deploy-tassan.ps1 -Fetch)
  round3 table        printed as markdown if results/custom_*-tassan-*.json exist

Usage: .venv\Scripts\python.exe make_cluster_figures.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

INK = "#1f2933"
MUTED = "#6b7785"
LOCAL = "#1f6feb"
CLUSTER = "#1a7f37"
NEUTRAL = "#3d4852"
PAPER = "#ffffff"

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
OUT = ROOT / "slides"
OUT.mkdir(exist_ok=True)


def setup_diagram():
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor(PAPER)

    def box(x, top, w, h, title, lines, edge, line_size=13):
        ax.add_patch(FancyBboxPatch((x, top - h), w, h, boxstyle="round,pad=0.7,rounding_size=1.4",
                                    linewidth=2.0, edgecolor=edge, facecolor=PAPER, zorder=2))
        ax.text(x + w / 2, top - 4.5, title, ha="center", va="center", fontsize=16,
                color=edge, fontweight="bold", zorder=3)
        y = top - 10.0
        for line in lines:
            ax.text(x + w / 2, y, line, ha="center", va="center", fontsize=line_size, color=INK, zorder=3)
            y -= 5.0

    def arrow(x1, y1, x2, y2, color, style="-"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=22,
                                     linewidth=2.4, color=color, linestyle=style, zorder=4))

    ax.text(50, 96, "One lab server, everyone's own agent", fontsize=24, color=INK,
            fontweight="bold", ha="center", va="center")

    # laptops
    ax.text(4, 85, "EACH LAB MEMBER  (Poly VPN)", fontsize=11, color=MUTED, fontweight="bold")
    for i, top in enumerate((81, 57, 33)):
        box(4, top, 34, 18 if i < 2 else 14, "Laptop" if i < 2 else "...",
            ["OpenCode  or  Claude Code", "edits your files, runs your tests"] if i < 2 else ["more users"],
            LOCAL, line_size=12.5)

    # tassan
    ax.text(58, 85, "TASSAN  (2 x RTX PRO 6000, 96 GB each)", fontsize=11, color=MUTED, fontweight="bold")
    box(58, 81, 38, 34, "Card 0: vLLM", [
        "Qwen3-Coder-Next 80B",
        "OpenAI + Anthropic APIs",
        "continuous batching:",
        "many users share one card",
    ], CLUSTER)
    box(58, 41, 38, 14, "Card 1: free", ["training jobs as usual"], NEUTRAL)

    for y in (70, 46, 24):
        arrow(39.5, y, 57, 62, CLUSTER)
    ax.text(48, 74, "SSH tunnel\n(your own\ntassan login)", ha="center", va="center", fontsize=12, color=CLUSTER)

    ax.text(50, 8, "Server listens on localhost only  |  code and prompts never leave Poly's network  |  "
            "no root, no per-seat cost", ha="center", va="center", fontsize=13, color=MUTED)

    path = OUT / "cluster_setup.png"
    fig.savefig(path, facecolor=PAPER, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"wrote {path}")


SERIES = {  # file stem -> (legend, color, linestyle)
    "conc_vllm": ("vLLM", CLUSTER, "-"),
    "conc_ollama_p4": ("Ollama, 4 slots", LOCAL, "--"),
    "conc_ollama_p1": ("Ollama, 1 slot (default)", "#cf222e", ":"),
}


def concurrency_chart():
    found = {stem: json.loads((RESULTS / f"{stem}.json").read_text())
             for stem in SERIES if (RESULTS / f"{stem}.json").exists()}
    if not found:
        print("no results/conc_*.json yet, skipping concurrency.png")
        return
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(16, 7), dpi=200)
    fig.patch.set_facecolor(PAPER)
    for stem, data in found.items():
        label, color, ls = SERIES[stem]
        lv = data["levels"]
        users = [r["users"] for r in lv]
        a1.plot(users, [r["ttft_p95_s"] for r in lv], ls, color=color, lw=2.6, marker="o", label=label)
        a2.plot(users, [r["aggregate_out_tok_s"] for r in lv], ls, color=color, lw=2.6, marker="o", label=label)
        for r in lv:
            if r["errors"]:
                a1.annotate(f"{r['errors']} rejected", (r["users"], r["ttft_p95_s"]), textcoords="offset points",
                            xytext=(0, 10), ha="center", fontsize=10, color=color)
    for a, title, ylab in ((a1, "Wait before the first word (p95)", "seconds"),
                           (a2, "Work done by the card", "tokens / s, all users")):
        a.set_title(title, fontsize=16, color=INK, loc="left", fontweight="bold")
        a.set_xlabel("simultaneous users", fontsize=13, color=MUTED)
        a.set_ylabel(ylab, fontsize=13, color=MUTED)
        a.set_xscale("log", base=2)
        a.set_xticks([1, 2, 4, 8, 16], labels=["1", "2", "4", "8", "16"])
        a.grid(alpha=0.25)
        a.spines[["top", "right"]].set_visible(False)
        a.set_ylim(bottom=0)
    a1.legend(frameon=False, fontsize=12)
    fig.tight_layout()
    path = OUT / "concurrency.png"
    fig.savefig(path, facecolor=PAPER, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"wrote {path}")

    print("\n| server | users | TTFT p95 (s) | total tok/s | errors | VRAM peak (GiB) |\n|---|---|---|---|---|---|")
    for stem, data in found.items():
        for r in data["levels"]:
            if r["users"] in (1, 4, 8):
                vram = f"{r['gpu_mem_peak_mib'] / 1024:.0f}" if r.get("gpu_mem_peak_mib") else "-"
                print(f"| {SERIES[stem][0]} | {r['users']} | {r['ttft_p95_s']:.2f} | "
                      f"{r['aggregate_out_tok_s']:.0f} | {r['errors']} | {vram} |")


def round3_table():
    rows = sorted(RESULTS.glob("custom_*-tassan-*.json"))
    if not rows:
        print("no round-3 results yet (results/custom_*-tassan-*.json)")
        return
    print("\n| task | harness | success | time | turns | files changed |\n|---|---|---|---|---|---|")
    for p in rows:
        d = json.loads(p.read_text(encoding="utf-8"))
        harness = p.stem.rsplit("_", 1)[-1].split("-tassan")[0]
        ok = {True: "yes", False: "no", None: "not reviewed"}.get(d["review"].get("success"), d["review"].get("success"))
        print(f"| {d['task']} | {harness} | {ok} | {d['elapsed_seconds']:.0f}s | {d.get('num_turns')} | "
              f"{len(d.get('files_changed') or [])} |")


if __name__ == "__main__":
    setup_diagram()
    concurrency_chart()
    round3_table()
