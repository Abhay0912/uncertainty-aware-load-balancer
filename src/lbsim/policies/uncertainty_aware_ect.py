"""Soft-tail-risk completion-time policy (V2)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

import numpy as np

from lbsim.config import V2Config
from lbsim.estimators.service_time import ServiceTimeEstimator
from lbsim.forecasting.queue_projection import Prediction, predict_completion
from lbsim.policies.earliest_completion import EarliestCompletionPolicy
from lbsim.scheduling_view import ServerView, TaskRequest

if TYPE_CHECKING:
    from lbsim.workload import Task


class UncertaintyAwareECTPolicy(EarliestCompletionPolicy):
    name = "uncertainty_ect"

    def __init__(
        self,
        estimator: ServiceTimeEstimator | None = None,
        cfg: V2Config = V2Config(),
    ) -> None:
        super().__init__(estimator, cfg.projection_horizon)
        self.cfg = cfg

    def select(self, servers: Sequence[ServerView], task: TaskRequest) -> int:
        work_distribution = self.estimator.distribution(task)  # type: ignore[arg-type]
        mean_work = float(np.mean(work_distribution))
        predictions: list[list[Prediction]] = []
        for server in servers:
            predictions.append([
                predict_completion(
                    server, task, task.arrival_tick, self.estimator,
                    candidate_work=work, horizon=self.horizon,
                )
                for work in work_distribution
            ])
        costs: list[float] = []
        means: list[float] = []
        q90s: list[float] = []
        feasible: list[int] = []
        for i, samples in enumerate(predictions):
            valid = [p.response_time for p in samples if p.status != "infeasible"]
            if not valid:
                costs.append(float("inf")); means.append(float("inf")); q90s.append(float("inf"))
                continue
            mean, q90 = float(np.mean(valid)), float(np.quantile(valid, 0.9))
            means.append(mean); q90s.append(q90)
            costs.append(mean + self.cfg.beta * max(0.0, q90 - mean))
            feasible.append(i)
        if not feasible:
            raise ValueError(f"task {task.id} fits on no server")
        best = min(feasible, key=lambda i: (costs[i], means[i], i))
        self._predictions[task.id] = means[best]
        self._info = {
            "predicted_ect_s": means[best],
            "predicted_q90_s": q90s[best],
            "ect_cost_s": costs[best],
            "uncertainty_premium_s": max(0.0, q90s[best] - means[best]),
            "prediction_status": predictions[best][0].status,
            "projection_steps": max(p.steps for p in predictions[best]),
            "jobs_ahead": predictions[best][0].jobs_ahead,
            "prediction_confidence": self.estimator.prediction_confidence(task),  # type: ignore[arg-type]
        }
        return best
