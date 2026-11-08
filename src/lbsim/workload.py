"""Seeded synthetic task generation for the stable and bursty workloads."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from lbsim.config import SERVERS, WORKLOAD, ServerSpec, WorkloadConfig

WorkloadKind = Literal["stable", "bursty", "heterogeneous"]
Interval = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Task:
    id: int
    arrival_tick: int
    cpu_demand: float
    mem_demand: float
    work: float
    task_class: str | None = None
    estimated_work: float | None = None


@dataclass(frozen=True, eq=False)
class Workload:
    kind: WorkloadKind
    seed: int
    tasks: tuple[Task, ...]
    rate_per_tick: np.ndarray
    bursts: tuple[Interval, ...]


def base_rate(cfg: WorkloadConfig, servers: tuple[ServerSpec, ...]) -> float:
    """Arrival rate giving cfg.target_utilisation of total cluster capacity on average."""
    capacity = sum(s.cores * s.speed for s in servers)
    mean_cpu = (cfg.cpu_low + cfg.cpu_high) / 2
    return cfg.target_utilisation * capacity / (mean_cpu * cfg.work_mean)


def bursty_baseline_scale(cfg: WorkloadConfig) -> float:
    """Scale on the bursty baseline so its mean offered load equals the stable workload's."""
    burst_load_mult = cfg.burst_rate_mult * cfg.burst_cpu_mult
    return 1.0 / (1.0 + cfg.burst_fraction * (burst_load_mult - 1.0))


def place_bursts(cfg: WorkloadConfig, rng: np.random.Generator) -> tuple[Interval, ...]:
    """One burst at a random offset inside each of n_bursts equal segments, so bursts never overlap."""
    if cfg.n_bursts == 0:
        return ()
    segment = cfg.t_sim // cfg.n_bursts
    offsets = rng.integers(0, segment - cfg.burst_length + 1, size=cfg.n_bursts)
    return tuple(
        (i * segment + int(off), i * segment + int(off) + cfg.burst_length)
        for i, off in enumerate(offsets)
    )


def burst_mask(t_sim: int, bursts: tuple[Interval, ...]) -> np.ndarray:
    mask = np.zeros(t_sim, dtype=bool)
    for start, end in bursts:
        mask[start:end] = True
    return mask


def arrival_rate(
    kind: WorkloadKind, cfg: WorkloadConfig, rate0: float, bursts: tuple[Interval, ...]
) -> np.ndarray:
    """Expected arrivals per tick: slow sinusoidal drift, plus rectangular bursts for 'bursty'."""
    t = np.arange(cfg.t_sim)
    rate = rate0 * (1.0 + cfg.drift_amplitude * np.sin(2 * math.pi * t / cfg.drift_period))
    if kind == "bursty":
        rate = rate * bursty_baseline_scale(cfg)
        rate[burst_mask(cfg.t_sim, bursts)] *= cfg.burst_rate_mult
    return rate


def generate_workload(
    kind: WorkloadKind,
    seed: int,
    cfg: WorkloadConfig = WORKLOAD,
    servers: tuple[ServerSpec, ...] = SERVERS,
) -> Workload:
    if kind not in ("stable", "bursty", "heterogeneous"):
        raise ValueError(f"unknown workload kind: {kind!r}")

    if kind == "heterogeneous":
        return _generate_heterogeneous(seed, cfg, servers)

    streams = np.random.SeedSequence(seed).spawn(5)
    burst_rng, arrival_rng, cpu_rng, mem_rng, work_rng = (np.random.default_rng(s) for s in streams)

    bursts = place_bursts(cfg, burst_rng) if kind == "bursty" else ()
    rate = arrival_rate(kind, cfg, base_rate(cfg, servers), bursts)

    arrivals = np.repeat(np.arange(cfg.t_sim), arrival_rng.poisson(rate))
    n = arrivals.size

    cpu = cpu_rng.uniform(cfg.cpu_low, cfg.cpu_high, n)
    cpu = np.where(burst_mask(cfg.t_sim, bursts)[arrivals], cpu * cfg.burst_cpu_mult, cpu)
    mem = mem_rng.uniform(cfg.mem_low, cfg.mem_high, n)
    log_mu = math.log(cfg.work_mean) - cfg.work_sigma**2 / 2
    work = np.maximum(work_rng.lognormal(log_mu, cfg.work_sigma, n), cfg.work_min)

    tasks = tuple(
        Task(id=i, arrival_tick=int(a), cpu_demand=float(c), mem_demand=float(m), work=float(w))
        for i, (a, c, m, w) in enumerate(zip(arrivals, cpu, mem, work))
    )
    return Workload(kind=kind, seed=seed, tasks=tasks, rate_per_tick=rate, bursts=bursts)


def _generate_heterogeneous(
    seed: int, cfg: WorkloadConfig, servers: tuple[ServerSpec, ...]
) -> Workload:
    """Matched-mean benchmark with visible job classes and noisy duration hints."""
    streams = np.random.SeedSequence([seed, 991]).spawn(5)
    arrival_rng, class_rng, resource_rng, work_rng, hint_rng = (
        np.random.default_rng(s) for s in streams
    )
    rate = arrival_rate("stable", cfg, base_rate(cfg, servers), ())
    arrivals = np.repeat(np.arange(cfg.t_sim), arrival_rng.poisson(rate))
    classes = np.array(("short", "medium", "long", "cpu_heavy", "memory_heavy"), dtype=object)
    task_classes = class_rng.choice(classes, size=arrivals.size, p=(0.30, 0.30, 0.15, 0.125, 0.125))
    means = {"short": 2.0, "medium": 6.0, "long": 14.0, "cpu_heavy": 7.0, "memory_heavy": 7.0}
    cpu = resource_rng.uniform(cfg.cpu_low, cfg.cpu_high, arrivals.size)
    mem = resource_rng.uniform(cfg.mem_low, cfg.mem_high, arrivals.size)
    cpu = np.where(task_classes == "cpu_heavy", np.minimum(cpu * 1.8, 1.9), cpu)
    mem = np.where(task_classes == "memory_heavy", np.minimum(mem * 1.8, 3.8), mem)
    log_sigma = cfg.work_sigma * 0.65
    work = np.array([
        max(cfg.work_min, float(work_rng.lognormal(math.log(means[c]) - log_sigma**2 / 2, log_sigma)))
        for c in task_classes
    ])
    hints = np.array([
        max(cfg.work_min, means[c] * float(hint_rng.lognormal(0.0, cfg.class_hint_noise)))
        for c in task_classes
    ])
    tasks = tuple(
        Task(
            id=i, arrival_tick=int(a), cpu_demand=float(c), mem_demand=float(m),
            work=float(w), task_class=str(cls), estimated_work=float(h),
        )
        for i, (a, c, m, w, cls, h) in enumerate(zip(
            arrivals, cpu, mem, work, task_classes, hints
        ))
    )
    return Workload(kind="heterogeneous", seed=seed, tasks=tasks, rate_per_tick=rate, bursts=())
