"""Pure functions turning simulation logs into the evaluation metrics of docs/spec.md section 6 (decision D22).

Task metrics (response, SLA) use completed tasks only; unfinished ones are counted separately.
Per-interval metrics (utilisation, imbalance, overload) average over the arrival horizon [0, t_sim),
where every policy faces the same offered load. Throughput uses the whole run, drain included (D4).
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from lbsim.config import EXPERIMENT, SCORING, WORKLOAD, ScoringConfig
from lbsim.simulator import SimulationResult

NAN = float("nan")

# metric -> True if higher is better (used for win counts in paired comparisons)
HIGHER_IS_BETTER: dict[str, bool] = {
    "mean_response_s": False,
    "p95_response_s": False,
    "throughput": True,
    "sla_violation_rate": False,
    "overload_frac_util": False,
    "overload_frac_load": False,
}


def _completed_response(tasks: pd.DataFrame) -> pd.Series:
    return tasks.loc[tasks["completed"].astype(bool), "response_time"]


def mean_response_time(tasks: pd.DataFrame) -> float:
    """R-bar = (1/K) sum R_j over the K completed tasks; NaN if none completed."""
    r = _completed_response(tasks)
    return float(r.mean()) if len(r) else NAN


def response_quantile(tasks: pd.DataFrame, q: float) -> float:
    r = _completed_response(tasks)
    return float(r.quantile(q)) if len(r) else NAN


def throughput(tasks: pd.DataFrame, n_ticks: int) -> float:
    """Completed tasks per tick (= per second) over the whole run, drain included."""
    if n_ticks <= 0:
        return NAN
    return float(tasks["completed"].astype(bool).sum()) / n_ticks


def sla_violation_rate(tasks: pd.DataFrame, r_sla: float) -> float:
    """#{j : R_j > R_SLA} / K over completed tasks; NaN if none completed."""
    r = _completed_response(tasks)
    return float((r > r_sla).mean()) if len(r) else NAN


def horizon(server_ticks: pd.DataFrame, t_sim: int) -> pd.DataFrame:
    """Per-(tick, server) rows inside the arrival horizon [0, t_sim)."""
    return server_ticks[server_ticks["tick"] < t_sim]


def avg_cpu_utilisation(server_ticks: pd.DataFrame) -> float:
    """(1/(N*T)) sum_i sum_t C_i(t): the unweighted mean of true utilisation over servers and ticks."""
    return float(server_ticks["cpu_pct"].mean()) if len(server_ticks) else NAN


def load_imbalance(server_ticks: pd.DataFrame) -> float:
    """Mean over ticks of I(t) = population std across servers of C_i(t)."""
    if not len(server_ticks):
        return NAN
    per_tick = server_ticks.groupby("tick")["cpu_pct"].std(ddof=0)
    return float(per_tick.mean())


def overload_fraction(
    server_ticks: pd.DataFrame, theta_cpu: float, theta_mem: float, cpu_col: str, mem_col: str
) -> float:
    """Fraction of server-intervals with C > theta_C or M > theta_M (strict, matching D6)."""
    if not len(server_ticks):
        return NAN
    over = (server_ticks[cpu_col] > theta_cpu) | (server_ticks[mem_col] > theta_mem)
    return float(over.mean())


def mean_decision_field(tasks: pd.DataFrame, column: str) -> float:
    """Mean of a per-decision field (e.g. p_risk); NaN for policies that do not log it."""
    if column not in tasks.columns or not len(tasks):
        return NAN
    return float(pd.to_numeric(tasks[column], errors="coerce").astype(float).mean())


def evaluate(
    res: SimulationResult,
    r_sla: float = EXPERIMENT.r_sla,
    cfg: ScoringConfig = SCORING,
    t_sim: int = WORKLOAD.t_sim,
) -> dict[str, float | int | bool | str]:
    """All spec section 6 metrics for one run."""
    t = res.tasks
    window = horizon(res.server_ticks, t_sim)
    n_completed = int(t["completed"].astype(bool).sum())
    return {
        "policy": res.policy,
        "n_tasks": len(t),
        "n_completed": n_completed,
        "n_unfinished": len(t) - n_completed,
        "drained": res.drained,
        "makespan": res.n_ticks,
        "mean_response_s": mean_response_time(t),
        "p95_response_s": response_quantile(t, 0.95),
        "throughput": throughput(t, res.n_ticks),
        "sla_violation_rate": sla_violation_rate(t, r_sla),
        "avg_cpu_util": avg_cpu_utilisation(window),
        "load_imbalance": load_imbalance(window),
        "overload_frac_util": overload_fraction(window, cfg.theta_cpu, cfg.theta_mem, "cpu_pct", "mem_pct"),
        "overload_frac_load": overload_fraction(
            window, cfg.theta_cpu, cfg.theta_mem, "cpu_load_pct", "mem_load_pct"
        ),
        "mean_p_risk": mean_decision_field(t, "p_risk"),
        "capacity_pressure_rate": mean_decision_field(t, "capacity_pressure"),
    }


def metric_columns(runs: pd.DataFrame) -> list[str]:
    keys = {"policy", "workload", "seed", "drained"}
    return [c for c in runs.columns if c not in keys and pd.api.types.is_numeric_dtype(runs[c])]


def summarise_runs(runs: pd.DataFrame) -> pd.DataFrame:
    """Mean and sample std (ddof=1) across seeds per (workload, policy); policy order is preserved."""
    cols = metric_columns(runs)
    grouped = runs.groupby(["workload", "policy"], sort=False)[cols]
    summary = grouped.agg(["mean", "std"])
    summary.columns = [f"{m}_{stat}" for m, stat in summary.columns]
    summary.insert(0, "n_seeds", grouped.size())
    summary.insert(1, "all_drained", runs.groupby(["workload", "policy"], sort=False)["drained"].all())
    return summary.reset_index()


def paired_differences(
    runs: pd.DataFrame,
    target: str,
    baseline: str,
    metrics: Iterable[str] = tuple(HIGHER_IS_BETTER),
) -> pd.DataFrame:
    """Per workload: mean and std over seeds of (target - baseline), and how many seeds the target won.
    Matched seeds share one task list, so the difference cancels workload-to-workload noise."""
    rows = []
    for workload, group in runs.groupby("workload", sort=False):
        a = group[group["policy"] == target].set_index("seed")
        b = group[group["policy"] == baseline].set_index("seed")
        seeds = a.index.intersection(b.index)
        for m in metrics:
            diff = a.loc[seeds, m] - b.loc[seeds, m]
            better = diff > 0 if HIGHER_IS_BETTER[m] else diff < 0
            rows.append({
                "workload": workload,
                "metric": m,
                "target": target,
                "baseline": baseline,
                "n_seeds": len(seeds),
                "mean_diff": float(diff.mean()) if len(seeds) else NAN,
                "std_diff": float(diff.std(ddof=1)) if len(seeds) > 1 else NAN,
                "target_wins": int(better.sum()),
                "ties": int((diff == 0).sum()),
            })
    return pd.DataFrame(rows)
