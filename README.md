# Completion-Time-Aware Load Balancing

**Repository:** [https://github.com/Abhay0912/uncertainty-aware-load-balancer](https://github.com/Abhay0912/uncertainty-aware-load-balancer)

M.Tech Cloud Computing project, NIT Warangal (2026). A discrete-time Python simulation compares a load balancer that predicts each task's **completion time** on every feasible server against six conventional baselines, under stable and bursty workloads.

> **Research question:** can task-specific completion-time prediction improve placement compared with blind, capacity-aware, and load-aware policies?

## Headline result

- **Stable workload:** ECT-only achieves the lowest p95 response time (14.21 s), lowest SLA violation rate (1.6%), and highest throughput (4.329 tasks/s) in the matched five-seed evaluation.

- **Bursty workload:** ECT-only achieves the lowest mean response time (30.79 s) and p95 (67.41 s). Uncertainty-aware ECT has slightly higher throughput, but also higher mean latency and SLA violations.

- **Important qualification:** bursts temporarily offer more work than the cluster can process. Placement can reduce avoidable delay, but cannot eliminate all queueing during overload.

- **Conclusion:** completion-time prediction is promising in this simulator, but the results do not establish universal superiority or production readiness.

The full analysis is in [docs/results.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/results.md).

### Results (means over 5 seeds, 1,000 matched tasks per trace, SLA = 18 s)

| Policy | Stable: mean resp (s) | Stable: SLA viol. | Bursty: mean resp (s) | Bursty: SLA viol. | Bursty: throughput (tasks/s) |
| - | - | - | - | - | - |
| Round Robin | 231.27 | 56.6% | 256.44 | 56.6% | 0.455 |
| Random | 243.82 | 57.3% | 273.73 | 56.8% | 0.440 |
| Weighted RR | 8.77 | 8.9% | 32.85 | 64.3% | 3.260 |
| Power of Two Choices | 15.64 | 24.2% | 37.53 | 58.7% | 2.097 |
| Least CPU | 6.99 | 3.9% | 32.70 | 61.5% | 2.609 |
| Weighted Metric | 7.11 | 3.7% | 32.87 | 60.9% | 2.830 |
| **ECT-only (proposed)** | **7.70** | **1.6%** | **30.79** | 62.5% | **3.607** |
| Uncertainty ECT | 9.15 | 3.0% | 31.59 | 63.2% | **3.628** |


Under bursts, every policy violates the SLA for over half of all tasks. Offered work temporarily exceeds capacity, so no placement rule can avoid queueing entirely.

## How the proposed policy works

For each incoming task, the scheduler builds a temporary FIFO projection for each server:

```
predicted work = public duration hint, class history, pooled history, or global prior
predicted finish = shadow-queue start time + predicted work / server speed
ECT = predicted finish − task arrival time
```

ECT-only chooses the feasible server with the lowest predicted completion time. The projection preserves running tasks, FIFO queue order, resource reservations, head-of-line blocking, and simulator tick timing. The practical policy receives immutable scheduler-visible state; hidden actual work and exact remaining work are not exposed.

Uncertainty-aware ECT adds a tail-risk premium to the predicted mean. It remains available as an ablation, but ECT-only is the primary proposed approach because it performed better on latency in this evaluation.

## Experimental setup

- **5 heterogeneous servers**, from (2 cores, speed 0.5) up to (8 cores, speed 2.0).

- **Synthetic tasks** with CPU and memory demands and lognormal work. Poisson arrivals for 1000 s at about 65% mean load, then the queue is drained until every task finishes.

- **Two workloads with the same mean load:** stable (gentle sinusoidal drift) and bursty (four bursts with 3× the arrival rate).

- **Fair comparison:** each (workload, seed) task list is generated once and given unchanged to all compared policies. Servers are rebuilt for every run, and randomised policies draw from their own seeded RNG streams.

- **Pre-declared parameters:** mean work is 6 s, the SLA is 18 s (3× nominal work), target utilisation is 65%, and the uncertainty penalty is beta = 0.5. These were fixed before inspecting the final results.

- The reported comparison contains 8 policies (six baselines plus ECT-only and Uncertainty ECT) × 2 workloads × 5 seeds. The comparison uses the same traces and a 1,000-task cap per trace. The runner also retains the original probabilistic policy for historical experiments.

## Running it

Requires Python ≥ 3.11.

```
git clone https://github.com/Abhay0912/uncertainty-aware-load-balancer.git
cd uncertainty-aware-load-balancer
python -m venv .venv
.venv\Scripts\Activate.ps1            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

python -m pytest -q                   # test suite
python -m experiments.run_v2 --limit 1000
                                       # matched baselines + ECT -> results/v2_*.csv
python -m experiments.run_all --limit 1000
                                       # original policy pipeline
python -m experiments.sensitivity     # original sensitivity sweep
python -m experiments.plots           # figures       -> results/figures/
```

`results/` is regenerated on every run and is not versioned. The figures in `docs/figures/` are the committed snapshot that the write-up refers to.

## Repository layout

```
src/lbsim/
  config.py          every tunable parameter (frozen dataclasses)
  workload.py        seeded stable/bursty task generation
  server.py          capacity, running tasks, FIFO queue, utilisation and load signals
  metric_window.py   rolling window (mean, population std)
  scoring.py          original load/risk formulas and baseline scoring
  simulator.py       time-stepped loop shared by every policy
  scheduling_view.py  immutable scheduler-visible state
  estimators/         task-duration estimation
  forecasting/        FIFO/resource-aware shadow projection
  evaluation.py      metrics, seed aggregation, paired comparison
  sensitivity.py     sweep definition and paired sweep runner
  policies/          one file per policy, all subclassing Policy
experiments/         run_all.py, sensitivity.py, plots.py
tests/               pytest suite (formula edge cases, fairness, determinism)
docs/                spec, architecture, decision log, results, interview notes, figures
```

## Documentation

| File | Contents |
| - | - |
| [docs/executive\_summary.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/executive_summary.md) | Component definitions, constants rationale, results, and conclusions |
| [docs/evaluation\_metrics\_v1\_v2.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/evaluation_metrics_v1_v2.md) | Compiled matched evaluation metrics |
| [docs/results.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/results.md) | Original results write-up, sensitivity, and threats to validity |
| [docs/spec.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/spec.md) | Specification: formulas, baselines, metrics, parameters |
| [docs/architecture.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/architecture.md) | Data flow, module responsibilities, policy contract |
| [docs/decisions.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/decisions.md) | Decision log (D1–D28), with alternatives and reasons |
| [docs/interview\_notes.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/interview_notes.md) | Pitch, notes for each phase, question bank |
| [report/main.tex](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/report/main.tex) | Final project report (LaTeX). [Open in Overleaf](https://www.overleaf.com/docs?snip_uri=https://raw.githubusercontent.com/Abhay0912/uncertainty-aware-load-balancer/master/report/overleaf_report.zip) |
| [docs/presentation\_slide\_explanations.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/presentation_slide_explanations.md) | Plain-language explanation of each presentation slide |
| [presentation/uncertainty\_aware\_lb.pptx](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/presentation/uncertainty_aware_lb.pptx) | Completion-time-focused presentation |


## Limitations

The workloads are synthetic and the matched evaluation is bounded to five seeds and 1,000 tasks per trace. Duration estimates can be noisy, and the simulator uses simplified FIFO reservations, one-second ticks, and static server speeds. ECT has not been evaluated here with stale telemetry, server-specific background load, or a larger held-out seed set. See [docs/executive\_summary.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/executive_summary.md) and [docs/results.md](file:///home/crankshaft/Projects/uncertainty-aware-load-balancer/docs/results.md#threats-to-validity).

