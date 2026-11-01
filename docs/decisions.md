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
