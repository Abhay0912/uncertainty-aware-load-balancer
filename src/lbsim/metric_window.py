"""Fixed-length rolling window with mean and population std (spec section 3.1)."""

from __future__ import annotations

import math
from collections import deque


class MetricWindow:
    """Keeps the latest `size` observations. Empty windows report 0.0 (an idle, unobserved server)."""

    def __init__(self, size: int) -> None:
        if size < 1:
            raise ValueError("window size must be >= 1")
        self._values: deque[float] = deque(maxlen=size)

    @property
    def size(self) -> int:
        return self._values.maxlen  # type: ignore[return-value]

    def __len__(self) -> int:
        return len(self._values)

    def is_full(self) -> bool:
        return len(self._values) == self.size

    def push(self, value: float) -> None:
        self._values.append(float(value))

    def values(self) -> tuple[float, ...]:
        return tuple(self._values)

    def latest(self) -> float:
        return self._values[-1] if self._values else 0.0

    def mean(self) -> float:
        return math.fsum(self._values) / len(self._values) if self._values else 0.0

    def std(self) -> float:
        """Population std (ddof=0). Exactly 0.0 for constant windows, so the sigma=0 rule triggers reliably."""
        if not self._values or max(self._values) == min(self._values):
            return 0.0
        mu = self.mean()
        return math.sqrt(math.fsum((x - mu) ** 2 for x in self._values) / len(self._values))
