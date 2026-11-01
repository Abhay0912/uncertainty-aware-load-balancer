"""Least CPU: the server with the lowest current observed CPU % (running + queued demand, D19)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from lbsim.policies.base import Policy, argmin_first

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class LeastCPUPolicy(Policy):
    name = "least_cpu"

    def select(self, servers: Sequence[Server], task: Task) -> int:
        return argmin_first([s.cpu_signal for s in servers])
