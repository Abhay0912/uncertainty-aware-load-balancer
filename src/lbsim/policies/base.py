"""Abstract base class every load-balancing policy implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Mapping, Sequence

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
