from collections import Counter
from itertools import groupby

import numpy as np
import pandas as pd
import pytest

from lbsim.config import SCORING, SERVERS, WRR_WEIGHTS, ServerSpec
from lbsim.policies import (
    LeastCPUPolicy,
    PowerOfTwoChoicesPolicy,
    RandomPolicy,
    WeightedMetricPolicy,
    WeightedRoundRobinPolicy,
    baseline_policies,
    policy_rng,
)
from lbsim.scoring import load_score, normalised_response, server_load_score
from lbsim.server import build_servers
from lbsim.simulator import simulate
from lbsim.workload import Task, generate_workload

SMALL = (ServerSpec(cores=4, mem_gb=8, speed=1.0), ServerSpec(cores=2, mem_gb=4, speed=0.5))


def make_task(i, cpu=1.0, mem=1.0, work=5.0, arrival=0):
    return Task(id=i, arrival_tick=arrival, cpu_demand=cpu, mem_demand=mem, work=work)


def loaded_servers(loads, specs=SERVERS):
    """Fresh servers; loads[i] is a list of (cpu, mem) tasks started on server i."""
    servers = build_servers(specs)
    tid = 0
    for server, tasks in zip(servers, loads):
        for cpu, mem in tasks:
            server.assign(make_task(tid, cpu, mem), tick=0)
            tid += 1
    return servers


def snapshot(servers):
    return [
        (s.cpu_pct, s.mem_pct, s.n_running, s.queue_length, s.completed,
         s.cpu_window.values(), s.mem_window.values(), s.resp_window.values())
        for s in servers
    ]


# --- scoring -------------------------------------------------------------------

def test_normalised_response_edges():
    assert normalised_response(0.0, 6.0) == 0.0
    assert normalised_response(6.0, 6.0) == 0.5
    assert 0.99 < normalised_response(1e4, 6.0) < 1.0
    with pytest.raises(ValueError):
        normalised_response(1.0, 0.0)
    with pytest.raises(ValueError):
        normalised_response(-1.0, 6.0)


def test_load_score_hand_computed():
    assert load_score(50.0, 25.0, 6.0, SCORING) == pytest.approx(0.4 * 0.5 + 0.4 * 0.25 + 0.2 * 0.5)
    assert load_score(0.0, 0.0, 0.0, SCORING) == 0.0
    assert load_score(100.0, 100.0, 0.0, SCORING) == pytest.approx(0.8)


def test_server_load_score_uses_live_state():
    (s,) = loaded_servers([[(2.0, 4.0)]], specs=SMALL[:1])
    assert server_load_score(s) == pytest.approx(0.4 * 0.5 + 0.4 * 0.5)


# --- WRR -----------------------------------------------------------------------

def test_wrr_exact_counts_per_cycle_and_smooth():
    wrr = WeightedRoundRobinPolicy()
    servers = [None] * len(WRR_WEIGHTS)
    cycle = int(sum(WRR_WEIGHTS))
    picks = [wrr.select(servers, None) for _ in range(2 * cycle)]
    for half in (picks[:cycle], picks[cycle:]):
        assert Counter(half) == {i: int(w) for i, w in enumerate(WRR_WEIGHTS)}
    assert picks[:cycle] == picks[cycle:]
    longest_run = max(len(list(run)) for _, run in groupby(picks))
    assert longest_run <= 2, "smooth WRR must interleave, not send blocks"


def test_wrr_equal_weights_is_round_robin_and_resets():
    wrr = WeightedRoundRobinPolicy((1, 1, 1))
    servers = [None] * 3
    assert [wrr.select(servers, None) for _ in range(6)] == [0, 1, 2, 0, 1, 2]
    wrr.select(servers, None)
    wrr.reset()
    assert wrr.select(servers, None) == 0


@pytest.mark.parametrize("weights", [(), (1, 0), (2, -1)])
def test_wrr_rejects_bad_weights(weights):
    with pytest.raises(ValueError):
        WeightedRoundRobinPolicy(weights)


def test_wrr_rejects_server_count_mismatch():
    with pytest.raises(ValueError):
        WeightedRoundRobinPolicy((1, 2)).select([None] * 3, None)


# --- Random --------------------------------------------------------------------

def test_random_is_roughly_uniform_and_seeded():
    servers = build_servers()
    task = make_task(0)
    policy = RandomPolicy(policy_rng(3))
    draws = [policy.select(servers, task) for _ in range(5000)]
    counts = np.bincount(draws, minlength=len(servers)) / len(draws)
    assert np.allclose(counts, 1 / len(servers), atol=0.03)
    twin = RandomPolicy(policy_rng(3))
    assert [twin.select(servers, task) for _ in range(50)] == draws[:50]
    policy.reset()
    assert [policy.select(servers, task) for _ in range(50)] == draws[:50]


def test_random_skips_servers_the_task_cannot_fit():
    servers = build_servers(SMALL)
    big = make_task(0, cpu=3.0)
    policy = RandomPolicy(policy_rng(0))
    assert {policy.select(servers, big) for _ in range(200)} == {0}
    with pytest.raises(ValueError):
        policy.select(servers, make_task(1, cpu=10.0))


def test_policy_rng_independent_of_workload_streams():
    wl_streams = np.random.SeedSequence(0).spawn(5)
    ours = policy_rng(0).random(5)
    for stream in [np.random.SeedSequence(0), *wl_streams]:
        assert not np.allclose(np.random.default_rng(stream).random(5), ours)
    assert np.array_equal(policy_rng(0).random(5), ours)
    assert not np.array_equal(policy_rng(1).random(5), ours)


# --- Least CPU -----------------------------------------------------------------

def test_least_cpu_picks_lowest_percentage_not_lowest_cores():
    # server 0: 1/4 = 25%, server 1: 1/2 = 50%  -> server 0 despite equal absolute load
    servers = loaded_servers([[(1.0, 1.0)], [(1.0, 0.5)]], specs=SMALL)
    assert LeastCPUPolicy().select(servers, make_task(9)) == 0
    servers = loaded_servers([[(3.0, 1.0)], [(1.0, 0.5)]], specs=SMALL)
    assert LeastCPUPolicy().select(servers, make_task(9)) == 1


def test_least_cpu_tie_goes_to_lowest_index():
    assert LeastCPUPolicy().select(build_servers(), make_task(0)) == 0


# --- Weighted metric -----------------------------------------------------------

def test_weighted_metric_accounts_for_memory():
    # server 0: CPU 25%, mem 87.5% -> L = 0.45; server 1: CPU 50%, mem 25% -> L = 0.30
    servers = loaded_servers([[(1.0, 7.0)], [(1.0, 1.0)]], specs=SMALL)
    assert LeastCPUPolicy().select(servers, make_task(9)) == 0
    assert WeightedMetricPolicy().select(servers, make_task(9)) == 1


def test_weighted_metric_accounts_for_response_time():
    servers = build_servers(SMALL)
    for _ in range(3):
        servers[0].resp_window.push(60.0)
    assert WeightedMetricPolicy().select(servers, make_task(9)) == 1


# --- P2C -----------------------------------------------------------------------

def test_p2c_with_two_servers_equals_weighted_metric():
    servers = loaded_servers([[(1.0, 7.0)], [(1.0, 1.0)]], specs=SMALL)
    p2c = PowerOfTwoChoicesPolicy(policy_rng(0))
    expected = WeightedMetricPolicy().select(servers, make_task(9))
    assert all(p2c.select(servers, make_task(9)) == expected for _ in range(50))


def test_p2c_never_picks_the_worse_of_its_two_samples():
    # L = 0.6, 0, 0.5, 0.075, 0.4: server 0 is the unique worst
    servers = loaded_servers([[(3.0, 6.0)], [], [(5.0, 10.0)], [(1.0, 1.0)], [(1.0, 2.0)]])
    scores = [server_load_score(s) for s in servers]
    worst = int(np.argmax(scores))
    assert sorted(scores)[-2] < scores[worst]
    p2c = PowerOfTwoChoicesPolicy(policy_rng(0))
    picks = [p2c.select(servers, make_task(9)) for _ in range(500)]
    assert worst not in picks
    assert set(picks) == set(range(len(servers))) - {worst}


def test_p2c_single_server():
    servers = build_servers(SMALL[:1])
    assert PowerOfTwoChoicesPolicy(policy_rng(0)).select(servers, make_task(0)) == 0


# --- contract & integration ----------------------------------------------------

@pytest.mark.parametrize("policy", baseline_policies(0), ids=lambda p: p.name)
def test_policy_does_not_mutate_servers(policy):
    servers = loaded_servers([[(1.0, 2.0)], [(3.0, 1.0)], [], [(2.0, 2.0)], [(1.0, 1.0)]])
    for s in servers:
        s.sample()
    servers[2].resp_window.push(4.0)
    before = snapshot(servers)
    for i in range(20):
        policy.select(servers, make_task(100 + i))
    assert snapshot(servers) == before


def test_baseline_names_unique():
    names = [p.name for p in baseline_policies(0)]
    assert len(set(names)) == len(names) == 6


@pytest.fixture(scope="module")
def bursty0():
    return generate_workload("bursty", 0)


@pytest.mark.parametrize("index", range(1, 6), ids=lambda i: baseline_policies(0)[i].name)
def test_baseline_end_to_end_complete_and_deterministic(bursty0, index):
    policy = baseline_policies(0)[index]
    a = simulate(bursty0.tasks, policy)
    b = simulate(bursty0.tasks, policy)
    assert a.drained and a.tasks["completed"].all()
    assert sorted(a.tasks["task_id"]) == [t.id for t in bursty0.tasks]
    pd.testing.assert_frame_equal(a.tasks, b.tasks)


def test_randomised_policy_seed_changes_assignments(bursty0):
    a = simulate(bursty0.tasks, RandomPolicy(policy_rng(0))).tasks["server_id"]
    b = simulate(bursty0.tasks, RandomPolicy(policy_rng(1))).tasks["server_id"]
    assert not a.equals(b)


def test_least_cpu_sees_hidden_backlog():
    # server 1 (2 cores): one 1.2-core task running (60%) + one 1.0-core task queued -> load 110%
    servers = loaded_servers([[(3.0, 1.0)], [(1.2, 0.5), (1.0, 0.5)]], specs=SMALL)
    assert servers[1].queue_length == 1 and servers[1].cpu_pct == pytest.approx(60.0)
    assert LeastCPUPolicy().select(servers, make_task(9)) == 0
    blind = build_servers(SMALL, count_queued=False)
    for sid, (cpu, mem) in [(0, (3.0, 1.0)), (1, (1.2, 0.5)), (1, (1.0, 0.5))]:
        blind[sid].assign(make_task(50 + sid, cpu, mem), tick=0)
    assert LeastCPUPolicy().select(blind, make_task(9)) == 1


def test_simulate_logs_load_and_respects_flag(bursty0):
    from dataclasses import replace
    on = simulate(bursty0.tasks, LeastCPUPolicy())
    off = simulate(bursty0.tasks, LeastCPUPolicy(), scoring=replace(SCORING, count_queued=False))
    st = on.server_ticks
    assert (st["cpu_load_pct"] >= st["cpu_pct"] - 1e-9).all()
    assert (st.loc[st.queue_length == 0, "cpu_load_pct"] - st.loc[st.queue_length == 0, "cpu_pct"]).abs().max() < 1e-9
    assert not on.tasks["server_id"].equals(off.tasks["server_id"])
