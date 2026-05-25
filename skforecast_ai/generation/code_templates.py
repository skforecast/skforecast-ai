"""Code generation templates for skforecast workflows."""

from collections.abc import Callable

from ..schemas import DataProfile, ForecastPlan, GeneratedCode

# Mapping from pandas frequency strings to seasonal period (m)
_FREQUENCY_TO_M: dict[str, int] = {
    "min": 60,
    "5min": 288,
    "10min": 144,
    "15min": 96,
    "30min": 48,
    "h": 24,
    "2h": 12,
    "4h": 6,
    "6h": 4,
    "D": 7,
    "2D": 7,
    "B": 5,
    "W": 52,
    "W-SUN": 52,
    "W-MON": 52,
    "MS": 12,
    "ME": 12,
    "QS": 4,
    "QE": 4,
    "YS": 1,
    "YE": 1,
}

_ESTIMATOR_IMPORTS: dict[str, str] = {
    "LGBMRegressor": "from lightgbm import LGBMRegressor",
    "Ridge": "from sklearn.linear_model import Ridge",
    "XGBRegressor": "from xgboost import XGBRegressor",
    "CatBoostRegressor": "from catboost import CatBoostRegressor",
    "RandomForestRegressor": "from sklearn.ensemble import RandomForestRegressor",
    "HistGradientBoostingRegressor": "from sklearn.ensemble import HistGradientBoostingRegressor",
}

# Default kwargs injected into estimator constructors (silencing + reproducibility)
_ESTIMATOR_DEFAULTS: dict[str, dict[str, object]] = {
    "LGBMRegressor": {"random_state": 123, "verbose": -1},
    "XGBRegressor": {"random_state": 123, "verbosity": 0},
    "CatBoostRegressor": {"random_state": 123, "verbose": 0},
    "RandomForestRegressor": {"random_state": 123},
    "HistGradientBoostingRegressor": {"random_state": 123},
    "Ridge": {},
}


# ─────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────

def _get_seasonal_period(frequency: str | None) -> int | None:
    """Return seasonal period m for the given pandas frequency string."""
    if frequency is None:
        return None
    return _FREQUENCY_TO_M.get(frequency)


def _get_interval_repr(plan: ForecastPlan) -> str:
    """Return the interval list as a code literal."""
    if plan.interval is not None:
        return repr(plan.interval)
    return "[10, 90]  # default 80% prediction interval"


def _emit_preprocessing_steps(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """Append blocking preprocessing steps after data loading."""
    blocking = [s for s in plan.preprocessing_steps if s.blocking]
    if not blocking:
        return

    target_str = (
        profile.target if isinstance(profile.target, str)
        else profile.target[0]
    )
    replacements = {
        "frequency": profile.frequency or "",
        "date_column": profile.date_column or "",
        "series_id_column": profile.series_id_column or "",
        "target": target_str,
    }

    lines.append("# Preprocessing")
    for step in blocking:
        snippet = step.code_snippet.format_map(replacements)
        for snippet_line in snippet.split("\n"):
            lines.append(snippet_line)

    # After deduplication, set the frequency that was deferred during loading
    if profile.has_duplicate_timestamps and profile.frequency:
        lines.append(f"data = data.asfreq('{profile.frequency}')")

    lines.append("")


def _emit_data_loading(
    lines: list[str],
    profile: DataProfile,
    long_format: bool = False,
) -> None:
    """
    Append CSV-loading code lines (only the read_csv call).

    Parameters
    ----------
    lines : list
        Output list of code lines to append to.
    profile : DataProfile
        Data profile with `data_path`, `date_column`, and `frequency`.
    long_format : bool, default False
        If `False` (wide format), emits read_csv only.
        If `True` (long format), emits read_csv only.

    Returns
    -------
    None
    
    """

    data_path = profile.data_path
    date_col = profile.date_column

    lines.append("# Load data")
    if long_format:
        lines.append(f"data = pd.read_csv({repr(data_path)})")
    else:
        if date_col:
            lines.append(f"data = pd.read_csv({repr(data_path)})")
        else:
            lines.append(
                f"data = pd.read_csv({repr(data_path)}, index_col=0, parse_dates=True)"
            )
    lines.append("")


def _emit_index_setup(
    lines: list[str],
    profile: DataProfile,
    long_format: bool = False,
) -> None:
    """
    Append index-setup code (to_datetime, set_index, asfreq, sort).

    This section is emitted into the core code so that it runs both
    in standalone scripts (after CSV loading) and in exec mode (when
    data is injected as a raw DataFrame).

    Parameters
    ----------
    lines : list
        Output list of code lines to append to.
    profile : DataProfile
        Data profile with `date_column` and `frequency`.
    long_format : bool, default False
        If `False` (wide format), emits set_index + asfreq + sort_index.
        If `True` (long format), emits to_datetime + sort_values only.

    Returns
    -------
    None
    
    """

    date_col = profile.date_column
    frequency = profile.frequency

    if long_format:
        if date_col:
            lines.append(
                f"data[{repr(date_col)}] = pd.to_datetime(data[{repr(date_col)}])"
            )
            lines.append(f"data = data.sort_values({repr(date_col)})")
        lines.append("")
    else:
        if date_col:
            lines.append(
                f"data[{repr(date_col)}] = pd.to_datetime(data[{repr(date_col)}])"
            )
            lines.append(f"data = data.set_index({repr(date_col)})")
        if frequency and not profile.has_duplicate_timestamps:
            lines.append(f"data = data.asfreq('{frequency}')")
        lines.append("data = data.sort_index()")
        lines.append("")


def _emit_window_features(lines: list[str], window_features: list[dict]) -> None:
    """Append RollingFeatures construction code."""
    if not window_features:
        return

    # Flatten all entries into a single RollingFeatures call
    all_stats: list[str] = []
    all_window_sizes: list[int] = []
    for wf in window_features:
        stats = wf.get("stats", [])
        window_size = wf.get("window_sizes")
        for stat in stats:
            all_stats.append(stat)
            all_window_sizes.append(window_size)

    lines.append("window_features = RollingFeatures(")
    lines.append(f"    stats        = {all_stats},")
    lines.append(f"    window_sizes = {all_window_sizes},")
    lines.append(")")


def _get_numeric_exog(profile: DataProfile) -> list[str]:
    """Return exog columns that are not categorical."""
    return [c for c in profile.exog_columns if c not in profile.categorical_exog]


def _emit_transformer_exog(
    lines: list[str],
    transformer_exog: str | None,
    profile: DataProfile,
) -> None:
    """Append ColumnTransformer setup for exogenous variables."""
    if transformer_exog is None:
        return

    numeric_exog = _get_numeric_exog(profile)

    if profile.categorical_exog and numeric_exog:
        lines.append("transformer_exog = make_column_transformer(")
        lines.append(f"    (StandardScaler(), {repr(numeric_exog)}),")
        lines.append("    remainder='passthrough',")
        lines.append("    verbose_feature_names_out=False,")
        lines.append(").set_output(transform='pandas')")
    elif numeric_exog:
        lines.append("transformer_exog = StandardScaler()")
    lines.append("")


def _needs_column_transformer(profile: DataProfile) -> bool:
    """Check if a ColumnTransformer is needed (mixed numeric + categorical exog)."""
    return bool(profile.categorical_exog and _get_numeric_exog(profile))


def _emit_production_note(
    lines: list[str],
    use_exog: bool,
    is_foundation: bool = False,
) -> None:
    """Append a trailing note about retraining for production use."""
    lines.append(
        "# NOTE: This script uses a train/test split for demonstration purposes."
    )
    if is_foundation:
        lines.append(
            "# For production forecasting, pass all available data as context"
        )
    else:
        lines.append(
            "# For production forecasting, retrain with all available data"
        )
    if use_exog:
        lines.append(
            "# and provide future exogenous values covering the forecast horizon."
        )
    else:
        lines.append("# and call predict() on the desired horizon.")


def _emit_end_train(
    lines: list[str],
    profile: DataProfile,
) -> None:
    """Emit the `end_train` variable (date-based split point).

    Raises `ValueError` if `profile.end_train` is not set because the
    generated code must contain a concrete date literal.
    """
    if profile.end_train is None:
        raise ValueError(
            "profile.end_train must be set before generating code. "
            "Run data profiling first so the 80% split date is computed."
        )
    lines.append(
        f"end_train = {repr(profile.end_train)}"
        "  # 80% of data, adjust to change the split point"
    )


_METRIC_REGISTRY: dict[str, dict[str, str | bool]] = {
    "mean_absolute_error": {
        "import": "from sklearn.metrics import mean_absolute_error",
        "var": "mae",
        "label": "MAE",
        "call": "mean_absolute_error(actual, {pred_expr})",
        "requires_y_train": False,
    },
    "mean_squared_error": {
        "import": "from sklearn.metrics import mean_squared_error",
        "var": "mse",
        "label": "MSE",
        "call": "mean_squared_error(actual, {pred_expr})",
        "requires_y_train": False,
    },
    "mean_absolute_scaled_error": {
        "import": "from skforecast.metrics import mean_absolute_scaled_error",
        "var": "mase",
        "label": "MASE",
        "call": (
            "mean_absolute_scaled_error(\n"
            "    y_true  = actual,\n"
            "    y_pred  = {pred_expr},\n"
            "    y_train = {train_expr},\n"
            ")"
        ),
        "requires_y_train": True,
    },
    "mean_absolute_percentage_error": {
        "import": "from sklearn.metrics import mean_absolute_percentage_error",
        "var": "mape",
        "label": "MAPE",
        "call": "mean_absolute_percentage_error(actual, {pred_expr})",
        "requires_y_train": False,
    },
}


def _get_metric_imports(metrics_to_compute: list[str]) -> list[str]:
    """
    Build deduplicated import lines for the requested metrics.

    Groups sklearn imports on a single line when possible.
    """
    sklearn_funcs: list[str] = []
    skforecast_imports: list[str] = []

    for m in metrics_to_compute:
        info = _METRIC_REGISTRY.get(m)
        if info is None:
            continue
        if info["import"].startswith("from sklearn"):
            func_name = info["import"].split("import ")[-1]
            if func_name not in sklearn_funcs:
                sklearn_funcs.append(func_name)
        else:
            if info["import"] not in skforecast_imports:
                skforecast_imports.append(info["import"])

    lines: list[str] = []
    if sklearn_funcs:
        lines.append(f"from sklearn.metrics import {', '.join(sklearn_funcs)}")
    lines.extend(skforecast_imports)
    return lines


def _emit_metrics_section(
    lines: list[str],
    actual_expr: str,
    pred_expr: str,
    train_expr: str,
    metrics_to_compute: list[str] | None = None,
) -> None:
    """Append test-set evaluation metrics based on metrics_to_compute."""
    if metrics_to_compute is None:
        metrics_to_compute = [
            "mean_absolute_error",
            "mean_squared_error",
            "mean_absolute_scaled_error",
        ]

    lines.append("# Evaluate on test set")
    lines.append(f"actual = {actual_expr}")

    for m in metrics_to_compute:
        info = _METRIC_REGISTRY.get(m)
        if info is None:
            continue
        call = info["call"].format(pred_expr=pred_expr, train_expr=train_expr)
        lines.append(f"{info['var']} = {call}")

    lines.append("")
    for m in metrics_to_compute:
        info = _METRIC_REGISTRY.get(m)
        if info is None:
            continue
        lines.append(f'print(f"{info["label"]:<5}: {{{info["var"]}:.4f}}")')


def _emit_metrics_section_multiseries(
    lines: list[str],
    test_dict_var: str,
    train_dict_var: str,
    pred_var: str,
    metrics_to_compute: list[str] | None = None,
) -> None:
    """Append per-series evaluation metrics as a DataFrame."""
    if metrics_to_compute is None:
        metrics_to_compute = [
            "mean_absolute_error",
            "mean_squared_error",
            "mean_absolute_scaled_error",
        ]

    lines.append("# Evaluate on test set (per series)")
    lines.append("metrics_list = []")
    lines.append(f"for series_name in {test_dict_var}:")
    lines.append(
        f"    actual = {test_dict_var}[series_name].iloc[:steps]"
    )
    lines.append(
        f"    mask = {pred_var}['level'] == series_name"
    )
    lines.append(
        f"    pred = {pred_var}.loc[mask, 'pred'].values"
    )
    lines.append("    metrics_list.append({")
    lines.append('        "series": series_name,')
    for m in metrics_to_compute:
        info = _METRIC_REGISTRY.get(m)
        if info is None:
            continue
        func_name = info["import"].split("import ")[-1]
        if info["requires_y_train"]:
            lines.append(f'        "{info["label"]}": {func_name}(')
            lines.append(
                f"            actual, pred, y_train={train_dict_var}[series_name]"
            )
            lines.append("        ),")
        else:
            lines.append(
                f'        "{info["label"]}": {func_name}(actual, pred),'
            )
    lines.append("    })")
    lines.append("metrics_df = pd.DataFrame(metrics_list)")
    lines.append("print(metrics_df.to_string(index=False))")


def _emit_metrics_section_foundation(
    lines: list[str],
    is_multi_series: bool,
    has_intervals: bool,
    test_var: str,
    train_var: str,
    metrics_to_compute: list[str] | None = None,
) -> None:
    """Append evaluation metrics for ForecasterFoundation output."""
    if metrics_to_compute is None:
        metrics_to_compute = [
            "mean_absolute_error",
            "mean_squared_error",
            "mean_absolute_scaled_error",
        ]

    pred_col = "'q_0.5'" if has_intervals else "'pred'"
    if is_multi_series:
        lines.append("# Evaluate on test set (per series)")
        lines.append("metrics_list = []")
        lines.append("for level in predictions['level'].unique():")
        lines.append("    mask = predictions['level'] == level")
        lines.append(
            f"    pred = predictions.loc[mask, {pred_col}].values"
        )
        lines.append(
            f"    actual = {test_var}[level].iloc[:steps]"
        )
        lines.append("    metrics_list.append({")
        lines.append('        "series": level,')
        for m in metrics_to_compute:
            info = _METRIC_REGISTRY.get(m)
            if info is None:
                continue
            func_name = info["import"].split("import ")[-1]
            if info["requires_y_train"]:
                lines.append(f'        "{info["label"]}": {func_name}(')
                lines.append(
                    f"            actual, pred, y_train={train_var}[level]"
                )
                lines.append("        ),")
            else:
                lines.append(
                    f'        "{info["label"]}": {func_name}(actual, pred),'
                )
        lines.append("    })")
        lines.append("metrics_df = pd.DataFrame(metrics_list)")
        lines.append("print(metrics_df.to_string(index=False))")
    else:
        lines.append("# Evaluate on test set")
        lines.append(f"actual = {test_var}.iloc[:steps]")
        lines.append(
            f"pred = predictions[{pred_col}].values"
        )
        for m in metrics_to_compute:
            info = _METRIC_REGISTRY.get(m)
            if info is None:
                continue
            call = info["call"].format(pred_expr="pred", train_expr=train_var)
            lines.append(f"{info['var']} = {call}")
        lines.append("")
        for m in metrics_to_compute:
            info = _METRIC_REGISTRY.get(m)
            if info is None:
                continue
            lines.append(f'print(f"{info["label"]:<5}: {{{info["var"]}:.4f}}")')


def _get_estimator_import(estimator: str | None) -> str:
    """Resolve the estimator import line."""
    return _ESTIMATOR_IMPORTS.get(
        estimator or "",
        f"from __main__ import {estimator}  "
        f"# TODO: replace with correct import for {estimator}",
    )


def _get_estimator_constructor(
    estimator: str | None,
    estimator_kwargs: dict[str, object] | None = None,
) -> str:
    """Return estimator constructor call with merged kwargs.

    Merges built-in defaults (silencing, random_state) with user-provided
    kwargs. User kwargs take precedence over defaults.
    """
    name = estimator or ""
    defaults = _ESTIMATOR_DEFAULTS.get(name, {})
    merged = {**defaults, **(estimator_kwargs or {})}

    if not merged:
        return f"{name}()"

    params = ", ".join(f"{k}={repr(v)}" for k, v in merged.items())
    return f"{name}({params})"


def _get_target_str(profile: DataProfile) -> str:
    """Get target as a string for single-series indexing."""
    if isinstance(profile.target, list):
        return profile.target[0]
    return profile.target


def _emit_aligned_kwargs(
    lines: list[str],
    header: str,
    kwargs: list[tuple[str, str]],
) -> None:
    """Append a multi-line call with dynamically aligned '=' signs.

    Parameters
    ----------
    lines : list[str]
        Output list to append to.
    header : str
        Opening line (e.g. "forecaster = ForecasterRecursive(").
    kwargs : list[tuple[str, str]]
        List of (param_name, value_str) pairs.
    """
    lines.append(header)
    max_len = max(len(k) for k, _ in kwargs)
    for key, value in kwargs:
        lines.append(f"    {key:<{max_len}} = {value},")
    lines.append(")")


# ─────────────────────────────────────────────────────────────────────
# Template: single_series
# ─────────────────────────────────────────────────────────────────────

def _template_single_series(
    plan: ForecastPlan,
    profile: DataProfile,
) -> GeneratedCode:
    """Generate code for ForecasterRecursive or ForecasterDirect."""

    is_direct = plan.forecaster == "ForecasterDirect"
    forecaster_module = "direct" if is_direct else "recursive"
    forecaster_class = plan.forecaster
    estimator_import = _get_estimator_import(plan.estimator)
    target = _get_target_str(profile)

    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags")
    dropna = kwargs.get("dropna_from_series")
    differentiation = kwargs.get("differentiation")
    transformer_y = kwargs.get("transformer_y")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")
    categorical_features = kwargs.get("categorical_features")

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
    core_lines.append('    f"Train dates : {data_train.index.min()} --- '
                 '{data_train.index.max()}  (n={len(data_train)})"')
    core_lines.append(")")
    core_lines.append("print(")
    core_lines.append('    f"Test dates  : {data_test.index.min()} --- '
                 '{data_test.index.max()}  (n={len(data_test)})"')
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
    core_lines.append("# Create forecaster")
    estimator_str = _get_estimator_constructor(plan.estimator, plan.estimator_kwargs)

    forecaster_kwargs: list[tuple[str, str]] = []
    if is_direct:
        forecaster_kwargs.append(("estimator", estimator_str))
        forecaster_kwargs.append(("steps", str(plan.steps)))
        forecaster_kwargs.append(("lags", str(lags)))
    else:
        forecaster_kwargs.append(("estimator", estimator_str))
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
        core_lines,
        f"forecaster = {forecaster_class}(",
        forecaster_kwargs,
    )
    core_lines.append("")

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

    return GeneratedCode(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: multi_series
# ─────────────────────────────────────────────────────────────────────

def _template_multi_series(
    plan: ForecastPlan,
    profile: DataProfile,
) -> GeneratedCode:
    """Generate code for ForecasterRecursiveMultiSeries."""

    estimator_import = _get_estimator_import(plan.estimator)

    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags")
    encoding = kwargs.get("encoding", "ordinal")
    dropna = kwargs.get("dropna_from_series")
    differentiation = kwargs.get("differentiation")
    transformer_series = kwargs.get("transformer_series")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")
    categorical_features = kwargs.get("categorical_features")

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
    core_lines.append("# Create forecaster")
    estimator_str = _get_estimator_constructor(plan.estimator, plan.estimator_kwargs)

    forecaster_kwargs: list[tuple[str, str]] = []
    forecaster_kwargs.append(("estimator", estimator_str))
    forecaster_kwargs.append(("lags", str(lags)))
    forecaster_kwargs.append(("encoding", f"'{encoding}'"))
    if window_features:
        forecaster_kwargs.append(("window_features", "window_features"))
    if transformer_series is not None:
        forecaster_kwargs.append(("transformer_series", f"{transformer_series}()"))
    if transformer_exog is not None and plan.use_exog and exog_columns:
        forecaster_kwargs.append(("transformer_exog", "transformer_exog"))
    if categorical_features is not None:
        forecaster_kwargs.append(("categorical_features", f"'{categorical_features}'"))
    if differentiation is not None:
        forecaster_kwargs.append(("differentiation", str(differentiation)))
    if dropna is not None:
        forecaster_kwargs.append(("dropna_from_series", str(dropna)))

    _emit_aligned_kwargs(
        core_lines,
        "forecaster = ForecasterRecursiveMultiSeries(",
        forecaster_kwargs,
    )
    core_lines.append("")

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

    return GeneratedCode(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: multivariate
# ─────────────────────────────────────────────────────────────────────

def _template_multivariate(
    plan: ForecastPlan,
    profile: DataProfile,
) -> GeneratedCode:
    """Generate code for ForecasterDirectMultiVariate."""

    estimator_import = _get_estimator_import(plan.estimator)

    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags")
    dropna = kwargs.get("dropna_from_series")
    differentiation = kwargs.get("differentiation")
    transformer_series = kwargs.get("transformer_series")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")
    categorical_features = kwargs.get("categorical_features")

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
        core_lines.append("series.columns = series.columns.droplevel(0)")
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
    core_lines.append("# Create forecaster")
    estimator_str = _get_estimator_constructor(plan.estimator, plan.estimator_kwargs)

    forecaster_kwargs: list[tuple[str, str]] = []
    forecaster_kwargs.append(("estimator", estimator_str))
    forecaster_kwargs.append(("level", repr(target)))
    forecaster_kwargs.append(("steps", str(plan.steps)))
    forecaster_kwargs.append(("lags", str(lags)))
    if window_features:
        forecaster_kwargs.append(("window_features", "window_features"))
    if transformer_series is not None:
        forecaster_kwargs.append(("transformer_series", f"{transformer_series}()"))
    if transformer_exog is not None and use_exog:
        forecaster_kwargs.append(("transformer_exog", "transformer_exog"))
    if categorical_features is not None and use_exog:
        forecaster_kwargs.append(("categorical_features", f"'{categorical_features}'"))
    if differentiation is not None:
        forecaster_kwargs.append(("differentiation", str(differentiation)))
    if dropna is not None:
        forecaster_kwargs.append(("dropna_from_series", str(dropna)))

    _emit_aligned_kwargs(
        core_lines,
        "forecaster = ForecasterDirectMultiVariate(",
        forecaster_kwargs,
    )
    core_lines.append("")

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

    return GeneratedCode(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: statistical
# ─────────────────────────────────────────────────────────────────────

def _template_statistical(
    plan: ForecastPlan,
    profile: DataProfile,
) -> GeneratedCode:
    """Generate code for ForecasterStats (Auto-ARIMA)."""

    target = _get_target_str(profile)
    m = _get_seasonal_period(profile.frequency)
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
    core_lines.append('    f"Train dates : {data_train.index.min()} --- '
                 '{data_train.index.max()}  (n={len(data_train)})"')
    core_lines.append(")")
    core_lines.append("print(")
    core_lines.append('    f"Test dates  : {data_test.index.min()} --- '
                 '{data_test.index.max()}  (n={len(data_test)})"')
    core_lines.append(")")
    core_lines.append("")

    # --- Create forecaster ---
    arima_defaults: dict[str, object] = {"order": None, "seasonal_order": None}
    if m is not None:
        arima_defaults["m"] = m
    arima_kwargs = {**arima_defaults, **(plan.estimator_kwargs or {})}
    arima_params = ", ".join(f"{k}={repr(v)}" for k, v in arima_kwargs.items())
    estimator_str = f"Arima({arima_params})"

    core_lines.append("# Create forecaster (Auto-ARIMA)")
    core_lines.append("forecaster = ForecasterStats(")
    core_lines.append(f"    estimator = {estimator_str},")
    core_lines.append(")")
    core_lines.append("")

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

    return GeneratedCode(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Template: foundation
# ─────────────────────────────────────────────────────────────────────

def _template_foundation(
    plan: ForecastPlan,
    profile: DataProfile,
) -> GeneratedCode:
    """Generate code for ForecasterFoundation (Chronos-2, TimesFM, Moirai, TabICL)."""

    target = _get_target_str(profile)
    foundation_defaults = {
        "model_id": "autogluon/chronos-2-small",
        "context_length": 8192,
    }
    foundation_kwargs = {**foundation_defaults, **(plan.estimator_kwargs or {})}
    model_id = foundation_kwargs["model_id"]
    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    # Multi-series: if profile has multiple target columns (wide format)
    is_multi_series = isinstance(profile.target, list) and len(profile.target) > 1

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    import_lines.append("import pandas as pd")
    import_lines.extend(_get_metric_imports(plan.metrics_to_compute))
    import_lines.append(
        "from skforecast.foundation import FoundationModel, ForecasterFoundation"
    )
    import_lines.append("")

    # --- Load data ---
    _emit_data_loading(loading_lines, profile)

    # --- Index setup (runs in both standalone and exec modes) ---
    _emit_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Series / exog extraction ---
    if is_multi_series:
        target_cols_repr = repr(profile.target)
        core_lines.append(f"series = data[{target_cols_repr}]")
    else:
        core_lines.append(f"series = data[{repr(target)}]")
    if use_exog:
        exog_cols_repr = repr(exog_columns)
        core_lines.append(f"exog = data[{exog_cols_repr}]")
    core_lines.append("")

    # --- Train/test split ---
    core_lines.append("# Train/test split")
    _emit_end_train(core_lines, profile)
    core_lines.append("series_train = series.loc[:end_train]")
    core_lines.append("series_test  = series.loc[series.index > end_train]")
    if use_exog:
        core_lines.append("exog_train = exog.loc[:end_train]")
        core_lines.append("exog_test  = exog.loc[exog.index > end_train]")
    core_lines.append("")

    # --- Create foundation model ---
    core_lines.append(f"# Create foundation model ({str(model_id).split('/')[-1]})")
    model_kwargs_pairs: list[tuple[str, str]] = [
        (k, repr(v)) for k, v in foundation_kwargs.items()
    ]
    _emit_aligned_kwargs(core_lines, "model = FoundationModel(", model_kwargs_pairs)
    core_lines.append("")

    # --- Create forecaster ---
    core_lines.append("# Create forecaster")
    core_lines.append("forecaster = ForecasterFoundation(estimator=model)")
    core_lines.append("")

    # --- Fit ---
    core_lines.append("# Fit (stores context only — no training)")
    if use_exog:
        core_lines.append("forecaster.fit(series=series_train, exog=exog_train)")
    else:
        core_lines.append("forecaster.fit(series=series_train)")
    core_lines.append("")

    # --- Predict ---
    if plan.interval_method is not None:
        # Derive quantiles from interval if provided
        if plan.interval is not None:
            quantiles = [round(v / 100, 2) for v in plan.interval]
            # Add median if not present
            if 0.5 not in quantiles:
                quantiles = sorted([quantiles[0], 0.5, quantiles[1]])
        else:
            quantiles = [0.1, 0.5, 0.9]
        quantiles_repr = repr(quantiles)
        core_lines.append("# Predict quantiles (native)")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if use_exog:
            predict_kwargs.append(("exog", "exog_test"))
        if is_multi_series:
            predict_kwargs.append(("levels", repr(profile.target)))
        predict_kwargs.append(("quantiles", quantiles_repr))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_quantiles(", predict_kwargs
        )
    else:
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        predict_args = ["steps=steps"]
        if use_exog:
            predict_args.append("exog=exog_test")
        if is_multi_series:
            predict_args.append(f"levels={repr(profile.target)}")
        core_lines.append(f"predictions = forecaster.predict({', '.join(predict_args)})")
    core_lines.append("print(predictions)")
    core_lines.append("")
    _emit_metrics_section_foundation(
        core_lines,
        is_multi_series=is_multi_series,
        has_intervals=plan.interval_method is not None,
        test_var="series_test",
        train_var="series_train",
        metrics_to_compute=plan.metrics_to_compute,
    )
    core_lines.append("")
    _emit_production_note(core_lines, use_exog=use_exog, is_foundation=True)
    core_lines.append("")

    return GeneratedCode(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


# ─────────────────────────────────────────────────────────────────────
# Dispatch table
# ─────────────────────────────────────────────────────────────────────

_TEMPLATE_DISPATCH: dict[str, Callable[[ForecastPlan, DataProfile], GeneratedCode]] = {
    "single_series": _template_single_series,
    "multi_series": _template_multi_series,
    "multivariate": _template_multivariate,
    "statistical": _template_statistical,
    "foundation": _template_foundation,
}


def generate_template(
    profile: DataProfile,
    plan: ForecastPlan,
) -> GeneratedCode:
    """
    Generate structured code from a plan and data profile.

    Parameters
    ----------
    profile : DataProfile
        Profile of the input dataset.
    plan : ForecastPlan
        Validated forecast plan.

    Returns
    -------
    generated : GeneratedCode
        Structured code split into imports, data_loading, and core
        sections.
    """
    template_fn = _TEMPLATE_DISPATCH.get(plan.task_type)
    if template_fn is None:
        supported = list(_TEMPLATE_DISPATCH.keys())
        raise ValueError(
            f"Unsupported task_type '{plan.task_type}'. "
            f"Supported types: {supported}"
        )
    return template_fn(plan, profile)
