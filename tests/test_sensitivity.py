import pytest

from lbsim.config import SCORING, SensitivityConfig, ScoringConfig
from lbsim.evaluation import evaluate
from lbsim.policies import ProbabilisticPolicy, WeightedMetricPolicy
from lbsim.sensitivity import (
    ABLATION, GRID, TARGET, SweepPoint, apply_axis, run_sweep, sensitivity_table, sweep_points,
)
from lbsim.simulator import simulate
from lbsim.workload import generate_workload

SMALL = SensitivityConfig(theta_cpu=(80.0, 120.0), admission=(0.5, 1.0), risk_weight=(0.0, 0.4), window=(10,))


@pytest.fixture(scope="module")
def stream():
    wl = generate_workload("bursty", 0)
    return [("bursty", 0, wl.tasks[:300])]


def test_theta_axis_keeps_memory_offset():
    cfg = apply_axis(SCORING, "theta", 120.0)
    assert (cfg.theta_cpu, cfg.theta_mem) == (120.0, 125.0)


def test_risk_weight_axis_sums_to_one():
    assert apply_axis(SCORING, "risk_weight", 0.8).score_weights == pytest.approx((0.2, 0.8))


def test_admission_and_window_axes():
    assert apply_axis(SCORING, "admission", 0.9).risk_admission_threshold == 0.9
    assert apply_axis(SCORING, "window", 20).window == 20


def test_unknown_axis_rejected():
    with pytest.raises(ValueError):
        apply_axis(SCORING, "gamma", 1.0)


def test_theta_above_100_needs_load_signal():
    assert ScoringConfig(theta_cpu=150.0, theta_mem=155.0).theta_cpu == 150.0
    with pytest.raises(ValueError):
        ScoringConfig(theta_cpu=150.0, count_queued=False)


def test_point_count_and_every_axis_contains_defaults():
    points = sweep_points(SCORING, SMALL)
    assert len(points) == 2 + 2 + 2 + 1 + 2 * 2
    for axis in ("theta", "admission", "risk_weight", "window"):
        assert any(p.cfg == SCORING for p in points if p.axis == axis)
    assert sum(p.axis == GRID for p in points) == 4


def test_default_point_matches_phase6_runs(stream):
    kind, seed, tasks = stream[0]
    runs = run_sweep([SweepPoint("theta", SCORING)], stream)
    for cls in (ProbabilisticPolicy, WeightedMetricPolicy):
        row = runs[runs["policy"] == cls.name].iloc[0]
        direct = evaluate(simulate(tasks, cls()))
        assert row["mean_response_s"] == direct["mean_response_s"]
        assert row["sla_violation_rate"] == direct["sla_violation_rate"]


def test_ablation_cache_matches_fresh_run(stream):
    _, _, tasks = stream[0]
    cfg = apply_axis(SCORING, "theta", 120.0)
    runs = run_sweep([SweepPoint("theta", SCORING), SweepPoint("theta", cfg)], stream)
    fresh = evaluate(simulate(tasks, WeightedMetricPolicy(cfg), scoring=cfg))
    wm = runs[(runs["policy"] == ABLATION) & (runs["theta_cpu"] == 120.0)].iloc[0]
    assert wm["mean_response_s"] == fresh["mean_response_s"]


def test_zero_risk_weight_without_admission_is_the_ablation(stream):
    cfg = apply_axis(apply_axis(SCORING, "risk_weight", 0.0), "admission", 1.0)
    table = sensitivity_table(run_sweep([SweepPoint(GRID, cfg)], stream))
    assert (table["mean_diff"] == 0).all()
    assert (table["ties"] == table["n_seeds"]).all()
    assert (table["target_wins"] == 0).all()


def test_table_has_one_row_per_point_workload_metric(stream):
    points = sweep_points(SCORING, SMALL)
    table = sensitivity_table(run_sweep(points, stream))
    n_unique = len({(p.axis, p.cfg) for p in points})
    assert len(table) == n_unique * table["metric"].nunique()
    assert set(table["target"]) == {TARGET}
    assert table["target_capacity_pressure_rate"].between(0, 1).all()
