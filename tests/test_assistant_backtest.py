# Unit test backtest ForecastingAssistant

import pickle
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
    CostNotConfirmedError,
    DataContentError,
    IntervalCoverageWarning,
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
def test_backtest_CostNotConfirmedError_when_estimator_fits_exceed_threshold():
    """
    Test that backtest() raises CostNotConfirmedError before running when
    the strategy fits the estimator more than 50 times and `confirm_cost`
    is not given: a ForecasterDirect refitted in each of 6 folds fits 10
    estimators per training. The error states the cost, the changes that
    lower it, the figure that confirms it and how to run it.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, forecaster="ForecasterDirect")
    cv = TimeSeriesFold(steps=10, initial_train_size=40, refit=True, verbose=False)

    err_msg = re.escape(
        "This backtest is above the threshold of an expensive run (50 estimator "
        "fits or 2000 inference windows), so it needs a confirmation and nothing "
        "ran. ForecasterDirect will be fit 60 times (6 trainings x 10 "
        "estimators). It can take substantial amounts of time. If not feasible, "
        "use an integer `refit` (retrain every n folds), fewer folds (a later "
        "`initial_train_size`, a larger `fold_stride` or `skip_folds`) or "
        "`refit=False` (train once)."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        assistant.backtest(
            data          = df_single,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
        )

    error = exc_info.value
    assert error.code == "invalid_argument"
    assert error.field == "confirm_cost"
    assert error.hint == "Pass `confirm_cost=True` to run it as it is."
    assert error.figure == 60
    assert error.cost == {
        "n_folds": 6, "n_fits": 6, "estimator_fits": 60, "inference_windows": 0
    }
    assert error.description == (
        "ForecasterDirect will be fit 60 times (6 trainings x 10 estimators)."
    )
    assert error.comparison_cost is None


@pytest.mark.parametrize("confirm_cost", [True, 60], ids=["true", "figure"])
def test_backtest_runs_without_warning_when_confirm_cost_confirms_the_cost(
    confirm_cost,
):
    """
    Test that backtest() above the threshold runs, without a
    LongTrainingWarning, when `confirm_cost` is True or the figure of its
    cost (60 estimator fits), and that the explanation states that cost.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, forecaster="ForecasterDirect")
    cv = TimeSeriesFold(steps=10, initial_train_size=40, refit=True, verbose=False)

    with warnings.catch_warnings():
        warnings.simplefilter("error", category=LongTrainingWarning)
        result = assistant.backtest(
            data          = df_single,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
            confirm_cost  = confirm_cost,
        )

    assert result.cv_config["n_fits"] == 6
    assert "(60 fits in all)" in result.explanation


def test_backtest_CostNotConfirmedError_when_confirm_cost_is_another_figure():
    """
    Test that backtest() above the threshold raises CostNotConfirmedError
    when `confirm_cost` is a figure other than that of its cost: 59, given
    for another strategy, does not confirm 60 estimator fits.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, forecaster="ForecasterDirect")
    cv = TimeSeriesFold(steps=10, initial_train_size=40, refit=True, verbose=False)

    err_msg = re.escape(
        "`confirm_cost=59` does not confirm it: the figure of this cost is 60, "
        "so the strategy or the plan changed since that number was given."
    )
    with pytest.raises(CostNotConfirmedError, match=f"{err_msg}$") as exc_info:
        assistant.backtest(
            data          = df_single,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
            confirm_cost  = 59,
        )

    assert exc_info.value.figure == 60


@pytest.mark.parametrize("confirm_cost", [False, 7], ids=["false", "figure"])
def test_backtest_ignores_confirm_cost_below_threshold(confirm_cost):
    """
    Test that backtest() at or below the threshold runs whatever
    `confirm_cost` says, also a figure that is not its cost: a
    ForecasterRecursive refitted in each of 6 folds fits 6 estimators.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    cv = TimeSeriesFold(steps=10, initial_train_size=40, refit=True, verbose=False)

    result = assistant.backtest(
        data          = df_single,
        cv            = cv,
        profile       = profile,
        plan          = plan,
        show_progress = False,
        confirm_cost  = confirm_cost,
    )

    assert result.cv_config["n_fits"] == 6


@pytest.mark.parametrize(
    "confirm_cost, error, err_msg",
    [
        (
            "60",
            InvalidInputTypeError,
            "`confirm_cost` must be True, False or the integer figure of the "
            "cost, got str.",
        ),
        (
            60.0,
            InvalidInputTypeError,
            "`confirm_cost` must be True, False or the integer figure of the "
            "cost, got float.",
        ),
        (
            -1,
            InvalidInputError,
            "`confirm_cost` must be True, False or the integer figure of the "
            "cost (0 or more), got -1.",
        ),
    ],
    ids=["text", "float", "negative"],
)
def test_backtest_InvalidInputError_when_confirm_cost_is_not_valid(
    confirm_cost, error, err_msg
):
    """
    Test that backtest() rejects a `confirm_cost` that is neither a bool nor
    an integer of at least 0 before anything else, also below the
    threshold.
    """
    with pytest.raises(error, match=re.escape(err_msg)) as exc_info:
        assistant.backtest(
            data          = df_single,
            cv            = TimeSeriesFold(steps=10, initial_train_size=40),
            target        = "sales",
            date_column   = "date",
            show_progress = False,
            confirm_cost  = confirm_cost,
        )

    assert exc_info.value.field == "confirm_cost"


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
    the predictions include the bounds. The interval covers far less than
    80 % of this data, which warns.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    with pytest.warns(IntervalCoverageWarning, match="nominal coverage of 80 %"):
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
            "root_mean_squared_error": [7.0],
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


def test_backtest_CostNotConfirmedError_when_foundation_inference_windows_exceed_threshold(
    monkeypatch,
):
    """
    Test that backtest() of a ForecasterFoundation plan, which fits no
    estimator, raises CostNotConfirmedError before running when its
    inference windows (series times folds) exceed the threshold (lowered to
    3 here, 2000 by default): the figure that confirms it is the number of
    windows. The backend is reported installed, so nothing is downloaded.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 3)
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: True
    )
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    err_msg = re.escape(
        "This backtest is above the threshold of an expensive run (50 estimator "
        "fits or 3 inference windows), so it needs a confirmation and nothing "
        "ran. ForecasterFoundation will forecast up to 6 inference windows (1 "
        "series x 6 folds). It can take substantial amounts of time. If not "
        "feasible, use fewer folds (a later `initial_train_size`, a larger "
        "`fold_stride` or `skip_folds`) or fewer series."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        assistant.backtest(
            data          = df_no_exog,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
        )

    assert exc_info.value.figure == 6
    assert exc_info.value.cost == {
        "n_folds": 6, "n_fits": 0, "estimator_fits": 0, "inference_windows": 6
    }


def test_backtest_missing_dependency_before_the_cost_is_checked(monkeypatch):
    """
    Test that backtest() of a ForecasterFoundation plan above the threshold
    of inference windows (lowered to 3) whose backend is not installed
    raises `missing_dependency`, not CostNotConfirmedError: a run that would
    fail does not ask first for a confirmation of its cost.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 3)
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    with pytest.raises(
        InvalidInputError, match=re.escape("chronos-forecasting")
    ) as exc_info:
        assistant.backtest(
            data          = df_no_exog,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
        )

    assert exc_info.value.code == "missing_dependency"


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
    the window of the plan, so the backtest runs. With refit, the series
    'b', with 3 observations in the first training window, is forecast from
    the second fold on, which a warning says: its metrics use 22 of its 23
    folds.
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

    warn_msg = re.escape("('b': in 22 of its 23 folds with values)")
    with pytest.warns(UserWarning, match=warn_msg):
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


def test_backtest_InvalidInputError_when_forecaster_stats_with_skip_folds():
    """
    Test that backtest() rejects, before running, a ForecasterStats plan with
    a cv that skips folds, with `cv` as field: skforecast refits it in every
    fold and rejects any `skip_folds`.
    """
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterStats")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, skip_folds=2, verbose=False)

    err_msg = re.escape(
        "`skip_folds=2` is not allowed for ForecasterStats: skforecast refits "
        "it in every fold and rejects any `skip_folds`, an empty list "
        "included. Use a strategy without `skip_folds`, or another forecaster."
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

    with warnings.catch_warnings():
        # The first fold leaves item_2 out with refit, which a warning says.
        warnings.filterwarnings(
            "ignore", message="Some series were not forecast", category=UserWarning
        )
        result = assistant.backtest(
            data=_items_starting_late(n_values), target="value",
            date_column="date", series_id_column="series", cv=cv,
            show_progress=False,
        )

    assert isinstance(result, BacktestResult)
    assert result.plan.forecaster == "ForecasterRecursiveMultiSeries"
    assert sorted(result.predictions["level"].unique()) == [
        "item_1", "item_2", "item_3"
    ]


def test_backtest_UserWarning_when_long_series_is_left_out_of_some_folds():
    """
    Test that backtest() warns, and says in its explanation, when a series
    is not forecast in some test fold where it has values: item_2 has its
    last 60 values and, with refit, the first fold trains on 20 of them, no
    more than the window of the plan (21). Its metrics, and the average
    across series, use 7 of its 8 folds; skforecast said nothing.
    """
    cv = _long_cv()
    cv.set_params({"refit": True})

    warn_msg = (
        "Some series were not forecast in every test fold where they have "
        "values to evaluate ('item_2': in 7 of its 8 folds with values), so "
        "their metrics, and the average across series, leave the other folds "
        "out. ForecasterRecursiveMultiSeries leaves a series out of a fold when "
        "the training window of the fold has too few of its observations, or "
        "when it cannot predict it from the values before the fold."
    )
    with pytest.warns(UserWarning, match=f"^{re.escape(warn_msg)}$"):
        result = assistant.backtest(
            data=_items_starting_late(60), target="value", date_column="date",
            series_id_column="series", cv=cv, show_progress=False,
        )

    assert result.explanation.endswith(f" {warn_msg}")


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
    plan of the CVResult: its estimator and interval are kept. The interval
    covers far less than 80 % of this data, which warns.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", interval=[0.1, 0.9]
    )
    with pytest.warns(UserWarning, match=INTERVAL_WARNING):
        cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    with pytest.warns(IntervalCoverageWarning, match="nominal coverage of 80 %"):
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


# The `FutureWarning` of skforecast 0.27 for `TimeSeriesFold(differentiation=...)`.
DEPRECATED_DIFFERENTIATION = re.escape("`differentiation` is deprecated")


def test_backtest_output_when_cv_without_differentiation_and_plan_with_it():
    """
    Test that a strategy without a differentiation order backtests a plan
    with one, where it was rejected before: skforecast 0.27 takes the order
    from the window of the forecaster. A strategy built with another order
    (deprecated by skforecast, with a `FutureWarning`) gives the same
    script and metrics, because its order is not read.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, differentiation=1)
    inputs = {
        "data": df_single, "target": "sales", "date_column": "date",
        "profile": profile, "plan": plan, "show_progress": False,
    }
    with pytest.warns(FutureWarning, match=DEPRECATED_DIFFERENTIATION):
        cv_with_order = TimeSeriesFold(
            steps=5, initial_train_size=60, differentiation=2
        )

    result = assistant.backtest(
        **inputs, cv=TimeSeriesFold(steps=5, initial_train_size=60)
    )
    result_with_order = assistant.backtest(**inputs, cv=cv_with_order)

    assert result.plan.forecaster_kwargs["differentiation"] == 1
    assert "differentiation" not in result.cv_config
    assert result_with_order.code == result.code
    pd.testing.assert_frame_equal(result_with_order.metrics, result.metrics)
    pd.testing.assert_frame_equal(
        result_with_order.predictions, result.predictions
    )


def test_backtest_output_when_cv_result_saved_with_differentiation():
    """
    Test that a `CVResult` saved before skforecast 0.27, whose splitter and
    `cv_config` carry the differentiation order of its plan, is accepted and
    its order ignored: the backtest runs without a `FutureWarning` (an
    error in this suite), with the script and metrics of the strategy
    created now, and its `cv_config` without the order.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, differentiation=1)
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)
    # pickle restores the attributes without running `__init__`, so the
    # deprecated order comes back without a warning, as from 0.4.x.
    saved = pickle.loads(pickle.dumps(cv_result))
    saved.cv.differentiation = 1
    saved.cv_config["differentiation"] = 1
    inputs = {
        "data": df_single, "target": "sales", "date_column": "date",
        "profile": profile, "show_progress": False,
    }

    expected = assistant.backtest(**inputs, cv=cv_result)
    result = assistant.backtest(**inputs, cv=saved)

    assert result.plan.forecaster_kwargs["differentiation"] == 1
    assert result.code == expected.code
    assert "differentiation" not in result.cv_config
    pd.testing.assert_frame_equal(result.metrics, expected.metrics)


def test_backtest_output_when_stats_ignores_cv_differentiation():
    """
    Test that ForecasterStats still runs with a strategy built with a
    differentiation order (deprecated by skforecast 0.27, with a
    `FutureWarning`), which it never read.
    """
    assistant = ForecastingAssistant()
    with pytest.warns(FutureWarning, match=DEPRECATED_DIFFERENTIATION):
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


def test_backtest_CostNotConfirmedError_counts_every_series_and_the_incomplete_fold(
    monkeypatch,
):
    """
    Test that the inference windows of a ForecasterFoundation backtest count
    every series and the last fold when it is incomplete: 2 series over 7
    folds (30 test observations in steps of 5 from 68, the last one of 2)
    are 14 windows, stated in the error and in `cv_config`.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 13)
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: True
    )
    targets = ["series_a", "series_b"]
    profile = assistant.profile(data=df_multi_wide, target=targets, date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    cv = TimeSeriesFold(steps=5, initial_train_size=68, verbose=False)

    err_msg = re.escape(
        "ForecasterFoundation will forecast up to 14 inference windows (2 series "
        "x 7 folds)."
    )
    with pytest.raises(CostNotConfirmedError, match=err_msg) as exc_info:
        assistant.backtest(
            data          = df_multi_wide,
            cv            = cv,
            profile       = profile,
            plan          = plan,
            show_progress = False,
        )

    assert exc_info.value.figure == 14
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


def test_backtest_output_when_stats_interval_80_is_narrower_than_95():
    """
    Test that the interval [0.1, 0.9] of ForecasterStats is the 80 % one in
    a backtest, narrower than the 95 % one, by the mean width that
    skforecast measures (`interval_width`). Before skforecast 0.27,
    `predict_interval` ignored `interval` and always returned the 95 %
    interval (skforecast #1416). The intervals of the ARIMA model are
    Gaussian, so the ratio of the widths is z(0.9) / z(0.975). Both cover
    clearly less than their nominal level on these folds (63 % and 83.3 %
    of the 54 predictions), which warns.
    """
    assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=12, initial_train_size=150)

    with pytest.warns(IntervalCoverageWarning, match="only 63 % of the 54"):
        result_80 = assistant.backtest(
            data          = df_h2o,
            target        = "x",
            cv            = cv,
            forecaster    = "ForecasterStats",
            interval      = [0.1, 0.9],
            show_progress = False,
        )
    with pytest.warns(IntervalCoverageWarning, match="only 83.3 % of the 54"):
        result_95 = assistant.backtest(
            data          = df_h2o,
            target        = "x",
            cv            = cv,
            forecaster    = "ForecasterStats",
            interval      = [0.025, 0.975],
            show_progress = False,
        )
    width_80 = result_80.metrics.loc[0, "interval_width"]
    width_95 = result_95.metrics.loc[0, "interval_width"]

    assert width_80 < width_95
    np.testing.assert_allclose(width_80, width_95 * 1.2815516 / 1.9599640, rtol=1e-4)
    # The width comes from the ARIMA fit, which differs between platforms
    # (a relative 4.7e-5 on macOS arm): the tolerance of the ratio above.
    # Since skforecast 0.27, `freeze_params=True` keeps the model selected in
    # the first fit, so the folds after the first one give another width.
    np.testing.assert_allclose(
        result_80.metrics[["coverage", "interval_width"]].to_numpy(),
        [[0.6296296296296297, 0.14169101871061165]],
        rtol=1e-4,
    )
