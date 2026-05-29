# Unit test _emit_imports helpers rendering

import pytest

from skforecast_ai.rendering._helpers import (
    _emit_imports_foundation,
    _emit_imports_multi_series,
    _emit_imports_single_series,
    _emit_imports_statistical,
)
from skforecast_ai.schemas import DataProfile, ForecastPlan

from .fixtures_rendering import (
    plan_foundation,
    plan_multi_series,
    plan_multi_series_exog,
    plan_multi_series_with_transformer_series,
    plan_multi_series_with_window_features,
    plan_multivariate,
    plan_single_direct,
    plan_single_recursive_no_exog,
    plan_single_with_transformer_exog,
    plan_single_with_transformer_y,
    plan_single_with_window_features,
    plan_statistical,
    profile_multi_long,
    profile_multi_long_exog,
    profile_multi_wide,
    profile_single,
    profile_single_mixed_exog,
    profile_single_no_exog,
)


# =============================================================================
# Tests: _emit_imports_single_series
# =============================================================================
def test_emit_imports_single_series_output_when_minimal_recursive():
    """
    Test that minimal ForecasterRecursive plan emits pandas, estimator,
    forecaster class, and trailing empty string without sklearn or
    model_selection imports.
    """
    lines: list[str] = []
    _emit_imports_single_series(lines, plan_single_recursive_no_exog, profile_single_no_exog)

    assert lines[0] == "import pandas as pd"
    assert "from lightgbm import LGBMRegressor" in lines
    assert "from skforecast.recursive import ForecasterRecursive" in lines
    assert lines[-1] == ""
    assert not any("StandardScaler" in l for l in lines)
    assert not any("model_selection" in l for l in lines)


def test_emit_imports_single_series_output_when_direct_forecaster():
    """
    Test that ForecasterDirect resolves to 'direct' module.
    """
    lines: list[str] = []
    _emit_imports_single_series(lines, plan_single_direct, profile_single_no_exog)

    assert "from skforecast.direct import ForecasterDirect" in lines


def test_emit_imports_single_series_output_when_transformer_y():
    """
    Test that transformer_y triggers StandardScaler import.
    """
    lines: list[str] = []
    _emit_imports_single_series(
        lines, plan_single_with_transformer_y, profile_single_no_exog
    )

    assert "from sklearn.preprocessing import StandardScaler" in lines


def test_emit_imports_single_series_output_when_transformer_exog_with_column_transformer():
    """
    Test that transformer_exog with mixed numeric/categorical exog triggers
    both StandardScaler and make_column_transformer imports.
    """
    lines: list[str] = []
    _emit_imports_single_series(
        lines, plan_single_with_transformer_exog, profile_single_mixed_exog
    )

    assert "from sklearn.preprocessing import StandardScaler" in lines
    assert "from sklearn.compose import make_column_transformer" in lines


def test_emit_imports_single_series_output_when_transformer_exog_without_column_transformer():
    """
    Test that transformer_exog with only numeric exog emits StandardScaler
    but not make_column_transformer.
    """
    lines: list[str] = []
    _emit_imports_single_series(
        lines, plan_single_with_transformer_exog, profile_single
    )

    assert "from sklearn.preprocessing import StandardScaler" in lines
    assert not any("make_column_transformer" in l for l in lines)


def test_emit_imports_single_series_output_when_window_features():
    """
    Test that window_features triggers RollingFeatures import.
    """
    lines: list[str] = []
    _emit_imports_single_series(
        lines, plan_single_with_window_features, profile_single_no_exog
    )

    assert "from skforecast.preprocessing import RollingFeatures" in lines


def test_emit_imports_single_series_output_when_include_metrics():
    """
    Test that include_metrics=True emits metric imports.
    """
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": 7},
        estimator="LGBMRegressor",
        estimator_kwargs={},
        steps=10,
        frequency="D",
        use_exog=False,
        metrics_to_compute=["mean_absolute_error"],
        explanation="test",
    )
    lines: list[str] = []
    _emit_imports_single_series(
        lines, plan, profile_single_no_exog, include_metrics=True
    )

    assert any("mean_absolute_error" in l for l in lines)


def test_emit_imports_single_series_output_when_include_backtesting():
    """
    Test that include_backtesting=True appends backtesting_forecaster
    and TimeSeriesFold as the last import before the trailing empty line.
    """
    lines: list[str] = []
    _emit_imports_single_series(
        lines, plan_single_recursive_no_exog, profile_single_no_exog,
        include_backtesting=True,
    )

    bt_line = [l for l in lines if "model_selection" in l]
    assert len(bt_line) == 1
    assert "backtesting_forecaster" in bt_line[0]
    assert "TimeSeriesFold" in bt_line[0]
    assert lines[-2] == bt_line[0]
    assert lines[-1] == ""


def test_emit_imports_single_series_ordering_model_selection_always_last():
    """
    Test that skforecast.model_selection import always appears after
    the forecaster class import when include_backtesting=True.
    """
    lines: list[str] = []
    _emit_imports_single_series(
        lines, plan_single_with_window_features, profile_single_no_exog,
        include_backtesting=True,
    )

    forecaster_idx = next(
        i for i, l in enumerate(lines) if "ForecasterRecursive" in l
    )
    bt_idx = next(i for i, l in enumerate(lines) if "model_selection" in l)
    assert bt_idx > forecaster_idx


# =============================================================================
# Tests: _emit_imports_multi_series
# =============================================================================
def test_emit_imports_multi_series_output_when_wide_no_exog():
    """
    Test that wide multi-series emits pandas, estimator, forecaster,
    and no reshape imports.
    """
    lines: list[str] = []
    _emit_imports_multi_series(lines, plan_multi_series, profile_multi_wide)

    assert lines[0] == "import pandas as pd"
    assert "from lightgbm import LGBMRegressor" in lines
    assert "from skforecast.recursive import ForecasterRecursiveMultiSeries" in lines
    assert not any("reshape" in l for l in lines)
    assert lines[-1] == ""


def test_emit_imports_multi_series_output_when_long_format_with_exog():
    """
    Test that long-format multi-series with exog emits both
    reshape_series_long_to_dict and reshape_exog_long_to_dict in a single
    preprocessing import line.
    """
    lines: list[str] = []
    _emit_imports_multi_series(lines, plan_multi_series_exog, profile_multi_long_exog)

    preprocessing_line = [l for l in lines if "skforecast.preprocessing" in l]
    assert len(preprocessing_line) == 1
    assert "reshape_series_long_to_dict" in preprocessing_line[0]
    assert "reshape_exog_long_to_dict" in preprocessing_line[0]


def test_emit_imports_multi_series_output_when_long_format_no_exog():
    """
    Test that long-format multi-series without exog only emits
    reshape_series_long_to_dict.
    """
    lines: list[str] = []
    _emit_imports_multi_series(lines, plan_multi_series, profile_multi_long)

    preprocessing_line = [l for l in lines if "skforecast.preprocessing" in l]
    assert len(preprocessing_line) == 1
    assert "reshape_series_long_to_dict" in preprocessing_line[0]
    assert "reshape_exog_long_to_dict" not in preprocessing_line[0]


def test_emit_imports_multi_series_output_when_multivariate_forecaster():
    """
    Test that ForecasterDirectMultiVariate resolves to 'direct' module
    and does not include reshape imports for wide format.
    """
    lines: list[str] = []
    _emit_imports_multi_series(lines, plan_multivariate, profile_multi_wide)

    assert "from skforecast.direct import ForecasterDirectMultiVariate" in lines
    assert not any("reshape" in l for l in lines)


def test_emit_imports_multi_series_output_when_transformer_series():
    """
    Test that transformer_series triggers StandardScaler import.
    """
    lines: list[str] = []
    _emit_imports_multi_series(
        lines, plan_multi_series_with_transformer_series, profile_multi_wide
    )

    assert "from sklearn.preprocessing import StandardScaler" in lines


def test_emit_imports_multi_series_output_when_window_features_and_long_format():
    """
    Test that window_features and long format both contribute to
    the same preprocessing import line.
    """
    lines: list[str] = []
    _emit_imports_multi_series(
        lines, plan_multi_series_with_window_features, profile_multi_long
    )

    preprocessing_line = [l for l in lines if "skforecast.preprocessing" in l]
    assert len(preprocessing_line) == 1
    assert "RollingFeatures" in preprocessing_line[0]
    assert "reshape_series_long_to_dict" in preprocessing_line[0]


def test_emit_imports_multi_series_output_when_include_backtesting():
    """
    Test that include_backtesting=True appends backtesting_forecaster_multiseries
    and TimeSeriesFold as the last import.
    """
    lines: list[str] = []
    _emit_imports_multi_series(
        lines, plan_multi_series, profile_multi_wide, include_backtesting=True
    )

    bt_line = [l for l in lines if "model_selection" in l]
    assert len(bt_line) == 1
    assert "backtesting_forecaster_multiseries" in bt_line[0]
    assert "TimeSeriesFold" in bt_line[0]
    assert lines[-2] == bt_line[0]
    assert lines[-1] == ""


def test_emit_imports_multi_series_ordering_model_selection_always_last():
    """
    Test that model_selection import appears after the forecaster class
    import when include_backtesting=True.
    """
    lines: list[str] = []
    _emit_imports_multi_series(
        lines, plan_multi_series, profile_multi_wide, include_backtesting=True
    )

    forecaster_idx = next(
        i for i, l in enumerate(lines) if "ForecasterRecursiveMultiSeries" in l
    )
    bt_idx = next(i for i, l in enumerate(lines) if "model_selection" in l)
    assert bt_idx > forecaster_idx


# =============================================================================
# Tests: _emit_imports_foundation
# =============================================================================
def test_emit_imports_foundation_output_when_minimal():
    """
    Test that minimal foundation plan emits pandas, FoundationModel,
    ForecasterFoundation, and trailing empty string without model_selection
    or sklearn imports.
    """
    lines: list[str] = []
    _emit_imports_foundation(lines, plan_foundation)

    assert lines[0] == "import pandas as pd"
    assert any("FoundationModel" in l and "ForecasterFoundation" in l for l in lines)
    assert lines[-1] == ""
    assert not any("model_selection" in l for l in lines)
    assert not any("sklearn" in l for l in lines)


def test_emit_imports_foundation_output_when_include_metrics():
    """
    Test that include_metrics=True emits metric imports between pandas
    and foundation imports.
    """
    plan = ForecastPlan(
        task_type="foundation",
        forecaster="ForecasterFoundation",
        forecaster_kwargs={},
        estimator=None,
        estimator_kwargs={},
        steps=10,
        frequency="D",
        use_exog=False,
        metrics_to_compute=["mean_absolute_error", "mean_absolute_scaled_error"],
        explanation="test",
    )
    lines: list[str] = []
    _emit_imports_foundation(lines, plan, include_metrics=True)

    assert any("mean_absolute_error" in l for l in lines)
    assert any("mean_absolute_scaled_error" in l for l in lines)


def test_emit_imports_foundation_output_when_include_backtesting():
    """
    Test that include_backtesting=True appends backtesting_foundation
    and TimeSeriesFold as the last import before the trailing empty line.
    """
    lines: list[str] = []
    _emit_imports_foundation(lines, plan_foundation, include_backtesting=True)

    bt_line = [l for l in lines if "model_selection" in l]
    assert len(bt_line) == 1
    assert "backtesting_foundation" in bt_line[0]
    assert "TimeSeriesFold" in bt_line[0]
    assert lines[-2] == bt_line[0]
    assert lines[-1] == ""


def test_emit_imports_foundation_ordering_model_selection_after_foundation():
    """
    Test that model_selection import appears after foundation import.
    """
    lines: list[str] = []
    _emit_imports_foundation(lines, plan_foundation, include_backtesting=True)

    foundation_idx = next(
        i for i, l in enumerate(lines) if "FoundationModel" in l
    )
    bt_idx = next(i for i, l in enumerate(lines) if "model_selection" in l)
    assert bt_idx > foundation_idx


# =============================================================================
# Tests: _emit_imports_statistical
# =============================================================================
def test_emit_imports_statistical_output_when_minimal():
    """
    Test that minimal statistical plan emits pandas, Arima,
    ForecasterStats, and trailing empty string without model_selection
    or sklearn imports.
    """
    lines: list[str] = []
    _emit_imports_statistical(lines, plan_statistical)

    assert lines[0] == "import pandas as pd"
    assert "from skforecast.stats import Arima" in lines
    assert "from skforecast.recursive import ForecasterStats" in lines
    assert lines[-1] == ""
    assert not any("model_selection" in l for l in lines)
    assert not any("sklearn" in l for l in lines)


def test_emit_imports_statistical_output_when_include_metrics():
    """
    Test that include_metrics=True emits metric imports.
    """
    plan = ForecastPlan(
        task_type="statistical",
        forecaster="ForecasterStats",
        forecaster_kwargs={},
        estimator=None,
        estimator_kwargs={},
        steps=10,
        frequency="D",
        use_exog=False,
        metrics_to_compute=["mean_absolute_error"],
        explanation="test",
    )
    lines: list[str] = []
    _emit_imports_statistical(lines, plan, include_metrics=True)

    assert any("mean_absolute_error" in l for l in lines)


def test_emit_imports_statistical_output_when_include_backtesting():
    """
    Test that include_backtesting=True appends backtesting_stats
    and TimeSeriesFold as the last import before the trailing empty line.
    """
    lines: list[str] = []
    _emit_imports_statistical(lines, plan_statistical, include_backtesting=True)

    bt_line = [l for l in lines if "model_selection" in l]
    assert len(bt_line) == 1
    assert "backtesting_stats" in bt_line[0]
    assert "TimeSeriesFold" in bt_line[0]
    assert lines[-2] == bt_line[0]
    assert lines[-1] == ""


def test_emit_imports_statistical_ordering_model_selection_after_forecaster():
    """
    Test that model_selection import appears after ForecasterStats import.
    """
    lines: list[str] = []
    _emit_imports_statistical(lines, plan_statistical, include_backtesting=True)

    forecaster_idx = next(
        i for i, l in enumerate(lines) if "ForecasterStats" in l
    )
    bt_idx = next(i for i, l in enumerate(lines) if "model_selection" in l)
    assert bt_idx > forecaster_idx
