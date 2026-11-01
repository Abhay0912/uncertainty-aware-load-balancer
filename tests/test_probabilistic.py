from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from lbsim.config import SCORING, ServerSpec
from lbsim.policies import ProbabilisticPolicy, WeightedMetricPolicy, all_policies
from lbsim.scoring import (
    combined_risk,
    exceedance_probability,
    normal_cdf,
    risk_adjusted_score,
    server_risk,
)
from lbsim.server import build_servers
from lbsim.simulator import simulate
from lbsim.workload import Task, generate_workload

SMALL = (ServerSpec(cores=4, mem_gb=8, speed=1.0), ServerSpec(cores=2, mem_gb=4, speed=0.5))


def make_task(i, cpu=1.0, mem=1.0, work=5.0):
    return Task(id=i, arrival_tick=0, cpu_demand=cpu, mem_demand=mem, work=work)


def fill_windows(server, cpu, mem=None):
    for i, c in enumerate(cpu):
        server.cpu_window.push(c)
        server.mem_window.push(0.0 if mem is None else mem[i])


# --- formulas ------------------------------------------------------------------

def test_normal_cdf_known_values():
    assert normal_cdf(0.0) == 0.5
    assert normal_cdf(1.959964) == pytest.approx(0.975, abs=1e-6)
    assert normal_cdf(-1.0) == pytest.approx(1 - normal_cdf(1.0))
    assert normal_cdf(-40.0) == 0.0 and normal_cdf(40.0) == 1.0


@pytest.mark.parametrize("mu, expected", [(80.1, 1.0), (80.0, 0.0), (79.9, 0.0), (250.0, 1.0)])
def test_exceedance_sigma_zero_is_deterministic(mu, expected):
    assert exceedance_probability(mu, 0.0, 80.0) == expected


def test_exceedance_with_variance():
    assert exceedance_probability(80.0, 5.0, 80.0) == 0.5
    assert exceedance_probability(60.0, 20.0, 80.0) == pytest.approx(1 - normal_cdf(1.0))
    # below threshold: more spread -> more risk; above threshold: more spread -> less risk
    assert exceedance_probability(60.0, 5.0, 80.0) < exceedance_probability(60.0, 20.0, 80.0)
    assert exceedance_probability(95.0, 5.0, 80.0) > exceedance_probability(95.0, 20.0, 80.0)
    with pytest.raises(ValueError):
        exceedance_probability(50.0, -1.0, 80.0)


def test_exceedance_always_a_probability():
    rng = np.random.default_rng(0)
    for mu, sigma in zip(rng.uniform(-50, 300, 500), rng.uniform(0, 100, 500)):
        assert 0.0 <= exceedance_probability(mu, sigma, 80.0) <= 1.0


def test_combined_risk():
    assert combined_risk(0.0, 0.0) == 0.0
    assert combined_risk(1.0, 0.3) == 1.0
    assert combined_risk(0.5, 0.5) == pytest.approx(0.75)
    assert combined_risk(0.2, 0.0) == pytest.approx(0.2)
    for bad in [(-0.1, 0.0), (0.0, 1.1)]:
        with pytest.raises(ValueError):
            combined_risk(*bad)


def test_risk_adjusted_score_hand_computed():
    assert risk_adjusted_score(0.5, 0.25, SCORING) == pytest.approx(0.6 * 0.5 + 0.4 * 0.25)
    assert risk_adjusted_score(0.0, 1.0, SCORING) == pytest.approx(0.4)


# --- server_risk -----------------------------------------------------------------

def test_empty_windows_mean_zero_risk():
    r = server_risk(build_servers(SMALL)[0])
    assert (r.p_cpu, r.p_mem, r.p_risk) == (0.0, 0.0, 0.0)


def test_same_mean_different_variance_motivating_example():
    steady, bursty = build_servers(SMALL)
    fill_windows(steady, [60.0] * 10)
    fill_windows(bursty, [30.0, 90.0] * 5)  # mean 60, sigma 30
    assert steady.cpu_window.mean() == bursty.cpu_window.mean() == 60.0
    assert server_risk(steady).p_risk == 0.0
    assert server_risk(bursty).p_risk == pytest.approx(1 - normal_cdf(20 / 30))


def test_backlogged_server_load_above_100_is_certain_risk():
    (s,) = build_servers(SMALL[:1])
    fill_windows(s, [150.0, 160.0] * 5, mem=[90.0] * 10)
    r = server_risk(s)
    assert r.p_cpu > 0.999 and r.p_mem == 1.0 and r.p_risk == 1.0


# --- policy ----------------------------------------------------------------------

def test_fresh_servers_pick_first_without_pressure():
    policy = ProbabilisticPolicy()
    assert policy.select(build_servers(), make_task(0)) == 0
    info = policy.decision_info()
    assert info["p_risk"] == 0.0 and info["n_eligible"] == 5 and info["capacity_pressure"] is False


def test_risky_server_excluded_even_with_lower_score():
    servers = build_servers(SMALL)
    fill_windows(servers[0], [71.0, 91.0] * 5)  # mu 81, sigma 10 -> P_C ~ 0.54; live load 0
    servers[1].assign(make_task(0, cpu=1.5, mem=3.0), tick=0)  # live L = 0.6, no history
    s0 = risk_adjusted_score(0.0, server_risk(servers[0]).p_risk)
    assert server_risk(servers[0]).p_risk > 0.5 and s0 < 0.6 * 0.6
    assert WeightedMetricPolicy().select(servers, make_task(1)) == 0
    policy = ProbabilisticPolicy()
    assert policy.select(servers, make_task(1)) == 1
    assert policy.decision_info()["n_eligible"] == 1
    assert policy.decision_info()["capacity_pressure"] is False


def test_risk_exactly_at_threshold_is_eligible():
    servers = build_servers(SMALL)
    fill_windows(servers[0], [75.0, 85.0] * 5)  # mu = theta_C -> P_risk = 0.5 exactly
    servers[1].assign(make_task(0, cpu=1.5, mem=3.0), tick=0)
    assert server_risk(servers[0]).p_risk == 0.5
    policy = ProbabilisticPolicy()
    assert policy.select(servers, make_task(1)) == 0
    assert policy.decision_info()["n_eligible"] == 2


def test_all_servers_risky_picks_lowest_score_and_flags_pressure():
    servers = build_servers(SMALL)
    for s in servers:
        fill_windows(s, [100.0] * 10)  # sigma = 0, mu > theta -> P = 1
    servers[0].assign(make_task(0, cpu=3.0, mem=6.0), tick=0)
    policy = ProbabilisticPolicy()
    assert policy.select(servers, make_task(1)) == 1
    info = policy.decision_info()
    assert info["capacity_pressure"] is True and info["n_eligible"] == 0 and info["p_risk"] == 1.0
    policy.reset()
    assert policy.decision_info() == {}


def test_does_not_mutate_servers():
    servers = build_servers()
    for i, s in enumerate(servers):
        fill_windows(s, [20.0 * i, 20.0 * i + 30.0] * 5)
    servers[2].assign(make_task(0, cpu=2.0, mem=2.0), tick=0)
    servers[3].resp_window.push(4.0)
    before = [(s.cpu_pct, s.queue_length, s.cpu_window.values(), s.mem_window.values(),
               s.resp_window.values()) for s in servers]
    policy = ProbabilisticPolicy()
    for i in range(20):
        policy.select(servers, make_task(10 + i))
    after = [(s.cpu_pct, s.queue_length, s.cpu_window.values(), s.mem_window.values(),
              s.resp_window.values()) for s in servers]
    assert after == before


# --- integration -----------------------------------------------------------------

@pytest.fixture(scope="module")
def bursty0():
    return generate_workload("bursty", 0)


def test_without_risk_term_equals_weighted_metric(bursty0):
    """Ablation identity: S = 1.0*L + 0*P and no admission filter must reproduce WeightedMetric exactly."""
    no_risk = replace(SCORING, score_weights=(1.0, 0.0), risk_admission_threshold=1.0)
    a = simulate(bursty0.tasks, ProbabilisticPolicy(no_risk)).tasks["server_id"]
    b = simulate(bursty0.tasks, WeightedMetricPolicy()).tasks["server_id"]
    pd.testing.assert_series_equal(a, b)


def test_end_to_end_logs_risk_and_is_deterministic(bursty0):
    a = simulate(bursty0.tasks, ProbabilisticPolicy())
    b = simulate(bursty0.tasks, ProbabilisticPolicy())
    pd.testing.assert_frame_equal(a.tasks, b.tasks)
    t = a.tasks
    assert a.drained and t["completed"].all() and len(t) == len(bursty0.tasks)
    assert t["p_risk"].between(0.0, 1.0).all()
    assert t["capacity_pressure"].dtype == bool
    assert (t.loc[t.capacity_pressure, "p_risk"] > SCORING.risk_admission_threshold).all()
    assert (t.loc[~t.capacity_pressure, "p_risk"] <= SCORING.risk_admission_threshold).all()


def test_all_policies_lists_seven_unique():
    names = [p.name for p in all_policies(0)]
    assert len(names) == len(set(names)) == 7 and names[-1] == "probabilistic"
