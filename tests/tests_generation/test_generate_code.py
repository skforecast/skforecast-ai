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
    assert (f"steps     = {plan_direct.steps}" in code
            or f"steps={plan_direct.steps}" in code)


def test_generate_code_output_when_correct_metric():
    """
    Test generate_code embeds the default metric in the backtesting call.
    """
    code = generate_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert "mean_absolute_error" in code


def test_generate_code_output_when_correct_lags():
    """
    Test generate_code embeds the plan's lags in the forecaster constructor.
    """
    code = generate_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert repr(plan_recursive_no_exog.forecaster_kwargs["lags"]) in code


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
        n_series               = 1,
        n_observations         = 365,
        target                 = "y",
        index_type             = "datetime",
        frequency              = "D",
    )
    plan = ForecastPlan(
        task_type            = "multivariate",
        forecaster           = "ForecasterDirectMultiVariate",
        estimator            = "Ridge",
        steps              = 10,
        frequency            = "D",
        forecaster_kwargs    = {"lags": [1, 2, 3], "steps": 10, "dropna_from_series": False},
        interval_method      = None,
        use_exog             = False,
        explanation            = "Multivariate forecaster.",
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
        n_series               = 1,
        n_observations         = 365,
        target                 = "y",
        index_type             = "datetime",
        frequency              = "D",
    )
    plan = ForecastPlan(
        task_type            = "single_series",
        forecaster           = "ForecasterRecursive",
        estimator            = "GradientBoostingRegressor",
        steps              = 10,
        frequency            = "D",
        forecaster_kwargs    = {"lags": [1, 2, 3], "dropna_from_series": False},
        interval_method      = None,
        use_exog             = False,
        explanation            = "Unknown estimator test.",
    )

    code = generate_code(plan=plan, profile=profile)

    compile(code, "<test>", "exec")
    assert "GradientBoostingRegressor" in code
    assert "TODO" in code


def test_generate_code_output_when_dropna_from_series_true():
    """
    Test generate_code includes dropna_from_series=True in the forecaster
    constructor when the plan specifies it.
    """
    from skforecast_ai.schemas import DataProfile, ForecastPlan

    profile = DataProfile(
        n_series               = 1,
        n_observations         = 200,
        target                 = "y",
        missing_values         = {"y": 5},
        index_type             = "datetime",
        frequency              = "D",
    )
    plan = ForecastPlan(
        task_type            = "single_series",
        forecaster           = "ForecasterRecursive",
        estimator            = "Ridge",
        steps              = 10,
        frequency            = "D",
        forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": True},
        interval_method      = None,
        use_exog             = False,
        explanation            = "Ridge with missing values.",
    )

    code = generate_code(plan=plan, profile=profile)

    compile(code, "<test>", "exec")
    assert "dropna_from_series = True" in code


def test_generate_code_output_when_dropna_from_series_none():
    """
    Test generate_code does NOT include dropna_from_series in the forecaster
    constructor when the plan has dropna_from_series=None (statistical).
    """
    code = generate_code(
        plan=plan_statistical,
        profile=profile_statistical,
        data_path="data.csv",
    )

    compile(code, "<test>", "exec")
    assert "dropna_from_series" not in code
