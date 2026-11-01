"""Figures for the write-up (Phase 7). Reads results/*.csv; writes results/figures/*.png.

Run experiments.run_all and experiments.sensitivity first.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from lbsim.config import EXPERIMENT, SCORING, SENSITIVITY, WORKLOAD
from lbsim.policies import ProbabilisticPolicy, WeightedMetricPolicy
from lbsim.sensitivity import ABLATION, AXIS_COLUMN, GRID, TARGET
from lbsim.simulator import simulate
from lbsim.workload import generate_workload

RESULTS_DIR = Path("results")

# Reference palette from the dataviz skill (light mode): fixed slot order, never cycled.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID_LINE, BASELINE, SURFACE, NEUTRAL = "#e1e0d9", "#c3c2b7", "#fcfcfb", "#f0efec"
DIVERGING = LinearSegmentedColormap.from_list("blue_gray_red", ["#1c5cab", "#86b6ef", NEUTRAL, "#f19a99", "#b42f2f"])
WORKLOAD_COLOR = dict(zip(EXPERIMENT.workloads, SERIES))
AXIS_TITLE = {
    "theta": "θ_C on load signal (%)  [θ_M = θ_C + 5]",
    "admission": "Admission threshold on P_risk",
    "risk_weight": "Risk weight w_R in S = (1−w_R)·L + w_R·P_risk",
    "window": "Window W (samples)",
}
DEFAULT_VALUE = {
    "theta": SCORING.theta_cpu, "admission": SCORING.risk_admission_threshold,
    "risk_weight": SCORING.score_weights[1], "window": SCORING.window,
}
SHORT = {"weighted_metric": "weighted\nmetric", "least_cpu": "least\nCPU", "round_robin": "round\nrobin",
         "probabilistic": "probabil-\nistic"}


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 9,
        "text.color": INK, "axes.labelcolor": INK_2, "axes.titlecolor": INK, "axes.titlesize": 10,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
        "axes.edgecolor": BASELINE, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID_LINE, "grid.linewidth": 0.6,
        "axes.axisbelow": True, "lines.linewidth": 1.5, "lines.markersize": 6,
        "legend.frameon": False, "legend.labelcolor": INK_2,
    })


def zero_line(ax: plt.Axes) -> None:
    ax.axhline(0, color=BASELINE, linewidth=1, zorder=1)


def save(fig: plt.Figure, out: Path, name: str) -> None:
    fig.savefig(out / name, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


def policy_comparison(summary: pd.DataFrame, out: Path) -> None:
    """Mean response (log) and SLA violation rate per policy and workload, error bars = std over seeds."""
    policies = list(dict.fromkeys(summary["policy"]))
    x = np.arange(len(policies))
    width = 0.38
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    panels = [("mean_response_s", "Mean response time (s, log scale)", 1.0),
              ("sla_violation_rate", f"SLA violation rate (%), R_SLA = {EXPERIMENT.r_sla:g} s", 100.0)]
    for ax, (metric, title, scale) in zip(axes, panels):
        for j, kind in enumerate(EXPERIMENT.workloads):
            s = summary[summary["workload"] == kind].set_index("policy").loc[policies]
            ax.bar(x + (j - 0.5) * width * 1.05, s[f"{metric}_mean"] * scale, width,
                   yerr=s[f"{metric}_std"] * scale, color=WORKLOAD_COLOR[kind], label=kind,
                   error_kw={"ecolor": INK_2, "elinewidth": 0.8, "capsize": 2})
        ax.set_title(title, loc="left")
        ax.set_xticks(x, [SHORT.get(p, p.replace("_", "\n")) for p in policies])
        if metric == "mean_response_s":
            ax.set_yscale("log")
    axes[1].legend(loc="upper right", bbox_to_anchor=(1.0, 1.16), ncols=2)
    fig.suptitle(f"All policies, mean ± std over {summary['n_seeds'].iloc[0]} seeds", x=0.01, ha="left",
                 fontsize=11, color=INK)
    fig.tight_layout()
    save(fig, out, "fig1_policy_comparison.png")


def paired_seeds(runs: pd.DataFrame, out: Path) -> None:
    """Per-seed paired difference probabilistic - weighted_metric for the headline metrics."""
    metrics = [("mean_response_s", "Δ mean response (s)", 1.0),
               ("sla_violation_rate", "Δ SLA violation rate (pp)", 100.0),
               ("overload_frac_util", "Δ overload frequency, utilisation (pp)", 100.0)]
    a = runs[runs["policy"] == TARGET].set_index(["workload", "seed"])
    b = runs[runs["policy"] == ABLATION].set_index(["workload", "seed"])
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
    for ax, (metric, title, scale) in zip(axes, metrics):
        zero_line(ax)
        for j, kind in enumerate(EXPERIMENT.workloads):
            d = (a.loc[kind, metric] - b.loc[kind, metric]) * scale
            ax.scatter(np.full(len(d), j) + np.linspace(-0.12, 0.12, len(d)), d, s=36,
                       color=WORKLOAD_COLOR[kind], edgecolor=SURFACE, linewidth=1.5, zorder=3)
            ax.hlines(d.mean(), j - 0.25, j + 0.25, color=INK, linewidth=1.5, zorder=4)
        ax.set_xticks(range(len(EXPERIMENT.workloads)), EXPERIMENT.workloads)
        ax.set_xlim(-0.6, len(EXPERIMENT.workloads) - 0.4)
        ax.set_title(title, loc="left")
    fig.suptitle("Probabilistic − weighted_metric per seed (dots), mean (bar). Below 0 = probabilistic better",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    save(fig, out, "fig2_paired_by_seed.png")


def calibration(runs: pd.DataFrame, out: Path) -> None:
    """Mean chosen P_risk vs observed load-signal overload frequency (per workload x seed)."""
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.grid(True, axis="both")
    ax.plot([0, 1], [0, 1], color=BASELINE, linewidth=1, linestyle="--", zorder=1)
    ax.text(0.97, 0.9, "perfect calibration", color=MUTED, ha="right", rotation=0, fontsize=8)
    t = runs[runs["policy"] == TARGET]
    for kind in EXPERIMENT.workloads:
        k = t[t["workload"] == kind]
        ax.scatter(k["overload_frac_load"], k["mean_p_risk"], s=40, color=WORKLOAD_COLOR[kind],
                   edgecolor=SURFACE, linewidth=1.5, label=f"{kind} (5 seeds)", zorder=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Observed fraction of server-intervals with load > θ")
    ax.set_ylabel("Mean P_risk of the chosen server")
    ax.set_title("Risk estimate vs observed overload (θ = 80/85)", loc="left")
    ax.legend(loc="upper left")
    fig.tight_layout()
    save(fig, out, "fig3_calibration.png")


def timeseries(out: Path) -> None:
    """Load signal per server over the arrival horizon for the ablation and the proposed policy."""
    kind, seed = SENSITIVITY.timeseries_workload, SENSITIVITY.timeseries_seed
    wl = generate_workload(kind, seed)
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True, sharey=True)
    for ax, cls in zip(axes, (WeightedMetricPolicy, ProbabilisticPolicy)):
        ticks = simulate(wl.tasks, cls()).server_ticks
        ticks = ticks[ticks["tick"] < WORKLOAD.t_sim]
        for b0, b1 in wl.bursts:
            ax.axvspan(b0, b1, color=NEUTRAL, zorder=0)
        ax.axhline(SCORING.theta_cpu, color=INK_2, linewidth=1, linestyle="--", zorder=2)
        ax.text(WORKLOAD.t_sim, SCORING.theta_cpu, f" θ_C = {SCORING.theta_cpu:g}%", color=INK_2,
                va="center", fontsize=8)
        for sid, g in ticks.groupby("server_id"):
            smooth = g["cpu_load_pct"].rolling(SCORING.window, min_periods=1).mean()
            ax.plot(g["tick"], smooth, color=SERIES[sid], linewidth=1.2, label=f"server {sid}", zorder=3)
        ax.set_title(f"{cls.name}", loc="left")
        ax.set_ylabel(f"CPU load % ({SCORING.window}-tick mean, log)")
        ax.set_yscale("log")
    axes[0].legend(loc="upper center", bbox_to_anchor=(0.5, 1.22), ncols=5)
    axes[1].set_xlabel("tick (s); shaded = burst windows")
    axes[1].set_xlim(0, WORKLOAD.t_sim)
    fig.suptitle(f"{kind} seed {seed}: load-aware balancing drives every server to the same level",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    save(fig, out, "fig4_load_timeseries.png")


def sensitivity_lines(table: pd.DataFrame, out: Path) -> None:
    """One column per axis: paired Δ response, Δ SLA, and the capacity-pressure rate."""
    rows = [("mean_response_s", "Δ mean response (s)", 1.0, "mean_diff"),
            ("sla_violation_rate", "Δ SLA violations (pp)", 100.0, "mean_diff"),
            ("sla_violation_rate", "Capacity-pressure rate (%)", 100.0, "target_capacity_pressure_rate")]
    fig, axes = plt.subplots(len(rows), len(AXIS_COLUMN), figsize=(13, 8), sharey="row")
    for c, (axis, col) in enumerate(AXIS_COLUMN.items()):
        t = table[table["axis"] == axis]
        for r, (metric, ylabel, scale, field) in enumerate(rows):
            ax = axes[r, c]
            if field == "mean_diff":
                zero_line(ax)
            ax.axvline(DEFAULT_VALUE[axis], color=BASELINE, linewidth=1, linestyle=":", zorder=1)
            for kind in EXPERIMENT.workloads:
                k = t[(t["workload"] == kind) & (t["metric"] == metric)].sort_values(col)
                y = k[field] * scale
                ax.plot(k[col], y, color=WORKLOAD_COLOR[kind], marker="o", label=kind, zorder=3)
                if field == "mean_diff":
                    ax.fill_between(k[col], y - k["std_diff"] * scale, y + k["std_diff"] * scale,
                                    color=WORKLOAD_COLOR[kind], alpha=0.12, linewidth=0, zorder=2)
            if c == 0:
                ax.set_ylabel(ylabel)
            if r == len(rows) - 1:
                ax.set_xlabel(AXIS_TITLE[axis], fontsize=8)
    axes[0, 0].legend(loc="upper left")
    fig.suptitle("Sensitivity, one axis at a time (dotted = frozen default). Δ = probabilistic − weighted_metric,"
                 " band = ±1 std over seeds; below 0 = probabilistic better", x=0.01, ha="left",
                 fontsize=11, color=INK)
    fig.tight_layout()
    save(fig, out, "fig5_sensitivity.png")


def sensitivity_grid(table: pd.DataFrame, out: Path) -> None:
    """θ x admission heatmap of Δ SLA violations with win counts, per workload."""
    g = table[(table["axis"] == GRID) & (table["metric"] == "sla_violation_rate")]
    fig, axes = plt.subplots(1, len(EXPERIMENT.workloads), figsize=(11, 3.8))
    lim = max(abs(g["mean_diff"]).max() * 100, 1e-9)
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim)
    for ax, kind in zip(axes, EXPERIMENT.workloads):
        k = g[g["workload"] == kind]
        diff = k.pivot(index="theta_cpu", columns="admission", values="mean_diff") * 100
        wins = k.pivot(index="theta_cpu", columns="admission", values="target_wins")
        n = int(k["n_seeds"].iloc[0])
        im = ax.imshow(diff.values, cmap=DIVERGING, norm=norm, aspect="auto", origin="lower")
        for i in range(diff.shape[0]):
            for j in range(diff.shape[1]):
                v = diff.values[i, j]
                ax.text(j, i, f"{v:+.1f}\n{int(wins.values[i, j])}/{n}", ha="center", va="center",
                        fontsize=7.5, color="#ffffff" if abs(v) > 0.6 * lim else INK)
        ax.set_xticks(range(diff.shape[1]), [f"{a:g}" for a in diff.columns])
        ax.set_yticks(range(diff.shape[0]), [f"{t:g}" for t in diff.index])
        ax.set_xlabel("Admission threshold")
        ax.set_ylabel("θ_C (%)")
        ax.set_title(f"{kind}", loc="left")
        ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
    cbar = fig.colorbar(im, ax=axes, shrink=0.9)
    cbar.set_label("Δ SLA violations (pp)", color=INK_2)
    cbar.outline.set_visible(False)
    fig.suptitle("Δ SLA violations, probabilistic − weighted_metric (cell: mean Δ pp, seeds won). Blue = better",
                 x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, out, "fig6_theta_admission_grid.png")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=RESULTS_DIR)
    args = parser.parse_args(argv)
    out = args.results / "figures"
    out.mkdir(parents=True, exist_ok=True)
    style()

    runs = pd.read_csv(args.results / "runs.csv")
    summary = pd.read_csv(args.results / "summary.csv")
    print(f"writing {out}/")
    policy_comparison(summary, out)
    paired_seeds(runs, out)
    timeseries(out)
    sens_path = args.results / "sensitivity.csv"
    sens = pd.read_csv(sens_path) if sens_path.exists() else None
    calibration(runs, out)
    if sens is None:
        print("  (no sensitivity.csv; run experiments.sensitivity for fig5/fig6)")
        return
    sensitivity_lines(sens, out)
    sensitivity_grid(sens, out)


if __name__ == "__main__":
    main()
