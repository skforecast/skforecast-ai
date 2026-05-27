# Integration tests: full profile → plan → generate_cv → backtest workflow
# Tests each supported forecaster type end-to-end.

import ast

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import BacktestResult, ForecastingAssistant

from tests.fixtures_assistant import df_single, df_no_exog, df_multi_long

assistant = ForecastingAssistant()


# =============================================================================
# Tests: ForecasterRecursive (single_series, default estimator)
# =============================================================================
def test_forecaster_recursive_full_workflow_with_exog():
    """
    Full workflow: profile → plan → generate_cv → backtest with
    ForecasterRecursive and exogenous variables. Validates all output
    fields, metric finiteness, and code syntax.
    """
    profile = assistant.profile(
        data=df_single, target="sales", date_column="date"
    )
    plan = assistant.generate_plan(profile, steps=5)
    cv, _ = assistant.generate_cv(profile, plan)

    result = assistant.backtest(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.forecaster == "ForecasterRecursive"
    assert result.plan.task_type == "single_series"
    assert result.cv_config["steps"] == 5
    assert not result.metrics.empty
    assert len(result.predictions) > 0
    assert "backtesting_forecaster" in result.code
    assert "Backtesting completed" in result.explanation
    ast.parse(result.code)

    numeric_metrics = result.metrics.select_dtypes(include="number")
    assert numeric_metrics.notna().all().all()
    assert np.isfinite(numeric_metrics.values).all()


def test_forecaster_recursive_full_workflow_without_exog():
    """
    Full workflow with ForecasterRecursive and no exogenous variables.
    """
    profile = assistant.profile(
        data=df_no_exog, target="sales", date_column="date"
    )
    plan = assistant.generate_plan(profile, steps=5)
    cv, _ = assistant.generate_cv(profile, plan)

    result = assistant.backtest(
        data=df_no_exog,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.forecaster == "ForecasterRecursive"
    assert result.plan.use_exog is False
    assert not result.metrics.empty
    assert len(result.predictions) > 0
    ast.parse(result.code)


# =============================================================================
# Tests: ForecasterDirect (single_series, explicit forecaster override)
# =============================================================================
@pytest.mark.parametrize(
    "steps",
    [5, 10],
    ids=lambda s: f"steps={s}",
)
def test_forecaster_direct_full_workflow(steps):
    """
    Full workflow with ForecasterDirect at different step horizons.
    Verifies cv.steps == plan.steps consistency through the chain.
    """
    profile = assistant.profile(
        data=df_single,
        target="sales",
        date_column="date",
    )
    plan = assistant.generate_plan(
        profile, steps=steps, forecaster="ForecasterDirect"
    )
    cv, _ = assistant.generate_cv(profile, plan)

    assert cv.steps == plan.steps == steps

    result = assistant.backtest(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.forecaster == "ForecasterDirect"
    assert result.cv_config["steps"] == steps
    assert not result.metrics.empty
    assert len(result.predictions) > 0
    assert "backtesting_forecaster" in result.code
    ast.parse(result.code)


# =============================================================================
# Tests: ForecasterRecursiveMultiSeries (multi_series)
# =============================================================================
@pytest.mark.slow
def test_forecaster_recursive_multiseries_full_workflow():
    """
    Full workflow with ForecasterRecursiveMultiSeries from long-format
    multi-series data. Validates predictions contain multiple series.
    """
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.generate_plan(profile, steps=5)
    cv, _ = assistant.generate_cv(profile, plan)

    result = assistant.backtest(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, BacktestResult)
    assert result.plan.forecaster == "ForecasterRecursiveMultiSeries"
    assert result.plan.task_type == "multi_series"
    assert not result.metrics.empty
    assert len(result.predictions) > 0
    assert len(result.predictions.columns) >= 2
    assert "backtesting_forecaster_multiseries" in result.code
    ast.parse(result.code)


# =============================================================================
# Tests: unsupported forecaster types raise NotImplementedError
# =============================================================================
@pytest.mark.parametrize(
    "forecaster, data, target, date_column, series_id_column, match_str",
    [
        (
            "ForecasterDirectMultiVariate",
            df_multi_long,
            "value",
            "date",
            "series_id",
            "multivariate",
        ),
        (
            "ForecasterStats",
            df_single,
            "sales",
            "date",
            None,
            "statistical",
        ),
    ],
    ids=["ForecasterDirectMultiVariate", "ForecasterStats"],
)
def test_backtest_NotImplementedError_when_unsupported_forecaster(
    forecaster, data, target, date_column, series_id_column, match_str
):
    """
    Test that backtest raises NotImplementedError for forecaster types
    not yet supported in the backtesting dispatch.
    """
    profile_kwargs = {
        "data": data,
        "target": target,
        "date_column": date_column,
    }
    if series_id_column:
        profile_kwargs["series_id_column"] = series_id_column

    profile = assistant.profile(**profile_kwargs)
    plan = assistant.generate_plan(profile, steps=5, forecaster=forecaster)
    cv, _ = assistant.generate_cv(profile, plan)

    backtest_kwargs = {
        "data": data,
        "target": target,
        "date_column": date_column,
        "cv": cv,
        "profile": profile,
        "plan": plan,
    }
    if series_id_column:
        backtest_kwargs["series_id_column"] = series_id_column

    with pytest.raises(NotImplementedError, match=match_str):
        assistant.backtest(**backtest_kwargs)


# =============================================================================
# Tests: custom CV parameters flow through the full chain
# =============================================================================
@pytest.mark.parametrize(
    "cv_kwargs, expected_key, expected_value",
    [
        ({"initial_train_size": 80}, "initial_train_size", 80),
        ({"refit": False}, "refit", False),
        ({"fixed_train_size": True}, "fixed_train_size", True),
        ({"gap": 2}, "gap", 2),
    ],
    ids=["initial_train_size=80", "refit=False", "fixed_train_size=True", "gap=2"],
)
def test_cv_kwarg_propagates_to_result(cv_kwargs, expected_key, expected_value):
    """
    Explicit CV kwargs flow through generate_cv → backtest → cv_config.
    """
    profile = assistant.profile(
        data=df_single, target="sales", date_column="date"
    )
    plan = assistant.generate_plan(profile, steps=5)
    cv, _ = assistant.generate_cv(profile, plan, **cv_kwargs)

    result = assistant.backtest(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert result.cv_config[expected_key] == expected_value
