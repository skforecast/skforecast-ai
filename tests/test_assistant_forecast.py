# Unit test forecast ForecastingAssistant

import contextlib
import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant, ForecastResult
from skforecast_ai.exceptions import (
    ForecastExecutionError,
    InvalidInputError,
    InvalidInputTypeError,
)
from skforecast_ai import _validation as validation_module
from skforecast_ai._constants import ALLOWED_METRICS

from tests.fixtures_datasets import (
    df_h2o,
    df_h2o_text,
    df_items_sales_long,
    df_items_sales_wide,
)
from tests.fixtures_assistant import (
    df_calendar_named_exog,
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
        test_size=10,
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
        test_size=steps,
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
        test_size=5,
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
        test_size=5,
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


def test_forecast_output_when_exog_columns_named_like_calendar_features():
    """
    Test that forecast() runs when exogenous columns are named like the raw
    calendar features of a tree-based plan ('month', 'weekend'), which made
    skforecast fail with duplicated feature names before those calendar
    features were skipped.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast(
        data        = df_calendar_named_exog,
        target      = "sales",
        date_column = "date",
        steps       = 5,
        test_size   = 5,
        estimator   = "LGBMRegressor",
    )

    assert isinstance(result, ForecastResult)
    assert result.plan.forecaster_kwargs["calendar_features"] == {
        "features": ["day_of_week"], "encoding": None
    }
    assert len(result.predictions) == 5
    assert list(result.metrics["series"]) == ["sales"]


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
        test_size=5,
    )

    assert np.isfinite(result.metrics["MAE"].iloc[0])
    assert np.isfinite(result.metrics["MSE"].iloc[0])
    assert result.metrics["MAE"].iloc[0] > 0
    assert result.metrics["MSE"].iloc[0] > 0


# =============================================================================
# Tests: plan overrides
# =============================================================================
def test_forecast_output_when_interval_passed_with_plan_without_intervals():
    """
    Test that an `interval` passed alongside a pre-built plan that has no
    intervals is applied: the interval is a prediction-time option, so the
    executed plan carries it and the predictions include the bounds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    assert plan.interval is None

    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        interval=[0.1, 0.9],
        test_size=5,
        profile=profile,
        plan=plan,
    )

    assert result.plan.interval == [0.1, 0.9]
    assert result.plan.interval_method == "bootstrapping"
    assert result.plan.explanation.endswith("Prediction intervals via bootstrapping.")
    assert {"lower_bound", "upper_bound"} <= set(result.predictions.columns)
    assert plan.interval is None


def test_forecast_no_warning_when_interval_matches_plan():
    """
    Test that an `interval` equal to the one the pre-built plan already
    holds is accepted silently and the plan is used unchanged.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, interval=[0.1, 0.9])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
            interval=[0.1, 0.9],
            test_size=5,
            profile=profile,
            plan=plan,
        )

    assert result.plan.interval == [0.1, 0.9]
    assert result.plan.explanation == plan.explanation


def test_forecast_ValueError_when_lags_differ_from_plan():
    """
    Test that forecast() rejects a `lags` override that differs from the
    lags of the pre-built plan, since the planning stage that would apply
    it is skipped and the value would otherwise be dropped silently.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    with pytest.raises(ValueError, match=re.escape("['lags']")):
        assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
            lags=[1, 2],
            test_size=5,
            profile=profile,
            plan=plan,
        )


def test_forecast_output_when_lags_match_plan():
    """
    Test that a `lags` override equal to the lags of the pre-built plan is
    accepted, also when given as the integer form of the same lag list.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, lags=3)

    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        lags=[1, 2, 3],
        test_size=5,
        profile=profile,
        plan=plan,
    )

    assert result.plan.forecaster_kwargs["lags"] == 3


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
            test_size=5,
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
        test_size=5,
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


def test_forecast_InvalidInputError_when_future_exog_has_gap():
    """
    Test that forecast() with future `exog` missing a date to forecast
    raises before running, naming the date, instead of forecasting with a
    missing value without an error.
    """
    future_dates = pd.date_range("2023-04-11", periods=6, freq="D").delete(2)
    exog = pd.DataFrame({"promo": [0.0, 1.0, 0.0, 1.0, 0.0]}, index=future_dates)

    err_msg = re.escape(
        "`exog` has no row for 1 of the 5 dates to forecast, such as 2023-04-13. "
        "It must hold the dates from 2023-04-11 to 2023-04-15 at frequency 'D'."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=df_single, target="sales", date_column="date", steps=5, exog=exog
        )

    assert exc_info.value.field == "exog"


def test_forecast_InvalidInputTypeError_when_exog_is_path():
    """
    Test that forecast() with `exog` given as a path raises a type error
    that says what it expects, instead of a message about the number of
    rows (the length of the str).
    """
    err_msg = re.escape(
        "`exog` must be a pandas DataFrame with the future values of the "
        "exogenous variables, not str."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg):
        ForecastingAssistant().forecast(
            data=df_single, target="sales", date_column="date", steps=5,
            exog="future_exog.csv",
        )


def test_forecast_output_when_exog_is_named_series():
    """
    Test that forecast() with future `exog` given as a named pandas Series
    forecasts with that variable (it failed inside the script before).
    """
    future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
    promo = pd.Series([0.0, 1.0, 0.0, 1.0, 0.0], index=future_dates, name="promo")

    result = ForecastingAssistant().forecast(
        data=df_single, target="sales", date_column="date", steps=5, exog=promo
    )

    expected = pd.DataFrame(
        {
            "pred": [
                99.92181716998854, 100.88007278086671, 101.84884665578019,
                102.81652287031471, 103.77227256755344,
            ]
        },
        index=future_dates,
    )
    pd.testing.assert_frame_equal(result.predictions, expected)


def test_forecast_UserWarning_when_future_exog_missing_value_and_lightgbm():
    """
    Test that forecast() with a missing value in the future `exog` and
    LightGBM, which tolerates it, warns and forecasts as before.
    """
    future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
    exog = pd.DataFrame({"promo": [0.0, np.nan, 0.0, 1.0, 0.0]}, index=future_dates)

    warn_msg = re.escape(
        "`exog` has missing values in the rows to forecast ('promo': 1 value(s), "
        "such as '2023-04-12')."
    )
    # skforecast warns too, from the executed script.
    with pytest.warns(
        MissingValuesWarning, match=re.escape("`exog` has missing values.")
    ):
        with pytest.warns(UserWarning, match=warn_msg) as record:
            result = ForecastingAssistant().forecast(
                data=df_single, target="sales", date_column="date", steps=5,
                exog=exog, estimator="LGBMRegressor",
            )

    assert result.predictions["pred"].notna().all()
    # The warning points at the call of the user.
    filenames = [
        warning.filename for warning in record
        if "rows to forecast" in str(warning.message)
    ]
    assert filenames == [__file__]


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
            test_size=5,
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
    split_date = str(df_single["date"].iloc[-6].date())
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


def test_forecast_output_when_profile_given_without_target():
    """
    Test that a supplied profile makes `target` and `date_column`
    optional: they are taken from the profile, which is what the executed
    script is rendered from anyway.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    result = assistant.forecast(
        data=df_single, steps=5, test_size=5, profile=profile, plan=plan
    )

    assert result.profile is profile
    assert len(result.predictions) == 5


def test_forecast_ValueError_when_target_conflicts_with_profile():
    """
    Test that a target different from the one recorded in the supplied
    profile raises ValueError. Previously it was ignored and the script
    used the profile's target regardless.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(ValueError, match="does not match the target recorded"):
        assistant.forecast(
            data=df_single, target="temperature", steps=5, test_size=5,
            profile=profile,
        )


def test_forecast_output_when_plan_given_without_steps():
    """
    Test that a supplied plan makes `steps` optional: the horizon is
    taken from the plan, which is what the executed script uses anyway.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=7)

    result = assistant.forecast(
        data=df_single, test_size=7, profile=profile, plan=plan
    )

    assert len(result.predictions) == 7


def test_forecast_ValueError_when_steps_conflicts_with_plan():
    """
    Test that a `steps` different from `plan.steps` raises ValueError,
    mirroring the `cv.steps` check of backtest(). Previously the argument
    was ignored and the script predicted `plan.steps` regardless.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=7)

    with pytest.raises(ValueError, match=re.escape("`steps` (3) does not match `plan.steps` (7)")):
        assistant.forecast(
            data=df_single, steps=3, test_size=7, profile=profile, plan=plan
        )


def test_forecast_ValueError_when_neither_steps_nor_plan():
    """
    Test that omitting `steps` without a plan raises a clear ValueError
    instead of failing inside plan validation.
    """
    assistant = ForecastingAssistant()

    with pytest.raises(ValueError, match="`steps` is required when `plan` is not provided"):
        assistant.forecast(data=df_single, target="sales", date_column="date")


def test_forecast_output_when_baseline_plan():
    """
    Test that forecast() runs a ForecasterEquivalentDate plan: on a linear
    series, the seasonal naive baseline (offset 7) repeats the value seven
    days earlier, so every prediction is off by exactly 7.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterEquivalentDate")

    result = assistant.forecast(
        data=df_single, profile=profile, plan=plan, test_size=5
    )

    expected_predictions = pd.DataFrame(
        {"pred": [88.0, 89.0, 90.0, 91.0, 92.0]},
        index=pd.date_range("2023-04-06", periods=5, freq="D"),
    )
    expected_metrics = pd.DataFrame(
        {"series": ["sales"], "MAE": [7.0], "MSE": [49.0], "MASE": [7.0]}
    )
    pd.testing.assert_frame_equal(
        result.predictions, expected_predictions, check_names=False, check_freq=False
    )
    pd.testing.assert_frame_equal(result.metrics, expected_metrics)
    assert "ForecasterEquivalentDate(" in result.code
    assert "promo" not in result.code


def test_forecast_output_when_baseline_prediction_mode_with_exog_in_data():
    """
    Test that forecast() in prediction mode needs no future `exog` for the
    baseline, even when the data has exogenous columns, because the
    baseline only repeats past target values.
    """
    assistant = ForecastingAssistant()

    result = assistant.forecast(
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
        forecaster="ForecasterEquivalentDate",
    )

    expected_predictions = pd.DataFrame(
        {"pred": [93.0, 94.0, 95.0, 96.0, 97.0]},
        index=pd.date_range("2023-04-11", periods=5, freq="D"),
    )
    pd.testing.assert_frame_equal(
        result.predictions, expected_predictions, check_names=False, check_freq=False
    )
    assert result.metrics is None
    assert "exog" not in result.code


def test_forecast_ValueError_when_baseline_given_future_exog():
    """
    Test that forecast() rejects a future `exog` for the baseline instead of
    silently ignoring it.
    """
    assistant = ForecastingAssistant()
    future_exog = pd.DataFrame(
        {"promo": [0.0, 1.0, 0.0, 1.0, 0.0]},
        index=pd.date_range("2023-04-11", periods=5, freq="D"),
    )

    err_msg = re.escape(
        "`exog` was provided but the plan does not use exogenous variables "
        "(`plan.use_exog` is False). Remove `exog`."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.forecast(
            data=df_single,
            target="sales",
            date_column="date",
            steps=5,
            forecaster="ForecasterEquivalentDate",
            exog=future_exog,
        )



def test_forecast_output_when_data_has_missing_timestamps():
    """
    Test that forecast() works on a series with missing timestamps: the
    frequency is inferred despite the gaps, the script restores them with
    `asfreq()`, and a Ridge plan drops the resulting NaN rows instead of
    failing on them.
    """
    assistant = ForecastingAssistant()
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    data = pd.DataFrame(
        {"date": dates, "sales": np.arange(100, dtype=float)}
    ).drop(index=[40, 41, 70]).reset_index(drop=True)

    # skforecast reports the rows it drops (from `y_train` and `X_train`)
    # because of the restored gaps.
    with pytest.warns(MissingValuesWarning, match="NaNs detected in"):
        result = assistant.forecast(
            data        = data,
            target      = "sales",
            date_column = "date",
            steps       = 5,
            estimator   = "Ridge",
        )

    assert result.profile.data_profile.frequency == "D"
    assert result.profile.data_profile.has_gaps is True
    assert result.plan.forecaster_kwargs["dropna_from_series"] is True
    assert "data = data.asfreq('D')" in result.code
    pd.testing.assert_index_equal(
        result.predictions.index,
        pd.date_range("2023-04-11", periods=5, freq="D"),
        check_names=False,
    )
    assert not result.predictions["pred"].isna().any()


@pytest.mark.parametrize(
    "test_size, n_test",
    [(10, 10), (3, 3)],
    ids=["test set longer than steps", "test set shorter than steps"],
)
def test_forecast_ValueError_when_test_size_differs_from_steps(test_size, n_test):
    """
    Test that forecast() in evaluation mode raises when the test set does
    not hold exactly `steps` observations: a longer one would be scored on
    its first `steps` rows only, and a shorter one cannot hold the forecast.
    """
    assistant = ForecastingAssistant()

    err_msg = re.escape(
        f"The test set has {n_test} observations but `steps` is 5. forecast() "
        f"evaluates one forecast of `steps` observations, so the test set "
        f"must have the same length: pass test_size=5. To evaluate over a "
        f"longer period, use backtest() (create_cv() builds the folds)."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.forecast(
            data        = df_single,
            target      = "sales",
            date_column = "date",
            steps       = 5,
            test_size   = test_size,
        )


def test_forecast_ValueError_when_plan_end_train_leaves_other_test_length():
    """
    Test that a pre-built plan carrying `end_train` (evaluation mode
    without `test_size`) is checked the same way against `steps`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5).model_copy(
        update={"end_train": str(df_single["date"].iloc[-21].date())}
    )

    err_msg = re.escape("The test set has 20 observations but `steps` is 5.")
    with pytest.raises(ValueError, match=err_msg):
        assistant.forecast(data=df_single, profile=profile, plan=plan)


def test_forecast_output_when_every_supported_metric_requested():
    """
    Test that forecast() computes every supported regression metric in
    evaluation mode, the same set backtesting accepts, instead of leaving
    out the ones it did not know.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5).model_copy(
        update={"metrics_to_compute": list(ALLOWED_METRICS)}
    )

    result = assistant.forecast(
        data=df_single, profile=profile, plan=plan, test_size=5
    )

    assert list(result.metrics.columns) == [
        "series", "MSE", "MAE", "MAPE", "MSLE", "MASE", "RMSSE", "MedAE", "SMAPE"
    ]
    assert np.isfinite(result.metrics.drop(columns="series").to_numpy()).all()


def test_forecast_ValueError_when_estimator_package_not_installed(monkeypatch):
    """
    Test that forecast() raises with the install command, before running
    the script, when the package of the estimator is not installed.
    """
    monkeypatch.setattr(
        validation_module.importlib.util, "find_spec", lambda name: None
    )
    assistant = ForecastingAssistant()

    err_msg = re.escape(
        "LGBMRegressor needs the 'lightgbm' package, which is not installed "
        "(pip install lightgbm)."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.forecast(
            data        = df_no_exog,
            target      = "sales",
            date_column = "date",
            steps       = 5,
            estimator   = "LGBMRegressor",
        )


def test_forecast_output_when_received_plan_holds_values_validation_converts():
    """
    Test that a received plan holding values the validators convert (an
    interval given as strings, set with `model_copy`) runs with the
    validated values, not the original ones.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(
        profile=profile, steps=5, estimator="Ridge", interval=[0.1, 0.9]
    ).model_copy(update={"interval": ["0.1", "0.9"]})

    result = assistant.forecast(data=df_no_exog, profile=profile, plan=plan, test_size=5)

    assert result.plan.interval == [0.1, 0.9]
    assert "    interval = [0.1, 0.9]," in result.code.splitlines()
    assert list(result.predictions.columns) == ["pred", "lower_bound", "upper_bound"]


# =============================================================================
# Tests: error code and field
# =============================================================================
@pytest.mark.parametrize(
    "test_size, error_class, err_msg",
    [
        (
            True, InvalidInputTypeError,
            "`test_size` must be an int, float, str or Timestamp, not bool.",
        ),
        (
            1.5, InvalidInputError,
            "Float `test_size` must be in the open interval (0, 1), got 1.5.",
        ),
        (
            3, InvalidInputError,
            "The test set has 3 observations but `steps` is 7. forecast() "
            "evaluates one forecast of `steps` observations, so the test set "
            "must have the same length: pass test_size=7. To evaluate over a "
            "longer period, use backtest() (create_cv() builds the folds).",
        ),
    ],
    ids=["bool", "float_out_of_range", "length_differs_from_steps"],
)
def test_forecast_error_code_and_field_when_test_size_invalid(
    test_size, error_class, err_msg
):
    """
    Test that an invalid `test_size` raises an error with the code
    'invalid_argument' and `test_size` as field; a bool keeps raising a
    TypeError, now also an InvalidInputError.
    """
    with pytest.raises(error_class, match=re.escape(err_msg)) as exc_info:
        ForecastingAssistant().forecast(
            data        = df_no_exog,
            target      = "sales",
            date_column = "date",
            steps       = 7,
            test_size   = test_size,
        )

    assert isinstance(exc_info.value, InvalidInputError)
    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "test_size"


def test_forecast_ValueError_when_csv_date_column_has_an_empty_cell(tmp_path):
    """
    Test that forecast() on a CSV whose date column has one empty cell raises
    the error of profile() before anything runs. Before, it asked for future
    exogenous values, as the date had become an exogenous variable.
    """
    data = df_h2o_text.copy()
    data.loc[100, "date"] = None
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        ForecastingAssistant().forecast(data=csv_path, target="x", steps=12)


def test_forecast_ValueError_when_profile_given_and_csv_date_has_an_empty_cell(
    tmp_path
):
    """
    Test that forecast() with a profile, on a CSV whose date column (the one
    of the profile) has one empty cell, raises before running the script,
    even when a later column holds complete dates. The dates used to stay
    as text and the script failed ('Input X contains NaN').
    """
    data = df_h2o_text.copy()
    data["period_end"] = (
        pd.to_datetime(data["date"]) + pd.offsets.MonthEnd(0)
    ).dt.strftime("%Y-%m-%d")
    clean_path = tmp_path / "clean.csv"
    data.to_csv(clean_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=clean_path, target="x")
    data.loc[100, "date"] = None
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        assistant.forecast(data=csv_path, profile=profile, steps=12)

    assert profile.data_profile.date_column == "date"


def test_forecast_note_when_long_series_ends_early():
    """
    Test that forecasting long-format data where a series (item_3) ends 30
    days before the others says so in the profile: the forecast covers only
    the series that reach the last date, which happened without any warning.
    """
    data = df_items_sales_long.drop(index=range(330, 360))

    result = ForecastingAssistant().forecast(
        data             = data,
        target           = "value",
        date_column      = "date",
        series_id_column = "series",
        steps            = 7,
    )

    assert result.profile.data_profile.warnings == [
        "Series ending early: 1 series ends before the last date with a value "
        "(2012-04-29): 'item_3' (2012-03-30). ForecasterRecursiveMultiSeries does "
        "not predict them, and ForecasterFoundation predicts each one after its "
        "own last row, rows without a value included."
    ]
    assert sorted(result.predictions["level"].unique()) == ["item_1", "item_2"]


def test_forecast_note_when_wide_series_ends_early():
    """
    Test that forecasting wide data where a series (item_3) has no value on
    the last 2 dates says so in the profile: the forecast covers only the
    series that reach the last date, which happened without any warning.
    """
    data = df_items_sales_wide.copy()
    data.iloc[-2:, 2] = np.nan

    result = ForecastingAssistant().forecast(
        data   = data,
        target = ["item_1", "item_2", "item_3"],
        steps  = 7,
    )

    assert result.profile.data_profile.warnings == [
        "Series ending early: 1 series ends before the last date with a value "
        "(2012-04-29): 'item_3' (2012-04-27). ForecasterRecursiveMultiSeries does "
        "not predict them, and the other forecasters read their last values as "
        "missing values, which not every estimator or foundation model can use."
    ]
    assert sorted(result.predictions["level"].unique()) == ["item_1", "item_2"]


# =============================================================================
# Tests: last window of the target
# =============================================================================
@pytest.mark.parametrize("with_exog", [True, False], ids=["exog", "no_exog"])
@pytest.mark.parametrize("estimator", ["Ridge", "LGBMRegressor"])
def test_forecast_InvalidInputError_when_final_rows_without_target(
    estimator, with_exog
):
    """
    Test that forecast() of data with future rows appended to carry the
    exogenous variables (no target value) raises, whatever the estimator,
    before the future `exog` is checked: it raised that `exog` started before
    the first date to forecast (the day after the appended rows) or, without
    `exog`, that `exog` was required.
    """
    future = pd.DataFrame({
        "date": pd.date_range("2023-04-11", periods=5, freq="D"),
        "sales": np.nan,
        "promo": [0.0, 1.0, 0.0, 1.0, 0.0],
    })
    data = pd.concat([df_single, future], ignore_index=True)
    exog = future[["date", "promo"]].set_index("date")

    err_msg = re.escape(
        "The data has no target value after 2023-04-10: drop its last 5 row(s) "
        "(2023-04-11 to 2023-04-15), so that it ends with the last value of the "
        "target; to forecast their dates, pass their exogenous variables in "
        "`exog`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=data, target="sales", date_column="date", steps=5,
            exog=exog if with_exog else None, estimator=estimator,
        )

    assert exc_info.value.field == "data"


@pytest.mark.parametrize("estimator", ["Ridge", "LGBMRegressor"])
def test_forecast_UserWarning_when_multiseries_final_rows_without_target(estimator):
    """
    Test that forecast() of wide data with future rows appended to every
    series (no target value) warns with ForecasterRecursiveMultiSeries, which
    drops them, and gives the predictions of the data without them.
    """
    future = pd.DataFrame(
        np.nan,
        index   = pd.date_range("2012-04-30", periods=3, freq="D"),
        columns = df_items_sales_wide.columns,
    )
    data = pd.concat([df_items_sales_wide, future])
    target = list(df_items_sales_wide.columns)
    assistant = ForecastingAssistant()

    warn_msg = re.escape(
        "The data has no target value after 2012-04-29: "
        "ForecasterRecursiveMultiSeries ignores its last 3 row(s) (2012-04-30 to "
        "2012-05-02) and forecasts the dates after 2012-04-29. Drop those rows to "
        "avoid this warning."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        result = assistant.forecast(
            data=data, target=target, steps=7, estimator=estimator
        )
    expected = assistant.forecast(
        data=df_items_sales_wide, target=target, steps=7, estimator=estimator
    )

    pd.testing.assert_frame_equal(result.predictions, expected.predictions)


def test_forecast_InvalidInputError_when_last_window_missing_value_and_ridge():
    """
    Test that forecast() with Ridge and a missing value of h2o that lag 13
    reads (2007-06-01) raises before running: the three predictions were
    missing without an error.
    """
    data = df_h2o.copy()
    data.iloc[-13, 0] = np.nan

    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('x': 1 "
        "value(s), such as '2007-06-01'). ForecasterRecursive with Ridge cannot "
        "use them, so its predictions would be missing: fill them in."
    )
    with pytest.warns(MissingValuesWarning):
        with pytest.raises(InvalidInputError, match=err_msg):
            ForecastingAssistant().forecast(
                data=data, target="x", steps=3, estimator="Ridge"
            )


def test_forecast_UserWarning_when_last_window_missing_value_and_lightgbm():
    """
    Test that forecast() with LightGBM, which tolerates missing values, and a
    missing value of h2o that lag 13 reads warns, naming it, and forecasts as
    before.
    """
    data = df_h2o.copy()
    data.iloc[-13, 0] = np.nan

    warn_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('x': 1 "
        "value(s), such as '2007-06-01'). LGBMRegressor treats them as missing "
        "values; check that they are meant to be missing."
    )
    # skforecast warns too, when profiling and from the executed script.
    with pytest.warns(MissingValuesWarning):
        with pytest.warns(UserWarning, match=warn_msg) as record:
            result = ForecastingAssistant().forecast(
                data=data, target="x", steps=3, estimator="LGBMRegressor"
            )

    expected = pd.DataFrame(
        {"pred": [0.9933306508753204, 0.9629531895209908, 1.0539713022220016]},
        index=pd.date_range("2008-07-01", periods=3, freq="MS"),
    )
    pd.testing.assert_frame_equal(result.predictions, expected)
    # The warning points at the call of the user.
    filenames = [
        warning.filename for warning in record
        if "reads missing values of the target" in str(warning.message)
    ]
    assert filenames == [__file__]


def test_forecast_output_when_evaluation_mode_and_last_window_missing_value():
    """
    Test that in evaluation mode the last window of the training split is
    checked as in prediction mode: a missing value that a lag reads gives
    LightGBM predictions with the warning of the estimators that tolerate
    missing values.
    """
    data = df_h2o.copy()
    data.iloc[-16, 0] = np.nan

    # skforecast warns about the missing value, when profiling and fitting.
    with (
        pytest.warns(UserWarning, match="reads missing values of the target") as record,
        pytest.warns(MissingValuesWarning),
    ):
        result = ForecastingAssistant().forecast(
            data=data, target="x", steps=3, test_size=3, estimator="LGBMRegressor"
        )

    messages = [
        str(warning.message) for warning in record
        if "reads missing values of the target" in str(warning.message)
    ]
    assert messages == [
        "The forecaster reads missing values of the target to predict ('x': 1 "
        "value(s), such as '2007-03-01'). LGBMRegressor treats them as missing "
        "values; check that they are meant to be missing."
    ]
    assert result.predictions["pred"].notna().all()


_H2O_LAST_TRAINING_READ = (
    "The forecaster reads missing values of the target to predict ('x': 1 "
    "value(s), such as '2007-06-01'). "
)
_H2O_LGBM_PREDICTIONS = [
    0.8277571065635025, 1.0205027382164744, 1.007466843600445,
    1.1209519874787484, 1.1665125040119138, 1.1516798899801441,
    1.1961369585574637, 0.6235227873454375, 0.7302412908869749,
    0.5799352257692894, 0.7430074572161064, 0.6159413043579267,
]
_H2O_RIDGE_FAR_PREDICTIONS = [
    0.86013224120506, 1.040723948807036, 0.9888977187331605,
    1.1745827805058775, 1.0877071723097516, 1.1184101903448553,
    1.2218821412132566, 0.6620868331391002, 0.7107535611148452,
    0.5971145894051624, 0.7564693445789693, 0.8592354552041727,
]


def test_forecast_InvalidInputError_when_evaluation_training_ends_with_missing_and_ridge():
    """
    Test that forecast() in evaluation mode with Ridge raises before running
    when the last training date of h2o (position -13 for `test_size` 12) or a
    date that a lag reads (-14) has no value: the predictions would be
    missing.
    """
    for position, date in [(-13, "2007-06-01"), (-14, "2007-05-01")]:
        data = df_h2o.copy()
        data.iloc[position, 0] = np.nan

        err_msg = re.escape(
            "The forecaster reads missing values of the target to predict ('x': "
            f"1 value(s), such as '{date}'). ForecasterRecursive with Ridge "
            "cannot use them, so its predictions would be missing: fill them in."
        )
        with pytest.warns(MissingValuesWarning):
            with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
                ForecastingAssistant().forecast(
                    data=data, target="x", steps=12, test_size=12, estimator="Ridge"
                )

        assert exc_info.value.field == "data"
        assert exc_info.value.code == "invalid_argument"


def test_forecast_UserWarning_when_evaluation_training_ends_with_missing_and_lightgbm():
    """
    Test that forecast() in evaluation mode with LightGBM warns, naming the
    missing value of the last training date, and gives the predictions of the
    run without the check.
    """
    data = df_h2o.copy()
    data.iloc[-13, 0] = np.nan

    warn_msg = re.escape(
        _H2O_LAST_TRAINING_READ
        + "LGBMRegressor treats them as missing values; check that they are "
        "meant to be missing."
    )
    # skforecast warns too, when profiling and from the executed script.
    with pytest.warns(MissingValuesWarning):
        with pytest.warns(UserWarning, match=warn_msg):
            result = ForecastingAssistant().forecast(
                data=data, target="x", steps=12, test_size=12,
                estimator="LGBMRegressor",
            )

    expected = pd.DataFrame(
        {"pred": _H2O_LGBM_PREDICTIONS},
        index=pd.date_range("2007-07-01", periods=12, freq="MS"),
    )
    pd.testing.assert_frame_equal(result.predictions, expected)


def test_forecast_output_when_evaluation_missing_value_not_read_by_lags():
    """
    Test that a missing value far in the past (position -100 of h2o, that no
    lag reads) gives no "reads missing values" error or warning in evaluation
    mode, and the predictions of the run without the check.
    """
    data = df_h2o.copy()
    data.iloc[-100, 0] = np.nan

    # Only skforecast warns, when profiling and training.
    with pytest.warns(MissingValuesWarning) as record:
        result = ForecastingAssistant().forecast(
            data=data, target="x", steps=12, test_size=12, estimator="Ridge"
        )

    assert not [
        warning for warning in record
        if "reads missing values of the target" in str(warning.message)
    ]
    expected = pd.DataFrame(
        {"pred": _H2O_RIDGE_FAR_PREDICTIONS},
        index=pd.date_range("2007-07-01", periods=12, freq="MS"),
    )
    pd.testing.assert_frame_equal(result.predictions, expected)


def _items_frame(data_format: str, series: str, date: str) -> pd.DataFrame:
    """Return the items_sales data with the target of `series` missing on `date`."""
    if data_format == "wide":
        data = df_items_sales_wide.copy()
        data.loc[date, series] = np.nan
    else:
        data = df_items_sales_long.copy()
        data.loc[
            (data["series"] == series) & (data["date"] == date), "value"
        ] = np.nan

    return data


def _items_kwargs(data_format: str) -> dict:
    """Return the arguments of forecast() for the items_sales data."""
    if data_format == "wide":
        return {"target": list(df_items_sales_wide.columns)}

    return {
        "target": "value", "date_column": "date", "series_id_column": "series"
    }


@pytest.mark.parametrize("data_format", ["wide", "long"])
def test_forecast_InvalidInputError_when_evaluation_series_has_no_last_training_value(
    data_format
):
    """
    Test that forecast() in evaluation mode with ForecasterRecursiveMultiSeries
    raises, with the field `test_size`, when a series has no value on the last
    training date (2012-04-22), and names every series when none has one.
    """
    kwargs = _items_kwargs(data_format)
    end_message = (
        "ForecasterRecursiveMultiSeries does not predict a series that ends "
        "before the others, and when no series has a value there it starts the "
        "forecast earlier, so the metrics would compare other dates. Choose "
        "another `test_size`, or fill in those values."
    )

    err_msg = re.escape(
        "Some series have no value on the last training date (2012-04-22): "
        f"'item_1'. {end_message}"
    )
    with pytest.warns(MissingValuesWarning):
        with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
            ForecastingAssistant().forecast(
                data=_items_frame(data_format, "item_1", "2012-04-22"),
                steps=7, test_size=7, **kwargs,
            )
    assert exc_info.value.field == "test_size"

    data = df_items_sales_wide.copy()
    data.loc["2012-04-22"] = np.nan
    if data_format == "long":
        data = df_items_sales_long[df_items_sales_long["date"] != "2012-04-22"]
    err_msg = re.escape(
        "Some series have no value on the last training date (2012-04-22): "
        f"'item_1', 'item_2', 'item_3'. {end_message}"
    )
    # skforecast warns about the missing values of the wide data only: the
    # long data has absent rows.
    expected_warning = (
        pytest.warns(MissingValuesWarning)
        if data_format == "wide" else contextlib.nullcontext()
    )
    with expected_warning:
        with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
            ForecastingAssistant().forecast(
                data=data, steps=7, test_size=7, **kwargs
            )
    assert exc_info.value.field == "test_size"


@pytest.mark.parametrize("data_format", ["wide", "long"])
def test_forecast_InvalidInputError_when_evaluation_series_has_missing_test_value(
    data_format
):
    """
    Test that forecast() in evaluation mode with ForecasterRecursiveMultiSeries
    raises, with the field `data`, when one series has a missing value in the
    test split.
    """
    err_msg = re.escape(
        "The target has missing values in the test split ('item_2': 1 value(s), "
        "such as '2012-04-25'). skforecast cannot compute the metrics on them, "
        "whatever the estimator. Impute the target, or evaluate on dates "
        "without missing values."
    )
    with pytest.warns(MissingValuesWarning):
        with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
            ForecastingAssistant().forecast(
                data=_items_frame(data_format, "item_2", "2012-04-25"),
                steps=7, test_size=7, **_items_kwargs(data_format),
            )

    assert exc_info.value.field == "data"


def test_forecast_InvalidInputError_when_evaluation_series_without_values_up_to_end_train():
    """
    Test that a series without any value up to the end of training keeps the
    message of `validate_series_lengths`, not the one of the last training
    date.
    """
    data = df_items_sales_wide.copy()
    data.loc[:"2012-04-22", "item_3"] = np.nan

    err_msg = re.escape(
        "Some series have no values up to the end of training (2012-04-22) "
        "('item_3'), so ForecasterRecursiveMultiSeries cannot be trained on "
        "them. Remove them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=data, target=list(data.columns), steps=7, test_size=7
        )

    assert exc_info.value.code == "insufficient_data"


@pytest.mark.parametrize("tz", ["UTC", "Europe/Madrid"])
def test_forecast_evaluation_mode_with_time_zone(tz):
    """
    Test that forecast() in evaluation mode runs on a tz-aware index, and that
    a missing value in the test split of a single series raises the message of
    the evaluated target (it raised `TypeError: Invalid comparison`).
    """
    data = df_h2o.copy()
    data.index = data.index.tz_localize(tz)

    result = ForecastingAssistant().forecast(
        data=data, target="x", steps=12, test_size=12, estimator="Ridge"
    )
    assert result.predictions.index[0] == pd.Timestamp("2007-07-01", tz=tz)
    assert result.predictions.index.tz is not None
    np.testing.assert_array_almost_equal(
        result.predictions["pred"].to_numpy()[:3],
        np.array([0.8514855921715546, 1.048000010028995, 0.9981468545403993]),
    )

    data.iloc[-5, 0] = np.nan
    offset = "+00:00" if tz == "UTC" else "+01:00"
    err_msg = re.escape(
        "The target has 1 missing value(s) in the test split "
        f"(2008-02-01 00:00:00{offset}), counting the missing timestamps that "
        "asfreq() restores. skforecast cannot compute the metrics on them, "
        "whatever the estimator. Impute the target, or evaluate on dates "
        "without missing values."
    )
    with pytest.warns(MissingValuesWarning):
        with pytest.raises(InvalidInputError, match=err_msg):
            ForecastingAssistant().forecast(
                data=data, target="x", steps=12, test_size=12, estimator="Ridge"
            )


def test_forecast_InvalidInputError_when_evaluation_time_zone_and_last_training_missing():
    """
    Test that the training partition of a tz-aware index is checked too: the
    missing value of the last training date is reported with Ridge.
    """
    data = df_h2o.copy()
    data.index = data.index.tz_localize("Europe/Madrid")
    data.iloc[-13, 0] = np.nan

    err_msg = re.escape(_H2O_LAST_TRAINING_READ + "ForecasterRecursive with Ridge")
    with pytest.warns(MissingValuesWarning):
        with pytest.raises(InvalidInputError, match=err_msg):
            ForecastingAssistant().forecast(
                data=data, target="x", steps=12, test_size=12, estimator="Ridge"
            )


def test_forecast_evaluation_mode_when_last_training_date_absent():
    """
    Test that forecast() in evaluation mode treats a last training date
    missing from the data (h2o without 2007-06-01, a gap and not a NaN) as a
    missing value read by the lags: Ridge raises before running and
    LGBMRegressor warns and forecasts.
    """
    data = df_h2o.drop(index=pd.Timestamp("2007-06-01"))

    err_msg = re.escape(
        _H2O_LAST_TRAINING_READ + "ForecasterRecursive with Ridge cannot use "
        "them, so its predictions would be missing: fill them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=data, target="x", steps=12, test_size=12, estimator="Ridge",
            lags=3,
        )
    assert exc_info.value.field == "data"

    warn_msg = re.escape(
        _H2O_LAST_TRAINING_READ
        + "LGBMRegressor treats them as missing values; check that they are "
        "meant to be missing."
    )
    with pytest.warns(MissingValuesWarning):
        with pytest.warns(UserWarning, match=warn_msg):
            result = ForecastingAssistant().forecast(
                data=data, target="x", steps=12, test_size=12,
                estimator="LGBMRegressor", lags=3,
            )

    np.testing.assert_array_almost_equal(
        result.predictions["pred"].to_numpy()[:3],
        np.array([0.7442731932499239, 0.8548371869682814, 0.9667814209167767]),
    )


def test_forecast_evaluation_mode_with_direct_multivariate_checks_the_level():
    """
    Test that forecast() in evaluation mode with ForecasterDirectMultiVariate
    checks the test split of its level (the first target column, 'item_1'):
    a missing value there raises the message of the evaluated target, and one
    of another series does not.
    """
    target = list(df_items_sales_wide.columns)

    data = df_items_sales_wide.copy()
    data.loc["2012-04-25", "item_1"] = np.nan
    err_msg = re.escape(
        "The target has 1 missing value(s) in the test split "
        "(2012-04-25 00:00:00), counting the missing timestamps that asfreq() "
        "restores. skforecast cannot compute the metrics on them, whatever the "
        "estimator. Impute the target, or evaluate on dates without missing "
        "values."
    )
    with pytest.warns(MissingValuesWarning):
        with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
            ForecastingAssistant().forecast(
                data=data, target=target, steps=7, test_size=7,
                forecaster="ForecasterDirectMultiVariate",
            )
    assert exc_info.value.field == "data"

    data = df_items_sales_wide.copy()
    data.loc["2012-04-25", "item_2"] = np.nan
    with pytest.warns(MissingValuesWarning):
        result = ForecastingAssistant().forecast(
            data=data, target=target, steps=7, test_size=7,
            forecaster="ForecasterDirectMultiVariate",
        )
    np.testing.assert_array_almost_equal(
        result.predictions["pred"].to_numpy()[:3],
        np.array([19.11669360058141, 19.389706633268087, 23.034484246415076]),
    )


@pytest.mark.parametrize("tz", [None, "Europe/Madrid"])
def test_forecast_evaluation_mode_when_hourly_data_and_test_size_int(tz):
    """
    Test that forecast() in evaluation mode on hourly data (naive and tz-aware)
    ends the training at the midnight written with its time, so the three test
    predictions are at 01:00, 02:00 and 03:00 (a date-only `end_train` trained
    on the whole day), and that the tz-aware data does not raise TypeError.
    """
    index = pd.date_range("2023-06-01 03:00", periods=25, freq="h", tz=tz)
    data = pd.DataFrame(
        {"y": np.arange(25, dtype=float) + np.sin(np.arange(25))}, index=index
    )

    result = ForecastingAssistant().forecast(
        data=data, target="y", steps=3, test_size=3, estimator="Ridge"
    )

    offset = "" if tz is None else "+02:00"
    assert result.plan.end_train == f"2023-06-02 00:00:00{offset}"
    expected_index = pd.date_range("2023-06-02 01:00", periods=3, freq="h", tz=tz)
    pd.testing.assert_index_equal(
        result.predictions.index, expected_index, check_names=False
    )


def test_forecast_evaluation_mode_when_monthly_data_keeps_end_train_date_only():
    """
    Test that monthly data keeps a date-only `end_train` ('2007-06-01' for h2o
    with `test_size` 12).
    """
    result = ForecastingAssistant().forecast(
        data=df_h2o, target="x", steps=12, test_size=12, estimator="Ridge"
    )

    assert result.plan.end_train == "2007-06-01"


def test_forecast_InvalidInputError_when_prediction_mode_final_row_without_target():
    """
    Test that prediction mode is unchanged: a final row without target still
    raises the error that asks to drop final rows, not the one of the
    values read.
    """
    data = df_h2o.copy()
    data.iloc[-1, 0] = np.nan

    err_msg = re.escape(
        "The data has no target value after 2008-05-01: drop its last 1 row(s) "
        "(2008-06-01), so that it ends with the last value of the target."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        ForecastingAssistant().forecast(
            data=data, target="x", steps=3, estimator="Ridge"
        )


# =============================================================================
# Tests: early input checks
# =============================================================================
@pytest.mark.parametrize(
    "data, type_name", [([1.0, 2.0, 3.0], "list"), (5, "int")], ids=["list", "int"]
)
def test_forecast_InvalidInputTypeError_when_data_wrong_type(data, type_name):
    """
    Test that forecast() raises InvalidInputTypeError (a TypeError) with the
    field 'data' when it is not a DataFrame, a Series or a path.
    """
    err_msg = re.escape(
        f"`data` must be a pandas DataFrame, a pandas Series, or the path or "
        f"URL of a CSV file, got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(data=data, target="sales", steps=5)

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "data"


@pytest.mark.parametrize("test_size", [None, 5], ids=["prediction", "evaluation"])
def test_forecast_InvalidInputError_when_foundation_backend_not_installed(
    monkeypatch, test_size
):
    """
    Test that forecast() with a ForecasterFoundation plan raises the error
    'missing_dependency' for the field 'estimator', with the install command,
    before running any script, in prediction and in evaluation mode.
    """
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )

    def _not_called(*args, **kwargs):
        raise AssertionError("run_forecast must not be called")

    monkeypatch.setattr("skforecast_ai.assistant.run_forecast", _not_called)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")

    err_msg = re.escape(
        "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
        "which is not installed (pip install \"chronos-forecasting\")."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.forecast(
            data      = df_no_exog,
            profile   = profile,
            plan      = plan,
            test_size = test_size,
        )

    assert exc_info.value.code == "missing_dependency"
    assert exc_info.value.field == "estimator"
    assert exc_info.value.hint == (
        'Install it where skforecast-ai runs: pip install "chronos-forecasting".'
    )


_H2O_WITH_INFINITE = df_h2o.copy()
_H2O_WITH_INFINITE.iloc[50, 0] = np.inf
_INFINITE_TARGET_HINT = (
    "Replace the infinite values of the target, for example with NaN."
)


@pytest.mark.parametrize("test_size", [None, 3], ids=["prediction", "evaluation"])
@pytest.mark.parametrize(
    "forecaster, estimator",
    [("ForecasterRecursive", "Ridge"), ("ForecasterStats", None)],
    ids=["ridge", "stats"],
)
def test_forecast_InvalidInputError_when_target_has_infinite_value(
    forecaster, estimator, test_size
):
    """
    Test that forecast() raises, before running the script, when the target
    has an infinite value and the forecaster is trained on it (h2o, position
    50, 1995-09-01), in prediction and in evaluation mode. The plan is built
    from the data without it, which profiling would warn about.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(
        profile, steps=3, forecaster=forecaster, estimator=estimator
    )
    if test_size is not None:
        plan = plan.model_copy(update={"end_train": "2008-03-01"})

    err_msg = re.escape(
        f"The target has infinite values (1 value(s), such as '1995-09-01'). "
        f"{forecaster} cannot be trained on them: replace them."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.forecast(data=_H2O_WITH_INFINITE, profile=profile, plan=plan)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == _INFINITE_TARGET_HINT


def test_forecast_output_when_baseline_does_not_read_infinite_value():
    """
    Test that forecast() with ForecasterEquivalentDate still forecasts when
    the infinite value (position 50) is not one that its predictions read:
    they are those of the data without it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=3, forecaster="ForecasterEquivalentDate")

    # skforecast warns inside the script when it fits on the infinite value.
    with pytest.warns(RuntimeWarning, match="invalid value encountered in subtract"):
        result = assistant.forecast(
            data=_H2O_WITH_INFINITE, profile=profile, plan=plan
        )

    expected = pd.DataFrame(
        {"pred": [0.954144, 1.07821949, 1.11098161]},
        index=pd.date_range("2008-07-01", periods=3, freq="MS"),
    )
    pd.testing.assert_frame_equal(result.predictions, expected, check_freq=False)


def test_forecast_InvalidInputError_when_baseline_reads_infinite_value():
    """
    Test that forecast() in prediction mode with ForecasterEquivalentDate
    raises when its predictions read the infinite values of the last 12
    observations of h2o (3 steps of a yearly offset read positions 12, 11
    and 10 from the end).
    """
    data = df_h2o.copy()
    data.iloc[-12, 0] = np.inf
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=3, forecaster="ForecasterEquivalentDate")

    err_msg = re.escape(
        "The forecaster reads infinite values of the target to predict (1 "
        "value(s), such as '2007-07-01'). ForecasterEquivalentDate repeats "
        "them as infinite predictions: replace them."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.forecast(data=data, profile=profile, plan=plan)

    assert exc_info.value.field == "data"
    assert exc_info.value.hint == _INFINITE_TARGET_HINT


# =============================================================================
# Tests: the script loads the file that ran
# =============================================================================
def test_forecast_output_script_loads_csv_path_that_ran(tmp_path):
    """
    Test that forecast() with a CSV path returns a script that loads that
    path, and records it in `result.profile`, although it profiles the
    DataFrame read from it.
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()

    result = assistant.forecast(
        data=csv_path, target="sales", date_column="date", steps=5, test_size=5
    )

    assert f"data = pd.read_csv({str(csv_path)!r})" in result.code
    assert "'data.csv'" not in result.code
    assert result.profile.data_profile.data_path == str(csv_path)


def test_forecast_output_script_loads_csv_path_that_ran_when_saved_profile(tmp_path):
    """
    Test that forecast() with a saved profile built from one CSV and data
    read from another path returns a script that loads the path that ran,
    without changing the profile passed.
    """
    old_path = tmp_path / "old.csv"
    new_path = tmp_path / "new.csv"
    df_single.to_csv(old_path, index=False)
    df_single.to_csv(new_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=old_path, target="sales", date_column="date")

    result = assistant.forecast(data=new_path, steps=5, test_size=5, profile=profile)

    assert f"data = pd.read_csv({str(new_path)!r})" in result.code
    assert result.profile.data_profile.data_path == str(new_path)
    assert profile.data_profile.data_path == str(old_path)


def test_forecast_output_script_loads_placeholder_when_data_is_dataframe(tmp_path):
    """
    Test that forecast() with a profile saved from a file and a DataFrame
    writes the placeholder of data passed in memory: the script loaded the
    file of the profile, which may hold other data, and gave other
    predictions without an error. The profile passed is not changed.
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=csv_path, target="sales", date_column="date")

    result = assistant.forecast(data=df_single, steps=5, test_size=5, profile=profile)

    assert result.profile.data_profile.data_path == "data.csv"
    assert profile.data_profile.data_path == str(csv_path)
    assert "data = pd.read_csv('data.csv')" in result.code
    assert str(csv_path) not in result.code


# =============================================================================
# Tests: series that ForecasterRecursiveMultiSeries cannot be trained on
# =============================================================================
_ITEMS = ["item_1", "item_2", "item_3"]
_SERIES_WINDOW = (
    "no more values than the 21 that ForecasterRecursiveMultiSeries reads to "
    "build its predictors"
)


def _wide_starting_late(n_values, column="item_2"):
    """
    Return the items_sales wide data (120 days, ending 2012-04-29) where
    `column` only has its last `n_values` values.
    """
    data = df_items_sales_wide.copy()
    data.iloc[: len(data) - n_values, data.columns.get_loc(column)] = np.nan
    return data


def test_forecast_InvalidInputError_when_series_has_window_values_or_fewer():
    """
    Test that forecast() in prediction mode rejects, before running, a series
    whose values from its first one are no more than the window the default
    plan reads (21 for daily data), with `data` as field. skforecast fails
    on it inside the script.
    """
    err_msg = re.escape(
        f"Some series have, from their first to their last value, {_SERIES_WINDOW} "
        f"('item_2': 21), so it cannot be trained on them. Use shorter lags "
        f"and window features, or remove those series."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=_wide_starting_late(21), target=_ITEMS, steps=5
        )

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Use lags and window features of at most 20 observations, or remove "
        "the short series."
    )


def test_forecast_runs_when_series_has_one_more_value_than_window():
    """
    Test that forecast() in prediction mode runs when the shortest series
    has one more value than the window (22 against 21), the boundary of
    skforecast's `len(y) <= window_size` failure.
    """
    result = ForecastingAssistant().forecast(
        data=_wide_starting_late(22), target=_ITEMS, steps=5
    )

    assert list(result.predictions.columns) == ["level", "pred"]
    assert result.predictions.shape == (15, 2)
    assert list(result.predictions["level"].unique()) == _ITEMS


def test_forecast_InvalidInputError_when_series_short_up_to_end_of_training():
    """
    Test that forecast() in evaluation mode checks the training partition
    (up to the end of training, 2012-04-24): item_2 has 15 values there,
    less than the window of 21, though 20 in the whole data.
    """
    err_msg = re.escape(
        f"Some series have, from their first to their last value up to the end of training "
        f"(2012-04-24), {_SERIES_WINDOW} ('item_2': 15), so it cannot be "
        f"trained on them. Use shorter lags and window features, or remove "
        f"those series."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=_wide_starting_late(20), target=_ITEMS, steps=5, test_size=5
        )

    assert exc_info.value.field == "data"


def test_forecast_InvalidInputError_when_series_has_no_values_up_to_end_of_training():
    """
    Test that forecast() in evaluation mode rejects a series whose only
    values are in the test partition (the last 5 days).
    """
    err_msg = re.escape(
        "Some series have no values up to the end of training (2012-04-24) "
        "('item_2'), so ForecasterRecursiveMultiSeries cannot be trained on "
        "them. Remove them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=_wide_starting_late(5), target=_ITEMS, steps=5, test_size=5
        )

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == "Remove the series without values from the data."


def test_forecast_InvalidInputError_when_long_series_has_no_values():
    """
    Test that forecast() rejects long-format data where a series has every
    value missing.
    """
    data = df_items_sales_long.copy()
    data.loc[data["series"] == "item_2", "value"] = np.nan

    err_msg = re.escape(
        "Some series have no values ('item_2'), so "
        "ForecasterRecursiveMultiSeries cannot be trained on them. Remove "
        "them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=data, target="value", date_column="date",
            series_id_column="series", steps=5,
        )

    assert exc_info.value.field == "data"


def test_forecast_InvalidInputError_when_long_series_shorter_than_window():
    """
    Test that forecast() in prediction mode rejects a long-format series
    with 21 values (from 2012-04-09 to the end), the window of the plan.
    """
    data = df_items_sales_long[
        ~(
            (df_items_sales_long["series"] == "item_2")
            & (df_items_sales_long["date"] < "2012-04-09")
        )
    ]

    err_msg = re.escape(
        f"Some series have, from their first to their last value, {_SERIES_WINDOW} "
        f"('item_2': 21), so it cannot be trained on them. Use shorter lags "
        f"and window features, or remove those series."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data=data, target="value", date_column="date",
            series_id_column="series", steps=5,
        )

    assert exc_info.value.field == "data"


def test_forecast_does_not_check_series_lengths_when_forecaster_is_not_multiseries():
    """
    Test that the series lengths are checked for ForecasterRecursiveMultiSeries
    only: ForecasterDirectMultiVariate with a series of 21 values gets past
    the check and fails in the script with the skforecast warning about the
    missing values it trains on.
    """
    err_msg = re.escape(
        "MissingValuesWarning: NaNs detected in `X_train`."
    )
    with pytest.raises(ForecastExecutionError, match=err_msg):
        ForecastingAssistant().forecast(
            data=_wide_starting_late(21), target=_ITEMS, steps=5,
            forecaster="ForecasterDirectMultiVariate",
        )


# =============================================================================
# Tests: received plan checked against the exogenous columns
# =============================================================================
@pytest.mark.parametrize("method", ["forecast", "forecast_code"])
def test_forecast_InvalidInputError_when_received_plan_clashes_with_exog_names(
    method,
):
    """
    Test that forecast() and forecast_code() check a plan built on clean data
    against the exogenous columns of the profile they receive: a column named
    'lag_1' clashes with the lags of the plan, as plan() would have found.
    """
    assistant = ForecastingAssistant()
    plan = assistant.plan(
        assistant.profile(data=df_single, target="sales", date_column="date"),
        steps=5, lags=[1, 2],
    )
    data = df_single.rename(columns={"promo": "lag_1"})
    profile = assistant.profile(data=data, target="sales", date_column="date")

    err_msg = re.escape(
        "Exogenous column(s) 'lag_1' have the name of a predictor that "
        "ForecasterRecursive creates (a lag or a window feature), so the "
        "script would fail with duplicated feature names. Rename them in the "
        "data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        getattr(assistant, method)(
            data=data, steps=5, test_size=5, profile=profile, plan=plan
        )

    assert exc_info.value.field == "data"
