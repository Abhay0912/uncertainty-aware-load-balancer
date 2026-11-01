import numpy as np
import pytest

from lbsim.config import SERVERS, WORKLOAD
from lbsim.workload import (
    arrival_rate,
    base_rate,
    burst_mask,
    generate_workload,
)

KINDS = ["stable", "bursty"]
CAPACITY = sum(s.cores * s.speed for s in SERVERS)


@pytest.mark.parametrize("kind", KINDS)
def test_same_seed_is_identical(kind):
    assert generate_workload(kind, 7).tasks == generate_workload(kind, 7).tasks


@pytest.mark.parametrize("kind", KINDS)
def test_different_seed_differs(kind):
    assert generate_workload(kind, 1).tasks != generate_workload(kind, 2).tasks


def test_global_numpy_state_unused():
    np.random.seed(0)
    a = generate_workload("bursty", 3).tasks
    np.random.seed(999)
    assert generate_workload("bursty", 3).tasks == a


@pytest.mark.parametrize("kind", KINDS)
def test_task_invariants(kind):
    tasks = generate_workload(kind, 0).tasks
    assert [t.id for t in tasks] == list(range(len(tasks)))
    ticks = [t.arrival_tick for t in tasks]
    assert ticks == sorted(ticks)
    assert 0 <= ticks[0] and ticks[-1] < WORKLOAD.t_sim
    max_cpu = WORKLOAD.cpu_high * WORKLOAD.burst_cpu_mult
    assert all(WORKLOAD.cpu_low <= t.cpu_demand <= max_cpu for t in tasks)
    assert all(WORKLOAD.mem_low <= t.mem_demand <= WORKLOAD.mem_high for t in tasks)
    assert all(t.work >= WORKLOAD.work_min for t in tasks)


def test_stable_has_no_bursts_and_no_inflated_cpu():
    w = generate_workload("stable", 0)
    assert w.bursts == ()
    assert max(t.cpu_demand for t in w.tasks) <= WORKLOAD.cpu_high


@pytest.mark.parametrize("seed", range(5))
def test_bursts_non_overlapping_and_in_horizon(seed):
    bursts = generate_workload("bursty", seed).bursts
    assert len(bursts) == WORKLOAD.n_bursts
    for (s1, e1), (s2, _) in zip(bursts, bursts[1:]):
        assert e1 <= s2
    assert all(0 <= s < e <= WORKLOAD.t_sim and e - s == WORKLOAD.burst_length for s, e in bursts)


def test_burst_cpu_only_inflated_inside_bursts():
    w = generate_workload("bursty", 0)
    mask = burst_mask(WORKLOAD.t_sim, w.bursts)
    outside = [t.cpu_demand for t in w.tasks if not mask[t.arrival_tick]]
    assert max(outside) <= WORKLOAD.cpu_high


def test_bursty_peak_exceeds_stable_peak():
    s, b = generate_workload("stable", 0), generate_workload("bursty", 0)
    assert b.rate_per_tick.max() > s.rate_per_tick.max()
    assert b.rate_per_tick.min() < s.rate_per_tick.min()


def test_stable_rate_hits_target_utilisation():
    rate = arrival_rate("stable", WORKLOAD, base_rate(WORKLOAD, SERVERS), ())
    mean_cpu = (WORKLOAD.cpu_low + WORKLOAD.cpu_high) / 2
    load = rate.mean() * mean_cpu * WORKLOAD.work_mean / CAPACITY
    assert load == pytest.approx(WORKLOAD.target_utilisation, rel=1e-9)


def _offered_load(kind: str) -> float:
    per_seed = []
    for seed in range(5):
        tasks = generate_workload(kind, seed).tasks
        per_seed.append(sum(t.cpu_demand * t.work for t in tasks) / WORKLOAD.t_sim / CAPACITY)
    return float(np.mean(per_seed))


def test_stable_and_bursty_have_matched_mean_load():
    stable, bursty = _offered_load("stable"), _offered_load("bursty")
    assert stable == pytest.approx(WORKLOAD.target_utilisation, rel=0.05)
    assert bursty == pytest.approx(stable, rel=0.10)


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        generate_workload("spiky", 0)
