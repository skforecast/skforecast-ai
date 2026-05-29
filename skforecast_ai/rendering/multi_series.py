"""Script rendering for multi-series and multivariate forecasting."""

from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_data_loading,
    _emit_end_train,
    _emit_index_setup,
    _emit_metrics_section,
    _emit_metrics_section_multiseries,
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


# ─────────────────────────────────────────────────────────────────────
# Helper: forecaster creation for multi-series / multivariate
# ─────────────────────────────────────────────────────────────────────

def _emit_forecaster_creation_multi(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
    *,
    forecaster_class: str,
    use_exog: bool,
) -> None:
    """Emit the forecaster instantiation block for multi-series/multivariate."""

    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags")
    dropna = kwargs.get("dropna_from_series")
    differentiation = kwargs.get("differentiation")
    transformer_series = kwargs.get("transformer_series")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")
    categorical_features = kwargs.get("categorical_features")

    lines.append("# Create forecaster")
    estimator_str = _get_estimator_constructor(plan.estimator, plan.estimator_kwargs)

    forecaster_kwargs: list[tuple[str, str]] = []
    forecaster_kwargs.append(("estimator", estimator_str))
    if forecaster_class == "ForecasterDirectMultiVariate":
        level = _get_target_str(profile)
        forecaster_kwargs.append(("level", repr(level)))
        forecaster_kwargs.append(("steps", str(plan.steps)))
    forecaster_kwargs.append(("lags", str(lags)))
    if forecaster_class == "ForecasterRecursiveMultiSeries":
        encoding = kwargs.get("encoding", "ordinal")
        forecaster_kwargs.append(("encoding", f"'{encoding}'"))
    
    if window_features:
        forecaster_kwargs.append(("window_features", "window_features"))
    if transformer_series is not None:
        forecaster_kwargs.append(("transformer_series", f"{transformer_series}()"))
    if transformer_exog is not None and use_exog:
        forecaster_kwargs.append(("transformer_exog", "transformer_exog"))
    if categorical_features is not None:
        if forecaster_class == "ForecasterRecursiveMultiSeries" or use_exog:
            forecaster_kwargs.append(
                ("categorical_features", f"'{categorical_features}'")
            )
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


# ─────────────────────────────────────────────────────────────────────
# Template: multi_series
# ─────────────────────────────────────────────────────────────────────

def render_forecast_multi_series(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterRecursiveMultiSeries."""

    estimator_import = _get_estimator_import(plan.estimator)

    kwargs = plan.forecaster_kwargs
    transformer_series = kwargs.get("transformer_series")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    is_wide = profile.data_format == "wide"
    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "date"

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    import_lines.append("import pandas as pd")
    if transformer_series or transformer_exog:
        import_lines.append("from sklearn.preprocessing import StandardScaler")
    if transformer_exog and _needs_column_transformer(profile):
        import_lines.append("from sklearn.compose import make_column_transformer")
    import_lines.extend(_get_metric_imports(plan.metrics_to_compute))
    import_lines.append(estimator_import)
    preprocessing_imports: list[str] = []
    if window_features:
        preprocessing_imports.append("RollingFeatures")
    if not is_wide:
        preprocessing_imports.append("reshape_series_long_to_dict")
        if plan.use_exog and profile.exog_columns:
            preprocessing_imports.append("reshape_exog_long_to_dict")
    if preprocessing_imports:
        import_lines.append(
            "from skforecast.preprocessing import "
            + ", ".join(preprocessing_imports)
        )
    import_lines.append("from skforecast.recursive import ForecasterRecursiveMultiSeries")
    import_lines.append("")

    # --- Load data ---
    if is_wide:
        _emit_data_loading(loading_lines, profile)
    else:
        _emit_data_loading(loading_lines, profile, long_format=True)

    # --- Index setup (runs in both standalone and exec modes) ---
    if is_wide:
        _emit_index_setup(core_lines, profile)
    else:
        _emit_index_setup(core_lines, profile, long_format=True)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Reshape to dict ---
    if is_wide:
        core_lines.append(
            "# Reshape to dict format"
            " (optimal for ForecasterRecursiveMultiSeries)"
        )
        if isinstance(profile.target, list):
            target_cols_repr = repr(profile.target)
            core_lines.append(
                f"series_dict = data[{target_cols_repr}].to_dict('series')"
            )
        else:
            core_lines.append(
                "series_dict = data.to_dict('series')"
            )
    else:
        target = _get_target_str(profile)
        core_lines.append(
            "# Reshape to dict format"
            " (optimal for ForecasterRecursiveMultiSeries)"
        )
        core_lines.append("series_dict = reshape_series_long_to_dict(")
        core_lines.append("    data      = data,")
        core_lines.append(f"    series_id = {repr(series_id)},")
        core_lines.append(f"    index     = {repr(date_col)},")
        core_lines.append(f"    values    = {repr(target)},")
        core_lines.append(f"    freq      = {repr(profile.frequency)},")
        core_lines.append(")")
    core_lines.append("")

    # --- Exog setup (multi-series) ---
    exog_columns = profile.exog_columns
    exog_train_var = "exog_train"
    exog_test_var = "exog_test"
    if plan.use_exog and exog_columns:
        if is_wide:
            exog_cols_repr = repr(exog_columns)
            core_lines.append(f"exog = data[{exog_cols_repr}]")
        else:
            exog_train_var = "exog_dict_train"
            exog_test_var = "exog_dict_test"
            exog_select_cols = [series_id, date_col] + list(exog_columns)
            exog_select_repr = repr(exog_select_cols)
            core_lines.append("exog_dict = reshape_exog_long_to_dict(")
            core_lines.append(f"    data      = data[{exog_select_repr}],")
            core_lines.append(f"    series_id = {repr(series_id)},")
            core_lines.append(f"    index     = {repr(date_col)},")
            core_lines.append(f"    freq      = {repr(profile.frequency)},")
            core_lines.append(")")
        core_lines.append("")

    # --- Train/test split ---
    core_lines.append("# Train/test split")
    _emit_end_train(core_lines, profile)
    core_lines.append(
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}"
    )
    core_lines.append(
        "series_dict_test  = {k: v.loc[v.index > end_train]"
        " for k, v in series_dict.items()}"
    )
    if plan.use_exog and exog_columns:
        if is_wide:
            core_lines.append("exog_train = exog.loc[:end_train]")
            core_lines.append("exog_test  = exog.loc[exog.index > end_train]")
        else:
            core_lines.append(
                "exog_dict_train = {k: v.loc[:end_train]"
                " for k, v in exog_dict.items()}"
            )
            core_lines.append(
                "exog_dict_test  = {k: v.loc[v.index > end_train]"
                " for k, v in exog_dict.items()}"
            )
    core_lines.append("")

    # --- Window features ---
    if window_features:
        _emit_window_features(core_lines, window_features)
        core_lines.append("")

    # --- Transformer exog ---
    if transformer_exog and plan.use_exog and exog_columns:
        _emit_transformer_exog(core_lines, transformer_exog, profile)

    # --- Create forecaster ---
    _emit_forecaster_creation_multi(
        core_lines,
        plan,
        profile,
        forecaster_class="ForecasterRecursiveMultiSeries",
        use_exog=bool(plan.use_exog and exog_columns),
    )

    # --- Fit & Predict ---
    if plan.interval_method is not None:
        interval_repr = _get_interval_repr(plan)
        core_lines.append("# Fit")
        fit_kwargs: list[tuple[str, str]] = []
        fit_kwargs.append(("series", "series_dict_train"))
        if plan.use_exog and exog_columns:
            fit_kwargs.append(("exog", exog_train_var))
        fit_kwargs.append(("store_in_sample_residuals", "True"))
        _emit_aligned_kwargs(core_lines, "forecaster.fit(", fit_kwargs)
        core_lines.append("")

        core_lines.append("# Predict intervals")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if plan.use_exog and exog_columns:
            predict_kwargs.append(("exog", exog_test_var))
        predict_kwargs.append(("method", f"'{plan.interval_method}'"))
        predict_kwargs.append(("interval", interval_repr))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_interval(", predict_kwargs
        )
    else:
        core_lines.append("# Fit")
        if plan.use_exog and exog_columns:
            core_lines.append(
                f"forecaster.fit(series=series_dict_train, exog={exog_train_var})"
            )
        else:
            core_lines.append("forecaster.fit(series=series_dict_train)")
        core_lines.append("")
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        if plan.use_exog and exog_columns:
            core_lines.append(
                f"predictions = forecaster.predict("
                f"steps=steps, exog={exog_test_var})"
            )
        else:
            core_lines.append("predictions = forecaster.predict(steps=steps)")
    core_lines.append("print(predictions)")
    core_lines.append("")
    _emit_metrics_section_multiseries(
        core_lines,
        test_dict_var="series_dict_test",
        train_dict_var="series_dict_train",
        pred_var="predictions",
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


# ─────────────────────────────────────────────────────────────────────
# Template: multivariate
# ─────────────────────────────────────────────────────────────────────

def render_forecast_multivariate(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterDirectMultiVariate."""

    estimator_import = _get_estimator_import(plan.estimator)

    kwargs = plan.forecaster_kwargs
    transformer_series = kwargs.get("transformer_series")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    is_wide = profile.data_format == "wide"
    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "date"
    target = _get_target_str(profile)

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    import_lines.append("import pandas as pd")
    if transformer_series or transformer_exog:
        import_lines.append("from sklearn.preprocessing import StandardScaler")
    if transformer_exog and _needs_column_transformer(profile):
        import_lines.append("from sklearn.compose import make_column_transformer")
    import_lines.extend(_get_metric_imports(plan.metrics_to_compute))
    import_lines.append(estimator_import)
    if window_features:
        import_lines.append("from skforecast.preprocessing import RollingFeatures")
    import_lines.append("from skforecast.direct import ForecasterDirectMultiVariate")
    import_lines.append("")

    # --- Load data ---
    if is_wide:
        _emit_data_loading(loading_lines, profile)
    else:
        _emit_data_loading(loading_lines, profile, long_format=True)

    # --- Index setup (runs in both standalone and exec modes) ---
    if is_wide:
        _emit_index_setup(core_lines, profile)
    else:
        _emit_index_setup(core_lines, profile, long_format=True)

    # --- Preprocessing / pivot ---
    if is_wide:
        _emit_preprocessing_steps(core_lines, plan, profile)
    else:
        _emit_preprocessing_steps(core_lines, plan, profile)
        core_lines.append("# Pivot to wide format (columns = series)")
        core_lines.append("series = data.pivot_table(")
        core_lines.append(
            f"    index={repr(date_col)}, columns={repr(series_id)},"
            f" values={repr(target)}"
        )
        core_lines.append(")")
        core_lines.append("series.index.name = None")
        core_lines.append("series.columns.name = None")
        if profile.frequency:
            core_lines.append(f"series = series.asfreq('{profile.frequency}')")
        core_lines.append("")

    # --- Exog ---
    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    # --- Train/test split ---
    core_lines.append("# Train/test split")
    _emit_end_train(core_lines, profile)
    if use_exog and isinstance(profile.target, list):
        core_lines.append(f"series_cols = {repr(profile.target)}")
    if use_exog:
        core_lines.append(f"exog_features = {repr(exog_columns)}")
    if is_wide:
        core_lines.append("data_train = data.loc[:end_train]")
        core_lines.append("data_test  = data.loc[data.index > end_train]")
    else:
        core_lines.append("series_train = series.loc[:end_train]")
        core_lines.append("series_test  = series.loc[series.index > end_train]")
    core_lines.append("")

    # --- Window features ---
    if window_features:
        _emit_window_features(core_lines, window_features)
        core_lines.append("")

    # --- Transformer exog ---
    if transformer_exog and use_exog:
        _emit_transformer_exog(core_lines, transformer_exog, profile)

    # --- Create forecaster ---
    _emit_forecaster_creation_multi(
        core_lines,
        plan,
        profile,
        forecaster_class="ForecasterDirectMultiVariate",
        use_exog=use_exog,
    )

    # --- Fit & Predict ---
    if is_wide:
        series_train_expr = "data_train[series_cols]" if use_exog else "data_train"
        exog_train_expr = "data_train[exog_features]"
        exog_test_expr = "data_test[exog_features]"
        actual_expr = f"data_test[{repr(target)}].iloc[:steps]"
        train_expr = f"data_train[{repr(target)}]"
    else:
        series_train_expr = "series_train"
        exog_train_expr = "exog_train"
        exog_test_expr = "exog_test"
        actual_expr = f"series_test[{repr(target)}].iloc[:steps]"
        train_expr = f"series_train[{repr(target)}]"

    if plan.interval_method is not None:
        interval_repr = _get_interval_repr(plan)
        core_lines.append("# Fit")
        fit_kwargs: list[tuple[str, str]] = []
        fit_kwargs.append(("series", series_train_expr))
        if use_exog:
            fit_kwargs.append(("exog", exog_train_expr))
        fit_kwargs.append(("store_in_sample_residuals", "True"))
        _emit_aligned_kwargs(core_lines, "forecaster.fit(", fit_kwargs)

        core_lines.append("")
        core_lines.append("# Predict intervals")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if use_exog:
            predict_kwargs.append(("exog", exog_test_expr))
        predict_kwargs.append(("method", f"'{plan.interval_method}'"))
        predict_kwargs.append(("interval", interval_repr))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_interval(", predict_kwargs
        )
    else:
        core_lines.append("# Fit")
        if use_exog:
            core_lines.append(
                f"forecaster.fit(series={series_train_expr},"
                f" exog={exog_train_expr})"
            )
        else:
            core_lines.append(f"forecaster.fit(series={series_train_expr})")
        core_lines.append("")
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        if use_exog:
            core_lines.append(
                f"predictions = forecaster.predict("
                f"steps=steps, exog={exog_test_expr})"
            )
        else:
            core_lines.append("predictions = forecaster.predict(steps=steps)")
    core_lines.append("print(predictions)")
    core_lines.append("")

    _emit_metrics_section(
        core_lines,
        actual_expr=actual_expr,
        pred_expr="predictions['pred']",
        train_expr=train_expr,
        metrics_to_compute=plan.metrics_to_compute,
    )
    core_lines.append("")
    _emit_production_note(core_lines, use_exog=use_exog)
    core_lines.append("")

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )
