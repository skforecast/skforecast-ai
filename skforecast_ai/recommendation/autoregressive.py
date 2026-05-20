"""Lag and window feature selection rules."""

from __future__ import annotations

import numpy as np
import pandas as pd
from skforecast.stats import calculate_lag_autocorrelation

from ..profiling.data_profile import estimate_seasonality


def select_lags_and_window_features(
    n_observations: int,
    frequency: str | None = None,
    target_series: pd.Series = None,
) -> tuple[list[int], list[dict] | None]:
    """
    Select lags and window features using PACF analysis of the target series.

    Lags are selected using the partial autocorrelation function (PACF):
    lags whose absolute PACF exceeds the asymptotic 95 % white-noise
    threshold (`1.96 / sqrt(n)`) are included. This is the data-aware
    approach recommended by the lag-selection skill.

    Window features follow the feature-engineering skill: a short-window
    `roll_mean` (and conditionally `roll_std` for heteroscedastic
    series) plus a long-window `roll_mean` for trend capture. When a
    rolling mean is added at window size W, redundant contiguous lags
    within that range are pruned.

    Parameters
    ----------
    n_observations : int
        Number of observations available for training.
    frequency : str, default None
        Pandas frequency string (e.g. `'h'`, `'D'`, `'ME'`). Used to
        determine seasonal periods. If None, a frequency-agnostic
        default is used.
    target_series : pandas Series, default None
        Target time series (NaN-free) for PACF-based lag selection.

    Returns
    -------
    lags : list of int
        Sorted list of lag indices to use as predictors.
    window_features : list of dict, None
        List of window feature configurations (dicts with keys
        `'stats'` and `'window_sizes'`) suitable for constructing
        `RollingFeatures` instances. None when the series is too short
        to benefit from rolling statistics.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`,
    `skforecast_ai/skills/feature-engineering/SKILL.md`.

    The PACF-based approach follows the skill end-to-end recipe:
    1. Rank lags by |PACF| using `calculate_lag_autocorrelation`.
    2. Filter by the asymptotic 95 % white-noise band: `1.96 / sqrt(n)`.
    3. Enrich with seasonal lags that may not exceed the threshold in
       short series but are structurally important.

    Window features follow the skill practical recipe:
    - `roll_mean` at the primary seasonal period (or generic 7) captures
      the recent level.
    - `roll_std` only when the series coefficient of variation > 0.1
      (heteroscedastic signal worth capturing).
    - A longer `roll_mean` (secondary period or 2x primary) captures
      trend-like slow dynamics.
    - Contiguous lags covered by a rolling mean window are pruned to
      avoid redundancy (skill anti-pattern: "shrink the lag set when
      you add the rolling stat").

    Constraints:
    - `max(lags) < n_observations // 3` (leave enough training rows).
    - `max_window_size < n_observations * 0.25` (preserve training data).
    - When the series is very short (< 30), only minimal lags are used
      and window features are skipped.
    """

    if target_series is None:
        raise ValueError(
            "`target_series` is required for lag selection. The series "
            "must be available from `ForecastingAnalysis.target_series`."
        )

    max_lag_allowed = max(n_observations // 3, 1)
    max_window_allowed = max(int(n_observations * 0.25), 1)

    seasonalities = estimate_seasonality(frequency)
    primary_season = seasonalities[0] if seasonalities else None
    secondary_season = seasonalities[1] if len(seasonalities) > 1 else None

    # --- Very short series: minimal lags, no window features ---
    if n_observations < 30:
        n_lags = min(5, max_lag_allowed)
        return list(range(1, n_lags + 1)), None

    # --- Build lag set from PACF ---
    lags = _select_lags_from_pacf(
        target_series, max_lag_allowed, primary_season, secondary_season
    )

    # --- Build window features ---
    window_features = _build_window_features(
        n_observations     = n_observations,
        max_window_allowed = max_window_allowed,
        primary_season     = primary_season,
        secondary_season   = secondary_season,
        target_series      = target_series,
    )

    # --- Prune redundant lags when rolling mean is present ---
    if window_features is not None:
        lags = _prune_redundant_lags(lags, window_features, primary_season)

    return lags, window_features


def _select_lags_from_pacf(
    target_series: pd.Series,
    max_lag_allowed: int,
    primary_season: int | None,
    secondary_season: int | None,
) -> list[int]:
    """
    Select lags using PACF significance (skill-recommended approach).

    Parameters
    ----------
    target_series : pandas Series
        Target time series (NaN-free).
    max_lag_allowed : int
        Maximum allowed lag index.
    primary_season : int, None
        Primary seasonal period.
    secondary_season : int, None
        Secondary seasonal period.

    Returns
    -------
    lags : list of int
        Sorted list of selected lag indices.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`.
    """

    n = len(target_series)
    # PACF requires nlags < n // 2
    n_lags = min(max_lag_allowed, n // 2 - 1)
    n_lags = max(n_lags, 1)

    lag_table = calculate_lag_autocorrelation(
        data=target_series, n_lags=n_lags
    )

    # Asymptotic 95% white-noise threshold
    threshold = 1.96 / np.sqrt(n)

    significant = lag_table.loc[
        lag_table["partial_autocorrelation_abs"] > threshold, "lag"
    ].astype(int).tolist()

    # Filter by max_lag_allowed
    lags = sorted(lag for lag in significant if lag <= max_lag_allowed)

    # Safety net: ensure at least 3 recent lags
    if len(lags) < 3:
        min_recent = min(5, max_lag_allowed)
        for lag in range(1, min_recent + 1):
            if lag not in lags:
                lags.append(lag)
        lags = sorted(lags)

    # Seasonal enrichment: ensure at least one seasonal lag is present
    if primary_season is not None and primary_season <= max_lag_allowed:
        if primary_season not in lags:
            lags.append(primary_season)
            lags = sorted(lags)

    if secondary_season is not None and secondary_season <= max_lag_allowed:
        if secondary_season not in lags:
            lags.append(secondary_season)
            lags = sorted(lags)

    return lags


def _build_window_features(
    n_observations: int,
    max_window_allowed: int,
    primary_season: int | None,
    secondary_season: int | None,
    target_series: pd.Series = None,
) -> list[dict] | None:
    """
    Build window feature configurations following the feature-engineering
    skill recommendations.

    Parameters
    ----------
    n_observations : int
        Number of observations available.
    max_window_allowed : int
        Maximum window size that preserves training data.
    primary_season : int, None
        Primary seasonal period.
    secondary_season : int, None
        Secondary seasonal period.
    target_series : pandas Series, default None
        Target series for coefficient of variation check.

    Returns
    -------
    window_features : list of dict, None
        Window feature configurations or None if not applicable.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    The skill recommends:
    - Always include `roll_mean` (the default smoothing signal).
    - Include `roll_std` only when the series is heteroscedastic
      (coefficient of variation > 0.1).
    - Multi-scale: combine short (reactive) and long (trend) windows.
    """
    if n_observations < 60:
        return None

    # Determine whether std is warranted (heteroscedasticity check)
    include_std = True
    if target_series is not None and len(target_series) > 0:
        mean_abs = abs(float(np.mean(target_series)))
        if mean_abs > 0:
            cv = float(np.std(target_series)) / mean_abs
            include_std = cv > 0.1

    if primary_season is not None:
        wf_configs = []

        # Short window: roll_mean (+ conditionally roll_std)
        short_window = min(primary_season, max_window_allowed)
        if short_window >= 3:
            stats = ["mean", "std"] if include_std else ["mean"]
            wf_configs.append({
                "stats": stats,
                "window_sizes": short_window,
            })

        # Long window: roll_mean at secondary period or 2x primary
        long_window_size = (
            secondary_season if secondary_season is not None
            else primary_season * 2
        )
        long_window_size = min(long_window_size, max_window_allowed)
        if long_window_size > short_window and long_window_size >= 5:
            wf_configs.append({
                "stats": ["mean"],
                "window_sizes": long_window_size,
            })

        return wf_configs if wf_configs else None

    # No frequency info but enough data: generic rolling window
    generic_window = min(7, max_window_allowed)
    if generic_window >= 3:
        stats = ["mean", "std"] if include_std else ["mean"]
        return [{"stats": stats, "window_sizes": generic_window}]

    return None


def _prune_redundant_lags(
    lags: list[int],
    window_features: list[dict],
    primary_season: int | None,
) -> list[int]:
    """
    Remove contiguous lags that overlap with a rolling mean window.

    When a `roll_mean` of window W is included, keeping all lags
    1..W is redundant for gradient boosting models (the tree can
    reconstruct the average from splits). Retain only representative
    lags (1, W//2, W) plus any seasonal lags within the range.

    Parameters
    ----------
    lags : list of int
        Current sorted lag list.
    window_features : list of dict
        Window feature configurations.
    primary_season : int, None
        Primary seasonal period (always preserved).

    Returns
    -------
    pruned_lags : list of int
        Reduced lag list.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`
    (anti-pattern: "keeping lags=range(1, 25) together with
    roll_mean_24 rarely helps").
    """
    # Find the shortest rolling mean window size
    mean_windows = []
    for wf in window_features:
        if "mean" in wf.get("stats", []):
            ws = wf.get("window_sizes")
            if isinstance(ws, int):
                mean_windows.append(ws)

    if not mean_windows:
        return lags

    shortest_mean_window = min(mean_windows)

    # Only prune if we have a solid contiguous block covered by the window
    contiguous_in_window = [lag for lag in lags if lag <= shortest_mean_window]
    if len(contiguous_in_window) < shortest_mean_window * 0.8:
        # Not enough contiguous coverage to justify pruning
        return lags

    # Preserve: lag 1, midpoint, window boundary, seasonal lags, lags > window
    keep = {1, shortest_mean_window // 2, shortest_mean_window}
    if primary_season is not None:
        keep.add(primary_season)

    pruned = []
    for lag in lags:
        if lag > shortest_mean_window:
            pruned.append(lag)
        elif lag in keep:
            pruned.append(lag)

    # Safety: always keep at least 3 lags
    if len(pruned) < 3:
        return lags

    return sorted(pruned)
