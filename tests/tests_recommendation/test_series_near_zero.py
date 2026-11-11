# Unit test series_near_zero

import pytest

from skforecast_ai.recommendation.metric_selection import series_near_zero
from skforecast_ai.schemas import DataProfile


def _profile(target_stats: dict) -> DataProfile:
    """
    Profile with the given target statistics, one entry per series.
    """
    return DataProfile(
        n_series       = max(len(target_stats), 1),
        series_lengths = {name: 100 for name in target_stats} or {"y": 100},
        target         = "y",
        index_type     = "datetime",
        frequency      = "D",
        target_stats   = target_stats,
    )


@pytest.mark.parametrize(
    "minimum, maximum, expected",
    [
        (5.2, 100.0, []),
        (0.0, 100.0, ["y"]),
        (0.01, 100.0, ["y"]),
        (0.011, 100.0, []),
        (-0.005, 100.0, ["y"]),
        (-10.0, 10.0, ["y"]),
        (-80.0, -0.01, ["y"]),
        (-80.0, -0.011, []),
        (-80.0, 0.0, ["y"]),
        (-0.001, 0.001, ["y"]),
    ],
    ids=lambda dt: f"{dt}",
)
def test_series_near_zero_single_series(minimum, maximum, expected):
    """
    Test that a series is near zero when its range reaches the band from
    -0.01 to 0.01: it touches zero (minimum or maximum in the band) or
    crosses it (negative minimum, positive maximum). A range on one side,
    away from the band, is not.
    """
    profile = _profile({"y": {"min": minimum, "max": maximum, "mean": 0.0, "std": 1.0}})

    assert series_near_zero(profile) == expected


def test_series_near_zero_names_each_series_in_order():
    """
    Test that, with several series, only those that touch or cross zero are
    returned, in the order of `target_stats`.
    """
    profile = _profile({
        "c": {"min": -3.0, "max": 4.0, "mean": 0.5, "std": 1.0},
        "a": {"min": 10.0, "max": 20.0, "mean": 15.0, "std": 1.0},
        "b": {"min": 0.0, "max": 9.0, "mean": 4.0, "std": 1.0},
    })

    assert series_near_zero(profile) == ["c", "b"]


def test_series_near_zero_empty_without_statistics():
    """
    Test that a profile without target statistics, or a series whose
    statistics lack the minimum or the maximum, has no series near zero.
    """
    assert series_near_zero(_profile({})) == []
    assert series_near_zero(_profile({"y": {}})) == []
