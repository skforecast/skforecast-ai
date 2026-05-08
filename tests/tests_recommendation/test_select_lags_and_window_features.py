"""Unit tests for select_lags_and_window_features."""

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.recommendation.rules import select_lags_and_window_features


def _make_series(n: int, seed: int = 123) -> pd.Series:
    """Create a simple AR(1) series for testing."""
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    for i in range(1, n):
        y[i] = 0.6 * y[i - 1] + rng.normal(0, 1)
    return pd.Series(y, name="target")


# ---------------------------------------------------------------------------
# ValueError when target_series is None
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_ValueError_when_target_series_none():
    """
    Test that select_lags_and_window_features raises ValueError when target_series
    is None.
    """
    match = re.escape("`target_series` is required for lag selection")
    with pytest.raises(ValueError, match=match):
        select_lags_and_window_features(n_observations=365, frequency="D", target_series=None)


# ---------------------------------------------------------------------------
# Lags: PACF-based selection
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_output_when_daily_frequency():
    """
    Test select_lags_and_window_features returns pruned representative lags and
    seasonal lags for a daily frequency series with 365 observations.
    Pruning reduces contiguous lags since a roll_mean_7 is included.
    """
    series = _make_series(365)
    lags, wf = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert isinstance(lags, list)
    assert lags == sorted(lags)
    # Lag 1 always preserved (AR(1) structure)
    assert 1 in lags
    # Seasonal enrichment: lag 7 (daily primary)
    assert 7 in lags


def test_select_lags_and_window_features_output_when_hourly_frequency():
    """
    Test select_lags_and_window_features includes seasonal lag 24 for hourly data
    with enough observations.
    """
    series = _make_series(720)
    lags, wf = select_lags_and_window_features(
        n_observations=720, frequency="h", target_series=series
    )

    # Seasonal lags: 24 must be present (enrichment)
    assert 24 in lags
    # Secondary season 168 included if within budget (720//3=240 > 168)
    assert 168 in lags


def test_select_lags_and_window_features_output_when_monthly_frequency():
    """
    Test select_lags_and_window_features returns seasonal lag 12 for monthly data.
    """
    series = _make_series(120)
    lags, wf = select_lags_and_window_features(
        n_observations=120, frequency="ME", target_series=series
    )

    # Seasonal enrichment: lag 12 must be present
    assert 12 in lags


def test_select_lags_and_window_features_output_when_weekly_frequency():
    """
    Test select_lags_and_window_features returns seasonal lag 52 for weekly data
    when enough observations are available.
    """
    series = _make_series(200)
    lags, wf = select_lags_and_window_features(
        n_observations=200, frequency="W", target_series=series
    )

    # primary season = 52; max_lag = 200//3 = 66 > 52 → included
    assert 52 in lags


def test_select_lags_and_window_features_output_when_no_frequency():
    """
    Test select_lags_and_window_features works with no frequency (no seasonal
    enrichment, only PACF-based lags).
    """
    series = _make_series(365)
    lags, wf = select_lags_and_window_features(
        n_observations=365, frequency=None, target_series=series
    )

    assert len(lags) >= 3
    assert 1 in lags
    assert lags == sorted(lags)


def test_select_lags_and_window_features_output_when_very_short_series():
    """
    Test select_lags_and_window_features returns minimal lags and no window features
    for a very short series (< 30 observations).
    """
    series = _make_series(20)
    lags, wf = select_lags_and_window_features(
        n_observations=20, frequency="D", target_series=series
    )

    assert len(lags) <= 5
    assert max(lags) <= 20 // 3
    assert wf is None


def test_select_lags_and_window_features_output_when_short_series_no_window_features():
    """
    Test select_lags_and_window_features returns no window features for series
    with fewer than 60 observations.
    """
    series = _make_series(50)
    lags, wf = select_lags_and_window_features(
        n_observations=50, frequency="D", target_series=series
    )

    assert wf is None


# ---------------------------------------------------------------------------
# Lags: constraints
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_output_max_lag_respects_constraint():
    """
    Test that the maximum lag never exceeds n_observations // 3.
    """
    series = _make_series(100)
    lags, _ = select_lags_and_window_features(
        n_observations=100, frequency="h", target_series=series
    )

    assert max(lags) <= 100 // 3


def test_select_lags_and_window_features_output_seasonal_lag_excluded_when_too_large():
    """
    Test that seasonal lags are excluded when they exceed the max allowed.
    For monthly data with only 30 observations, lag 12 exceeds 30//3=10.
    """
    series = _make_series(30)
    lags, _ = select_lags_and_window_features(
        n_observations=30, frequency="ME", target_series=series
    )

    # Very short: n == 30, returns minimal lags
    assert max(lags) <= 30 // 3


def test_select_lags_and_window_features_output_secondary_season_excluded_when_too_large():
    """
    Test that secondary seasonal lag (168 for hourly) is excluded when
    n_observations is too small to allow it.
    """
    series = _make_series(300)
    lags, _ = select_lags_and_window_features(
        n_observations=300, frequency="h", target_series=series
    )

    # max_lag_allowed = 300 // 3 = 100; 168 > 100 -> excluded
    assert 168 not in lags
    # But 24 should be there (seasonal enrichment)
    assert 24 in lags


# ---------------------------------------------------------------------------
# PACF-based lag selection: specific patterns
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_output_when_pacf_with_ar_series():
    """
    Test that select_lags_and_window_features selects lags using PACF when a
    target series with clear AR structure is provided. An AR(2) series
    should select at least lags 1 and 2.
    """
    rng = np.random.default_rng(123)
    n = 500
    y = np.zeros(n)
    for i in range(2, n):
        y[i] = 0.7 * y[i - 1] + 0.2 * y[i - 2] + rng.normal(0, 0.1)
    series = pd.Series(y, name="target")

    lags, _ = select_lags_and_window_features(
        n_observations=n, frequency="D", target_series=series
    )

    assert 1 in lags
    assert 2 in lags
    # Seasonal enrichment: lag 7 (daily primary) must be present
    assert 7 in lags


def test_select_lags_and_window_features_output_when_pacf_with_seasonal_series():
    """
    Test that PACF-based selection captures seasonal lags for a series
    with strong seasonal component (period 12 monthly).
    """
    rng = np.random.default_rng(42)
    n = 240
    t = np.arange(n)
    y = np.sin(2 * np.pi * t / 12) + rng.normal(0, 0.3, n)
    series = pd.Series(y, name="target")

    lags, _ = select_lags_and_window_features(
        n_observations=n, frequency="ME", target_series=series
    )

    # Seasonal lag 12 must be present (either from PACF or enrichment)
    assert 12 in lags
    assert lags == sorted(lags)


def test_select_lags_and_window_features_output_when_pacf_selects_few_lags():
    """
    Test the safety net: when PACF selects very few significant lags
    (e.g. white noise series), at least 3 recent lags are returned.
    """
    rng = np.random.default_rng(99)
    # White noise: no significant PACF lags expected
    series = pd.Series(rng.normal(0, 1, 200), name="target")

    lags, _ = select_lags_and_window_features(
        n_observations=200, frequency="D", target_series=series
    )

    assert len(lags) >= 3
    # Must include lag 1 (safety net)
    assert 1 in lags
    # Seasonal enrichment: lag 7 (daily)
    assert 7 in lags


def test_select_lags_and_window_features_output_pacf_respects_max_lag_constraint():
    """
    Test that PACF-selected lags respect the n_observations // 3 constraint.
    """
    rng = np.random.default_rng(7)
    n = 100
    y = np.zeros(n)
    for i in range(1, n):
        y[i] = 0.9 * y[i - 1] + rng.normal(0, 0.1)
    series = pd.Series(y, name="target")

    lags, _ = select_lags_and_window_features(
        n_observations=n, frequency="D", target_series=series
    )

    assert max(lags) <= n // 3


# ---------------------------------------------------------------------------
# Window features: std conditional on heteroscedasticity
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_window_features_no_std_when_low_cv():
    """
    Test that roll_std is not included when the series has low
    coefficient of variation (< 0.1), indicating homoscedastic behavior.
    """
    # Constant series with tiny noise: mean=100, std~0.01 -> cv=0.0001
    rng = np.random.default_rng(42)
    series = pd.Series(100.0 + rng.normal(0, 0.01, 365), name="target")

    _, wf = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert wf is not None
    for config in wf:
        assert "std" not in config["stats"]


def test_select_lags_and_window_features_window_features_includes_std_when_high_cv():
    """
    Test that roll_std is included when the series has high coefficient
    of variation (> 0.1), indicating heteroscedastic behavior.
    """
    # Series with mean=10, std=5 -> cv=0.5
    rng = np.random.default_rng(42)
    series = pd.Series(10.0 + rng.normal(0, 5, 365), name="target")

    _, wf = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert wf is not None
    assert "std" in wf[0]["stats"]


# ---------------------------------------------------------------------------
# Window features: structure
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_output_window_features_for_daily():
    """
    Test select_lags_and_window_features returns window features with seasonal
    window sizes for daily frequency with sufficient data.
    """
    series = _make_series(365)
    _, wf = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert wf is not None
    assert isinstance(wf, list)
    assert len(wf) >= 1

    # First config: short window at primary season (7)
    short_config = wf[0]
    assert "mean" in short_config["stats"]
    assert short_config["window_sizes"] == 7


def test_select_lags_and_window_features_output_window_features_for_hourly():
    """
    Test select_lags_and_window_features returns window features with window=24
    (primary) and window=168 (secondary) for hourly data.
    """
    series = _make_series(720)
    _, wf = select_lags_and_window_features(
        n_observations=720, frequency="h", target_series=series
    )

    assert wf is not None
    assert len(wf) == 2

    # Short window: mean at 24
    assert "mean" in wf[0]["stats"]
    assert wf[0]["window_sizes"] == 24

    # Long window: mean at 168
    assert wf[1]["stats"] == ["mean"]
    assert wf[1]["window_sizes"] == 168


def test_select_lags_and_window_features_output_window_features_monthly():
    """
    Test select_lags_and_window_features returns window features with window=12
    for monthly frequency.
    """
    series = _make_series(120)
    _, wf = select_lags_and_window_features(
        n_observations=120, frequency="ME", target_series=series
    )

    assert wf is not None
    short_config = wf[0]
    assert short_config["window_sizes"] == 12


def test_select_lags_and_window_features_output_window_features_none_frequency():
    """
    Test select_lags_and_window_features returns generic window features (window=7)
    when no frequency is provided but enough data exists.
    """
    series = _make_series(200)
    _, wf = select_lags_and_window_features(
        n_observations=200, frequency=None, target_series=series
    )

    assert wf is not None
    assert "mean" in wf[0]["stats"]
    assert wf[0]["window_sizes"] == 7


def test_select_lags_and_window_features_output_window_features_capped_by_data_size():
    """
    Test that window sizes are capped at 25% of n_observations.
    For 80 observations with hourly data: max_window = 20, primary=24
    -> window capped to 20.
    """
    series = _make_series(80)
    _, wf = select_lags_and_window_features(
        n_observations=80, frequency="h", target_series=series
    )

    assert wf is not None
    max_window = int(80 * 0.25)
    for config in wf:
        assert config["window_sizes"] <= max_window


def test_select_lags_and_window_features_output_no_long_window_when_equals_short():
    """
    Test that a long window config is omitted when it would equal the
    short window (e.g. monthly with no secondary season and 2*12=24
    exceeds the data constraint).
    """
    series = _make_series(60)
    _, wf = select_lags_and_window_features(
        n_observations=60, frequency="ME", target_series=series
    )

    if wf is not None and len(wf) > 1:
        # Long window must be strictly greater than short
        assert wf[1]["window_sizes"] > wf[0]["window_sizes"]


# ---------------------------------------------------------------------------
# Lag pruning when rolling mean present
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_lag_pruning_preserves_minimum_lags():
    """
    Test that pruning never reduces lags below 3 elements.
    """
    series = _make_series(365)
    lags, _ = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert len(lags) >= 3


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------
def test_select_lags_and_window_features_output_returns_tuple():
    """
    Test that select_lags_and_window_features always returns a 2-element tuple.
    """
    series = _make_series(365)
    result = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert isinstance(result, tuple)
    assert len(result) == 2


def test_select_lags_and_window_features_output_lags_are_sorted_integers():
    """
    Test that lags are always sorted positive integers.
    """
    series = _make_series(500)
    lags, _ = select_lags_and_window_features(
        n_observations=500, frequency="h", target_series=series
    )

    assert all(isinstance(lag, int) for lag in lags)
    assert all(lag > 0 for lag in lags)
    assert lags == sorted(lags)
    # No duplicates
    assert len(lags) == len(set(lags))
