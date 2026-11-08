# V1 and V2 Evaluation Metrics

This document contains the regenerated evaluation metrics for the original V1 policy matrix and the V2
completion-time policies.

## Evaluation protocol

- Workloads: `stable` and `bursty`.
- Seeds: `0, 1, 2, 3, 4`.
- Tasks per matched trace: first 1,000 tasks.
- SLA threshold: 18 seconds.
- Every policy receives the same workload trace for each workload and seed.
- Values below are means over the five seeds. Response time includes the per-seed standard deviation.
- All runs drained successfully.

V1 was generated with:

```text
python -m experiments.run_all --seeds 0 1 2 3 4 --limit 1000 --out results/v1
```

V2 was generated with:

```text
python -m experiments.run_v2 --seeds 0 1 2 3 4 --workloads stable bursty --limit 1000
```

## Metric definitions

| Metric | Definition | Better |
|---|---|---|
| Mean response | Mean arrival-to-completion time | Lower |
| p95 response | 95th percentile response time | Lower |
| SLA violations | Fraction of completed tasks with response time > 18 s | Lower |
| Throughput | Completed tasks per simulation second | Higher |
| Goodput | Tasks completed within SLA per arrival-horizon second | Higher |
| CPU utilisation | Mean true running CPU utilisation | Context |
| Memory utilisation | Mean true running memory utilisation | Context |
| Load imbalance | Mean population standard deviation of CPU utilisation across servers | Lower, interpreted with heterogeneity |
| Mean queue length | Mean queued tasks across server-tick observations | Lower |
| Drain ticks | Ticks after the arrival horizon needed to empty queues | Lower |

## V1 metrics

### Stable workload

| Policy | Mean response (s) | p95 (s) | SLA violations | Throughput | Goodput | CPU util. | Mem. util. | Imbalance | Queue length | Drain ticks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Round Robin | 231.265 ± 9.722 | 1414.63 | 56.6% | 0.485 | 0.434 | 29.737% | 26.228% | 26.616 | 33.512 | 1066.2 |
| Weighted RR | 8.774 ± 1.420 | 23.80 | 8.9% | 3.553 | 0.911 | 63.882% | 55.421% | 18.197 | 2.857 | 0 |
| Random | 243.818 ± 16.861 | 1471.71 | 57.3% | 0.474 | 0.427 | 29.830% | 26.389% | 27.336 | 35.225 | 1108.8 |
| Least CPU | 6.987 ± 1.187 | 16.80 | 3.9% | 3.886 | 0.961 | 69.679% | 61.637% | 14.569 | 1.710 | 0 |
| Weighted Metric | 7.105 ± 1.225 | 16.00 | 3.7% | 3.809 | 0.963 | 68.609% | 60.241% | 14.629 | 1.751 | 0 |
| P2C | 15.644 ± 2.906 | 52.41 | 24.2% | 2.765 | 0.758 | 56.221% | 49.286% | 21.407 | 5.753 | 0 |
| Probabilistic V1 | 7.421 ± 1.318 | 17.40 | 4.5% | 4.097 | 0.955 | 72.538% | 64.437% | 14.928 | 2.165 | 0 |

### Bursty workload

| Policy | Mean response (s) | p95 (s) | SLA violations | Throughput | Goodput | CPU util. | Mem. util. | Imbalance | Queue length | Drain ticks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Round Robin | 256.439 ± 23.557 | 1536.55 | 56.6% | 0.455 | 0.434 | 32.801% | 25.418% | 28.770 | 35.989 | 1201.2 |
| Weighted RR | 32.853 ± 4.972 | 71.22 | 64.3% | 3.260 | 0.357 | 66.152% | 50.847% | 15.984 | 18.442 | 0 |
| Random | 273.734 ± 14.120 | 1628.88 | 56.8% | 0.440 | 0.432 | 32.665% | 25.546% | 29.007 | 37.903 | 1274.6 |
| Least CPU | 32.696 ± 4.413 | 81.83 | 61.5% | 2.609 | 0.385 | 57.224% | 43.143% | 18.081 | 14.777 | 0 |
| Weighted Metric | 32.871 ± 4.378 | 87.03 | 60.9% | 2.830 | 0.391 | 60.988% | 46.236% | 16.728 | 16.148 | 0 |
| P2C | 37.528 ± 6.081 | 101.60 | 58.7% | 2.097 | 0.413 | 51.284% | 39.130% | 23.050 | 13.709 | 0 |
| Probabilistic V1 | 32.843 ± 3.751 | 90.21 | 62.0% | 2.671 | 0.380 | 57.571% | 44.020% | 17.233 | 15.205 | 0 |

## V2 metrics

V2 includes the same seven policies plus `ECT-only` and `Uncertainty-aware ECT`. The seven baseline rows
are intentionally unchanged by the V2 additions.

### Stable workload

| Policy | Mean response (s) | p95 (s) | SLA violations | Throughput | Goodput | CPU util. | Mem. util. | Imbalance | Queue length | Drain ticks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Round Robin | 231.265 ± 9.722 | 1414.63 | 56.6% | 0.485 | 0.434 | 29.737% | 26.228% | 26.616 | 33.512 | 1066.2 |
| Weighted RR | 8.774 ± 1.420 | 23.80 | 8.9% | 3.553 | 0.911 | 63.882% | 55.421% | 18.197 | 2.857 | 0 |
| Random | 243.818 ± 16.861 | 1471.71 | 57.3% | 0.474 | 0.427 | 29.830% | 26.389% | 27.336 | 35.225 | 1108.8 |
| Least CPU | 6.987 ± 1.187 | 16.80 | 3.9% | 3.886 | 0.961 | 69.679% | 61.637% | 14.569 | 1.710 | 0 |
| Weighted Metric | 7.105 ± 1.225 | 16.00 | 3.7% | 3.809 | 0.963 | 68.609% | 60.241% | 14.629 | 1.751 | 0 |
| P2C | 15.644 ± 2.906 | 52.41 | 24.2% | 2.765 | 0.758 | 56.221% | 49.286% | 21.407 | 5.753 | 0 |
| Probabilistic V1 | 7.421 ± 1.318 | 17.40 | 4.5% | 4.097 | 0.955 | 72.538% | 64.437% | 14.928 | 2.165 | 0 |
| **ECT-only** | **7.695 ± 1.385** | **14.21** | **1.6%** | **4.329** | **0.984** | 61.085% | 53.700% | 36.527 | 2.798 | 0 |
| Uncertainty-aware ECT | 9.149 ± 1.300 | 16.00 | 3.0% | 4.263 | 0.970 | 59.002% | 51.926% | 36.937 | 4.023 | 0 |

### Bursty workload

| Policy | Mean response (s) | p95 (s) | SLA violations | Throughput | Goodput | CPU util. | Mem. util. | Imbalance | Queue length | Drain ticks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Round Robin | 256.439 ± 23.557 | 1536.55 | 56.6% | 0.455 | 0.434 | 32.801% | 25.418% | 28.770 | 35.989 | 1201.2 |
| Weighted RR | 32.853 ± 4.972 | 71.22 | 64.3% | 3.260 | 0.357 | 66.152% | 50.847% | 15.984 | 18.442 | 0 |
| Random | 273.734 ± 14.120 | 1628.88 | 56.8% | 0.440 | 0.432 | 32.665% | 25.546% | 29.007 | 37.903 | 1274.6 |
| Least CPU | 32.696 ± 4.413 | 81.83 | 61.5% | 2.609 | 0.385 | 57.224% | 43.143% | 18.081 | 14.777 | 0 |
| Weighted Metric | 32.871 ± 4.378 | 87.03 | 60.9% | 2.830 | 0.391 | 60.988% | 46.236% | 16.728 | 16.148 | 0 |
| P2C | 37.528 ± 6.081 | 101.60 | 58.7% | 2.097 | 0.413 | 51.284% | 39.130% | 23.050 | 13.709 | 0 |
| Probabilistic V1 | 32.843 ± 3.751 | 90.21 | 62.0% | 2.671 | 0.380 | 57.571% | 44.020% | 17.233 | 15.205 | 0 |
| **ECT-only** | **30.785 ± 4.572** | **67.41** | 62.5% | **3.607** | 0.375 | 65.786% | 49.603% | 19.156 | 19.070 | 0 |
| Uncertainty-aware ECT | 31.593 ± 4.416 | **68.01** | 63.2% | **3.628** | 0.368 | 64.694% | 49.909% | 21.138 | 19.831 | 0 |

## V2 uncertainty ablation

The uncertainty-aware policy and ECT-only use the same task estimator and shadow projection. Only the
completion-time uncertainty penalty differs.

| Workload | Metric | Uncertainty ECT − ECT-only | Uncertainty wins |
|---|---|---:|---:|
| Stable | Mean response | +1.454 s | 0/5 |
| Stable | p95 response | +1.790 s | 0/5 |
| Stable | SLA violations | +1.42 percentage points | 0/5 |
| Stable | Throughput | −0.0665/s | 0/5 (1 tie) |
| Bursty | Mean response | +0.807 s | 0/5 |
| Bursty | p95 response | +0.600 s | 0/5 (2 ties) |
| Bursty | SLA violations | +0.72 percentage points | 0/5 |
| Bursty | Throughput | +0.0217/s | 3/5 |

## Metric-only conclusion

On this matched five-seed, 1,000-task evaluation, ECT adds a useful task-aware completion-time signal:

- Stable: lower p95 latency and SLA violations than the original load-aware baselines.
- Bursty: lower mean and p95 latency than the original policies, with higher throughput than the other
  load-aware policies.
- Uncertainty-aware ECT does not yet improve consistently over ECT-only; its mean latency and SLA results
  are worse in this evaluation.

These are simulation results under the configured duration-estimate and workload assumptions, not production
performance claims.
