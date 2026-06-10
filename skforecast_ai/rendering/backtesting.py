"""Script rendering for backtesting workflows."""

from typing import Any

from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_data_loading,
    _emit_imports_foundation,
    _emit_imports_multi_series,
    _emit_imports_single_series,
    _emit_imports_statistical,
    _emit_index_setup,
    _emit_preprocessing_steps,
    _emit_transformer_exog,
    _emit_window_features,
    _get_target_str,
)
from .foundation import _emit_forecaster_creation_foundation
from .multi_series import _emit_forecaster_creation_multi
from .single_series import _emit_forecaster_creation_single
from .statistical import _emit_forecaster_creation_statistical


def _emit_cv_configuration(
    lines: list[str],
    cv: Any,
) -> None:
    """Append TimeSeriesFold construction code."""

    lines.append("# Time series cross-validation configuration")
    cv_kwargs: list[tuple[str, str]] = []
    cv_kwargs.append(("steps", str(cv.steps)))
    its = cv.initial_train_size
    its_repr = repr(its) if isinstance(its, str) else str(its)
    cv_kwargs.append(("initial_train_size", its_repr))
    if cv.fold_stride is not None and cv.fold_stride != cv.steps:
        cv_kwargs.append(("fold_stride", str(cv.fold_stride)))
    cv_kwargs.append(("refit", str(cv.refit)))
    if cv.refit:
        cv_kwargs.append(("fixed_train_size", str(cv.fixed_train_size)))
    if cv.gap != 0:
        cv_kwargs.append(("gap", str(cv.gap)))
    if cv.skip_folds is not None:
        cv_kwargs.append(("skip_folds", str(cv.skip_folds)))
    if cv.allow_incomplete_fold is False:
        cv_kwargs.append(("allow_incomplete_fold", "False"))
    if cv.differentiation is not None:
        cv_kwargs.append(("differentiation", str(cv.differentiation)))

    _emit_aligned_kwargs(lines, "cv = TimeSeriesFold(", cv_kwargs)
    lines.append("")


def _emit_backtesting_call(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """Append backtesting_forecaster call for single-series."""

    target = _get_target_str(profile)
    exog_columns = profile.exog_columns

    lines.append("# Run backtesting")
    if plan.use_exog and exog_columns:
        lines.append(f"exog_features = {repr(exog_columns)}")
        lines.append("")

    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("y", f"data[{repr(target)}]"))
    if plan.use_exog and exog_columns:
        bt_kwargs.append(("exog", "data[exog_features]"))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if plan.interval is not None:
        bt_kwargs.append(("interval", repr(plan.interval)))
    bt_kwargs.append(("n_jobs", "'auto'"))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines, "metrics, predictions = backtesting_forecaster(", bt_kwargs
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


def _emit_backtesting_call_multiseries(
    lines: list[str],
    plan: ForecastPlan,
    *,
    series_expr: str,
    exog_expr: str | None,
) -> None:
    """Append backtesting_forecaster_multiseries call."""

    lines.append("# Run backtesting")
    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("series", series_expr))
    if exog_expr is not None:
        bt_kwargs.append(("exog", exog_expr))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if plan.interval is not None:
        bt_kwargs.append(("interval", repr(plan.interval)))
    bt_kwargs.append(("n_jobs", "'auto'"))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines,
        "metrics, predictions = backtesting_forecaster_multiseries(",
        bt_kwargs,
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


# ─────────────────────────────────────────────────────────────────────
# Template: backtesting single_series
# ─────────────────────────────────────────────────────────────────────


def render_backtesting_single_series(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterRecursive or ForecasterDirect."""

    kwargs = plan.forecaster_kwargs
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_single_series(
        import_lines,
        plan,
        profile,
        include_backtesting=True,
    )

    # --- Load data ---
    _emit_data_loading(loading_lines, profile)

    # --- Index setup ---
    _emit_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Window features ---
    if window_features and isinstance(window_features, list):
        _emit_window_features(core_lines, window_features)
        core_lines.append("")

    # --- Transformer exog ---
    if transformer_exog and plan.use_exog and profile.exog_columns:
        _emit_transformer_exog(core_lines, transformer_exog, profile)

    # --- Create forecaster ---
    _emit_forecaster_creation_single(core_lines, plan, profile)

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call(core_lines, plan, profile)

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: backtesting multi_series
# ─────────────────────────────────────────────────────────────────────


def render_backtesting_multi_series(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterRecursiveMultiSeries."""

    kwargs = plan.forecaster_kwargs
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    is_wide = profile.data_format == "wide"
    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_multi_series(
        import_lines,
        plan,
        profile,
        include_backtesting=True,
    )

    # --- Load data ---
    if is_wide:
        _emit_data_loading(loading_lines, profile)
    else:
        _emit_data_loading(loading_lines, profile, long_format=True)

    # --- Index setup ---
    if is_wide:
        _emit_index_setup(core_lines, profile)
    else:
        _emit_index_setup(core_lines, profile, long_format=True)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Reshape to series expression ---
    if is_wide:
        if isinstance(profile.target, list):
            series_expr = f"data[{repr(profile.target)}]"
        else:
            series_expr = f"data[[{repr(profile.target)}]]"
    else:
        series_id = profile.series_id_column or "series_id"
        date_col = profile.date_column or "datetime"
        target = _get_target_str(profile)
        core_lines.append(
            "# Reshape to dict format"
            " (required for backtesting multi-series)"
        )
        core_lines.append("series_dict = reshape_series_long_to_dict(")
        core_lines.append("    data      = data,")
        core_lines.append(f"    series_id = {repr(series_id)},")
        core_lines.append(f"    index     = {repr(date_col)},")
        core_lines.append(f"    values    = {repr(target)},")
        core_lines.append(f"    freq      = {repr(profile.frequency)},")
        core_lines.append(")")
        core_lines.append("")
        series_expr = "series_dict"

    # --- Exog setup ---
    exog_expr: str | None = None
    if use_exog:
        if is_wide:
            core_lines.append(f"exog_features = {repr(exog_columns)}")
            core_lines.append("")
            exog_expr = "data[exog_features]"
        else:
            exog_select_cols = [series_id, date_col] + list(exog_columns)
            core_lines.append("exog_dict = reshape_exog_long_to_dict(")
            core_lines.append(f"    data      = data[{repr(exog_select_cols)}],")
            core_lines.append(f"    series_id = {repr(series_id)},")
            core_lines.append(f"    index     = {repr(date_col)},")
            core_lines.append(f"    freq      = {repr(profile.frequency)},")
            core_lines.append(")")
            core_lines.append("")
            exog_expr = "exog_dict"

    # --- Window features ---
    if window_features and isinstance(window_features, list):
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
        forecaster_class="ForecasterRecursiveMultiSeries",
        use_exog=use_exog,
    )

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call_multiseries(
        core_lines, plan, series_expr=series_expr, exog_expr=exog_expr
    )

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: backtesting multivariate
# ─────────────────────────────────────────────────────────────────────


def render_backtesting_multivariate(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterDirectMultiVariate."""

    kwargs = plan.forecaster_kwargs
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")

    is_wide = profile.data_format == "wide"
    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_multi_series(
        import_lines,
        plan,
        profile,
        include_backtesting=True,
    )

    # --- Load data ---
    if is_wide:
        _emit_data_loading(loading_lines, profile)
    else:
        _emit_data_loading(loading_lines, profile, long_format=True)

    # --- Index setup ---
    if is_wide:
        _emit_index_setup(core_lines, profile)
    else:
        _emit_index_setup(core_lines, profile, long_format=True)

    # --- Preprocessing / pivot ---
    _emit_preprocessing_steps(core_lines, plan, profile)
    if not is_wide:
        series_id = profile.series_id_column or "series_id"
        date_col = profile.date_column or "datetime"
        target = _get_target_str(profile)
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

    # --- Series expression ---
    if is_wide:
        if isinstance(profile.target, list):
            series_expr = f"data[{repr(profile.target)}]"
        else:
            series_expr = f"data[[{repr(profile.target)}]]"
    else:
        series_expr = "series"

    # --- Exog setup ---
    exog_expr: str | None = None
    if use_exog:
        core_lines.append(f"exog_features = {repr(exog_columns)}")
        core_lines.append("")
        exog_expr = "data[exog_features]"

    # --- Window features ---
    if window_features and isinstance(window_features, list):
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

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call_multiseries(
        core_lines, plan, series_expr=series_expr, exog_expr=exog_expr
    )

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: backtesting foundation
# ─────────────────────────────────────────────────────────────────────


def _get_quantiles_from_plan(plan: ForecastPlan) -> list[float] | None:
    """Derive quantiles list from plan.interval, or None if no intervals."""

    if plan.interval_method is None:
        return None
    if plan.interval is not None:
        quantiles = [round(v / 100, 2) for v in plan.interval]
        if 0.5 not in quantiles:
            quantiles = sorted([quantiles[0], 0.5, quantiles[1]])
        return quantiles
    return [0.1, 0.5, 0.9]


def _emit_backtesting_call_foundation(
    lines: list[str],
    plan: ForecastPlan,
    *,
    series_expr: str,
    exog_expr: str | None,
    levels_expr: str | None,
) -> None:
    """Append backtesting_foundation call."""

    quantiles = _get_quantiles_from_plan(plan)

    lines.append("# Run backtesting")
    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("series", series_expr))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if levels_expr is not None:
        bt_kwargs.append(("levels", levels_expr))
    if exog_expr is not None:
        bt_kwargs.append(("exog", exog_expr))
    if quantiles is not None:
        bt_kwargs.append(("quantiles", repr(quantiles)))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines,
        "metrics, predictions = backtesting_foundation(",
        bt_kwargs,
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


def render_backtesting_foundation(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterFoundation."""

    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    is_multi_series = isinstance(profile.target, list) and len(profile.target) > 1

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_foundation(import_lines, plan, include_backtesting=True)

    # --- Load data ---
    _emit_data_loading(loading_lines, profile)

    # --- Index setup ---
    _emit_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Series expression ---
    target = _get_target_str(profile)
    if is_multi_series:
        series_expr = f"data[{repr(profile.target)}]"
    else:
        series_expr = f"data[{repr(target)}]"

    # --- Exog setup ---
    exog_expr: str | None = None
    if use_exog:
        core_lines.append(f"exog_features = {repr(exog_columns)}")
        core_lines.append("")
        exog_expr = "data[exog_features]"

    # --- Levels ---
    levels_expr: str | None = None
    if is_multi_series:
        levels_expr = repr(profile.target)

    # --- Create forecaster ---
    _emit_forecaster_creation_foundation(core_lines, plan)

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call_foundation(
        core_lines,
        plan,
        series_expr=series_expr,
        exog_expr=exog_expr,
        levels_expr=levels_expr,
    )

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: backtesting statistical
# ─────────────────────────────────────────────────────────────────────


def _emit_backtesting_call_statistical(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """Append backtesting_stats call for ForecasterStats."""

    target = _get_target_str(profile)
    exog_columns = profile.exog_columns

    lines.append("# Run backtesting")
    if plan.use_exog and exog_columns:
        lines.append(f"exog_features = {repr(exog_columns)}")
        lines.append("")

    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("y", f"data[{repr(target)}]"))
    if plan.use_exog and exog_columns:
        bt_kwargs.append(("exog", "data[exog_features]"))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if plan.interval is not None:
        bt_kwargs.append(("interval", repr(plan.interval)))
    bt_kwargs.append(("freeze_params", "True"))
    bt_kwargs.append(("n_jobs", "'auto'"))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines, "metrics, predictions = backtesting_stats(", bt_kwargs
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


def render_backtesting_statistical(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterStats (Auto-ARIMA)."""

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_statistical(import_lines, plan, include_backtesting=True)

    # --- Load data ---
    _emit_data_loading(loading_lines, profile)

    # --- Index setup ---
    _emit_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Create forecaster ---
    _emit_forecaster_creation_statistical(core_lines, plan, profile)

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call_statistical(core_lines, plan, profile)

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )
