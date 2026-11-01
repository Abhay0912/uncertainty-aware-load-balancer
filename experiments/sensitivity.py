"""Sensitivity sweep of the probabilistic policy vs its ablation over every workload and seed (Phase 7).

results/sensitivity_runs.csv    one row per (sweep point, workload, seed, policy)
results/sensitivity.csv         paired probabilistic - weighted_metric per sweep point, workload, metric
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Sequence

import pandas as pd

from lbsim.config import EXPERIMENT
from lbsim.sensitivity import AXIS_COLUMN, GRID, run_sweep, sensitivity_table, sweep_points
from lbsim.workload import generate_workload

RESULTS_DIR = Path("results")
HEADLINE = ["mean_response_s", "sla_violation_rate", "overload_frac_util"]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(EXPERIMENT.seeds))
    parser.add_argument("--out", type=Path, default=RESULTS_DIR)
    args = parser.parse_args(argv)

    points = sweep_points()
    streams = [(k, s, generate_workload(k, s).tasks) for k in EXPERIMENT.workloads for s in args.seeds]
    print(f"{len(points)} sweep points x {len(streams)} streams")
    start = time.perf_counter()
    runs = run_sweep(points, streams)
    table = sensitivity_table(runs)
    print(f"swept in {time.perf_counter() - start:.0f} s")

    args.out.mkdir(parents=True, exist_ok=True)
    runs.to_csv(args.out / "sensitivity_runs.csv", index=False)
    table.to_csv(args.out / "sensitivity.csv", index=False)

    shown = table[table["metric"].isin(HEADLINE) & (table["axis"] != GRID)]
    with pd.option_context("display.width", 200, "display.max_rows", 500):
        for axis, col in AXIS_COLUMN.items():
            t = shown[shown["axis"] == axis]
            wide = t.pivot_table(index=["workload", col], columns="metric",
                                 values=["mean_diff", "target_wins"], sort=False)
            wide[("pressure", "")] = t.groupby(["workload", col], sort=False)["target_capacity_pressure_rate"].first()
            print(f"\n== {axis}: probabilistic - weighted_metric (mean diff, wins of {len(args.seeds)}) ==")
            print(wide.round(4).to_string())
    print(f"\nwrote {args.out}/sensitivity_runs.csv, sensitivity.csv")


if __name__ == "__main__":
    main()
