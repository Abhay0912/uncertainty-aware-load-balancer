"""Abstract base class every load-balancing policy implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Sequence

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
