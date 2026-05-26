# Unit test run_forecast execution/runner

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import ForecastExecutionError
from skforecast_ai.execution.runner import run_forecast
from skforecast_ai.schemas import ForecastPlan

from .fixtures_execution import (
    df_multi,
    df_single,
    plan_multi,
    plan_single,
    plan_single_custom_kwargs,
    plan_single_with_intervals,
    profile_multi,
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


def test_run_forecast_single_series_returns_metrics():
    """
    Test that run_forecast returns a metrics DataFrame with MAE, MSE, and
    MASE for a single-series task.
    """
    result = run_forecast(data=df_single, profile=profile_single, plan=plan_single)

    metrics = result["metrics"]
    assert isinstance(metrics, pd.DataFrame)
    assert list(metrics.columns) == ["series", "MAE", "MSE", "MASE"]
    assert len(metrics) == 1
    assert metrics["series"].iloc[0] == "sales"
    assert metrics["MAE"].iloc[0] > 0
    assert metrics["MSE"].iloc[0] > 0
    assert metrics["MASE"].iloc[0] > 0


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
    metrics = result["metrics"]
    assert isinstance(metrics, pd.DataFrame)
    assert list(metrics.columns) == ["series", "MAE", "MSE", "MASE"]
    assert len(metrics) == n_series
    assert (metrics["MAE"] > 0).all()


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
        forecaster_kwargs={},
        estimator=None,
        steps=5,
        frequency="D",
        interval_method="native",
        use_exog=False,
        warnings=[],
        explanation="Statistical ARIMA model.",
    )

    result = run_forecast(data=df_single, profile=profile_single, plan=plan_stats)

    assert isinstance(result["predictions"], pd.DataFrame)
    assert len(result["predictions"]) == plan_stats.steps
    assert isinstance(result["metrics"], pd.DataFrame)
    assert result["metrics"]["MAE"].iloc[0] > 0
    assert result["intervals"] is not None


# Tests: run_forecast — unsupported task type


def test_run_forecast_ForecastExecutionError_when_invalid_estimator():
    """
    Test that run_forecast raises ForecastExecutionError when the generated
    code references an estimator that cannot be imported.
    """
    plan_bad = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        estimator="NonExistentEstimator",
        steps=5,
        frequency="D",
        explanation="Bad estimator.",
    )

    with pytest.raises((ValueError, ForecastExecutionError)):
        run_forecast(data=df_single, profile=profile_single, plan=plan_bad)





def test_run_forecast_single_series_with_custom_estimator_kwargs():
    """
    Test that run_forecast correctly passes estimator_kwargs to the
    estimator constructor (Ridge with alpha=0.5).
    """
    result = run_forecast(
        data=df_single, profile=profile_single, plan=plan_single_custom_kwargs
    )

    assert isinstance(result["predictions"], pd.DataFrame)
    assert len(result["predictions"]) == plan_single_custom_kwargs.steps
    assert result["metrics"]["MAE"].iloc[0] > 0
