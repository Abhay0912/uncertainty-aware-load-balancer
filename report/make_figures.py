"""Figures for the final report (report/figures/).

Diagrams need nothing; result charts read results/v2/v2_runs.csv, produced by
    python -m experiments.run_v2 --seeds 0 1 2 3 4 --workloads stable bursty --limit 1000 --out results/v2

Usage: python report/make_figures.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report" / "figures"
RUNS = ROOT / "results" / "v2" / "v2_runs.csv"

INK, TEAL, FILL, MUTED = "#1B2A41", "#1A7F8E", "#EEF4F6", "#5B6575"
BLUE, ORANGE, GREY = "#2B78D6", "#E8643A", "#9AA5B4"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED})

ORDER = ["round_robin", "random", "wrr", "p2c", "least_cpu", "weighted_metric", "probabilistic",
         "ect_only", "uncertainty_ect"]
LABEL = {"round_robin": "Round Robin", "random": "Random", "wrr": "Weighted RR", "p2c": "P2C",
         "least_cpu": "Least CPU", "weighted_metric": "Weighted metric", "probabilistic": "Probabilistic (V1)",
         "ect_only": "ECT-only", "uncertainty_ect": "Uncertainty ECT"}


def box(ax, x, y, w, h, title, sub="", fill=FILL, edge=TEAL, tcolor=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fill, ec=edge, lw=1.4))
    ax.text(x + w / 2, y + h * (0.62 if sub else 0.5), title, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color=tcolor)
    if sub:
        ax.text(x + w / 2, y + h * 0.3, sub, ha="center", va="center", fontsize=8.5, color=MUTED)


def arrow(ax, x0, y0, x1, y1, color=MUTED, style="-|>"):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle=style, color=color, lw=1.3, shrinkA=0, shrinkB=0))


def architecture():
    fig, ax = plt.subplots(figsize=(10.4, 4.6))
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 4.6)
    ax.axis("off")
    w, h = 2.95, 0.9
    xs = [0.1, 3.55, 7.0]
    ys = [3.45, 1.95, 0.45]
    rows = [
        [("Seeded workload", "one trace per (workload, seed)"),
         ("Scheduler-visible view", "immutable; no hidden work"),
         ("Duration estimator", "hint → class → pooled → prior")],
        [("Select server", "argmin cost over feasible"),
         ("Completion-time cost", "ECT, or mean + β·tail"),
         ("Shadow-queue projection", "per server, FIFO + fit")],
        [("Simulator tick", "dispatch → sample → step"),
         ("Completion feedback", "observed work → history"),
         ("Evaluation", "latency, SLA, throughput")],
    ]
    for r, row in enumerate(rows):
        for c, (t, s) in enumerate(row):
            hi = (r, c) == (1, 1)
            box(ax, xs[c], ys[r], w, h, t, s, fill=INK if hi else FILL, edge=INK if hi else TEAL,
                tcolor="white" if hi else INK)
            if hi:
                ax.texts[-1].set_color("#C3CDDA")
    mid = lambda r: ys[r] + h / 2
    arrow(ax, xs[0] + w, mid(0), xs[1], mid(0))
    arrow(ax, xs[1] + w, mid(0), xs[2], mid(0))
    arrow(ax, xs[2] + w / 2, ys[0], xs[2] + w / 2, ys[1] + h)
    arrow(ax, xs[2], mid(1), xs[1] + w, mid(1))
    arrow(ax, xs[1], mid(1), xs[0] + w, mid(1))
    arrow(ax, xs[0] + w / 2, ys[1], xs[0] + w / 2, ys[2] + h)
    arrow(ax, xs[0] + w, mid(2), xs[1], mid(2))
    arrow(ax, xs[1] + w, mid(2), xs[2], mid(2))
    # feedback loop: completion feedback -> estimator (dashed, up the right side)
    ax.plot([xs[1] + w / 2, xs[1] + w / 2], [ys[2] + h, ys[2] + h + 0.22], color=ORANGE, lw=1.3, ls="--")
    ax.plot([xs[1] + w / 2, 10.25], [ys[2] + h + 0.22, ys[2] + h + 0.22], color=ORANGE, lw=1.3, ls="--")
    ax.plot([10.25, 10.25], [ys[2] + h + 0.22, mid(0)], color=ORANGE, lw=1.3, ls="--")
    arrow(ax, 10.25, mid(0), xs[2] + w, mid(0), color=ORANGE)
    ax.text(10.32, mid(1), "after completion only", rotation=90, ha="left", va="center",
            fontsize=8, color=ORANGE)
    fig.savefig(OUT / "fig_architecture.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def shadow_queue():
    """Illustrative two-server projection (not simulation output)."""
    fig, ax = plt.subplots(figsize=(9.2, 3.0))
    lanes = {"Server 3 (8 cores, speed 2.0)": 1.6, "Server 4 (2 cores, speed 0.5)": 0.4}
    bars = {
        "Server 3 (8 cores, speed 2.0)": [("running", 0, 2, GREY), ("queued", 2, 4, GREY),
                                          ("candidate", 4, 7, ORANGE)],
        "Server 4 (2 cores, speed 0.5)": [("candidate", 0, 12, ORANGE)],
    }
    for name, y in lanes.items():
        for label, s, e, col in bars[name]:
            ax.barh(y, e - s, left=s, height=0.55, color=col, edgecolor="white")
            ax.text((s + e) / 2, y, label, ha="center", va="center", fontsize=9,
                    color="white" if col == ORANGE else INK)
    ax.axvline(0, color=INK, lw=1)
    ax.text(0, 2.15, "arrival t", ha="center", fontsize=9, color=INK)
    for name, f in (("Server 3 (8 cores, speed 2.0)", 7), ("Server 4 (2 cores, speed 0.5)", 12)):
        y = lanes[name]
        ax.annotate(f"ECT = {f} s", xy=(f, y + 0.3), xytext=(f + 0.3, y + 0.45), fontsize=9.5,
                    fontweight="bold", color=INK)
    ax.set_yticks(list(lanes.values()), list(lanes.keys()))
    ax.set_xlim(-0.3, 15)
    ax.set_ylim(-0.1, 2.35)
    ax.set_xlabel("Projected time after arrival (s)")
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.savefig(OUT / "fig_shadow_queue.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def results():
    runs = pd.read_csv(RUNS)
    g = runs.groupby(["workload", "policy"])
    mean, std = g.mean(numeric_only=True), g.std(numeric_only=True)
    pols = [p for p in ORDER if p in runs.policy.unique()]
    colors = [ORANGE if p in ("ect_only", "uncertainty_ect") else (INK if p == "probabilistic" else GREY)
              for p in pols]
    labels = [LABEL[p] for p in pols]

    # Fig: mean and p95 response, log scale
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), sharey=True)
    y = np.arange(len(pols))
    for ax, wl in zip(axes, ("stable", "bursty")):
        m = [mean.loc[(wl, p), "mean_response_s"] for p in pols]
        p95 = [mean.loc[(wl, p), "p95_response_s"] for p in pols]
        ax.barh(y + 0.2, m, height=0.38, color=colors, label="mean")
        ax.barh(y - 0.2, p95, height=0.38, color=colors, alpha=0.45, label="p95")
        for yi, a, b in zip(y, m, p95):
            ax.text(a * 1.08, yi + 0.2, f"{a:.1f}", va="center", fontsize=7.5, color=INK)
            ax.text(b * 1.08, yi - 0.2, f"{b:.1f}", va="center", fontsize=7.5, color=MUTED)
        ax.set_xscale("log")
        ax.set_xlim(3, 8000)
        ax.set_title(f"{wl.capitalize()} workload", fontsize=11, color=INK, loc="left")
        ax.set_xlabel("Response time (s, log scale); solid = mean, light = p95")
        ax.axvline(18, color=MUTED, ls=":", lw=1)
        ax.text(19.5, -0.75, "SLA 18 s", fontsize=8, color=MUTED, ha="left", va="center")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_yticks(y, labels)
    axes[0].set_ylim(len(pols) - 0.45, -1.1)
    fig.tight_layout()
    fig.savefig(OUT / "fig_v2_response.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    # Fig: SLA violations and throughput (load-aware policies only, linear)
    aware = [p for p in pols if p not in ("round_robin", "random")]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    x = np.arange(len(aware))
    for ax, metric, scale, ylab in ((axes[0], "sla_violation_rate", 100, "SLA violations (%)"),
                                    (axes[1], "throughput", 1, "Throughput (tasks/s)")):
        for k, (wl, col) in enumerate((("stable", BLUE), ("bursty", ORANGE))):
            v = [mean.loc[(wl, p), metric] * scale for p in aware]
            e = [std.loc[(wl, p), metric] * scale for p in aware]
            ax.bar(x + (k - 0.5) * 0.38, v, 0.38, yerr=e, color=col, label=wl, capsize=2,
                   error_kw=dict(lw=0.8, ecolor=MUTED))
        short = {"wrr": "Weighted\nRR", "p2c": "P2C", "least_cpu": "Least\nCPU",
                 "weighted_metric": "Weighted\nmetric", "probabilistic": "Prob.\n(V1)",
                 "ect_only": "ECT-\nonly", "uncertainty_ect": "Uncert.\nECT"}
        ax.set_xticks(x, [short[p] for p in aware], fontsize=8.5)
        ax.set_ylim(bottom=0)
        ax.set_ylabel(ylab)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="upper center", ncol=2, frameon=False, fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT / "fig_v2_sla_throughput.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    # Fig: paired per-seed differences, uncertainty_ect - ect_only
    a = runs[runs.policy == "uncertainty_ect"].set_index(["workload", "seed"])
    b = runs[runs.policy == "ect_only"].set_index(["workload", "seed"])
    metrics = [("mean_response_s", "Mean response (s)", 1), ("p95_response_s", "p95 response (s)", 1),
               ("sla_violation_rate", "SLA violations (pp)", 100), ("throughput", "Throughput (tasks/s)", 1)]
    fig, axes = plt.subplots(1, 4, figsize=(10, 2.8))
    for ax, (col, title, sc) in zip(axes, metrics):
        for k, (wl, c) in enumerate((("stable", BLUE), ("bursty", ORANGE))):
            d = (a.loc[wl, col] - b.loc[wl, col]) * sc
            ax.scatter(np.full(len(d), k) + np.linspace(-0.12, 0.12, len(d)), d, color=c, s=22, zorder=3)
            ax.plot([k - 0.25, k + 0.25], [d.mean()] * 2, color=INK, lw=2)
        ax.axhline(0, color=MUTED, lw=1, ls="--")
        ax.set_xticks([0, 1], ["stable", "bursty"])
        ax.set_title(title, fontsize=9.5, color=INK)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_v2_ablation.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    architecture()
    shadow_queue()
    if RUNS.exists():
        results()
    else:
        print(f"{RUNS} missing: result figures skipped")
    print("figures ->", OUT)
