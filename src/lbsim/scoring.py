"""Pure scoring formulas shared by policies (spec section 3.3). Phase 5 adds the risk terms here."""

from __future__ import annotations

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
    """L_i from live CPU/memory % and the windowed mean response time (decision D16)."""
    return load_score(server.cpu_pct, server.mem_pct, server.mean_response_time, cfg)
