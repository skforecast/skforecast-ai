# Unit test _helpers rendering

import re

import pytest

from skforecast_ai.rendering._helpers import (
    _emit_aligned_kwargs,
    _emit_end_train,
    _emit_window_features,
    _get_estimator_constructor,
    _get_estimator_import,
    _get_interval_repr,
    _get_metric_imports,
    _get_seasonal_period,
    _needs_column_transformer,
)
from skforecast_ai.schemas import DataProfile, ForecastPlan

from .fixtures_rendering import (
    profile_single,
)


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
        ("3h", None),
        ("unknown", None),
        (None, None),
    ],
    ids=lambda x: f"frequency={x}",
)
def test_get_seasonal_period_output_when_different_frequencies(frequency, expected):
    """
    Test that _get_seasonal_period returns the correct seasonal period
    for known frequencies, and None for unknown or None inputs.
    """
    assert _get_seasonal_period(frequency) == expected


# =============================================================================
# Tests: _get_interval_repr
# =============================================================================
@pytest.mark.parametrize(
    "interval, expected",
    [
        ([10, 90], "[10, 90]"),
        (None, "[10, 90]  # default 80% prediction interval"),
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
        explanation="test",
    )
    assert _get_interval_repr(plan) == expected


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


def test_get_estimator_import_output_when_unknown():
    """
    Test that _get_estimator_import returns a TODO placeholder for
    unknown estimators.
    """
    result = _get_estimator_import("MyCustomEstimator")
    assert "TODO" in result
    assert "MyCustomEstimator" in result


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
    Test that _emit_end_train raises ValueError when profile.end_train
    is None.
    """
    profile = DataProfile(
        n_series=1,
        n_observations=100,
        target="sales",
        index_type="datetime",
        end_train=None,
    )
    err_msg = re.escape("profile.end_train must be set before generating code.")
    with pytest.raises(ValueError, match=err_msg):
        _emit_end_train([], profile)


def test_emit_end_train_output_when_end_train_set():
    """
    Test that _emit_end_train emits the correct date literal with
    the 80% comment.
    """
    lines: list[str] = []
    _emit_end_train(lines, profile_single)
    assert len(lines) == 1
    assert "end_train = '2023-03-12'" in lines[0]
    assert "80%" in lines[0]


# =============================================================================
# Tests: _get_metric_imports
# =============================================================================
def test_get_metric_imports_output_when_multiple_metrics():
    """
    Test that _get_metric_imports produces deduplicated import lines,
    groups sklearn imports together, and ignores unknown metric names.
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

    # Unknown metrics are silently ignored
    result_with_unknown = _get_metric_imports(["mean_absolute_error", "unknown_metric"])
    assert len(result_with_unknown) == 1
    assert "mean_absolute_error" in result_with_unknown[0]


# =============================================================================
# Tests: _needs_column_transformer
# =============================================================================
@pytest.mark.parametrize(
    "profile, expected",
    [
        (
            DataProfile(
                n_series=1, n_observations=100, target="sales",
                index_type="datetime", exog_columns=["temp", "holiday"],
                categorical_exog=["holiday"],
            ),
            True,
        ),
        (
            DataProfile(
                n_series=1, n_observations=100, target="sales",
                index_type="datetime", exog_columns=["promo"],
                categorical_exog=[],
            ),
            False,
        ),
        (
            DataProfile(
                n_series=1, n_observations=100, target="sales",
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
    window_features = [{"stats": ["mean", "std"], "window_sizes": 7}]
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
