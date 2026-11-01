"""Weighted metric (risk-free): lowest L_i. The key ablation, i.e. the probabilistic policy without P_risk."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from lbsim.config import SCORING, ScoringConfig
from lbsim.policies.base import Policy, argmin_first
from lbsim.scoring import server_load_score

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class WeightedMetricPolicy(Policy):
    name = "weighted_metric"

    def __init__(self, cfg: ScoringConfig = SCORING) -> None:
        self.cfg = cfg

    def select(self, servers: Sequence[Server], task: Task) -> int:
        return argmin_first([server_load_score(s, self.cfg) for s in servers])
