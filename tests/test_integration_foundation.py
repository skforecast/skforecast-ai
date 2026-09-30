# Integration tests: ForecasterFoundation executed with a real backend
# The generated scripts load Chronos-2 and run it, so these tests need the
# `chronos-forecasting` backend and its weights. They are skipped when the
# backend is not installed (CI does not install it).

import numpy as np
import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import BacktestResult, ComparisonResult, ForecastingAssistant

from tests.fixtures_assistant import df_multi_long, df_multi_wide

pytest.importorskip("chronos")

assistant = ForecastingAssistant()

_MULTI_SERIES_INPUTS = [
    (
        df_multi_long,
        {"target": "value", "date_column": "date", "series_id_column": "series_id"},
        ["store_a", "store_b"],
    ),
    (
        df_multi_wide,
        {"target": ["series_a", "series_b"], "date_column": "date"},
        ["series_a", "series_b"],
    ),
]


# =============================================================================
# Tests: forecast() with several series
# =============================================================================
@pytest.mark.slow
@pytest.mark.parametrize(
    "data, inputs, series", _MULTI_SERIES_INPUTS, ids=["long", "wide"]
)
def test_forecast_foundation_multi_series(data, inputs, series):
    """
    Test that forecast() runs the generated ForecasterFoundation script on
    several series, in long and wide format, predicting every series with
    a native interval in the columns of the other forecasters and scoring
    each one.
    """
    profile = assistant.profile(data=data, **inputs)
    plan = assistant.plan(
        profile, steps=5, forecaster="ForecasterFoundation", interval=[0.1, 0.9]
    )

    result = assistant.forecast(data=data, **inputs, plan=plan, test_size=5)

    assert list(result.predictions.columns) == [
        "level", "pred", "lower_bound", "upper_bound"
    ]
    assert sorted(result.predictions["level"].unique()) == series
    assert len(result.predictions) == 5 * len(series)
    assert sorted(result.metrics["series"]) == series
    assert np.isfinite(result.metrics["MAE"]).all()


# =============================================================================
# Tests: backtest() and compare() with several series
# =============================================================================
@pytest.mark.slow
@pytest.mark.parametrize(
    "data, inputs, series", _MULTI_SERIES_INPUTS, ids=["long", "wide"]
)
def test_backtest_and_compare_foundation_multi_series(data, inputs, series):
    """
    Test that backtest() reports ForecasterFoundation metrics per series
    plus the average row, and that compare() ranks it against
    ForecasterRecursiveMultiSeries on that average, without a baseline.
    """
    profile = assistant.profile(data=data, **inputs)
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    backtest = assistant.backtest(
        data=data, **inputs, cv=cv, profile=profile, plan=plan,
        show_progress=False,
    )
    comparison = assistant.compare(
        data=data, **inputs, cv=cv, profile=profile, show_progress=False
    )

    assert isinstance(backtest, BacktestResult)
    assert list(backtest.metrics["levels"])[:len(series)] == series
    assert "average" in list(backtest.metrics["levels"])
    assert isinstance(comparison, ComparisonResult)
    assert sorted(comparison.results["name"]) == [
        "ForecasterFoundation",
        "ForecasterRecursiveMultiSeries",
    ]
    assert comparison.baseline_name is None
    assert np.isfinite(comparison.results["mean_absolute_scaled_error"]).all()
