"""Shared helpers for script rendering."""

################################################################################
#                                 Helpers                                      #
#                                                                              #
# Shared helpers for script rendering                                          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

import numbers
import unicodedata
from ..schemas import DataProfile, ForecastPlan
from .._constants import (
    BLOCKING_PREPROCESSING_TEMPLATES,
    FREQUENCY_TO_SEASONAL_PERIOD,
    PLACEHOLDER_DATA_PATH,
    SUPPORTED_ESTIMATORS,
    SUPPORTED_TRANSFORMERS,
)
from .._validation import validate_kwarg_names
from ..exceptions import InvalidInputError

# Render boundary: a value from a plan, a profile or a cross-validation
# object reaches a script only through `repr()`, as a constant of one of the
# closed maps below, as `str()` of a validated int or bool, or inside a
# comment through `_comment_text()`. A name that is not in a map raises
# instead of being written.

_ESTIMATOR_IMPORTS: dict[str, str] = {
    name: f"from {module} import {name}"
    for name, module in SUPPORTED_ESTIMATORS.items()
}

_FORECASTER_IMPORTS: dict[str, str] = {
    "ForecasterRecursive": "from skforecast.recursive import ForecasterRecursive",
    "ForecasterDirect": "from skforecast.direct import ForecasterDirect",
    "ForecasterRecursiveMultiSeries": (
        "from skforecast.recursive import ForecasterRecursiveMultiSeries"
    ),
    "ForecasterDirectMultiVariate": (
        "from skforecast.direct import ForecasterDirectMultiVariate"
    ),
}

# Forecasters each family of renderers builds.
_SINGLE_SERIES_FORECASTERS: tuple[str, ...] = (
    "ForecasterRecursive",
    "ForecasterDirect",
)
_MULTI_SERIES_FORECASTERS: tuple[str, ...] = (
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
)

# Target transformers a plan can name (`transformer_y`, `transformer_series`).
_TRANSFORMER_CONSTRUCTORS: dict[str, str] = {
    name: f"{name}()" for name in SUPPORTED_TRANSFORMERS
}

# Interval methods written into `predict_interval` and the backtesting call.
# `'native'` intervals (statistical and foundation models) take no method.
_INTERVAL_METHOD_LITERALS: dict[str, str] = {
    "bootstrapping": "'bootstrapping'",
    "conformal": "'conformal'",
}

# Unicode categories escaped in comments: control characters (newlines,
# carriage return, NUL) and the line and paragraph separators. Any of them
# would end the comment and turn the rest of the text into code.
_COMMENT_ESCAPED_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})

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
    "mean_squared_log_error": {
        "import": "from sklearn.metrics import mean_squared_log_error",
        "var": "msle",
        "label": "MSLE",
        "call": "mean_squared_log_error(actual, {pred_expr})",
        "requires_y_train": False,
    },
    "median_absolute_error": {
        "import": "from sklearn.metrics import median_absolute_error",
        "var": "medae",
        "label": "MedAE",
        "call": "median_absolute_error(actual, {pred_expr})",
        "requires_y_train": False,
    },
    "symmetric_mean_absolute_percentage_error": {
        "import": (
            "from skforecast.metrics import "
            "symmetric_mean_absolute_percentage_error"
        ),
        "var": "smape",
        "label": "SMAPE",
        "call": "symmetric_mean_absolute_percentage_error(actual, {pred_expr})",
        "requires_y_train": False,
    },
    "root_mean_squared_scaled_error": {
        "import": "from skforecast.metrics import root_mean_squared_scaled_error",
        "var": "rmsse",
        "label": "RMSSE",
        "call": (
            "root_mean_squared_scaled_error(\n"
            "    y_true  = actual,\n"
            "    y_pred  = {pred_expr},\n"
            "    y_train = {train_expr},\n"
            ")"
        ),
        "requires_y_train": True,
    },
}


def _metric_info(metric: str) -> dict[str, str | bool]:
    """
    Look up how a metric is imported, named and computed in the scripts.

    Parameters
    ----------
    metric : str
        Metric name.

    Returns
    -------
    info : dict
        Registry entry of the metric.

    Notes
    -----
    An unknown metric raises a `ValueError` instead of being left out of
    the script: plans are validated before rendering, so reaching this
    means the registry and `ALLOWED_METRICS` have drifted apart.
    """
    if metric not in _METRIC_REGISTRY:
        raise InvalidInputError(
            f"Metric {metric!r} cannot be rendered. Supported metrics: "
            f"{list(_METRIC_REGISTRY)}.",
            field = "metric",
        )
    return _METRIC_REGISTRY[metric]


def _comment_text(text: str) -> str:
    """
    Make text safe to write inside a `#` comment of a generated script.

    Characters of the Unicode categories Cc, Zl and Zp (newlines, NUL and
    other control characters, line and paragraph separators) are written as
    their escape sequence (`'\\n'` becomes the two characters `\\n`), so a
    column name or a model ID taken from the data cannot end the comment
    and start a statement. Any other text is returned unchanged.

    Parameters
    ----------
    text : str
        Text of the comment, `#` included or not.

    Returns
    -------
    text : str
        The same text on a single line.
    """
    return "".join(
        char.encode("unicode_escape").decode("ascii")
        if unicodedata.category(char) in _COMMENT_ESCAPED_CATEGORIES
        else char
        for char in text
    )


def _format_int(value: object, name: str) -> str:
    """
    Render an integer argument (`steps`, a cross-validation size) as a code
    literal.

    Parameters
    ----------
    value : int
        Value to write. Numpy integers and integral floats (`12.0`) are
        accepted.
    name : str
        Argument name, quoted in the error message.

    Returns
    -------
    literal : str
        The value as a Python integer literal.

    Notes
    -----
    Anything else (a bool, a string, `2.9`) raises a `ValueError` instead of
    being written or silently truncated: plans and folds are validated
    before rendering, so reaching this means one skipped that validation.
    """
    is_integral = (
        not isinstance(value, bool)
        and isinstance(value, numbers.Real)
        and (isinstance(value, numbers.Integral) or float(value).is_integer())
    )
    if not is_integral:
        raise InvalidInputError(
            f"`{name}` must be an integer, got {value!r}.",
            field = name,
        )
    return str(int(value))


def _format_bool(value: object, name: str) -> str:
    """
    Render a boolean argument as a code literal.

    Parameters
    ----------
    value : bool
        Value to write.
    name : str
        Argument name, quoted in the error message.

    Returns
    -------
    literal : str
        `'True'` or `'False'`.

    Notes
    -----
    Anything other than a bool raises a `ValueError` instead of being
    written.
    """
    if not isinstance(value, bool):
        raise InvalidInputError(
            f"`{name}` must be a bool, got {value!r}.",
            field = name,
        )
    return repr(value)


def _get_forecaster_import(
    forecaster: str,
    supported: tuple[str, ...],
) -> str:
    """
    Resolve the import line of a forecaster the renderer builds.

    Parameters
    ----------
    forecaster : str
        Forecaster class name of the plan.
    supported : tuple of str
        Forecasters of the renderer family (`_SINGLE_SERIES_FORECASTERS` or
        `_MULTI_SERIES_FORECASTERS`).

    Returns
    -------
    import_line : str
        Constant import line from `_FORECASTER_IMPORTS`.

    Notes
    -----
    Any other name raises a `ValueError` instead of being written into the
    script: plans are validated before rendering, so reaching this means a
    plan skipped that validation.
    """
    if not isinstance(forecaster, str) or forecaster not in supported:
        raise InvalidInputError(
            f"{forecaster!r} cannot be rendered by this script template. "
            f"Supported forecasters: {list(supported)}.",
            field = "forecaster",
        )
    return _FORECASTER_IMPORTS[forecaster]


def _get_transformer_constructor(transformer: str) -> str:
    """
    Resolve the constructor call of a target transformer.

    Parameters
    ----------
    transformer : str
        Transformer class name of the plan (`transformer_y` or
        `transformer_series`).

    Returns
    -------
    constructor : str
        Constant constructor call from `_TRANSFORMER_CONSTRUCTORS`.

    Notes
    -----
    Any other name raises a `ValueError` instead of being written into the
    script.
    """
    if (
        not isinstance(transformer, str)
        or transformer not in _TRANSFORMER_CONSTRUCTORS
    ):
        raise InvalidInputError(
            f"{transformer!r} is not a supported transformer. Supported "
            f"transformers: {list(_TRANSFORMER_CONSTRUCTORS)}.",
            field = "forecaster_kwargs",
        )
    return _TRANSFORMER_CONSTRUCTORS[transformer]


def _get_interval_method_literal(interval_method: str) -> str:
    """
    Resolve the code literal of the interval method of a plan.

    Parameters
    ----------
    interval_method : str
        Interval method of the plan.

    Returns
    -------
    literal : str
        Constant literal from `_INTERVAL_METHOD_LITERALS`.

    Notes
    -----
    Any other value raises a `ValueError` instead of being written into the
    script.
    """
    if (
        not isinstance(interval_method, str)
        or interval_method not in _INTERVAL_METHOD_LITERALS
    ):
        raise InvalidInputError(
            f"Interval method {interval_method!r} cannot be rendered. "
            f"Supported methods: {list(_INTERVAL_METHOD_LITERALS)}.",
            field = "interval_method",
        )
    return _INTERVAL_METHOD_LITERALS[interval_method]


def _get_seasonal_period(frequency: str | None) -> int | None:
    """Return seasonal period m for the given pandas frequency string."""
    if frequency is None:
        return None
    return FREQUENCY_TO_SEASONAL_PERIOD.get(frequency)


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
    `n` into lags 1 to `n`. Any other value is rendered with `repr`.

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
    return repr(lags)


def _emit_preprocessing_steps(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """
    Append blocking preprocessing steps after data loading.

    The snippet of each blocking step must be one of the closed templates of
    `BLOCKING_PREPROCESSING_TEMPLATES`, matched together with its action;
    anything else raises a `ValueError` instead of being written. The
    template placeholders are filled with `repr()` of the profile columns,
    so a column name with a quote stays inside its string literal.
    """
    blocking = [s for s in plan.preprocessing_steps if s.blocking]
    if not blocking:
        return

    replacements = {
        "date_column": repr(profile.date_column),
        "series_id_column": repr(profile.series_id_column),
    }

    lines.append("# Preprocessing")
    for step in blocking:
        if (step.action, step.code_snippet) not in BLOCKING_PREPROCESSING_TEMPLATES:
            raise InvalidInputError(
                f"The blocking preprocessing step {step.action!r} is not one "
                f"of the steps the scripts can contain, so its code snippet "
                f"is not written into the script. Build the plan with "
                f"`plan()`, or remove the step.",
                field = "preprocessing_steps",
            )
        snippet = step.code_snippet.format_map(replacements)
        for snippet_line in snippet.split("\n"):
            lines.append(snippet_line)

    # After deduplication, set the frequency that was deferred during loading.
    # Long-format data gets its frequency when the series are reshaped.
    if (
        profile.has_duplicate_timestamps
        and profile.frequency
        and profile.data_format != "long"
    ):
        lines.append(f"data = data.asfreq({profile.frequency!r})")

    lines.append("")


def _emit_data_loading(
    lines: list[str],
    profile: DataProfile,
    long_format: bool = False,
    *,
    var: str = "data",
    path: str | None = None,
    comment: str = "# Load data",
) -> None:
    """
    Append CSV-loading code lines (only the read_csv call).

    The CSV is read with `index_col=0, parse_dates=True` only when there is
    no `date_column` in wide format and the index is stored in the file:
    for the future exogenous variables (`path` given), for a datetime
    index, and for data passed in memory (the placeholder `data_path`,
    the frame saved with `to_csv()`). A CSV read by path without dates
    holds no index, so it is read as is.

    Parameters
    ----------
    lines : list
        Output list of code lines to append to.
    profile : DataProfile
        Data profile with `data_path`, `date_column` and `index_type`.
    long_format : bool, default False
        Whether the data is in long format, which always has its dates in a
        column and is read as is.
    var : str, default 'data'
        Name of the variable to assign the loaded frame to. Allows the
        same loader to be reused for the future exogenous frame
        (`var='exog_future'`).
    path : str, default None
        CSV path to read from. Defaults to `profile.data_path`.
    comment : str, default '# Load data'
        Comment header emitted above the read_csv call.

    Returns
    -------
    None
    
    """

    data_path = profile.data_path if path is None else path
    date_col = profile.date_column

    # Without a date column the index is saved as the first column of the
    # CSV. A CSV read by path without dates was read with a row index that
    # it does not store, so its first column is data and not an index. Data
    # passed in memory (the placeholder path) keeps the index read, the
    # frame saved with `to_csv()`, and so do the future exogenous variables,
    # which must carry the positions that follow the data.
    index_read = not date_col and (
        path is not None
        or profile.index_type == "datetime"
        or profile.data_path == PLACEHOLDER_DATA_PATH
    )

    lines.append(comment)
    if long_format or not index_read:
        lines.append(f"{var} = pd.read_csv({repr(data_path)})")
    else:
        lines.append(
            f"{var} = pd.read_csv({repr(data_path)}, index_col=0, parse_dates=True)"
        )
    lines.append("")


def _emit_index_setup(
    lines: list[str],
    profile: DataProfile,
    long_format: bool = False,
    *,
    var: str = "data",
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
    var : str, default 'data'
        Name of the variable to prepare. Allows the same preparation to
        be reused for the future exogenous frame (`var='exog_future'`).

    Returns
    -------
    None
    
    """

    date_col = profile.date_column
    frequency = profile.frequency

    if long_format:
        if date_col:
            lines.append(
                f"{var}[{repr(date_col)}] = pd.to_datetime({var}[{repr(date_col)}])"
            )
            lines.append(f"{var} = {var}.sort_values({repr(date_col)})")
        lines.append("")
    else:
        if date_col:
            lines.append(
                f"{var}[{repr(date_col)}] = pd.to_datetime({var}[{repr(date_col)}])"
            )
            lines.append(f"{var} = {var}.set_index({repr(date_col)})")
        if frequency and not profile.has_duplicate_timestamps:
            lines.append(f"{var} = {var}.asfreq({frequency!r})")
        lines.append(f"{var} = {var}.sort_index()")
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
        window_size = wf.get("window_size")
        for stat in stats:
            all_stats.append(stat)
            all_window_sizes.append(window_size)

    lines.append("window_features = RollingFeatures(")
    lines.append(f"    stats        = {all_stats!r},")
    lines.append(f"    window_sizes = {all_window_sizes!r},")
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
    lines.append(f"    features = {features!r},")
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
    plan: ForecastPlan,
) -> None:
    """Emit the `end_train` variable (date-based split point).

    Raises `ValueError` if `plan.end_train` is not set because the
    evaluation code must contain a concrete date literal.
    """
    if plan.end_train is None:
        raise InvalidInputError(
            "plan.end_train must be set to generate evaluation code. "
            "Pass `test_size` so the train/test split date is computed.",
            field = "end_train",
        )
    lines.append(
        f"end_train = {repr(plan.end_train)}"
        "  # last training date, adjust to change the split point"
    )


def _emit_split_dates(lines: list[str]) -> None:
    """Emit the prints of the train and test date ranges of `data`."""
    lines.append("print(")
    lines.append(
        '    f"Train dates : {data_train.index.min()} --- '
        '{data_train.index.max()}  (n={len(data_train)})"'
    )
    lines.append(")")
    lines.append("print(")
    lines.append(
        '    f"Test dates  : {data_test.index.min()} --- '
        '{data_test.index.max()}  (n={len(data_test)})"'
    )
    lines.append(")")
    lines.append("")


def _emit_future_exog_loading(
    lines: list[str],
    profile: DataProfile,
) -> None:
    """Emit code loading future exogenous variables (prediction mode).

    Delegates to `_emit_data_loading` so `exog_future` is loaded exactly
    like `data` (same `date_column`-driven read). Only used by the
    standalone script (`full_script`); in exec mode the `exog_future`
    variable is injected directly into the namespace.
    """
    _emit_data_loading(
        lines,
        profile,
        var="exog_future",
        path="exog_future.csv",
        comment="# Load future exogenous variables covering the forecast horizon",
    )


def _emit_future_exog_index_setup(
    lines: list[str],
    profile: DataProfile,
    long_format: bool = False,
) -> None:
    """Append index-setup code for the future exogenous variables.

    Delegates to `_emit_index_setup` so `exog_future` is prepared exactly
    like `data` (`to_datetime`/`set_index` when a date column is used,
    then `asfreq` + `sort_index`; in long format, `to_datetime` and
    `sort_values`). Emitted into the core code so it runs both in
    standalone scripts and in exec mode, putting the future exogenous
    variables on the same regular, sorted grid as the training data, as
    required by skforecast. In long format the dates read from
    `exog_future.csv` are text until parsed, and the reshape to a dict
    would not match them with the dates to predict.
    """
    _emit_index_setup(lines, profile, long_format=long_format, var="exog_future")


def _get_metric_imports(metrics_to_compute: list[str]) -> list[str]:
    """
    Build deduplicated import lines for the requested metrics.

    Groups sklearn imports on a single line when possible.
    """
    sklearn_funcs: list[str] = []
    skforecast_imports: list[str] = []

    for m in metrics_to_compute:
        info = _metric_info(m)
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
        info = _metric_info(m)
        call = info["call"].format(pred_expr=pred_expr, train_expr=train_expr)
        lines.append(f"{info['var']} = {call}")

    lines.append("")
    for m in metrics_to_compute:
        info = _metric_info(m)
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
        info = _metric_info(m)
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

    # `predict` and `predict_interval` both return the median as `pred`.
    if is_multi_series:
        lines.append("# Evaluate on test set (per series)")
        lines.append("metrics_list = []")
        lines.append("for level in predictions['level'].unique():")
        lines.append("    mask = predictions['level'] == level")
        lines.append(
            "    pred = predictions.loc[mask, 'pred'].values"
        )
        lines.append(
            f"    actual = {test_var}[level].iloc[:steps]"
        )
        lines.append("    metrics_list.append({")
        lines.append('        "series": level,')
        for m in metrics_to_compute:
            info = _metric_info(m)
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
            "pred = predictions['pred'].values"
        )
        for m in metrics_to_compute:
            info = _metric_info(m)
            call = info["call"].format(pred_expr="pred", train_expr=train_var)
            lines.append(f"{info['var']} = {call}")
        lines.append("")
        for m in metrics_to_compute:
            info = _metric_info(m)
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

    forecaster_import = _get_forecaster_import(
        plan.forecaster, _SINGLE_SERIES_FORECASTERS
    )

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
    lines.append(forecaster_import)
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

    forecaster_import = _get_forecaster_import(
        plan.forecaster, _MULTI_SERIES_FORECASTERS
    )
    is_multi_series = plan.forecaster == "ForecasterRecursiveMultiSeries"
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

    lines.append(forecaster_import)
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
    profile: DataProfile | None = None,
    use_exog: bool = False,
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
    profile : DataProfile, default None
        Profiled dataset metadata. Long-format data imports the helpers
        that reshape it into one entry per series.
    use_exog : bool, default False
        Whether the script passes exogenous variables, which long-format
        data reshapes with `reshape_exog_long_to_dict`.

    """

    lines.append("import pandas as pd")
    if include_metrics:
        lines.extend(_get_metric_imports(plan.metrics_to_compute))
    if profile is not None and profile.data_format == "long":
        reshape_imports = ["reshape_series_long_to_dict"]
        if use_exog:
            reshape_imports.append("reshape_exog_long_to_dict")
        lines.append(
            "from skforecast.preprocessing import " + ", ".join(reshape_imports)
        )
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


def _emit_imports_baseline(
    lines: list[str],
    plan: ForecastPlan,
    include_metrics: bool = False,
    include_backtesting: bool = False,
) -> None:
    """Append import lines for baseline (`ForecasterEquivalentDate`) scripts.

    Parameters
    ----------
    lines : list of str
        Output list to append import lines to.
    plan : ForecastPlan
        Forecast plan containing metrics_to_compute.
    include_metrics : bool, default False
        If True, include metric import lines based on `plan.metrics_to_compute`.
    include_backtesting : bool, default False
        If True, append `TimeSeriesFold, backtesting_forecaster` from
        `skforecast.model_selection` as the last import.

    """

    lines.append("import pandas as pd")
    if include_metrics:
        lines.extend(_get_metric_imports(plan.metrics_to_compute))
    lines.append("from skforecast.recursive import ForecasterEquivalentDate")
    if include_backtesting:
        lines.append(
            "from skforecast.model_selection import "
            "TimeSeriesFold, backtesting_forecaster"
        )
    lines.append("")


def _get_estimator_import(estimator: str | None) -> str:
    """Resolve the estimator import line.

    An estimator without a known import raises instead of writing its name
    into the script: plans are validated before rendering, so reaching this
    means a plan skipped that validation.
    """
    if estimator not in _ESTIMATOR_IMPORTS:
        raise InvalidInputError(
            f"{estimator!r} is not a supported estimator. Supported "
            f"estimators: {list(_ESTIMATOR_IMPORTS)}.",
            field = "estimator",
        )
    return _ESTIMATOR_IMPORTS[estimator]


def _get_estimator_constructor(
    estimator: str | None,
    estimator_kwargs: dict[str, object] | None = None,
) -> str:
    """Return estimator constructor call with merged kwargs.

    Merges built-in defaults (silencing, random_state) with user-provided
    kwargs. User kwargs take precedence over defaults. The estimator must be
    one the script can import and every key a Python parameter name; the
    values are written with `repr()`.
    """
    _get_estimator_import(estimator)
    validate_kwarg_names(estimator_kwargs)
    name = estimator
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


def _emit_loading_and_index(
    loading_lines: list[str],
    core_lines: list[str],
    profile: DataProfile,
    *,
    long_format: bool = False,
) -> None:
    """
    Append the data loading and the index setup blocks.

    Loading goes to the standalone-only section; index setup goes to the
    core section, which runs in both standalone and exec modes.

    Parameters
    ----------
    loading_lines : list of str
        Data loading lines to append to (modified in place).
    core_lines : list of str
        Core code lines to append to (modified in place).
    profile : DataProfile
        Profiled dataset metadata.
    long_format : bool, default False
        Whether the data is in long format (one row per series and
        timestamp).

    Returns
    -------
    None
    """

    _emit_data_loading(loading_lines, profile, long_format=long_format)
    _emit_index_setup(core_lines, profile, long_format=long_format)


def _emit_feature_setup(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
    *,
    use_exog: bool,
) -> None:
    """
    Append the window features, calendar features and exog transformer.

    Shared by the forecast and backtesting renderers of every
    autoregressive forecaster, which emit the same three blocks before
    creating the forecaster.

    Parameters
    ----------
    lines : list of str
        Code lines to append to (modified in place).
    plan : ForecastPlan
        Forecast plan carrying `forecaster_kwargs`.
    profile : DataProfile
        Profiled dataset metadata.
    use_exog : bool
        Whether exogenous variables are used, which gates the transformer.

    Returns
    -------
    None
    """

    kwargs = plan.forecaster_kwargs

    window_features = kwargs.get("window_features")
    if window_features and isinstance(window_features, list):
        _emit_window_features(lines, window_features)
        lines.append("")

    if kwargs.get("calendar_features"):
        _emit_calendar_features(lines, kwargs["calendar_features"])
        lines.append("")

    transformer_exog = kwargs.get("transformer_exog")
    if transformer_exog and use_exog:
        _emit_transformer_exog(lines, transformer_exog, profile)


def _emit_pivot_to_wide(lines: list[str], profile: DataProfile) -> None:
    """
    Append the pivot from long format to a wide `series` frame.

    Used by the multivariate renderers, whose forecaster needs one column
    per series.

    Parameters
    ----------
    lines : list of str
        Code lines to append to (modified in place).
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    None
    """

    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "datetime"
    target = _get_target_str(profile)

    lines.append("# Pivot to wide format (columns = series)")
    lines.append("series = data.pivot_table(")
    lines.append(
        f"    index={repr(date_col)}, columns={repr(series_id)},"
        f" values={repr(target)}"
    )
    lines.append(")")
    lines.append("series.index.name = None")
    lines.append("series.columns.name = None")
    if profile.frequency:
        lines.append(f"series = series.asfreq({profile.frequency!r})")
    lines.append("")


def _emit_reshape_series_long_to_dict(
    lines: list[str],
    profile: DataProfile,
    *,
    comment: str,
) -> None:
    """
    Append the `reshape_series_long_to_dict` call building `series_dict`.

    Parameters
    ----------
    lines : list of str
        Code lines to append to (modified in place).
    profile : DataProfile
        Profiled dataset metadata (long format).
    comment : str
        Comment line emitted before the call.

    Returns
    -------
    None
    """

    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "datetime"
    target = _get_target_str(profile)

    lines.append(comment)
    lines.append("series_dict = reshape_series_long_to_dict(")
    lines.append("    data      = data,")
    lines.append(f"    series_id = {repr(series_id)},")
    lines.append(f"    index     = {repr(date_col)},")
    lines.append(f"    values    = {repr(target)},")
    lines.append(f"    freq      = {repr(profile.frequency)},")
    lines.append(")")


def _emit_series_dict(
    lines: list[str],
    profile: DataProfile,
    *,
    comment: str,
) -> None:
    """
    Append the code that builds `series_dict`, one entry per series.

    Wide data is split by column; long data is reshaped with
    `reshape_series_long_to_dict`.

    Parameters
    ----------
    lines : list of str
        Code lines to append to (modified in place).
    profile : DataProfile
        Profiled dataset metadata (wide or long format).
    comment : str
        Comment line emitted before the code.

    Returns
    -------
    None
    """

    if profile.data_format == "wide":
        lines.append(comment)
        if isinstance(profile.target, list):
            lines.append(
                f"series_dict = data[{repr(profile.target)}].to_dict('series')"
            )
        else:
            lines.append("series_dict = data.to_dict('series')")
    else:
        _emit_reshape_series_long_to_dict(lines, profile, comment=comment)


def _emit_train_test_split_multiseries(
    lines: list[str],
    plan: ForecastPlan,
    *,
    is_wide: bool,
    use_exog: bool,
) -> None:
    """
    Append the train/test split of `series_dict` and its exogenous variables.

    Wide data shares one `exog` frame across series; long data has one
    exogenous frame per series in `exog_dict`.

    Parameters
    ----------
    lines : list of str
        Code lines to append to (modified in place).
    plan : ForecastPlan
        Plan in evaluation mode (`end_train` set).
    is_wide : bool
        Whether the data is in wide format.
    use_exog : bool
        Whether exogenous variables are split as well.

    Returns
    -------
    None
    """

    lines.append("# Train/test split")
    _emit_end_train(lines, plan)
    lines.append(
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}"
    )
    lines.append(
        "series_dict_test  = {k: v.loc[v.index > end_train]"
        " for k, v in series_dict.items()}"
    )
    if use_exog:
        if is_wide:
            lines.append("exog_train = exog.loc[:end_train]")
            lines.append("exog_test  = exog.loc[exog.index > end_train]")
        else:
            lines.append(
                "exog_dict_train = {k: v.loc[:end_train]"
                " for k, v in exog_dict.items()}"
            )
            lines.append(
                "exog_dict_test  = {k: v.loc[v.index > end_train]"
                " for k, v in exog_dict.items()}"
            )
    lines.append("")


def _emit_reshape_exog_long_to_dict(
    lines: list[str],
    profile: DataProfile,
    *,
    var: str,
    data_expr: str,
    columns: list[str] | None = None,
) -> None:
    """
    Append a `reshape_exog_long_to_dict` call assigning to `var`.

    Parameters
    ----------
    lines : list of str
        Code lines to append to (modified in place).
    profile : DataProfile
        Profiled dataset metadata (long format).
    var : str
        Name of the variable receiving the dict, e.g. `'exog_dict'`.
    data_expr : str
        Expression of the long-format frame to reshape, e.g. `'data'`.
    columns : list of str, default None
        Exogenous columns to reshape. None reshapes every exogenous column
        of the profile.

    Returns
    -------
    None
    """

    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "datetime"
    exog_columns = profile.exog_columns if columns is None else columns
    exog_select_cols = [series_id, date_col] + list(exog_columns)

    lines.append(f"{var} = reshape_exog_long_to_dict(")
    lines.append(f"    data      = {data_expr}[{repr(exog_select_cols)}],")
    lines.append(f"    series_id = {repr(series_id)},")
    lines.append(f"    index     = {repr(date_col)},")
    lines.append(f"    freq      = {repr(profile.frequency)},")
    lines.append(")")
