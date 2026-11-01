import math

import pytest

from lbsim.config import SCORING, SERVERS, ServerSpec
from lbsim.server import Server, build_servers
from lbsim.workload import Task, generate_workload


def make_task(i=0, arrival=0, cpu=1.0, mem=1.0, work=1.0):
    return Task(id=i, arrival_tick=arrival, cpu_demand=cpu, mem_demand=mem, work=work)


def run_until_idle(server, start_tick=0, limit=10_000):
    done, tick = [], start_tick
    while not server.is_idle():
        done += server.step(tick)
        tick += 1
        assert tick < limit
    return done


@pytest.mark.parametrize(
    "work, speed",
    [(1.0, 1.0), (3.0, 1.5), (1.0, 0.5), (6.3, 2.0), (2.5, 1.0)],
)
def test_runtime_is_work_over_speed_rounded_up(work, speed):
    s = Server(0, ServerSpec(cores=4, mem_gb=8, speed=speed))
    run = s.assign(make_task(work=work), tick=0)
    run_until_idle(s)
    assert run.start_tick == 0
    assert run.finish_tick == math.ceil(work / speed)
    assert run.response_time == math.ceil(work / speed)


def test_response_time_includes_queue_wait():
    s = Server(0, ServerSpec(cores=2, mem_gb=4, speed=0.5))
    a = s.assign(make_task(0, cpu=1.5, work=1.0), tick=0)
    b = s.assign(make_task(1, cpu=1.5, work=1.0), tick=0)
    assert (s.n_running, s.queue_length) == (1, 1)
    run_until_idle(s)
    assert a.finish_tick == 2
    assert b.start_tick == 2 and b.finish_tick == 4
    assert b.response_time == 4.0


def test_response_time_measured_from_arrival_not_assignment():
    s = Server(0, ServerSpec(cores=4, mem_gb=8, speed=1.0))
    run = s.assign(make_task(arrival=5, work=2.0), tick=7)
    run_until_idle(s, start_tick=7)
    assert run.finish_tick == 9
    assert run.response_time == 4.0


def test_memory_also_limits_admission():
    s = Server(0, ServerSpec(cores=8, mem_gb=4, speed=1.0))
    s.assign(make_task(0, cpu=0.5, mem=3.0), tick=0)
    s.assign(make_task(1, cpu=0.5, mem=3.0), tick=0)
    assert (s.n_running, s.queue_length) == (1, 1)


def test_strict_fifo_no_overtaking():
    s = Server(0, ServerSpec(cores=2, mem_gb=8, speed=1.0))
    s.assign(make_task(0, cpu=1.5, work=1.0), tick=0)
    big = s.assign(make_task(1, cpu=1.5, work=1.0), tick=0)
    small = s.assign(make_task(2, cpu=0.5, work=1.0), tick=0)
    assert small.start_tick is None
    run_until_idle(s)
    assert big.start_tick <= small.start_tick


def test_utilisation_percentages():
    s = Server(0, ServerSpec(cores=4, mem_gb=8, speed=1.0))
    s.assign(make_task(0, cpu=1.0, mem=2.0), tick=0)
    s.assign(make_task(1, cpu=2.0, mem=4.0), tick=0)
    assert s.cpu_pct == pytest.approx(75.0)
    assert s.mem_pct == pytest.approx(75.0)
    s.sample()
    assert s.cpu_window.latest() == pytest.approx(75.0)
    assert s.mem_window.latest() == pytest.approx(75.0)


def test_capacity_never_exceeded_and_everything_drains():
    tasks = generate_workload("bursty", 0).tasks[:400]
    s = Server(4, SERVERS[4])
    runs, finished, tick = [], [], 0
    for task in tasks:
        while tick < task.arrival_tick:
            finished += s.step(tick)
            s.sample()
            tick += 1
        runs.append(s.assign(task, tick))
        assert 0.0 <= s.cpu_pct <= 100.0 + 1e-9
        assert 0.0 <= s.mem_pct <= 100.0 + 1e-9
    finished += run_until_idle(s, start_tick=tick)
    assert len(finished) == len(tasks) == s.completed
    assert all(r.finish_tick is not None for r in runs)
    assert max(s.cpu_window.values()) <= 100.0 + 1e-9


def test_response_window_keeps_last_w_completions():
    s = Server(0, ServerSpec(cores=100, mem_gb=100, speed=1.0), window=3)
    for i, work in enumerate([1.0, 2.0, 3.0, 4.0, 5.0]):
        s.assign(make_task(i, work=work), tick=0)
    run_until_idle(s)
    assert s.resp_window.values() == (3.0, 4.0, 5.0)
    assert s.mean_response_time == 4.0


def test_no_completions_means_zero_mean_response():
    s = Server(0, SERVERS[0])
    assert s.mean_response_time == 0.0


def test_task_that_never_fits_is_rejected():
    s = Server(0, ServerSpec(cores=2, mem_gb=4, speed=1.0))
    with pytest.raises(ValueError):
        s.assign(make_task(cpu=3.0), tick=0)


def test_unfinished_response_time_raises():
    s = Server(0, SERVERS[0])
    run = s.assign(make_task(work=5.0), tick=0)
    with pytest.raises(ValueError):
        _ = run.response_time


def test_build_servers_fresh_and_independent():
    a, b = build_servers(), build_servers()
    assert [s.id for s in a] == list(range(len(SERVERS)))
    assert [s.spec for s in a] == list(SERVERS)
    assert all(s.cpu_window.size == SCORING.window for s in a)
    a[0].assign(make_task(), tick=0)
    a[0].sample()
    assert b[0].is_idle() and len(b[0].cpu_window) == 0
