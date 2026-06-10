"""Unit tests for autoregressive lag and window feature selection."""

import numpy as np
import pandas as pd

from skforecast_ai.recommendation.autoregressive import (
    DEFAULT_PACF_CAP,
    MAX_PACF_CAP,
    _strongest_pacf_window,
    compute_series_pacf,
    finalize_lags,
    select_window_features,
)
from skforecast_ai.schemas import DataProfile, SeriesPacf


def _target_stats(series: pd.Series) -> dict:
    """Build a target_stats mapping from a series."""
    s = pd.Series(series)
    if len(s) == 0:
        return {}
    return {
        "target": {
            "min": float(s.min()),
            "max": float(s.max()),
            "mean": float(s.mean()),
            "std": float(s.std()),
        }
    }


def select_lags_and_window_features(
    n_observations: int,
    frequency: str | None = None,
    target_series: pd.Series | None = None,
) -> tuple[list[int], list[dict] | None]:
    """
    Test shim wrapping the new PACF-primitive selection API.

    Exercises `compute_series_pacf` -> `finalize_lags` for a single
    series, plus `select_window_features`.
    """
    series = pd.Series(target_series, name="target").reset_index(drop=True)
    target_stats = _target_stats(series)
    profile = DataProfile(
        n_series=1,
        series_lengths={"target": n_observations},
        target="target",
        index_type="datetime",
        frequency=frequency,
        target_stats=target_stats,
    )
    df = pd.DataFrame({"target": series})

    series_pacf = compute_series_pacf(df, profile)
    window_features = select_window_features(
        task_type="single_series", n_observations=n_observations, frequency=frequency, series_pacf=series_pacf
    )

    lags = finalize_lags(
        series_pacf     = series_pacf,
        task_type       = "single_series",
        n_observations  = n_observations,
        frequency       = frequency,
    )

    return lags, window_features


def _make_series(n: int, seed: int = 123) -> pd.Series:
    """Create a simple AR(1) series for testing."""
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    for i in range(1, n):
        y[i] = 0.6 * y[i - 1] + rng.normal(0, 1)
    return pd.Series(y, name="target")


# ---------------------------------------------------------------------------
# Lags: PACF-based selection
# ---------------------------------------------------------------------------
def test_select_autoregressive_output_when_daily_frequency():
    """
    Test select_autoregressive returns lags and seasonal lags for a
    daily frequency series with 365 observations.
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


def test_select_autoregressive_output_when_hourly_frequency():
    """
    Test select_autoregressive includes seasonal lag 24 for hourly data
    with enough observations.
    """
    series = _make_series(720)
    lags, wf = select_lags_and_window_features(
        n_observations=720, frequency="h", target_series=series
    )

    # Primary seasonal lag 24 must be present (enrichment)
    assert 24 in lags
    # Secondary season 168 is NOT force-added: enrichment is primary-only,
    # and this AR(1) series has no genuine weekly PACF signal.
    assert 168 not in lags


def test_select_autoregressive_output_when_monthly_frequency():
    """
    Test select_autoregressive returns seasonal lag 12 for monthly data.
    """
    series = _make_series(120)
    lags, wf = select_lags_and_window_features(
        n_observations=120, frequency="ME", target_series=series
    )

    # Seasonal enrichment: lag 12 must be present
    assert 12 in lags


def test_select_autoregressive_output_when_weekly_frequency():
    """
    Test select_autoregressive returns seasonal lag 52 for weekly data
    when enough observations are available.
    """
    series = _make_series(200)
    lags, wf = select_lags_and_window_features(
        n_observations=200, frequency="W", target_series=series
    )

    # primary season = 52; max_lag = 200//3 = 66 > 52 → included
    assert 52 in lags


def test_select_autoregressive_output_when_no_frequency():
    """
    Test select_autoregressive works with no frequency (no seasonal
    enrichment, only PACF-based lags).
    """
    series = _make_series(365)
    lags, wf = select_lags_and_window_features(
        n_observations=365, frequency=None, target_series=series
    )

    assert len(lags) >= 3
    assert 1 in lags
    assert lags == sorted(lags)


def test_select_autoregressive_output_when_very_short_series():
    """
    Test select_autoregressive returns minimal lags and no window features
    for a very short series (< 30 observations).
    """
    series = _make_series(20)
    lags, wf = select_lags_and_window_features(
        n_observations=20, frequency="D", target_series=series
    )

    assert len(lags) <= 5
    assert max(lags) <= 20 // 3
    assert wf is None


def test_select_autoregressive_output_when_short_series_no_window_features():
    """
    Test select_autoregressive returns no window features for series
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
def test_select_autoregressive_output_max_lag_respects_constraint():
    """
    Test that the maximum lag never exceeds n_observations // 3.
    """
    series = _make_series(100)
    lags, _ = select_lags_and_window_features(
        n_observations=100, frequency="h", target_series=series
    )

    assert max(lags) <= 100 // 3


def test_select_autoregressive_output_seasonal_lag_excluded_when_too_large():
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


def test_select_autoregressive_output_secondary_season_excluded_when_too_large():
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
def test_select_autoregressive_output_when_pacf_with_ar_series():
    """
    Test that select_autoregressive selects lags using PACF when a
    target series with clear AR structure is provided. An AR(2) series
    should select recent autoregressive lags (lag 1 and a low lag),
    evaluated without window-feature pruning so the raw lag set is checked.
    """
    rng = np.random.default_rng(123)
    n = 500
    y = np.zeros(n)
    for i in range(2, n):
        y[i] = 0.7 * y[i - 1] + 0.2 * y[i - 2] + rng.normal(0, 0.1)
    series = pd.Series(y, name="target")

    profile = DataProfile(
        n_series=1,
        series_lengths={"target": n},
        target="target",
        index_type="datetime",
        frequency="D",
        target_stats={},
    )
    df = pd.DataFrame({"target": series})
    series_pacf = compute_series_pacf(df, profile)

    lags = finalize_lags(
        series_pacf     = series_pacf,
        task_type       = "single_series",
        n_observations  = n,
        frequency       = "D",
    )

    # Recent AR lags present (lag 1 always; lag 2 via PACF or safety net).
    assert 1 in lags
    assert 2 in lags
    # Seasonal enrichment: lag 7 (daily primary) must be present.
    assert 7 in lags


def test_select_autoregressive_output_when_pacf_with_seasonal_series():
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


def test_select_autoregressive_output_when_pacf_selects_few_lags():
    """
    Test the safety net: when PACF selects very few significant lags
    (e.g. white noise series), at least 3 recent lags are returned and
    seasonal enrichment still applies via the empty-candidate fallback.
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
    # Seasonal enrichment: lag 7 (daily) reached through the fallback path
    assert 7 in lags


def test_select_autoregressive_output_pacf_respects_max_lag_constraint():
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
# PACF horizon cap (n_lags_cap)
# ---------------------------------------------------------------------------
def _capture_requested_n_lags(monkeypatch) -> list[int]:
    """
    Patch `calculate_lag_autocorrelation` to record the `n_lags` argument
    requested by `compute_series_pacf`, returning the capture list.
    """
    import skforecast_ai.recommendation.autoregressive as ar

    captured: list[int] = []

    def _fake_calc(data, n_lags, sort_by):
        captured.append(n_lags)
        return pd.DataFrame(
            {
                "lag": [1],
                "partial_autocorrelation_abs": [0.0],
            }
        )

    monkeypatch.setattr(ar, "calculate_lag_autocorrelation", _fake_calc)
    return captured


def _pacf_profile(n_observations: int, frequency: str | None) -> DataProfile:
    """Build a single-series datetime profile for cap tests."""
    return DataProfile(
        n_series=1,
        series_lengths={"target": n_observations},
        target="target",
        index_type="datetime",
        frequency=frequency,
        target_stats={},
    )


def test_compute_series_pacf_n_lags_cap_bound_by_max_when_fine_frequency(
    monkeypatch,
):
    """
    Test that for a fine-grained frequency (minutely, seasonalities
    `[60, 1440]`) the requested `n_lags` is clamped to `MAX_PACF_CAP`
    rather than reaching `3 * 1440`, given a long enough series for the
    `n // 2 - 1` clamp not to bind first.
    """
    captured = _capture_requested_n_lags(monkeypatch)
    n = 4 * MAX_PACF_CAP  # n // 2 - 1 > MAX_PACF_CAP so the cap binds
    df = pd.DataFrame({"target": np.zeros(n)})

    compute_series_pacf(df, _pacf_profile(n, frequency="min"))

    assert captured == [MAX_PACF_CAP]


def test_compute_series_pacf_n_lags_cap_no_floor_when_coarse_frequency(
    monkeypatch,
):
    """
    Test that for a coarse frequency (yearly, seasonalities `[1]`) the
    requested `n_lags` follows `3 * last` and is no longer forced up to
    the old constant floor of 50.
    """
    captured = _capture_requested_n_lags(monkeypatch)
    n = 600  # large enough that the n // 2 - 1 clamp does not bind
    df = pd.DataFrame({"target": np.zeros(n)})

    compute_series_pacf(df, _pacf_profile(n, frequency="YE"))

    assert captured == [3]
    assert captured[0] < DEFAULT_PACF_CAP


def test_compute_series_pacf_n_lags_cap_default_when_no_frequency(monkeypatch):
    """
    Test that when no frequency (and thus no seasonality) is available,
    the requested `n_lags` falls back to `DEFAULT_PACF_CAP`.
    """
    captured = _capture_requested_n_lags(monkeypatch)
    n = 4 * DEFAULT_PACF_CAP
    df = pd.DataFrame({"target": np.zeros(n)})

    compute_series_pacf(df, _pacf_profile(n, frequency=None))

    assert captured == [DEFAULT_PACF_CAP]


# ---------------------------------------------------------------------------
# Window features: roll_std placement
# ---------------------------------------------------------------------------
def test_select_autoregressive_window_features_std_only_on_shortest_window():
    """
    Test that roll_std is added only on the shortest window while every
    longer window keeps roll_mean only.
    """
    series = _make_series(365)
    _, wf = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert wf is not None
    windows = [config["window_sizes"] for config in wf]
    shortest = min(windows)
    for config in wf:
        if config["window_sizes"] == shortest:
            assert "std" in config["stats"]
        else:
            assert config["stats"] == ["mean"]


def test_select_autoregressive_window_features_shortest_has_mean_and_std():
    """
    Test that the shortest window always carries both roll_mean and
    roll_std regardless of the series scale.
    """
    rng = np.random.default_rng(42)
    series = pd.Series(10.0 + rng.normal(0, 5, 365), name="target")

    _, wf = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert wf is not None
    assert wf[0]["stats"] == ["mean", "std"]


# ---------------------------------------------------------------------------
# Window features: structure
# ---------------------------------------------------------------------------
def test_select_autoregressive_output_window_features_for_daily():
    """
    Test select_autoregressive returns window features with seasonal
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


def test_select_autoregressive_output_window_features_for_hourly():
    """
    Test select_autoregressive returns a multi-scale window ladder
    (24, 48, 72) for hourly data with sufficient observations, with
    roll_std only on the shortest window.
    """
    series = _make_series(720)
    _, wf = select_lags_and_window_features(
        n_observations=720, frequency="h", target_series=series
    )

    assert wf is not None
    windows = [c["window_sizes"] for c in wf]
    # Multi-scale ladder: multiples of the primary season (24).
    assert 24 in windows
    assert 48 in windows
    assert 72 in windows

    # roll_std only on the shortest window (24); others keep mean only.
    shortest = min(windows)
    for config in wf:
        if config["window_sizes"] == shortest:
            assert "std" in config["stats"]
        else:
            assert config["stats"] == ["mean"]


def test_select_autoregressive_output_window_features_monthly():
    """
    Test select_autoregressive returns window features with window=12
    for monthly frequency.
    """
    series = _make_series(120)
    _, wf = select_lags_and_window_features(
        n_observations=120, frequency="ME", target_series=series
    )

    assert wf is not None
    short_config = wf[0]
    assert short_config["window_sizes"] == 12


def test_select_autoregressive_output_window_features_none_frequency():
    """
    Test select_autoregressive returns generic window features (window=7)
    when no frequency is provided but enough data exists.
    """
    series = _make_series(200)
    _, wf = select_lags_and_window_features(
        n_observations=200, frequency=None, target_series=series
    )

    assert wf is not None
    assert "mean" in wf[0]["stats"]
    assert wf[0]["window_sizes"] == 7


def test_select_autoregressive_output_window_features_capped_by_data_size():
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


def test_select_autoregressive_output_no_long_window_when_equals_short():
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
# Window features: extreme frequencies
# ---------------------------------------------------------------------------
def test_select_autoregressive_output_window_features_minutely():
    """
    Test the multi-scale window ladder for minutely data (primary season
    60) with enough observations, capped by the data budget.
    """
    series = _make_series(1000)
    _, wf = select_lags_and_window_features(
        n_observations=1000, frequency="min", target_series=series
    )

    assert wf is not None
    windows = [config["window_sizes"] for config in wf]
    assert 60 in windows
    max_window = int(1000 * 0.25)
    for w in windows:
        assert w <= max_window


def test_select_autoregressive_output_window_features_yearly_generic():
    """
    Test that an extreme low-period frequency (yearly, primary season 1)
    falls back to a generic short window instead of a degenerate window
    of size 1 or 2.
    """
    series = _make_series(100)
    _, wf = select_lags_and_window_features(
        n_observations=100, frequency="YS", target_series=series
    )

    assert wf is not None
    windows = [config["window_sizes"] for config in wf]
    assert 7 in windows
    for w in windows:
        assert w >= 3


def test_select_autoregressive_output_window_features_include_pacf_lag():
    """
    Test that the strongest PACF lag is added as an extra rolling window
    distinct from the seasonal ladder. With no frequency the ladder is
    the generic window (7); a series with strong period-12 memory
    contributes a longer window.
    """
    rng = np.random.default_rng(42)
    n = 240
    t = np.arange(n)
    y = np.sin(2 * np.pi * t / 12) + rng.normal(0, 0.3, n)
    series = pd.Series(y, name="target")

    _, wf = select_lags_and_window_features(
        n_observations=n, frequency=None, target_series=series
    )

    windows = [config["window_sizes"] for config in wf]
    assert 7 in windows
    # PACF-derived window added alongside the generic base window.
    assert len(windows) >= 2


# ---------------------------------------------------------------------------
# _strongest_pacf_window
# ---------------------------------------------------------------------------
def test_strongest_pacf_window_returns_strongest_non_trivial_lag():
    """
    Test that the strongest significant lag above 1 is returned when it
    fits the data budget and is distinct from existing windows.
    """
    sp = SeriesPacf(
        series_id="s", n_observations=200, lags=[1, 10, 3], pacf_abs=[0.9, 0.5, 0.2]
    )
    window = _strongest_pacf_window(
        series_pacf=[sp], max_window_allowed=50, existing_windows=[7]
    )

    assert window == 10


def test_strongest_pacf_window_None_when_only_lag_one():
    """
    Test that lag 1 is excluded (recent lags already cover it), so a
    primitive with only lag 1 yields no window.
    """
    sp = SeriesPacf(series_id="s", n_observations=200, lags=[1], pacf_abs=[0.9])

    assert _strongest_pacf_window([sp], max_window_allowed=50, existing_windows=[7]) is None


def test_strongest_pacf_window_None_when_near_existing_window():
    """
    Test that a candidate within one period of an existing window is
    discarded as redundant.
    """
    sp = SeriesPacf(series_id="s", n_observations=200, lags=[7], pacf_abs=[0.9])

    assert _strongest_pacf_window([sp], max_window_allowed=50, existing_windows=[7]) is None


def test_strongest_pacf_window_None_when_out_of_range():
    """
    Test that a candidate exceeding the data budget is discarded.
    """
    sp = SeriesPacf(series_id="s", n_observations=200, lags=[100], pacf_abs=[0.9])

    assert _strongest_pacf_window([sp], max_window_allowed=50, existing_windows=[7]) is None


# ---------------------------------------------------------------------------
# Lag pruning when rolling mean present
# ---------------------------------------------------------------------------
def test_select_autoregressive_lag_pruning_preserves_minimum_lags():
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
def test_select_autoregressive_output_returns_tuple():
    """
    Test that select_autoregressive always returns a 2-element tuple.
    """
    series = _make_series(365)
    result = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert isinstance(result, tuple)
    assert len(result) == 2


def test_select_autoregressive_output_lags_are_sorted_integers():
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
