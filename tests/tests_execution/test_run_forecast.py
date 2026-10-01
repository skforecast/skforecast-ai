# Unit test run_forecast execution/runner

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import ForecastExecutionError
from skforecast_ai.execution.forecast_runner import run_forecast
from skforecast_ai.schemas import ForecastPlan

from .fixtures_execution import (
    _end_train_single,
    df_multi,
    df_single,
    df_single_future_exog,
    plan_baseline,
    plan_multi,
    plan_single,
    plan_single_custom_kwargs,
    plan_single_predict,
    plan_single_predict_no_exog,
    plan_single_with_intervals,
    profile_multi,
    profile_single,
    profile_single_no_exog,
)


# Tests: run_forecast: single series


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
    Test that run_forecast includes prediction interval columns in
    predictions when interval_method is set to bootstrapping.
    """
    result = run_forecast(
        data=df_single, profile=profile_single, plan=plan_single_with_intervals
    )

    predictions = result["predictions"]
    assert isinstance(predictions, pd.DataFrame)
    assert len(predictions) == plan_single_with_intervals.steps
    assert "lower_bound" in predictions.columns
    assert "upper_bound" in predictions.columns


# Tests: run_forecast: multi series


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


# Tests: run_forecast: statistical


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
        end_train=_end_train_single,
        warnings=[],
        explanation="Statistical ARIMA model.",
    )

    result = run_forecast(data=df_single, profile=profile_single, plan=plan_stats)

    assert isinstance(result["predictions"], pd.DataFrame)
    assert len(result["predictions"]) == plan_stats.steps
    assert isinstance(result["metrics"], pd.DataFrame)
    assert result["metrics"]["MAE"].iloc[0] > 0
    assert "lower_bound" in result["predictions"].columns
    assert "upper_bound" in result["predictions"].columns


# Tests: run_forecast: baseline


def test_run_forecast_baseline_repeats_last_seasonal_period():
    """
    Test that run_forecast runs the ForecasterEquivalentDate baseline: each
    prediction repeats the training value one offset (7 days) earlier, the
    conformal interval columns are present and the metrics are computed.
    """
    result = run_forecast(data=df_single, profile=profile_single, plan=plan_baseline)

    train = df_single.set_index("date").loc[:_end_train_single, "sales"]
    expected_pred = train.iloc[-7:-2].to_numpy()

    predictions = result["predictions"]
    assert list(predictions.columns) == ["pred", "lower_bound", "upper_bound"]
    np.testing.assert_allclose(predictions["pred"].to_numpy(), expected_pred)
    assert list(result["metrics"].columns) == ["series", "MAE", "MSE", "MASE"]
    assert "ForecasterEquivalentDate" in result["rendered_code"].imports


# Tests: run_forecast: unsupported task type


def test_run_forecast_ValueError_when_estimator_not_supported():
    """
    Test that run_forecast raises ValueError, before writing the name into
    the script, for a plan whose estimator skipped validation (model_copy
    does not run the ForecastPlan validator).
    """
    plan_bad = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        estimator="Ridge",
        steps=5,
        frequency="D",
        end_train=_end_train_single,
        explanation="Bad estimator.",
    ).model_copy(update={"estimator": "NonExistentEstimator"})

    err_msg = re.escape("'NonExistentEstimator' is not a supported estimator.")
    with pytest.raises(ValueError, match=err_msg):
        run_forecast(data=df_single, profile=profile_single, plan=plan_bad)


def test_run_forecast_ForecastExecutionError_when_exog_column_is_missing():
    """
    Test that a script failing while it runs (the data lacks the exogenous
    column of the profile) raises ForecastExecutionError with the line and
    the statement of the executed code that failed.
    """
    data = df_single.rename(columns={"promo": "discount"})

    with pytest.raises(ForecastExecutionError, match=re.escape("KeyError")) as exc_info:
        run_forecast(data=data, profile=profile_single, plan=plan_single)

    error = exc_info.value
    statement = "forecaster.fit(y=data_train['sales'], exog=data_train[exog_features])"
    assert isinstance(error.original_error, KeyError)
    assert error.failed_statement == statement
    assert error.generated_code.splitlines()[error.failed_line - 1] == statement





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


# Tests: run_forecast: prediction mode (plan.end_train is None)


def test_run_forecast_prediction_mode_no_exog_returns_no_metrics():
    """
    Test that run_forecast in prediction mode (plan.end_train is None) for
    data without exogenous variables trains on all data, forecasts the
    future, and returns no metrics.
    """
    result = run_forecast(
        data=df_single,
        profile=profile_single_no_exog,
        plan=plan_single_predict_no_exog,
    )

    assert result["metrics"] is None
    assert isinstance(result["predictions"], pd.DataFrame)
    assert len(result["predictions"]) == plan_single_predict_no_exog.steps


def test_run_forecast_prediction_mode_with_exog_returns_no_metrics():
    """
    Test that run_forecast in prediction mode with exogenous variables uses
    the future `exog` supplied to forecast the horizon and returns no
    metrics.
    """
    result = run_forecast(
        data=df_single,
        profile=profile_single,
        plan=plan_single_predict,
        exog=df_single_future_exog,
    )

    assert result["metrics"] is None
    assert isinstance(result["predictions"], pd.DataFrame)
    assert len(result["predictions"]) == plan_single_predict.steps

