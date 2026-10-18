# Unit test backtest ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import (
    IgnoredArgumentWarning,
    LongTrainingWarning,
    MissingValuesWarning,
)
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import BacktestResult, ForecastingAssistant
from skforecast_ai.exceptions import (
    DataContentError,
    EstimatorNotRecommendedWarning,
    InvalidInputError,
    InvalidInputTypeError,
)

from tests.fixtures_csv_dialect import df_dialect, write_dialect
from tests.fixtures_assistant import (
    df_categorical_exog,
    df_multi_wide,
    df_no_exog,
    df_single,
)
from tests.fixtures_last_window import data_h2o_gaps
from tests.fixtures_datasets import (
    df_h2o,
    df_h2o_daily,
    df_h2o_madrid,
    df_items_sales_long,
)

assistant = ForecastingAssistant()

# Distinctive part of the warning of `create_cv()` for a short first training
# window with intervals (the series of 100 observations leaves few residuals).
INTERVAL_WARNING = re.escape("so the prediction intervals are estimated from")

# Warning of backtest() for a Ridge chosen by the user on the multi-series data.
RIDGE_MULTISERIES_WARNING = re.escape(
    "The estimator of the plan, 'Ridge' (chosen by the user), is not the one "
    "the rules recommend for ForecasterRecursiveMultiSeries on these data: "
    "'LGBMRegressor'."
)


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_backtest_ValueError_when_cv_steps_differs_from_plan_steps():
    """
    Test that backtest() raises ValueError when cv.steps != plan.steps
    and plan is explicitly provided.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    err_msg = re.escape("cv.steps (5) does not match plan.steps (10)")
    with pytest.raises(ValueError, match=err_msg):
        assistant.backtest(
            data=df_single,
            target="sales",
            date_column="date",
            cv=cv,
            profile=profile,
            plan=plan,
        )


# =============================================================================
# Tests: basic output
# =============================================================================
def test_backtest_LongTrainingWarning_when_estimator_fits_exceed_threshold():
    """
    Test that backtest() warns before running when the strategy fits the
    estimator more than 50 times (the skforecast threshold, silenced in the
    generated scripts): a ForecasterDirect refitted in each of 6 folds fits
    10 estimators per training. The backtest still runs.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, forecaster="ForecasterDirect")
    cv = TimeSeriesFold(steps=10, initial_train_size=40, refit=True, verbose=False)

    warn_msg = re.escape(
        "ForecasterDirect will be fit 60 times (6 trainings x 10 estimators). "
        "This can take substantial amounts of time. If not feasible, use a "
        "cross-validation strategy with `refit=False` (train once) or an "
        "integer `refit` (retrain every n folds)."
    )
    with pytest.warns(LongTrainingWarning, match=warn_msg):
        result = assistant.backtest(
            data          = df_single,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
        )

    assert result.cv_config["n_fits"] == 6
    assert "(60 fits in all)" in result.explanation


def test_backtest_output_when_single_series():
    """
    Test that backtest() returns a BacktestResult with correct types,
    finite metrics, non-empty predictions, valid code, explanation with
    results, and accurate cv_config for a single-series dataset.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = assistant.create_cv(profile, plan).cv

    result = assistant.backtest(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    # Type and structure
    assert isinstance(result, BacktestResult)
    assert result.profile is not None
    assert result.plan is not None
    assert isinstance(result.metrics, pd.DataFrame)
    assert isinstance(result.predictions, pd.DataFrame)
    assert isinstance(result.code, str)
    assert isinstance(result.explanation, str)
    assert isinstance(result.cv_config, dict)

    # Metrics are finite
    numeric_cols = result.metrics.select_dtypes(include=[np.number]).columns
    assert len(numeric_cols) > 0
    for col in numeric_cols:
        assert np.all(np.isfinite(result.metrics[col].values))

    # Predictions non-empty
    assert len(result.predictions) > 0

    # Code contains expected content
    assert "backtesting_forecaster" in result.code
    assert "TimeSeriesFold" in result.code
    assert "skforecast" in result.code
    assert "exog_features = ['promo']" in result.code
    assert "data[exog_features]" in result.code

    # Explanation includes results summary
    assert "Results" in result.explanation

    # cv_config matches cv object
    assert result.cv_config["steps"] == 5
    assert result.cv_config["initial_train_size"] == cv.initial_train_size
    assert result.cv_config["refit"] == cv.refit

    # The fold count is resolved here so consumers, including the LLM, never
    # have to re-derive it from the training size and the horizon.
    y = df_single.set_index("date")["sales"].asfreq(
        profile.data_profile.frequency
    )
    # `cv` has no forecaster attached, so skforecast warns that the last
    # window cannot be computed; irrelevant for counting folds.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=IgnoredArgumentWarning)
        n_folds = len(cv.split(X=y))
    assert result.cv_config["n_folds"] == n_folds


# =============================================================================
# Tests: auto profile/plan generation
# =============================================================================
def test_backtest_output_when_no_profile_or_plan():
    """
    Test that backtest() auto-generates profile and plan when not provided.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    result = assistant.backtest(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.steps == 5
    assert isinstance(result.metrics, pd.DataFrame)


def test_backtest_output_when_no_exog():
    """
    Test that backtest() works correctly for data without exogenous
    variables.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    result = assistant.backtest(
        data=df_no_exog,
        target="sales",
        date_column="date",
        cv=cv,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.use_exog is False
    assert len(result.predictions) > 0


def test_backtest_output_when_profile_given_without_target():
    """
    Test that a supplied profile makes `target` and `date_column`
    optional for backtest(), taking them from the profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60)

    result = assistant.backtest(
        data=df_single, cv=cv, profile=profile, plan=plan, show_progress=False
    )

    assert result.profile is profile
    assert result.cv_config["n_folds"] >= 2


def test_backtest_output_when_cv_result_given():
    """
    Test that backtest() accepts the CVResult returned by create_cv() and
    runs with its splitter, reporting the same configuration.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=plan,
        show_progress=False,
    )

    assert result.cv_config == cv_result.cv_config
    assert len(result.predictions) > 0


def test_backtest_output_when_interval_passed_with_plan():
    """
    Test that an `interval` passed alongside a pre-built plan without
    intervals is applied to the backtest: the executed plan carries it and
    the predictions include the bounds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    result = assistant.backtest(
        data=df_single,
        cv=cv,
        interval=[0.1, 0.9],
        profile=profile,
        plan=plan,
        show_progress=False,
    )

    assert result.plan.interval == [0.1, 0.9]
    assert {"lower_bound", "upper_bound"} <= set(result.predictions.columns)


def test_backtest_ValueError_when_estimator_differs_from_plan():
    """
    Test that backtest() rejects an `estimator` override that differs from
    the estimator of the pre-built plan instead of silently ignoring it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, estimator="Ridge")
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    with pytest.raises(ValueError, match=re.escape("['estimator']")):
        assistant.backtest(
            data=df_single,
            cv=cv,
            estimator="LGBMRegressor",
            profile=profile,
            plan=plan,
            show_progress=False,
        )


def test_backtest_output_when_baseline_plan():
    """
    Test that backtest() runs a ForecasterEquivalentDate plan and reports
    the error of the seasonal naive baseline on a linear series (7 per step).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterEquivalentDate")

    result = assistant.backtest(
        data=df_single,
        cv=TimeSeriesFold(steps=5, initial_train_size=70, verbose=False),
        profile=profile,
        plan=plan,
        show_progress=False,
    )

    expected_metrics = pd.DataFrame(
        {
            "mean_absolute_error": [7.0],
            "mean_squared_error": [49.0],
            "mean_absolute_scaled_error": [7.0],
        }
    )
    assert isinstance(result, BacktestResult)
    pd.testing.assert_frame_equal(result.metrics, expected_metrics)
    assert "backtesting_forecaster(" in result.code



def test_backtest_output_script_loads_csv_path_that_ran(tmp_path):
    """
    Test that backtest() with a CSV path returns a script that loads that
    path, also with a saved profile built from another path.
    """
    old_path = tmp_path / "old.csv"
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(old_path, index=False)
    df_single.to_csv(csv_path, index=False)
    cv = TimeSeriesFold(steps=5, initial_train_size=60)
    profile = assistant.profile(data=old_path, target="sales", date_column="date")

    result = assistant.backtest(
        data=csv_path, cv=cv, target="sales", date_column="date",
        show_progress=False,
    )
    result_saved = assistant.backtest(
        data=csv_path, cv=cv, profile=profile, show_progress=False
    )

    for res in (result, result_saved):
        assert f"data = pd.read_csv({str(csv_path)!r})" in res.code
        assert res.profile.data_profile.data_path == str(csv_path)
    assert profile.data_profile.data_path == str(old_path)


# =============================================================================
# Tests: early input checks
# =============================================================================
@pytest.mark.parametrize(
    "cv, type_name",
    [({"steps": 5}, "dict"), (None, "NoneType"), (5, "int")],
    ids=["dict", "None", "int"],
)
def test_backtest_InvalidInputTypeError_when_cv_wrong_type(cv, type_name):
    """
    Test that backtest() raises InvalidInputTypeError (a TypeError) with the
    field 'cv' when it is not a TimeSeriesFold or a CVResult.
    """
    err_msg = re.escape(
        f"`cv` must be a skforecast TimeSeriesFold or the CVResult of "
        f"create_cv(), got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        assistant.backtest(
            data=df_single, cv=cv, target="sales", date_column="date"
        )

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "cv"


def test_backtest_InvalidInputError_when_foundation_backend_not_installed(
    monkeypatch,
):
    """
    Test that backtest() with a ForecasterFoundation plan raises the error
    'missing_dependency' for the field 'estimator', with the install command,
    before running any script.
    """
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )

    def _not_called(*args, **kwargs):
        raise AssertionError("run_backtest must not be called")

    monkeypatch.setattr("skforecast_ai.assistant.run_backtest", _not_called)
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    err_msg = re.escape(
        "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
        "which is not installed (pip install \"chronos-forecasting\")."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data          = df_no_exog,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
        )

    assert exc_info.value.code == "missing_dependency"
    assert exc_info.value.field == "estimator"
    assert exc_info.value.hint == (
        'Install it where skforecast-ai runs: pip install "chronos-forecasting".'
    )


def test_backtest_LongTrainingWarning_when_foundation_inference_windows_exceed_threshold(
    monkeypatch,
):
    """
    Test that backtest() of a ForecasterFoundation plan, which fits no
    estimator, warns before running when its inference windows (series
    times folds) exceed the threshold (lowered to 3 here, 2000 by default),
    and states them in `cv_config`. The warning comes before the check of
    the backend, which then fails here because it is not installed.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 3)
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    warn_msg = re.escape(
        "ForecasterFoundation will forecast up to 6 inference windows (1 series x 6 "
        "folds), more than 3. This can take minutes on a CPU."
    )
    with pytest.warns(LongTrainingWarning, match=warn_msg):
        with pytest.raises(
            InvalidInputError, match=re.escape("chronos-forecasting")
        ):
            assistant.backtest(
                data          = df_no_exog,
                cv            = cv,
                profile       = profile,
                plan          = plan,
                show_progress = False,
            )


@pytest.mark.parametrize(
    "forecaster, estimator",
    [("ForecasterRecursive", "Ridge"), ("ForecasterStats", None)],
    ids=["ridge", "stats"],
)
def test_backtest_InvalidInputError_when_target_has_infinite_value(
    forecaster, estimator
):
    """
    Test that backtest() raises, before running the script, when the target
    has an infinite value (h2o, position 50, 1995-09-01) and the forecaster
    is trained on it. The plan is built from the data without it; the data
    are profiled again, which warns about the infinite value.
    """
    data = df_h2o.copy()
    data.iloc[50, 0] = np.inf
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(
        profile, steps=3, forecaster=forecaster, estimator=estimator
    )
    cv = assistant.create_cv(profile, plan)

    err_msg = re.escape(
        f"The target has infinite values (1 value(s), such as '1995-09-01'). "
        f"{forecaster} cannot be trained on them: replace them."
    )
    with (
        pytest.raises(InvalidInputError, match=err_msg) as exc_info,
        pytest.warns(RuntimeWarning, match="invalid value encountered in subtract"),
        pytest.warns(MissingValuesWarning, match="Interleaved NaN/inf detected"),
    ):
        assistant.backtest(
            data=data, cv=cv, profile=profile, plan=plan, show_progress=False
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Replace the infinite values of the target, for example with NaN."
    )


def test_backtest_InvalidInputError_when_lag_reads_missing_timestamp():
    """
    Test that backtest() raises InvalidInputError, naming the date, instead
    of ForecastExecutionError from the generated script ("Input contains
    NaN"), when a lag reads a missing timestamp (2004-10-01) to predict a
    test fold, and that forecast() of the same plan, whose last values are
    complete, still works. `create_cv()` warns beforehand.
    """
    profile = assistant.profile(data=data_h2o_gaps, target="x")
    plan = assistant.plan(profile, steps=12)
    warn_msg = re.escape("`backtest()` checks every test fold")
    with pytest.warns(UserWarning, match=warn_msg):
        cv = assistant.create_cv(profile, plan, initial_train_size=84, refit=False)

    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict 1 of "
        "the 3 test folds ('x': 1 value(s), such as '2004-10-01'). "
        "ForecasterRecursive with Ridge cannot use them, so its predictions "
        "would be missing. "
        "Either they are filled in, or the plan uses an estimator that "
        "accepts missing values (such as 'RandomForestRegressor')."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=data_h2o_gaps, cv=cv, profile=profile, plan=plan, show_progress=False
        )
    with (
        pytest.warns(MissingValuesWarning, match="NaNs detected in `y_train`"),
        pytest.warns(MissingValuesWarning, match="NaNs detected in `X_train`"),
    ):
        result = assistant.forecast(data=data_h2o_gaps, profile=profile, plan=plan)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert len(result.predictions) == 12


# =============================================================================
# Tests: plans that cannot run
# =============================================================================
@pytest.mark.parametrize(
    "initial_train_size, n_train",
    [(None, 4), (36, 36)],
    ids=["default strategy of a long horizon", "explicit window"],
)
def test_backtest_InvalidInputError_when_first_window_shorter_than_forecaster(
    initial_train_size, n_train
):
    """
    Test that backtest() rejects, before running, a strategy whose first
    training window is not longer than the window of the forecaster, with
    code 'insufficient_data' and field 'cv': on h2o (204 observations), the
    default strategy of `steps=100` leaves 4 observations, and the default
    plan reads 36 (its largest window feature).
    """
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=100)
    with pytest.warns(UserWarning, match="The first training window"):
        cv = assistant.create_cv(
            profile, plan, initial_train_size=initial_train_size
        )

    err_msg = re.escape(
        f"The first training window of the strategy has {n_train} "
        f"observations, and ForecasterRecursive needs at least 37 (more than "
        f"its window size, 36), so skforecast would fail. Use a later "
        f"`initial_train_size`, or a shorter horizon (`steps`), fewer lags or "
        f"smaller window features."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data          = df_h2o,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
        )

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "cv"


def test_backtest_output_when_long_series_start_on_different_dates_and_date_split():
    """
    Test that a date `initial_train_size` on long data whose series start on
    different dates is placed from the earliest first date, as skforecast
    splits them: '2020-01-13' leaves 13 observations, more than the 5 of
    the window of the plan, so the backtest runs without a warning. With
    refit, the series 'b', with 3 observations in the first training window,
    is forecast from the second fold on.
    """
    dates = pd.date_range("2020-01-01", periods=80, freq="D")
    values = np.arange(80, dtype=float) % 7
    data = pd.concat([
        pd.DataFrame({"date": dates, "sid": "a", "y": values}),
        pd.DataFrame({"date": dates[10:], "sid": "b", "y": values[10:] + 1.0}),
    ], ignore_index=True)
    profile = assistant.profile(
        data             = data,
        target           = "y",
        date_column      = "date",
        series_id_column = "sid",
    )
    plan = assistant.plan(
        profile,
        steps           = 3,
        lags            = 5,
        window_features = [{"stats": ["mean"], "window_size": 2}],
    )
    cv = assistant.create_cv(
        profile, plan, initial_train_size="2020-01-13", refit=True
    )

    result = assistant.backtest(
        data          = data,
        cv            = cv,
        profile       = profile,
        plan          = plan,
        show_progress = False,
    )

    assert result.predictions.index.min() == pd.Timestamp("2020-01-14")
    first_dates = result.predictions.reset_index().groupby("level")["index"].min()
    assert first_dates.to_dict() == {
        "a": pd.Timestamp("2020-01-14"), "b": pd.Timestamp("2020-01-17")
    }


def test_backtest_output_when_dates_have_a_time_zone():
    """
    Test that backtest() of data whose dates have a time zone, with the
    default strategy of create_cv() (a date without time zone), runs: the
    date is read in the time zone of the data, the script gets its number
    of observations, `cv_config` keeps the date, backtest_code() returns
    the same script, and the predictions are those of the same data
    without time zone.
    """
    data = df_h2o_madrid
    profile = assistant.profile(data=data, target="x")
    plan = assistant.plan(profile, steps=12)
    cv = assistant.create_cv(profile, plan)
    naive_profile = assistant.profile(data=df_h2o, target="x")
    naive_plan = assistant.plan(naive_profile, steps=12)
    expected = assistant.backtest(
        data          = df_h2o,
        cv            = assistant.create_cv(naive_profile, naive_plan),
        profile       = naive_profile,
        plan          = naive_plan,
        show_progress = False,
    )

    result = assistant.backtest(
        data          = data,
        cv            = cv,
        profile       = profile,
        plan          = plan,
        show_progress = False,
    )
    code = assistant.backtest_code(data=data, cv=cv, profile=profile, plan=plan)

    assert result.cv_config["initial_train_size"] == "2003-04-01"
    assert "    initial_train_size = 142,\n" in result.code
    assert code.code == result.code
    np.testing.assert_allclose(
        result.predictions["pred"].to_numpy(),
        expected.predictions["pred"].to_numpy(),
    )
    assert result.predictions.index[0] == pd.Timestamp(
        "2003-05-01", tz="Europe/Madrid"
    )


@pytest.mark.parametrize(
    "initial_train_size, in_config, in_code",
    [
        (
            "2003-04-01 00:00:00+02:00",
            "2003-04-01 00:00:00+02:00",
            "    initial_train_size = '2003-04-01 00:00:00+02:00',\n",
        ),
        (
            "2003-03-31 22:00:00+00:00",
            "2003-03-31 22:00:00+00:00",
            "    initial_train_size = '2003-03-31 22:00:00+00:00',\n",
        ),
        (
            pd.Timestamp("2003-04-01", tz="Europe/Madrid"),
            "2003-04-01 00:00:00+02:00",
            "    initial_train_size = pd.Timestamp('2003-04-01 00:00:00+02:00'),\n",
        ),
    ],
    ids=["local offset", "UTC", "Timestamp"],
)
def test_backtest_output_when_cv_date_and_dates_have_a_time_zone(
    initial_train_size, in_config, in_code
):
    """
    Test that backtest() of data whose dates have a time zone, with an
    `initial_train_size` date that has one too, runs (the strategy was
    rejected as a date with a time zone on an index without one): the date
    is placed at its instant, the script and `cv_config` keep it as given,
    backtest_code() returns the same script, and the predictions are those
    of the same date without time zone.
    """
    cv = TimeSeriesFold(
        steps=12, initial_train_size=initial_train_size, verbose=False
    )
    expected = assistant.backtest(
        data          = df_h2o_madrid,
        cv            = TimeSeriesFold(
                            steps=12, initial_train_size="2003-04-01", verbose=False
                        ),
        target        = "x",
        estimator     = "Ridge",
        show_progress = False,
    )

    result = assistant.backtest(
        data=df_h2o_madrid, cv=cv, target="x", estimator="Ridge",
        show_progress=False,
    )
    code = assistant.backtest_code(
        data=df_h2o_madrid, cv=cv, target="x", estimator="Ridge"
    )

    assert result.cv_config["initial_train_size"] == in_config
    assert result.cv_config["n_folds"] == 6
    assert in_code in result.code
    assert code.code == result.code
    pd.testing.assert_frame_equal(result.predictions, expected.predictions)
    assert result.predictions.index[0] == pd.Timestamp(
        "2003-05-01", tz="Europe/Madrid"
    )


def test_backtest_output_when_cv_initial_train_size_is_a_timestamp():
    """
    Test that backtest() runs a `TimeSeriesFold` whose `initial_train_size`
    is a pandas Timestamp (it raised a bare TypeError while describing the
    strategy): `cv_config` stores the date as text, the explanation names
    it, the script keeps the Timestamp and the predictions are those of the
    same date as text.
    """
    cv = TimeSeriesFold(
        steps=12, initial_train_size=pd.Timestamp("2003-04-01"), verbose=False
    )
    expected = assistant.backtest(
        data          = df_h2o,
        cv            = TimeSeriesFold(
                            steps=12, initial_train_size="2003-04-01", verbose=False
                        ),
        target        = "x",
        estimator     = "Ridge",
        show_progress = False,
    )

    result = assistant.backtest(
        data=df_h2o, cv=cv, target="x", estimator="Ridge", show_progress=False
    )
    code = assistant.backtest_code(data=df_h2o, cv=cv, target="x", estimator="Ridge")

    assert result.cv_config["initial_train_size"] == "2003-04-01"
    assert result.explanation.startswith("Initial training up to 2003-04-01,")
    assert (
        "    initial_train_size = pd.Timestamp('2003-04-01 00:00:00'),\n"
        in result.code
    )
    assert code.code == result.code
    pd.testing.assert_frame_equal(result.predictions, expected.predictions)


def test_backtest_InvalidInputError_when_direct_forecaster_with_gap():
    """
    Test that backtest() rejects, before running, a ForecasterDirect plan
    with a cv whose gap is greater than 0, with `cv` as field: each fold asks
    the forecaster for steps + gap steps, more than it was built for.
    """
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterDirect")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=2, verbose=False)

    err_msg = re.escape(
        "ForecasterDirect is trained to predict 5 steps, and with `gap=2` "
        "each fold needs steps + gap = 7 steps ahead, so skforecast would "
        "fail. Use a strategy without gap, or a recursive forecaster."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=df_no_exog, target="sales", date_column="date", cv=cv,
            profile=profile, plan=plan, show_progress=False,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "cv"


@pytest.mark.parametrize(
    "forecaster, gap",
    [("ForecasterRecursive", 2), ("ForecasterDirect", 0)],
    ids=["recursive_with_gap", "direct_without_gap"],
)
def test_backtest_runs_when_gap_is_valid_for_forecaster(forecaster, gap):
    """
    Test that backtest() runs a ForecasterRecursive plan with a gap, and a
    ForecasterDirect plan with gap 0.
    """
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster=forecaster)
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=gap, verbose=False)

    result = assistant.backtest(
        data=df_no_exog, target="sales", date_column="date", cv=cv,
        profile=profile, plan=plan, show_progress=False,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.forecaster == forecaster


_ITEMS_LONG = df_items_sales_long


def _long_cv():
    """Return a TimeSeriesFold for the items_sales fixtures (120 days)."""
    return TimeSeriesFold(steps=5, initial_train_size=80, verbose=False)


def test_backtest_InvalidInputError_when_long_series_has_no_values():
    """
    Test that backtest() rejects long-format data where a series has every
    value missing, whatever its folds: skforecast fails on it in the script.
    """
    data = _ITEMS_LONG.copy()
    data.loc[data["series"] == "item_2", "value"] = np.nan

    err_msg = re.escape(
        "Some series have no values ('item_2'), so "
        "ForecasterRecursiveMultiSeries cannot be trained on them. Remove "
        "them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=data, target="value", date_column="date",
            series_id_column="series", cv=_long_cv(), show_progress=False,
        )

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == "Remove the series without values from the data."


def _items_starting_late(n_values: int) -> pd.DataFrame:
    """Return the long items_sales data with only the last `n_values` of item_2."""
    return _ITEMS_LONG[
        ~(
            (_ITEMS_LONG["series"] == "item_2")
            & (_ITEMS_LONG["date"] <= pd.Timestamp("2012-04-29") - pd.Timedelta(
                days=n_values
            ))
        )
    ]


@pytest.mark.parametrize(
    "n_values, refit",
    [(100, False), (60, True)],
    ids=["first_window_holds_40", "refit"],
)
def test_backtest_runs_when_long_series_starts_late(n_values, refit):
    """
    Test that backtest() runs when a long-format series starts late but some
    fold forecasts it: with 100 values, the first training window (80 days)
    holds 40 of them, more than the window of the plan (21); with 60 and
    refit, the later folds train on more than 21 of them. Every series is
    in the predictions.
    """
    cv = _long_cv()
    cv.set_params({"refit": refit})

    result = assistant.backtest(
        data=_items_starting_late(n_values), target="value", date_column="date",
        series_id_column="series", cv=cv, show_progress=False,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.forecaster == "ForecasterRecursiveMultiSeries"
    assert sorted(result.predictions["level"].unique()) == [
        "item_1", "item_2", "item_3"
    ]


@pytest.mark.parametrize("n_values", [1, 21, 60], ids=lambda n: f"values: {n}")
def test_backtest_InvalidInputError_when_long_series_is_never_forecast(n_values):
    """
    Test that backtest() rejects, before running, a long-format series that
    no fold forecasts: with 1 or 21 values, no more than the window of the
    plan (21); with 60, only 20 in the first training window (80 days) and
    no refit. skforecast left it out of the predictions and of the average
    across series without a warning.
    """
    with pytest.raises(InvalidInputError) as exc_info:
        assistant.backtest(
            data=_items_starting_late(n_values), target="value",
            date_column="date", series_id_column="series", cv=_long_cv(),
            show_progress=False,
        )

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert str(exc_info.value).startswith(
        f"Some series cannot be forecast in any fold of the backtest ('item_2': "
        f"{n_values} observations, from their first to their last value). "
        f"ForecasterRecursiveMultiSeries forecasts a series in a fold only when "
        f"the training window of the fold has more than the 21 observations"
    )


@pytest.mark.parametrize("with_profile", [True, False], ids=["profile", "no_profile"])
def test_backtest_output_when_long_format_multiindex(with_profile):
    """
    Test that backtest() runs long-format data indexed by a (series, date)
    MultiIndex as the same data with the levels as columns, which is how the
    script reads the frame saved with `to_csv()`: same script, predictions
    and metrics. Before, the executed script did not find the date column
    (KeyError: 'date').
    """
    with pytest.warns(
        EstimatorNotRecommendedWarning, match=RIDGE_MULTISERIES_WARNING
    ):
        expected = assistant.backtest(
            data             = _ITEMS_LONG,
            target           = "value",
            date_column      = "date",
            series_id_column = "series",
            cv               = _long_cv(),
            estimator        = "Ridge",
            show_progress    = False,
        )
    data = _ITEMS_LONG.set_index(["series", "date"])
    if with_profile:
        profile = assistant.profile(data=data, target="value")
        plan = assistant.plan(profile, steps=5, estimator="Ridge")
        kwargs = {"profile": profile, "plan": plan}
    else:
        kwargs = {"target": "value", "estimator": "Ridge"}

    with pytest.warns(
        EstimatorNotRecommendedWarning, match=RIDGE_MULTISERIES_WARNING
    ):
        result = assistant.backtest(
            data=data, cv=_long_cv(), show_progress=False, **kwargs
        )

    assert result.code == expected.code
    pd.testing.assert_frame_equal(result.predictions, expected.predictions)
    pd.testing.assert_frame_equal(result.metrics, expected.metrics)


@pytest.mark.parametrize("with_profile", [True, False], ids=["profile", "no_profile"])
def test_backtest_InvalidInputError_when_multiindex_level_unnamed(with_profile):
    """
    Test that backtest() rejects long-format data indexed by a MultiIndex
    with a level without a name, also with a profile of the same data with
    named levels: the script reads the levels by name from the frame saved
    with `to_csv()`, which writes an empty header for them.
    """
    data = _ITEMS_LONG.set_index(["series", "date"])
    kwargs = {"target": "value", "estimator": "Ridge"}
    if with_profile:
        kwargs = {"profile": assistant.profile(data=data, target="value")}
    err_msg = re.escape(
        "`data` is indexed by a MultiIndex with levels without a name "
        "(names ['series', None])."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data          = data.rename_axis(["series", None]),
            cv            = _long_cv(),
            show_progress = False,
            **kwargs,
        )

    assert exc_info.value.field == "data"


def test_backtest_InvalidInputError_when_received_plan_clashes_with_exog_names():
    """
    Test that backtest() checks a plan built on clean data against the
    exogenous columns of the profile it receives: a column named 'lag_1'
    clashes with the lags of the plan, as plan() would have found.
    """
    plan = assistant.plan(
        assistant.profile(data=df_single, target="sales", date_column="date"),
        steps=5, lags=[1, 2],
    )
    data = df_single.rename(columns={"promo": "lag_1"})
    profile = assistant.profile(data=data, target="sales", date_column="date")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    err_msg = re.escape(
        "Exogenous column(s) 'lag_1' have the name of a predictor that "
        "ForecasterRecursive creates (a lag or a window feature), so the "
        "script would fail with duplicated feature names. Rename them in the "
        "data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=data, cv=cv, profile=profile, plan=plan, show_progress=False
        )

    assert exc_info.value.field == "data"


@pytest.mark.parametrize("tz", ["UTC", "Europe/Madrid"])
def test_backtest_DataContentError_when_time_zone_data_and_cv_date_without_zone(
    tz
):
    """
    Test that backtest() of tz-aware data with a missing value in a test fold
    and an `initial_train_size` date without time zone reports the missing
    value before any script runs: the date is read in the time zone of the
    data, so the check of the evaluated target finds the test folds.
    """
    data = df_h2o.copy()
    data.index = data.index.tz_localize(tz)
    data.iloc[-5, 0] = np.nan
    cv = TimeSeriesFold(steps=12, initial_train_size="2004-01-01", verbose=False)

    err_msg = re.escape(
        "The target has 1 missing value(s) in test fold 5 of 5 (2008-02-01"
    )
    with pytest.warns(MissingValuesWarning):
        with pytest.raises(DataContentError, match=err_msg):
            assistant.backtest(
                data=data, cv=cv, target="x", estimator="Ridge",
                show_progress=False,
            )


# =============================================================================
# Tests: coherence of the CVResult, the plan and the profile
# =============================================================================
def test_backtest_output_when_cv_result_without_plan_keeps_its_plan():
    """
    Test that backtest() with the CVResult of create_cv() and no `plan`,
    `forecaster`, `estimator`, `estimator_kwargs` or `interval` runs the
    plan of the CVResult: its estimator and interval are kept.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", interval=[0.1, 0.9]
    )
    with pytest.warns(UserWarning, match=INTERVAL_WARNING):
        cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    warn_msg = re.escape(
        "The estimator of the plan, 'LGBMRegressor' (chosen by the user), is "
        "not the one the rules recommend for ForecasterRecursive on these "
        "data: 'Ridge'."
    )
    with pytest.warns(EstimatorNotRecommendedWarning, match=warn_msg):
        result = assistant.backtest(
            data=df_single,
            target="sales",
            date_column="date",
            cv=cv_result,
            show_progress=False,
        )

    assert result.plan == cv_result.plan
    assert result.plan.estimator == "LGBMRegressor"
    assert result.plan.interval == [0.1, 0.9]
    assert list(result.predictions.columns) == [
        "fold", "pred", "lower_bound", "upper_bound"
    ]
    assert result.cv_config == cv_result.cv_config


def test_backtest_output_when_cv_result_and_estimator_passed_builds_new_plan():
    """
    Test that backtest() with the CVResult and an `estimator` builds a new
    plan with it, without the interval of the plan of the CVResult.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", interval=[0.1, 0.9]
    )
    with pytest.warns(UserWarning, match=INTERVAL_WARNING):
        cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.backtest(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv_result,
        estimator="Ridge",
        show_progress=False,
    )

    assert result.plan.estimator == "Ridge"
    assert result.plan.interval is None
    assert list(result.predictions.columns) == ["fold", "pred"]


def test_backtest_output_when_bare_time_series_fold_builds_default_plan():
    """
    Test that backtest() with the TimeSeriesFold of a CVResult (not the
    CVResult) builds the default plan, not the plan of the CVResult.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", interval=[0.1, 0.9]
    )
    with pytest.warns(UserWarning, match=INTERVAL_WARNING):
        cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.backtest(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv_result.cv,
        show_progress=False,
    )

    assert result.plan == assistant.plan(profile, steps=5)
    assert result.plan.estimator == "Ridge"
    assert result.plan.interval is None


def test_backtest_InvalidInputError_when_cv_result_of_another_structure():
    """
    Test that backtest() raises InvalidInputError with the field 'cv' when
    the CVResult was created for data of another structure (single series
    of monthly data used with wide multi-series daily data).
    """
    h2o_profile = assistant.profile(data=df_h2o, target="x")
    cv_result = assistant.create_cv(h2o_profile, assistant.plan(h2o_profile, steps=5))

    err_msg = re.escape(
        "The CVResult was created for data of another structure "
        "(data_format: 'single' != 'wide'; "
        "target: 'x' != ['series_a', 'series_b']; "
        "date_column: None != 'date'; "
        "frequency: 'MS' != 'D'). Create the strategy from the profile of "
        "these data with `create_cv()`, or pass its TimeSeriesFold "
        "(`cv.cv`)."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=df_multi_wide,
            target=["series_a", "series_b"],
            date_column="date",
            cv=cv_result,
            show_progress=False,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "cv"


def test_backtest_output_when_cv_result_of_same_data_shorter():
    """
    Test that backtest() accepts a CVResult created for the same data with
    more observations (same structure).
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    cv_result = assistant.create_cv(profile, assistant.plan(profile, steps=5))

    result = assistant.backtest(
        data=df_single.iloc[:80],
        target="sales",
        date_column="date",
        cv=cv_result,
        show_progress=False,
    )

    assert len(result.predictions) > 0


def test_backtest_InvalidInputError_when_plan_of_another_frequency():
    """
    Test that backtest() raises InvalidInputError with the field 'plan'
    when the plan was built for monthly data and the data is daily.
    """
    h2o_profile = assistant.profile(data=df_h2o, target="x")
    h2o_plan = assistant.plan(h2o_profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    err_msg = re.escape(
        "The plan was built for data of frequency 'MS', and the data has "
        "frequency 'D'. Build the plan from the profile of these data with "
        "`plan()`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=df_single,
            target="sales",
            date_column="date",
            cv=cv,
            plan=h2o_plan,
            show_progress=False,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "plan"


def test_backtest_InvalidInputError_when_single_series_plan_on_multi_series_data():
    """
    Test that backtest() raises the task type error of the plan when a
    single-series plan is used with wide multi-series data of the same
    frequency.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    err_msg = re.escape(
        "Task type 'single_series' supports a single series only, but the "
        "input contains 2 series (['series_a', 'series_b']). Use a "
        "multi-series forecaster (e.g. 'ForecasterRecursiveMultiSeries') or "
        "provide a single series."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=df_multi_wide,
            target=["series_a", "series_b"],
            date_column="date",
            cv=cv,
            plan=plan,
            show_progress=False,
        )

    assert exc_info.value.field == "forecaster"


def test_backtest_InvalidInputError_when_plan_uses_exog_and_data_has_none():
    """
    Test that backtest() raises InvalidInputError with the field 'plan'
    when the plan uses exogenous variables and the data has none.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    err_msg = re.escape(
        "The plan uses exogenous variables and the data has none. Build the "
        "plan from the profile of these data with `plan()`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=df_no_exog,
            target="sales",
            date_column="date",
            cv=cv,
            plan=plan,
            show_progress=False,
        )

    assert exc_info.value.field == "plan"


# =============================================================================
# Tests: data against a saved profile
# =============================================================================
def test_backtest_output_when_data_have_more_rows_than_profile():
    """
    Test that backtest() with data that extend the saved profile (192 rows
    in the profile, 204 in the data) uses the new data: the note is added to
    the profile and the backtest runs 35 folds, not the 31 of the profile.
    """
    cv = TimeSeriesFold(steps=3, initial_train_size=100, verbose=False)
    profile = assistant.profile(data=df_h2o.iloc[:192], target="x")

    saved_result = assistant.backtest(
        data=df_h2o.iloc[:192], cv=cv, profile=profile, show_progress=False
    )
    result = assistant.backtest(
        data=df_h2o, cv=cv, profile=profile, show_progress=False
    )

    assert saved_result.cv_config["n_folds"] == 31
    assert saved_result.profile.data_profile.warnings == []
    assert result.cv_config["n_folds"] == 35
    assert result.profile.data_profile.n_total_observations == 204
    assert result.profile.data_profile.warnings == [
        "The data differ in their values from the profile passed (changed: "
        "series_lengths, span_index_length, n_total_observations, "
        "target_stats): the profile was computed again from these data."
    ]
    assert result.predictions.shape == (104, 2)
    assert result.predictions.index[-1] == pd.Timestamp("2008-06-01")


def test_backtest_output_when_data_equal_to_profile():
    """
    Test that backtest() with data equal to the saved profile keeps the
    profile unchanged, without a note.
    """
    cv = TimeSeriesFold(steps=3, initial_train_size=100, verbose=False)
    profile = assistant.profile(data=df_h2o, target="x")

    result = assistant.backtest(
        data=df_h2o, cv=cv, profile=profile, show_progress=False
    )

    assert result.profile.data_profile == profile.data_profile
    assert result.profile.data_profile.warnings == []
    assert result.cv_config["n_folds"] == 35


@pytest.mark.parametrize(
    "data, differences",
    [
        (df_h2o_daily, "(frequency: 'MS' != 'D')"),
    ],
    ids=["frequency"],
)
def test_backtest_InvalidInputError_when_data_have_other_structure_than_profile(
    data, differences
):
    """
    Test that backtest() raises InvalidInputError with the field 'profile'
    when the data have another frequency than the saved
    profile, before running the backtest.
    """
    cv = TimeSeriesFold(steps=3, initial_train_size=50, verbose=False)
    profile = assistant.profile(data=df_h2o, target="x")

    err_msg = re.escape(
        f"The data do not have the structure of the profile passed {differences}: "
        f"profile these data and build the plan from that profile."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest(
            data=data, cv=cv, profile=profile, show_progress=False
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "profile"


def test_backtest_output_when_lags_window_features_and_metric_given():
    """
    Test that backtest() takes `lags`, `window_features` and `metric` to
    build its plan, also with the CVResult of create_cv(), whose plan is
    then not the one run.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)
    window_features = [{"stats": ["mean"], "window_size": 3}]

    result = assistant.backtest(
        data            = df_single,
        target          = "sales",
        date_column     = "date",
        cv              = cv_result,
        lags            = [1, 2],
        window_features = window_features,
        metric          = "mean_squared_error",
        show_progress   = False,
    )

    assert result.plan.forecaster_kwargs["lags"] == [1, 2]
    assert result.plan.forecaster_kwargs["window_features"] == window_features
    assert result.plan.metrics_to_compute == ["mean_squared_error"]
    assert result.plan.overridden_fields == ["lags", "window_features", "metric"]
    assert list(result.metrics.columns) == ["mean_squared_error"]


def test_backtest_ValueError_when_metric_differs_from_plan():
    """
    Test that a `metric` different from what a given plan computes is
    rejected, pointing to refine_plan(), and an equal one is accepted.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, metric="mean_squared_error")
    cv = TimeSeriesFold(steps=5, initial_train_size=60)
    inputs = {
        "data": df_single, "target": "sales", "date_column": "date", "cv": cv,
        "profile": profile, "plan": plan, "show_progress": False,
    }

    err_msg = re.escape(
        "A pre-built `plan` was provided and the following argument(s) differ "
        "from what it holds: ['metric']."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        assistant.backtest(**inputs, metric="mean_absolute_error")
    result = assistant.backtest(**inputs, metric=["mean_squared_error"])

    assert result.plan.metric == "mean_squared_error"


def test_backtest_ValueError_when_use_exog_differs_from_plan():
    """
    Test that a `use_exog` different from the one of a given plan is
    rejected, pointing to refine_plan().
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60)

    with pytest.raises(InvalidInputError, match=re.escape("['use_exog']")):
        assistant.backtest(
            data=df_single, target="sales", date_column="date", cv=cv,
            profile=profile, plan=plan, use_exog=False, show_progress=False,
        )


def test_backtest_ValueError_when_cv_differentiation_differs_from_plan():
    """
    Test that a strategy whose differentiation order is not the one of the
    plan (also None against an order) is rejected before running, where
    skforecast rejected it inside the script.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, differentiation=1)
    inputs = {
        "data": df_single, "target": "sales", "date_column": "date",
        "profile": profile, "show_progress": False,
    }

    for cv_differentiation in (2, None):
        err_msg = re.escape(
            f"The cross-validation strategy has `differentiation="
            f"{cv_differentiation}` and the plan `differentiation=1`: they "
            f"must match."
        )
        cv = TimeSeriesFold(
            steps=5, initial_train_size=60, differentiation=cv_differentiation
        )
        with pytest.raises(InvalidInputError, match=err_msg) as info:
            assistant.backtest(**inputs, plan=plan, cv=cv)
        assert info.value.field == "cv"
    result = assistant.backtest(
        **inputs, plan=plan,
        cv=TimeSeriesFold(steps=5, initial_train_size=60, differentiation=1),
    )

    assert result.plan.forecaster_kwargs["differentiation"] == 1


def test_backtest_output_when_stats_ignores_cv_differentiation():
    """
    Test that ForecasterStats, which skforecast backtests without checking
    the differentiation order of the strategy, still runs with a strategy
    that has one, as it did.
    """
    assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=12, initial_train_size=150, differentiation=1)

    result = assistant.backtest(
        df_h2o, target="x", cv=cv, forecaster="ForecasterStats",
        show_progress=False,
    )

    assert result.plan.forecaster == "ForecasterStats"


def test_backtest_output_when_plan_of_exog_columns_given_without_its_profile():
    """
    Test that backtest() and backtest_code() given a plan built from a
    profile with `exog_columns`, without that profile, profile the data with
    the columns the plan records: same script and metrics as with the
    profile.
    """
    cv = TimeSeriesFold(steps=3, initial_train_size=70, verbose=False)
    profile = assistant.profile(
        data         = df_categorical_exog,
        target       = "sales",
        date_column  = "date",
        exog_columns = ["promo"],
    )
    plan = assistant.plan(profile, steps=3)
    expected = assistant.backtest(
        data=df_categorical_exog, cv=cv, profile=profile, plan=plan,
        show_progress=False,
    )

    result = assistant.backtest(
        data          = df_categorical_exog,
        cv            = cv,
        target        = "sales",
        date_column   = "date",
        plan          = plan,
        show_progress = False,
    )
    code = assistant.backtest_code(
        data        = df_categorical_exog,
        cv          = cv,
        target      = "sales",
        date_column = "date",
        plan        = plan,
    )

    assert result.code == expected.code == code.code
    pd.testing.assert_frame_equal(result.metrics, expected.metrics)
    assert result.profile.data_profile.unused_columns == ["weekday"]


def test_backtest_LongTrainingWarning_counts_every_series_and_the_incomplete_fold(
    monkeypatch,
):
    """
    Test that the inference windows of a ForecasterFoundation backtest count
    every series and the last fold when it is incomplete: 2 series over 7
    folds (30 test observations in steps of 5 from 68, the last one of 2)
    are 14 windows, stated in the warning and in `cv_config`. The backend
    is not installed here, so the backtest then fails.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 13)
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )
    targets = ["series_a", "series_b"]
    profile = assistant.profile(data=df_multi_wide, target=targets, date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    cv = TimeSeriesFold(steps=5, initial_train_size=68, verbose=False)

    warn_msg = re.escape(
        "ForecasterFoundation will forecast up to 14 inference windows (2 series "
        "x 7 folds), more than 13."
    )
    with pytest.warns(LongTrainingWarning, match=warn_msg):
        with pytest.raises(
            InvalidInputError, match=re.escape("chronos-forecasting")
        ):
            assistant.backtest(
                data          = df_multi_wide,
                cv            = cv,
                profile       = profile,
                plan          = plan,
                show_progress = False,
            )

    assert assistant.create_cv(
        profile, plan, initial_train_size=68
    ).cv_config["inference_windows"] == 14


# =============================================================================
# Tests: provenance of the strategy
# =============================================================================
_INITIAL_TRAIN_SIZE_DEFAULT = (
    "Initial training size by default: 70% of the 100 observations (70), up "
    "to 2023-03-11."
)
_TRAINED_ONCE_DEFAULT = (
    "Trained once by default: refitting in every fold would multiply the "
    "training cost by the 6 folds."
)


def test_backtest_cv_provenance_when_cv_result_with_defaults_and_same_plan():
    """
    Test that backtest() with the CVResult of create_cv() without arguments
    records that nothing was passed and explains the two defaults, for the
    plan that ran.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan)

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=plan,
        show_progress=False,
    )

    assert result.cv_overridden_fields == []
    assert result.cv_fields_without_effect == []
    assert result.cv_llm_configured is False
    assert result.cv_defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} {_TRAINED_ONCE_DEFAULT}"
    )


def test_backtest_cv_provenance_when_splitter_was_changed_after_create_cv():
    """
    Test that backtest() gives no reason of a default for a value that is
    not the default any more: a CVResult whose splitter was changed after
    create_cv() keeps its empty list of names, and the text must not say
    that the strategy trains once or starts at 70% of the data.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan)
    cv_result.cv.refit = True
    cv_result.cv.initial_train_size = 50

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=plan,
        show_progress=False,
    )

    assert result.cv_config["refit"] is True
    assert result.cv_config["initial_train_size"] == 50
    assert result.cv_overridden_fields == []
    assert result.cv_defaults_explanation == ""


def test_backtest_cv_provenance_when_cv_result_with_arguments_and_same_plan():
    """
    Test that backtest() carries the names the user passed to create_cv()
    and says they were requested, without the sentence about refit that
    the user decided.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, refit=True, gap=2)

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=plan,
        show_progress=False,
    )

    assert result.cv_overridden_fields == ["refit", "gap"]
    assert result.cv_fields_without_effect == []
    assert result.cv_llm_configured is False
    assert result.cv_defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} `refit` and `gap` as requested."
    )


def test_backtest_cv_provenance_when_cv_result_llm_configured():
    """
    Test that backtest() carries `llm_configured` of the CVResult and, as
    the LLM set the parameters, explains no default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, refit=True).model_copy(
        update={"llm_configured": True}
    )

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=plan,
        show_progress=False,
    )

    assert result.cv_overridden_fields == ["refit"]
    assert result.cv_llm_configured is True
    assert result.cv_defaults_explanation == "`refit` as requested."


def test_backtest_cv_provenance_when_cv_result_and_another_plan():
    """
    Test that backtest() with a CVResult created for another plan says so,
    and explains the defaults of the plan the strategy was created for.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    direct_plan = assistant.plan(profile, steps=5, forecaster="ForecasterDirect")
    cv_result = assistant.create_cv(profile, plan)

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=direct_plan,
        show_progress=False,
    )

    assert result.plan.forecaster == "ForecasterDirect"
    assert result.cv_overridden_fields == []
    assert result.cv_fields_without_effect == []
    assert result.cv_defaults_explanation == (
        "The strategy was created for another plan (ForecasterRecursive + "
        f"Ridge). {_INITIAL_TRAIN_SIZE_DEFAULT} {_TRAINED_ONCE_DEFAULT}"
    )


def test_backtest_cv_provenance_when_refit_has_no_effect_on_the_plan_that_ran():
    """
    Test that a `refit=False` passed to create_cv() for a recursive plan is
    reported without effect when the strategy runs for ForecasterStats,
    which refits in every fold, while it had effect for its own plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    stats_plan = assistant.plan(profile, steps=5, forecaster="ForecasterStats")
    cv_result = assistant.create_cv(profile, plan, refit=False)

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=stats_plan,
        show_progress=False,
    )

    assert cv_result.fields_without_effect == []
    assert result.cv_overridden_fields == ["refit"]
    assert result.cv_fields_without_effect == ["refit"]
    assert result.cv_config["refit"] is True
    assert result.cv_defaults_explanation == (
        "The strategy was created for another plan (ForecasterRecursive + "
        f"Ridge). {_INITIAL_TRAIN_SIZE_DEFAULT} `refit` was passed but has no "
        "effect on this forecaster."
    )


def test_backtest_cv_provenance_when_cv_is_a_time_series_fold():
    """
    Test that backtest() with a bare TimeSeriesFold leaves the provenance
    unknown (`cv_overridden_fields` None, not an empty list) and without
    text, and that `cv_config` and `explanation` are the same as with the
    CVResult of the same strategy.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, refit=True)

    from_fold = assistant.backtest(
        data=df_single, cv=cv_result.cv, profile=profile, plan=plan,
        show_progress=False,
    )
    from_result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=plan,
        show_progress=False,
    )

    assert from_fold.cv_overridden_fields is None
    assert from_fold.cv_fields_without_effect == []
    assert from_fold.cv_llm_configured is False
    assert from_fold.cv_defaults_explanation == ""
    assert from_fold.cv_config == from_result.cv_config
    assert from_fold.explanation == from_result.explanation
    assert from_result.cv_defaults_explanation not in from_result.explanation


def test_backtest_cv_provenance_when_plan_differs_only_in_metric():
    """
    Test that a plan that differs from the plan of the strategy only in the
    metric gets no "created for another plan" sentence: the defaults of the
    strategy do not depend on the metric.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    metric_plan = assistant.plan(profile, steps=5, metric="mean_squared_error")
    cv_result = assistant.create_cv(profile, plan)

    result = assistant.backtest(
        data=df_single, cv=cv_result, profile=profile, plan=metric_plan,
        show_progress=False,
    )

    assert result.plan.metric == "mean_squared_error"
    assert result.cv_defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} {_TRAINED_ONCE_DEFAULT}"
    )


def test_backtest_cv_defaults_explanation_when_data_have_more_rows_than_the_strategy():
    """
    Test that backtest() of a strategy created on fewer observations than
    the data it runs on says that its default was computed on those, next
    to the numbers of that default.
    """
    short = df_no_exog.iloc[:80]
    profile = assistant.profile(data=short, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, estimator="Ridge")
    cv = assistant.create_cv(profile, plan)

    result = assistant.backtest(
        data=df_no_exog, cv=cv, profile=profile, plan=plan, show_progress=False
    )

    assert cv.defaults_explanation.startswith(
        "Initial training size by default: 70% of the 80 observations (56), up "
        "to 2023-02-25. Trained once"
    )
    assert result.cv_defaults_explanation.startswith(
        "Initial training size by default: 70% of the 80 observations (56), up "
        "to 2023-02-25. It was computed when the strategy was created, on 80 "
        "observations; the data it runs on have 100."
    )


def test_backtest_output_when_csv_has_semicolon_and_decimal_comma(tmp_path):
    """
    Test that backtest() on a CSV with ';' and a decimal comma gives the
    same metrics as on the same data written with commas, and a script that
    reads the file with `sep=';', decimal=','`.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    comma_path = tmp_path / "us.csv"
    df_dialect.to_csv(comma_path, index=False)
    cv = TimeSeriesFold(steps=5, initial_train_size=40, verbose=False)

    result = assistant.backtest(
        data=path, cv=cv, target="y", estimator="Ridge", show_progress=False
    )
    expected = assistant.backtest(
        data=comma_path, cv=cv, target="y", estimator="Ridge", show_progress=False
    )

    assert f"data = pd.read_csv({path!r}, sep=';', decimal=',')\n" in result.code
    assert "sep=" not in expected.code
    assert result.profile.data_profile.csv_sep == ";"
    assert result.profile.data_profile.csv_decimal == ","
    pd.testing.assert_frame_equal(result.metrics, expected.metrics)
    pd.testing.assert_frame_equal(result.predictions, expected.predictions)


# =============================================================================
# Tests: estimator that is not the one of the rules
# =============================================================================
def test_backtest_EstimatorNotRecommendedWarning_when_plan_refined_to_another_estimator():
    """
    Test that backtest() of a plan refined to LGBMRegressor, when the rules
    recommend Ridge for the 100 observations of the series, warns
    EstimatorNotRecommendedWarning once, with the text that names both
    estimators and says that the user chose it, and still runs that plan. The
    warning points at the call of the user.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.refine_plan(
        profile, assistant.plan(profile, steps=5), estimator="LGBMRegressor"
    )
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    warn_msg = re.escape(
        "The estimator of the plan, 'LGBMRegressor' (chosen by the user), is "
        "not the one the rules recommend for ForecasterRecursive on these "
        "data: 'Ridge'."
    )
    with pytest.warns(EstimatorNotRecommendedWarning, match=warn_msg) as record:
        result = assistant.backtest(
            data=df_single, cv=cv, profile=profile, plan=plan, show_progress=False
        )

    filenames = [
        warning.filename for warning in record
        if issubclass(warning.category, EstimatorNotRecommendedWarning)
    ]
    assert filenames == [__file__]
    assert result.plan.estimator == "LGBMRegressor"


def test_backtest_does_not_warn_EstimatorNotRecommendedWarning_when_plan_of_the_rules():
    """
    Test that backtest() of the plan of the rules (Ridge for 100
    observations), and of the same plan refined to the same estimator, does
    not warn EstimatorNotRecommendedWarning.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    same_estimator = assistant.refine_plan(profile, plan, estimator="Ridge")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    with warnings.catch_warnings():
        warnings.simplefilter("error", category=EstimatorNotRecommendedWarning)
        results = [
            assistant.backtest(
                data=df_single, cv=cv, profile=profile, plan=one_plan,
                show_progress=False,
            )
            for one_plan in (plan, same_estimator)
        ]

    assert [result.plan.estimator for result in results] == ["Ridge", "Ridge"]
