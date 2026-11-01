"""All tunable parameters. Values come from docs/spec.md section 8; choices are logged in docs/decisions.md.

Units: 1 tick = 1 second. CPU demand in cores, memory in GB, work in seconds on a speed-1.0 server.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _check_weights(name: str, weights: tuple[float, ...]) -> None:
    if any(w < 0 for w in weights) or not math.isclose(sum(weights), 1.0):
        raise ValueError(f"{name} must be non-negative and sum to 1, got {weights}")


@dataclass(frozen=True)
class ServerSpec:
    cores: float
    mem_gb: float
    speed: float

    def __post_init__(self) -> None:
        if self.cores <= 0 or self.mem_gb <= 0 or self.speed <= 0:
            raise ValueError(f"server capacities must be positive: {self}")


@dataclass(frozen=True)
class WorkloadConfig:
    t_sim: int = 1000
    target_utilisation: float = 0.65

    cpu_low: float = 0.5
    cpu_high: float = 1.5
    mem_low: float = 0.5
    mem_high: float = 3.0
    work_mean: float = 6.0
    work_sigma: float = 0.6
    work_min: float = 1.0

    drift_amplitude: float = 0.2
    drift_period: int = 500

    n_bursts: int = 4
    burst_length: int = 50
    burst_rate_mult: float = 3.0
    burst_cpu_mult: float = 1.3

    def __post_init__(self) -> None:
        if self.t_sim <= 0 or self.drift_period <= 0:
            raise ValueError("t_sim and drift_period must be positive")
        if not 0 < self.target_utilisation < 1:
            raise ValueError("target_utilisation must be in (0, 1)")
        if not (0 < self.cpu_low <= self.cpu_high and 0 < self.mem_low <= self.mem_high):
            raise ValueError("demand bounds must satisfy 0 < low <= high")
        if not 0 < self.work_min < self.work_mean or self.work_sigma <= 0:
            raise ValueError("need 0 < work_min < work_mean and work_sigma > 0")
        if not 0 <= self.drift_amplitude < 1:
            raise ValueError("drift_amplitude must be in [0, 1) so the rate stays positive")
        if self.n_bursts < 0 or self.burst_length <= 0:
            raise ValueError("n_bursts must be >= 0 and burst_length > 0")
        if self.n_bursts * self.burst_length > self.t_sim:
            raise ValueError("bursts do not fit in the horizon")
        if self.burst_rate_mult < 1 or self.burst_cpu_mult < 1:
            raise ValueError("burst multipliers must be >= 1")

    @property
    def burst_fraction(self) -> float:
        return self.n_bursts * self.burst_length / self.t_sim


@dataclass(frozen=True)
class ScoringConfig:
    window: int = 10
    theta_cpu: float = 80.0
    theta_mem: float = 85.0
    load_weights: tuple[float, float, float] = (0.4, 0.4, 0.2)
    score_weights: tuple[float, float] = (0.6, 0.4)
    risk_admission_threshold: float = 0.5
    r_ref: float = 6.0
    count_queued: bool = True  # observed C/M include queued demand (D19); False = pure utilisation

    def __post_init__(self) -> None:
        if self.window < 1:
            raise ValueError("window must be >= 1")
        if self.theta_cpu <= 0 or self.theta_mem <= 0:
            raise ValueError("thresholds must be > 0")
        if not self.count_queued and max(self.theta_cpu, self.theta_mem) > 100:
            raise ValueError("utilisation signal is bounded by 100, so thresholds must be <= 100 (D25)")
        _check_weights("load_weights", self.load_weights)
        _check_weights("score_weights", self.score_weights)
        if not 0 <= self.risk_admission_threshold <= 1:
            raise ValueError("risk_admission_threshold must be in [0, 1]")
        if self.r_ref <= 0:
            raise ValueError("r_ref must be > 0")


@dataclass(frozen=True)
class ExperimentConfig:
    r_sla: float
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4)
    workloads: tuple[str, ...] = ("stable", "bursty")

    def __post_init__(self) -> None:
        if self.r_sla <= 0:
            raise ValueError("r_sla must be > 0")
        if not self.seeds:
            raise ValueError("need at least one seed")


@dataclass(frozen=True)
class SensitivityConfig:
    """One-at-a-time axes around the frozen SCORING defaults, plus a theta x admission grid (D26).
    theta values set theta_C; theta_M keeps its default offset above theta_C."""

    theta_cpu: tuple[float, ...] = (60.0, 80.0, 100.0, 120.0, 150.0)
    admission: tuple[float, ...] = (0.3, 0.5, 0.7, 0.9, 1.0)
    risk_weight: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8)
    window: tuple[int, ...] = (5, 10, 20, 40)
    timeseries_workload: str = "bursty"
    timeseries_seed: int = 0

    def __post_init__(self) -> None:
        if not all((self.theta_cpu, self.admission, self.risk_weight, self.window)):
            raise ValueError("every sensitivity axis needs at least one value")
        if any(not 0 <= w <= 1 for w in self.risk_weight):
            raise ValueError("risk weights must be in [0, 1]")


@dataclass(frozen=True)
class SimulationConfig:
    max_ticks: int = 200_000

    def __post_init__(self) -> None:
        if self.max_ticks < 1:
            raise ValueError("max_ticks must be >= 1")


def validate_fit(servers: tuple[ServerSpec, ...], workload: WorkloadConfig) -> None:
    """Every task (including burst-inflated CPU) must fit on the smallest server."""
    if workload.cpu_high * workload.burst_cpu_mult > min(s.cores for s in servers):
        raise ValueError("largest CPU demand exceeds the smallest server's cores")
    if workload.mem_high > min(s.mem_gb for s in servers):
        raise ValueError("largest memory demand exceeds the smallest server's memory")


SERVERS: tuple[ServerSpec, ...] = (
    ServerSpec(cores=4, mem_gb=8, speed=1.0),
    ServerSpec(cores=4, mem_gb=8, speed=1.0),
    ServerSpec(cores=8, mem_gb=16, speed=1.5),
    ServerSpec(cores=8, mem_gb=16, speed=2.0),
    ServerSpec(cores=2, mem_gb=4, speed=0.5),
)
N_SERVERS = len(SERVERS)
WRR_WEIGHTS: tuple[float, ...] = tuple(s.cores * s.speed for s in SERVERS)
POLICY_SEED_TAG = 7  # mixed into SeedSequence so policy draws never share a workload stream

WORKLOAD = WorkloadConfig()
SCORING = ScoringConfig(r_ref=WORKLOAD.work_mean)
EXPERIMENT = ExperimentConfig(r_sla=3.0 * WORKLOAD.work_mean)
SIMULATION = SimulationConfig()
SENSITIVITY = SensitivityConfig()

validate_fit(SERVERS, WORKLOAD)
