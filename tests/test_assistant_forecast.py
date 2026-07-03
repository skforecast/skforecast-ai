# Unit test forecast ForecastingAssistant

import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import IgnoredArgumentWarning

from skforecast_ai import ForecastingAssistant, ForecastResult

from tests.fixtures_assistant import (
    df_single,
    df_no_exog,
    df_short,
    df_multi_long,
    series_single,
    series_unnamed,
)


# =============================================================================
# Tests: basic output
# =============================================================================
def test_forecast_output_when_single_series():
    """
    Test that forecast() returns a ForecastResult with all fields
    populated for a single-series dataset.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
        test_size=0.2,
    )

    assert isinstance(result, ForecastResult)
    assert result.profile is not None
    assert result.plan is not None
    assert result.code is not None
    assert isinstance(result.metrics, pd.DataFrame)
    assert list(result.metrics.columns) == ["series", "MAE", "MSE", "MASE"]
    assert len(result.metrics) == 1
    assert result.metrics["MAE"].iloc[0] > 0
    assert result.predictions is not None


def test_forecast_predictions_length_matches_steps():
    """
    Test that the number of prediction rows matches the requested steps.
    """
    steps = 7
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=steps,
        test_size=0.2,
    )

    assert len(result.predictions) == steps


def test_forecast_code_contains_skforecast_imports():
    """
    Test that the generated code field is a non-empty string containing
    skforecast imports.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        test_size=0.2,
    )

    assert isinstance(result.code, str)
    assert len(result.code) > 0
    assert "skforecast" in result.code


# =============================================================================
# Tests: pandas Series input
# =============================================================================
def test_forecast_output_when_named_series():
    """
    Test that forecast() accepts a named pandas Series and derives the
    target from the Series name.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(data=series_single, steps=10)

    assert isinstance(result, ForecastResult)
    assert result.plan.task_type == "single_series"
    assert len(result.predictions) == 10


def test_forecast_warns_and_uses_y_when_unnamed_series():
    """
    Test that forecast() warns and uses 'y' as the target when the input
    Series has no name.
    """
    assistant = ForecastingAssistant()
    with pytest.warns(UserWarning, match="using 'y'"):
        result = assistant.forecast(data=series_unnamed, steps=5)

    assert result.profile.data_profile.target == "y"
    assert len(result.predictions) == 5


# =============================================================================
# Tests: feature-rich (intervals, exog, multi-series)
# =============================================================================
def test_forecast_output_when_interval_requested():
    """
    Test that forecast() includes prediction interval columns in
    predictions when interval is specified.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        interval=[0.1, 0.9],
        test_size=0.2,
    )

    assert isinstance(result.predictions, pd.DataFrame)
    assert len(result.predictions) == 5
    assert "lower_bound" in result.predictions.columns
    assert "upper_bound" in result.predictions.columns


def test_forecast_output_when_no_exog():
    """
    Test that forecast() works correctly for data without exogenous
    variables.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_no_exog,
        target="sales",
        date_column="date",
        steps=5,
    )

    assert isinstance(result, ForecastResult)
    assert result.plan.use_exog is False
    assert len(result.predictions) == 5


@pytest.mark.slow
def test_forecast_output_when_multi_series_long_format():
    """
    Test that forecast() handles long-format multi-series data and
    returns predictions for all series.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
        steps=5,
    )

    assert isinstance(result, ForecastResult)
    assert result.plan.task_type == "multi_series"
    assert result.predictions is not None
    assert len(result.predictions) > 0


# =============================================================================
# Tests: edge cases
# =============================================================================
def test_forecast_output_when_short_series():
    """
    Test that forecast() handles a short time series (25 observations)
    without errors.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_short,
        target="sales",
        date_column="date",
        steps=3,
    )

    assert isinstance(result, ForecastResult)
    assert len(result.predictions) == 3


def test_forecast_metrics_are_finite():
    """
    Test that forecast metrics are finite positive numbers.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        test_size=0.2,
    )

    assert np.isfinite(result.metrics["MAE"].iloc[0])
    assert np.isfinite(result.metrics["MSE"].iloc[0])
    assert result.metrics["MAE"].iloc[0] > 0
    assert result.metrics["MSE"].iloc[0] > 0


# =============================================================================
# Tests: ignored plan-override warning
# =============================================================================
def test_forecast_IgnoredArgumentWarning_when_interval_passed_with_plan():
    """
    Test that forecast() warns with IgnoredArgumentWarning when an interval
    override is passed alongside a pre-built plan, because the planning
    stage (which consumes interval) is skipped.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    with pytest.warns(IgnoredArgumentWarning, match="pre-built `plan`"):
        assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
            interval=[0.1, 0.9],
            test_size=0.2,
            profile=profile,
            plan=plan,
        )


def test_forecast_no_override_warning_when_plan_without_overrides():
    """
    Test that forecast() does not emit the plan-override warning when a
    pre-built plan is passed without any plan-shaping override arguments.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
            test_size=0.2,
            profile=profile,
            plan=plan,
        )

    assert not any("pre-built `plan`" in str(w.message) for w in records)


# =============================================================================
# Tests: evaluation vs prediction mode
# =============================================================================
def test_forecast_evaluation_mode_returns_metrics():
    """
    Test that forecast() in evaluation mode (test_size set) returns a
    metrics DataFrame computed against the held-out test set.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        test_size=0.2,
    )

    assert isinstance(result.metrics, pd.DataFrame)
    assert list(result.metrics.columns) == ["series", "MAE", "MSE", "MASE"]
    assert result.plan.end_train is not None


def test_forecast_prediction_mode_returns_no_metrics():
    """
    Test that forecast() in prediction mode (test_size None) trains on all
    data, forecasts the future, and returns no metrics.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_no_exog,
        target="sales",
        date_column="date",
        steps=5,
    )

    assert result.metrics is None
    assert result.plan.end_train is None
    assert len(result.predictions) == 5


def test_forecast_prediction_mode_with_exog_returns_no_metrics():
    """
    Test that forecast() in prediction mode with exogenous data forecasts
    the future using the supplied future `exog` and returns no metrics.
    """
    future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
    exog = pd.DataFrame({"promo": np.tile([0.0, 1.0], 3)[:5]}, index=future_dates)

    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        exog=exog,
    )

    assert result.metrics is None
    assert result.plan.end_train is None
    assert len(result.predictions) == 5


# =============================================================================
# Tests: forecast-mode validation guards
# =============================================================================
def test_forecast_ValueError_when_test_size_and_exog_combined():
    """
    Test that forecast() raises ValueError when both test_size (evaluation
    mode) and exog (prediction mode) are supplied.
    """
    future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
    exog = pd.DataFrame({"promo": np.tile([0.0, 1.0], 3)[:5]}, index=future_dates)

    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="only used for future prediction"):
        assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
            test_size=0.2,
            exog=exog,
        )


def test_forecast_ValueError_when_prediction_mode_missing_exog():
    """
    Test that forecast() raises ValueError in prediction mode when the data
    contains exogenous variables but no future `exog` is provided.
    """
    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="exog. is required for future prediction"):
        assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
        )


def test_forecast_ValueError_when_exog_provided_without_exog_data():
    """
    Test that forecast() raises ValueError in prediction mode when future
    `exog` is provided but the data contains no exogenous variables.
    """
    future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
    exog = pd.DataFrame({"promo": np.tile([0.0, 1.0], 3)[:5]}, index=future_dates)

    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="data contains no exogenous"):
        assistant.forecast(
            data=df_no_exog,
            target="sales",
            date_column="date",
            steps=5,
            exog=exog,
        )


def test_forecast_prebuilt_evaluation_plan_without_test_size_no_exog_required():
    """
    Test that a pre-built evaluation-mode plan (its `end_train` already set)
    passed without `test_size` runs in evaluation mode and does NOT demand
    future `exog`, even when the data contains exogenous variables. The
    effective mode is driven by the plan's `end_train`, not by `test_size`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    split_date = str(df_single["date"].iloc[int(len(df_single) * 0.8)].date())
    plan = plan.model_copy(update={"end_train": split_date})

    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        profile=profile,
        plan=plan,
    )

    assert result.metrics is not None
    assert result.plan.end_train == split_date


def test_forecast_ValueError_when_exog_with_prebuilt_evaluation_plan():
    """
    Test that supplying `exog` alongside a pre-built evaluation-mode plan
    (no `test_size`) raises, because evaluation mode takes its test-set
    exogenous values from the split.
    """
    future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
    exog = pd.DataFrame({"promo": np.tile([0.0, 1.0], 3)[:5]}, index=future_dates)

    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    split_date = str(df_single["date"].iloc[int(len(df_single) * 0.8)].date())
    plan = plan.model_copy(update={"end_train": split_date})

    with pytest.raises(ValueError, match="only used for future prediction"):
        assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
            exog=exog,
            profile=profile,
            plan=plan,
        )
