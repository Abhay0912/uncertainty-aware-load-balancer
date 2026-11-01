# Architecture

## Data flow
```
config.py ──────────────────────────────────────────────────────────────┐
                                                                        │
WorkloadGenerator(seed, "stable"|"bursty")                              │
   └─► list[Task]  (generated ONCE per seed, reused by every policy)    │
                                   │                                    │
        ┌──────────────────────────▼──────────────────────────────────┐ │
        │ Simulator.run(tasks, servers, policy)   — one tick at a time│◄┘
        │  1. move arrived tasks into the dispatch queue              │
        │  2. for each queued task: sid = policy.select(servers, task)│
        │  3. servers[sid].assign(task)                               │
        │  4. every server.step(): progress work, finish tasks        │
        │  5. every server samples C, M, R into its MetricWindow      │
        │  6. Recorder logs per-task + per-tick rows                  │
        │  stop arrivals at T_sim, then drain until all tasks finish  │
        └──────────────────────────┬──────────────────────────────────┘
                                   │ pandas DataFrames
                         evaluation.py  → 6 metrics per (policy, workload, seed)
                                   │
                    experiments/run_all.py → results/*.csv + plots
```

## Module responsibilities
| Module | Responsibility |
|---|---|
| `config.py` | Every tunable constant (see `docs/spec.md` §8). No logic. |
| `workload.py` | Seeded `Task` generation for the stable and bursty patterns. |
| `server.py` | Capacity, running tasks and local queue; computes the current CPU %, memory % and response time; owns a `MetricWindow`. |
| `metric_window.py` | A fixed-length rolling buffer with mean and population std. |
| `policies/base.py` | The `Policy` abstract base class (Strategy pattern). |
| `policies/*.py` | One policy per file: RR, WRR, Random, LeastCPU, WeightedMetric, P2C, Probabilistic. |
| `simulator.py` | The time-stepped loop, queue draining, and recording. Knows nothing about specific policies. |
| `evaluation.py` | Pure functions: logs → metrics. |
| `experiments/run_all.py` | Runs every policy × workload × seed, then writes CSVs and plots. |

## Policy contract
```python
class Policy(ABC):
    name: str
    def reset(self) -> None: ...                           # clear state between runs (e.g. RR pointer)
    def select(self, servers: Sequence[Server], task: Task) -> int: ...   # returns a server index
```
- Policies only **read** server state. They never modify it.
- Randomised policies (Random, P2C) receive their own seeded `numpy.random.Generator` in `__init__`, so their randomness doesn't shift the workload's random stream.
- `ProbabilisticPolicy` also exposes the last decision's `P_risk` and the capacity-pressure flag, so the Recorder can log them.

## Fairness guarantees
1. The task list is generated once per (workload, seed) and passed unchanged to every policy.
2. Server configuration comes from `config.py` and is rebuilt fresh for each run.
3. The same simulator loop and the same drain rule are used for all policies.
