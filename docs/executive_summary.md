# Executive Summary

## Project purpose

This project studies how incoming cloud tasks should be assigned to a group of servers with different capacities and processing speeds.

The central approach predicts how long a particular task is likely to take on each possible server. It then selects the server with the lowest predicted completion cost.

The project is a controlled simulation study. Its results describe the configured simulator and workloads; they are not a guarantee of production-cloud performance.

## End-to-end flow

```
Generate the same task stream for every policy
        ↓
Read scheduler-visible task and server information
        ↓
Estimate the task's required work
        ↓
Project the task through each server's temporary shadow queue
        ↓
Calculate predicted completion cost
        ↓
Select the best server
        ↓
Run the real simulator and record results
        ↓
Evaluate latency, SLA, throughput and resource metrics
```

## Component definitions

### Workload generator

The workload generator creates reproducible task streams using seeded random number generators.

Each task has:

- Arrival time.

- CPU requirement.

- Memory requirement.

- Actual execution work used internally by the simulator.

- Optional task class or public duration estimate.

The project evaluates:

- **Stable workload:** demand changes gradually.

- **Bursty workload:** demand temporarily spikes above available capacity.

- **Heterogeneous workload:** tasks have visible classes and different typical durations.

The stable and bursty evaluation results use the same generated task stream for every policy within a workload and seed.

### Server model

Each server has:

- CPU capacity.

- Memory capacity.

- Processing speed.

- Running tasks.

- A strict FIFO waiting queue.

CPU and memory are reserved by running tasks. A waiting task starts only when it is at the head of the queue and both resources are available.

### Simulator

The simulator advances in one-second ticks:

1. Tasks arriving during the tick are assigned one at a time.

2. Server state is sampled.

3. Running tasks make progress.

4. Completed tasks release resources.

5. Waiting tasks may start on the next tick.

After arrivals stop, the simulator drains the queues so completed tasks are not silently omitted.

### Scheduler-visible state

The practical scheduler receives an immutable view of information available at dispatch time:

- Task CPU and memory requirements.

- Task class or estimated duration.

- Server capacity and speed.

- Running-task reservations.

- FIFO queued tasks.

- Current CPU and memory state.

It does not receive the task’s hidden actual work, exact remaining work, or future completion time.

This prevents the proposed method from using information that a real scheduler would not have.

### Duration estimator

The duration estimator predicts how much work the incoming task may require.

It uses the following fallback order:

1. A public duration estimate supplied with the task.

2. Historical observations for the same task class.

3. Historical observations pooled across classes.

4. A global default prior.

When a task completes, its observed service time is converted back into speed-1 work and added to the history. The current task cannot update its own estimate before it is assigned.

For the original stable and bursty workloads, tasks generally lack useful class information, so the estimator relies mainly on the global prior. The heterogeneous workload provides more informative task classes and duration hints.

### Shadow queue projection

A shadow queue is a temporary copy of a server’s running tasks and FIFO queue.

For each candidate server, the projection:

1. Adds the incoming task after existing queued work.

2. Preserves FIFO ordering and head-of-line blocking.

3. Checks CPU and memory fit.

4. Advances running tasks according to server speed.

5. Releases resources when tasks finish.

6. Starts waiting tasks at the correct simulator tick.

7. Records the incoming task’s predicted start and finish time.

The shadow projection does not modify the real server. It is discarded after the prediction.

### ECT-only policy

ECT means **Earliest Completion Time**.

ECT-only chooses the feasible server with the lowest predicted response time:

\[ \\text\{ECT\}\_i = \\text\{predicted finish time on server \} i

- \\text\{task arrival time\} \]

This includes both waiting time and execution time.

### Uncertainty-aware ECT

The uncertainty-aware policy considers several plausible task-duration outcomes rather than relying only on one expected value.

Its cost is:

\[ J\_i = \\hat\{\\mu\}*i +* *\\beta \\max(0,\\hat\{q\}*\{90,i\}-\\hat\{\\mu\}\_i) \]

where:

- (\\hat\{\\mu\}\_i) is the predicted mean completion time.

- (\\hat\{q\}\_\{90,i\}) is the predicted 90th-percentile completion time.

- (\\beta) controls how much uncertainty matters.

When (\\beta = 0), this becomes ECT-only. A positive (\\beta) prefers predictions with smaller high-end delays.

### Baseline policies

The proposed policies are compared with conventional alternatives:

- **Round Robin:** assigns tasks in repeating server order.

- **Random:** chooses a feasible server randomly.

- **Weighted Round Robin:** assigns more tasks to servers with greater capacity.

- **Least CPU:** selects the server with the lowest current CPU load.

- **Power of Two Choices:** samples two servers and chooses the one with the lower load score.

- **Weighted Metric:** combines CPU load, memory load and recent response time.

The original threshold-risk policy remains available in the implementation as a historical comparison, but the current presentation treats completion-time prediction as the main approach.

### Evaluation metrics

The evaluator records:

- **Mean response time:** average arrival-to-completion time.

- **p95 response time:** time within which 95% of tasks finish.

- **SLA violation rate:** percentage of completed tasks taking longer than 18 seconds.

- **Throughput:** completed tasks per simulation second.

- **Goodput:** tasks completed within the SLA per arrival-horizon second.

- **CPU and memory utilisation:** average true resource use by running tasks.

- **Load imbalance:** difference in utilisation across servers.

- **Queue length:** average number of waiting tasks.

- **Drain time:** time needed to finish queued work after arrivals stop.

## Results

The following results use five seeds, the first 1,000 tasks per matched trace, and an 18-second SLA. Values are means across seeds. All runs drained successfully.

### Stable workload

| Policy | Mean response (s) | p95 (s) | SLA violations | Throughput |
| - | -: | -: | -: | -: |
| Round Robin | 231.27 | 1414.63 | 56.6% | 0.485/s |
| Random | 243.82 | 1471.71 | 57.3% | 0.474/s |
| Weighted RR | 8.77 | 23.80 | 8.9% | 3.553/s |
| P2C | 15.64 | 52.41 | 24.2% | 2.765/s |
| Least CPU | 6.99 | 16.80 | 3.9% | 3.886/s |
| Weighted Metric | 7.11 | 16.00 | 3.7% | 3.809/s |
| ECT-only | **7.70** | **14.21** | **1.6%** | **4.329/s** |
| Uncertainty ECT | 9.15 | 16.00 | 3.0% | 4.263/s |


### Bursty workload

| Policy | Mean response (s) | p95 (s) | SLA violations | Throughput |
| - | -: | -: | -: | -: |
| Round Robin | 256.44 | 1536.55 | **56.6%** | 0.455/s |
| Random | 273.73 | 1628.88 | 56.8% | 0.440/s |
| Weighted RR | 32.85 | 71.22 | 64.3% | 3.260/s |
| P2C | 37.53 | 101.60 | 58.7% | 2.097/s |
| Least CPU | 32.70 | 81.83 | 61.5% | 2.609/s |
| Weighted Metric | 32.87 | 87.03 | 60.9% | 2.830/s |
| ECT-only | **30.79** | **67.41** | 62.5% | 3.607/s |
| Uncertainty ECT | 31.59 | 68.01 | 63.2% | **3.628/s** |


## Main findings

1. **Ignoring capacity and queues performs badly.** Round Robin and Random overload the slowest server even though it has very little capacity.

2. **Load awareness is important.** CPU, memory, queue and capacity information reduce response time by a very large amount compared with blind assignment.

3. **Task-aware prediction improves the decision signal.** ECT-only has the best p95 latency in both workloads and the best throughput in the stable workload.

4. **Bursts cannot be eliminated by placement alone.** During a burst, offered work exceeds total cluster capacity, so many SLA violations remain unavoidable.

5. **Uncertainty is not yet a proven improvement.** The uncertainty-aware policy is close to ECT-only but has higher mean latency and SLA violations in this evaluation. Its small throughput advantage under bursts is not enough to establish a general result.

## Overall conclusion

The strongest supported conclusion is:

> Predicting the completion time of the specific incoming task is a promising and practical way to improve task placement in this simulator.

The results do not yet justify claiming universal superiority, production readiness, or a consistent benefit from the uncertainty penalty. More held-out seeds, noisy duration estimates, stale telemetry and per-server background volatility should be evaluated before making broader claims.

## Why the main constants were chosen

These values were fixed before the final comparison rather than selected after looking at which policy performed best:

- **Mean task work = 6 seconds:** This provides a representative nominal task duration and sets the reference scale for the experiment.

- **SLA limit = 18 seconds:** This is three times the nominal six-second task duration. It allows normal variation and moderate queueing while flagging tasks delayed substantially by overload. Fixing it in advance prevents the SLA from being tuned to favour a particular policy.

- **One-second simulation tick:** This keeps the discrete simulator understandable, reproducible, and easy to inspect. The trade-off is that completion times are rounded to tick boundaries.

- **Target utilisation = 65%:** The stable workload remains below saturation, leaving room for policies to demonstrate how well they distribute work while still creating meaningful contention.

- **Burst settings:** Four 50-tick bursts multiply arrivals by 3 and CPU demand by 1.3, creating short, visible overload episodes. The bursty baseline is reduced so its average offered load matches the stable workload; the comparison therefore tests variability rather than simply adding more total work.

- **Five seeds and 1,000 matched tasks:** Five seeds provide a reproducible view of workload randomness, and the cap keeps the comparison practical. Every policy receives the same trace for each seed, so differences are attributable to placement rather than different tasks.

- **Uncertainty penalty beta = 0.5:** The high-delay tail receives a meaningful but not dominant influence. Beta zero would make the policy identical to ECT-only; 0.5 is retained as a preselected first-pass value, not a value tuned to these results.

- **90th-percentile uncertainty estimate:** The 90th percentile focuses on unusually slow outcomes without relying on an unstable extreme maximum from limited history.

- **Duration-history size = 200 observations:** Recent history keeps predictions responsive while preventing one unusually short or long task from dominating the estimate.

- **Heterogeneous server types:** The cluster includes different capacity and speed levels so capacity-blind policies can be meaningfully tested. The smaller, slower server exposes the cost of assigning work by rotation alone.

- **Queue draining after arrivals stop:** Accepted tasks are allowed to finish instead of being silently dropped at the horizon. This makes response-time and SLA measurements complete, while throughput still reflects the time required to clear a backlog.

