# CLAUDE.md

Cloud Computing M.Tech project (NIT Warangal): **uncertainty-aware probabilistic load balancer**, evaluated in a
Python simulation against 6 baselines under stable and bursty workloads.

- **Source of truth: `docs/spec.md`.** Do NOT re-read `Cloud_Computing_PR.pdf` (expensive). Read the spec instead.
- Design: `docs/architecture.md` · Decisions: `docs/decisions.md` · Interview prep: `docs/interview_notes.md`

## Commands (PowerShell, from repo root)
```
.venv\Scripts\Activate.ps1
python -m pytest -q
python -m experiments.run_all
```

## Layout
- `src/lbsim/`
  - `config.py`
  - `workload.py`
  - `server.py`
  - `metric_window.py`
  - `simulator.py`
  - `evaluation.py`
  - `policies/` (`base.py` + one file per policy)
- `experiments/run_all.py`: the experiment driver, which writes to `results/` (gitignored)
- `tests/`: pytest. `pyproject.toml` puts `src` on the path.

## Conventions
- Every tunable lives in `config.py`. No magic numbers in the logic.
- Pass all randomness explicitly as seeded `numpy.random.Generator` objects. Never use the global `np.random`.
- Every policy subclasses `Policy` (`policies/base.py`) and only *reads* server state.
- Every policy gets the identical task list per (workload, seed). Rebuild the servers fresh for each run.
- Keep functions pure where practical, add type hints, and keep comments minimal.
- Add tests for formula edge cases (σ=0, every server risky, matching seeds).

## Working style (student is learning, preparing for interviews)
- One phase per session. Plan first, then build.
- Explain design choices briefly. End each phase with a 5-question quiz.
- After each phase:
  - update `docs/interview_notes.md` (and `docs/decisions.md` if new choices were made)
  - tick the roadmap below
  - commit

## Roadmap
- [x] 0 Foundation: spec, docs, skeleton
- [ ] 1 Config + workload generator (stable/bursty, seeded)
- [ ] 2 Server model + rolling MetricWindow
- [ ] 3 Simulator loop + Round Robin, working end to end
- [ ] 4 Baselines: WRR, Random, LeastCPU, WeightedMetric, P2C
- [ ] 5 Probabilistic policy + edge-case tests
- [ ] 6 Evaluation metrics + multi-seed runner
- [ ] 7 Plots + sensitivity analysis
- [ ] 8 README, results write-up, interview pack
