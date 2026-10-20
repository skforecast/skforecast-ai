# Unit test _unit_notices

import pandas as pd
import pytest

from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _metric_notices, _unit_notices
from skforecast_ai.schemas import DataProfile

MAPE_NOTICE = ToolNotice(
    source   = "runtime",
    category = "MetricUnitNotice",
    message  = (
        "`mean_absolute_percentage_error` is a fraction, not a percentage: "
        "0.05 is 5 %, and 1.245 is 124.5 %. Multiply it by 100 before you "
        "write it with a % sign."
    ),
    count    = 1,
)

SMAPE_UNIT = (
    "`symmetric_mean_absolute_percentage_error` is already a percentage, "
    "from 0 to 200: 1.245 is 1.245 %. Write it with a % sign as it is, "
    "without multiplying it by 100."
)

RMSE_UNIT = (
    "`root_mean_squared_error` is in the units of the target (the square "
    "root of `mean_squared_error`, which is in squared units): report it as "
    "it is."
)


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


profile_positive = _profile({"y": {"min": 5.0, "max": 70.0, "mean": 40.0, "std": 9.0}})
profile_crossing_zero = _profile(
    {"y": {"min": -10.0, "max": 10.0, "mean": 0.0, "std": 7.3}}
)
profile_multi_crossing_zero = _profile({
    "a": {"min": 5.0, "max": 70.0, "mean": 40.0, "std": 9.0},
    "b": {"min": -2.0, "max": 30.0, "mean": 10.0, "std": 4.0},
})


@pytest.mark.parametrize(
    "columns",
    [
        ["mean_absolute_error", "mean_absolute_percentage_error"],
        ["levels", "mean_absolute_error", "mean_absolute_percentage_error"],
        ["rank", "name", "mean_absolute_percentage_error"],
    ],
    ids=lambda dt: f"columns: {dt}",
)
def test_unit_notices_unit_of_mape(columns):
    """
    Test that the metrics of a backtest or a forecast, one series or several
    (`levels`), or the leaderboard of a comparison with MAPE get one notice
    saying that it is a fraction, not a percentage.
    """
    metrics = pd.DataFrame([[1.245] * len(columns)], columns=columns)

    assert _unit_notices(metrics) == [MAPE_NOTICE]


@pytest.mark.parametrize(
    "metrics",
    [
        None,
        pd.DataFrame({
            "mean_absolute_error": [0.5],
            "mean_squared_error": [0.4],
            "mean_absolute_scaled_error": [0.1],
        }),
    ],
    ids=["no metrics", "no MAPE, sMAPE nor RMSE"],
)
def test_unit_notices_empty_without_mape_smape_nor_rmse(metrics):
    """
    Test that a result without metrics, or without MAPE, sMAPE and RMSE,
    gets no notice.
    """
    assert _unit_notices(metrics) == []


def test_unit_notices_follow_the_reference_of_the_scaled_metrics():
    """
    Test that `_metric_notices` gives the notice of MAPE after the one of
    the scaled metrics, and alone when no scaled metric was computed, and
    passes the profile on (an undefined MAPE on a target crossing zero).
    """
    both = pd.DataFrame(
        {"mean_absolute_scaled_error": [0.5], "mean_absolute_percentage_error": [1.2]}
    )
    alone = pd.DataFrame({"mean_absolute_percentage_error": [1.2]})

    assert [notice.category for notice in _metric_notices(both)] == [
        "MetricReferenceNotice", "MetricUnitNotice",
    ]
    assert _metric_notices(alone) == [MAPE_NOTICE]
    assert [
        notice.category
        for notice in _metric_notices(both, profile_crossing_zero)
    ] == ["MetricReferenceNotice", "MetricUndefinedNotice"]


@pytest.mark.parametrize(
    "columns",
    [
        ["mean_absolute_error", "symmetric_mean_absolute_percentage_error"],
        ["levels", "mean_absolute_error", "symmetric_mean_absolute_percentage_error"],
    ],
    ids=lambda dt: f"columns: {dt}",
)
def test_unit_notices_unit_of_smape(columns):
    """
    Test that the metrics of a backtest or of a forecast with sMAPE get one
    notice saying that it is already a percentage, not to multiply by 100,
    also on a target at or around zero.
    """
    metrics = pd.DataFrame([[1.245] * len(columns)], columns=columns)

    expected = [
        ToolNotice(
            source   = "runtime",
            category = "MetricUnitNotice",
            message  = SMAPE_UNIT,
            count    = 1,
        )
    ]
    assert _unit_notices(metrics) == expected
    assert _unit_notices(metrics, profile_crossing_zero) == expected


@pytest.mark.parametrize(
    "columns",
    [
        ["mean_squared_error", "root_mean_squared_error"],
        ["levels", "root_mean_squared_error"],
        ["rank", "name", "root_mean_squared_error"],
    ],
    ids=lambda dt: f"columns: {dt}",
)
def test_unit_notices_unit_of_rmse(columns):
    """
    Test that the metrics of a backtest or a forecast, one series or several
    (`levels`), or the leaderboard of a comparison with RMSE get one notice
    saying that it is in the units of the target, unlike MSE, also on a
    target at or around zero.
    """
    metrics = pd.DataFrame([[1.245] * len(columns)], columns=columns)

    expected = [
        ToolNotice(
            source   = "runtime",
            category = "MetricUnitNotice",
            message  = RMSE_UNIT,
            count    = 1,
        )
    ]
    assert _unit_notices(metrics) == expected
    assert _unit_notices(metrics, profile_crossing_zero) == expected


def test_unit_notices_unit_of_mape_and_smape_in_one_notice():
    """
    Test that a result with MAPE and sMAPE gets a single unit notice that
    gives the unit of each one: a fraction and a percentage.
    """
    metrics = pd.DataFrame({
        "mean_absolute_percentage_error": [0.011278],
        "symmetric_mean_absolute_percentage_error": [1.136376],
    })

    assert _unit_notices(metrics, profile_positive) == [
        ToolNotice(
            source   = "runtime",
            category = "MetricUnitNotice",
            message  = f"{MAPE_NOTICE.message} {SMAPE_UNIT}",
            count    = 1,
        )
    ]


def test_unit_notices_unit_of_rmse_after_mape_and_smape_in_one_notice():
    """
    Test that a result with MAPE, sMAPE and RMSE gets a single unit notice
    that gives the unit of each one, RMSE last, and that on a target at or
    around zero RMSE keeps its unit next to the notice of an undefined MAPE.
    """
    metrics = pd.DataFrame({
        "root_mean_squared_error": [2.5],
        "mean_absolute_percentage_error": [0.011278],
        "symmetric_mean_absolute_percentage_error": [1.136376],
    })

    assert _unit_notices(metrics, profile_positive) == [
        ToolNotice(
            source   = "runtime",
            category = "MetricUnitNotice",
            message  = f"{MAPE_NOTICE.message} {SMAPE_UNIT} {RMSE_UNIT}",
            count    = 1,
        )
    ]
    notices = _unit_notices(metrics, profile_crossing_zero)
    assert [notice.category for notice in notices] == [
        "MetricUnitNotice", "MetricUndefinedNotice",
    ]
    assert notices[0].message == f"{SMAPE_UNIT} {RMSE_UNIT}"


def test_unit_notices_positive_target_keeps_the_unit_of_mape():
    """
    Test that the profile of a target away from zero changes nothing: MAPE
    gets its unit notice.
    """
    metrics = pd.DataFrame({"mean_absolute_percentage_error": [0.05]})

    assert _unit_notices(metrics, profile_positive) == [MAPE_NOTICE]


def test_unit_notices_undefined_mape_on_target_crossing_zero():
    """
    Test that MAPE on a target that crosses zero gets a notice saying that
    it has no meaning (with the range of the target), and never the one that
    says to multiply it by 100.
    """
    metrics = pd.DataFrame({"mean_absolute_percentage_error": [3.3e13]})

    assert _unit_notices(metrics, profile_crossing_zero) == [
        ToolNotice(
            source   = "runtime",
            category = "MetricUndefinedNotice",
            message  = (
                "`mean_absolute_percentage_error` has no meaning on this "
                "data: it divides each error by the actual value, and the "
                "target takes values at or around zero (from -10 to 10). Do "
                "not report its value, neither as a fraction nor as a "
                "percentage, and do not convert it: say that MAPE is not "
                "defined for this target, and use a metric that does not "
                "divide by the actual value, such as `mean_absolute_error`."
            ),
            count    = 1,
        )
    ]


def test_unit_notices_undefined_mape_names_the_series_and_keeps_smape():
    """
    Test that, with several series, the notice of an undefined MAPE names
    the series at or around zero, and that sMAPE keeps its unit notice
    without the text of MAPE.
    """
    metrics = pd.DataFrame({
        "levels": ["a", "b"],
        "mean_absolute_percentage_error": [0.05, 4.1e12],
        "symmetric_mean_absolute_percentage_error": [4.9, 80.2],
    })

    notices = _unit_notices(metrics, profile_multi_crossing_zero)

    assert [notice.category for notice in notices] == [
        "MetricUnitNotice", "MetricUndefinedNotice",
    ]
    assert notices[0].message == SMAPE_UNIT
    assert "in series 'b' (from -2 to 30)" in notices[1].message
