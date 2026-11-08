# Uncertainty-Aware Predictive Task Placement (V2)

## Consolidated improvement, correction, implementation, and evaluation specification

**Project:** Uncertainty-Aware Probabilistic Load Balancing  
**Original implementation:** [`Abhay0912/uncertainty-aware-load-balancer`](https://github.com/Abhay0912/uncertainty-aware-load-balancer)  
**Basis:** `main.tex` (November 2026 report), the repository's `docs/spec.md` and `docs/architecture.md`, and the simulator's current `server.py`, `simulator.py`, and `workload.py`.  
**Status:** Research and implementation proposal. None of the proposed V2 improvements should be described as experimentally successful until they have been implemented and evaluated.

---

## 0. Executive summary

The recommended next version is **Uncertainty-Aware Predictive Task Placement (V2)**.

The original project estimates whether a server is likely to cross CPU or memory thresholds based on recent rolling means and standard deviations. It then combines that probability with a current-load score. The study found that the probability estimate was broadly calibrated at an aggregate level, but it did not distinguish servers well enough to improve placement. The load-aware baseline was already equalising the servers, and during bursts all servers became highly loaded together.

The proposed change is to make the scheduling decision **task-specific and outcome-oriented**:

1. Estimate how long the incoming task is likely to take to complete on each feasible server, including its wait behind the server's existing work.
2. Respect the simulator's actual resource reservations, strict FIFO queue, and one-second tick order when projecting that completion time.
3. Represent uncertainty in the *predicted completion time*, rather than treating historical CPU and memory variability as a direct proxy for task-placement risk.
4. Choose the server using a risk-sensitive completion-time objective, expressed in seconds.
5. Remove the hard 50% risk admission filter from the V2 default. Use a soft penalty instead.
6. Prevent hidden-information leakage: the practical scheduler must not see the simulator's true task work or exact remaining work. It must use an estimate available at dispatch time.
7. Preserve V1 unchanged as a reproducible baseline. Add V2 alongside it and compare both against all original baselines.

The central proposed research question becomes:

> **Can task-specific completion-time prediction, adjusted for prediction uncertainty, improve task placement across heterogeneous cloud servers compared with conventional load-balancing policies?**

The main experimental comparison must be **ECT-only versus uncertainty-aware ECT**. That isolates the contribution of uncertainty after introducing task-aware scheduling. Comparisons against Round Robin, Weighted Round Robin, Random, Least CPU, Power of Two Choices, Weighted Metric, and the original Probabilistic policy remain necessary.

There is no honest way to guarantee in advance that V2 will outperform every baseline on every metric and workload. The design below makes that outcome more plausible and, more importantly, makes a positive result defensible if the experiments support it.

---

# Part I — Understand and preserve V1

## 1. What V1 currently does

The original report describes a discrete-time Python simulator containing five heterogeneous servers. The load balancer observes CPU and memory load, keeps a rolling window of ten samples, calculates means and population standard deviations, and estimates threshold-exceedance probabilities using a normal approximation.

The principal V1 formulas are:

\[
P_C = 1 - \Phi\left(\frac{\theta_C-\mu_C}{\sigma_C}\right),
\qquad
P_M = 1 - \Phi\left(\frac{\theta_M-\mu_M}{\sigma_M}\right)
\]

with CPU and memory thresholds of 80% and 85%, respectively. If a standard deviation is zero, the implementation uses a deterministic threshold check.

The two probabilities are combined under an independence assumption:

\[
P_{risk}=1-(1-P_C)(1-P_M)
\]

The current-load score combines CPU, memory, and recent response time:

\[
L_i = 0.4\frac{C_i}{100}+0.4\frac{M_i}{100}+0.2r_i
\]

The proposed V1 score is:

\[
S_i = 0.6L_i+0.4P_{risk,i}
\]

The V1 policy excludes servers with risk above 0.5 whenever at least one server is at or below that threshold. If all servers exceed it, it falls back to the lowest score and records capacity pressure.

The seven policies in the original comparison are:

1. Round Robin.
2. Weighted Round Robin.
3. Random.
4. Least CPU.
5. Power of Two Choices (P2C).
6. Weighted Metric — the risk-free ablation of V1.
7. Probabilistic — the original V1 policy.

## 2. V1's empirical result

The report's primary result is not that the probabilistic policy wins. It does not.

Under the stable workload, the reported mean response times were approximately:

| Policy | Mean response time |
|---|---:|
| Round Robin | 857 s |
| Random | 847 s |
| Weighted RR | 9.1 s |
| P2C | 24.8 s |
| Least CPU | 6.16 s |
| Weighted Metric | 6.15 s |
| Probabilistic V1 | 6.44 s |

Under the bursty workload, the weighted-metric baseline achieved 29.3 s mean response time and 53.5% SLA violations, while V1 achieved 29.5 s and 53.9%, respectively.

The paired comparison found that V1 was consistently slightly worse on the stable workload and indistinguishable within seed variation on the bursty workload. The report's explanation is that the risk estimate often had little ranking value: a load-aware algorithm made server load trajectories similar, and during bursts all servers became highly loaded together. The admission filter also proved brittle in the sensitivity analysis.

These results must remain visible in the project history. V2 is a new hypothesis and a new experiment, not a retroactive reinterpretation of V1.

## 3. V1 components worth preserving

Do not discard the foundations that made the original evaluation credible:

- One common simulator loop for all policies.
- The same generated task stream for all policies within each workload/seed pair.
- Fresh server state and reset policy state for each run.
- Independent random streams for workload generation and randomized policies.
- Queue draining after the arrival horizon, with unfinished tasks explicitly recorded if the configured maximum tick count is reached.
- Paired per-seed comparisons.
- A risk-free ablation that isolates the additional component being studied.
- Frozen evaluation thresholds and SLA definitions.
- Tests for determinism, fairness, policy state mutation, and edge cases.

Keep the original V1 configurations, result files, figures, and report reproducible. Prefer a separate V2 branch or a clearly versioned set of modules and experiment configurations.

---

# Part II — Diagnosis: what must change and why

## 4. Weaknesses in the V1 decision signal

### 4.1 V1 predicts threshold exceedance, not the outcome of placing a particular task

V1 asks whether the server's CPU or memory load may cross a threshold based on recent observations. That is a server-level risk estimate.

It does not directly answer the scheduling question:

> If task T is placed on server i now, when will T finish?

The answer depends on the task's CPU and memory requirements, its expected processing duration, the running tasks, the queue order, the resource reservations, and the server's speed.

Two tasks can face different completion times on the same server. Two servers with similar aggregate load can offer very different completion times for a particular task.

### 4.2 A calibrated risk score can still be useless for ranking

A probability can match an observed frequency on average but fail to distinguish the candidate servers at a decision point.

For V2, do not evaluate uncertainty only by comparing one aggregate predicted probability with one aggregate observed frequency. Measure at least:

- **Calibration:** Do predicted completion-time quantiles or SLA probabilities match observed outcomes?
- **Sharpness:** How concentrated or wide are the predicted outcome distributions?
- **Discrimination/ranking:** Do predictions distinguish candidate servers and rank them in a useful order?
- **Decision regret:** How much worse was the selected server than the best counterfactual server under the simulator's actual model?

Aggregate calibration alone is not sufficient evidence that a predictor is useful for scheduling.

### 4.3 Fixed weights give risk influence even when it contains little information

The V1 60:40 score always gives the risk term 40% of the score. When the risk values are almost equal across servers, that constant term does not affect ranking. When estimates are noisy, it can still perturb decisions without providing useful information.

V2 should combine quantities with a common interpretation and unit: predicted completion time in seconds and a completion-time tail penalty in seconds.

### 4.4 Hard admission filtering is brittle

A hard rule that excludes a server above a fixed probability can remove otherwise reasonable choices because of noisy estimates. When every server crosses the cutoff, the filter becomes inactive and falls back to scoring all servers.

The V1 sensitivity analysis already indicates that disabling the admission filter helps slightly. V2 should use a soft cost penalty as its default. Retain hard filtering only as a separately labelled experimental variant if there is a clear feasibility or safety reason for it.

### 4.5 A server-level score ignores task-specific demands

The incoming task has CPU and memory requirements. Its expected completion time also depends on processing duration. A server with more free CPU is not necessarily the best choice for a memory-heavy task; a server with a shorter queue is not necessarily best for a long-running task.

V2 should estimate the completion of the incoming task on every feasible server rather than rank servers using one task-independent score.

## 5. Important simulator facts and corrections

The implementation details below are important. A forecast that ignores them will be inconsistent with the simulator it is meant to predict.

### 5.1 The simulator uses strict FIFO with head-of-line blocking

The server starts tasks from the head of its queue while the head task fits in the currently available CPU and memory. If the head task does not fit, later tasks do not overtake it, even if a later task would fit.

A V2 shadow queue must reproduce this exact rule. It must not sort queued jobs by size, shortest processing time, or resource fit.

### 5.2 The dispatch tick matters

The simulator's per-tick order is:

1. Dispatch all tasks arriving during the tick, one at a time.
2. Sample server metrics.
3. Advance running tasks by one tick; completed tasks release resources.
4. Start queued tasks at the next tick.

When a task is assigned, the server immediately attempts to start queued work at the current tick. A task that starts at tick `t` and finishes during that tick receives `finish_tick = t + 1`.

A shadow simulation must use the same event order. In particular, a candidate that fits immediately may begin processing during the current tick.

### 5.3 The current simulator does not divide one server-speed budget among concurrent tasks

In the current implementation, each running task's remaining work is reduced by `server.speed` on each tick. CPU and memory demands determine whether tasks can run concurrently; the speed value is applied independently to each running task.

This is the simulator's current execution model. V2 must reproduce it exactly when comparing against the existing simulator. Do not silently replace it with a shared-CPU model in the same experiment.

A shared-resource contention model may be a separate future simulator extension, but it would change the environment and must be applied consistently to every policy.

### 5.4 Load signal and true utilisation are different quantities

The implementation distinguishes:

- True utilisation: resources held by running tasks, bounded by 100%.
- Load: resources held by running plus queued tasks, which can exceed 100%.

The balancer's current observed signal can include queued demand. Evaluation separately logs true utilisation. Preserve this distinction in V2 and in plots.

### 5.5 Task work is currently hidden information from a real scheduler's perspective

The current `Task` object contains `cpu_demand`, `mem_demand`, and the generated actual `work`. The server's internal task-run objects also contain exact remaining work.

The simulator needs actual work to execute tasks. A real load balancer generally does not know a newly submitted task's exact future execution time, nor does it know the exact remaining service time of a running job.

**Do not let the practical V2 policy read `task.work` or exact internal remaining work.** If it does, it is using oracle information and the comparison overstates deployable performance.

Use an immutable scheduler-facing task descriptor and server snapshot that contain only information a scheduler could know. Keep an oracle policy or oracle forecast strictly separate and label it as an upper-bound diagnostic.

### 5.6 CPU and memory demands do not currently predict task work

In the current workload generator, CPU demand, memory demand, and work are sampled from separate random streams. Work is lognormally distributed and independent of the resource demands.

Therefore, a model cannot infer an individual task's actual duration from CPU and memory requirements alone in the existing workload. A useful practical task-duration estimate requires additional observable information, such as a task class, job type, historical class runtime, or a caller-provided estimate.

Add this information in a new workload scenario. Do not pretend that CPU and memory alone reveal task duration in the current synthetic generator.

### 5.7 The current code already provides a useful insertion point

The policy contract is `select(servers, task) -> server_index`, and the simulator calls it for each arriving task. Since each assignment is applied before the next task arriving in the same tick is dispatched, later decisions in the same tick see earlier assignments in the live server state.

V2 should preserve this sequential visibility. Its forecast must not mutate live state while comparing candidates.

---

# Part III — Proposed V2 design

## 6. New research question and hypothesis

### Research question

Can task-specific completion-time prediction, adjusted for prediction uncertainty, improve task placement across heterogeneous cloud servers compared with conventional load-balancing policies?

### Primary hypothesis

A policy that selects a server using the predicted completion-time distribution of the incoming task will reduce response time and tail/SLA violations compared with task-agnostic load-balancing policies, while maintaining throughput.

### Secondary hypothesis

When task-duration estimates are imperfect and servers differ in prediction error or workload volatility, incorporating calibrated completion-time uncertainty will improve decisions over an otherwise identical earliest-completion-time (ECT-only) policy.

### Important distinction

The first hypothesis tests **task-aware completion-time prediction**. The second tests the incremental value of **uncertainty**. The second cannot be claimed merely because V2 beats Round Robin or Weighted Metric. The main ablation is uncertainty-aware ECT versus ECT-only.

## 7. V2 architecture at a glance

```text
Incoming task descriptor
        |
        v
Task/service-time estimator
        |
        v
For each feasible server:
    Build a read-only server forecast snapshot
    Append candidate behind existing FIFO work
    Run shadow queue projection
    Estimate completion-time distribution
        |
        v
Calculate mean completion time + tail-risk penalty
        |
        v
Choose lowest-cost server
        |
        v
Return server index; simulator performs the real assignment
        |
        v
When task completes, update service-time/error history
```

The three primary V2 components are:

1. **Task/service-time estimator:** estimates how much work an incoming task is likely to require using visible task metadata and historical observations.
2. **Shadow queue completion-time estimator:** predicts when the candidate will finish on each server by replaying the server's queue rules on a copy of its observable state.
3. **Uncertainty-aware decision engine:** estimates the distribution of completion time and applies a soft tail-risk penalty.

---

## 8. Component A — A scheduler-safe information interface

This is a correctness requirement, not optional cleanup.

### 8.1 Separate execution state from scheduling-visible state

The simulator needs exact task work to execute tasks. The policy should receive only a safe, immutable view.

Suggested types (names are illustrative):

```python
@dataclass(frozen=True)
class TaskRequest:
    task_id: int
    arrival_tick: int
    cpu_demand: float
    mem_demand: float
    task_class: str | None
    estimated_work: float | None

@dataclass(frozen=True)
class ActiveTaskView:
    task_id: int
    cpu_demand: float
    mem_demand: float
    task_class: str | None
    estimated_total_work: float | None
    elapsed_ticks: int

@dataclass(frozen=True)
class QueuedTaskView:
    task_id: int
    cpu_demand: float
    mem_demand: float
    task_class: str | None
    estimated_work: float | None

@dataclass(frozen=True)
class ServerView:
    server_id: int
    cores: float
    mem_gb: float
    speed: float
    running: tuple[ActiveTaskView, ...]
    queue: tuple[QueuedTaskView, ...]  # preserve exact FIFO order
    cpu_pct: float
    mem_pct: float
    cpu_load_pct: float
    mem_load_pct: float
```

`TaskRequest`, `ActiveTaskView`, `QueuedTaskView`, and `ServerView` must not expose:

- `Task.work` (actual generated work).
- `TaskRun.remaining` (exact remaining work).
- Any future completion tick or hidden simulator outcome.

The simulator retains the real `Task` and `TaskRun` objects internally. It constructs safe views for the policy at decision time.

### 8.2 Preserve policy fairness

All policies should receive the same scheduler-visible information in a given experiment. Existing policies may ignore fields they do not use. The V2 policy must not receive privileged information that the baselines are denied, except in a separately labelled oracle experiment.

The `ServerView` should preserve the live CPU, memory, load, and queue statistics needed by existing baselines. A common interface avoids maintaining one simulator for V1 and another for V2.

### 8.3 Read-only guarantee

The V2 policy and forecasting components must be pure with respect to live simulator state:

- They may construct local copies/snapshots.
- They may update their own predictor history after a task completes through an explicit callback or event.
- They may not mutate a live server, queue, task run, resource reservation, or simulator clock during candidate evaluation.

Keep or extend the existing policy contract test that verifies server state is unchanged after `select`.

---

## 9. Component B — Estimate task work without oracle leakage

### 9.1 Why a visible duration estimate is necessary

The existing workload generator samples task work independently of CPU and memory demand. A scheduler that sees only CPU and memory cannot infer the actual work of an individual task from those fields.

V2 therefore needs one of the following observable inputs:

- A declared task/job class (for example, short, medium, long, CPU-oriented, memory-oriented).
- A caller-provided estimated duration or work hint.
- Historical runtime estimates for a known service or task class.

The best first implementation is a **task-class-conditioned service-time model**.

### 9.2 Recommended task classes for the extended workloads

Introduce a visible `task_class` field in the new workload generator. For example:

| Class | Example behaviour | Scheduler information |
|---|---|---|
| Short | Short processing duration | Class ID and historical duration estimate |
| Medium | Moderate duration | Class ID and historical duration estimate |
| Long | Long processing duration | Class ID and historical duration estimate |
| CPU-heavy | Higher CPU reservation/demand | Class ID and CPU/memory requirements |
| Memory-heavy | Higher memory reservation/demand | Class ID and CPU/memory requirements |

The classes should be tied to distributions with meaningful differences in actual work and/or resource demands. Keep the original stable and bursty generator intact for direct V1 comparability; add these as new scenarios or a versioned generator.

### 9.3 Practical service-time estimate

For task class `c`, maintain a model based only on tasks that have completed before the current scheduling decision:

\[
\widehat{W}(T)=\widehat{E}[W\mid c(T)]
\]

A more detailed model may also condition on other public features, but do not introduce a complex predictor before establishing a baseline.

The estimate can be obtained from:

- A historical mean/median by task class.
- A rolling class-specific distribution.
- A caller-supplied duration estimate when available.
- A cluster-wide prior when the class has insufficient observations.

For server `i`, the expected processing ticks for a known amount of work are approximately:

\[
\widehat{P}_i(T)=\left\lceil\frac{\widehat{W}(T)}{speed_i}\right\rceil
\]

The shadow simulator should use the same discrete tick progression as the actual simulator rather than relying only on this closed-form expression when the task must wait behind existing work.

### 9.4 Cold start and sparse history

At the beginning of a run there may be no completed tasks. Do not use future outcomes to populate the estimator.

Use this fallback order:

1. Class-specific prior learned from a separate training set, if the experiment explicitly models a warm-start deployment.
2. Class-specific configured prior derived from the workload specification.
3. Cluster-wide historical prior from tasks completed earlier in the same run.
4. A conservative global default from training/validation data, frozen before test evaluation.

Evaluate both cold-start and warm-start behaviour if the system is meant to adapt online.

### 9.5 Store the estimate at task admission

When a task is accepted, persist the estimate used at its arrival in its execution metadata. This makes it possible to reconstruct what the scheduler believed about the task when it made the decision.

Do not retroactively replace the prediction with a more accurate estimate learned after the task has completed.

### 9.6 Running tasks require survival-conditioned remaining-time estimates

A running task is known not to have completed yet. This is useful information. Simply calculating:

`estimated_remaining = max(estimated_total_work - elapsed_ticks * speed, 0)`

can be wrong: a task whose estimated duration has already elapsed but which is still running must not be treated as finished in the forecast.

A stronger estimator computes the remaining work/time conditional on the task still being active:

\[
E[W-a\mid W>a, c]
\]

where `a` is the amount of work already processed (or the corresponding elapsed service time), and `c` is the task class.

For a first version, use a simple lower-bounded remaining-tick estimate and clearly document it. A later version can use the empirical class-conditioned survival distribution. The exact internal `TaskRun.remaining` must never be used by the practical policy.

---

## 10. Component C — Shadow queue completion-time prediction

### 10.1 What it estimates

For an incoming task `T` and candidate server `i`, estimate:

\[
ECT_i(T)=\text{predicted finish time of T}-\text{arrival time of T}
\]

This is the task's predicted response time, including queue wait and processing time.

Do not reduce it to `queued_work / server_capacity`. That shortcut cannot reproduce resource fragmentation, multi-resource fit constraints, or strict FIFO head-of-line blocking.

### 10.2 Required inputs

The projection needs:

- Server cores, memory capacity, and speed.
- Current running jobs and their CPU/memory reservations.
- Estimated remaining service for running jobs.
- Existing queued jobs in their exact FIFO order.
- Each queued job's resource demands and estimated service work.
- The incoming task's resource demands and estimated service work.
- Current simulator tick.

### 10.3 Projection procedure

For each feasible server:

1. Create a local shadow copy of its scheduling-visible state.
2. Preserve the set of running tasks and current resource reservations.
3. Preserve the existing FIFO queue order.
4. Append the candidate after all work already in the queue.
5. Apply the same FIFO queue-start rule as the real server.
6. Advance every projected running job by the server's configured speed once per simulated tick.
7. Release CPU and memory when a projected job completes.
8. Start queued jobs at the same point in the tick as the real simulator.
9. Continue until the candidate completes or a safe projection horizon is reached.
10. Return the predicted response time and diagnostic details (predicted start tick, finish tick, wait, number of jobs ahead, and projection status).

### 10.4 Pseudocode

```python
def predict_candidate_completion(server_view, candidate, now, duration_model):
    state = make_shadow_state(server_view, duration_model)
    candidate_run = make_shadow_run(candidate, duration_model)
    state.fifo_queue.append(candidate_run)

    # Server.assign() attempts to start queued work during the dispatch tick.
    start_queued_fifo(state, tick=now)

    for tick in range(now, now + MAX_PROJECTION_TICKS):
        # Match Server.step(): every running task advances by server.speed.
        completed = advance_running_tasks(state, server_speed=state.speed)

        if candidate_run in completed:
            finish_tick = tick + 1
            return Prediction(
                response_time=finish_tick - candidate.arrival_tick,
                start_tick=candidate_run.start_tick,
                finish_tick=finish_tick,
                status="predicted",
            )

        release_resources(state, completed)

        # Match the real simulator: queued tasks may start at the next tick.
        start_queued_fifo(state, tick=tick + 1)

    return Prediction(status="projection_horizon_exceeded")
```

This is conceptual pseudocode. The real implementation must match the repository's exact resource accounting and tick semantics.

### 10.5 FIFO and resource-fit details

The queue-start routine should reproduce the real server behaviour:

```python
def start_queued_fifo(state, tick):
    while state.queue:
        head = state.queue[0]
        if not fits_available_cpu_and_memory(state, head):
            break  # strict FIFO: do not let later tasks overtake
        run = state.queue.popleft()
        reserve_resources(state, run)
        run.start_tick = tick
        state.running.append(run)
```

The actual implementation must also handle simultaneous completions, floating-point resource accounting, and the current server's exact queue bookkeeping.

### 10.6 Same-tick arrivals

The simulator dispatches tasks arriving in the same tick one at a time. Each real assignment updates the target server before the next task is selected.

Therefore, each V2 decision should build its snapshot from the state after all earlier assignments in that tick. Do not forecast all same-tick tasks independently from the same stale snapshot.

### 10.7 Future arrivals

The initial projection can focus on the candidate and tasks already ahead of it. Under the current strict FIFO queue, future arrivals are appended behind the candidate and cannot overtake it. Also, in the current simulator, each running task progresses at a fixed per-task rate independent of the number of other running tasks, subject to CPU/memory reservations.

This makes a candidate-focused forecast reasonable under the current simulator model. If the simulator later introduces shared CPU contention, preemption, non-FIFO queues, or priority scheduling, future arrivals may change the candidate's completion time and the projection must be updated.

### 10.8 Feasibility handling

Only consider a server if the task can ever fit its total CPU and memory capacity. This is different from whether it can fit immediately.

- **Can ever fit:** task CPU demand is no greater than server cores and task memory demand is no greater than server memory capacity.
- **Can fit now:** current running reservations plus the task's demands fit available CPU and memory.

A task that cannot ever fit must not be assigned to that server. If no server can ever fit a task, use a common, explicit handling rule for every policy (for example, mark it infeasible/rejected). Do not let one algorithm silently crash or discard it.

### 10.9 Projection limits and runtime cost

The current cluster has only five servers, so evaluating every feasible server should be tractable. However, a server may have a long queue during overload.

Add:

- A maximum projection horizon.
- A clear status for predictions that exceed the horizon.
- A safe high-cost fallback for those cases (never a falsely optimistic completion time).
- Logging of projection steps and wall-clock decision cost.

Initially use exact tick-by-tick projection for semantic correctness. Optimise with event jumps only after tests prove that the optimised projection is equivalent to the tick-based reference.

---

## 11. Component D — Estimate uncertainty in completion time

### 11.1 Replace the original risk target

The original risk score estimates CPU or memory threshold exceedance. V2 should estimate uncertainty in the actual decision outcome: the candidate task's completion time on each server.

For each server `i` and candidate task `T`, the desired output is a predictive distribution:

\[
R_i(T) \sim \widehat{F}_i(\cdot\mid T,\text{visible server state})
\]

where `R_i(T)` is the task's response time if assigned to server `i` under the simulator's model.

### 11.2 Recommended first practical implementation: empirical duration uncertainty

Use a task-class-conditioned empirical distribution of observed service durations, with server speed accounted for. When a task completes, the simulator can record its observable start-to-finish service ticks. The scheduler's model may update after completion, but cannot use that outcome before the task was assigned.

For a practical deployment simulation:

- Use public task class and resource metadata.
- Learn from previously completed tasks only.
- Maintain empirical service-time samples or a compact distribution per class.
- Use a pooled global distribution when class-specific data is sparse.
- For active jobs, condition the remaining-time distribution on the fact that the job is still running.

### 11.3 Monte Carlo shadow projection (recommended research target)

A stronger implementation samples plausible service durations for the candidate and relevant existing queued/running jobs, then repeats the shadow queue projection many times.

For server `i`, this produces:

\[
\{R_i^{(1)}(T),R_i^{(2)}(T),\ldots,R_i^{(M)}(T)\}
\]

From those samples calculate:

\[
\widehat{\mu}_i(T)=\frac{1}{M}\sum_{m=1}^{M}R_i^{(m)}(T)
\]

\[
\widehat{Q}_{0.90,i}(T)=\operatorname{quantile}_{0.90}\left(\{R_i^{(m)}(T)\}_{m=1}^{M}\right)
\]

and, where the SLA is relevant:

\[
\widehat{P}_{SLA,i}(T)=\frac{1}{M}\sum_{m=1}^{M}\mathbf{1}[R_i^{(m)}(T)>R_{SLA}]
\]

The Monte Carlo samples must be generated from the service-time model available to the scheduler, not from the simulator's hidden actual `work` values.

A practical starting point is 100–200 samples per candidate server, then profile the decision cost. Use fixed, policy-owned random streams or deterministic quasi-random samples so that one policy's prediction draws never perturb workload generation or another policy's random decisions.

### 11.4 Prediction-error calibration as an alternative/extension

A simpler alternative is to store each selected task's predicted response time at dispatch and, after completion, calculate:

\[
e_j=R_j^{actual}-\widehat{R}_j^{dispatch}
\]

The empirical upper quantile of these residuals can provide an underprediction penalty. This should be conditioned on task class and, where data permits, server or predicted-latency band.

Important caveat: residuals are observed only for the server actually selected. Per-server residual histories can therefore be selection-biased and may have different task mixes. Use pooled/class-conditioned history first, shrink local estimates toward pooled estimates, and report this limitation. Do not claim counterfactual calibration for servers that did not receive the task.

### 11.5 Hierarchical shrinkage for sparse per-server history

If a local server/class quantile is estimated from very few completed tasks, it will be unstable. Blend it with a pooled estimate:

\[
q_{i,c}^{shrunk}=w_{i,c}q_{i,c}^{local}+(1-w_{i,c})q_c^{global}
\]

\[
w_{i,c}=\frac{n_{i,c}}{n_{i,c}+k}
\]

where `n` is the number of usable local observations and `k` is a smoothing constant selected on validation data.

This avoids making strong per-server claims from a handful of samples.

### 11.6 Cold-start behaviour

When no relevant prediction history exists, use the class prior or pooled distribution. If neither exists, use ECT-only (`uncertainty_penalty = 0`) rather than inventing a confident risk estimate.

The system should expose a diagnostic such as `uncertainty_samples`, `uncertainty_source`, and `uncertainty_confidence`.

### 11.7 Do not reuse the V1 ten-sample window blindly

Ten samples may be adequate for a simple rolling diagnostic but are too few for a stable 90th-percentile estimate. V2's error/service-time history should have its own configuration and should be evaluated for sample efficiency.

An initial engineering setting might retain up to 200 observations per class and require at least 30 local observations before trusting a local quantile; these are starting points only, not experimentally established optimal values. Tune them on validation seeds and freeze them before the final test.

---

## 12. Component E — Risk-sensitive completion-time objective

### 12.1 Recommended initial score

Use quantities in seconds:

\[
\boxed{J_i(T)=\widehat{\mu}_i(T)+\beta\max\left(0,\widehat{Q}_{0.90,i}(T)-\widehat{\mu}_i(T)\right)}
\]

where:

- `μ̂_i(T)` is the predicted mean response time.
- `Q̂90_i(T)` is its predicted 90th-percentile response time.
- `β` is a risk-aversion parameter in `[0,1]` (or a wider range only if validation justifies it).
- `J_i(T)` is a predicted cost in seconds.

Interpretation:

- `β = 0`: ECT-only; uncertainty has no effect.
- `β > 0`: penalise candidate/server pairs whose upper-tail completion time is materially worse than their mean.
- If every server has the same tail premium, that common value does not change the ranking. The score naturally avoids the V1 failure of adding an almost-constant probability term that contributes no useful distinction.

This score is a recommended first objective, not a proven best formula. Keep ECT-only as an explicit ablation.

### 12.2 Optional SLA-specific objective

If the principal objective is SLA compliance, test this as a separate alternative:

\[
J_i^{SLA}(T)=\widehat{\mu}_i(T)+\lambda R_{SLA}\widehat{P}_{SLA,i}(T)
\]

Here, `λ` determines how much extra cost is assigned to the predicted probability of violating the SLA. This has units of seconds because `R_SLA` is in seconds.

Do not include both the q90 penalty and the SLA-probability penalty in the first implementation unless there is a clear reason. Too many weights make it harder to isolate the mechanism and easier to overfit.

### 12.3 Why this is better than the V1 score conceptually

- The mean and tail estimate describe the same outcome: task response time.
- The quantities have a common unit.
- The score is task-specific.
- The forecast includes queue order and resource fit.
- Uncertainty contributes only through differences in the predicted completion-time distribution.
- There is no arbitrary CPU/memory probability cutoff in the core decision.

### 12.4 Selection rule

For each server that can ever fit the task:

1. Estimate the candidate's completion-time distribution.
2. Calculate `J_i(T)`.
3. Select the server with the smallest cost.
4. Break exact ties deterministically, for example by lower predicted mean response time and then lower server ID.

If every feasible projection exceeds the configured horizon, use a conservative deterministic fallback and log the condition. Never treat a failed projection as a zero-second completion.

---

# Part IV — Algorithm variants and ablations

## 13. Policies to implement

Keep all original policies and add these variants:

| Policy name | Description | Role |
|---|---|---|
| Round Robin | Original cyclic assignment | Existing baseline |
| Weighted RR | Original capacity-proportional assignment | Existing baseline |
| Random | Original seeded uniform assignment | Existing baseline |
| Least CPU | Original lowest CPU-load assignment | Existing baseline |
| P2C | Original two-choice assignment | Existing baseline |
| Weighted Metric | Original risk-free `L_i` policy | Key V1 ablation |
| Probabilistic V1 | Original normal-threshold risk policy | Original proposed method |
| ECT-only | Choose lowest predicted mean completion time | Key V2 ablation |
| Uncertainty-aware ECT | Choose lowest risk-adjusted completion-time cost | Main V2 proposal |
| Oracle ECT (optional) | Uses exact service durations/remaining work | Upper-bound diagnostic only; never a deployable baseline |

### 13.1 Why ECT-only is mandatory

If uncertainty-aware ECT beats Weighted Metric, that does not prove uncertainty helped. It may simply be the task-aware completion-time estimator that improved placement.

The core uncertainty claim requires:

\[
\text{Uncertainty-aware ECT} \quad\text{vs.}\quad \text{ECT-only}
\]

The only difference between these two policies should be the uncertainty penalty. Their task estimates, server snapshots, queue projection, candidate eligibility, and tie-breaking must be identical.

### 13.2 Why Oracle ECT is not a normal competitor

Oracle ECT may use actual task work and exact remaining work to quantify the upper bound of a perfect duration-information model. This helps answer whether the queue projection itself has potential if duration estimates were perfect.

It must be clearly marked **oracle / non-deployable**. Do not include it in the headline claim that V2 beats practical methods.

---

# Part V — New benchmark scenarios

## 14. Preserve the existing workloads

The original stable and bursty scenarios must remain unchanged for direct comparability with V1. Re-run all relevant policies on the same task list for each seed.

The original burst scenario intentionally reaches demand above total capacity. No load-balancing algorithm can remove the fundamental capacity deficit. A better policy may distribute waiting time more intelligently, but it cannot make the offered workload feasible without additional capacity, admission control, or autoscaling.

## 15. Add scenarios where task-aware uncertainty has a reason to help

### 15.1 Heterogeneous task sizes/classes

Add a workload with a visible task class and different service-time distributions. Include a mixture of short, medium, and long jobs, as well as CPU-heavy and memory-heavy resource profiles.

Purpose:

- Test whether the scheduler places tasks according to their resource requirements and predicted duration.
- Test whether the duration estimator can learn class-specific behaviour.
- Measure whether long tasks create head-of-line or resource-fragmentation effects.

Keep task class visible to every policy through the common task descriptor. Only policies designed to use it will benefit from it.

### 15.2 Heterogeneous background volatility / noisy neighbours

Add background work on selected servers. Some servers should have relatively stable background demand; others should experience bursty or correlated background demand.

The background trace must be generated once per scenario/seed and reused for every policy. It must affect the actual simulated server resources, not merely the reported metric.

Purpose:

- Create different volatility profiles across servers.
- Test the original motivating idea under conditions where risk may genuinely distinguish candidates.
- Test whether completion-time uncertainty predicts the consequences of noisy-neighbour interference.

Keep total offered load controlled or report it explicitly. Do not accidentally make one policy face a higher exogenous workload.

### 15.3 Stale telemetry

Introduce delayed server observations, for example 5, 15, and 30 seconds of telemetry delay.

Every policy in a given stale-telemetry experiment must receive the same information regime. If the V2 policy maintains a local dispatch ledger for tasks it has assigned since the last telemetry sample, document and expose that mechanism fairly.

Purpose:

- Model a real monitoring pipeline in which metrics arrive late.
- Test whether prediction and uncertainty help when observed server state is not current.

This is a later-stage scenario because it requires a clear definition of what information the scheduler can observe between telemetry updates.

### 15.4 Noisy duration estimates

Vary the quality of the task-duration metadata:

- No per-task estimate: use class/global prior only.
- Noisy estimate: provide an estimate with controlled multiplicative error.
- Good estimate: provide a relatively accurate public estimate.
- Oracle estimate: exact work, diagnostic only.

This separates the value of task awareness from the value of perfect information.

### 15.5 Keep mean demand matched where the comparison requires it

For stable versus bursty comparisons, continue matching mean offered load. For new scenarios, report both mean and peak offered load, and match mean demand when the goal is to isolate volatility rather than total demand.

---

# Part VI — Implementation plan

## 16. Suggested code structure

Keep the current modules and add focused V2 modules rather than rewriting the simulator wholesale.

```text
src/lbsim/
    config.py
    workload.py
    server.py
    metric_window.py
    scoring.py
    simulator.py
    evaluation.py

    scheduling_view.py              # immutable public Task/Server views

    estimators/
        service_time.py              # task-class duration estimates
        service_time_history.py      # online completed-service history
        completion_uncertainty.py    # empirical residual/quantile model

    forecasting/
        shadow_state.py              # local candidate state representation
        queue_projection.py          # FIFO/resource-aware projection
        monte_carlo_ect.py           # optional sampled completion distribution

    policies/
        ... existing policies ...
        earliest_completion.py       # ECT-only ablation
        uncertainty_aware_ect.py    # main V2 policy
        oracle_ect.py                # optional diagnostic, isolated

experiments/
    run_all.py                       # V1 + V2 policy matrix
    run_v2.py                        # focused V2 evaluation
    sensitivity_v2.py                # validation-only tuning
    plots.py

tests/
    test_scheduling_view.py
    test_queue_projection.py
    test_service_time_estimator.py
    test_uncertainty_calibration.py
    test_v2_policy.py
```

This is a suggested layout; it should be adapted to the repository's existing packaging conventions.

## 17. Implementation stages

### Stage 0 — Freeze and reproduce V1

- Create a version tag or branch for the current V1 code and results.
- Run the original test suite.
- Reproduce the original primary result tables and figures.
- Save the exact configuration, commit hash, environment, and output files.
- Do not change V1 formulas or baselines while implementing V2.

**Exit condition:** V1 remains reproducible from a clean checkout.

### Stage 1 — Introduce safe scheduling views

- Create immutable `TaskRequest` and `ServerView` structures.
- Include only public task metadata and estimated durations.
- Include existing FIFO queue order and estimated active/queued job state.
- Hide actual work and exact remaining work from practical policies.
- Adapt the existing policies to use the safe view without changing their decisions.
- Add tests proving baseline decisions are unchanged.

**Exit condition:** Existing policy assignments and V1 result metrics remain identical (or any difference is fully explained and fixed before continuing).

### Stage 2 — Build and validate the shadow queue simulator

- Implement local shadow-state construction.
- Implement exact FIFO head-of-line blocking.
- Implement CPU and memory reservation/release.
- Match current dispatch/sample/step tick order.
- Include multiple running tasks and simultaneous completions.
- Add a maximum projection horizon and explicit failure status.
- Keep forecasting pure and read-only.

**Exit condition:** In oracle test fixtures with exact remaining work supplied to the test harness, predicted start/finish ticks match the real server simulator exactly.

### Stage 3 — Implement ECT-only

- Add a public task-duration estimate.
- Add task classes or an explicit estimated-work hint to new workloads.
- Estimate active-task remaining time without reading exact remaining work.
- Implement candidate completion-time prediction for every feasible server.
- Select the lowest predicted mean completion time.

**Exit condition:** ECT-only is deterministic, does not leak actual work, and passes queue/feasibility tests.

### Stage 4 — Add uncertainty estimation

- Maintain class-conditioned empirical service-time distributions or prediction residuals.
- Update only after a task completes.
- Add pooled fallback and local-estimate shrinkage.
- Add Monte Carlo projections if profiling allows.
- Compute mean and q90 completion estimates.
- Implement the V2 soft risk penalty.

**Exit condition:** Predictions can be logged and evaluated prequentially; no future information is used.

### Stage 5 — Extend workloads

- Add heterogeneous task classes.
- Add per-server background volatility.
- Add duration-estimate quality variants.
- Add stale telemetry only after the information model is precisely defined.
- Preserve the original stable/bursty scenarios unchanged.

**Exit condition:** Every scenario has deterministic generation and matched workload inputs across policies.

### Stage 6 — Evaluate and freeze

- Use separate development, validation, and final test seeds.
- Tune only on validation seeds.
- Freeze all parameters and code before the final test.
- Run paired experiments against all original policies and V2 ablations.
- Report every metric, effect size, confidence interval, and per-seed result.

**Exit condition:** The main claim is supported by final held-out results, or the result is reported as null/negative.

---

# Part VII — Experimental design and success criteria

## 18. Main policy matrix

At minimum, evaluate:

- All seven original policies.
- ECT-only.
- Uncertainty-aware ECT.
- Oracle ECT as an optional upper-bound diagnostic.

That is nine deployable/comparable policies, plus the optional oracle diagnostic.

For each workload and seed, every policy receives the same generated task stream, same server specifications, same background workload (when present), same arrival schedule, and same evaluation horizon.

## 19. Seeds and data separation

Five seeds were adequate for an initial feasibility study but are weak for detecting small effects. Use more seeds for V2.

Recommended protocol:

- Development seeds: used to debug code and understand failure modes.
- Validation seeds: used to select model settings, history size, Monte Carlo count, and risk weight.
- Final test seeds: never used for parameter tuning.
- Aim for 30–50 independent final test seeds per benchmark configuration if computationally feasible.

The exact counts may be adjusted based on runtime and a pre-study power/effect-size assessment. Do not choose test seeds after looking at their outcomes.

For online adaptation, a task may update the model only after it completes. The task's own outcome must not influence the prediction used to dispatch that same task.

## 20. Metrics to report

Keep the original metrics for comparability and add metrics that diagnose V2.

| Metric | Meaning | Direction |
|---|---|---|
| Mean response time | Arrival to completion, including waiting | Lower |
| Median response time | Typical task response | Lower |
| p95 response time | Tail latency | Lower |
| p99 response time | Extreme tail latency | Lower |
| SLA violation rate | Fraction with response time above the frozen SLA | Lower |
| Throughput | Completed tasks per defined simulation makespan | Higher |
| Goodput | Tasks completed within SLA per arrival-horizon second | Higher |
| True CPU utilisation | Actual running CPU use | Context, not always lower |
| True memory utilisation | Actual running memory use | Context, not always lower |
| Overload frequency | Fraction of intervals above frozen load/utilisation thresholds | Lower, interpreted carefully |
| Queue length / backlog | Waiting tasks and queue growth | Lower |
| Drain time | Time required to finish remaining work after arrivals stop | Lower |
| Prediction MAE | Absolute error of predicted vs actual response time | Lower |
| q90 coverage | Fraction of outcomes below predicted q90 | Near 90% |
| q90 width / tail premium | Width or distance between central and upper-tail prediction | Lower subject to calibration |
| Candidate-ranking regret | Difference between selected and best counterfactual completion time | Lower |
| Decision runtime | Time spent selecting a server | Lower |

### 20.1 Preserve original metric windows

The original report calculates interval metrics over the common arrival horizon and task metrics over completed tasks. Preserve these definitions for direct comparison.

Also report drain time and unfinished tasks. Do not let a max-tick cutoff silently make a policy look better by omitting its slowest tasks.

If an unfinished task exists at the hard cutoff, report it explicitly and define how it contributes to SLA/throughput analyses.

### 20.2 Counterfactual ranking regret

The simulator can calculate an offline oracle after a decision using the actual hidden task work and actual server state. This information is for evaluation only.

For each incoming task, compute the actual-model completion time on every candidate server in isolated counterfactual shadow executions. Then calculate:

\[
Regret(T)=ECT_{selected}^{oracle}(T)-\min_{i\in feasible}ECT_i^{oracle}(T)
\]

Report mean and percentile regret. The scheduling policy must never receive these oracle values.

This metric directly tests whether the forecast ranks candidate servers usefully, rather than merely predicting aggregate overload frequency.

## 21. Statistical comparisons

For each matched seed, calculate paired differences between V2 and each baseline:

\[
\Delta_s = Metric_{V2,s}-Metric_{baseline,s}
\]

For metrics where lower is better, negative values favour V2. For throughput/goodput, positive values favour V2.

Report:

- Mean paired difference.
- Median paired difference.
- Standard deviation across seeds.
- Paired confidence interval (bootstrap over seeds is appropriate as a practical option).
- Number and percentage of seeds won.
- Relative percentage change where meaningful.
- Effect size and practical significance.

If formal significance tests are conducted across multiple baselines/metrics, account for multiple comparisons (for example, Holm correction). Do not select one favourable metric after looking at the results and present it as the primary outcome.

## 22. Define the success condition before the final run

The phrase "better on all benchmarks" needs a precise operational definition.

A strict universal win would require V2 to outperform every baseline on every primary metric in every workload. That may be unrealistic because metrics can trade off and overloaded systems have hard capacity limits.

A defensible pre-registered target is:

1. **Primary metrics:** V2 improves mean response time, p95 response time, and SLA violation rate against the strongest practical baseline on each target benchmark, with paired uncertainty reported.
2. **Guardrails:** V2 does not materially reduce throughput/goodput or create a substantial increase in overload frequency, queue growth, or drain time.
3. **Across-seed robustness:** Improvements are not driven by one or two favourable seeds.
4. **Incremental uncertainty value:** Uncertainty-aware ECT improves over ECT-only on at least the benchmark conditions where predicted uncertainty is expected to vary meaningfully across candidates.
5. **No hidden information:** The practical policy uses only scheduler-visible task and server information.
6. **Held-out validity:** The final test seeds were not used for parameter selection.

If the goal is a literal win over every original policy on every workload, report that as an aspirational target, not an assumption or guaranteed outcome.

## 23. Avoid overfitting the parameter search

- Tune `beta`, quantile level, history size, Monte Carlo samples, and task-duration model only on validation seeds.
- Use a small, declared search space.
- Keep the final evaluation SLA and workload definitions frozen.
- Do not change benchmark thresholds to make overload appear lower.
- Do not repeatedly rerun the final test set while changing settings.
- Include ECT-only at every relevant parameter setting so the risk component remains isolated.

---

# Part VIII — Testing and correctness requirements

## 24. Required unit and contract tests

### Scheduling-view and information-leakage tests

- `TaskRequest` does not expose actual `work`.
- `ServerView` does not expose exact `TaskRun.remaining`.
- The policy cannot access hidden future finish ticks.
- The practical policy uses `estimated_work`/class estimates only.
- Oracle-only access is isolated to a clearly named diagnostic path.

### Shadow queue tests

- Candidate fits immediately and starts during the current dispatch tick.
- Candidate waits behind an existing queued task.
- A non-fitting FIFO head blocks later tasks even if they would fit.
- CPU is the limiting resource.
- Memory is the limiting resource.
- Both CPU and memory are limiting resources.
- Multiple tasks run concurrently when reservations allow it.
- Multiple tasks complete on the same tick.
- Resources are released at the correct point in the tick.
- Queued tasks start at `tick + 1` after completions, matching the real server.
- Candidate is appended after all existing queue entries.
- Earlier same-tick assignments are visible to later same-tick decisions.
- Infeasible tasks are handled consistently.
- Projection horizon exhaustion is explicit and conservative.

### Forecast accuracy tests

- Under an exact-duration test fixture, the oracle shadow projection matches the real simulator's start/finish ticks.
- A public estimated duration is used instead of actual hidden work.
- Long-running tasks that are still active are not forecast as already finished.
- Survival-conditioned remaining-time estimates are lower-bounded by the observed active state.
- Prediction records are stored at dispatch time and are not overwritten later.

### Uncertainty estimator tests

- Empty history uses fallback prior safely.
- Sparse local history shrinks toward pooled history.
- Quantiles are deterministic for a fixed sample history.
- Only completed prior tasks update the history.
- Current task outcome cannot update its own prediction.
- Calibration is evaluated on future/held-out outcomes.
- Quantile estimator handles ties and small sample counts.

### Policy tests

- ECT-only and uncertainty-aware ECT use identical projections.
- With `beta = 0`, uncertainty-aware ECT must make the same decisions as ECT-only (decision-for-decision identity).
- When every candidate has the same tail premium, the premium must not arbitrarily change their ranking.
- Increasing risk aversion should never reward a candidate solely because its upper-tail uncertainty increases.
- Deterministic tie-breaking is stable.
- `select()` does not mutate live server state.
- Random streams remain independent of workload generation.

### Regression and fairness tests

- Existing V1 policies preserve their decisions after the scheduler-view refactor.
- Original V1 benchmark results remain reproducible within the same environment.
- Every policy sees identical task and exogenous-background traces for a matched run.
- Server state is reset between runs.

---

# Part IX — Risks, limitations, and guardrails

## 25. Model uncertainty is not the same as workload randomness

The term "uncertainty" should be defined precisely in V2. It may include:

- Uncertainty about task service duration.
- Uncertainty about remaining duration of active jobs.
- Uncertainty from queue-state estimates.
- Telemetry staleness or incomplete state.
- Exogenous background workload variation.

Do not combine all of these into one unlabelled number. Identify which sources are modelled and which are omitted.

## 26. Current simulator's service model is simplified

Each running task progresses at a fixed per-server speed every tick, while CPU and memory reservations constrain concurrency. This does not model all details of a real operating system or cloud runtime, where tasks may share CPU time, experience interference, throttle, migrate, or block on I/O.

The V2 claim should initially be limited to the simulator's defined execution model. A shared-resource or production-like model can be a separate validation extension.

## 27. The empirical duration model can be biased

Only tasks that were actually assigned to a server produce observed outcomes there. A per-server prediction-error model may therefore see a selected subset of task classes and sizes.

Mitigations:

- Condition on public task class/features.
- Pool data when local observations are sparse.
- Use shrinkage rather than trusting tiny per-server samples.
- Report sample counts by server and class.
- Evaluate cold-start and warm-start performance.
- Do not imply that a selected-server residual history provides counterfactual outcomes for every server.

## 28. A greedy earliest-completion policy can still make poor global decisions

The ECT policy optimises the candidate task's own predicted completion time. It does not automatically optimise every task's completion time, total cluster makespan, fairness, or energy use.

In the current FIFO/reservation model, appending a task behind existing queued work and applying fixed per-task speed limits how much it can delay earlier work. In a more realistic shared-resource model, assigning a task to one server may slow several existing tasks.

Later work can examine a marginal-cost objective over the queue, such as the change in predicted total completion/tardiness cost after adding a task. Treat this as a separate policy variant because it changes the optimisation target and is more computationally expensive.

## 29. Bursts above capacity cannot be solved by placement alone

When offered demand exceeds total processing capacity, queueing is unavoidable. V2 may reduce the damage by placing work more effectively, but it cannot guarantee that all tasks meet the SLA.

A complete cloud solution may also need:

- Admission control or load shedding.
- Autoscaling or additional capacity.
- Priority classes and deadline-aware scheduling.
- Backpressure to upstream services.

These mechanisms are outside the first V2 scope and should not be quietly mixed into the comparison.

## 30. Be precise about calibration claims

The V1 report's predicted-vs-observed aggregate values (for example, 0.74 vs 0.72 under bursts) are useful diagnostics, but they do not by themselves establish full probabilistic calibration across all servers, task classes, load levels, and time periods.

V2 should report quantile coverage and, if using SLA probability, reliability diagrams or calibration tables across bins and scenarios. A well-calibrated q90 should contain approximately 90% of the relevant held-out outcomes, subject to sampling uncertainty.

---

# Part X — Recommended experiment order

## 31. Run these experiments in this order

### Experiment 1 — Validate the shadow simulator in oracle mode

Use exact remaining work in unit tests only. Prove that the shadow queue projection reproduces the real simulator's finish tick under controlled states.

This tests the queue simulator, not an algorithmic improvement.

### Experiment 2 — ECT-only versus Weighted Metric on original stable/bursty tasks

Use a scheduler-visible duration estimate. Since current `work` is independent of CPU and memory, use a public global/class prior rather than actual task work.

This determines whether task-aware completion-time projection helps even before uncertainty is introduced.

### Experiment 3 — Oracle ECT as an upper-bound diagnostic

Allow exact task work and exact remaining work in this isolated experiment. Compare Oracle ECT with practical ECT-only.

This measures the potential value of better service-time information. It is not a deployable result.

### Experiment 4 — Uncertainty-aware ECT versus ECT-only

Use empirical or Monte Carlo completion-time uncertainty. Keep the task estimator and queue projection exactly the same in both variants.

This is the key uncertainty ablation.

### Experiment 5 — Heterogeneous task-class workload

Add visible job classes and class-conditioned service distributions. Measure whether task-specific duration estimates help.

### Experiment 6 — Heterogeneous background volatility

Inject controlled per-server background work. Measure whether predictive uncertainty separates otherwise similar servers.

### Experiment 7 — Stale telemetry

Only after the preceding experiments are stable, introduce delayed state and a clearly documented information model.

This sequence avoids spending time tuning an uncertainty model before verifying that the completion-time estimator itself is correct and useful.

---

# Part XI — Proposed algorithm in compact form

## 32. Uncertainty-aware ECT algorithm

```text
INPUT:
    incoming scheduler-visible task T
    scheduler-visible snapshots of servers 1..N
    service-time estimator M
    completion-time uncertainty model U
    risk weight beta
    projection horizon H

CANDIDATES:
    servers on which T can ever fit in CPU and memory

FOR each candidate server i:
    1. Build a local shadow state from the immutable server snapshot.
    2. Estimate service durations for existing queued and running jobs.
    3. Estimate service duration distribution for T.
    4. Append T to the end of the current FIFO queue.
    5. Run M shadow queue projections using the simulator's exact tick,
       resource reservation, completion, and FIFO semantics.
    6. If the projections complete:
           mean_i = mean predicted response time
           q90_i  = 90th percentile predicted response time
       Else:
           mark projection failure and use conservative fallback.
    7. risk_premium_i = max(0, q90_i - mean_i)
    8. cost_i = mean_i + beta * risk_premium_i

SELECT:
    feasible server with minimum cost_i
    ties: lower mean_i, then lower server ID

AFTER TASK COMPLETES:
    update service-time and prediction-error histories
    using only data now observable from the completed task
```

For a deterministic ECT-only ablation, use one expected-duration projection and set `beta = 0`.

---

# Part XII — What to claim in the final report

## 33. Claims that are justified before V2 experiments

It is justified to say:

- V1's uncertainty term did not improve over its weighted-metric ablation in the reported simulation.
- The V1 risk score was reasonably aligned with aggregate overload frequency in the report's diagnostic, but it did not provide useful candidate ranking in many decisions.
- The V1 admission filter was brittle and the sensitivity analysis suggests removing it is worth testing.
- The V1 simulator has task resource demands, processing work, per-server FIFO queues, and heterogeneous server speeds that can support a task-aware completion-time projection.
- The current simulator's task work is hidden information for a practical scheduler and must be replaced by an estimate in the deployable policy.

## 34. Claims that are not justified until experiments finish

Do not state as facts that:

- V2 beats all baselines.
- V2 improves all metrics.
- Monte Carlo uncertainty is better than empirical residual quantiles.
- A 90th-percentile objective is optimal.
- The method is production-ready.
- A simulation result proves performance on real cloud traces.

Use language such as "we hypothesise", "we evaluate", or "the results indicate" until final held-out evidence supports stronger wording.

## 35. Suggested V2 contribution statement (revise after results)

> We extend a threshold-risk-based load balancer into an uncertainty-aware predictive task-placement method. For each incoming task, the scheduler estimates completion time on each feasible server by projecting the server's existing running and queued work under the simulator's resource reservation and FIFO semantics. It then incorporates uncertainty in the predicted completion-time distribution through a soft tail-risk penalty. We compare the resulting policy against conventional load-balancing baselines and an ECT-only ablation, using matched workload traces and held-out seeds. The study tests whether uncertainty adds value beyond task-aware completion-time prediction and identifies the workload conditions under which it is useful.

This contribution statement deliberately describes the method and evaluation plan without claiming a performance win in advance.

---

# Part XIII — Final implementation checklist

## 36. Before coding

- [ ] Freeze V1 branch/tag and record commit hash.
- [ ] Reproduce V1 output tables and figures.
- [ ] Decide the scheduler-visible information contract.
- [ ] Decide how task classes or duration hints are generated.
- [ ] Decide whether initial V2 uncertainty uses empirical quantiles or Monte Carlo.
- [ ] Freeze the first ECT-only and uncertainty-aware ECT definitions.

## 37. During implementation

- [ ] Add safe immutable task/server snapshots.
- [ ] Ensure actual task work and exact remaining work are not exposed to practical V2.
- [ ] Implement a shadow server state.
- [ ] Reproduce strict FIFO and head-of-line blocking.
- [ ] Reproduce CPU/memory reservations and release timing.
- [ ] Reproduce dispatch/sample/step order.
- [ ] Include previous same-tick assignments in the next decision's snapshot.
- [ ] Add duration estimates from visible metadata/history.
- [ ] Add survival-conditioned estimates for running tasks, or document a simpler approximation.
- [ ] Add ECT-only first.
- [ ] Add uncertainty estimation second.
- [ ] Remove hard 50% admission filtering from V2 default.
- [ ] Log prediction, quantile, uncertainty, cost, and fallback reason per task.
- [ ] Preserve deterministic random streams.

## 38. Before final experiments

- [ ] All V1 regression tests pass.
- [ ] Shadow forecast matches actual simulator in exact-duration unit fixtures.
- [ ] No oracle information leaks into practical policy inputs.
- [ ] ECT-only and uncertainty-aware ECT are identical when `beta = 0`.
- [ ] No policy mutates server state during selection.
- [ ] Same workload and background traces are used for matched policy runs.
- [ ] Development, validation, and final test seeds are separated.
- [ ] Parameters and primary metrics are frozen before final test.
- [ ] All unfinished tasks and projection failures are reported.

## 39. Before writing the final research claims

- [ ] Compare against every original baseline.
- [ ] Compare uncertainty-aware ECT directly against ECT-only.
- [ ] Report mean, median, p95, p99, SLA, throughput, goodput, overload, backlog, and drain time.
- [ ] Report per-seed paired differences and confidence intervals.
- [ ] Report prediction calibration and candidate-ranking regret.
- [ ] Report cold-start and warm-start behaviour.
- [ ] Separate practical results from oracle upper-bound results.
- [ ] State the simulator's simplifying assumptions.
- [ ] Report negative or mixed findings honestly.

---

# References to the existing project

The following repository files were used to ground the implementation-specific corrections and extension points:

- [Original report (`report/main.tex`)](https://github.com/Abhay0912/uncertainty-aware-load-balancer/blob/master/report/main.tex)
- [Project specification (`docs/spec.md`)](https://github.com/Abhay0912/uncertainty-aware-load-balancer/blob/master/docs/spec.md)
- [Architecture and policy contract (`docs/architecture.md`)](https://github.com/Abhay0912/uncertainty-aware-load-balancer/blob/master/docs/architecture.md)
- [Server implementation (`src/lbsim/server.py`)](https://github.com/Abhay0912/uncertainty-aware-load-balancer/blob/master/src/lbsim/server.py)
- [Simulator loop (`src/lbsim/simulator.py`)](https://github.com/Abhay0912/uncertainty-aware-load-balancer/blob/master/src/lbsim/simulator.py)
- [Workload generator (`src/lbsim/workload.py`)](https://github.com/Abhay0912/uncertainty-aware-load-balancer/blob/master/src/lbsim/workload.py)

---

## Final recommendation

Implement **shadow-queue ECT first**, validate it against the real simulator, and benchmark it against Weighted Metric before adding uncertainty. Only after the point predictor is trustworthy should the project add a completion-time distribution and a soft tail-risk penalty.

This ordering answers the most important question efficiently:

> Does task-specific completion-time prediction improve placement at all, and if it does, does uncertainty add another measurable improvement?

That is the cleanest path to a stronger, more defensible V2 research contribution.
