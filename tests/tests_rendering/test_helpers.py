# Unit test _helpers rendering

import re

import pytest

from skforecast_ai.rendering._helpers import (
    _comment_text,
    _emit_aligned_kwargs,
    _emit_end_train,
    _emit_preprocessing_steps,
    _emit_window_features,
    _format_lags,
    _get_estimator_constructor,
    _get_estimator_import,
    _get_forecaster_import,
    _get_interval_method_literal,
    _get_interval_repr,
    _get_metric_imports,
    _get_seasonal_period,
    _get_transformer_constructor,
    _MULTI_SERIES_FORECASTERS,
    _needs_column_transformer,
    _SINGLE_SERIES_FORECASTERS,
)
from skforecast_ai.schemas import DataProfile, ForecastPlan, PreprocessingStep


# =============================================================================
# Tests: _get_seasonal_period
# =============================================================================
@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("h", 24),
        ("D", 7),
        ("MS", 12),
        ("ME", 12),
        ("W", 52),
        ("QS", 4),
        ("YE", 1),
        ("15min", 96),
        ("3h", 8),
        ("2W-SUN", 26),
        ("s", 3600),
        ("3D", None),
        ("unknown", None),
        (None, None),
    ],
    ids=lambda x: f"frequency={x}",
)
def test_get_seasonal_period_output_when_different_frequencies(frequency, expected):
    """
    Test that _get_seasonal_period returns the correct seasonal period
    for known frequencies, the first whole cycle of estimate_seasonality
    for multiplied ones ('3h', '2W-SUN'), and None when there is no whole
    cycle ('3D') or for unknown or None inputs.
    """
    assert _get_seasonal_period(frequency) == expected


# =============================================================================
# Tests: _get_interval_repr
# =============================================================================
@pytest.mark.parametrize(
    "interval, expected",
    [
        ([0.1, 0.9], "[0.1, 0.9]"),
        (None, "[0.1, 0.9]  # default 80% prediction interval"),
    ],
    ids=["with_interval", "without_interval"],
)
def test_get_interval_repr_output_when_interval_set_or_none(interval, expected):
    """
    Test that _get_interval_repr returns the exact code literal
    depending on whether plan.interval is set or None.
    """
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        steps=10,
        interval=interval,
        interval_method="bootstrapping" if interval else None,
        explanation="test",
    )
    assert _get_interval_repr(plan) == expected


# =============================================================================
# Tests: _format_lags
# =============================================================================
@pytest.mark.parametrize(
    "lags, expected",
    [
        ([1, 2, 3, 4], "4"),
        ([1, 2], "2"),
        (list(range(1, 73)), "72"),
        ([1, 2, 3, 5], "[1, 2, 3, 5]"),
        ([2, 3, 4], "[2, 3, 4]"),
        ([1], "[1]"),
        (24, "24"),
        (None, "None"),
        ([5, 4, 3, 2, 1], "[5, 4, 3, 2, 1]"),
        ("3) or (7", "'3) or (7'"),
    ],
    ids=lambda x: f"lags={x}",
)
def test_format_lags_output_when_different_inputs(lags, expected):
    """
    Test that _format_lags collapses a consecutive list starting at 1
    into an integer string, and renders any other value with repr, so a
    string stays a string literal.
    """
    assert _format_lags(lags) == expected


# =============================================================================
# Tests: _get_estimator_import
# =============================================================================
@pytest.mark.parametrize(
    "estimator, expected",
    [
        ("LGBMRegressor", "from lightgbm import LGBMRegressor"),
        ("XGBRegressor", "from xgboost import XGBRegressor"),
        ("CatBoostRegressor", "from catboost import CatBoostRegressor"),
        ("RandomForestRegressor", "from sklearn.ensemble import RandomForestRegressor"),
        ("Ridge", "from sklearn.linear_model import Ridge"),
    ],
    ids=lambda e: f"estimator={e}",
)
def test_get_estimator_import_output_when_known(estimator, expected):
    """
    Test that _get_estimator_import returns the correct import line
    for known estimators.
    """
    assert _get_estimator_import(estimator) == expected


def test_get_estimator_import_ValueError_when_unknown():
    """
    Test that _get_estimator_import raises for an estimator without a known
    import instead of writing its name into the script.
    """
    err_msg = re.escape(
        "'MyCustomEstimator' is not a supported estimator. Supported "
        "estimators: ['LGBMRegressor', 'Ridge', 'XGBRegressor', "
        "'CatBoostRegressor', 'RandomForestRegressor', "
        "'HistGradientBoostingRegressor']."
    )
    with pytest.raises(ValueError, match=err_msg):
        _get_estimator_import("MyCustomEstimator")


# =============================================================================
# Tests: _get_estimator_constructor
# =============================================================================
@pytest.mark.parametrize(
    "estimator, kwargs, expected",
    [
        ("LGBMRegressor", {}, "LGBMRegressor(random_state=123, verbose=-1)"),
        ("Ridge", {}, "Ridge()"),
    ],
    ids=["with_defaults", "no_defaults"],
)
def test_get_estimator_constructor_output_when_no_user_kwargs(estimator, kwargs, expected):
    """
    Test that _get_estimator_constructor merges built-in defaults or
    returns empty parens when no defaults exist.
    """
    assert _get_estimator_constructor(estimator, kwargs) == expected


def test_get_estimator_constructor_output_when_user_overrides():
    """
    Test that user-provided kwargs override built-in defaults while
    preserving other defaults.
    """
    result = _get_estimator_constructor(
        "LGBMRegressor", {"n_estimators": 200, "random_state": 42}
    )
    assert "random_state=42" in result
    assert "n_estimators=200" in result
    assert "verbose=-1" in result


@pytest.mark.parametrize(
    "estimator, kwargs, err_msg",
    [
        (
            "Ridge",
            {"alpha=1.0); import os; Ridge(fit_intercept": True},
            "`estimator_kwargs` keys must be valid Python parameter names, "
            "got 'alpha=1.0); import os; Ridge(fit_intercept'.",
        ),
        (
            "Ridge",
            {"lambda": 1.0},
            "`estimator_kwargs` keys must be valid Python parameter names, "
            "got 'lambda'.",
        ),
        (
            "Ridge\nimport os\nRidge",
            {},
            "'Ridge\\nimport os\\nRidge' is not a supported estimator.",
        ),
    ],
    ids=["key with code", "keyword key", "estimator with code"],
)
def test_get_estimator_constructor_ValueError_when_name_cannot_be_written(
    estimator, kwargs, err_msg
):
    """
    Test that _get_estimator_constructor raises instead of writing a key
    that is not a Python parameter name, or an estimator the script cannot
    import, for a plan that skipped validation.
    """
    with pytest.raises(ValueError, match=re.escape(err_msg)):
        _get_estimator_constructor(estimator, kwargs)


# =============================================================================
# Tests: _comment_text
# =============================================================================
@pytest.mark.parametrize(
    "text, expected",
    [
        ("# Categorical exog excluded (weekday)", "# Categorical exog excluded (weekday)"),
        ("# Temperature (°C), día", "# Temperature (°C), día"),
        ("# a\nimport os", "# a\\nimport os"),
        ("# a\r\nb", "# a\\r\\nb"),
        ("# a\x00b\x0bc\x0cd\x85e", "# a\\x00b\\x0bc\\x0cd\\x85e"),
        ("# a\u2028b\u2029c", "# a\\u2028b\\u2029c"),
    ],
    ids=[
        "plain",
        "non-ASCII letters",
        "newline",
        "carriage return",
        "control characters",
        "line and paragraph separators",
    ],
)
def test_comment_text_output_when_text_holds_line_breaks(text, expected):
    """
    Test that _comment_text escapes the characters of the Unicode categories
    Cc, Zl and Zp, so the comment stays on one line, and leaves any other
    text unchanged.
    """
    result = _comment_text(text)

    assert result == expected
    assert len(result.splitlines()) == 1


# =============================================================================
# Tests: _get_forecaster_import
# =============================================================================
@pytest.mark.parametrize(
    "forecaster, supported, expected",
    [
        (
            "ForecasterRecursive",
            _SINGLE_SERIES_FORECASTERS,
            "from skforecast.recursive import ForecasterRecursive",
        ),
        (
            "ForecasterDirect",
            _SINGLE_SERIES_FORECASTERS,
            "from skforecast.direct import ForecasterDirect",
        ),
        (
            "ForecasterRecursiveMultiSeries",
            _MULTI_SERIES_FORECASTERS,
            "from skforecast.recursive import ForecasterRecursiveMultiSeries",
        ),
        (
            "ForecasterDirectMultiVariate",
            _MULTI_SERIES_FORECASTERS,
            "from skforecast.direct import ForecasterDirectMultiVariate",
        ),
    ],
    ids=lambda x: f"{x}",
)
def test_get_forecaster_import_output_when_supported(forecaster, supported, expected):
    """
    Test that _get_forecaster_import returns the constant import line of
    each forecaster a renderer family builds.
    """
    assert _get_forecaster_import(forecaster, supported) == expected


@pytest.mark.parametrize(
    "forecaster, supported",
    [
        ("ForecasterRecursive\nimport os\nForecasterRecursive", _SINGLE_SERIES_FORECASTERS),
        ("ForecasterRecursiveMultiSeries", _SINGLE_SERIES_FORECASTERS),
        ("ForecasterRecursive", _MULTI_SERIES_FORECASTERS),
        (["ForecasterRecursive"], _SINGLE_SERIES_FORECASTERS),
    ],
    ids=["name with code", "other family", "single in multi", "not a string"],
)
def test_get_forecaster_import_ValueError_when_not_supported(forecaster, supported):
    """
    Test that _get_forecaster_import raises instead of writing a forecaster
    name outside the renderer family into the script.
    """
    err_msg = re.escape(
        f"{forecaster!r} cannot be rendered by this script template. "
        f"Supported forecasters: {list(supported)}."
    )
    with pytest.raises(ValueError, match=err_msg):
        _get_forecaster_import(forecaster, supported)


# =============================================================================
# Tests: _get_transformer_constructor
# =============================================================================
def test_get_transformer_constructor_output_when_supported():
    """
    Test that _get_transformer_constructor returns the constant constructor
    call of a supported transformer.
    """
    assert _get_transformer_constructor("StandardScaler") == "StandardScaler()"


@pytest.mark.parametrize(
    "transformer",
    ["(open('x', 'w').close() or StandardScaler)", "MinMaxScaler", "", None],
    ids=lambda x: f"transformer={x!r}",
)
def test_get_transformer_constructor_ValueError_when_not_supported(transformer):
    """
    Test that _get_transformer_constructor raises instead of writing a
    transformer name outside the closed map into the script.
    """
    err_msg = re.escape(
        f"{transformer!r} is not a supported transformer. Supported "
        f"transformers: ['StandardScaler']."
    )
    with pytest.raises(ValueError, match=err_msg):
        _get_transformer_constructor(transformer)


# =============================================================================
# Tests: _get_interval_method_literal
# =============================================================================
@pytest.mark.parametrize(
    "interval_method, expected",
    [("bootstrapping", "'bootstrapping'"), ("conformal", "'conformal'")],
    ids=lambda x: f"{x}",
)
def test_get_interval_method_literal_output_when_supported(interval_method, expected):
    """
    Test that _get_interval_method_literal returns the constant literal of
    the interval methods written into the scripts.
    """
    assert _get_interval_method_literal(interval_method) == expected


@pytest.mark.parametrize(
    "interval_method",
    ["bootstrapping' if open('x', 'w').close() is None else '", "native", None],
    ids=lambda x: f"interval_method={x!r}",
)
def test_get_interval_method_literal_ValueError_when_not_supported(interval_method):
    """
    Test that _get_interval_method_literal raises for any other value,
    including the native intervals, which the scripts never write as a
    method.
    """
    err_msg = re.escape(
        f"Interval method {interval_method!r} cannot be rendered. Supported "
        f"methods: ['bootstrapping', 'conformal']."
    )
    with pytest.raises(ValueError, match=err_msg):
        _get_interval_method_literal(interval_method)


# =============================================================================
# Tests: _emit_aligned_kwargs
# =============================================================================
def test_emit_aligned_kwargs_output_when_multiple_params():
    """
    Test that _emit_aligned_kwargs produces properly aligned output
    with padded parameter names.
    """
    lines: list[str] = []
    _emit_aligned_kwargs(
        lines,
        "forecaster = ForecasterRecursive(",
        [("estimator", "LGBMRegressor()"), ("lags", "7")],
    )
    expected = [
        "forecaster = ForecasterRecursive(",
        "    estimator = LGBMRegressor(),",
        "    lags      = 7,",
        ")",
    ]
    assert lines == expected


# =============================================================================
# Tests: _emit_end_train
# =============================================================================
def test_emit_end_train_ValueError_when_end_train_is_none():
    """
    Test that _emit_end_train raises ValueError when plan.end_train is
    None, since evaluation code requires a concrete split date.
    """
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        steps=10,
        end_train=None,
        explanation="test",
    )
    err_msg = re.escape("plan.end_train must be set to generate evaluation code.")
    with pytest.raises(ValueError, match=err_msg):
        _emit_end_train([], plan)


def test_emit_end_train_output_when_end_train_set():
    """
    Test that _emit_end_train emits the correct date literal with the
    "last training date" comment when plan.end_train is set.
    """
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        steps=10,
        end_train="2023-03-12",
        explanation="test",
    )
    lines: list[str] = []
    _emit_end_train(lines, plan)
    assert len(lines) == 1
    assert "end_train = '2023-03-12'" in lines[0]
    assert "last training date" in lines[0]


# =============================================================================
# Tests: _get_metric_imports
# =============================================================================
def test_get_metric_imports_output_when_multiple_metrics():
    """
    Test that _get_metric_imports produces deduplicated import lines,
    groups sklearn imports together, and raises for an unknown metric
    instead of leaving it out of the script.
    """
    metrics = [
        "mean_absolute_error",
        "mean_squared_error",
        "mean_absolute_scaled_error",
    ]
    result = _get_metric_imports(metrics)
    assert len(result) == 2
    assert "from sklearn.metrics import mean_absolute_error, mean_squared_error" in result
    assert "from skforecast.metrics import mean_absolute_scaled_error" in result

    result_new = _get_metric_imports([
        "median_absolute_error",
        "mean_squared_log_error",
        "symmetric_mean_absolute_percentage_error",
        "root_mean_squared_scaled_error",
    ])
    assert result_new == [
        "from sklearn.metrics import median_absolute_error, mean_squared_log_error",
        "from skforecast.metrics import symmetric_mean_absolute_percentage_error",
        "from skforecast.metrics import root_mean_squared_scaled_error",
    ]

    err_msg = re.escape("Metric 'unknown_metric' cannot be rendered.")
    with pytest.raises(ValueError, match=err_msg):
        _get_metric_imports(["mean_absolute_error", "unknown_metric"])


# =============================================================================
# Tests: _needs_column_transformer
# =============================================================================
@pytest.mark.parametrize(
    "profile, expected",
    [
        (
            DataProfile(
                n_series=1, series_lengths={"sales": 100}, target="sales",
                index_type="datetime", exog_columns=["temp", "holiday"],
                categorical_exog=["holiday"],
            ),
            True,
        ),
        (
            DataProfile(
                n_series=1, series_lengths={"sales": 100}, target="sales",
                index_type="datetime", exog_columns=["promo"],
                categorical_exog=[],
            ),
            False,
        ),
        (
            DataProfile(
                n_series=1, series_lengths={"sales": 100}, target="sales",
                index_type="datetime", exog_columns=[],
                categorical_exog=[],
            ),
            False,
        ),
    ],
    ids=["mixed_numeric_and_categorical", "all_numeric", "no_exog"],
)
def test_needs_column_transformer_output_when_different_exog_configs(profile, expected):
    """
    Test that _needs_column_transformer returns True only when both
    numeric and categorical exogenous columns exist.
    """
    assert _needs_column_transformer(profile) is expected


# =============================================================================
# Tests: _emit_window_features
# =============================================================================
def test_emit_window_features_output_when_features_provided():
    """
    Test that _emit_window_features produces correct RollingFeatures
    constructor code, and emits nothing for an empty list.
    """
    # Non-empty window features
    lines: list[str] = []
    window_features = [{"stats": ["mean", "std"], "window_size": 7}]
    _emit_window_features(lines, window_features)
    expected = [
        "window_features = RollingFeatures(",
        "    stats        = ['mean', 'std'],",
        "    window_sizes = [7, 7],",
        ")",
    ]
    assert lines == expected

    # Empty list emits nothing
    empty_lines: list[str] = []
    _emit_window_features(empty_lines, [])
    assert empty_lines == []


# =============================================================================
# Tests: _emit_preprocessing_steps
# =============================================================================
@pytest.mark.parametrize(
    "profile_kwargs, code_snippet, expected",
    [
        (
            {"series_lengths": {"y": 100}, "n_series": 1, "target": "y"},
            "data = data[~data.index.duplicated(keep='first')]",
            [
                "# Preprocessing",
                "data = data[~data.index.duplicated(keep='first')]",
                "data = data.asfreq('D')",
                "",
            ],
        ),
        (
            {
                "series_lengths": {"A": 100, "B": 100},
                "n_series": 2,
                "target": "value",
                "data_format": "long",
                "date_column": "date",
                "series_id_column": "series_id",
            },
            "data = data.drop_duplicates(subset=[{series_id_column}, "
            "{date_column}], keep='first')",
            [
                "# Preprocessing",
                "data = data.drop_duplicates(subset=['series_id', 'date'], "
                "keep='first')",
                "",
            ],
        ),
    ],
    ids=["single", "long"],
)
def test_emit_preprocessing_steps_output_when_duplicate_timestamps(
    profile_kwargs, code_snippet, expected
):
    """
    Test that the drop_duplicates step is emitted with its placeholders
    filled, followed by the deferred asfreq() for single-series data but
    not for long-format data, whose frequency is set when the series are
    reshaped (asfreq on its RangeIndex would fail).
    """
    profile = DataProfile(
        index_type               = "datetime",
        frequency                = "D",
        has_duplicate_timestamps = True,
        **profile_kwargs,
    )
    plan = ForecastPlan(
        task_type           = "single_series",
        forecaster          = "ForecasterRecursive",
        forecaster_kwargs   = {"lags": 7},
        estimator           = "Ridge",
        estimator_kwargs    = {},
        steps               = 10,
        frequency           = "D",
        use_exog            = False,
        preprocessing_steps = [
            PreprocessingStep(
                action       = "drop_duplicates",
                reason       = "Timestamps repeated in identical rows.",
                code_snippet = code_snippet,
                blocking     = True,
            )
        ],
        explanation         = "Plan.",
    )

    lines: list[str] = []
    _emit_preprocessing_steps(lines, plan, profile)

    assert lines == expected


def test_emit_preprocessing_steps_ValueError_when_snippet_not_in_templates():
    """
    Test that a blocking step whose snippet is not one of the closed
    templates (here, the drop_duplicates action with arbitrary code) raises
    instead of being written into the script.
    """
    profile = DataProfile(
        index_type     = "datetime",
        frequency      = "D",
        series_lengths = {"y": 100},
        n_series       = 1,
        target         = "y",
    )
    plan = ForecastPlan.model_construct(
        task_type           = "single_series",
        forecaster          = "ForecasterRecursive",
        forecaster_kwargs   = {"lags": 7},
        estimator           = "Ridge",
        estimator_kwargs    = {},
        steps               = 10,
        use_exog            = False,
        preprocessing_steps = [
            PreprocessingStep(
                action       = "drop_duplicates",
                reason       = "Injected.",
                code_snippet = "import os",
                blocking     = True,
            )
        ],
        explanation         = "Plan.",
    )

    err_msg = re.escape(
        "The blocking preprocessing step 'drop_duplicates' is not one of the "
        "steps the scripts can contain, so its code snippet is not written "
        "into the script. Build the plan with `plan()`, or remove the step."
    )
    lines: list[str] = []
    with pytest.raises(ValueError, match=err_msg):
        _emit_preprocessing_steps(lines, plan, profile)


def test_emit_preprocessing_steps_output_when_steps_of_version_0_3_1():
    """
    Test that the blocking steps generated by skforecast-ai 0.3.1
    (drop_duplicates on the index, provide_datetime_index and
    encode_target) are still written into the script, and that the
    non-blocking steps never are.
    """
    profile = DataProfile(
        index_type     = "datetime",
        frequency      = "D",
        series_lengths = {"y": 100},
        n_series       = 1,
        target         = "y",
    )
    plan = ForecastPlan(
        task_type           = "single_series",
        forecaster          = "ForecasterRecursive",
        forecaster_kwargs   = {"lags": 7},
        estimator           = "Ridge",
        steps               = 10,
        preprocessing_steps = [
            PreprocessingStep(
                action       = "drop_duplicates",
                reason       = "Duplicate timestamps cause errors in skforecast.",
                code_snippet = "data = data[~data.index.duplicated(keep='first')]",
                blocking     = True,
            ),
            PreprocessingStep(
                action       = "provide_datetime_index",
                reason       = "Provide a DatetimeIndex.",
                code_snippet = (
                    "# Set a DatetimeIndex:\n"
                    "# data.index = pd.date_range(start=..., "
                    "periods=len(data), freq=...)"
                ),
                blocking     = True,
            ),
            PreprocessingStep(
                action       = "encode_target",
                reason       = "The target column is not numeric.",
                code_snippet = "# Convert target to numeric",
                blocking     = True,
            ),
            PreprocessingStep(
                action       = "handle_gaps",
                reason       = "Informational only.",
                code_snippet = "import os",
                blocking     = False,
            ),
        ],
        explanation         = "Plan.",
    )

    lines: list[str] = []
    _emit_preprocessing_steps(lines, plan, profile)

    assert lines == [
        "# Preprocessing",
        "data = data[~data.index.duplicated(keep='first')]",
        "# Set a DatetimeIndex:",
        "# data.index = pd.date_range(start=..., periods=len(data), freq=...)",
        "# Convert target to numeric",
        "",
    ]
