# Unit test _build_backtest_explanation execution/backtesting_runner

import pandas as pd

from skforecast_ai.execution.backtesting_runner import _build_backtest_explanation


# Tests: _build_backtest_explanation — metric formatting


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
