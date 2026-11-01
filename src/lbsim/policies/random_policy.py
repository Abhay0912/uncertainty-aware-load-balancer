"""Random: uniform over the servers the task can ever fit on."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from lbsim.policies.base import RandomizedPolicy

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class RandomPolicy(RandomizedPolicy):
    name = "random"

    def select(self, servers: Sequence[Server], task: Task) -> int:
        eligible = [i for i, s in enumerate(servers) if s.can_ever_fit(task)]
        if not eligible:
            raise ValueError(f"task {task.id} fits on no server")
        return eligible[int(self._rng.integers(len(eligible)))]
