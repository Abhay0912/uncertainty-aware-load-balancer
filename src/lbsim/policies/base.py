"""Abstract base class every load-balancing policy implements."""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np

from lbsim.config import POLICY_SEED_TAG

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class Policy(ABC):
    """Chooses a server for each task. Must only read server state, never modify it."""

    name: str = "base"

    def reset(self) -> None:
        """Clear any internal state (e.g. a round-robin pointer) before a new run."""

    @abstractmethod
    def select(self, servers: Sequence[Server], task: Task) -> int:
        """Return the index of the server that should receive `task`."""

    def decision_info(self) -> Mapping[str, float | bool]:
        """Extra fields about the last decision to log with the task (e.g. p_risk, capacity_pressure)."""
        return {}

    def observe_completion(self, task: "Task", server_id: int, service_ticks: int, speed: float) -> None:
        """Receive post-completion data; practical policies never see it before dispatch."""


class RandomizedPolicy(Policy):
    """Owns a seeded Generator; reset() rewinds it so repeated runs make the same draws."""

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng
        self._initial_state: dict[str, Any] = copy.deepcopy(rng.bit_generator.state)

    def reset(self) -> None:
        self._rng.bit_generator.state = copy.deepcopy(self._initial_state)


def policy_rng(seed: int) -> np.random.Generator:
    """Generator for a policy's own draws, independent of the workload's SeedSequence(seed) streams."""
    return np.random.default_rng(np.random.SeedSequence([POLICY_SEED_TAG, seed]))


def argmin_first(values: Sequence[float]) -> int:
    """Index of the smallest value; ties go to the lowest index, so choices are deterministic."""
    return min(range(len(values)), key=values.__getitem__)
