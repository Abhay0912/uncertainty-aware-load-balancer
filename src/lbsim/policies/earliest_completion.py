"""Task-aware earliest predicted completion-time policy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from lbsim.estimators.service_time import ServiceTimeEstimator
from lbsim.forecasting.queue_projection import Prediction, predict_completion
from lbsim.policies.base import Policy
from lbsim.scheduling_view import ServerView, TaskRequest

if TYPE_CHECKING:
    from lbsim.workload import Task


class EarliestCompletionPolicy(Policy):
    name = "ect_only"

    def __init__(self, estimator: ServiceTimeEstimator | None = None, horizon: int = 100_000) -> None:
        self.estimator = estimator or ServiceTimeEstimator()
        self.horizon = horizon
        self._info: dict[str, float | bool | int] = {}
        self._predictions: dict[int, float] = {}

    def reset(self) -> None:
        self.estimator.reset()
        self._info = {}
        self._predictions = {}

    def _predict(self, servers: Sequence[ServerView], task: TaskRequest, now: int) -> list[Prediction]:
        work = self.estimator.estimate(task)  # type: ignore[arg-type]
        return [
            predict_completion(s, task, now, self.estimator, candidate_work=work, horizon=self.horizon)
            for s in servers
        ]

    def select(self, servers: Sequence[ServerView], task: TaskRequest) -> int:
        preds = self._predict(servers, task, task.arrival_tick)
        feasible = [i for i, p in enumerate(preds) if p.status != "infeasible"]
        if not feasible:
            raise ValueError(f"task {task.id} fits on no server")
        best = min(feasible, key=lambda i: (preds[i].response_time, i))
        self._predictions[task.id] = preds[best].response_time
        self._info = {
            "predicted_ect_s": preds[best].response_time,
            "prediction_status": preds[best].status,
            "projection_steps": preds[best].steps,
            "jobs_ahead": preds[best].jobs_ahead,
            "prediction_confidence": self.estimator.prediction_confidence(task),  # type: ignore[arg-type]
        }
        return best

    def decision_info(self) -> Mapping[str, float | bool | int | str]:
        return dict(self._info)

    def observe_completion(self, task: "Task", server_id: int, service_ticks: int, speed: float) -> None:
        self.estimator.observe(task, service_ticks, speed)
