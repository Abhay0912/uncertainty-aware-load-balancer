"""Immutable information exposed to practical scheduling policies."""

from __future__ import annotations

from dataclasses import dataclass

from lbsim.workload import Task


@dataclass(frozen=True, slots=True)
class TaskRequest:
    id: int
    arrival_tick: int
    cpu_demand: float
    mem_demand: float
    task_class: str | None
    estimated_work: float | None

    def can_fit(self, cores: float, mem_gb: float) -> bool:
        return self.cpu_demand <= cores and self.mem_demand <= mem_gb


@dataclass(frozen=True, slots=True)
class ActiveTaskView:
    id: int
    cpu_demand: float
    mem_demand: float
    task_class: str | None
    estimated_total_work: float
    elapsed_ticks: int


@dataclass(frozen=True, slots=True)
class QueuedTaskView:
    id: int
    cpu_demand: float
    mem_demand: float
    task_class: str | None
    estimated_work: float


@dataclass(frozen=True, slots=True)
class SnapshotWindow:
    _values: tuple[float, ...]

    def values(self) -> tuple[float, ...]:
        return self._values

    def __len__(self) -> int:
        return len(self._values)

    def mean(self) -> float:
        return sum(self._values) / len(self._values) if self._values else 0.0

    def std(self) -> float:
        if not self._values:
            return 0.0
        mu = self.mean()
        return (sum((x - mu) ** 2 for x in self._values) / len(self._values)) ** 0.5


@dataclass(frozen=True, slots=True)
class ServerView:
    id: int
    cores: float
    mem_gb: float
    speed: float
    running: tuple[ActiveTaskView, ...]
    queue: tuple[QueuedTaskView, ...]
    cpu_pct: float
    mem_pct: float
    cpu_load_pct: float
    mem_load_pct: float
    cpu_window: SnapshotWindow
    mem_window: SnapshotWindow
    resp_window: SnapshotWindow
    count_queued: bool = True

    @property
    def spec(self):
        """Compatibility object for existing policies; it contains no execution state."""
        from lbsim.config import ServerSpec

        return ServerSpec(self.cores, self.mem_gb, self.speed)

    @property
    def cpu_signal(self) -> float:
        return self.cpu_load_pct if self.count_queued else self.cpu_pct

    @property
    def mem_signal(self) -> float:
        return self.mem_load_pct if self.count_queued else self.mem_pct

    @property
    def mean_response_time(self) -> float:
        return self.resp_window.mean()

    @property
    def n_running(self) -> int:
        return len(self.running)

    @property
    def queue_length(self) -> int:
        return len(self.queue)

    @property
    def active_tasks(self) -> int:
        return self.n_running + self.queue_length

    def is_idle(self) -> bool:
        return not self.active_tasks

    def can_ever_fit(self, task: Task | TaskRequest) -> bool:
        return task.cpu_demand <= self.cores and task.mem_demand <= self.mem_gb


def task_request(task: Task) -> TaskRequest:
    return TaskRequest(
        task.id, task.arrival_tick, task.cpu_demand, task.mem_demand,
        task.task_class, task.estimated_work,
    )


def make_server_views(servers, now: int) -> tuple[ServerView, ...]:
    """Create a snapshot without copying hidden work or remaining-work fields."""
    views = []
    for server in servers:
        running = tuple(
            ActiveTaskView(
                r.task.id, r.task.cpu_demand, r.task.mem_demand, r.task.task_class,
                r.task.estimated_work or 0.0,
                max(0, now - (r.start_tick if r.start_tick is not None else now)),
            )
            for r in server._running
        )
        queued = tuple(
            QueuedTaskView(
                r.task.id, r.task.cpu_demand, r.task.mem_demand, r.task.task_class,
                r.task.estimated_work or 0.0,
            )
            for r in server._queue
        )
        views.append(ServerView(
            server.id, server.spec.cores, server.spec.mem_gb, server.spec.speed,
            running, queued, server.cpu_pct, server.mem_pct,
            server.cpu_load_pct, server.mem_load_pct,
            SnapshotWindow(server.cpu_window.values()),
            SnapshotWindow(server.mem_window.values()),
            SnapshotWindow(server.resp_window.values()),
            server.count_queued,
        ))
    return tuple(views)
