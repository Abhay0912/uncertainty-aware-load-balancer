"""Load-balancing policies (Strategy pattern). One policy per module."""

from lbsim.policies.base import Policy, RandomizedPolicy, policy_rng
from lbsim.policies.least_cpu import LeastCPUPolicy
from lbsim.policies.p2c import PowerOfTwoChoicesPolicy
from lbsim.policies.probabilistic import ProbabilisticPolicy
from lbsim.policies.random_policy import RandomPolicy
from lbsim.policies.round_robin import RoundRobinPolicy
from lbsim.policies.weighted_metric import WeightedMetricPolicy
from lbsim.policies.wrr import WeightedRoundRobinPolicy
from lbsim.policies.earliest_completion import EarliestCompletionPolicy
from lbsim.policies.uncertainty_aware_ect import UncertaintyAwareECTPolicy
from lbsim.policies.oracle_ect import OracleECTPolicy

__all__ = [
    "Policy", "RandomizedPolicy", "policy_rng", "baseline_policies", "all_policies",
    "RoundRobinPolicy", "WeightedRoundRobinPolicy", "RandomPolicy",
    "LeastCPUPolicy", "WeightedMetricPolicy", "PowerOfTwoChoicesPolicy", "ProbabilisticPolicy",
    "EarliestCompletionPolicy", "UncertaintyAwareECTPolicy", "OracleECTPolicy",
]


def baseline_policies(seed: int) -> list[Policy]:
    """Fresh instances of the six baselines. Randomised ones draw from policy_rng(seed)."""
    return [
        RoundRobinPolicy(),
        WeightedRoundRobinPolicy(),
        RandomPolicy(policy_rng(seed)),
        LeastCPUPolicy(),
        WeightedMetricPolicy(),
        PowerOfTwoChoicesPolicy(policy_rng(seed)),
    ]


def all_policies(seed: int) -> list[Policy]:
    """The six baselines followed by the proposed probabilistic policy."""
    return [*baseline_policies(seed), ProbabilisticPolicy()]


def v2_policies(seed: int) -> list[Policy]:
    """Comparable matrix: original policies plus the two practical V2 variants."""
    return [*all_policies(seed), EarliestCompletionPolicy(), UncertaintyAwareECTPolicy()]
