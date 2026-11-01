import numpy as np
import pytest

from lbsim.metric_window import MetricWindow


def test_matches_numpy_population_stats():
    rng = np.random.default_rng(0)
    data = rng.uniform(0, 100, 25)
    w = MetricWindow(10)
    for x in data:
        w.push(x)
    assert w.values() == pytest.approx(tuple(data[-10:]))
    assert w.mean() == pytest.approx(np.mean(data[-10:]))
    assert w.std() == pytest.approx(np.std(data[-10:], ddof=0))


def test_evicts_oldest():
    w = MetricWindow(3)
    for x in (1, 2, 3, 4):
        w.push(x)
    assert w.values() == (2.0, 3.0, 4.0)
    assert w.latest() == 4.0
    assert w.is_full() and len(w) == 3


def test_partial_window_uses_available_values():
    w = MetricWindow(10)
    w.push(10)
    w.push(30)
    assert not w.is_full()
    assert w.mean() == 20.0
    assert w.std() == 10.0


def test_empty_window_reports_zero():
    w = MetricWindow(5)
    assert (w.latest(), w.mean(), w.std()) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("value", [0.0, 0.1, 80.1, 100.0])
def test_constant_window_has_exactly_zero_std(value):
    w = MetricWindow(10)
    for _ in range(10):
        w.push(value)
    assert w.std() == 0.0


def test_single_value_has_zero_std():
    w = MetricWindow(10)
    w.push(42.0)
    assert w.std() == 0.0


def test_invalid_size():
    with pytest.raises(ValueError):
        MetricWindow(0)
