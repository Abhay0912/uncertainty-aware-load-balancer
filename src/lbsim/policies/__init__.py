"""Load-balancing policies (Strategy pattern). One policy per module."""

from lbsim.policies.base import Policy, RandomizedPolicy, policy_rng
from lbsim.policies.least_cpu import LeastCPUPolicy
from lbsim.policies.p2c import PowerOfTwoChoicesPolicy
from lbsim.policies.random_policy import RandomPolicy
from lbsim.policies.round_robin import RoundRobinPolicy
from lbsim.policies.weighted_metric import WeightedMetricPolicy
from lbsim.policies.wrr import WeightedRoundRobinPolicy

__all__ = [
    "Policy", "RandomizedPolicy", "policy_rng", "baseline_policies",
    "RoundRobinPolicy", "WeightedRoundRobinPolicy", "RandomPolicy",
    "LeastCPUPolicy", "WeightedMetricPolicy", "PowerOfTwoChoicesPolicy",
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
