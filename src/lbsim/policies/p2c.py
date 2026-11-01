"""Power of Two Choices: sample two distinct servers uniformly, keep the one with the lower L_i."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

import numpy as np

from lbsim.config import SCORING, ScoringConfig
from lbsim.policies.base import RandomizedPolicy
from lbsim.scoring import server_load_score

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class PowerOfTwoChoicesPolicy(RandomizedPolicy):
    name = "p2c"

    def __init__(self, rng: np.random.Generator, cfg: ScoringConfig = SCORING) -> None:
        super().__init__(rng)
        self.cfg = cfg

    def select(self, servers: Sequence[Server], task: Task) -> int:
        if len(servers) == 1:
            return 0
        a, b = (int(i) for i in self._rng.choice(len(servers), size=2, replace=False))
        score_a = server_load_score(servers[a], self.cfg)
        score_b = server_load_score(servers[b], self.cfg)
        return b if score_b < score_a else a
