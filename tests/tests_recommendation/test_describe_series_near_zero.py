# Unit test describe_series_near_zero

from skforecast_ai.recommendation.metric_selection import describe_series_near_zero
from skforecast_ai.schemas import DataProfile


def _profile(target_stats: dict) -> DataProfile:
    """
    Profile with the given target statistics, one entry per series.
    """
    return DataProfile(
        n_series       = len(target_stats),
        series_lengths = {name: 100 for name in target_stats},
        target         = "y",
        index_type     = "datetime",
        frequency      = "D",
        target_stats   = target_stats,
    )


def _stats(minimum: float, maximum: float) -> dict:
    """
    Target statistics with the given range.
    """
    return {"min": minimum, "max": maximum, "mean": 0.0, "std": 1.0}


def test_describe_series_near_zero_none_away_from_zero():
    """
    Test that a target away from zero gets no description.
    """
    profile = _profile({"y": _stats(5.2, 100.0)})

    assert describe_series_near_zero(profile) is None


def test_describe_series_near_zero_single_series():
    """
    Test that one series is described with its range, without its name.
    """
    profile = _profile({"y": _stats(-10.0, 10.0)})

    assert describe_series_near_zero(profile) == (
        "the target takes values at or around zero (from -10 to 10)"
    )


def test_describe_series_near_zero_one_of_several_series():
    """
    Test that one series among several is named, with its range.
    """
    profile = _profile({"a": _stats(5.0, 9.0), "b": _stats(-3.5, 4.0)})

    assert describe_series_near_zero(profile) == (
        "the target takes values at or around zero in series 'b' "
        "(from -3.5 to 4)"
    )


def test_describe_series_near_zero_several_series_shows_five():
    """
    Test that several series are counted and the first five are named with
    their range, followed by how many more.
    """
    profile = _profile({f"s{i}": _stats(-float(i), 10.0) for i in range(1, 8)})

    assert describe_series_near_zero(profile) == (
        "the target takes values at or around zero in 7 series ('s1': -1 to "
        "10, 's2': -2 to 10, 's3': -3 to 10, 's4': -4 to 10, 's5': -5 to 10 "
        "and 2 more series)"
    )
