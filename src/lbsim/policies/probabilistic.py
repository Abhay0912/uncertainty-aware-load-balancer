"""Uncertainty-aware probabilistic policy (spec sections 3.2-3.3): lowest S_i = w_L*L_i + w_R*P_risk_i
among servers whose P_risk is within the admission threshold; if none is, lowest S_i overall
and the decision is flagged as capacity pressure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from lbsim.config import SCORING, ScoringConfig
from lbsim.policies.base import Policy, argmin_first
from lbsim.scoring import risk_adjusted_score, server_load_score, server_risk

if TYPE_CHECKING:
    from lbsim.server import Server
    from lbsim.workload import Task


class ProbabilisticPolicy(Policy):
    name = "probabilistic"

    def __init__(self, cfg: ScoringConfig = SCORING) -> None:
        self.cfg = cfg
        self._info: dict[str, float | bool] = {}

    def reset(self) -> None:
        self._info = {}

    def select(self, servers: Sequence[Server], task: Task) -> int:
        risks = [server_risk(s, self.cfg) for s in servers]
        scores = [
            risk_adjusted_score(server_load_score(s, self.cfg), r.p_risk, self.cfg)
            for s, r in zip(servers, risks)
        ]
        threshold = self.cfg.risk_admission_threshold
        eligible = [i for i, r in enumerate(risks) if r.p_risk <= threshold]
        pressure = not eligible
        candidates = eligible or list(range(len(servers)))
        best = candidates[argmin_first([scores[i] for i in candidates])]
        self._info = {
            "p_risk": risks[best].p_risk,
            "p_cpu": risks[best].p_cpu,
            "p_mem": risks[best].p_mem,
            "score": scores[best],
            "n_eligible": len(eligible),
            "capacity_pressure": pressure,
        }
        return best

    def decision_info(self) -> Mapping[str, float | bool]:
        return dict(self._info)
