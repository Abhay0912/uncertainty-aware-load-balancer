"""Time-stepped simulation loop with end-of-run queue draining (decisions D1, D4, D13).

Each tick t:
  1. dispatch: every task arriving at t is assigned via policy.select (tasks start at t if they fit)
  2. sample:   each server records its observed CPU/memory signal (D19), and a per-tick row is logged
  3. step:     running tasks progress; finished ones free capacity and queued ones start at t + 1
Arrivals end when the task list is exhausted; the loop then drains until every server is idle,
or stops at max_ticks with the unfinished tasks flagged (completed = False).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from lbsim.config import SCORING, SERVERS, SIMULATION, ScoringConfig, ServerSpec, SimulationConfig
from lbsim.policies.base import Policy
from lbsim.server import Server, TaskRun, build_servers
from lbsim.scheduling_view import make_server_views, task_request
from lbsim.workload import Task

TASK_COLUMNS = [
    "task_id", "arrival_tick", "server_id", "cpu_demand", "mem_demand", "work",
    "server_cpu_pct", "server_mem_pct", "server_cpu_load_pct", "server_mem_load_pct",
    "start_tick", "finish_tick", "response_time",
    "completed", "capacity_pressure",
]
TICK_COLUMNS = [
    "tick", "server_id", "cpu_pct", "mem_pct", "cpu_load_pct", "mem_load_pct",
    "n_running", "queue_length", "completed",
]


@dataclass(frozen=True, eq=False)
class SimulationResult:
    policy: str
    tasks: pd.DataFrame
    server_ticks: pd.DataFrame
    n_ticks: int
    drained: bool


def simulate(
    tasks: Sequence[Task],
    policy: Policy,
    specs: tuple[ServerSpec, ...] = SERVERS,
    scoring: ScoringConfig = SCORING,
    sim: SimulationConfig = SIMULATION,
) -> SimulationResult:
    """Run one policy over one task stream on freshly built servers.
    `scoring` sets what servers record (window size, D19 signal); give the policy the same config."""
    if any(a.arrival_tick > b.arrival_tick for a, b in zip(tasks, tasks[1:])):
        raise ValueError("tasks must be sorted by arrival_tick")
    if tasks and tasks[-1].arrival_tick >= sim.max_ticks:
        raise ValueError("max_ticks must exceed the last arrival so every task is dispatched")

    servers = build_servers(specs, scoring.window, scoring.count_queued)
    policy.reset()
    runs: list[TaskRun] = []
    decisions: list[dict[str, Any]] = []
    tick_rows: list[tuple] = []
    next_task, tick = 0, 0

    while next_task < len(tasks) or not all(s.is_idle() for s in servers):
        if tick >= sim.max_ticks:
            break

        while next_task < len(tasks) and tasks[next_task].arrival_tick <= tick:
            task = tasks[next_task]
            sid = policy.select(make_server_views(servers, tick), task_request(task))
            if not 0 <= sid < len(servers):
                raise ValueError(f"{policy.name} returned invalid server index {sid}")
            target = servers[sid]
            decisions.append({
                "server_cpu_pct": target.cpu_pct,
                "server_mem_pct": target.mem_pct,
                "server_cpu_load_pct": target.cpu_load_pct,
                "server_mem_load_pct": target.mem_load_pct,
                "capacity_pressure": False,
                **policy.decision_info(),
            })
            runs.append(target.assign(task, tick))
            next_task += 1

        for s in servers:
            s.sample()
            tick_rows.append(
                (tick, s.id, s.cpu_pct, s.mem_pct, s.cpu_load_pct, s.mem_load_pct,
                 s.n_running, s.queue_length, s.completed)
            )
        for s in servers:
            finished = s.step(tick)
            for run in finished:
                policy.observe_completion(
                    run.task, s.id, run.finish_tick - run.start_tick, s.spec.speed
                )
        tick += 1

    return SimulationResult(
        policy=policy.name,
        tasks=_task_frame(runs, decisions),
        server_ticks=pd.DataFrame(tick_rows, columns=TICK_COLUMNS),
        n_ticks=tick,
        drained=all(s.is_idle() for s in servers),
    )


def _task_frame(runs: list[TaskRun], decisions: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for run, info in zip(runs, decisions):
        done = run.finish_tick is not None
        rows.append({
            "task_id": run.task.id,
            "arrival_tick": run.task.arrival_tick,
            "server_id": run.server_id,
            "cpu_demand": run.task.cpu_demand,
            "mem_demand": run.task.mem_demand,
            "work": run.task.work,
            "start_tick": run.start_tick,
            "finish_tick": run.finish_tick,
            "response_time": run.response_time if done else float("nan"),
            "completed": done,
            **info,
        })
    frame = pd.DataFrame(rows)
    extra = [c for c in frame.columns if c not in TASK_COLUMNS]
    return frame.reindex(columns=TASK_COLUMNS + extra)
