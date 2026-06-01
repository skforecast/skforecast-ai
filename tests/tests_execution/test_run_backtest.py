# Unit test run_backtest execution/backtesting_runner

import pandas as pd
import pytest

from skforecast_ai.exceptions import ForecastExecutionError
from skforecast_ai.execution.backtesting_runner import run_backtest
from skforecast_ai.schemas import ForecastPlan, RenderedScript

from .fixtures_execution import (
    cv_explanation_single,
    cv_multi,
    cv_short,
    cv_single,
    df_multi,
    df_short,
    df_single,
    plan_multi,
    plan_short,
    plan_single,
    plan_statistical,
    profile_multi,
    profile_short,
    profile_single,
    profile_single_no_exog,
)


# Tests: run_backtest — error handling


def test_run_backtest_ValueError_when_unsupported_task_type():
    """
    Test that run_backtest raises ValueError when the plan has an
    unsupported task_type not present in the dispatch table.
    """
    plan_bad = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        estimator="Ridge",
        steps=5,
        frequency="D",
        explanation="Bad task type.",
    )
    # Monkey-patch task_type to an unsupported value
    object.__setattr__(plan_bad, "task_type", "unsupported_type")

    with pytest.raises(ValueError, match="Unsupported task_type"):
        run_backtest(
            data=df_single,
            profile=profile_single,
            plan=plan_bad,
            cv=cv_single,
            cv_explanation=cv_explanation_single,
        )


def test_run_backtest_ForecastExecutionError_when_invalid_estimator():
    """
    Test that run_backtest raises ForecastExecutionError when the generated
    code references an estimator that cannot be imported.
    """
    plan_bad = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        estimator="NonExistentEstimator",
        steps=5,
        frequency="D",
        explanation="Bad estimator for backtesting.",
    )

    with pytest.raises((ValueError, ForecastExecutionError)):
        run_backtest(
            data=df_single,
            profile=profile_single,
            plan=plan_bad,
            cv=cv_single,
            cv_explanation=cv_explanation_single,
        )


# Tests: run_backtest — single series


def test_run_backtest_single_series_returns_dict_with_expected_keys():
    """
    Test that run_backtest returns a dict with keys 'metrics',
    'predictions', 'rendered_code', and 'explanation'.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    assert isinstance(result, dict)
    expected_keys = {"metrics", "predictions", "rendered_code", "explanation"}
    assert set(result.keys()) == expected_keys


def test_run_backtest_single_series_metrics_is_dataframe():
    """
    Test that run_backtest returns a metrics DataFrame with numeric values
    for a single-series task.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    metrics = result["metrics"]
    assert isinstance(metrics, pd.DataFrame)
    assert not metrics.empty
    # All non-level columns should have numeric values
    for col in metrics.columns:
        if col not in ("levels", "level"):
            assert metrics[col].dtype.kind == "f"


def test_run_backtest_single_series_predictions_is_dataframe():
    """
    Test that run_backtest returns a non-empty predictions DataFrame for
    a single-series task.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    predictions = result["predictions"]
    assert isinstance(predictions, pd.DataFrame)
    assert not predictions.empty


def test_run_backtest_single_series_rendered_code_is_RenderedScript():
    """
    Test that run_backtest returns a RenderedScript instance in the
    'rendered_code' key.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    assert isinstance(result["rendered_code"], RenderedScript)


def test_run_backtest_single_series_explanation_contains_metrics():
    """
    Test that the explanation string includes metric summary values from
    the backtesting results.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    explanation = result["explanation"]
    assert isinstance(explanation, str)
    assert "Results" in explanation
    assert cv_explanation_single in explanation


def test_run_backtest_single_series_show_progress_false():
    """
    Test that run_backtest executes without error when show_progress is
    set to False.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
        show_progress=False,
    )

    assert isinstance(result["metrics"], pd.DataFrame)
    assert not result["metrics"].empty


# Tests: run_backtest — multi series


def test_run_backtest_multi_series_returns_predictions():
    """
    Test that run_backtest works end-to-end for a multi-series task and
    returns a predictions DataFrame.
    """
    result = run_backtest(
        data=df_multi,
        profile=profile_multi,
        plan=plan_multi,
        cv=cv_multi,
        cv_explanation="Multi-series CV with 5 steps.",
    )

    assert isinstance(result["predictions"], pd.DataFrame)
    assert not result["predictions"].empty


def test_run_backtest_multi_series_metrics_per_level():
    """
    Test that multi-series backtesting returns metrics with one row per
    series level.
    """
    result = run_backtest(
        data=df_multi,
        profile=profile_multi,
        plan=plan_multi,
        cv=cv_multi,
        cv_explanation="Multi-series CV with 5 steps.",
    )

    metrics = result["metrics"]
    assert isinstance(metrics, pd.DataFrame)
    assert len(metrics) >= profile_multi.n_series


# Tests: run_backtest — statistical


@pytest.mark.slow
def test_run_backtest_statistical_returns_predictions():
    """
    Test that run_backtest works for statistical forecasters (ForecasterStats
    with Arima) and returns a predictions DataFrame.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single_no_exog,
        plan=plan_statistical,
        cv=cv_single,
        cv_explanation="Statistical backtesting with ARIMA.",
    )

    assert isinstance(result["predictions"], pd.DataFrame)
    assert not result["predictions"].empty
    assert isinstance(result["metrics"], pd.DataFrame)


# Tests: run_backtest — edge cases


def test_run_backtest_short_series_runs_without_error():
    """
    Test that run_backtest handles a short time series (30 observations)
    without raising an error.
    """
    result = run_backtest(
        data=df_short,
        profile=profile_short,
        plan=plan_short,
        cv=cv_short,
        cv_explanation="Short series CV with 5 steps.",
    )

    assert isinstance(result["metrics"], pd.DataFrame)
    assert isinstance(result["predictions"], pd.DataFrame)
