"""Simulated heterogeneous server: capacity, running tasks, FIFO queue, utilisation and response time.

Tick semantics (1 tick = 1 s): a task that starts at tick t is processed during tick t and, if done,
finishes at the end of it (finish_tick = t + 1). Response time = finish_tick - arrival_tick.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from lbsim.config import SCORING, SERVERS, ServerSpec
from lbsim.metric_window import MetricWindow
from lbsim.workload import Task


@dataclass(slots=True)
class TaskRun:
    task: Task
    server_id: int
    assigned_tick: int
    remaining: float
    start_tick: int | None = None
    finish_tick: int | None = None

    @property
    def response_time(self) -> float:
        if self.finish_tick is None:
            raise ValueError(f"task {self.task.id} has not finished")
        return float(self.finish_tick - self.task.arrival_tick)


class Server:
    """cpu_pct/mem_pct: true utilisation, bounded to [0, 100], used for evaluation.
    cpu_load_pct/mem_load_pct: running + queued demand (can exceed 100).
    cpu_signal/mem_signal: what the balancer observes and the windows record (D19)."""

    def __init__(
        self,
        server_id: int,
        spec: ServerSpec,
        window: int = SCORING.window,
        count_queued: bool = SCORING.count_queued,
    ) -> None:
        self.id = server_id
        self.spec = spec
        self.count_queued = count_queued
        self._running: list[TaskRun] = []
        self._queue: deque[TaskRun] = deque()
        self._queued_cpu = 0.0
        self._queued_mem = 0.0
        self.cpu_window = MetricWindow(window)
        self.mem_window = MetricWindow(window)
        self.resp_window = MetricWindow(window)
        self.completed = 0

    @property
    def cpu_used(self) -> float:
        return sum(r.task.cpu_demand for r in self._running)

    @property
    def mem_used(self) -> float:
        return sum(r.task.mem_demand for r in self._running)

    @property
    def cpu_pct(self) -> float:
        return 100.0 * self.cpu_used / self.spec.cores

    @property
    def mem_pct(self) -> float:
        return 100.0 * self.mem_used / self.spec.mem_gb

    @property
    def cpu_load_pct(self) -> float:
        return 100.0 * (self.cpu_used + self._queued_cpu) / self.spec.cores

    @property
    def mem_load_pct(self) -> float:
        return 100.0 * (self.mem_used + self._queued_mem) / self.spec.mem_gb

    @property
    def cpu_signal(self) -> float:
        return self.cpu_load_pct if self.count_queued else self.cpu_pct

    @property
    def mem_signal(self) -> float:
        return self.mem_load_pct if self.count_queued else self.mem_pct

    @property
    def mean_response_time(self) -> float:
        """R-bar: mean response time of the last W tasks completed here (0.0 before any completion)."""
        return self.resp_window.mean()

    @property
    def n_running(self) -> int:
        return len(self._running)

    @property
    def queue_length(self) -> int:
        return len(self._queue)

    @property
    def active_tasks(self) -> int:
        return self.n_running + self.queue_length

    def is_idle(self) -> bool:
        return self.active_tasks == 0

    def can_ever_fit(self, task: Task) -> bool:
        return task.cpu_demand <= self.spec.cores and task.mem_demand <= self.spec.mem_gb

    def assign(self, task: Task, tick: int) -> TaskRun:
        if not self.can_ever_fit(task):
            raise ValueError(f"task {task.id} can never fit on server {self.id}")
        run = TaskRun(task=task, server_id=self.id, assigned_tick=tick, remaining=task.work)
        self._queue.append(run)
        self._queued_cpu += task.cpu_demand
        self._queued_mem += task.mem_demand
        self._start_queued(tick)
        return run

    def step(self, tick: int) -> list[TaskRun]:
        """Process one tick of work; return the tasks that finished at the end of it."""
        finished: list[TaskRun] = []
        still_running: list[TaskRun] = []
        for run in self._running:
            run.remaining -= self.spec.speed
            if run.remaining <= 0:
                run.finish_tick = tick + 1
                finished.append(run)
            else:
                still_running.append(run)
        self._running = still_running
        for run in finished:
            self.resp_window.push(run.response_time)
        self.completed += len(finished)
        self._start_queued(tick + 1)
        return finished

    def sample(self) -> None:
        """Record the observed CPU and memory signal as one observation."""
        self.cpu_window.push(self.cpu_signal)
        self.mem_window.push(self.mem_signal)

    def _fits_now(self, task: Task) -> bool:
        return (
            self.cpu_used + task.cpu_demand <= self.spec.cores
            and self.mem_used + task.mem_demand <= self.spec.mem_gb
        )

    def _start_queued(self, tick: int) -> None:
        """Strict FIFO: start tasks from the head while the head fits (no overtaking, so no starvation)."""
        while self._queue and self._fits_now(self._queue[0].task):
            run = self._queue.popleft()
            run.start_tick = tick
            self._running.append(run)
            self._queued_cpu -= run.task.cpu_demand
            self._queued_mem -= run.task.mem_demand
        if not self._queue:
            self._queued_cpu = self._queued_mem = 0.0  # clear float drift from repeated +/-


def build_servers(
    specs: tuple[ServerSpec, ...] = SERVERS,
    window: int = SCORING.window,
    count_queued: bool = SCORING.count_queued,
) -> list[Server]:
    """Fresh, independent servers for one run."""
    return [Server(i, spec, window, count_queued) for i, spec in enumerate(specs)]
