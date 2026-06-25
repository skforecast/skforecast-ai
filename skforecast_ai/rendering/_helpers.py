"""Shared helpers for script rendering."""


from ..schemas import DataProfile, ForecastPlan


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
    return "[0.1, 0.9]  # default 80% prediction interval"


def _format_lags(lags: object) -> str:
    """
    Render the `lags` value as a compact code literal.

    A list of consecutive integers starting at 1 (for example `[1, 2, 3, 4]`)
    is collapsed to a single integer (`4`), since skforecast expands an integer
    `n` into lags 1 to `n`. Any other value is rendered with `str`.

    Parameters
    ----------
    lags : object
        The `lags` value taken from the forecaster kwargs. Typically an int,
        a list of ints, or None.

    Returns
    -------
    lags_repr : str
        Code literal for the `lags` argument.
    """
    if isinstance(lags, list) and lags == list(range(1, len(lags) + 1)) and len(lags) > 1:
        return str(len(lags))
    return str(lags)


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


def _emit_calendar_features(lines: list[str], calendar_features: dict) -> None:
    """Append CalendarFeatures construction code.

    `keep_original_columns` is intentionally omitted: when `X` is a
    `DatetimeIndex` there are no original columns to keep, so the argument
    has no effect.
    """
    if not calendar_features:
        return

    features = calendar_features.get("features")
    if not features:
        return

    encoding = calendar_features.get("encoding")
    encoding_repr = repr(encoding) if encoding is not None else "None"

    lines.append("calendar_features = CalendarFeatures(")
    lines.append(f"    features = {features},")
    lines.append(f"    encoding = {encoding_repr},")
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


def _emit_imports_single_series(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
    include_metrics: bool = False,
    include_backtesting: bool = False,
) -> None:
    """Append import lines for single-series forecasting scripts.

    Parameters
    ----------
    lines : list of str
        Output list to append import lines to.
    plan : ForecastPlan
        Forecast plan containing estimator, forecaster, and forecaster kwargs.
    profile : DataProfile
        Data profile for column transformer detection.
    include_metrics : bool, default False
        If True, include metric import lines based on `plan.metrics_to_compute`.
    include_backtesting : bool, default False
        If True, append `TimeSeriesFold, backtesting_forecaster` from
        `skforecast.model_selection` as the last import.

    """

    forecaster_class = plan.forecaster
    forecaster_module = "direct" if forecaster_class == "ForecasterDirect" else "recursive"

    kwargs = plan.forecaster_kwargs
    transformer_y = kwargs.get("transformer_y")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")
    calendar_features = kwargs.get("calendar_features")
    estimator_import = _get_estimator_import(plan.estimator)

    lines.append("import pandas as pd")
    if transformer_y or transformer_exog:
        lines.append("from sklearn.preprocessing import StandardScaler")
    if transformer_exog and _needs_column_transformer(profile):
        lines.append("from sklearn.compose import make_column_transformer")
    if include_metrics:
        lines.extend(_get_metric_imports(plan.metrics_to_compute))
    lines.append(estimator_import)
    preprocessing_imports: list[str] = []
    if window_features:
        preprocessing_imports.append("RollingFeatures")
    if calendar_features:
        preprocessing_imports.append("CalendarFeatures")
    if preprocessing_imports:
        lines.append(
            "from skforecast.preprocessing import "
            + ", ".join(preprocessing_imports)
        )
    lines.append(f"from skforecast.{forecaster_module} import {forecaster_class}")
    if include_backtesting:
        lines.append(
            "from skforecast.model_selection import "
            "TimeSeriesFold, backtesting_forecaster"
        )
    lines.append("")


def _emit_imports_multi_series(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
    include_metrics: bool = False,
    include_backtesting: bool = False,
) -> None:
    """Append import lines for multi-series and multivariate forecasting scripts.

    Parameters
    ----------
    lines : list of str
        Output list to append import lines to.
    plan : ForecastPlan
        Forecast plan containing estimator, forecaster, and forecaster kwargs.
    profile : DataProfile
        Data profile for column transformer and format detection.
    include_metrics : bool, default False
        If True, include metric import lines based on `plan.metrics_to_compute`.
    include_backtesting : bool, default False
        If True, append `TimeSeriesFold, backtesting_forecaster_multiseries`
        from `skforecast.model_selection` as the last import.

    """

    forecaster_class = plan.forecaster
    is_multi_series = forecaster_class == "ForecasterRecursiveMultiSeries"
    forecaster_module = "recursive" if is_multi_series else "direct"
    is_wide = profile.data_format == "wide"

    kwargs = plan.forecaster_kwargs
    transformer_series = kwargs.get("transformer_series")
    transformer_exog = kwargs.get("transformer_exog")
    window_features = kwargs.get("window_features")
    calendar_features = kwargs.get("calendar_features")
    estimator_import = _get_estimator_import(plan.estimator)

    lines.append("import pandas as pd")
    if transformer_series or transformer_exog:
        lines.append("from sklearn.preprocessing import StandardScaler")
    if transformer_exog and _needs_column_transformer(profile):
        lines.append("from sklearn.compose import make_column_transformer")
    if include_metrics:
        lines.extend(_get_metric_imports(plan.metrics_to_compute))
    lines.append(estimator_import)

    preprocessing_imports: list[str] = []
    if window_features:
        preprocessing_imports.append("RollingFeatures")
    if calendar_features:
        preprocessing_imports.append("CalendarFeatures")
    if is_multi_series and not is_wide:
        preprocessing_imports.append("reshape_series_long_to_dict")
        if plan.use_exog and profile.exog_columns:
            preprocessing_imports.append("reshape_exog_long_to_dict")
    if preprocessing_imports:
        lines.append(
            "from skforecast.preprocessing import "
            + ", ".join(preprocessing_imports)
        )

    lines.append(f"from skforecast.{forecaster_module} import {forecaster_class}")
    if include_backtesting:
        lines.append(
            "from skforecast.model_selection import "
            "TimeSeriesFold, backtesting_forecaster_multiseries"
        )
    lines.append("")


def _emit_imports_foundation(
    lines: list[str],
    plan: ForecastPlan,
    include_metrics: bool = False,
    include_backtesting: bool = False,
) -> None:
    """Append import lines for foundation model forecasting scripts.

    Parameters
    ----------
    lines : list of str
        Output list to append import lines to.
    plan : ForecastPlan
        Forecast plan containing metrics_to_compute.
    include_metrics : bool, default False
        If True, include metric import lines based on `plan.metrics_to_compute`.
    include_backtesting : bool, default False
        If True, append `TimeSeriesFold, backtesting_foundation` from
        `skforecast.model_selection` as the last import.

    """

    lines.append("import pandas as pd")
    if include_metrics:
        lines.extend(_get_metric_imports(plan.metrics_to_compute))
    lines.append(
        "from skforecast.foundation import FoundationModel, ForecasterFoundation"
    )
    if include_backtesting:
        lines.append(
            "from skforecast.model_selection import "
            "TimeSeriesFold, backtesting_foundation"
        )
    lines.append("")


def _emit_imports_statistical(
    lines: list[str],
    plan: ForecastPlan,
    include_metrics: bool = False,
    include_backtesting: bool = False,
) -> None:
    """Append import lines for statistical forecasting scripts.

    Parameters
    ----------
    lines : list of str
        Output list to append import lines to.
    plan : ForecastPlan
        Forecast plan containing metrics_to_compute.
    include_metrics : bool, default False
        If True, include metric import lines based on `plan.metrics_to_compute`.
    include_backtesting : bool, default False
        If True, append `TimeSeriesFold, backtesting_stats` from
        `skforecast.model_selection` as the last import.

    """

    lines.append("import pandas as pd")
    if include_metrics:
        lines.extend(_get_metric_imports(plan.metrics_to_compute))
    lines.append("from skforecast.stats import Arima")
    lines.append("from skforecast.recursive import ForecasterStats")
    if include_backtesting:
        lines.append(
            "from skforecast.model_selection import "
            "TimeSeriesFold, backtesting_stats"
        )
    lines.append("")


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
