"""Run policies over workloads and summarise. Phase 5: the six baselines + probabilistic on seed 0, one row per policy.
(Full metrics, the multi-seed runner and results/ output arrive in Phase 6.)"""

from __future__ import annotations

import pandas as pd

from lbsim.config import EXPERIMENT, SERVERS, WORKLOAD
from lbsim.policies import all_policies
from lbsim.simulator import SimulationResult, simulate
from lbsim.workload import Workload, generate_workload

CAPACITY = sum(s.cores * s.speed for s in SERVERS)


def offered_load(wl: Workload) -> float:
    """Core-seconds of speed-1 work generated, as a fraction of cluster capacity over the arrival horizon."""
    return sum(t.cpu_demand * t.work for t in wl.tasks) / (WORKLOAD.t_sim * CAPACITY)


def delivered_core_seconds(res: SimulationResult) -> float:
    """Capacity actually consumed: sum over ticks of reserved cores x speed (includes tick rounding)."""
    st = res.server_ticks
    cores = st["server_id"].map(lambda i: SERVERS[i].cores)
    speed = st["server_id"].map(lambda i: SERVERS[i].speed)
    return float((st["cpu_pct"] / 100 * cores * speed).sum())


def summarise(wl: Workload, res: SimulationResult) -> None:
    t = res.tasks
    required = sum(task.cpu_demand * task.work for task in wl.tasks)
    per_server = t.groupby("server_id")["response_time"].agg(["count", "mean"]).round(1)
    print(f"\n== {res.policy} | {wl.kind} | seed {wl.seed} ==")
    print(f"tasks {len(t)}, ticks {res.n_ticks} (arrivals end at {WORKLOAD.t_sim}), drained {res.drained}")
    print(f"offered load {offered_load(wl):.3f} (target {WORKLOAD.target_utilisation})")
    print(f"delivered / required core-seconds {delivered_core_seconds(res) / required:.3f}")
    print(f"mean response {t['response_time'].mean():.1f} s, "
          f"SLA (> {EXPERIMENT.r_sla:.0f} s) violations {(t['response_time'] > EXPERIMENT.r_sla).mean():.1%}")
    print(per_server.to_string())


def quick_row(res: SimulationResult) -> dict[str, float | str]:
    """Preview numbers only; the real metric definitions live in evaluation.py (Phase 6)."""
    t, st = res.tasks, res.server_ticks
    per_server_cpu = st.groupby("server_id")["cpu_pct"].mean()
    return {
        "policy": res.policy,
        "mean_resp_s": t["response_time"].mean(),
        "p95_resp_s": t["response_time"].quantile(0.95),
        "sla_viol": (t["response_time"] > EXPERIMENT.r_sla).mean(),
        "ticks": res.n_ticks,
        "max_queue": st["queue_length"].max(),
        "cpu_min_srv": per_server_cpu.min(),
        "cpu_max_srv": per_server_cpu.max(),
        "cap_pressure": t["capacity_pressure"].mean(),
    }


def main() -> None:
    seed = EXPERIMENT.seeds[0]
    for kind in EXPERIMENT.workloads:
        wl = generate_workload(kind, seed)
        print(f"\n== {kind} | seed {seed} | {len(wl.tasks)} tasks | offered load {offered_load(wl):.3f} ==")
        rows = [quick_row(simulate(wl.tasks, p)) for p in all_policies(seed)]
        print(pd.DataFrame(rows).set_index("policy").round(3).to_string())


if __name__ == "__main__":
    main()
