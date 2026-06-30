# Unit test autoregressive recommendation/autoregressive

import numpy as np
import pandas as pd

from skforecast_ai.recommendation.autoregressive import (
    _aggregate_lags_multiseries,
    _aggregate_lags_multivariate,
    compute_series_pacf,
    finalize_lags,
    select_window_features,
)
from skforecast_ai.schemas import DataProfile, SeriesPacf

# Mirror the function-local caps in compute_series_pacf.
MAX_PACF_CAP = 512
DEFAULT_PACF_CAP = 50


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
        task_type="single_series", n_observations=n_observations, frequency=frequency
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
def test_autoregressive_output_when_daily_frequency():
    """
    Test select_lags_and_window_features returns lags and seasonal lags for a
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


def test_autoregressive_output_when_hourly_frequency():
    """
    Test select_lags_and_window_features includes seasonal lag 24 for hourly data
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


def test_autoregressive_output_when_monthly_frequency():
    """
    Test select_lags_and_window_features returns seasonal lag 12 for monthly data.
    """
    series = _make_series(120)
    lags, wf = select_lags_and_window_features(
        n_observations=120, frequency="ME", target_series=series
    )

    # Seasonal enrichment: lag 12 must be present
    assert 12 in lags


def test_autoregressive_output_when_weekly_frequency():
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


def test_autoregressive_output_when_no_frequency():
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


def test_autoregressive_output_when_very_short_series():
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


def test_autoregressive_output_when_short_series_no_window_features():
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
def test_autoregressive_output_max_lag_respects_constraint():
    """
    Test that the maximum lag never exceeds n_observations // 3.
    """
    series = _make_series(100)
    lags, _ = select_lags_and_window_features(
        n_observations=100, frequency="h", target_series=series
    )

    assert max(lags) <= 100 // 3


def test_autoregressive_output_seasonal_lag_excluded_when_too_large():
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


def test_autoregressive_output_secondary_season_excluded_when_too_large():
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
def test_autoregressive_output_when_pacf_with_ar_series():
    """
    Test that select_lags_and_window_features selects lags using PACF when a
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


def test_autoregressive_output_when_pacf_with_seasonal_series():
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


def test_autoregressive_output_when_pacf_selects_few_lags():
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


def test_autoregressive_output_pacf_respects_max_lag_constraint():
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
    Patch `pacf` to record the `nlags` argument requested by
    `compute_series_pacf`, returning the capture list.
    """
    import skforecast_ai.recommendation.autoregressive as ar

    captured: list[int] = []

    def _fake_pacf(x, nlags):
        captured.append(nlags)
        return np.zeros(nlags + 1)  # all-zero PACF -> nothing passes threshold

    monkeypatch.setattr(ar, "pacf", _fake_pacf)
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
def test_autoregressive_window_features_std_only_on_shortest_window():
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


def test_autoregressive_window_features_shortest_has_mean_and_std():
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
def test_autoregressive_output_window_features_for_daily():
    """
    Test select_lags_and_window_features returns multi-scale window features (short, 
    weekly, trend multiple) for daily frequency with sufficient data.
    """
    series = _make_series(365)
    _, wf = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert wf is not None
    windows = [c["window_sizes"] for c in wf]
    assert 3 in windows
    assert 7 in windows
    assert 21 in windows


def test_autoregressive_output_window_features_for_hourly():
    """
    Test select_lags_and_window_features returns a multi-scale window ladder
    (3, 24, 168) for hourly data with sufficient observations, with
    roll_std only on the shortest window.
    """
    series = _make_series(720)
    _, wf = select_lags_and_window_features(
        n_observations=720, frequency="h", target_series=series
    )

    assert wf is not None
    windows = [c["window_sizes"] for c in wf]
    # Multi-scale ladder: short, primary season, secondary season.
    assert 3 in windows
    assert 24 in windows
    assert 168 in windows

    # roll_std only on the shortest window (24); others keep mean only.
    shortest = min(windows)
    for config in wf:
        if config["window_sizes"] == shortest:
            assert "std" in config["stats"]
        else:
            assert config["stats"] == ["mean"]


def test_autoregressive_output_window_features_monthly():
    """
    Test select_lags_and_window_features returns window features with window=3 and 12
    for monthly frequency.
    """
    series = _make_series(120)
    _, wf = select_lags_and_window_features(
        n_observations=120, frequency="ME", target_series=series
    )

    assert wf is not None
    windows = [c["window_sizes"] for c in wf]
    assert 3 in windows
    assert 12 in windows


def test_autoregressive_output_window_features_none_frequency():
    """
    Test select_lags_and_window_features returns short and generic window features (3, 7)
    when no frequency is provided but enough data exists.
    """
    series = _make_series(200)
    _, wf = select_lags_and_window_features(
        n_observations=200, frequency=None, target_series=series
    )

    assert wf is not None
    windows = [c["window_sizes"] for c in wf]
    assert 3 in windows
    assert 7 in windows


def test_autoregressive_output_window_features_capped_by_data_size():
    """
    Test that window sizes are capped at 33% of n_observations.
    For 60 observations with hourly data: max_window = int(60 * 0.33) = 19,
    primary=24 -> window capped to 19.
    """
    series = _make_series(60)
    _, wf = select_lags_and_window_features(
        n_observations=60, frequency="h", target_series=series
    )

    assert wf is not None
    max_window = int(60 * 0.33)
    for config in wf:
        assert config["window_sizes"] <= max_window


def test_autoregressive_output_no_long_window_when_equals_short():
    """
    Test that the seasonal/trend window is replaced by a single
    budget-capped window when the seasonal period exceeds the data budget.
    For monthly data with 60 observations the warm-up budget caps windows
    at 10, so the seasonal period 12 (and its multiples) does not fit and a
    single window capped at the budget is used instead, yielding a strictly
    increasing ladder with no window equal to the short one.
    """
    series = _make_series(60)
    _, wf = select_lags_and_window_features(
        n_observations=60, frequency="ME", target_series=series
    )

    assert wf is not None
    windows = [config["window_sizes"] for config in wf]
    # Short window (3) + a single budget-capped window (10); the seasonal
    # period 12 exceeds the 10-observation budget and is omitted.
    assert windows == [3, 10]
    # Strictly increasing: no degenerate window equal to the short one.
    assert windows == sorted(set(windows))


# ---------------------------------------------------------------------------
# Window features: extreme frequencies
# ---------------------------------------------------------------------------
def test_autoregressive_output_window_features_minutely():
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
    max_window = int(1000 * 0.33)
    for w in windows:
        assert w <= max_window


def test_autoregressive_output_window_features_yearly_generic():
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


# ---------------------------------------------------------------------------
# Lag pruning when rolling mean present
# ---------------------------------------------------------------------------
def test_autoregressive_lag_pruning_preserves_minimum_lags():
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
def test_autoregressive_output_returns_tuple():
    """
    Test that select_lags_and_window_features always returns a 2-element tuple.
    """
    series = _make_series(365)
    result = select_lags_and_window_features(
        n_observations=365, frequency="D", target_series=series
    )

    assert isinstance(result, tuple)
    assert len(result) == 2


def test_autoregressive_output_lags_are_sorted_integers():
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


# ---------------------------------------------------------------------------
# _aggregate_lags_multiseries (consensus)
# ---------------------------------------------------------------------------
def test_aggregate_lags_multiseries_keeps_shared_drops_rare():
    """
    Test the consensus floor: with 3 series and the default threshold of
    0.5 (floor = ceil(3 * 0.5) = 2), a lag significant in only one series
    is dropped while lags shared by at least two are kept, ranked by
    series-count descending.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=200, lags=[1, 2, 5], pacf_abs=[0.9, 0.5, 0.3]),
        SeriesPacf(series_id="b", n_observations=200, lags=[1, 2], pacf_abs=[0.8, 0.4]),
        SeriesPacf(series_id="c", n_observations=200, lags=[1], pacf_abs=[0.7]),
    ]

    result = _aggregate_lags_multiseries(series_pacf)

    # lag 1 (in 3 series) ranks first, lag 2 (in 2 series) next; lag 5
    # (only 1 series) is below the floor and excluded.
    assert result == [1, 2]


def test_aggregate_lags_multiseries_tie_broken_by_summed_pacf():
    """
    Test that lags with equal series-counts are ordered by summed `|PACF|`
    descending.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=200, lags=[3, 4], pacf_abs=[0.2, 0.9]),
        SeriesPacf(series_id="b", n_observations=200, lags=[3, 4], pacf_abs=[0.2, 0.9]),
    ]

    result = _aggregate_lags_multiseries(series_pacf)

    # Both lags appear in both series (count tie); lag 4 has the larger
    # summed magnitude (1.8 vs 0.4) so it ranks first.
    assert result == [4, 3]


def test_aggregate_lags_multiseries_falls_back_to_full_ranked_set():
    """
    Test that when the threshold leaves no lag passing the floor, the full
    ranked set is returned instead of an empty list.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=200, lags=[1, 2], pacf_abs=[0.9, 0.5]),
        SeriesPacf(series_id="b", n_observations=200, lags=[3, 4], pacf_abs=[0.8, 0.4]),
    ]

    # threshold 1.0 -> floor 2, but no lag is shared by both series.
    result = _aggregate_lags_multiseries(series_pacf, consensus_threshold=1.0)

    # Fallback: every lag, ranked by summed |PACF| descending.
    assert result == [1, 3, 2, 4]


def test_aggregate_lags_multiseries_empty_input():
    """
    Test that an empty primitive list yields an empty consensus list.
    """
    assert _aggregate_lags_multiseries([]) == []


# ---------------------------------------------------------------------------
# _aggregate_lags_multivariate (top-n union)
# ---------------------------------------------------------------------------
def test_aggregate_lags_multivariate_union_ordered_by_summed_pacf():
    """
    Test that the union of per-series lags is ordered by summed `|PACF|`
    across series, descending.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=200, lags=[1, 2], pacf_abs=[0.5, 0.3]),
        SeriesPacf(series_id="b", n_observations=200, lags=[2, 3], pacf_abs=[0.6, 0.1]),
    ]

    result = _aggregate_lags_multivariate(series_pacf, top_n=10)

    # Summed magnitudes: lag 2 -> 0.9, lag 1 -> 0.5, lag 3 -> 0.1.
    assert result == [2, 1, 3]


def test_aggregate_lags_multivariate_truncates_to_top_n_per_series():
    """
    Test that each series contributes only its strongest `top_n` lags, so
    a weaker lag beyond the cut is absent from the union.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=200, lags=[1, 2, 3], pacf_abs=[0.9, 0.8, 0.7]),
        SeriesPacf(series_id="b", n_observations=200, lags=[4], pacf_abs=[0.5]),
    ]

    result = _aggregate_lags_multivariate(series_pacf, top_n=2)

    # Series "a" contributes only lags 1 and 2 (top 2 by |PACF|); lag 3 is
    # truncated. Union ordered by summed |PACF|.
    assert 3 not in result
    assert result == [1, 2, 4]


def test_aggregate_lags_multivariate_empty_input():
    """
    Test that an empty primitive list yields an empty union list.
    """
    assert _aggregate_lags_multivariate([], top_n=10) == []


# ---------------------------------------------------------------------------
# finalize_lags: multi_series / multivariate dispatch (regression guards)
# ---------------------------------------------------------------------------
def test_finalize_lags_multi_series_end_to_end():
    """
    Test that the multi_series branch runs end-to-end and post-processes
    the consensus lags. This path raised a TypeError before the
    consensus_threshold keyword was fixed.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=365, lags=[1, 2, 7], pacf_abs=[0.9, 0.5, 0.3]),
        SeriesPacf(series_id="b", n_observations=365, lags=[1, 3, 7], pacf_abs=[0.8, 0.4, 0.3]),
    ]

    lags = finalize_lags(
        series_pacf    = series_pacf,
        task_type      = "multi_series",
        n_observations = 365,
        frequency      = "D",
    )

    assert lags == sorted(set(lags))
    assert all(isinstance(lag, int) and lag > 0 for lag in lags)
    # Consensus lag 1 retained; lag 7 present via seasonal enrichment (daily).
    assert 1 in lags
    assert 7 in lags


def test_finalize_lags_multi_series_consensus_threshold_threaded_through():
    """
    Test that the consensus_threshold argument actually reaches the
    aggregation step. Rare lags (10, 12) appear in only one series each
    and sit above the recent-lag safety-net range, so they survive at a
    permissive threshold and are dropped at a strict one.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=300, lags=[1, 10], pacf_abs=[0.9, 0.5]),
        SeriesPacf(series_id="b", n_observations=300, lags=[1, 12], pacf_abs=[0.8, 0.4]),
    ]
    kwargs = dict(
        series_pacf    = series_pacf,
        task_type      = "multi_series",
        n_observations = 300,
        frequency      = None,
    )

    permissive = finalize_lags(**kwargs, consensus_threshold=0.5)
    strict = finalize_lags(**kwargs, consensus_threshold=1.0)

    # floor 1: rare single-series lags kept.
    assert 10 in permissive and 12 in permissive
    # floor 2: only the shared lag survives consensus; the rare lags are
    # not reintroduced by the safety net (which only adds 1..5).
    assert 10 not in strict and 12 not in strict


def test_finalize_lags_multivariate_end_to_end():
    """
    Test that the multivariate branch runs end-to-end and that the top-n
    union lags survive the select_lags data budget.
    """
    series_pacf = [
        SeriesPacf(series_id="a", n_observations=300, lags=[1, 2, 10], pacf_abs=[0.9, 0.6, 0.4]),
        SeriesPacf(series_id="b", n_observations=300, lags=[2, 3], pacf_abs=[0.7, 0.5]),
    ]

    lags = finalize_lags(
        series_pacf    = series_pacf,
        task_type      = "multivariate",
        n_observations = 300,
        frequency      = None,
    )

    assert lags == sorted(set(lags))
    assert all(isinstance(lag, int) and lag > 0 for lag in lags)
    # Union of {1, 2, 10} and {2, 3}; all fit within max_lag = 300 // 3.
    assert lags == [1, 2, 3, 10]
