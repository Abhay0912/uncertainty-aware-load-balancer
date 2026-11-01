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
- **Shared `L_i`:** one pure function (`scoring.load_score`) is used by WeightedMetric, P2C and, later, the probabilistic policy. Then the ablation "with vs. without P_risk" differs in exactly one term.
- **Live vs. windowed values (D16):** about 4 tasks arrive per tick. If policies read the last *window sample*, all of them see the same snapshot and herd onto one server. Live `cpu_pct` includes the tasks placed earlier in the same tick. The windows are kept for μ, σ and R̄.
- **Smooth WRR (D17):** the nginx algorithm. It gives exact proportions per 37-task cycle without sending 16 tasks in a row to the big server.
- **Reproducible randomness:** Random and P2C take a seeded `Generator` from `policy_rng(seed)` (a `SeedSequence([tag, seed])`, separate from the workload streams). `reset()` rewinds the generator state, so rerunning the same policy object gives identical results. Tests check that same seed means same assignments, and a different seed means different ones.
- **Contract test:** every baseline is run against loaded servers and the full server state is compared before and after, which proves that policies only *read*.
- **P2C with N=2 is exactly WeightedMetric.** It samples both servers, so it always picks the global minimum. That makes a nice sanity test.
- **Seed-0 preview (mean response / SLA violation rate):**
  - stable: WRR 9 s / 9% · WM 236 s / 14% · P2C 588 s / 22% · LeastCPU 907 s / 24% · RR 899 s / 60% · Random 870 s / 59%
  - bursty: WRR 39 s / 61% · WM 489 s / 34% · P2C 880 s / 40% · LeastCPU 1773 s / 37%
- **Key finding (D18): utilisation % hides backlog.** The 2-core server has a 424-task queue yet shows only about 62% CPU, because the head-of-line task can't fit next to the running one. Load-aware policies keep feeding it. That's why capacity-aware but load-blind WRR wins here. Interview angle: this is why real systems also look at **queue length / load average** (Linux load average counts *waiting* tasks, not just running ones), not only CPU %.
- **Fix (D19): the balancer observes *load* %, i.e. (running + queued demand) ÷ capacity.** Utilisation is still logged for evaluation. Load equals utilisation when there is no queue, so nothing changes until a backlog exists. The flag `count_queued=False` reproduces the old run.
  - stable: LeastCPU 907 → 6.5 s, WeightedMetric 236 → 6.4 s (3% SLA), P2C 588 → 26 s. WRR 9 s is unchanged.
  - bursty: the load-aware policies are about 36 s, but **every policy has 57–61% SLA violations**. During bursts the offered load is about 160% of capacity, so no placement rule can avoid queueing. Phase 5 has to be judged on *how much* it reduces that, and on overload frequency, not on eliminating it.
  - P2C now trails WeightedMetric. With N = 5, a two-server sample misses the fastest server (16 of 37 capacity units) 60% of the time. P2C's strengths, large N and stale information, don't apply here.
  - Interview soundbite: "My first baselines were blind to backlog because CPU % saturates under fragmentation. I changed the *observed signal*, not the formula, and verified that the metric-blind policies' results were byte-identical."
- **WRR's bursty weakness:** WRR is still the best on mean response, but it has 61% SLA violations under bursts, because it can't react to a spike. The load-aware policies have a lower SLA violation rate. That's the trade-off the probabilistic policy is meant to address.
### Phase 5 — Probabilistic policy
- **Pipeline per decision:** window → (μ, σ) → `P = 1 − Φ((θ − μ)/σ)` for CPU and memory → `P_risk = 1 − (1−P_C)(1−P_M)` → `S = 0.6·L + 0.4·P_risk` → exclude P_risk > 0.5 unless all servers are above it → lowest S.
- **Φ without SciPy:** `Φ(z) = ½(1 + erf(z/√2))` (D2). It is exact, and you can derive it on a whiteboard.
- **σ = 0 edge case (D6):** a constant window is a point mass, so P is 1 if μ > θ, else 0. `MetricWindow.std()` returns exactly 0.0 for a constant window, so float noise around 1e-15 can't turn that into Φ(±huge).
- **Variance cuts both ways:** below θ, a larger σ means *more* risk (the tail reaches θ). Above θ, a larger σ means *less* risk (some mass falls back below). There's a test for each direction.
- **Motivating example as a test:** two servers both with mean 60%. Steady (σ = 0) gives P = 0. Fluctuating (σ = 30) gives P = 1 − Φ(0.67) ≈ 0.25. A least-loaded policy can't tell them apart.
- **Window vs. live (D20):** risk comes from past samples and is constant within a tick. L comes from live state and moves with each placement, so herding is prevented by L.
- **Ablation identity:** with weights (1, 0) and threshold 1.0, the probabilistic policy reproduces WeightedMetric's assignments exactly (a test). So any experimental difference comes *only* from P_risk.
- **Seed-0 result (mean response / SLA violation rate):** stable: prob 6.5 s / 3.7% vs WM 6.4 s / 3.0%. Bursty: prob 37.6 s / 58.2% vs WM 36.4 s / 56.7%. **No improvement on seed 0.** It is reported as measured.
- **Why (D21):** a good balancer *equalises* load, so every server hovers around the same level (about 100% load % here, above θ = 80%). Then P_risk is close to 1 everywhere, the admission rule falls back ("capacity pressure" in 62–73% of decisions), and S ranks like L. Risk only adds information when servers *differ* in variability, and a load-aware balancer erodes exactly that difference.
- **But the estimate is calibrated:** mean chosen P_risk is 0.64 vs. an observed exceedance frequency of 0.61. The model predicts well; it just can't *discriminate* between servers.
- **Interview soundbite:** "The risk model was calibrated but non-discriminative: its threshold sat below the operating point the balancer itself drives every server to. I didn't retune θ after seeing results. It became a pre-declared sensitivity axis."
### Phase 6 — Metrics & experiments
- **The matrix:** 7 policies × 2 workloads × 5 seeds = 70 runs in about 26 s. Each (workload, seed) task list is generated **once** and shared by all 7 policies, and the servers are rebuilt per run. Outputs: `runs.csv`, `summary.csv` (mean ± std), `paired.csv`.
- **Metric windows (D22):** response time and SLA come from completed tasks, with unfinished ones counted, never dropped. Throughput spans the whole run including the drain. Utilisation, imbalance and overload average over the arrival horizon [0, T_sim). Otherwise RR's 8,500-tick drain tail would dominate them.
- **Two overload numbers:** on true utilisation (the spec's metric) and on the load signal (what P_risk actually predicts). Calibration has to compare a prediction with the quantity it predicts.
- **Paired, not pooled (D23):** with matched seeds, compare per-seed differences against the ablation. Report mean Δ, std Δ and wins out of 5. A sign test with 5/5 wins gives p = 1/32 ≈ 0.03. With 5 seeds a CI is wide and assumption-heavy, while a win count is honest.
- **The result (D24):** probabilistic ≈ weighted_metric. Stable: slightly *worse* on all 5 seeds (+0.29 s, +0.7 pp SLA). Bursty: no detectable difference (+0.2 s ± 0.85, SLA +0.4 pp ± 1.8, 2–3/5 wins). Its only edge is bursty utilisation overload, −1.1 pp (4/5 wins), which is inside the noise. **The primary outcome is not met at the pre-declared parameters.**
- **Still calibrated:** mean P_risk 0.62 vs observed load overload 0.62 (stable), 0.74 vs 0.72 (bursty). The model predicts the *level* correctly but can't rank servers, because they all sit at the same level (D21).
- **Throughput caveat:** when everything drains, throughput ≈ n_tasks ÷ makespan, so the last task to finish sets it. It only separates policies with long backlogs (RR 0.49/s vs ~3.9/s).
- **Interview soundbite:** "I compared against the ablation that differs by exactly one term, paired by seed, and counted wins. Over five seeds the risk term didn't help. The diagnostics explain why, and I didn't move the thresholds after seeing it."
### Phase 7 — Plots & sensitivity
### Phase 8 — Wrap-up

## Question bank (answer each as its phase completes)
1. Why isn't Least Loaded enough? What does variance add?
   *(Phase 5)* Same mean, different σ means a different tail probability of crossing θ (60% steady → P=0; 60% ± 30 → P≈0.25). In practice here, a load-aware balancer equalises servers, so the extra information shrinks (D21). Variance helps most when servers differ in volatility and the threshold sits near the operating point.
2. Utilisation is bounded to [0,100], and W=10. Is the normal assumption valid? What would you use instead?
3. Why `1 − (1−P_C)(1−P_M)`? What breaks if CPU and memory are correlated?
   *(Phase 5)* It is P(at least one exceeds) = 1 − P(neither), and it needs independence to factor. With positive correlation the true union probability is *lower* (the events overlap), so the formula overestimates risk. The bounds are max(P_C, P_M) ≤ P_union ≤ min(1, P_C + P_M). Our demands are drawn independently (D8), but queued load couples CPU and memory, since both grow with the backlog.
4. How did you make sure the comparison between policies was fair?
   *(Phase 6)* The task list is generated once per (workload, seed) and passed unchanged to every policy. Servers are rebuilt and `policy.reset()` is called per run. Randomised policies draw from their own seeded stream, so they can't shift the workload. Every policy runs through one simulator loop and one drain rule. R_SLA and θ were frozen before the results (and R_SLA never enters the simulator). Comparisons are paired by seed against the one-term ablation.
5. Why is the risk-free weighted-metric baseline the most important one?
   *(Phase 5)* It is the proposed method minus exactly one term. A test proves that setting the risk weight to 0 and disabling admission reproduces it bit for bit. Beating RR only shows that load-awareness helps; beating WM is the only evidence that *uncertainty* helps.
6. Why does Power of Two Choices work so well for how little it does?
   *(Phase 4)* With n balls into n bins, the maximum load drops from Θ(log n / log log n) to Θ(log log n) with just two random probes (Mitzenmacher). It is cheap (O(1) probes) and robust to stale data, because it doesn't herd. Caveat seen here: with only 5 servers and a metric that hides backlog, its two samples often include the hidden-backlog node, so its advantage over Random is real but limited.
7. Why drain the queue at the end? What bias does a hard cutoff introduce?
   *(Phase 3)* A cutoff drops exactly the tasks stuck behind overload, the slowest ones, so the policies that overload servers look *better*. With RR at seed 0, most of server 4's ~800 tasks would be unfinished at t=1000, and its 3,800 s mean response would vanish from the average.
8. Lower load imbalance isn't automatically better. Why?
   *(Phase 6)* The servers are heterogeneous (speeds 0.5–2.0). Equal utilisation % on a 0.5-speed node means its tasks take 4× longer than on the fastest one. Imbalance is measured on utilisation %, which ignores speed and queues. In the data, least_cpu has the lowest imbalance (12.1) but weighted_metric has equal or better response. RR's imbalance (22.6) is a *symptom* of the one hidden-backlog node, not the cause. So it's a context metric, not a target.
9. How would this run on a real cloud? (Metrics source: Prometheus or CloudWatch; LB: Envoy, NGINX or a K8s scheduler plugin.)
10. Limitations, and what you'd do next. (Real traces, a correlated risk model, tuning the weights, prediction after assignment.)
