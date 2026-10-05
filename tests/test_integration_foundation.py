# Integration tests: ForecasterFoundation executed with a real backend
# The generated scripts load Chronos-2 and run it, so these tests need the
# `chronos-forecasting` backend and its weights. They are skipped when the
# backend is not installed (CI does not install it).

import numpy as np
import pytest

from skforecast.exceptions import MissingValuesWarning
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import BacktestResult, ComparisonResult, ForecastingAssistant
from skforecast_ai.exceptions import InvalidInputError

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


# =============================================================================
# Tests: forecast() in evaluation mode with incomplete series
# =============================================================================
@pytest.mark.slow
def test_forecast_foundation_evaluation_with_missing_last_training_value():
    """
    Test that forecast() in evaluation mode scores every series when one has
    no value on the last training date: the model predicts the 5 test dates
    of both series, and each MAE is the one of its predictions against
    the test values of the same dates.
    """
    data = df_multi_long.copy()
    dates = np.sort(data["date"].unique())
    first = data["series_id"].unique()[0]
    data.loc[
        (data["series_id"] == first) & (data["date"] == dates[-6]), "value"
    ] = np.nan
    inputs = {
        "target": "value", "date_column": "date", "series_id_column": "series_id"
    }
    # skforecast warns about the missing value when the data are profiled.
    with pytest.warns(MissingValuesWarning):
        profile = assistant.profile(data=data, **inputs)
        plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
        result = assistant.forecast(
            data=data, profile=profile, plan=plan, test_size=5
        )

    actual = data.set_index(["series_id", "date"])["value"]
    metrics = result.metrics.set_index("series")["MAE"]
    assert sorted(metrics.index) == sorted(data["series_id"].unique())
    for series, predictions in result.predictions.groupby("level"):
        assert list(predictions.index) == list(dates[-5:])
        expected = np.abs(
            actual.loc[series].loc[predictions.index].to_numpy()
            - predictions["pred"].to_numpy()
        ).mean()
        np.testing.assert_allclose(metrics.loc[series], expected)


@pytest.mark.slow
def test_forecast_foundation_evaluation_InvalidInputError_when_series_ends_early():
    """
    Test that forecast() in evaluation mode raises before running the model
    when a series of long-format data ends before the test split, and that
    the same data are forecast in prediction mode, each series from its own
    last date.
    """
    dates = np.sort(df_multi_long["date"].unique())
    first = df_multi_long["series_id"].unique()[0]
    data = df_multi_long.loc[
        (df_multi_long["series_id"] != first) | (df_multi_long["date"] <= dates[-9])
    ]
    inputs = {
        "target": "value", "date_column": "date", "series_id_column": "series_id"
    }
    profile = assistant.profile(data=data, **inputs)
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")

    with pytest.raises(InvalidInputError, match="missing values in the test split"):
        assistant.forecast(data=data, profile=profile, plan=plan, test_size=5)
    result = assistant.forecast(data=data, profile=profile, plan=plan)

    assert len(result.predictions) == 5 * data["series_id"].nunique()
    ended = result.predictions.loc[result.predictions["level"] == first]
    assert ended.index[0] > dates[-9]
    assert ended.index[-1] < dates[-1]
