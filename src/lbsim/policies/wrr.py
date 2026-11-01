"""Weighted Round Robin, smooth variant (nginx): server i gets exactly w_i of every sum(w) picks,
interleaved rather than in blocks. Weights are fixed before the run (cores x speed, decision D8)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from lbsim.config import WRR_WEIGHTS
from lbsim.policies.base import Policy, argmin_first

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class WeightedRoundRobinPolicy(Policy):
    name = "wrr"

    def __init__(self, weights: Sequence[float] = WRR_WEIGHTS) -> None:
        if not weights or any(w <= 0 for w in weights):
            raise ValueError(f"WRR weights must be positive, got {tuple(weights)}")
        self.weights = tuple(float(w) for w in weights)
        self._total = sum(self.weights)
        self._current = [0.0] * len(self.weights)

    def reset(self) -> None:
        self._current = [0.0] * len(self.weights)

    def select(self, servers: Sequence[Server], task: Task) -> int:
        if len(servers) != len(self.weights):
            raise ValueError(f"{len(self.weights)} WRR weights for {len(servers)} servers")
        for i, w in enumerate(self.weights):
            self._current[i] += w
        choice = argmin_first([-c for c in self._current])
        self._current[choice] -= self._total
        return choice
