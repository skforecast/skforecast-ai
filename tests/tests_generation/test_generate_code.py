# Unit test generate_code generation

import pytest

from skforecast_ai.generation import generate_code

from .fixtures_generation import (
    plan_direct,
    plan_foundation,
    plan_multi_series,
    plan_recursive_no_exog,
    plan_recursive_no_interval,
    plan_recursive_with_exog,
    plan_statistical,
    profile_direct,
    profile_foundation,
    profile_multi_series,
    profile_recursive_no_exog,
    profile_recursive_with_exog,
    profile_statistical,
)


def test_generate_code_output_when_recursive_single_series_syntax():
    """
    Test generate_code produces syntactically valid Python for a basic
    ForecasterRecursive plan without exogenous variables.
    """
    code = generate_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
        data_path="data.csv",
    )

    compile(code, "<test>", "exec")


def test_generate_code_output_when_recursive_includes_backtest():
    """
    Test generate_code includes a backtesting_forecaster call in the
    generated script.
    """
    code = generate_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert "backtesting_forecaster" in code
    assert "TimeSeriesFold" in code


def test_generate_code_output_when_recursive_with_exog():
    """
    Test generate_code includes exogenous variable handling when
    use_exog=True in the plan.
    """
    code = generate_code(
        plan=plan_recursive_with_exog,
        profile=profile_recursive_with_exog,
    )

    assert "exog" in code
    assert "temperature" in code or "exog_train" in code


def test_generate_code_output_when_direct_includes_steps():
    """
    Test generate_code passes steps= to ForecasterDirect constructor.
    """
    code = generate_code(
        plan=plan_direct,
        profile=profile_direct,
    )

    assert "ForecasterDirect" in code
    assert "steps" in code
    assert (f"steps     = {plan_direct.horizon}" in code
            or f"steps={plan_direct.horizon}" in code)


def test_generate_code_output_when_correct_metric():
    """
    Test generate_code embeds the plan's metric in the backtesting call.
    """
    code = generate_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert plan_recursive_no_exog.metric in code


def test_generate_code_output_when_correct_lags():
    """
    Test generate_code embeds the plan's lags in the forecaster constructor.
    """
    code = generate_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert repr(plan_recursive_no_exog.lags) in code


def test_generate_code_output_when_interval_method_present():
    """
    Test generate_code includes predict_interval when interval_method is set.
    """
    code = generate_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert "predict_interval" in code
    assert "bootstrapping" in code


def test_generate_code_output_when_no_interval_method():
    """
    Test generate_code does NOT include predict_interval when
    interval_method is None.
    """
    code = generate_code(
        plan=plan_recursive_no_interval,
        profile=profile_recursive_no_exog,
    )

    assert "predict_interval" not in code


def test_generate_code_output_when_multi_series_syntax():
    """
    Test generate_code produces syntactically valid Python for a
    multi-series plan.
    """
    code = generate_code(
        plan=plan_multi_series,
        profile=profile_multi_series,
    )

    compile(code, "<test>", "exec")
    assert "ForecasterRecursiveMultiSeries" in code
    assert "backtesting_forecaster_multiseries" in code


def test_generate_code_output_when_statistical_syntax():
    """
    Test generate_code produces syntactically valid Python for a
    statistical model plan.
    """
    code = generate_code(
        plan=plan_statistical,
        profile=profile_statistical,
    )

    compile(code, "<test>", "exec")
    assert "ForecasterStats" in code
    assert "backtesting_stats" in code
    assert "Arima" in code


def test_generate_code_output_when_foundation_syntax():
    """
    Test generate_code produces syntactically valid Python for a
    foundation model plan.
    """
    code = generate_code(
        plan=plan_foundation,
        profile=profile_foundation,
    )

    compile(code, "<test>", "exec")
    assert "ForecasterFoundation" in code
    assert "backtesting_foundation" in code
    assert "FoundationModel" in code


def test_generate_code_ValueError_when_unsupported_task_type():
    """
    Test generate_code raises ValueError for task types without a
    template implementation.
    """
    from skforecast_ai.schemas import DataProfile, ForecastPlan

    profile = DataProfile(
        n_observations         = 365,
        n_series               = 1,
        index_type             = "datetime",
        frequency              = "D",
        target                 = "y",
        inferred_seasonalities = [7],
    )
    plan = ForecastPlan(
        task_type            = "multivariate",
        forecaster           = "ForecasterDirectMultiVariate",
        estimator            = "Ridge",
        horizon              = 10,
        frequency            = "D",
        lags                 = [1, 2, 3],
        metric               = "mean_absolute_error",
        backtesting_strategy = "TimeSeriesFold",
        interval_method      = None,
        use_exog             = False,
        rationale            = "Multivariate forecaster.",
    )

    with pytest.raises(ValueError, match="Unsupported task_type"):
        generate_code(plan=plan, profile=profile)


def test_generate_code_output_when_unknown_estimator_syntax():
    """
    Test generate_code produces syntactically valid Python even when the
    estimator is not in the known imports mapping.
    """
    from skforecast_ai.schemas import DataProfile, ForecastPlan

    profile = DataProfile(
        n_observations         = 365,
        n_series               = 1,
        index_type             = "datetime",
        frequency              = "D",
        target                 = "y",
        inferred_seasonalities = [7],
    )
    plan = ForecastPlan(
        task_type            = "single_series",
        forecaster           = "ForecasterRecursive",
        estimator            = "GradientBoostingRegressor",
        horizon              = 10,
        frequency            = "D",
        lags                 = [1, 2, 3],
        metric               = "mean_absolute_error",
        backtesting_strategy = "TimeSeriesFold",
        interval_method      = None,
        use_exog             = False,
        rationale            = "Unknown estimator test.",
    )

    code = generate_code(plan=plan, profile=profile)

    compile(code, "<test>", "exec")
    assert "GradientBoostingRegressor" in code
    assert "TODO" in code
