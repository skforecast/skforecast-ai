# Unit test forecast ForecastingAssistant

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant, ForecastResult

from tests.fixtures_assistant import df_single, df_no_exog, df_short, df_multi_long


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
    )

    assert isinstance(result.code, str)
    assert len(result.code) > 0
    assert "skforecast" in result.code


# =============================================================================
# Tests: feature-rich (intervals, exog, multi-series)
# =============================================================================
def test_forecast_output_when_interval_requested():
    """
    Test that forecast() returns intervals as a DataFrame when interval
    is specified.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        interval=[10, 90],
    )

    assert result.intervals is not None
    assert isinstance(result.intervals, pd.DataFrame)
    assert len(result.intervals) == 5


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
    )

    assert np.isfinite(result.metrics["MAE"].iloc[0])
    assert np.isfinite(result.metrics["MSE"].iloc[0])
    assert result.metrics["MAE"].iloc[0] > 0
    assert result.metrics["MSE"].iloc[0] > 0
