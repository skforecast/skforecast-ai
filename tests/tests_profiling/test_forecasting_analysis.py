"""Tests for create_analysis_context (Stage 3)."""

import numpy as np
import pandas as pd

from skforecast_ai.profiling import create_forecasting_analysis
from skforecast_ai.schemas import ForecastingAnalysis, DataProfile


def test_analysis_context_multi_series_computes_series_lengths():
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "date": np.concatenate([np.tile(dates, 1), np.tile(dates[:50], 1)]),
        "series_id": ["A"] * 100 + ["B"] * 50,
        "value": np.arange(150, dtype=float),
    })
    profile = DataProfile(
        data_format="long",
        n_series=2,
        n_observations=50,
        series_lengths={"A": 100, "B": 50},
        target="value",
        date_column="date",
        series_id_column="series_id",
        index_type="datetime",
        frequency="D",
    )
    ctx = create_forecasting_analysis(df, profile, "ForecasterRecursiveMultiSeries")
    assert isinstance(ctx, ForecastingAnalysis)
    assert ctx.min_series_length == 50
    assert ctx.max_series_length == 100
    assert ctx.series_length_ratio == 2.0
    assert ctx.effective_n_observations == 150


def test_analysis_context_multi_series_without_data_uses_defaults():
    profile = DataProfile(
        data_format="long",
        n_series=3,
        n_observations=100,
        series_lengths={"A": 100, "B": 100, "C": 100},
        target="value",
        series_id_column="series_id",
        index_type="datetime",
        frequency="D",
    )
    ctx = create_forecasting_analysis(None, profile, "ForecasterRecursiveMultiSeries")
    assert ctx.effective_n_observations == 300
    assert ctx.min_series_length == 100


def test_analysis_context_single_ml_returns_n_observations():
    df = pd.DataFrame(
        {"y": np.arange(365, dtype=float)},
        index=pd.date_range("2023-01-01", periods=365, freq="D"),
    )
    profile = DataProfile(
        n_series=1,
        n_observations=365,
        target="y",
        index_type="datetime",
        frequency="D",
    )
    ctx = create_forecasting_analysis(df, profile, "ForecasterRecursive")
    assert ctx.effective_n_observations == 365
    assert ctx.target_variance is not None
    assert ctx.target_variance > 0


def test_analysis_context_foundation_computes_viable_context_length():
    profile = DataProfile(
        n_series=1,
        n_observations=500,
        target="y",
        index_type="datetime",
        frequency="D",
    )
    ctx = create_forecasting_analysis(None, profile, "ForecasterFoundation")
    assert ctx.effective_n_observations == 500
    assert ctx.viable_context_length == 500  # min(500, 2048)


def test_analysis_context_foundation_caps_context_length():
    profile = DataProfile(
        n_series=1,
        n_observations=10000,
        target="y",
        index_type="datetime",
        frequency="D",
    )
    ctx = create_forecasting_analysis(None, profile, "ForecasterFoundation")
    assert ctx.viable_context_length == 2048


def test_analysis_context_stats_returns_basic():
    profile = DataProfile(
        n_series=1,
        n_observations=200,
        target="y",
        index_type="datetime",
        frequency="D",
    )
    ctx = create_forecasting_analysis(None, profile, "ForecasterStats")
    assert ctx.effective_n_observations == 200
