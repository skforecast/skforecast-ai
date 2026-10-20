# Unit test _build_backtest_explanation execution/backtesting_runner

import pandas as pd

from skforecast_ai.execution.backtesting_runner import _build_backtest_explanation

# Fixtures
from .fixtures_interval_coverage import (
    interval,
    predictions_single_200,
    metrics_single_06,
    predictions_multi_2,
    metrics_multi_2,
)


# Tests: _build_backtest_explanation: metric formatting


def test_build_backtest_explanation_includes_cv_and_metrics():
    """
    Test that _build_backtest_explanation combines the CV explanation with
    a metric summary when metrics are non-empty.
    """
    cv_explanation = "TimeSeriesFold with 10 steps, refit=False."
    metrics = pd.DataFrame({"mean_absolute_error": [1.2345], "mean_squared_error": [2.3456]})

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=metrics
    )

    assert cv_explanation in result
    assert "Results" in result
    assert "mean_absolute_error" in result
    assert "1.2345" in result


def test_build_backtest_explanation_empty_metrics_returns_cv_only():
    """
    Test that _build_backtest_explanation returns only the CV explanation
    when metrics is an empty DataFrame.
    """
    cv_explanation = "TimeSeriesFold with 10 steps, refit=False."
    metrics = pd.DataFrame()

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=metrics
    )

    assert result == cv_explanation


def test_build_backtest_explanation_none_metrics_returns_cv_only():
    """
    Test that _build_backtest_explanation returns only the CV explanation
    when metrics is None.
    """
    cv_explanation = "TimeSeriesFold with 10 steps, refit=False."

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=None
    )

    assert result == cv_explanation


def test_build_backtest_explanation_skips_level_columns():
    """
    Test that _build_backtest_explanation excludes 'levels' and 'level'
    columns from the metric summary string.
    """
    cv_explanation = "CV explanation."
    metrics = pd.DataFrame({
        "levels": ["series_a"],
        "mean_absolute_error": [0.5678],
    })

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=metrics
    )

    assert "levels" not in result.split("Results")[1]
    assert "mean_absolute_error" in result
    assert "0.5678" in result


def test_build_backtest_explanation_uses_average_row_when_multi_series():
    """
    Test that a multi-series metrics frame is summarised with its
    `average` row, not with the mean of every row: skforecast appends
    `average`, `weighted_average` and `pooling` rows, and averaging them
    together with the per-series rows produces a number that matches no
    row of the table.
    """
    metrics = pd.DataFrame({
        "levels": ["a", "b", "average", "weighted_average", "pooling"],
        "mean_absolute_error": [1.0, 3.0, 2.0, 2.0, 2.1],
    })

    result = _build_backtest_explanation(cv_explanation="CV.", metrics=metrics)

    assert result == "CV. Results (average across series): mean_absolute_error: 2.0000."


# Tests: _build_backtest_explanation: prediction interval coverage


def test_build_backtest_explanation_single_series_with_interval():
    """
    Test that with a prediction interval the `coverage` and `interval_width`
    metrics are not listed in the "Results" part and a sentence of their own
    is appended to the explanation.
    """
    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics_single_06,
        predictions    = predictions_single_200,
        interval       = interval,
    )

    expected = (
        "CV. Results: mean_absolute_error: 1.5000. Prediction interval "
        "[0.1, 0.9] (nominal coverage 80 %): 60 % of the 200 actual values "
        "fell inside it (coverage: 0.6000), with a mean width of 4.0000 in "
        "the units of the target (interval_width)."
    )
    assert result == expected


def test_build_backtest_explanation_multi_series_with_interval():
    """
    Test that a multi-series backtest with a prediction interval keeps the
    average row in the "Results" part, without the interval metrics, and
    appends the sentence by series.
    """
    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics_multi_2,
        predictions    = predictions_multi_2,
        interval       = interval,
    )

    expected = (
        "CV. Results (average across series): mean_absolute_error: 1.5000. "
        "Prediction interval [0.1, 0.9] (nominal coverage 80 %), share of "
        "the actual values inside it (coverage) and mean width in the units "
        "of each series (interval_width), by series: 'a' 80 % of 100 "
        "predictions, width 4.0000; 'b' 50 % of 100 predictions, width "
        "3.0000; average across series 65 %, width 3.5000."
    )
    assert result == expected
