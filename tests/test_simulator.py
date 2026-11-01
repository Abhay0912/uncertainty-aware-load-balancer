import math

import numpy as np
import pandas as pd
import pytest

from lbsim.config import SERVERS, ServerSpec, SimulationConfig
from lbsim.policies import Policy, RoundRobinPolicy
from lbsim.simulator import TASK_COLUMNS, simulate
from lbsim.workload import Task, generate_workload

SMALL = (ServerSpec(cores=4, mem_gb=8, speed=1.0), ServerSpec(cores=2, mem_gb=4, speed=0.5))


def make_task(i, arrival, work, cpu=1.0, mem=1.0):
    return Task(id=i, arrival_tick=arrival, cpu_demand=cpu, mem_demand=mem, work=work)


MICRO = (make_task(0, 0, 2.0), make_task(1, 0, 1.0), make_task(2, 1, 1.0))


class FixedPolicy(Policy):
    name = "fixed"

    def __init__(self, index):
        self.index = index

    def select(self, servers, task):
        return self.index


class InfoPolicy(FixedPolicy):
    name = "info"

    def decision_info(self):
        return {"p_risk": 0.25, "capacity_pressure": True}


@pytest.fixture(scope="module")
def bursty0():
    return generate_workload("bursty", 0)


def test_round_robin_cycles_and_resets():
    rr = RoundRobinPolicy()
    servers = [None] * 3
    assert [rr.select(servers, None) for _ in range(7)] == [0, 1, 2, 0, 1, 2, 0]
    rr.reset()
    assert rr.select(servers, None) == 0


def test_micro_scenario_hand_computed():
    res = simulate(MICRO, RoundRobinPolicy(), specs=SMALL)
    t = res.tasks.set_index("task_id")
    assert list(t["server_id"]) == [0, 1, 0]
    assert list(t["start_tick"]) == [0, 0, 1]
    assert list(t["finish_tick"]) == [2, 2, 2]
    assert list(t["response_time"]) == [2.0, 2.0, 1.0]
    assert res.drained and res.n_ticks == 2

    ticks = res.server_ticks.set_index(["tick", "server_id"])
    assert ticks.loc[(0, 0), "cpu_pct"] == 25.0
    assert ticks.loc[(1, 0), "cpu_pct"] == 50.0
    assert ticks.loc[(1, 1), "cpu_pct"] == 50.0
    assert ticks.loc[(1, 0), "completed"] == 0


def test_single_tick_task_is_visible_in_utilisation():
    res = simulate((make_task(0, 0, 1.0),), FixedPolicy(0), specs=SMALL)
    assert res.n_ticks == 1
    assert res.server_ticks.query("server_id == 0")["cpu_pct"].iloc[0] == 25.0


@pytest.mark.parametrize("kind", ["stable", "bursty"])
def test_every_task_completes_exactly_once(kind):
    wl = generate_workload(kind, 1)
    res = simulate(wl.tasks, RoundRobinPolicy())
    t = res.tasks
    assert res.drained
    assert sorted(t["task_id"]) == [task.id for task in wl.tasks]
    assert t["completed"].all()
    per_server = t.groupby("server_id").size()
    assert per_server.sum() == len(wl.tasks)
    assert res.server_ticks["tick"].max() == res.n_ticks - 1


def test_response_time_at_least_service_time(bursty0):
    t = simulate(bursty0.tasks, RoundRobinPolicy()).tasks
    speed = t["server_id"].map(lambda i: SERVERS[i].speed)
    service = np.ceil(t["work"] / speed)
    assert (t["response_time"] >= service).all()
    assert (t["start_tick"] >= t["arrival_tick"]).all()


def test_utilisation_bounded_and_log_is_complete(bursty0):
    res = simulate(bursty0.tasks, RoundRobinPolicy())
    st = res.server_ticks
    assert len(st) == res.n_ticks * len(SERVERS)
    assert st["cpu_pct"].between(0, 100 + 1e-9).all()
    assert st["mem_pct"].between(0, 100 + 1e-9).all()


def test_round_robin_assignment_follows_task_order(bursty0):
    t = simulate(bursty0.tasks, RoundRobinPolicy()).tasks
    assert list(t["server_id"]) == [i % len(SERVERS) for i in range(len(t))]


def test_deterministic_and_policy_reused_safely(bursty0):
    rr = RoundRobinPolicy()
    a = simulate(bursty0.tasks, rr)
    b = simulate(bursty0.tasks, rr)
    pd.testing.assert_frame_equal(a.tasks, b.tasks)
    pd.testing.assert_frame_equal(a.server_ticks, b.server_ticks)
    assert a.n_ticks == b.n_ticks


def test_truncation_flags_unfinished_tasks():
    tasks = (make_task(0, 0, 10.0), make_task(1, 1, 1.0))
    res = simulate(tasks, FixedPolicy(0), specs=SMALL, sim=SimulationConfig(max_ticks=3))
    assert not res.drained and res.n_ticks == 3
    t = res.tasks.set_index("task_id")
    assert not t.loc[0, "completed"] and math.isnan(t.loc[0, "response_time"])
    assert t.loc[1, "completed"] and t.loc[1, "response_time"] == 1.0


def test_max_ticks_before_last_arrival_rejected():
    with pytest.raises(ValueError):
        simulate((make_task(0, 5, 1.0),), FixedPolicy(0), specs=SMALL, sim=SimulationConfig(max_ticks=5))


def test_invalid_server_index_raises():
    with pytest.raises(ValueError):
        simulate(MICRO, FixedPolicy(2), specs=SMALL)


def test_unsorted_tasks_rejected():
    with pytest.raises(ValueError):
        simulate(tuple(reversed(MICRO)), FixedPolicy(0), specs=SMALL)


def test_decision_info_is_logged():
    t = simulate(MICRO, InfoPolicy(0), specs=SMALL).tasks
    assert list(t.columns) == TASK_COLUMNS + ["p_risk"]
    assert t["capacity_pressure"].all() and (t["p_risk"] == 0.25).all()


def test_default_capacity_pressure_false():
    t = simulate(MICRO, RoundRobinPolicy(), specs=SMALL).tasks
    assert not t["capacity_pressure"].any()


def test_empty_task_list():
    res = simulate((), RoundRobinPolicy(), specs=SMALL)
    assert res.n_ticks == 0 and res.drained and res.tasks.empty
