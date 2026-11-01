"""Pure scoring formulas shared by policies (spec sections 3.2-3.3): L_i, P_C, P_M, P_risk, S_i."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lbsim.config import SCORING, ScoringConfig

if TYPE_CHECKING:
    from lbsim.server import Server


def normalised_response(mean_response: float, r_ref: float) -> float:
    """r = R-bar / (R-bar + R_ref), in [0, 1). R-bar = 0 (no completions yet) gives 0."""
    if r_ref <= 0:
        raise ValueError("r_ref must be > 0")
    if mean_response < 0:
        raise ValueError("mean_response must be >= 0")
    return mean_response / (mean_response + r_ref)


def load_score(
    cpu_pct: float, mem_pct: float, mean_response: float, cfg: ScoringConfig = SCORING
) -> float:
    """L = w_c * C/100 + w_m * M/100 + w_r * r."""
    w_cpu, w_mem, w_resp = cfg.load_weights
    r = normalised_response(mean_response, cfg.r_ref)
    return w_cpu * cpu_pct / 100.0 + w_mem * mem_pct / 100.0 + w_resp * r


def server_load_score(server: Server, cfg: ScoringConfig = SCORING) -> float:
    """L_i from the live observed CPU/memory signal (D16, D19) and the windowed mean response time."""
    return load_score(server.cpu_signal, server.mem_signal, server.mean_response_time, cfg)


def normal_cdf(z: float) -> float:
    """Standard normal CDF via erf (D2)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def exceedance_probability(mu: float, sigma: float, theta: float) -> float:
    """P(X > theta) for X ~ N(mu, sigma^2). sigma = 0 is a point mass: 1 if mu > theta else 0 (D6)."""
    if sigma < 0:
        raise ValueError("sigma must be >= 0")
    if sigma == 0:
        return 1.0 if mu > theta else 0.0
    return 1.0 - normal_cdf((theta - mu) / sigma)


def combined_risk(p_cpu: float, p_mem: float) -> float:
    """P_risk = 1 - (1 - P_C)(1 - P_M): probability that at least one resource exceeds (independence assumed)."""
    for p in (p_cpu, p_mem):
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"probabilities must be in [0, 1], got {p}")
    return 1.0 - (1.0 - p_cpu) * (1.0 - p_mem)


def risk_adjusted_score(load: float, p_risk: float, cfg: ScoringConfig = SCORING) -> float:
    """S = w_load * L + w_risk * P_risk."""
    w_load, w_risk = cfg.score_weights
    return w_load * load + w_risk * p_risk


@dataclass(frozen=True, slots=True)
class ServerRisk:
    p_cpu: float
    p_mem: float
    p_risk: float


def server_risk(server: Server, cfg: ScoringConfig = SCORING) -> ServerRisk:
    """Overload risk from the rolling windows of past observed samples (spec 3.2). Empty windows give 0."""
    p_cpu = exceedance_probability(server.cpu_window.mean(), server.cpu_window.std(), cfg.theta_cpu)
    p_mem = exceedance_probability(server.mem_window.mean(), server.mem_window.std(), cfg.theta_mem)
    return ServerRisk(p_cpu, p_mem, combined_risk(p_cpu, p_mem))
