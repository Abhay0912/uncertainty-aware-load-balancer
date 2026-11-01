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
