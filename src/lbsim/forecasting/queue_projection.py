"""Exact, local FIFO shadow projection matching Server's tick model."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from lbsim.estimators.service_time import ServiceTimeEstimator
from lbsim.scheduling_view import ServerView, TaskRequest


@dataclass(frozen=True, slots=True)
class Prediction:
    response_time: float
    start_tick: int | None
    finish_tick: int | None
    status: str
    jobs_ahead: int
    steps: int


@dataclass(slots=True)
class _Run:
    task_id: int
    cpu: float
    mem: float
    remaining: float
    start_tick: int | None = None


def predict_completion(
    server: ServerView,
    candidate: TaskRequest,
    now: int,
    estimator: ServiceTimeEstimator,
    *,
    candidate_work: float | None = None,
    horizon: int = 100_000,
) -> Prediction:
    if not candidate.can_fit(server.cores, server.mem_gb):
        return Prediction(float("inf"), None, None, "infeasible", 0, 0)
    running = [
        _Run(r.id, r.cpu_demand, r.mem_demand,
             estimator.remaining_work(r, server.speed))
        for r in server.running
    ]
    queue = [
        _Run(q.id, q.cpu_demand, q.mem_demand,
             q.estimated_work if q.estimated_work > 0 else estimator.prior)
        for q in server.queue
    ]
    candidate_run = _Run(
        candidate.id, candidate.cpu_demand, candidate.mem_demand,
        candidate_work if candidate_work is not None else (
            candidate.estimated_work if candidate.estimated_work and candidate.estimated_work > 0
            else estimator.prior
        ),
    )
    queue.append(candidate_run)
    ahead = len(queue) - 1
    steps = 0

    def start_queued(tick: int) -> None:
        while queue:
            head = queue[0]
            used_cpu = sum(r.cpu for r in running)
            used_mem = sum(r.mem for r in running)
            if used_cpu + head.cpu > server.cores or used_mem + head.mem > server.mem_gb:
                break
            queue.pop(0)
            head.start_tick = tick
            running.append(head)

    start_queued(now)
    if candidate_run.start_tick is not None and candidate_run.remaining <= 0:
        return Prediction(0.0, now, now, "predicted", ahead, 0)

    for tick in range(now, now + horizon):
        steps += 1
        finished = []
        for run in running:
            run.remaining -= server.speed
            if run.remaining <= 0:
                finished.append(run)
        for run in finished:
            running.remove(run)
        if candidate_run in finished:
            finish = tick + 1
            return Prediction(
                finish - candidate.arrival_tick, candidate_run.start_tick, finish,
                "predicted", ahead, steps,
            )
        start_queued(tick + 1)
    return Prediction(float("inf"), candidate_run.start_tick, None, "horizon_exceeded", ahead, steps)
