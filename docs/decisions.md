# Architecture Decision Log

Format: **Decision** · Alternatives · Why. Add an entry whenever a non-obvious choice is made.

## D1 — Time-stepped (discrete-time) simulator
- **Decision:** Advance the clock in fixed ticks. Each tick: admit arrivals → schedule → progress running tasks → sample metrics.
- **Alternatives:**
  - Discrete-event simulation (SimPy, or a heap of events)
  - A real deployment (VMs or containers)
- **Why:**
  - The spec measures metrics "at each interval", which maps directly onto ticks.
  - It is easy to explain and debug.
  - Precise event timing isn't needed for a policy comparison.
  - Cost: response times are quantised to the tick length.

## D2 — Normal CDF via `math.erf`
- **Decision:** `Φ(z) = 0.5 · (1 + erf(z / √2))`
- **Alternatives:** `scipy.stats.norm.cdf`
- **Why:**
  - No heavy dependency, and it's exact to float precision.
  - The formula can be derived in an interview.

## D3 — Strategy pattern for policies
- **Decision:** An abstract `Policy` with `select(servers, task) -> int`. One subclass per policy.
- **Alternatives:** `if policy == "rr": ...` branches inside the simulator.
- **Why:**
  - The simulator stays policy-agnostic.
  - Adding a baseline means adding one new file.
  - It guarantees every policy runs through the exact same loop, which keeps the comparison fair.

## D4 — Drain the queue at end of run
- **Decision:** Stop new arrivals at `T_sim`, then keep ticking until every accepted task completes.
  Throughput still uses the completed tasks over the actual elapsed time.
- **Alternatives:** Cut off at `T_sim` and count unfinished tasks.
- **Why:**
  - The spec (§3.6) warns that a hard cutoff biases response time and SLA results toward slow policies, because their slowest tasks are never counted.

## D5 — Population standard deviation (÷W)
- **Decision:** `numpy.std(window, ddof=0)`
- **Alternatives:** Sample std (÷(W−1), `ddof=1`)
- **Why:**
  - It matches the spec formula (§3.2).
  - With W=10 the difference is about 5%. That's documented, not hidden.

## D6 — σ = 0 rule
- **Decision:** If σ == 0, then P = 1.0 if μ > θ, else 0.0.
- **Why:**
  - It avoids division by zero.
  - With no observed variance, the "distribution" is a point mass at μ.
  - μ == θ counts as not exceeding, consistent with the strict `>` used for overload elsewhere.

## D7 — Config as frozen dataclasses
- **Decision:** Group parameters into frozen dataclasses (`ServerSpec`, `WorkloadConfig`, `ScoringConfig`, `ExperimentConfig`), each validated in `__post_init__`, with default instances in `config.py`.
- **Alternatives:** Module-level constants; a YAML file.
- **Why:**
  - Sensitivity analysis becomes `dataclasses.replace(SCORING, score_weights=(0.8, 0.2))`, with no global mutation.
  - Invalid settings (weights not summing to 1, R_REF ≤ 0, a task larger than the smallest server) fail at import time, not mid-run.

## D8 — Server and task model units
- **Decision:** Servers have `cores`, `mem_gb` and `speed`. Tasks have `cpu_demand` (cores), `mem_demand` (GB) and `work` (seconds on a speed-1.0 server). Run time on server i is `work / speed_i`.
- **Why:**
  - Heterogeneity comes in two forms: parallel capacity (cores) and per-task speed. The weak node (2 cores, speed 0.5) is where capacity-blind policies such as RR break down.
  - Work is lognormal (right-skewed, like real jobs). CPU is capped at 1.5 so that, even with ×1.3 burst inflation, every task fits on the 2-core server (checked by `validate_fit`).
  - CPU and memory demands are drawn independently, matching the independence assumption behind P_risk. This is noted as a limitation.

## D9 — Arrival process and bursts with matched mean load
- **Decision:**
  - Arrivals are Poisson per tick with rate λ(t).
  - λ₀ is calibrated analytically: `λ₀ = target_util · Σ(cores·speed) / (E[cpu]·E[work])`, with target_util = 0.65.
  - Both workloads share a gentle ±20% sinusoidal drift.
  - Bursty adds 4 non-overlapping 50-tick bursts (×3 arrivals, ×1.3 CPU). Each burst is placed at a random offset within its own quarter of the horizon.
  - The bursty baseline is scaled by `b = 1/(1 + f·(3·1.3 − 1)) ≈ 0.63`, where f is the burst fraction, so mean offered load equals stable's.
- **Alternatives:**
  - Bursts on top of an unchanged baseline, which would make bursty heavier overall.
  - Fully random burst placement, which can cause overlaps.
- **Why:**
  - Matching the mean load means stable vs bursty differ only in variability, which is exactly what the research question is about.
  - Separate `SeedSequence.spawn` streams for burst placement, arrivals, CPU, memory and work mean that changing one parameter doesn't reshuffle the others.
- **Note:** The utilisation target is analytic. It will be sanity-checked once the simulator exists (Phase 3), before any policy comparison.

## D10 — R_REF and R_SLA
- **Decision:** R_REF = mean work (6 s). R_SLA = 3 × mean work (18 s). Both are fixed now, before any results exist.
- **Why:**
  - With R_REF set to the mean work, a typical task gets r ≈ 0.5, the midpoint of the normalised range.
  - An SLA of 3× nominal duration tolerates normal queueing but flags tasks stuck behind overload.
  - Choosing R_SLA after seeing results would let the threshold be tuned to favour one policy.

## D11 — Server resource model and local queue
- **Decision:**
  - A task runs only while its CPU and memory demands fit into the server's free capacity (a reservation model).
  - Tasks that don't fit wait in a **strict FIFO** local queue. Only the head can start (head-of-line blocking), so a later small task can't overtake an earlier one.
  - CPU % = reserved cores ÷ cores; memory % = reserved GB ÷ mem_gb. Both are bounded to [0, 100].
  - Each tick, a running task's remaining work drops by `speed`. A task started at tick t finishes at the end of the tick in which its work reaches ≤ 0, so `finish_tick = t + ceil(work / speed)`.
  - Response time = `finish_tick − arrival_tick`. It includes any wait in the server's queue.
- **Alternatives:**
  - Processor sharing, where every task slows down when the server is oversubscribed and CPU can exceed 100%.
  - A FIFO queue where any queued task that fits may start ("backfilling").
- **Why:**
  - The reservation model is simple and explainable. Overload shows up as **queueing delay**, which is exactly what the SLA metric measures.
  - Strict FIFO can't starve large tasks, and it's the most neutral choice: no policy benefits from a smarter local queue.
  - Cost: CPU % saturates at 100% instead of showing how oversubscribed a server is. Queue length is exposed separately.

## D12 — Rolling-window semantics and empty windows
- **Decision:**
  - The CPU and memory windows hold the last W **per-tick samples**.
  - The response-time window holds the last W **completed tasks** on that server, so R̄ uses completions, not ticks.
  - An empty window reports mean = std = 0.0. That covers an idle server at the start of a run, and R̄ before any task has completed.
  - `std()` returns exactly 0.0 when all values are equal (it checks max == min), so the σ = 0 rule (D6) can't be dodged by floating-point noise of about 1e-15.
- **Alternatives:** A tick-based response window where R̄ = the mean of responses completed in the last W ticks.
- **Why:**
  - With a tick-based window, a congested server that completed nothing in the last 10 ticks would have no R̄ data and look *attractive*. The count-based window keeps the most recent evidence.
  - At the start of a run, every server really is empty, so 0 is the true value, not a guess.

## D13 — Tick order: dispatch → sample → step
- **Decision:** Each tick, (1) every task arriving at t is dispatched and starts at t if it fits, (2) each server samples CPU/memory and a per-tick row is logged, (3) running tasks progress and queued tasks start at t+1.
  This supersedes the "step, then sample" order first sketched in architecture.md.
- **Alternatives:** Step, then sample (records the state *after* the tick).
- **Why:**
  - Sampling after the step misses any task that starts and finishes within one tick (`work ≤ speed`). Utilisation would be under-counted, mostly on the fastest server.
  - Sampling after dispatch records exactly the tasks that consumed capacity during tick t, so `Σ cpu% × cores × speed` over the log equals the core-seconds actually delivered.
  - Tasks are dispatched on arrival (no central queue). Waiting happens only in the server's local FIFO queue (D11), so a policy's choice is final and its cost appears as response time.

## D14 — Run termination and the simulator's interface
- **Decision:**
  - `simulate(tasks, policy, specs, window, sim)` rebuilds servers and calls `policy.reset()` on every call.
  - It drains until all servers are idle (D4). `SimulationConfig.max_ticks` (200,000) is a safety cap: hitting it stops the run with `drained=False` and the unfinished tasks flagged `completed=False` with a NaN response time.
  - `max_ticks` must exceed the last arrival, so every task is always dispatched and logged.
  - `Policy.decision_info()` (default `{}`) lets a policy attach fields such as `p_risk` and `capacity_pressure` to each task row without the simulator knowing about specific policies.
  - The simulator never sees R_SLA. SLA status is derived in `evaluation.py`.
- **Why:**
  - The spec (§3.6) allows either draining or counting unfinished tasks explicitly. The cap uses the second as a fallback, so a diverging policy can't hang the experiment or silently drop tasks.
  - Keeping R_SLA out of the run makes it impossible for the threshold to influence behaviour.

## D15 — Tick quantisation inflates effective load by about 10% (measured, kept)
- **Observation (Phase 3, seed 0):** Offered load is 0.662, but delivered core-seconds are about 1.10× the required ones, because a task reserves its cores for `ceil(work/speed)` whole ticks. The effective cluster load is therefore about 72%, not 65%.
- **Decision:** Keep it. It applies identically to every policy, so the comparison stays fair. It is reported in the write-up rather than "fixed" by retuning λ₀ after looking at results.
- **Alternative:** A smaller tick (e.g. 0.1 s), at about 10× the runtime.

## D16 — "Current" load means live state; ties go to the lowest index
- **Decision:**
  - The spec's `C_i`, `M_i` ("latest observed") are read live at dispatch time (`server.cpu_pct`, `server.mem_pct`). That includes tasks placed earlier in the same tick.
  - The rolling windows are used only for what needs history: μ, σ (Phase 5) and R̄.
  - `L_i` lives in one pure function, `scoring.load_score`, shared by WeightedMetric, P2C and (in Phase 5) the probabilistic policy.
  - Deterministic policies break ties by lowest server index. P2C breaks ties toward its first draw, which is random.
- **Alternatives:** `cpu_window.latest()`, the sample taken at the end of the previous tick's dispatch.
- **Why:**
  - About 4 tasks arrive per tick (12 or more during bursts). With a once-per-tick snapshot, every arrival in a tick would see the same values and all of them would pile onto one server. That herding comes from our tick size, not from the policy.
  - A real balancer knows its own placements, so leaving them out would be artificial.
  - A single shared `L_i` guarantees that WeightedMetric is exactly "the probabilistic policy minus P_risk".
  - Stale metrics are a legitimate topic, but a separate one. They are future work, not something to mix into this comparison.

## D17 — Smooth Weighted Round Robin (nginx algorithm)
- **Decision:** Each pick adds w_i to every server's counter, picks the maximum (ties go to the lowest index), then subtracts Σw from the chosen server. Weights = cores × speed = (4, 4, 12, 16, 1), so every 37 picks give exactly w_i to server i, interleaved.
- **Alternatives:**
  - Naive block WRR: 16 consecutive tasks to server 3.
  - Random sampling proportional to the weights.
- **Why:**
  - It is deterministic and gives exact proportions every cycle.
  - It never sends long bursts of tasks to one server. A test asserts that no server is picked more than 2 times in a row.

## D18 — Observation: utilisation % hides queued backlog (Phase 4, seed 0, measured, not yet acted on)
- **Observation:** Under LeastCPU (stable), server 4 (2 cores) averages a **424-task** local queue during arrivals, but its CPU averages only **62%** while that queue exists.
  - Strict FIFO plus coarse task sizes (0.5–1.95 cores) on a 2-core node means the head task often doesn't fit beside the running one, so CPU % stalls well below 100%.
  - Every policy that reads `C_i`/`M_i` therefore sees the most backlogged server as "moderately loaded". LeastCPU sends it 22% of the tasks; its capacity share is 2.7%.
  - R̄ catches up only slowly, because it comes from completions (D12). WeightedMetric does better (12% share), but is still far off.
- **Effect:** On stable seed 0, WRR (capacity-aware but load-blind) beats every load-aware baseline by a wide margin: 9 s mean response vs. 236–907 s.
- **Status:** Resolved by D19. The baselines implement the spec exactly. Whether the server metric should include queued demand is a server-model question (D11). It is to be decided before Phase 5, because the probabilistic policy reads the same metrics.

## D19 — The observed load signal includes queued demand
- **Decision:**
  - Each server exposes three CPU/memory views:
    - `cpu_pct`/`mem_pct`: true utilisation of running tasks, bounded [0, 100]
    - `cpu_load_pct`/`mem_load_pct`: (running + queued demand) ÷ capacity, which can exceed 100
    - `cpu_signal`/`mem_signal`: what the balancer observes, which is load % when `ScoringConfig.count_queued` (default True), otherwise utilisation
  - The rolling windows sample the *signal*, so μ, σ (and later P_risk) see backlog too.
  - All policies read the signal (LeastCPU, and `L_i` via `scoring.server_load_score`).
  - Evaluation (avg utilisation, delivered core-seconds) keeps using true utilisation. Both views are logged per tick and per decision.
  - `simulate()` now takes the whole `ScoringConfig` instead of a bare `window`, so window size and signal choice always travel together.
  - Queued totals are kept incrementally and reset to exactly 0.0 when the queue empties, which removes float drift.
- **Alternatives:**
  - (A) Keep pure utilisation and report D18 as a limitation.
  - Add queue length as an extra term in `L_i`, which would change the spec's formula and weights.
  - Make queued servers ineligible, a new mechanism that would have to apply to every policy.
- **Why:**
  - It fixes D18 without touching any spec formula or weight. Load % equals utilisation exactly whenever there is no queue, so it only differs when a backlog exists.
  - It is the same idea as the Linux load average, which counts runnable *waiting* tasks, not just running ones.
  - With θ_C = 80%, a backlogged server (load ≫ 100%) now gets P_C → 1 in Phase 5, which is the behaviour the risk model is meant to have.
- **Cost:** The spec assumes bounded [0,100] utilisation for the normal approximation. The load signal is unbounded above, which arguably fits a normal model *better* (no ceiling at 100), but it is a deliberate deviation, noted in spec.md §3.1.
- **Effect (seed 0):**
  - stable: LeastCPU 907 → 6.5 s mean response, WeightedMetric 236 → 6.4 s, P2C 588 → 26 s
  - bursty: about 36 s, but SLA violations are still 57–60% for every policy
  - RR, WRR and Random are byte-identical to before, a built-in check that only metric readers changed

## D20 — P_risk comes from the window; L_i stays live
- **Decision:**
  - μ and σ (and therefore P_C, P_M, P_risk) come from the rolling windows of past per-tick samples (spec §3.1, step 2). L_i reads live state, as in D16.
  - So P_risk is constant for every arrival within one tick, while L_i moves with each placement. Herding within a tick is prevented by the L term.
  - The admission rule uses `P_risk <= threshold` to mean eligible. A server at exactly 0.5 is admitted, consistent with the strict `>` in D6.
  - Ties in S_i go to the lowest index (`argmin_first`), and the capacity-pressure fallback considers all servers.
  - The ablation identity is a test: with `score_weights=(1, 0)` and threshold 1.0, the policy reproduces WeightedMetric's assignments exactly.
- **Alternatives:** Push a live sample into the statistics before scoring (μ and σ would then mix the past with this tick's placements).
- **Why:**
  - It is the spec's definition, and it keeps "risk from recent history" separate from "current load". That separation is what the ablation measures.
  - Cost: the risk view lags by up to one tick, which is listed in spec §7 as a known limitation.

## D21 — Observation: on the load signal, the 80% threshold makes risk non-discriminative (Phase 5, seed 0, measured, not acted on)
- **Observation:**
  - Load-aware balancing equalises the observed load signal. On stable, every server averages about 100% load % (running + queued, D19), so 61% of server-intervals exceed θ_C = 80%.
  - In 62% of stable decisions (73% bursty), *every* server has P_risk > 0.5. The admission rule then falls back to all servers ("capacity pressure"), and because P_risk is close to 1 everywhere, S_i ranks almost exactly like L_i.
  - Result: probabilistic ≈ WeightedMetric. Stable: 6.5 s / 3.7% SLA vs 6.4 s / 3.0%. Bursty: 37.6 s / 58.2% vs 36.4 s / 56.7%.
  - The risk *estimate* is reasonably calibrated: the mean P_risk of the chosen server is 0.64, and the observed fraction of server-intervals with signal > 80 is 0.61 (stable).
  - With `count_queued=False` (utilisation signal), pressure falls to 1–2% and the admission rule does discriminate. But the policy inherits the D18 backlog blindness (593 s mean response on stable).
- **Status:** Reported as measured. θ_C/θ_M were fixed before results (spec §8), and changing them now would tune toward a desired outcome. θ on the load signal (e.g. 100%) and the admission threshold become Phase 7 sensitivity axes, run across all seeds and reported whatever they show.

## D22 — Metric windows: task metrics over completions, interval metrics over the arrival horizon
- **Decision:**
  - Response time (mean, p95) and SLA rate use the K *completed* tasks. Unfinished tasks (only possible if `max_ticks` is hit, D14) are reported as `n_unfinished`, never silently dropped.
  - Throughput = completed ÷ makespan (whole run, drain included), as in D4.
  - Avg CPU utilisation, load imbalance and overload fraction average the per-(tick, server) rows over **[0, T_sim)** only.
  - Overload is strict (`C > θ_C or M > θ_M`, as in D6) and is reported twice: on true utilisation (`overload_frac_util`, the spec's literal metric) and on the D19 load signal (`overload_frac_load`, the quantity P_risk actually predicts, so it's the fair calibration target).
  - Avg utilisation is the spec's unweighted mean over servers (1/N), not capacity-weighted.
  - `mean_p_risk` / `capacity_pressure_rate` are NaN / 0 for policies that don't log them.
- **Alternatives:** average the interval metrics over the whole run.
- **Why:** RR drains for about 8,500 ticks against about 1,000 for the others. Over the whole run, its utilisation would look low and its imbalance would be dominated by one slow server grinding through a backlog alone. That measures the drain tail, which throughput and makespan already capture. The arrival horizon is the only window where every policy faces the identical offered load.
- **Cost:** throughput ≈ n_tasks ÷ makespan, so when everything drains it is set by the *last* task to finish. It is noisy, and it only separates policies that build long backlogs.

## D23 — Multi-seed reporting: paired differences and win counts, no confidence intervals
- **Decision:**
  - `runs.csv` holds one row per (workload, seed, policy). `summary.csv` holds the mean and sample std (ddof=1) across seeds.
  - `paired.csv` holds probabilistic − weighted_metric per seed: mean, std, and the number of seeds on which the target won.
- **Alternatives:** t-based 95% CIs (needs SciPy or a hard-coded t-table value); bootstrap CIs.
- **Why:**
  - Matched seeds share one task list, so the paired difference cancels workload noise. That's the same logic as a paired t-test.
  - With n = 5, a CI is wide and leans on a normality assumption. "Won 0/5 seeds" is honest, assumption-free (a sign test: 5/5 has p = 1/32 ≈ 0.03 one-sided), and easy to explain.
  - The comparison is against the ablation baseline, because it differs from the proposed method by exactly the P_risk term (D20).

## D24 — Observation: across 5 seeds, the probabilistic policy matches but does not beat the ablation (Phase 6, measured)
- **Result (mean over seeds 0–4; probabilistic vs weighted_metric):**
  - stable: 6.44 s vs 6.15 s mean response, 3.4% vs 2.7% SLA violations. Probabilistic is worse on **all 5 seeds** for both (Δ = +0.29 s, +0.7 pp).
  - bursty: 29.5 s vs 29.3 s, 53.9% vs 53.5% SLA violations. Δ is +0.18 s ± 0.85 s and +0.4 pp ± 1.8 pp, with 3/5 and 2/5 wins, i.e. no detectable difference.
  - bursty overload on true utilisation: 48.0% vs 49.1% (Δ −1.1 pp ± 1.5 pp, 4/5 wins). This is the only metric in its favour, and it's small and inside the noise.
  - Capacity pressure: 57% (stable) and 73% (bursty) of decisions, confirming that D21 holds beyond seed 0.
- **Calibration:** mean chosen P_risk 0.62 vs observed load-signal overload 0.62 (stable); 0.74 vs 0.72 (bursty). It is well calibrated, and still non-discriminative (D21).
- **Context:** least_cpu and weighted_metric are the best baselines. P2C is notably worse with 5 servers (24.8 s stable). RR and Random diverge (~850 s) because they ignore the 0.5-speed server's backlog.
- **Status:** the primary outcome (spec §6) is **not met** at the pre-declared parameters. Phase 7 sensitivity (θ on the load signal, admission threshold, weights) will test whether any setting changes that, across all seeds, and report it either way.
