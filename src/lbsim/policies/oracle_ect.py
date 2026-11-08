"""Non-deployable diagnostic policy using the task's hidden exact work."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from lbsim.estimators.service_time import ServiceTimeEstimator
from lbsim.forecasting.queue_projection import predict_completion
from lbsim.policies.base import Policy
from lbsim.scheduling_view import ServerView, TaskRequest

if TYPE_CHECKING:
    from lbsim.workload import Task


class OracleECTPolicy(Policy):
    name = "oracle_ect"

    def select(self, servers: Sequence[ServerView], task: TaskRequest) -> int:
        # Simulator intentionally supplies only a safe request; use this policy only
        # through oracle_select, never in the practical policy matrix.
        raise RuntimeError("OracleECTPolicy requires the isolated oracle diagnostic path")


def oracle_select(servers: Sequence[ServerView], task: "Task", now: int) -> int:
    estimator = ServiceTimeEstimator(prior=task.work)
    request = TaskRequest(task.id, task.arrival_tick, task.cpu_demand, task.mem_demand,
                          task.task_class, task.work)
    predictions = [
        predict_completion(s, request, now, estimator, candidate_work=task.work)
        for s in servers
    ]
    feasible = [i for i, p in enumerate(predictions) if p.status != "infeasible"]
    if not feasible:
        raise ValueError(f"task {task.id} fits on no server")
    return min(feasible, key=lambda i: (predictions[i].response_time, i))
