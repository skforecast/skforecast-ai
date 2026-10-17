# Unit test _fitting_grid

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _fitting_grid

_DAYS = pd.date_range("2023-01-02", periods=20, freq="D")


@pytest.mark.parametrize(
    "index, frequency, expected",
    [
        (_DAYS, "D", _DAYS),
        (_DAYS.delete([3, 8, 15]), "D", _DAYS),
        (_DAYS.delete(list(range(1, 19, 2))), "D", _DAYS),
    ],
    ids=["full", "with gaps", "half of the grid"],
)
def test_fitting_grid_output_when_grid_fits(index, frequency, expected):
    """
    Test _fitting_grid returns the grid of the frequency from the first to the
    last timestamp when it holds every timestamp and at least half of it is
    observed (11 of 20 days).
    """
    result = _fitting_grid(index, frequency)
    pd.testing.assert_index_equal(result, expected)


@pytest.mark.parametrize(
    "index, frequency",
    [
        (_DAYS.insert(5, pd.Timestamp("2023-01-06 12:00")), "D"),
        (_DAYS[::3], "D"),
        (_DAYS, "B"),
    ],
    ids=["timestamp off the grid", "a third of the grid", "weekend off the grid"],
)
def test_fitting_grid_output_when_grid_does_not_fit(index, frequency):
    """
    Test _fitting_grid returns None when a timestamp lies off the grid (noon
    among days, a weekend among business days) or less than half of the grid
    is observed.
    """
    assert _fitting_grid(index, frequency) is None


def test_fitting_grid_output_when_grid_is_far_larger_than_the_index(monkeypatch):
    """
    Test _fitting_grid returns None without building a grid estimated at more
    than twice the size the minimum coverage allows: a grid of seconds over
    20 days would hold 1.6 million timestamps for 20 dates.
    """
    def build(*args, **kwargs):
        raise AssertionError("the grid was built")

    monkeypatch.setattr(pd, "date_range", build)

    assert _fitting_grid(_DAYS, "s") is None
