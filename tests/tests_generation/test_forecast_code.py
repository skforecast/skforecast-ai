# Unit test forecast_code generation

import pytest

from skforecast_ai import ForecastingAssistant

from .fixtures_generation import (
    plan_direct,
    plan_foundation,
    plan_foundation_custom,
    plan_foundation_multi,
    plan_foundation_with_interval,
    plan_multi_series,
    plan_multi_series_wide,
    plan_multi_series_exog,
    plan_multivariate,
    plan_multivariate_exog,
    plan_recursive_custom_kwargs,
    plan_recursive_differentiation,
    plan_recursive_full,
    plan_recursive_no_exog,
    plan_recursive_no_interval,
    plan_recursive_with_exog,
    plan_statistical,
    plan_statistical_arima_exog,
    plan_statistical_with_interval,
    plan_with_date_column,
    plan_with_preprocessing,
    profile_direct,
    profile_foundation,
    profile_foundation_exog,
    profile_foundation_multi,
    profile_multi_series,
    profile_multi_series_wide,
    profile_multi_series_exog,
    profile_multivariate,
    profile_multivariate_exog,
    profile_recursive_full,
    profile_recursive_no_exog,
    profile_recursive_with_exog,
    profile_statistical,
    profile_statistical_exog,
    profile_needs_preprocessing,
    profile_with_date_column,
)

assistant = ForecastingAssistant()


def forecast_code(plan, profile, data_path="data.csv"):
    """Test helper: call render_code with optional data_path override."""
    if data_path != profile.data_path:
        profile = profile.model_copy(update={"data_path": data_path})
    return assistant.render_code(profile=profile, plan=plan)


def test_forecast_code_output_when_recursive_single_series_syntax():
    """
    Test forecast_code produces syntactically valid Python for a basic
    ForecasterRecursive plan without exogenous variables.
    """
    code = forecast_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
        data_path="data.csv",
    )

    compile(code, "<test>", "exec")


def test_forecast_code_output_when_recursive_with_exog():
    """
    Test forecast_code includes exogenous variable handling when
    use_exog=True in the plan.
    """
    code = forecast_code(
        plan=plan_recursive_with_exog,
        profile=profile_recursive_with_exog,
    )

    assert "exog" in code
    assert "temperature" in code or "exog_features" in code


def test_forecast_code_output_when_direct_includes_steps():
    """
    Test forecast_code passes steps= to ForecasterDirect constructor.
    """
    code = forecast_code(
        plan=plan_direct,
        profile=profile_direct,
    )

    assert "ForecasterDirect" in code
    assert f"steps = {plan_direct.steps}" in code
    assert "= steps," in code


def test_forecast_code_output_when_correct_lags():
    """
    Test forecast_code embeds the plan's lags in the forecaster constructor.
    """
    code = forecast_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert repr(plan_recursive_no_exog.forecaster_kwargs["lags"]) in code


def test_forecast_code_output_when_interval_method_present():
    """
    Test forecast_code includes predict_interval when interval_method is set.
    """
    code = forecast_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    assert "predict_interval" in code
    assert "bootstrapping" in code


def test_forecast_code_output_when_no_interval_method():
    """
    Test forecast_code does NOT include predict_interval when
    interval_method is None.
    """
    code = forecast_code(
        plan=plan_recursive_no_interval,
        profile=profile_recursive_no_exog,
    )

    assert "predict_interval" not in code


def test_forecast_code_output_when_multi_series_syntax():
    """
    Test forecast_code produces syntactically valid Python for a
    multi-series plan.
    """
    code = forecast_code(
        plan=plan_multi_series,
        profile=profile_multi_series,
    )

    compile(code, "<test>", "exec")
    assert "ForecasterRecursiveMultiSeries" in code


def test_forecast_code_output_when_statistical_syntax():
    """
    Test forecast_code produces syntactically valid Python for a
    statistical model plan.
    """
    code = forecast_code(
        plan=plan_statistical,
        profile=profile_statistical,
    )

    compile(code, "<test>", "exec")
    assert "ForecasterStats" in code
    assert "Arima" in code


def test_forecast_code_output_when_foundation_syntax():
    """
    Test forecast_code produces syntactically valid Python for a
    foundation model plan.
    """
    code = forecast_code(
        plan=plan_foundation,
        profile=profile_foundation,
    )

    compile(code, "<test>", "exec")
    assert "ForecasterFoundation" in code
    assert "FoundationModel" in code


def test_forecast_code_output_when_multivariate_syntax():
    """
    Test forecast_code produces syntactically valid Python for a
    multivariate plan (ForecasterDirectMultiVariate).
    """
    code = forecast_code(
        plan=plan_multivariate,
        profile=profile_multivariate,
    )

    compile(code, "<test>", "exec")
    assert "ForecasterDirectMultiVariate" in code
    assert f"'{profile_multivariate.target[0]}'" in code
    assert "level" in code


def test_forecast_code_ValueError_when_unsupported_task_type():
    """
    Test forecast_code raises ValueError for task types without a
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
        task_type            = "single_series",
        forecaster           = "ForecasterRecursive",
        estimator            = "LGBMRegressor",
        steps              = 10,
        frequency            = "D",
        forecaster_kwargs    = {"lags": [1, 2, 3]},
        interval_method      = None,
        use_exog             = False,
        explanation            = "Dummy.",
    )
    # Manually set an invalid task_type to test the error path
    plan.task_type = "unsupported_type"

    with pytest.raises(ValueError, match="Unsupported task_type"):
        forecast_code(plan=plan, profile=profile)


def test_forecast_code_output_when_unknown_estimator_syntax():
    """
    Test forecast_code produces syntactically valid Python even when the
    estimator is not in the known imports mapping.
    """
    from skforecast_ai.schemas import DataProfile, ForecastPlan

    profile = DataProfile(
        n_series               = 1,
        n_observations         = 365,
        target                 = "y",
        index_type             = "datetime",
        frequency              = "D",
        end_train              = "2024-10-01",
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

    code = forecast_code(plan=plan, profile=profile)

    compile(code, "<test>", "exec")
    assert "GradientBoostingRegressor" in code
    assert "TODO" in code


def test_forecast_code_output_when_dropna_from_series_true():
    """
    Test forecast_code includes dropna_from_series=True in the forecaster
    constructor when the plan specifies it.
    """
    from skforecast_ai.schemas import DataProfile, ForecastPlan

    profile = DataProfile(
        n_series               = 1,
        n_observations         = 200,
        target                 = "y",
        missing_target         = {"y": 5},
        index_type             = "datetime",
        frequency              = "D",
        end_train              = "2024-10-01",
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

    code = forecast_code(plan=plan, profile=profile)

    compile(code, "<test>", "exec")
    assert "dropna_from_series = True" in code


def test_forecast_code_output_when_dropna_from_series_none():
    """
    Test forecast_code does NOT include dropna_from_series in the forecaster
    constructor when the plan has dropna_from_series=None (statistical).
    """
    code = forecast_code(
        plan=plan_statistical,
        profile=profile_statistical,
        data_path="data.csv",
    )

    compile(code, "<test>", "exec")
    assert "dropna_from_series" not in code


# ─────────────────────────────────────────────────────────────────────
# New tests: window_features, categorical, transformers, preprocessing
# ─────────────────────────────────────────────────────────────────────

def test_forecast_code_output_when_window_features_present():
    """
    Test forecast_code includes RollingFeatures import and instantiation
    when window_features are in the plan.
    """
    code = forecast_code(
        plan=plan_recursive_full,
        profile=profile_recursive_full,
    )

    compile(code, "<test>", "exec")
    assert "from skforecast.preprocessing import RollingFeatures" in code
    assert "RollingFeatures(" in code
    assert "window_features" in code


def test_forecast_code_output_when_categorical_features_present():
    """
    Test forecast_code includes categorical_features='auto' in the
    forecaster constructor when specified in kwargs.
    """
    code = forecast_code(
        plan=plan_recursive_full,
        profile=profile_recursive_full,
    )

    compile(code, "<test>", "exec")
    assert "categorical_features = 'auto'" in code


def test_forecast_code_output_when_transformer_exog_with_categoricals():
    """
    Test forecast_code generates a ColumnTransformer (not bare
    StandardScaler) when both numeric and categorical exog exist.
    """
    code = forecast_code(
        plan=plan_recursive_full,
        profile=profile_recursive_full,
    )

    compile(code, "<test>", "exec")
    assert "make_column_transformer" in code
    assert "remainder='passthrough'" in code
    assert "StandardScaler()" in code


def test_forecast_code_output_when_transformer_y_present():
    """
    Test forecast_code includes transformer_y = StandardScaler() when
    the plan specifies a target transformer.
    """
    code = forecast_code(
        plan=plan_recursive_full,
        profile=profile_recursive_full,
    )

    assert "transformer_y" in code
    assert "= StandardScaler()," in code


def test_forecast_code_output_when_custom_interval_used():
    """
    Test forecast_code uses the plan's interval values instead of
    hardcoded [10, 90].
    """
    code = forecast_code(
        plan=plan_recursive_full,
        profile=profile_recursive_full,
    )

    assert "[5, 95]" in code
    assert "[10, 90]" not in code


def test_forecast_code_output_when_multi_series_wide_format():
    """
    Test forecast_code handles wide-format multi-series data without
    pivot_table.
    """
    code = forecast_code(
        plan=plan_multi_series_wide,
        profile=profile_multi_series_wide,
    )

    compile(code, "<test>", "exec")
    assert "pivot_table" not in code
    assert "series_dict" in code
    assert ".to_dict('series')" in code


def test_forecast_code_output_when_multi_series_long_format():
    """
    Test forecast_code uses reshape_series_long_to_dict for long-format
    multi-series data.
    """
    code = forecast_code(
        plan=plan_multi_series,
        profile=profile_multi_series,
    )

    compile(code, "<test>", "exec")
    assert "reshape_series_long_to_dict" in code
    assert "series_dict" in code


def test_forecast_code_output_when_multi_series_with_exog():
    """
    Test forecast_code includes exog handling in multi-series template.
    """
    code = forecast_code(
        plan=plan_multi_series_exog,
        profile=profile_multi_series_exog,
    )

    compile(code, "<test>", "exec")
    assert "exog_dict" in code
    assert "reshape_exog_long_to_dict" in code
    assert "forecaster.fit(series=series_dict_train, exog=exog_dict_train)" in code


def test_forecast_code_output_when_statistical_correct_imports():
    """
    Test forecast_code uses correct import paths for ForecasterStats.
    """
    code = forecast_code(
        plan=plan_statistical,
        profile=profile_statistical,
    )

    assert "from skforecast.recursive import ForecasterStats" in code
    assert "from skforecast.stats import Arima" in code


def test_forecast_code_output_when_statistical_no_intervals_by_default():
    """
    Test forecast_code does NOT include predict_interval for statistical
    template when interval_method is None.
    """
    code = forecast_code(
        plan=plan_statistical,
        profile=profile_statistical,
    )

    assert "predict_interval" not in code


def test_forecast_code_output_when_statistical_with_intervals():
    """
    Test forecast_code includes predict_interval for statistical
    template when interval_method is set.
    """
    code = forecast_code(
        plan=plan_statistical_with_interval,
        profile=profile_statistical,
    )

    compile(code, "<test>", "exec")
    assert "predict_interval" in code
    assert "[10, 90]" in code


def test_forecast_code_output_when_foundation_no_quantiles_by_default():
    """
    Test forecast_code does NOT include predict_quantiles for foundation
    template when interval_method is None.
    """
    code = forecast_code(
        plan=plan_foundation,
        profile=profile_foundation,
    )

    assert "predict_quantiles" not in code


def test_forecast_code_output_when_foundation_with_quantiles():
    """
    Test forecast_code includes predict_quantiles for foundation
    template when interval_method is set.
    """
    code = forecast_code(
        plan=plan_foundation_with_interval,
        profile=profile_foundation,
    )

    compile(code, "<test>", "exec")
    assert "predict_quantiles" in code


def test_forecast_code_output_when_preprocessing_steps_emitted():
    """
    Test forecast_code includes preprocessing code from
    plan.preprocessing_steps and deterministic loading block.
    """
    code = forecast_code(
        plan=plan_with_preprocessing,
        profile=profile_needs_preprocessing,
    )

    compile(code, "<test>", "exec")
    # Deterministic loading emits sort_index and asfreq
    assert "data = data.asfreq('D')" in code
    assert "data = data.sort_index()" in code
    # Preprocessing step emits drop_duplicates
    assert "data = data[~data.index.duplicated(keep='first')]" in code


def test_forecast_code_output_when_multi_series_exog_categorical():
    """
    Test forecast_code handles categorical features and ColumnTransformer
    in multi-series template.
    """
    code = forecast_code(
        plan=plan_multi_series_exog,
        profile=profile_multi_series_exog,
    )

    compile(code, "<test>", "exec")
    assert "categorical_features = 'auto'" in code
    assert "make_column_transformer" in code


# ─────────────────────────────────────────────────────────────────────
# Statistical: Auto-ARIMA with exog
# ─────────────────────────────────────────────────────────────────────


def test_forecast_code_output_when_statistical_arima_with_exog():
    """
    Test forecast_code produces valid code for Auto-ARIMA with exog.
    """
    code = forecast_code(
        plan=plan_statistical_arima_exog,
        profile=profile_statistical_exog,
    )

    compile(code, "<test>", "exec")
    assert "Arima" in code
    assert "order=None" in code
    assert "seasonal_order=None" in code
    assert "exog_features" in code
    assert "data_train[exog_features]" in code
    assert "m=12" in code


def test_forecast_code_output_when_statistical_exog_in_predict():
    """
    Test forecast_code passes exog to predict for statistical.
    """
    code = forecast_code(
        plan=plan_statistical_arima_exog,
        profile=profile_statistical_exog,
    )

    assert "data_test[exog_features]" in code


def test_forecast_code_output_when_statistical_interval_with_exog():
    """
    Test forecast_code includes exog in predict_interval for statistical.
    """
    code = forecast_code(
        plan=plan_statistical_arima_exog,
        profile=profile_statistical_exog,
    )

    assert "predict_interval" in code
    assert "exog" in code.split("predict_interval")[1]


# ─────────────────────────────────────────────────────────────────────
# Multivariate: exog
# ─────────────────────────────────────────────────────────────────────


def test_forecast_code_output_when_multivariate_with_exog():
    """
    Test forecast_code handles exog in multivariate template.
    """
    code = forecast_code(
        plan=plan_multivariate_exog,
        profile=profile_multivariate_exog,
    )

    compile(code, "<test>", "exec")
    assert "series_cols" in code
    assert "exog_features" in code
    assert "data_train[series_cols]" in code
    assert "data_train[exog_features]" in code
    assert "data_test[exog_features]" in code


# ─────────────────────────────────────────────────────────────────────
# Foundation: model_id, exog, multi-series, quantiles
# ─────────────────────────────────────────────────────────────────────


def test_forecast_code_output_when_foundation_custom_model_id():
    """
    Test forecast_code uses custom model_id from estimator_kwargs.
    """
    code = forecast_code(
        plan=plan_foundation_custom,
        profile=profile_foundation_exog,
    )

    compile(code, "<test>", "exec")
    assert "autogluon/chronos-2-base" in code
    assert "context_length = 4096" in code


def test_forecast_code_output_when_foundation_with_exog():
    """
    Test forecast_code includes exog in foundation template fit/predict.
    """
    code = forecast_code(
        plan=plan_foundation_custom,
        profile=profile_foundation_exog,
    )

    assert "exog=exog" in code or "exog = exog" in code
    assert "temperature" in code


def test_forecast_code_output_when_foundation_multi_series():
    """
    Test forecast_code handles multi-series in foundation template.
    """
    code = forecast_code(
        plan=plan_foundation_multi,
        profile=profile_foundation_multi,
    )

    compile(code, "<test>", "exec")
    assert "series_a" in code
    assert "levels=" in code


def test_forecast_code_output_when_foundation_quantiles_from_interval():
    """
    Test forecast_code derives quantiles from plan.interval for foundation.
    """
    code = forecast_code(
        plan=plan_foundation_custom,
        profile=profile_foundation_exog,
    )

    assert "predict_quantiles" in code
    assert "0.2" in code  # 20/100
    assert "0.8" in code  # 80/100


# ─────────────────────────────────────────────────────────────────────
# Differentiation
# ─────────────────────────────────────────────────────────────────────


def test_forecast_code_output_when_recursive_with_differentiation():
    """
    Test forecast_code includes differentiation param in forecaster constructor.
    """
    code = forecast_code(
        plan=plan_recursive_differentiation,
        profile=profile_recursive_no_exog,
    )

    compile(code, "<test>", "exec")
    assert "differentiation" in code
    assert "= 1," in code


# ─────────────────────────────────────────────────────────────────────
# Data loading: date_column scenarios
# ─────────────────────────────────────────────────────────────────────


def test_forecast_code_output_when_date_column_present():
    """
    Test forecast_code emits to_datetime + set_index when date_column is set.
    """
    code = forecast_code(
        plan=plan_with_date_column,
        profile=profile_with_date_column,
    )

    compile(code, "<test>", "exec")
    assert "pd.to_datetime(data['datetime'])" in code
    assert "data = data.set_index('datetime')" in code
    assert "data = data.asfreq('D')" in code
    assert "data = data.sort_index()" in code
    # Should NOT use index_col=0
    assert "index_col=0" not in code


def test_forecast_code_output_when_no_date_column():
    """
    Test forecast_code emits index_col=0, parse_dates=True when no date_column.
    """
    code = forecast_code(
        plan=plan_recursive_no_exog,
        profile=profile_recursive_no_exog,
    )

    compile(code, "<test>", "exec")
    assert "index_col=0, parse_dates=True" in code
    assert "data = data.asfreq('D')" in code
    assert "data = data.sort_index()" in code
    assert "pd.to_datetime" not in code


def test_forecast_code_output_when_multi_series_long_uses_sort_values():
    """
    Test forecast_code uses sort_values for long-format multi-series
    (no set_index since reshape functions expect date as column).
    """
    code = forecast_code(
        plan=plan_multi_series,
        profile=profile_multi_series,
    )

    compile(code, "<test>", "exec")
    assert "pd.to_datetime(data['date'])" in code
    assert "data = data.sort_values('date')" in code
    assert "set_index" not in code
    assert "reshape_series_long_to_dict" in code


def test_forecast_code_output_when_custom_estimator_kwargs():
    """
    Test forecast_code renders user-provided estimator_kwargs merged
    with defaults in the estimator constructor call.
    """
    code = forecast_code(
        plan=plan_recursive_custom_kwargs,
        profile=profile_recursive_no_exog,
    )

    compile(code, "<test>", "exec")
    assert "n_estimators=200" in code
    assert "learning_rate=0.05" in code
    assert "random_state=123" in code
    assert "verbose=-1" in code


def test_forecast_code_output_when_custom_estimator_kwargs_override_default():
    """
    Test user kwargs override built-in defaults (e.g. random_state).
    """
    plan = plan_recursive_custom_kwargs.model_copy(
        update={"estimator_kwargs": {"random_state": 42}}
    )
    code = forecast_code(
        plan=plan,
        profile=profile_recursive_no_exog,
    )

    compile(code, "<test>", "exec")
    assert "random_state=42" in code
    assert "random_state=123" not in code


# ─────────────────────────────────────────────────────────────────────
# Backtesting code generation: multi-series and multivariate
# ─────────────────────────────────────────────────────────────────────


class _MockCV:
    """Minimal mock of TimeSeriesFold for code generation tests."""

    def __init__(
        self,
        steps=14,
        initial_train_size=200,
        refit=False,
        fixed_train_size=True,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        differentiation=None,
    ):
        self.steps = steps
        self.initial_train_size = initial_train_size
        self.refit = refit
        self.fixed_train_size = fixed_train_size
        self.gap = gap
        self.fold_stride = fold_stride
        self.skip_folds = skip_folds
        self.allow_incomplete_fold = allow_incomplete_fold
        self.differentiation = differentiation


def test_backtesting_code_output_when_multi_series_long_syntax():
    """
    Test backtesting code generation produces syntactically valid Python
    for ForecasterRecursiveMultiSeries with long-format data.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_multi_series,
    )

    cv = _MockCV(steps=14, initial_train_size=200)
    result = _template_backtesting_multi_series(
        plan=plan_multi_series, profile=profile_multi_series, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "ForecasterRecursiveMultiSeries" in result.core
    assert "backtesting_forecaster_multiseries" in result.imports
    assert "TimeSeriesFold" in result.imports
    assert "reshape_series_long_to_dict" in result.core
    assert "series_dict" in result.core


def test_backtesting_code_output_when_multi_series_wide_syntax():
    """
    Test backtesting code generation produces syntactically valid Python
    for ForecasterRecursiveMultiSeries with wide-format data.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_multi_series,
    )

    cv = _MockCV(steps=14, initial_train_size=200)
    result = _template_backtesting_multi_series(
        plan=plan_multi_series_wide, profile=profile_multi_series_wide, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "ForecasterRecursiveMultiSeries" in result.core
    assert "reshape_series_long_to_dict" not in result.core
    assert "series_a" in result.core


def test_backtesting_code_output_when_multi_series_exog_syntax():
    """
    Test backtesting code generation produces syntactically valid Python
    for ForecasterRecursiveMultiSeries with exog and categoricals.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_multi_series,
    )

    cv = _MockCV(steps=7, initial_train_size=250)
    result = _template_backtesting_multi_series(
        plan=plan_multi_series_exog, profile=profile_multi_series_exog, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "reshape_exog_long_to_dict" in result.core
    assert "exog_dict" in result.core
    assert "categorical_features = 'auto'" in result.core
    assert "make_column_transformer" in result.core


def test_backtesting_code_output_when_multivariate_syntax():
    """
    Test backtesting code generation produces syntactically valid Python
    for ForecasterDirectMultiVariate.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_multivariate,
    )

    cv = _MockCV(steps=10, initial_train_size=300)
    result = _template_backtesting_multivariate(
        plan=plan_multivariate, profile=profile_multivariate, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "ForecasterDirectMultiVariate" in result.core
    assert "backtesting_forecaster_multiseries" in result.imports
    assert "level" in result.core


def test_backtesting_code_output_when_foundation_syntax():
    """
    Test backtesting code generation produces syntactically valid Python
    for ForecasterFoundation without quantiles.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_foundation,
    )

    cv = _MockCV(steps=30, initial_train_size=300)
    result = _template_backtesting_foundation(
        plan=plan_foundation, profile=profile_foundation, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "ForecasterFoundation" in result.core
    assert "FoundationModel" in result.core
    assert "backtesting_foundation" in result.imports
    assert "quantiles" not in result.core


def test_backtesting_code_output_when_foundation_with_quantiles_syntax():
    """
    Test backtesting code generation includes quantiles when
    interval_method is set for foundation models.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_foundation,
    )

    cv = _MockCV(steps=30, initial_train_size=300)
    result = _template_backtesting_foundation(
        plan=plan_foundation_with_interval, profile=profile_foundation, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "quantiles" in result.core
    assert "0.1" in result.core
    assert "0.5" in result.core
    assert "0.9" in result.core


def test_backtesting_code_output_when_foundation_multi_series_syntax():
    """
    Test backtesting code generation includes levels for multi-series
    foundation models.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_foundation,
    )

    cv = _MockCV(steps=14, initial_train_size=300)
    result = _template_backtesting_foundation(
        plan=plan_foundation_multi, profile=profile_foundation_multi, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "levels" in result.core
    assert "series_a" in result.core


def test_backtesting_code_output_when_statistical_syntax():
    """
    Test backtesting code generation produces syntactically valid Python
    for ForecasterStats without exog or intervals.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_statistical,
    )

    cv = _MockCV(steps=30, initial_train_size=300)
    result = _template_backtesting_statistical(
        plan=plan_statistical, profile=profile_statistical, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "ForecasterStats" in result.core
    assert "Arima" in result.core
    assert "backtesting_stats" in result.imports
    assert "freeze_params" in result.core
    assert "interval" not in result.core


def test_backtesting_code_output_when_statistical_with_interval_syntax():
    """
    Test backtesting code generation includes interval parameter when
    interval_method is set for statistical models.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_statistical,
    )

    cv = _MockCV(steps=30, initial_train_size=300)
    result = _template_backtesting_statistical(
        plan=plan_statistical_with_interval, profile=profile_statistical, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "interval" in result.core
    assert "[10, 90]" in result.core
    assert "freeze_params" in result.core


def test_backtesting_code_output_when_statistical_with_exog_syntax():
    """
    Test backtesting code generation includes exog for statistical models
    when use_exog is True.
    """
    from skforecast_ai.generation.backtesting import (
        _template_backtesting_statistical,
    )

    cv = _MockCV(steps=12, initial_train_size=300)
    result = _template_backtesting_statistical(
        plan=plan_statistical_arima_exog, profile=profile_statistical_exog, cv=cv
    )

    compile(result.full_script, "<test>", "exec")
    assert "exog" in result.core
    assert "temperature" in result.core
    assert "interval" in result.core
