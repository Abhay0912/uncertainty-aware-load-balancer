# Architecture

## Data flow
```
config.py ──────────────────────────────────────────────────────────────┐
                                                                        │
WorkloadGenerator(seed, "stable"|"bursty")                              │
   └─► list[Task]  (generated ONCE per seed, reused by every policy)    │
                                   │                                    │
        ┌──────────────────────────▼──────────────────────────────────┐ │
        │ simulate(tasks, policy) — one tick at a time, fresh servers │◄┘
        │  1. for each task arriving now:                             │
        │       sid = policy.select(servers, task); assign(task)      │
        │  2. every server samples C, M into its MetricWindow and a   │
        │     per-(tick, server) row is logged          (D13)         │
        │  3. every server.step(): progress work, finish tasks        │
        │     (finished tasks push R into the response window)        │
        │  arrivals end with the task list; drain until idle (D4/D14) │
        └──────────────────────────┬──────────────────────────────────┘
                                   │ pandas DataFrames
                         evaluation.py  → spec §6 metrics per (policy, workload, seed) (D22)
                                   │
                    experiments/run_all.py → results/runs.csv, summary.csv, paired.csv (D23)
                    experiments/sensitivity.py → results/sensitivity.csv (sensitivity.py, D26)
                    experiments/plots.py → results/figures/fig1–fig6.png
```

## Module responsibilities
| Module | Responsibility |
|---|---|
| `config.py` | Every tunable constant (see `docs/spec.md` §8). No logic. |
| `workload.py` | Seeded `Task` generation for the stable and bursty patterns. |
| `server.py` | Capacity, running tasks and local queue; computes utilisation % (running), load % (running + queued) and the observed signal (D19); owns the `MetricWindow`s. |
| `metric_window.py` | A fixed-length rolling buffer with mean and population std. |
| `scoring.py` | Pure formulas: `normalised_response`, `load_score` (L_i), `normal_cdf`, `exceedance_probability` (P_C, P_M), `combined_risk` (P_risk), `risk_adjusted_score` (S_i), `server_risk`. |
| `policies/base.py` | The `Policy` ABC (Strategy pattern), `RandomizedPolicy` (seeded, rewindable RNG), `policy_rng`, tie-break helper. |
| `policies/*.py` | One policy per file: RR, WRR, Random, LeastCPU, WeightedMetric, P2C, Probabilistic. |
| `simulator.py` | The time-stepped loop, queue draining, and recording. Knows nothing about specific policies. |
| `evaluation.py` | Pure functions: logs → metrics (`evaluate`), seed aggregation (`summarise_runs`), paired ablation comparison (`paired_differences`). |
| `experiments/run_all.py` | Runs every policy × workload × seed (`--seeds`, `--out`), then writes the CSVs. |
| `sensitivity.py` | Sweep points (`apply_axis`, `sweep_points`), paired target-vs-ablation runs under one config with a WM cache (`run_sweep`), and the per-point paired table (`sensitivity_table`). Outcomes are always scored at the frozen thresholds (D26). |
| `experiments/sensitivity.py` | Runs the sweep over every workload × seed and writes `sensitivity_runs.csv` / `sensitivity.csv` (about 200 s). |
| `experiments/plots.py` | Reads the CSVs and writes six PNGs. It re-simulates one bursty seed for the load time series. |

## Policy contract
```python
class Policy(ABC):
    name: str
    def reset(self) -> None: ...                           # clear state between runs (e.g. RR pointer)
    def select(self, servers: Sequence[Server], task: Task) -> int: ...   # returns a server index
    def decision_info(self) -> Mapping[str, float | bool]: ...           # extra per-task log fields, default {}
```
- Policies only **read** server state. They never modify it.
- Randomised policies (Random, P2C) receive their own seeded `numpy.random.Generator` in `__init__`, so their randomness doesn't shift the workload's random stream.
- `ProbabilisticPolicy` exposes the last decision's `p_risk`, `p_cpu`, `p_mem`, `score`, `n_eligible` and the capacity-pressure flag through `decision_info()`, so the simulator logs them with the task.

## Fairness guarantees
1. The task list is generated once per (workload, seed) and passed unchanged to every policy.
2. Server configuration comes from `config.py` and is rebuilt fresh for each run.
3. The same simulator loop and the same drain rule are used for all policies.
