# Unit test forecast ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant, ForecastResult
from skforecast_ai import _validation as validation_module
from skforecast_ai._constants import ALLOWED_METRICS

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
