# Interview Notes

## 2-minute pitch
_(Fill in after Phase 7, once the results exist.)_

## Phase notes
### Phase 0 — Foundation
- The project is a simulation-based comparison, which keeps the scope honest. The goal is to test a hypothesis, not to ship a scheduler.
- The spec, decision log and architecture docs were written before any code.
- Strategy pattern + one shared task stream → a fair, matched comparison.

### Phase 1 — Config & workload
- **Workloads differ only in variability.** Bursty is scaled so its mean offered load equals stable's (≈65%). About 41% utilisation between bursts and about 160% during them. Without this, "bursty is worse" could just mean "bursty has more load".
- **Calibrating by offered load:** each task consumes `cpu × work` core-seconds at speed 1, and the cluster supplies `Σ cores·speed` per second. That gives λ₀ ≈ 4 tasks/s.
- **Reproducibility:** one `SeedSequence(seed)` is split into independent child streams (bursts, arrivals, CPU, mem, work). The global `np.random` is never used, and a test proves it.
- **Fairness:** the workload is generated once per (kind, seed) as an immutable tuple of frozen `Task`s, and every policy receives the same object.
- **R_SLA is frozen up front** (18 s = 3× mean work), so the threshold can't be tuned to favour a policy.
- **Fail fast:** config dataclasses validate themselves. A task that can't fit on the smallest server is rejected at import time.
### Phase 2 — Server & rolling window
- **Reservation model:** a task runs only if its CPU and memory demands fit. Otherwise it waits in a strict FIFO local queue. Overload therefore appears as *queueing delay*, which the SLA metric captures. CPU % stays within [0,100], and the queue length is the separate signal for overload beyond that.
- **Heterogeneity:** run time = `ceil(work / speed)` ticks. The weak node (speed 0.5) takes twice as long per task *and* fits fewer tasks (2 cores).
- **Response time = finish − arrival**, not finish − start. Queue wait is the cost of a bad placement, so it must be counted.
- **Two kinds of window:** CPU and memory are sampled once per tick. R̄ covers the last W *completions*. A tick-based R̄ would leave a stalled server with no data, making it look free. That is a classic "absence of evidence" bug.
- **σ = 0 must be exact:** floating-point mean/std of ten identical values can give σ ≈ 1e-15 instead of 0, which would skip the deterministic rule and give z ≈ ±1e16. So `std()` returns exactly 0.0 when max == min.
- **Fairness:** `build_servers()` creates fresh servers for each run. A test checks that two builds share no state.
### Phase 3 — Simulator + Round Robin
- **Loop per tick:** dispatch arrivals → sample metrics → step. Sampling *before* the step is deliberate. Otherwise a task that starts and ends inside one tick never shows up in utilisation (D13). A test checks this exact case.
- **One loop for every policy:** `simulate(tasks, policy)` builds fresh servers and calls `policy.reset()` itself, so reusing a policy object can't leak state between runs. A determinism test runs the same policy object twice and requires identical DataFrames.
- **Policy-agnostic logging:** `decision_info()` lets the probabilistic policy attach `p_risk` and `capacity_pressure` to each task row, without `if policy == ...` branches in the simulator.
- **Termination:** drain until idle. A `max_ticks` cap turns a runaway run into explicit `completed=False` rows instead of a hang or silently dropped tasks.
- **Sanity check (D9 → D15):** offered load is 0.662 ≈ 0.65 target ✓. But whole-tick reservation (`ceil(work/speed)`) delivers about 1.10× the needed core-seconds, so the effective load is about 72%. It's kept because it is identical for all policies, and documented rather than retuned after seeing results.
- **Round Robin result (seed 0):** server 4 has 1/37 of capacity but receives 1/5 of the tasks. Its mean response is about 3,800 s and the drain takes about 7,500 ticks, with 60% SLA violations overall. Servers 2 and 3 sit at about 35%. This is capacity-blindness made visible, and the motivation for every later baseline.
- **Engineering:** `pythonpath` in pytest config doesn't help `python -m experiments...`. The fix was a proper `src`-layout editable install (`pip install -e .`).
### Phase 4 — Baselines
### Phase 5 — Probabilistic policy
### Phase 6 — Metrics & experiments
### Phase 7 — Plots & sensitivity
### Phase 8 — Wrap-up

## Question bank (answer each as its phase completes)
1. Why isn't Least Loaded enough? What does variance add?
2. Utilisation is bounded to [0,100], and W=10. Is the normal assumption valid? What would you use instead?
3. Why `1 − (1−P_C)(1−P_M)`? What breaks if CPU and memory are correlated?
4. How did you make sure the comparison between policies was fair?
5. Why is the risk-free weighted-metric baseline the most important one?
6. Why does Power of Two Choices work so well for how little it does?
7. Why drain the queue at the end? What bias does a hard cutoff introduce?
   *(Phase 3)* A cutoff drops exactly the tasks stuck behind overload, the slowest ones, so the policies that overload servers look *better*. With RR at seed 0, most of server 4's ~800 tasks would be unfinished at t=1000, and its 3,800 s mean response would vanish from the average.
8. Lower load imbalance isn't automatically better. Why?
9. How would this run on a real cloud? (Metrics source: Prometheus or CloudWatch; LB: Envoy, NGINX or a K8s scheduler plugin.)
10. Limitations, and what you'd do next. (Real traces, a correlated risk model, tuning the weights, prediction after assignment.)
