# Unit test run_forecast execution/runner

import re

import pandas as pd
import pytest

from skforecast_ai.execution.runner import run_forecast
from skforecast_ai.execution.runner import validate_run_inputs
from skforecast_ai.schemas import ForecastPlan

from .fixtures_execution import (
    df_multi,
    df_short,
    df_single,
    plan_multi,
    plan_short,
    plan_single,
    plan_single_with_intervals,
    profile_multi,
    profile_short,
    profile_single,
)


# Tests: run_forecast — single series


def test_run_forecast_single_series_returns_predictions():
    """
    Test that run_forecast returns predictions with length equal to steps
    for a single-series task.
    """
    result = run_forecast(data=df_single, profile=profile_single, plan=plan_single)

    assert isinstance(result["predictions"], pd.DataFrame)
    assert len(result["predictions"]) == plan_single.steps


def test_run_forecast_single_series_returns_metric():
    """
    Test that run_forecast returns metric_name and a positive metric_value
    for a single-series task.
    """
    result = run_forecast(data=df_single, profile=profile_single, plan=plan_single)

    assert result["metric_name"] == "mean_absolute_error"
    assert isinstance(result["metric_value"], float)
    assert result["metric_value"] > 0


def test_run_forecast_single_series_with_intervals():
    """
    Test that run_forecast returns prediction intervals when interval_method
    is set to bootstrapping.
    """
    result = run_forecast(
        data=df_single, profile=profile_single, plan=plan_single_with_intervals
    )

    assert result["intervals"] is not None
    assert isinstance(result["intervals"], pd.DataFrame)
    assert len(result["intervals"]) == plan_single_with_intervals.steps


# Tests: run_forecast — multi series


def test_run_forecast_multi_series_returns_predictions():
    """
    Test that run_forecast works end-to-end for a multi-series task and
    returns predictions.
    """
    result = run_forecast(data=df_multi, profile=profile_multi, plan=plan_multi)

    assert isinstance(result["predictions"], pd.DataFrame)
    # Multi-series returns steps * n_series rows
    n_series = profile_multi.n_series
    assert len(result["predictions"]) == plan_multi.steps * n_series
    assert result["metric_name"] == "mean_absolute_error"
    assert isinstance(result["metric_value"], float)
    assert result["metric_value"] > 0


# Tests: run_forecast — statistical


@pytest.mark.slow
def test_run_forecast_statistical_returns_predictions():
    """
    Test that run_forecast works for statistical forecasters (ForecasterStats
    with Arima).
    """
    plan_stats = ForecastPlan(
        task_type="statistical",
        forecaster="ForecasterStats",
        estimator=None,
        steps=5,
        frequency="D",
        forecaster_kwargs={},
        interval_method=None,
        use_exog=False,
        data_requirements=[],
        warnings=[],
        explanation="Statistical ARIMA model.",
    )

    result = run_forecast(data=df_single, profile=profile_single, plan=plan_stats)

    assert isinstance(result["predictions"], pd.DataFrame)
    assert len(result["predictions"]) == plan_stats.steps
    assert isinstance(result["metric_value"], float)
    assert result["intervals"] is not None


# Tests: run_forecast — unsupported task type


def test_run_forecast_ValueError_when_unsupported_task_type():
    """
    Test that run_forecast raises ValueError for task types not yet
    supported by the execution engine (e.g. multivariate).
    """
    plan_unsupported = ForecastPlan(
        task_type="multivariate",
        forecaster="ForecasterDirectMultiVariate",
        estimator="Ridge",
        steps=5,
        explanation="Unsupported.",
    )

    err_msg = re.escape(
        "Unsupported task_type 'multivariate' for execution. "
        "Supported types: ['single_series', 'multi_series', 'statistical', "
        "'foundation']"
    )
    with pytest.raises(ValueError, match=err_msg):
        run_forecast(data=df_single, profile=profile_single, plan=plan_unsupported)


# Tests: validate_run_inputs


def test_validate_run_inputs_warns_horizon_exceeds_observations():
    """
    Test that validate_run_inputs returns a warning when steps exceeds
    the total number of observations.
    """
    plan_huge_steps = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        steps=500,
        frequency="D",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        explanation="Huge steps.",
    )

    warnings = validate_run_inputs(
        data=df_short, profile=profile_short, plan=plan_huge_steps
    )

    assert any("exceeds available observations" in w for w in warnings)


def test_validate_run_inputs_warns_short_series():
    """
    Test that validate_run_inputs returns a warning when the series has fewer
    than 50 observations.
    """
    warnings = validate_run_inputs(
        data=df_short, profile=profile_short, plan=plan_short
    )

    assert len(warnings) >= 1
    assert any("fewer than 50" in w for w in warnings)


def test_validate_run_inputs_warns_steps_exceeds_test_size():
    """
    Test that validate_run_inputs warns when steps exceeds the test set size.
    """
    plan_large_steps = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        steps=100,
        frequency="D",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        explanation="Large steps.",
    )

    warnings = validate_run_inputs(
        data=df_single, profile=profile_single, plan=plan_large_steps
    )

    assert len(warnings) >= 1
    assert any("exceeds test set size" in w for w in warnings)
