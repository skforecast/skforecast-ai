################################################################################
#            Rendering for multi-series and multivariate forecasting           #
#                                                                              #
# Script rendering for multi-series and multivariate forecasting               #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_calendar_features,
    _emit_data_loading,
    _emit_end_train,
    _emit_future_exog_index_setup,
    _emit_future_exog_loading,
    _emit_imports_multi_series,
    _emit_index_setup,
    _emit_metrics_section,
    _emit_metrics_section_multiseries,
    _emit_preprocessing_steps,
    _emit_production_note,
    _emit_transformer_exog,
    _emit_window_features,
    _format_lags,
    _get_estimator_constructor,
    _get_interval_repr,
    _get_target_str,
)


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
    window_features = kwargs.get("window_features")
    calendar_features = kwargs.get("calendar_features")
    transformer_series = kwargs.get("transformer_series")
    transformer_exog = kwargs.get("transformer_exog")
    categorical_features = kwargs.get("categorical_features")
    dropna = kwargs.get("dropna_from_series")
    differentiation = kwargs.get("differentiation")

    lines.append("# Create forecaster")
    estimator_str = _get_estimator_constructor(plan.estimator, plan.estimator_kwargs)

    forecaster_kwargs: list[tuple[str, str]] = []
    forecaster_kwargs.append(("estimator", estimator_str))
    if forecaster_class == "ForecasterDirectMultiVariate":
        level = _get_target_str(profile)
        forecaster_kwargs.append(("level", repr(level)))
        forecaster_kwargs.append(("steps", str(plan.steps)))

    forecaster_kwargs.append(("lags", _format_lags(lags)))
    if window_features:
        forecaster_kwargs.append(("window_features", "window_features"))
    if calendar_features:
        forecaster_kwargs.append(("calendar_features", "calendar_features"))

    if forecaster_class == "ForecasterRecursiveMultiSeries":
        encoding = kwargs.get("encoding", "ordinal")
        forecaster_kwargs.append(("encoding", f"'{encoding}'"))
    
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


def render_forecast_multi_series(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterRecursiveMultiSeries."""

    kwargs = plan.forecaster_kwargs
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    is_wide = profile.data_format == "wide"
    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "datetime"

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    evaluate = plan.end_train is not None
    use_exog_load = bool(plan.use_exog and profile.exog_columns)

    _emit_imports_multi_series(
        import_lines,
        plan,
        profile,
        include_metrics=evaluate,
    )

    # --- Load data ---
    if is_wide:
        _emit_data_loading(loading_lines, profile)
    else:
        _emit_data_loading(loading_lines, profile, long_format=True)
    if not evaluate and use_exog_load:
        _emit_future_exog_loading(loading_lines, profile)

    # --- Index setup (runs in both standalone and exec modes) ---
    if is_wide:
        _emit_index_setup(core_lines, profile)
    else:
        _emit_index_setup(core_lines, profile, long_format=True)
    if not evaluate and is_wide and use_exog_load:
        _emit_future_exog_index_setup(core_lines, profile)

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

    # --- Train/test split (evaluation mode) ---
    if evaluate:
        core_lines.append("# Train/test split")
        _emit_end_train(core_lines, plan)
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
    elif plan.use_exog and exog_columns and not is_wide:
        # Prediction mode, long format: reshape the future exogenous
        # variables into the dict format the forecaster expects.
        exog_select_cols = [series_id, date_col] + list(exog_columns)
        core_lines.append(
            "# Reshape future exogenous variables to dict format"
        )
        core_lines.append("exog_future_dict = reshape_exog_long_to_dict(")
        core_lines.append(f"    data      = exog_future[{repr(exog_select_cols)}],")
        core_lines.append(f"    series_id = {repr(series_id)},")
        core_lines.append(f"    index     = {repr(date_col)},")
        core_lines.append(f"    freq      = {repr(profile.frequency)},")
        core_lines.append(")")
        core_lines.append("")

    # --- Window features ---
    if window_features:
        _emit_window_features(core_lines, window_features)
        core_lines.append("")

    # --- Calendar features ---
    if kwargs.get("calendar_features"):
        _emit_calendar_features(core_lines, kwargs["calendar_features"])
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

    # In evaluation mode the model trains on the training split; in
    # prediction mode it trains on all the series and forecasts the future.
    series_fit_var = "series_dict_train" if evaluate else "series_dict"
    if evaluate:
        exog_fit_var = exog_train_var
        exog_pred_var = exog_test_var
    else:
        exog_fit_var = "exog" if is_wide else "exog_dict"
        exog_pred_var = "exog_future" if is_wide else "exog_future_dict"

    # --- Fit & Predict ---
    if plan.interval_method is not None:
        interval_repr = _get_interval_repr(plan)
        core_lines.append("# Fit")
        fit_kwargs: list[tuple[str, str]] = []
        fit_kwargs.append(("series", series_fit_var))
        if plan.use_exog and exog_columns:
            fit_kwargs.append(("exog", exog_fit_var))
        fit_kwargs.append(("store_in_sample_residuals", "True"))
        _emit_aligned_kwargs(core_lines, "forecaster.fit(", fit_kwargs)
        core_lines.append("")

        core_lines.append("# Predict intervals")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if plan.use_exog and exog_columns:
            predict_kwargs.append(("exog", exog_pred_var))
        predict_kwargs.append(("method", f"'{plan.interval_method}'"))
        predict_kwargs.append(("interval", interval_repr))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_interval(", predict_kwargs
        )
    else:
        core_lines.append("# Fit")
        if plan.use_exog and exog_columns:
            core_lines.append(
                f"forecaster.fit(series={series_fit_var}, exog={exog_fit_var})"
            )
        else:
            core_lines.append(f"forecaster.fit(series={series_fit_var})")
        core_lines.append("")
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        if plan.use_exog and exog_columns:
            core_lines.append(
                f"predictions = forecaster.predict("
                f"steps=steps, exog={exog_pred_var})"
            )
        else:
            core_lines.append("predictions = forecaster.predict(steps=steps)")
    core_lines.append("print(predictions)")
    core_lines.append("")

    if evaluate:
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


def render_forecast_multivariate(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterDirectMultiVariate."""

    kwargs = plan.forecaster_kwargs
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    is_wide = profile.data_format == "wide"
    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "datetime"
    target = _get_target_str(profile)

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    evaluate = plan.end_train is not None
    use_exog_load = bool(plan.use_exog and profile.exog_columns)

    _emit_imports_multi_series(
        import_lines,
        plan,
        profile,
        include_metrics=evaluate,
    )

    # --- Load data ---
    if is_wide:
        _emit_data_loading(loading_lines, profile)
    else:
        _emit_data_loading(loading_lines, profile, long_format=True)
    if not evaluate and use_exog_load:
        _emit_future_exog_loading(loading_lines, profile)

    # --- Index setup (runs in both standalone and exec modes) ---
    if is_wide:
        _emit_index_setup(core_lines, profile)
    else:
        _emit_index_setup(core_lines, profile, long_format=True)
    if not evaluate and is_wide and use_exog_load:
        _emit_future_exog_index_setup(core_lines, profile)

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

    # --- Train/test split (evaluation mode) ---
    if evaluate:
        core_lines.append("# Train/test split")
        _emit_end_train(core_lines, plan)
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
    else:
        if use_exog and isinstance(profile.target, list):
            core_lines.append(f"series_cols = {repr(profile.target)}")
        if use_exog:
            core_lines.append(f"exog_features = {repr(exog_columns)}")
        if use_exog or isinstance(profile.target, list):
            core_lines.append("")

    # --- Window features ---
    if window_features:
        _emit_window_features(core_lines, window_features)
        core_lines.append("")

    # --- Calendar features ---
    if kwargs.get("calendar_features"):
        _emit_calendar_features(core_lines, kwargs["calendar_features"])
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
    if evaluate:
        if is_wide:
            series_fit_expr = "data_train[series_cols]" if use_exog else "data_train"
            exog_fit_expr = "data_train[exog_features]"
            exog_pred_expr = "data_test[exog_features]"
        else:
            series_fit_expr = "series_train"
            exog_fit_expr = "exog_train"
            exog_pred_expr = "exog_test"
        actual_expr = (
            f"data_test[{repr(target)}].iloc[:steps]"
            if is_wide
            else f"series_test[{repr(target)}].iloc[:steps]"
        )
        train_expr = (
            f"data_train[{repr(target)}]"
            if is_wide
            else f"series_train[{repr(target)}]"
        )
    else:
        if is_wide:
            series_fit_expr = "data[series_cols]" if use_exog else "data"
            exog_fit_expr = "data[exog_features]"
            exog_pred_expr = "exog_future[exog_features]"
        else:
            series_fit_expr = "series"
            exog_fit_expr = "exog_train"
            exog_pred_expr = "exog_future"

    if plan.interval_method is not None:
        interval_repr = _get_interval_repr(plan)
        core_lines.append("# Fit")
        fit_kwargs: list[tuple[str, str]] = []
        fit_kwargs.append(("series", series_fit_expr))
        if use_exog:
            fit_kwargs.append(("exog", exog_fit_expr))
        fit_kwargs.append(("store_in_sample_residuals", "True"))
        _emit_aligned_kwargs(core_lines, "forecaster.fit(", fit_kwargs)

        core_lines.append("")
        core_lines.append("# Predict intervals")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if use_exog:
            predict_kwargs.append(("exog", exog_pred_expr))
        predict_kwargs.append(("method", f"'{plan.interval_method}'"))
        predict_kwargs.append(("interval", interval_repr))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_interval(", predict_kwargs
        )
    else:
        core_lines.append("# Fit")
        if use_exog:
            core_lines.append(
                f"forecaster.fit(series={series_fit_expr},"
                f" exog={exog_fit_expr})"
            )
        else:
            core_lines.append(f"forecaster.fit(series={series_fit_expr})")
        core_lines.append("")
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        if use_exog:
            core_lines.append(
                f"predictions = forecaster.predict("
                f"steps=steps, exog={exog_pred_expr})"
            )
        else:
            core_lines.append("predictions = forecaster.predict(steps=steps)")
    core_lines.append("print(predictions)")
    core_lines.append("")

    if evaluate:
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
