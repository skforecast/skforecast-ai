# Unit test check_metric_domain

import re

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.recommendation.metric_selection import check_metric_domain
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


def _stats(minimum: float) -> dict:
    """
    Statistics of a series with the given minimum.
    """
    return {"min": minimum, "max": 100.0, "mean": 50.0, "std": 10.0}


@pytest.mark.parametrize(
    "minimum",
    [-1.0, -35.5],
    ids=lambda dt: f"min: {dt}",
)
def test_check_metric_domain_InvalidInputError_when_msle_and_target_at_or_below_minus_one(
    minimum,
):
    """
    Test that `mean_squared_log_error` on a target with values at or below
    -1, which sklearn rejects, raises `InvalidInputError` with
    `field='metric'`, giving the minimum of the target and what to use.
    """
    profile = _profile({"y": _stats(minimum)})

    err_msg = re.escape(
        f"`mean_squared_log_error` cannot be computed on this data: it takes "
        f"the logarithm of 1 plus each value, so it needs values above -1, "
        f"and the target has values down to {minimum:g}. Use a metric "
        f"without a logarithm, such as `mean_absolute_error` or "
        f"`root_mean_squared_error`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as info:
        check_metric_domain(
            ["mean_absolute_error", "mean_squared_log_error"], profile
        )

    assert info.value.field == "metric"


@pytest.mark.parametrize(
    "metrics, minimum",
    [
        (["mean_squared_log_error"], 0.0),
        (["mean_squared_log_error"], -0.5),
        (["mean_squared_log_error"], 5.0),
        (["mean_absolute_error", "root_mean_squared_error"], -50.0),
    ],
    ids=["MSLE at zero", "MSLE above -1", "MSLE positive", "no MSLE"],
)
def test_check_metric_domain_no_error_when_metric_fits_the_target(
    metrics, minimum
):
    """
    Test that MSLE on a target above -1, or metrics without a logarithm on
    any target, pass the check.
    """
    profile = _profile({"y": _stats(minimum)})

    assert check_metric_domain(metrics, profile) is None


def test_check_metric_domain_no_error_when_target_has_no_statistics():
    """
    Test that a profile without target statistics passes the check: there
    is no range to compare.
    """
    profile = _profile({})

    assert check_metric_domain(["mean_squared_log_error"], profile) is None


def test_check_metric_domain_InvalidInputError_names_the_series_when_multiseries():
    """
    Test that, with several series, the error names those at or below -1
    with their minimum, up to 5, and counts the rest.
    """
    profile = _profile({
        "ok": _stats(3.0),
        **{f"s{i}": _stats(-2.0 - i) for i in range(7)},
    })

    err_msg = re.escape(
        "and the target has values at or below -1 in 's0' (down to -2), "
        "'s1' (down to -3), 's2' (down to -4), 's3' (down to -5), 's4' "
        "(down to -6) and 2 more series."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        check_metric_domain(["mean_squared_log_error"], profile)
