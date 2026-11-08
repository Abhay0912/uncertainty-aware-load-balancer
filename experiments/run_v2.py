"""Run the V1 matrix plus ECT ablations on original and heterogeneous workloads."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from lbsim.config import EXPERIMENT
from lbsim.evaluation import evaluate, paired_differences, summarise_runs
from lbsim.policies import v2_policies
from lbsim.simulator import simulate
from lbsim.workload import generate_workload


def run_matrix(
    workloads: Sequence[str], seeds: Sequence[int], limit: int | None = None
) -> pd.DataFrame:
    rows = []
    for kind in workloads:
        for seed in seeds:
            workload = generate_workload(kind, seed)  # one immutable trace per matched run
            tasks = workload.tasks if limit is None else workload.tasks[:limit]
            print(f"{kind:>14} seed {seed}: {len(tasks)} tasks")
            for policy in v2_policies(seed):
                result = simulate(tasks, policy)
                rows.append({"workload": kind, "seed": seed, **evaluate(result)})
    return pd.DataFrame(rows)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(EXPERIMENT.seeds))
    parser.add_argument("--workloads", nargs="+", default=["stable", "bursty", "heterogeneous"])
    parser.add_argument("--limit", type=int, default=None, help="cap tasks per matched trace")
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    runs = run_matrix(args.workloads, args.seeds, args.limit)
    summary = summarise_runs(runs)
    ect = paired_differences(runs, "uncertainty_ect", "ect_only")
    args.out.mkdir(parents=True, exist_ok=True)
    runs.to_csv(args.out / "v2_runs.csv", index=False)
    summary.to_csv(args.out / "v2_summary.csv", index=False)
    ect.to_csv(args.out / "v2_ect_paired.csv", index=False)
    for workload in args.workloads:
        selected = summary[summary.workload == workload]
        cols = ["policy", "mean_response_s_mean", "p95_response_s_mean",
                "sla_violation_rate_mean", "throughput_mean", "goodput_mean"]
        print(f"\n== {workload} ==")
        print(selected[cols].round(3).to_string(index=False))
    print("\n== uncertainty_ect - ect_only ==")
    print(ect.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
