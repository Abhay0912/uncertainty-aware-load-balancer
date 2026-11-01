import pytest

from lbsim.config import (
    EXPERIMENT,
    N_SERVERS,
    SCORING,
    SERVERS,
    WORKLOAD,
    WRR_WEIGHTS,
    ExperimentConfig,
    ScoringConfig,
    ServerSpec,
    WorkloadConfig,
    validate_fit,
)


def test_spec_values():
    assert N_SERVERS == 5
    assert SCORING.window == 10
    assert (SCORING.theta_cpu, SCORING.theta_mem) == (80.0, 85.0)
    assert SCORING.load_weights == (0.4, 0.4, 0.2)
    assert SCORING.score_weights == (0.6, 0.4)
    assert SCORING.risk_admission_threshold == 0.5


def test_servers_are_heterogeneous():
    assert len({(s.cores, s.speed) for s in SERVERS}) > 1
    assert len(WRR_WEIGHTS) == N_SERVERS


def test_derived_constants_positive():
    assert SCORING.r_ref > 0
    assert EXPERIMENT.r_sla > SCORING.r_ref


@pytest.mark.parametrize("weights", [(0.5, 0.4, 0.2), (1.2, -0.1, -0.1)])
def test_bad_load_weights_rejected(weights):
    with pytest.raises(ValueError):
        ScoringConfig(load_weights=weights)


def test_bad_score_weights_rejected():
    with pytest.raises(ValueError):
        ScoringConfig(score_weights=(0.6, 0.6))


@pytest.mark.parametrize("r_ref", [0.0, -1.0])
def test_nonpositive_r_ref_rejected(r_ref):
    with pytest.raises(ValueError):
        ScoringConfig(r_ref=r_ref)


def test_nonpositive_r_sla_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(r_sla=0.0)


def test_bursts_must_fit_horizon():
    with pytest.raises(ValueError):
        WorkloadConfig(t_sim=100, n_bursts=3, burst_length=50)


def test_invalid_server_rejected():
    with pytest.raises(ValueError):
        ServerSpec(cores=0, mem_gb=8, speed=1.0)


def test_task_too_large_for_smallest_server_rejected():
    tiny = SERVERS + (ServerSpec(cores=1, mem_gb=4, speed=1.0),)
    with pytest.raises(ValueError):
        validate_fit(tiny, WORKLOAD)
