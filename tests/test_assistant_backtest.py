# Unit test backtest ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import IgnoredArgumentWarning
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import BacktestResult, ForecastingAssistant

from tests.fixtures_assistant import df_single, df_no_exog

assistant = ForecastingAssistant()


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
