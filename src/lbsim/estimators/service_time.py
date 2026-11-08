"""Prequential task-class service-time estimates."""

from __future__ import annotations

from collections import defaultdict
from math import ceil

import numpy as np

from lbsim.config import WORKLOAD
from lbsim.workload import Task


class ServiceTimeEstimator:
    """Estimates speed-1 work using only public metadata and completed tasks."""

    def __init__(self, prior: float = WORKLOAD.work_mean, max_samples: int = 200) -> None:
        if prior <= 0 or max_samples < 1:
            raise ValueError("prior must be positive and max_samples must be >= 1")
        self.prior = float(prior)
        self.max_samples = max_samples
        self._samples: dict[str | None, list[float]] = defaultdict(list)

    def reset(self) -> None:
        self._samples.clear()

    def estimate(self, task: Task, rng: np.random.Generator | None = None) -> float:
        if task.estimated_work is not None:
            return max(float(task.estimated_work), WORKLOAD.work_min)
        values = self._samples.get(task.task_class, [])
        if values:
            return float(np.mean(values))
        pooled = [x for group in self._samples.values() for x in group]
        return float(np.mean(pooled)) if pooled else self.prior

    def distribution(self, task: Task) -> tuple[float, ...]:
        values = self._samples.get(task.task_class, [])
        if values:
            return tuple(values)
        pooled = tuple(x for group in self._samples.values() for x in group)
        return pooled or (self.prior,)

    def observe(self, task: Task, service_ticks: int, speed: float) -> None:
        if service_ticks < 1 or speed <= 0:
            raise ValueError("service_ticks must be positive and speed must be positive")
        values = self._samples[task.task_class]
        values.append(float(service_ticks * speed))
        del values[:-self.max_samples]

    def remaining_work(self, active, speed: float) -> float:
        """Conservative lower bound; an active job is never treated as completed."""
        expected = active.estimated_total_work if active.estimated_total_work > 0 else self.prior
        processed = active.elapsed_ticks * speed
        return max(expected - processed, speed)

    def prediction_confidence(self, task: Task) -> int:
        return len(self._samples.get(task.task_class, ()))

    @staticmethod
    def processing_ticks(work: float, speed: float) -> int:
        return max(1, ceil(work / speed))
