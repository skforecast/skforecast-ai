# Unit test forecast ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant, ForecastResult
from skforecast_ai.exceptions import InvalidInputError, InvalidInputTypeError
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
    Test that the last window is not checked in evaluation mode, where the
    forecaster is trained on the training split (left for the checks of the
    evaluation split): a missing value of the training split that a lag
    reads gives LightGBM predictions without the warning.
    """
    data = df_h2o.copy()
    data.iloc[-16, 0] = np.nan

    # skforecast warns about the missing value, when profiling and fitting.
    with pytest.warns(MissingValuesWarning) as record:
        result = ForecastingAssistant().forecast(
            data=data, target="x", steps=3, test_size=3, estimator="LGBMRegressor"
        )

    assert not [
        warning for warning in record
        if "reads missing values of the target" in str(warning.message)
    ]
    assert result.predictions["pred"].notna().all()
