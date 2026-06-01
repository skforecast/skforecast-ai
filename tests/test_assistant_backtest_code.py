# Unit test backtest_code ForecastingAssistant

import re

import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import CodeGenerationResult, ForecastingAssistant

from tests.fixtures_assistant import df_single, df_multi_long, df_no_exog

assistant = ForecastingAssistant()


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_backtest_code_ValueError_when_cv_steps_differs_from_plan_steps():
    """
    Test that backtest_code() raises ValueError when cv.steps != plan.steps
    and plan is explicitly provided.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    err_msg = re.escape("cv.steps (5) does not match plan.steps (10)")
    with pytest.raises(ValueError, match=err_msg):
        assistant.backtest_code(
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
def test_backtest_code_output_when_single_series():
    """
    Test that backtest_code() returns a CodeGenerationResult with valid
    backtesting code for a single-series dataset.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv, _ = assistant.create_cv(profile, plan)

    result = assistant.backtest_code(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert result.profile is not None
    assert result.plan is not None
    assert result.plan.steps == 5
    assert "backtesting_forecaster" in result.code
    assert "TimeSeriesFold" in result.code
    assert "skforecast" in result.code


def test_backtest_code_output_when_multi_series():
    """
    Test that backtest_code() generates code containing the multi-series
    backtesting call for a long-format multi-series dataset.
    """
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)
    cv, _ = assistant.create_cv(profile, plan)

    result = assistant.backtest_code(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, CodeGenerationResult)
    assert "backtesting_forecaster_multiseries" in result.code
    assert "ForecasterRecursiveMultiSeries" in result.code


def test_backtest_code_output_when_no_profile_or_plan():
    """
    Test that backtest_code() auto-generates profile and plan when not
    provided.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    result = assistant.backtest_code(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
    )

    assert isinstance(result, CodeGenerationResult)
    assert result.plan.steps == 5
    assert "backtesting_forecaster" in result.code


def test_backtest_code_output_when_no_exog():
    """
    Test that backtest_code() works correctly for data without exogenous
    variables.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    result = assistant.backtest_code(
        data=df_no_exog,
        target="sales",
        date_column="date",
        cv=cv,
    )

    assert isinstance(result, CodeGenerationResult)
    assert result.plan.use_exog is False
    assert "backtesting_forecaster" in result.code


def test_backtest_code_contains_cv_configuration():
    """
    Test that the generated code includes TimeSeriesFold configuration
    matching the provided cv object.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(
        steps=5, initial_train_size=70, refit=False, verbose=False
    )

    result = assistant.backtest_code(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert "initial_train_size" in result.code
    assert "refit" in result.code
