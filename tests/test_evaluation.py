import math

import pandas as pd
import pytest

from lbsim.config import ServerSpec, SimulationConfig
from lbsim.evaluation import (
    avg_cpu_utilisation, evaluate, horizon, load_imbalance, mean_response_time,
    overload_fraction, paired_differences, sla_violation_rate, summarise_runs, throughput,
)
from lbsim.policies import ProbabilisticPolicy, RoundRobinPolicy
from lbsim.simulator import SimulationResult, simulate
from lbsim.workload import Task, generate_workload


def task_frame(responses, completed=None):
    completed = completed or [True] * len(responses)
    return pd.DataFrame({"response_time": responses, "completed": completed})


def tick_frame(rows):
    """rows: (tick, server_id, cpu_pct, mem_pct, cpu_load_pct, mem_load_pct)"""
    return pd.DataFrame(rows, columns=["tick", "server_id", "cpu_pct", "mem_pct", "cpu_load_pct", "mem_load_pct"])


TICKS = tick_frame([
    (0, 0, 90.0, 10.0, 120.0, 10.0),
    (0, 1, 10.0, 10.0, 10.0, 10.0),
    (1, 0, 50.0, 90.0, 50.0, 90.0),
    (1, 1, 50.0, 10.0, 50.0, 10.0),
    (2, 0, 80.0, 85.0, 80.0, 85.0),   # exactly at both thresholds: not overloaded
    (2, 1, 0.0, 0.0, 0.0, 0.0),
])


def test_task_metrics_hand_computed():
    t = task_frame([2.0, 4.0, 20.0, 18.0])
    assert mean_response_time(t) == 11.0
    assert sla_violation_rate(t, 18.0) == 0.25          # 18 is not > 18
    assert throughput(t, 8) == 0.5


def test_unfinished_tasks_excluded_from_response_and_sla():
    t = task_frame([2.0, float("nan")], completed=[True, False])
    assert mean_response_time(t) == 2.0
    assert sla_violation_rate(t, 1.0) == 1.0
    assert throughput(t, 10) == 0.1


def test_zero_completions_give_nan_not_crash():
    t = task_frame([float("nan")], completed=[False])
    assert math.isnan(mean_response_time(t))
    assert math.isnan(sla_violation_rate(t, 18.0))
    assert throughput(t, 5) == 0.0
    assert math.isnan(throughput(t, 0))


def test_interval_metrics_hand_computed():
    assert avg_cpu_utilisation(TICKS) == pytest.approx(280 / 6)
    assert load_imbalance(TICKS) == pytest.approx((40 + 0 + 40) / 3)   # population std per tick
    assert overload_fraction(TICKS, 80, 85, "cpu_pct", "mem_pct") == pytest.approx(2 / 6)
    assert overload_fraction(TICKS, 80, 85, "cpu_load_pct", "mem_load_pct") == pytest.approx(2 / 6)


def test_horizon_drops_drain_ticks():
    assert set(horizon(TICKS, 2)["tick"]) == {0, 1}
    assert avg_cpu_utilisation(horizon(TICKS, 1)) == 50.0


def test_empty_interval_metrics_are_nan():
    empty = TICKS.iloc[0:0]
    assert math.isnan(avg_cpu_utilisation(empty))
    assert math.isnan(load_imbalance(empty))
    assert math.isnan(overload_fraction(empty, 80, 85, "cpu_pct", "mem_pct"))


def test_evaluate_on_real_run_is_consistent():
    tasks = generate_workload("stable", 0).tasks[:300]
    res = simulate(tasks, ProbabilisticPolicy())
    m = evaluate(res, r_sla=18.0, t_sim=tasks[-1].arrival_tick + 1)
    assert m["drained"] and m["n_completed"] == m["n_tasks"] == 300 and m["n_unfinished"] == 0
    assert m["throughput"] == pytest.approx(300 / res.n_ticks)
    assert 0 <= m["sla_violation_rate"] <= 1 and 0 <= m["avg_cpu_util"] <= 100
    assert 0 <= m["mean_p_risk"] <= 1 and 0 <= m["capacity_pressure_rate"] <= 1
    assert m["overload_frac_util"] <= m["overload_frac_load"]   # load % >= utilisation % (D19)


def test_baselines_report_nan_risk():
    res = simulate(generate_workload("stable", 0).tasks[:50], RoundRobinPolicy())
    m = evaluate(res)
    assert math.isnan(m["mean_p_risk"])
    assert m["capacity_pressure_rate"] == 0.0


def test_undrained_run_counts_unfinished():
    tasks = [Task(id=i, arrival_tick=0, cpu_demand=1.0, mem_demand=1.0, work=50.0) for i in range(3)]
    res = simulate(tasks, RoundRobinPolicy(), specs=(ServerSpec(4, 8, 1.0),), sim=SimulationConfig(max_ticks=10))
    m = evaluate(res, t_sim=1)
    assert not m["drained"] and m["n_unfinished"] == 3 and m["n_completed"] == 0
    assert math.isnan(m["mean_response_s"]) and m["throughput"] == 0.0


def test_evaluate_is_deterministic_for_matching_seeds():
    tasks = generate_workload("bursty", 3).tasks[:200]
    a = evaluate(simulate(tasks, ProbabilisticPolicy()))
    b = evaluate(simulate(tasks, ProbabilisticPolicy()))
    assert a == pytest.approx(b, nan_ok=True)


RUNS = pd.DataFrame([
    {"workload": "w", "seed": s, "policy": p, "drained": True,
     "mean_response_s": r, "p95_response_s": r, "throughput": th,
     "sla_violation_rate": v, "overload_frac_util": 0.1, "overload_frac_load": 0.2}
    for s, p, r, th, v in [
        (0, "new", 5.0, 1.0, 0.1), (0, "old", 6.0, 1.0, 0.2),
        (1, "new", 7.0, 2.0, 0.3), (1, "old", 6.0, 1.0, 0.3),
    ]
])


def test_paired_differences_and_wins():
    p = paired_differences(RUNS, "new", "old").set_index("metric")
    assert p.loc["mean_response_s", "mean_diff"] == 0.0           # (-1 + 1) / 2
    assert p.loc["mean_response_s", "target_wins"] == 1
    assert p.loc["throughput", "target_wins"] == 1                 # higher is better
    assert p.loc["sla_violation_rate", "ties"] == 1
    assert p.loc["overload_frac_util", "ties"] == 2 and p.loc["overload_frac_util", "target_wins"] == 0
    assert (p["n_seeds"] == 2).all()


def test_summarise_runs_mean_std_and_order():
    s = summarise_runs(RUNS).set_index("policy")
    assert list(s.index) == ["new", "old"]
    assert s.loc["new", "mean_response_s_mean"] == 6.0
    assert s.loc["new", "mean_response_s_std"] == pytest.approx(math.sqrt(2))   # ddof=1
    assert s.loc["old", "n_seeds"] == 2 and s.loc["old", "all_drained"]
    assert "seed_mean" not in s.columns
