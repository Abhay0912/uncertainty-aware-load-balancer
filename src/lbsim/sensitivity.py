"""Sensitivity sweeps of the probabilistic policy against its ablation (decision D26).

At every sweep point both `probabilistic` and `weighted_metric` run under the same ScoringConfig on the
same task list, so the paired difference isolates the risk term at that setting. Outcome metrics are
always evaluated with the frozen SCORING thresholds: the knob moves, the yardstick does not.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

import pandas as pd

from lbsim.config import SCORING, SENSITIVITY, ScoringConfig, SensitivityConfig
from lbsim.evaluation import evaluate, paired_differences
from lbsim.policies import ProbabilisticPolicy, WeightedMetricPolicy
from lbsim.simulator import simulate
from lbsim.workload import Task

TARGET, ABLATION = ProbabilisticPolicy.name, WeightedMetricPolicy.name
AXES = ("theta", "admission", "risk_weight", "window")
GRID = "theta_x_admission"
# axis -> config column that varies along it (used for grouping and plotting)
AXIS_COLUMN = {"theta": "theta_cpu", "admission": "admission", "risk_weight": "risk_weight", "window": "window"}
POINT_COLUMNS = ["axis", "theta_cpu", "admission", "risk_weight", "window"]

Stream = tuple[str, int, Sequence[Task]]


@dataclass(frozen=True)
class SweepPoint:
    axis: str
    cfg: ScoringConfig


def apply_axis(base: ScoringConfig, axis: str, value: float) -> ScoringConfig:
    """Copy of `base` with one sensitivity axis set to `value`."""
    if axis == "theta":
        return replace(base, theta_cpu=value, theta_mem=value + (base.theta_mem - base.theta_cpu))
    if axis == "admission":
        return replace(base, risk_admission_threshold=value)
    if axis == "risk_weight":
        return replace(base, score_weights=(1.0 - value, value))
    if axis == "window":
        return replace(base, window=int(value))
    raise ValueError(f"unknown sensitivity axis {axis!r}")


def sweep_points(base: ScoringConfig = SCORING, sens: SensitivityConfig = SENSITIVITY) -> list[SweepPoint]:
    """One-at-a-time points for each axis, then the theta x admission grid."""
    values = {"theta": sens.theta_cpu, "admission": sens.admission,
              "risk_weight": sens.risk_weight, "window": sens.window}
    points = [SweepPoint(axis, apply_axis(base, axis, v)) for axis in AXES for v in values[axis]]
    points += [
        SweepPoint(GRID, apply_axis(apply_axis(base, "theta", t), "admission", a))
        for t in sens.theta_cpu for a in sens.admission
    ]
    return points


def point_fields(p: SweepPoint) -> dict[str, float | str]:
    return {
        "axis": p.axis,
        "theta_cpu": p.cfg.theta_cpu,
        "admission": p.cfg.risk_admission_threshold,
        "risk_weight": p.cfg.score_weights[1],
        "window": p.cfg.window,
    }


def _ablation_key(cfg: ScoringConfig) -> tuple:
    """WeightedMetric ignores theta, score weights and admission; only these fields change its run."""
    return (cfg.window, cfg.load_weights, cfg.r_ref, cfg.count_queued)


def run_sweep(
    points: Sequence[SweepPoint],
    streams: Iterable[Stream],
    eval_cfg: ScoringConfig = SCORING,
) -> pd.DataFrame:
    """One row per (point, workload, seed, policy). Identical configs are simulated once and reused."""
    cache: dict[tuple, dict] = {}
    rows = []
    for kind, seed, tasks in streams:
        for p in points:
            for policy_cls, key in (
                (ProbabilisticPolicy, (TARGET, p.cfg)),
                (WeightedMetricPolicy, (ABLATION, _ablation_key(p.cfg))),
            ):
                ckey = (kind, seed, key)
                if ckey not in cache:
                    res = simulate(tasks, policy_cls(p.cfg), scoring=p.cfg)
                    cache[ckey] = evaluate(res, cfg=eval_cfg)
                rows.append({**point_fields(p), "workload": kind, "seed": seed, **cache[ckey]})
    return pd.DataFrame(rows)


def sensitivity_table(runs: pd.DataFrame) -> pd.DataFrame:
    """Paired target - ablation per sweep point and metric, plus the target's own diagnostics."""
    frames = []
    for point, group in runs.groupby(POINT_COLUMNS, sort=False):
        paired = paired_differences(group, TARGET, ABLATION)
        target = group[group["policy"] == TARGET].groupby("workload", sort=False)
        diag = target[["capacity_pressure_rate", "mean_p_risk"]].mean().add_prefix("target_")
        paired = paired.join(diag, on="workload")
        for col, val in zip(POINT_COLUMNS, point):
            paired[col] = val
        frames.append(paired)
    table = pd.concat(frames, ignore_index=True)
    return table[POINT_COLUMNS + [c for c in table.columns if c not in POINT_COLUMNS]]
