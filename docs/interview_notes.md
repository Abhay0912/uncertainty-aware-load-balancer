# Interview Notes

## 2-minute pitch
_(Fill in after Phase 7, once the results exist.)_

## Phase notes
### Phase 0 — Foundation
- The project is a simulation-based comparison, which keeps the scope honest. The goal is to test a hypothesis, not to ship a scheduler.
- The spec, decision log and architecture docs were written before any code.
- Strategy pattern + one shared task stream → a fair, matched comparison.

### Phase 1 — Config & workload
### Phase 2 — Server & rolling window
### Phase 3 — Simulator + Round Robin
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
8. Lower load imbalance isn't automatically better. Why?
9. How would this run on a real cloud? (Metrics source: Prometheus or CloudWatch; LB: Envoy, NGINX or a K8s scheduler plugin.)
10. Limitations, and what you'd do next. (Real traces, a correlated risk model, tuning the weights, prediction after assignment.)
