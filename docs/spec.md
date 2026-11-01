# Specification — Uncertainty-Aware Probabilistic Load Balancing

> Text digest of `Cloud_Computing_PR.pdf` (NIT Warangal, M.Tech CSE, Oct 2026).
> **This file is the source of truth for the implementation.** Section numbers (§) refer to the PDF.

## 1. Research question & scope
**How can recent server metrics and their variability be used to estimate overload risk and improve
task assignment compared with simple load-balancing policies?**

- Simulation-based implementation and comparison, **not** a production cloud scheduler, and **not** a claim of a new general-purpose algorithm.
- Motivation: two servers both at 60% CPU, where one is steady and one fluctuates a lot, have different overload risk. Policies that look only at the current value treat them as the same.
- Risk values are **heuristic proxies**, not calibrated forecasts of what happens after an assignment.
- Report results as measured. **Do not assume an improvement in advance.**

## 2. Workflow per scheduling decision (§3.1)
1. Generate or receive an incoming task.
2. Collect each server's recent CPU, memory, and response-time observations.
3. Compute the rolling mean and standard deviation of each metric over the window.
4. Estimate the CPU and memory threshold-exceedance probabilities.
5. Combine them into an overload-risk score.
6. Compute the risk-adjusted score and select an eligible server (lowest score).
7. Simulate task execution, update server metrics, and record performance.

## 3. Formulas

### 3.1 Metrics & rolling statistics (§3.2)
- Metric vector for server i at time t: `x_i(t) = [C_i(t), M_i(t), R_i(t)]` = CPU %, memory %, response time.
- Rolling window: the latest **W = 10** observations (configurable, not tuned).
- Mean: `μ_C = (1/W) Σ C_i(t)`
- Std (**population**, ÷W): `σ_C = sqrt( (1/W) Σ (C_i(t) − μ_C)² )`
- The same statistics are computed for memory (μ_M, σ_M).

### 3.2 Overload probabilities (§3.3)
- Thresholds: **θ_C = 80%**, **θ_M = 85%** (configurable).
- `P_C = 1 − Φ((θ_C − μ_C) / σ_C)`
- `P_M = 1 − Φ((θ_M − μ_M) / σ_M)`
- Φ = standard normal CDF.
- **If σ = 0:** use a deterministic check instead of dividing by zero: P = 1 if μ > θ, else 0.
  (Treating μ == θ as 0 is our choice; see decisions.md D6.)
- Combined risk (assumes CPU and memory are independent): `P_risk = 1 − (1 − P_C)(1 − P_M)`

### 3.3 Risk-adjusted selection (§3.4)
- `R̄_i` = mean response time of tasks completed on server i within the rolling window.
- `C_i`, `M_i` = **latest** observed CPU and memory %.
- Normalised response time: `r_i = R̄_i / (R̄_i + R_ref)`, where R_ref > 0.
- Current-load score: `L_i = 0.4·C_i/100 + 0.4·M_i/100 + 0.2·r_i`
- Risk-adjusted score: `S_i = 0.6·L_i + 0.4·P_risk_i`. **Select the lowest S_i.**
- **Admission rule:** exclude servers with `P_risk > 0.5` when at least one server is at or below that threshold.
  If *all* servers exceed it, pick the lowest S_i and **record the assignment as "capacity pressure"**.
- The weights are initial, interpretable choices, not optimal ones. An optional sensitivity analysis can vary them.

## 4. Baselines (§3.5)
**Required (implement first):**
| Policy | Rule |
|---|---|
| Round Robin | Repeating order 0,1,…,N−1 |
| Weighted-metric (risk-free) | Lowest `L_i`, with no risk term. **Key ablation** that isolates the effect of P_risk |
| Least CPU | Lowest current `C_i` |
| Weighted Round Robin | Proportional to fixed capacity weights (set before the experiment) |
| Random | Uniform over eligible servers |
| Power of Two Choices (P2C) | Sample 2 servers at random and pick the lower `L_i` |

**Optional (if time permits):** Least Memory (lowest `M_i`) and Least Active Tasks.

All policies must get **the same task sequence, server capacities, and workload realisation** in each matched run.

## 5. Simulation (§3.6, §4)
- Lightweight Python: NumPy, pandas, Matplotlib.
- **5 heterogeneous servers** with different processing capacities.
- Synthetic tasks, each with a CPU demand, memory demand, and expected processing duration.
- Workloads:
  - **stable**: arrivals and demands change gradually.
  - **bursty**: arrivals and/or demands spike temporarily.
- Fixed seed per run. Use multiple seeds if time permits.
- The simulator must explicitly define the following, identically for every policy:
  - task-arrival generation
  - task CPU and memory demands, and service durations
  - queue handling
  - how utilisation and response time are updated
- **End of run:** drain the queue until all accepted tasks finish, *or* count unfinished tasks explicitly. Otherwise the results are biased.
- **Logged data:**
  - timestamp
  - task id
  - assigned server
  - CPU %
  - memory %
  - response time
  - completion status
  - SLA status
  - capacity-pressure flag
  - per-interval server utilisation

## 6. Evaluation metrics (§5)
| Metric | Definition | Better |
|---|---|---|
| Avg response time | `R̄ = (1/K) Σ R_j` over K completed tasks (submission → completion) | lower |
| Throughput | completed tasks / simulation duration | higher |
| SLA violation rate | `#{j : R_j > R_SLA} / K` (R_SLA fixed before the comparison) | lower |
| Avg CPU utilisation | `(1/(N·T_sim)) Σ_i ∫ C_i(t) dt` (time-averaged) | context only |
| Load imbalance | mean over t of `I(t) = sqrt((1/N) Σ (C_i(t) − C̄(t))²)` | context only (servers are heterogeneous) |
| Est. risk vs observed overload | the scheduler's mean P_risk vs the fraction of intervals with C > θ_C or M > θ_M | diagnostic |

**Primary outcome:** does the proposed method reduce SLA violations and observed overload frequency
under **bursty** demand without an unacceptable loss of throughput or increase in response time?

## 7. Known assumptions & limitations
- Normal approximation for bounded [0,100] utilisation, with a small window (W=10). This is least accurate during abrupt changes.
- The independence assumption when combining P_C and P_M (real metrics are often correlated).
- Risk is computed from *past* observations, not from the predicted state after the assignment.
- Weights and thresholds are hand-picked.
- Synthetic data does not prove the method behaves the same in production. Real traces are future work.

## 8. Parameters (→ `src/lbsim/config.py`)
| Name | Value | Source |
|---|---|---|
| N_SERVERS | 5 | §3.6 |
| WINDOW W | 10 | §3.2 |
| THETA_CPU | 80.0 | §3.3 |
| THETA_MEM | 85.0 | §3.3 |
| L weights (cpu, mem, resp) | 0.4, 0.4, 0.2 | §3.4 |
| S weights (load, risk) | 0.6, 0.4 | §3.4 |
| RISK_ADMISSION_THRESHOLD | 0.5 | §3.4 |
| R_REF | 6.0 s (= mean task work) | §3.4 (must be > 0); D10 |
| R_SLA | 18.0 s (= 3 × mean work), frozen | §5.3; D10 |
| Servers (cores, GB, speed) | (4,8,1.0) (4,8,1.0) (8,16,1.5) (8,16,2.0) (2,4,0.5); WRR weight = cores × speed | §3.5; D8 |
| Tick, horizon | 1 tick = 1 s; arrivals for 1000 ticks, then drain | §3.6 |
| Tasks | CPU ~U(0.5,1.5) cores, mem ~U(0.5,3) GB, work ~lognormal(mean 6 s, σ=0.6), ≥1 s | §3.6; D8 |
| Arrivals | Poisson per tick, λ₀ ≈ 4.0/s → 65% mean utilisation, ±20% sinusoidal drift (period 500) | §3.6; D9 |
| Bursts | 4 × 50 ticks, ×3 arrivals, ×1.3 CPU; bursty baseline scaled so mean load = stable | §3.6; D9 |
| Seeds | 0–4 | §3.6 |
