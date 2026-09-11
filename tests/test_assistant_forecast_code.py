# Unit test forecast_code ForecastingAssistant

import numpy as np
import pandas as pd
import re

import pytest


from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import CodeGenerationResult

from tests.fixtures_assistant import df_single, df_multi_long, df_no_exog


# =============================================================================
# Tests: forecast_code with pre-computed profile and plan
# =============================================================================
def test_forecast_code_with_profile_and_plan_when_single_series():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    a valid Python script for single series.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert "import" in result.code
    assert "ForecasterRecursive" in result.code
    assert "fit" in result.code or "predict" in result.code


def test_forecast_code_with_profile_and_plan_when_multi_series():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    code containing the multi-series forecaster class.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    result = assistant.forecast_code(
        data=df_multi_long, target="value", steps=5, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert "ForecasterRecursiveMultiSeries" in result.code


def test_forecast_code_with_profile_and_plan_when_statistical():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    code for statistical models (ForecasterStats).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert "ForecasterStats" in result.code


def test_forecast_code_with_profile_and_plan_contains_frequency():
    """
    Test that generated code includes the frequency assignment.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert "freq" in result.code.lower() or "asfreq" in result.code


# =============================================================================
# Tests: forecast_code: basic output
# =============================================================================
def test_forecast_code_output_when_single_series():
    """
    Test that forecast_code() returns a CodeGenerationResult with all
    fields populated for a single-series dataset.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert result.plan.steps == 10
    assert result.profile is not None
    assert "import" in result.code


def test_forecast_code_output_when_forecaster_selected():
    """
    Test that forecast_code() generates code for an explicitly selected
    forecaster.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
        forecaster="ForecasterDirect",
    )

    assert result.plan.forecaster == "ForecasterDirect"
    assert "ForecasterDirect" in result.code


def test_forecast_code_output_when_no_exog():
    """
    Test that forecast_code() works correctly for data without exogenous
    variables.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, CodeGenerationResult)
    assert result.plan.use_exog is False


def test_forecast_code_output_when_interval_requested():
    """
    Test that forecast_code() includes interval logic when interval is
    specified.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
        interval=[0.1, 0.9],
    )

    assert result.plan.interval == [0.1, 0.9]
    assert "interval" in result.code.lower() or "predict_interval" in result.code


# =============================================================================
# Tests: evaluation vs prediction mode
# =============================================================================
def test_forecast_code_prediction_mode_when_test_size_not_set():
    """
    Test that forecast_code() generates prediction-mode code by default
    (no test_size): no train/test split, no metrics, fit on the full data.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=10
    )

    assert result.plan.end_train is None
    assert "# Train/test split" not in result.code
    assert "data_train" not in result.code
    assert "# Evaluate on test set" not in result.code


def test_forecast_code_evaluation_mode_when_test_size_set():
    """
    Test that forecast_code() generates evaluation-mode code when test_size
    is set: train/test split, metrics, and a concrete end_train date.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=10,
        test_size=0.2,
    )

    assert result.plan.end_train is not None
    assert "# Train/test split" in result.code
    assert "data_train" in result.code
    assert "# Evaluate on test set" in result.code


# =============================================================================
# Tests: exog argument (mirrors forecast, validation only)
# =============================================================================
def test_forecast_code_does_not_require_exog_in_prediction_mode():
    """
    Test that forecast_code() generates prediction-mode code for data with
    exogenous variables without requiring future `exog` (unlike forecast(),
    the script loads the future values from a CSV at run time).
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single, target="sales", date_column="date", steps=10
    )

    assert result.plan.end_train is None
    assert "data_train" not in result.code
    assert "exog_future" in result.code


def test_forecast_code_ValueError_when_test_size_and_exog_combined():
    """
    Test that forecast_code() rejects `test_size` and `exog` supplied
    together, mirroring forecast().
    """
    future_dates = pd.date_range("2023-04-11", periods=10, freq="D")
    exog = pd.DataFrame(
        {"promo": np.tile([0.0, 1.0], 5)}, index=future_dates
    )

    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="only used for future prediction"):
        assistant.forecast_code(
            data=df_single, target="sales", date_column="date", steps=10,
            test_size=0.2, exog=exog,
        )


def test_forecast_code_ValueError_when_exog_without_exog_data():
    """
    Test that forecast_code() rejects future `exog` when the data has no
    exogenous variables, mirroring forecast().
    """
    future_dates = pd.date_range("2023-04-11", periods=10, freq="D")
    exog = pd.DataFrame(
        {"promo": np.tile([0.0, 1.0], 5)}, index=future_dates
    )

    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="data contains no exogenous"):
        assistant.forecast_code(
            data=df_no_exog, target="sales", date_column="date", steps=10,
            exog=exog,
        )


# =============================================================================
# Tests: plan overrides
# =============================================================================
def test_forecast_code_output_when_interval_passed_with_plan():
    """
    Test that an `interval` passed alongside a pre-built plan replaces the
    plan's interval in the rendered script, so the script predicts the
    requested bounds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        steps=10,
        interval=[0.1, 0.9],
        profile=profile,
        plan=plan,
    )

    assert result.plan.interval == [0.1, 0.9]
    assert "predict_interval" in result.code


def test_forecast_code_ValueError_when_window_features_differ_from_plan():
    """
    Test that forecast_code() rejects a `window_features` override that
    differs from the window features of the pre-built plan, naming the
    argument, because the planning stage that consumes it is skipped.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(ValueError, match=re.escape("['window_features']")):
        assistant.forecast_code(
            data=df_single,
            target="sales",
            date_column="date",
            steps=10,
            window_features=[{"stats": ["mean"], "window_size": 3}],
            profile=profile,
            plan=plan,
        )


def test_forecast_code_ValueError_when_estimator_differs_from_plan():
    """
    Test that forecast_code() rejects an `estimator` override that differs
    from the estimator of the pre-built plan, and that the message points
    to `refine_plan()`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, estimator="Ridge")

    with pytest.raises(ValueError, match=re.escape("refine_plan()")):
        assistant.forecast_code(
            data=df_single,
            target="sales",
            steps=10,
            estimator="LGBMRegressor",
            profile=profile,
            plan=plan,
        )


def test_forecast_code_ValueError_when_data_conflicts_with_profile():
    """
    Test that forecast_code() checks supplied data against the supplied
    profile, so a dataset lacking the profile's target is reported before
    any script is rendered.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    with pytest.raises(ValueError, match=re.escape("column(s) ['sales']")):
        assistant.forecast_code(
            data=df_single.drop(columns=["sales"]), profile=profile, plan=plan
        )


def test_forecast_code_ValueError_when_steps_conflicts_with_plan():
    """
    Test that forecast_code() rejects a `steps` different from
    `plan.steps`, like forecast() does.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=7)

    with pytest.raises(ValueError, match="does not match `plan.steps`"):
        assistant.forecast_code(steps=3, profile=profile, plan=plan)


def test_forecast_code_ValueError_when_neither_steps_nor_plan():
    """
    Test that forecast_code() without `steps` and without a plan raises a
    clear ValueError.
    """
    assistant = ForecastingAssistant()

    with pytest.raises(ValueError, match="`steps` is required"):
        assistant.forecast_code(data=df_single, target="sales", date_column="date")
