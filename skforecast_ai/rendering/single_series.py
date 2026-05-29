"""Script rendering for single-series forecasting."""

from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_data_loading,
    _emit_end_train,
    _emit_index_setup,
    _emit_metrics_section,
    _emit_preprocessing_steps,
    _emit_production_note,
    _emit_transformer_exog,
    _emit_window_features,
    _get_estimator_constructor,
    _get_estimator_import,
    _get_interval_repr,
    _get_metric_imports,
    _get_target_str,
    _needs_column_transformer,
)


def _emit_forecaster_creation_single(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """Append ForecasterRecursive/ForecasterDirect construction code."""

    is_direct = plan.forecaster == "ForecasterDirect"
    forecaster_class = plan.forecaster
    estimator_str = _get_estimator_constructor(plan.estimator, plan.estimator_kwargs)

    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags")
    dropna = kwargs.get("dropna_from_series")
    differentiation = kwargs.get("differentiation")
    transformer_y = kwargs.get("transformer_y")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")
    categorical_features = kwargs.get("categorical_features")

    exog_columns = profile.exog_columns

    lines.append("# Create forecaster")
    forecaster_kwargs: list[tuple[str, str]] = []

    forecaster_kwargs.append(("estimator", estimator_str))
    if is_direct:
        forecaster_kwargs.append(("steps", str(plan.steps)))
    forecaster_kwargs.append(("lags", str(lags)))

    if window_features:
        forecaster_kwargs.append(("window_features", "window_features"))
    if transformer_y is not None:
        forecaster_kwargs.append(("transformer_y", f"{transformer_y}()"))
    if transformer_exog is not None and plan.use_exog and exog_columns:
        forecaster_kwargs.append(("transformer_exog", "transformer_exog"))
    if categorical_features is not None:
        forecaster_kwargs.append(("categorical_features", f"'{categorical_features}'"))
    if differentiation is not None:
        forecaster_kwargs.append(("differentiation", str(differentiation)))
    if dropna is not None:
        forecaster_kwargs.append(("dropna_from_series", str(dropna)))

    _emit_aligned_kwargs(
        lines,
        f"forecaster = {forecaster_class}(",
        forecaster_kwargs,
    )
    lines.append("")


def render_forecast_single_series(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterRecursive or ForecasterDirect."""

    is_direct = plan.forecaster == "ForecasterDirect"
    forecaster_module = "direct" if is_direct else "recursive"
    forecaster_class = plan.forecaster
    estimator_import = _get_estimator_import(plan.estimator)
    target = _get_target_str(profile)

    kwargs = plan.forecaster_kwargs
    transformer_y = kwargs.get("transformer_y")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    import_lines.append("import pandas as pd")
    if transformer_y or transformer_exog:
        import_lines.append("from sklearn.preprocessing import StandardScaler")
    if transformer_exog and _needs_column_transformer(profile):
        import_lines.append("from sklearn.compose import make_column_transformer")
    import_lines.extend(_get_metric_imports(plan.metrics_to_compute))
    import_lines.append(estimator_import)
    if window_features:
        import_lines.append("from skforecast.preprocessing import RollingFeatures")
    import_lines.append(f"from skforecast.{forecaster_module} import {forecaster_class}")
    import_lines.append("")

    # --- Load data ---
    _emit_data_loading(loading_lines, profile)

    # --- Index setup (runs in both standalone and exec modes) ---
    _emit_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Train/test split ---
    exog_columns = profile.exog_columns
    core_lines.append("# Train/test split")
    _emit_end_train(core_lines, profile)
    core_lines.append("data_train = data.loc[:end_train]")
    core_lines.append("data_test  = data.loc[data.index > end_train]")
    if plan.use_exog and exog_columns:
        exog_cols_repr = repr(exog_columns)
        core_lines.append(f"exog_features = {exog_cols_repr}")
    core_lines.append("")
    core_lines.append("print(")
    core_lines.append(
        '    f"Train dates : {data_train.index.min()} --- '
        '{data_train.index.max()}  (n={len(data_train)})"'
    )
    core_lines.append(")")
    core_lines.append("print(")
    core_lines.append(
        '    f"Test dates  : {data_test.index.min()} --- '
        '{data_test.index.max()}  (n={len(data_test)})"'
    )
    core_lines.append(")")
    core_lines.append("")

    # --- Window features ---
    if window_features:
        _emit_window_features(core_lines, window_features)
        core_lines.append("")

    # --- Transformer exog ---
    if transformer_exog and plan.use_exog and exog_columns:
        _emit_transformer_exog(core_lines, transformer_exog, profile)

    # --- Create forecaster ---
    _emit_forecaster_creation_single(core_lines, plan, profile)

    # --- Fit & Predict ---
    if plan.interval_method is not None:
        interval_repr = _get_interval_repr(plan)
        core_lines.append("# Fit")
        fit_kwargs: list[tuple[str, str]] = []
        fit_kwargs.append(("y", f"data_train[{repr(target)}]"))
        if plan.use_exog and exog_columns:
            fit_kwargs.append(("exog", "data_train[exog_features]"))
        fit_kwargs.append(("store_in_sample_residuals", "True"))
        _emit_aligned_kwargs(core_lines, "forecaster.fit(", fit_kwargs)
        core_lines.append("")

        core_lines.append("# Predict intervals")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if plan.use_exog and exog_columns:
            predict_kwargs.append(("exog", "data_test[exog_features]"))
        predict_kwargs.append(("method", f"'{plan.interval_method}'"))
        predict_kwargs.append(("interval", interval_repr))
        _emit_aligned_kwargs(core_lines, "predictions = forecaster.predict_interval(", predict_kwargs)
    else:
        core_lines.append("# Fit")
        if plan.use_exog and exog_columns:
            core_lines.append(
                f"forecaster.fit(y=data_train[{repr(target)}], "
                f"exog=data_train[exog_features])"
            )
        else:
            core_lines.append(f"forecaster.fit(y=data_train[{repr(target)}])")
        core_lines.append("")
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        if plan.use_exog and exog_columns:
            core_lines.append(
                "predictions = forecaster.predict("
                "steps=steps, exog=data_test[exog_features])"
            )
        else:
            core_lines.append("predictions = forecaster.predict(steps=steps)")
    core_lines.append("print(predictions)")
    core_lines.append("")

    pred_expr = "predictions['pred']" if plan.interval_method else "predictions"

    # --- Metrics ---
    _emit_metrics_section(
        core_lines,
        actual_expr=f"data_test[{repr(target)}].iloc[:steps]",
        pred_expr=pred_expr,
        train_expr=f"data_train[{repr(target)}]",
        metrics_to_compute=plan.metrics_to_compute,
    )
    core_lines.append("")

    # --- Production note ---
    _emit_production_note(core_lines, use_exog=bool(plan.use_exog and exog_columns))
    core_lines.append("")

    return RenderedScript(
        imports      = "\n".join(import_lines),
        data_loading = "\n".join(loading_lines),
        core         = "\n".join(core_lines),
    )
