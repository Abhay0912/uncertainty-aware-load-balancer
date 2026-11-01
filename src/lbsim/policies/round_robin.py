"""Round Robin: servers 0, 1, ..., N-1 in a repeating cycle, ignoring load and capacity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from lbsim.policies.base import Policy

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class RoundRobinPolicy(Policy):
    name = "round_robin"

    def __init__(self) -> None:
        self._next = 0

    def reset(self) -> None:
        self._next = 0

    def select(self, servers: Sequence[Server], task: Task) -> int:
        choice = self._next % len(servers)
        self._next = choice + 1
        return choice
