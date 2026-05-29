"""Script rendering for statistical forecasting (Auto-ARIMA)."""

from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_data_loading,
    _emit_end_train,
    _emit_index_setup,
    _emit_metrics_section,
    _emit_preprocessing_steps,
    _emit_production_note,
    _get_interval_repr,
    _get_metric_imports,
    _get_seasonal_period,
    _get_target_str,
)


def _emit_forecaster_creation_statistical(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """Append ForecasterStats (Auto-ARIMA) construction code."""

    m = _get_seasonal_period(profile.frequency)
    arima_defaults: dict[str, object] = {"order": None, "seasonal_order": None}
    if m is not None:
        arima_defaults["m"] = m
    arima_kwargs = {**arima_defaults, **(plan.estimator_kwargs or {})}
    arima_params = ", ".join(f"{k}={repr(v)}" for k, v in arima_kwargs.items())
    estimator_str = f"Arima({arima_params})"

    lines.append("# Create forecaster (Auto-ARIMA)")
    lines.append("forecaster = ForecasterStats(")
    lines.append(f"    estimator = {estimator_str},")
    lines.append(")")
    lines.append("")


def render_forecast_statistical(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterStats (Auto-ARIMA)."""

    target = _get_target_str(profile)
    exog_columns = profile.exog_columns

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    import_lines.append("import pandas as pd")
    import_lines.extend(_get_metric_imports(plan.metrics_to_compute))
    import_lines.append("from skforecast.stats import Arima")
    import_lines.append("from skforecast.recursive import ForecasterStats")
    import_lines.append("")

    # --- Load data ---
    _emit_data_loading(loading_lines, profile)

    # --- Index setup (runs in both standalone and exec modes) ---
    _emit_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Train/test split ---
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

    # --- Create forecaster ---
    _emit_forecaster_creation_statistical(core_lines, plan, profile)

    # --- Fit & Predict ---
    core_lines.append("# Fit")
    if plan.use_exog and exog_columns:
        core_lines.append(
            f"forecaster.fit(y=data_train[{repr(target)}], "
            f"exog=data_train[exog_features])"
        )
    else:
        core_lines.append(f"forecaster.fit(y=data_train[{repr(target)}])")
    core_lines.append("")

    if plan.interval_method is not None:
        interval_repr = _get_interval_repr(plan)
        core_lines.append("# Predict intervals (native)")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if plan.use_exog and exog_columns:
            predict_kwargs.append(("exog", "data_test[exog_features]"))
        predict_kwargs.append(("interval", interval_repr))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_interval(", predict_kwargs
        )
    else:
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
    _emit_metrics_section(
        core_lines,
        actual_expr=f"data_test[{repr(target)}].iloc[:steps]",
        pred_expr=pred_expr,
        train_expr=f"data_train[{repr(target)}]",
        metrics_to_compute=plan.metrics_to_compute,
    )
    core_lines.append("")
    _emit_production_note(core_lines, use_exog=bool(plan.use_exog and exog_columns))
    core_lines.append("")

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )
