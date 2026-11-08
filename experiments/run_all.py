"""Run every policy x workload x seed, evaluate, and write results/ (Phase 6).

results/runs.csv     one row per (workload, seed, policy) with every spec section 6 metric
results/summary.csv  mean and std across seeds per (workload, policy)
results/paired.csv   probabilistic minus weighted_metric (the key ablation), paired by seed
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from lbsim.config import EXPERIMENT, SERVERS, WORKLOAD
from lbsim.evaluation import evaluate, paired_differences, summarise_runs
from lbsim.policies import all_policies
from lbsim.simulator import simulate
from lbsim.workload import Workload, generate_workload

RESULTS_DIR = Path("results")
TARGET, ABLATION = "probabilistic", "weighted_metric"
CAPACITY = sum(s.cores * s.speed for s in SERVERS)
SHOWN = [
    "mean_response_s", "p95_response_s", "throughput", "sla_violation_rate",
    "avg_cpu_util", "load_imbalance", "overload_frac_util", "overload_frac_load",
    "mean_p_risk", "capacity_pressure_rate",
]


def offered_load(wl: Workload) -> float:
    """Core-seconds of speed-1 work generated, as a fraction of cluster capacity over the arrival horizon."""
    return sum(t.cpu_demand * t.work for t in wl.tasks) / (WORKLOAD.t_sim * CAPACITY)


def run_matrix(workloads: Sequence[str], seeds: Sequence[int]) -> pd.DataFrame:
    """One task list per (workload, seed), shared unchanged by every policy; servers rebuilt per run."""
    rows = []
    for kind in workloads:
        for seed in seeds:
            wl = generate_workload(kind, seed)
            print(f"{kind:>6} seed {seed}: {len(wl.tasks)} tasks, offered load {offered_load(wl):.3f}")
            for policy in all_policies(seed):
                rows.append({"workload": kind, "seed": seed, **evaluate(simulate(wl.tasks, policy))})
    return pd.DataFrame(rows)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(EXPERIMENT.seeds))
    parser.add_argument("--out", type=Path, default=RESULTS_DIR)
    parser.add_argument("--limit", type=int, default=None, help="cap tasks per matched trace")
    args = parser.parse_args(argv)

    if args.limit is None:
        runs = run_matrix(EXPERIMENT.workloads, args.seeds)
    else:
        rows = []
        for kind in EXPERIMENT.workloads:
            for seed in args.seeds:
                wl = generate_workload(kind, seed)
                tasks = wl.tasks[:args.limit]
                print(f"{kind:>6} seed {seed}: {len(tasks)} tasks")
                for policy in all_policies(seed):
                    rows.append({"workload": kind, "seed": seed, **evaluate(simulate(tasks, policy))})
        runs = pd.DataFrame(rows)
    summary = summarise_runs(runs)
    paired = paired_differences(runs, TARGET, ABLATION)

    args.out.mkdir(parents=True, exist_ok=True)
    runs.to_csv(args.out / "runs.csv", index=False)
    summary.to_csv(args.out / "summary.csv", index=False)
    paired.to_csv(args.out / "paired.csv", index=False)

    with pd.option_context("display.width", 200, "display.max_columns", 20):
        for kind in EXPERIMENT.workloads:
            s = summary[summary["workload"] == kind].set_index("policy")
            print(f"\n== {kind} | mean over {len(args.seeds)} seeds ==")
            print(s[[f"{m}_mean" for m in SHOWN]].rename(columns=lambda c: c[:-5]).round(3).to_string())
            print(f"all drained: {bool(s['all_drained'].all())}")
        print(f"\n== {TARGET} - {ABLATION} (paired by seed) ==")
        print(paired.round(4).to_string(index=False))
    print(f"\nwrote {args.out}/runs.csv, summary.csv, paired.csv")


if __name__ == "__main__":
    main()
