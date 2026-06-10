"""Lag and window feature selection rules."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm
from skforecast.stats import calculate_lag_autocorrelation

from ..profiling.data_profile import estimate_seasonality
from ..schemas import DataProfile, SeriesPacf

# PACF horizon (`n_lags_cap`) bounds. The cap scales with the largest seasonal
# period (`3 * seasonalities[-1]`) so PACF can see a few seasonal cycles, but is
# clamped to `MAX_PACF_CAP` to bound compute on fine-grained frequencies (e.g.
# minutely, whose 3-day reach would otherwise be 4320 lags). Seasonal lags
# beyond the ceiling are not lost: `select_lags` re-adds them via seasonal
# enrichment. `DEFAULT_PACF_CAP` is the fallback when the frequency is unknown
# or carries no seasonality.
DEFAULT_PACF_CAP = 50
MAX_PACF_CAP = 512

# Window feature bounds. `MIN_WINDOW` is the smallest rolling window worth
# computing (a 1-2 period mean adds no smoothing over the raw lags).
# `MAX_WINDOW_MULTIPLE` caps the multi-scale ladder at three multiples of the
# primary seasonal period (e.g. daily -> 7, 14, 21) so the rolling windows stay
# short relative to the training history.
MIN_WINDOW = 3
MAX_WINDOW_MULTIPLE = 3
GENERIC_WINDOW = 7


def compute_series_pacf(
    data: pd.DataFrame,
    profile: DataProfile,
) -> list[SeriesPacf]:
    """
    Compute PACF-significant lags for every series in the dataset.

    Iterates the series implied by the data format (single, wide list of
    target columns, or long via `series_id_column`), runs PACF on each
    cleaned series, and keeps lags whose `|PACF|` exceeds the asymptotic
    95 % white-noise threshold (`1.96 / sqrt(n)`). Results are ordered by
    descending `|PACF|` so downstream aggregation can take the top-n.

    Parameters
    ----------
    data : pandas DataFrame
        Raw input data the `profile` was built from.
    profile : DataProfile
        Universal data profile from Stage 1. Its `frequency` is used to
        derive the candidate PACF window so seasonal lags are never
        excluded.

    Returns
    -------
    series_pacf : list of SeriesPacf
        One entry per valid series. Empty when no valid series exist.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`.

    NaN handling is delegated to `calculate_lag_autocorrelation`, which
    strips leading/trailing non-finite values and falls back to pairwise
    deletion for interior gaps. Runs one PACF per series, so wide datasets
    incur one PACF computation per column.

    Significance uses a Bonferroni-corrected threshold. Testing `n_lags`
    lags at a fixed per-lag 5 % level yields ~`0.05 * n_lags` spurious
    spikes by chance; on a wide PACF horizon (e.g. 504 lags hourly) these
    isolated far-lag false positives survive into `select_lags` and become
    an expensive `max(lags)` that drops that many training rows. Correcting
    the family-wise error rate (`alpha = 0.05 / n_lags`) raises the bar so
    only genuinely significant lags pass.

    """

    seasonalities = estimate_seasonality(profile.frequency)
    n_lags_cap = (
        min(3 * seasonalities[-1], MAX_PACF_CAP)
        if seasonalities else DEFAULT_PACF_CAP
    )

    if isinstance(profile.target, list):
        # Wide format: each target column is a series.
        raw_series = [(col, data[col]) for col in profile.target]
    elif profile.series_id_column is not None:
        # Long format: group by series id.
        raw_series = [
            (str(sid), group[profile.target])
            for sid, group in data.groupby(profile.series_id_column)
        ]
    else:
        # Single series.
        raw_series = [(profile.target, data[profile.target])]

    results: list[SeriesPacf] = []
    for series_id, raw in raw_series:
        n = int(raw.count())
        if n < 4:
            continue

        # PACF requires n_lags < n_finite // 2.
        n_lags = max(min(n_lags_cap, n // 2 - 1), 1)
        lag_table = calculate_lag_autocorrelation(
            data=raw, n_lags=n_lags, sort_by="partial_autocorrelation_abs"
        )
        # Bonferroni-corrected white-noise threshold: split the 5 %
        # family-wise error across the `n_lags` tested lags so isolated
        # far-lag noise no longer passes as significant.
        alpha = 0.05 / n_lags
        threshold = norm.ppf(1 - alpha / 2) / np.sqrt(n)
        significant = lag_table.loc[
            lag_table["partial_autocorrelation_abs"] > threshold
        ]

        results.append(
            SeriesPacf(
                series_id      = str(series_id),
                n_observations = n,
                lags           = significant["lag"].astype(int).tolist(),
                pacf_abs       = (
                    significant["partial_autocorrelation_abs"]
                    .astype(float).tolist()
                ),
            )
        )

    return results


def _aggregate_consensus(series_pacf: list[SeriesPacf]) -> list[int]:
    """
    Consensus aggregation for global multi-series models.

    Lags are ranked by the number of series in which they are
    significant (descending), ties broken by summed `|PACF|`. Lags that
    appear in at least half of the series are kept; if that floor leaves
    no lags, the full ranked set is returned instead.

    Parameters
    ----------
    series_pacf : list of SeriesPacf
        Per-series PACF primitive.

    Returns
    -------
    lags : list of int
        Consensus lags ordered by descending importance.
    """
    counts: dict[int, int] = {}
    magnitudes: dict[int, float] = {}
    for sp in series_pacf:
        for lag, mag in zip(sp.lags, sp.pacf_abs):
            counts[lag] = counts.get(lag, 0) + 1
            magnitudes[lag] = magnitudes.get(lag, 0.0) + mag

    if not counts:
        return []

    ranked = sorted(
        counts,
        key=lambda lag: (counts[lag], magnitudes[lag]),
        reverse=True,
    )

    floor = math.ceil(len(series_pacf) / 2)
    consensus = [lag for lag in ranked if counts[lag] >= floor]

    return consensus if consensus else ranked


def _aggregate_top_n_union(
    series_pacf: list[SeriesPacf],
    top_n: int,
) -> list[int]:
    """
    Top-n union aggregation for multivariate models.

    Each series contributes its top-n lags by `|PACF|`. The union is
    ordered by descending summed `|PACF|` across series.

    Parameters
    ----------
    series_pacf : list of SeriesPacf
        Per-series PACF primitive.
    top_n : int
        Number of top lags taken per series.

    Returns
    -------
    lags : list of int
        Union lags ordered by descending importance.
    """
    magnitudes: dict[int, float] = {}
    for sp in series_pacf:
        for lag, mag in zip(sp.lags[:top_n], sp.pacf_abs[:top_n]):
            magnitudes[lag] = magnitudes.get(lag, 0.0) + mag

    if not magnitudes:
        return []

    return sorted(magnitudes, key=lambda lag: magnitudes[lag], reverse=True)


def select_lags(
    candidate_lags: list[int],
    n_observations: int,
    seasonalities: list[int] | None = None,
) -> list[int]:
    """
    Post-process a candidate lag set into the final lag list.

    Applies the maximum-lag constraint, a very-short-series early
    return, an importance-ordered cap, a recent-lag safety net, and
    seasonal enrichment.

    Parameters
    ----------
    candidate_lags : list of int
        Candidate lags ordered by descending importance (the aggregated
        PACF lags computed in `finalize_lags`).
    n_observations : int
        Number of observations available for training (per series).
    seasonalities : list of int, default None
        Seasonal periods for the series frequency (from
        `estimate_seasonality`). Only the primary period is used, for
        seasonal enrichment. If None or empty, no enrichment is applied.

    Returns
    -------
    lags : list of int
        Sorted list of lag indices to use as predictors.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`.

    Constraints:
    - `max(lags) < n_observations // 3` (leave enough training rows).
    - When the series is very short (< 30), only minimal lags are used.

    """

    max_lag_allowed = max(n_observations // 3, 1)

    primary_season = seasonalities[0] if seasonalities else None

    # --- Very short series: minimal lags ---
    if n_observations < 30:
        n_lags = min(5, max_lag_allowed)
        return list(range(1, n_lags + 1))

    # Filter candidate lags by max_lag_allowed and cap the total,
    # keeping the most important lags (candidate_lags is already ordered
    # by descending importance).
    max_selected = 200
    lags = [lag for lag in candidate_lags if 1 <= lag <= max_lag_allowed]
    lags = lags[:max_selected]

    # Safety net: ensure at least 3 recent lags.
    if len(lags) < 3:
        min_recent = min(5, max_lag_allowed)
        for lag in range(1, min_recent + 1):
            if lag not in lags:
                lags.append(lag)

    # Seasonal enrichment: force only the primary (short) seasonal cycle.
    # The secondary/long cycle (e.g. yearly lag 365 on daily data) is
    # deliberately not force-added: it is left to PACF (the `n_lags_cap`
    # horizon reaches it, so a genuine signal is still detected) and to
    # calendar exog features, which capture long seasonality without the
    # data cost of a long lag (`window_size = max(lags)` drops that many
    # training rows and demands that much prediction history).
    if primary_season is not None and primary_season <= max_lag_allowed:
        if primary_season not in lags:
            lags.append(primary_season)

    return sorted(set(lags))


def _strongest_pacf_window(
    series_pacf: list[SeriesPacf],
    max_window_allowed: int,
    existing_windows: list[int],
) -> int | None:
    """
    Pick a long rolling window from the strongest PACF lag.

    Scans every series' significant lags and returns the lag with the
    largest `|PACF|` (excluding lag 1, which the recent lags already
    cover) that fits the data budget and is distinct from the seasonal
    windows. Candidates are tried in descending `|PACF|` order, so a very
    short strongest lag (below `MIN_WINDOW`) does not block a weaker but
    usable longer lag.

    Parameters
    ----------
    series_pacf : list of SeriesPacf
        Per-series PACF primitive from `compute_series_pacf`.
    max_window_allowed : int
        Maximum window size permitted by the data budget.
    existing_windows : list of int
        Windows already selected from the seasonal ladder. A candidate
        within one period of any of these is discarded as redundant.

    Returns
    -------
    window : int, None
        Rolling window size derived from the strongest usable PACF lag,
        or None when no suitable lag exists.
    """

    candidates: list[tuple[float, int]] = []
    for sp in series_pacf:
        for lag, mag in zip(sp.lags, sp.pacf_abs):
            if lag > 1:
                candidates.append((mag, lag))

    for _, lag in sorted(candidates, key=lambda c: c[0], reverse=True):
        if not (MIN_WINDOW <= lag <= max_window_allowed):
            continue
        if any(abs(lag - w) <= 1 for w in existing_windows):
            continue
        return lag

    return None


def select_window_features(
    task_type: str,
    n_observations: int,
    frequency: str | None,
    series_pacf: list[SeriesPacf],
) -> list[dict] | None:
    """
    Build window feature configurations following the feature-engineering
    skill recommendations.

    Parameters
    ----------
    task_type : str
        Forecasting task type implied by the chosen forecaster.
    n_observations : int
        Number of observations available (per series).
    frequency : str, None
        Pandas frequency string used to determine seasonal periods.
    series_pacf : list of SeriesPacf
        Per-series PACF primitive from `compute_series_pacf`. The
        strongest significant lag informs an extra long rolling window.

    Returns
    -------
    window_features : list of dict, None
        List of window feature configurations (dicts with keys
        `'stats'` and `'window_sizes'`) suitable for constructing
        `RollingFeatures` instances. None when the series is too short
        to benefit from rolling statistics.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    The selection logic:
    - Multi-scale `roll_mean` over multiples of the primary seasonal
      period (e.g. daily -> 7, 14, 21; hourly -> 24, 48, 72), capped at
      `MAX_WINDOW_MULTIPLE` multiples.
    - Extreme frequencies are handled by the bounds: sub-`MIN_WINDOW`
      primary periods (e.g. yearly, primary 1) fall back to a generic
      window, and large periods are capped by the data budget.
    - An extra `roll_mean` at the strongest PACF lag (when distinct from
      the seasonal windows) captures non-seasonal memory.
    - `roll_std` is added only on the shortest window (the most reactive
      volatility signal); longer windows keep `roll_mean` only.
    - `max_window_size < n_observations * 0.25` (preserve training data).
    - When the series is very short (< 60), window features are skipped.
    """

    if task_type in ("statistical", "foundation"):
        return None

    if n_observations < 60:
        return None

    max_window_allowed = max(int(n_observations * 0.25), 1)
    if max_window_allowed < MIN_WINDOW:
        return None

    seasonalities = estimate_seasonality(frequency)
    primary_season = seasonalities[0] if seasonalities else None

    if primary_season is not None and primary_season >= MIN_WINDOW:
        # Multi-scale ladder: multiples of the primary seasonal period.
        windows = [primary_season * k for k in range(1, MAX_WINDOW_MULTIPLE + 1)]
        windows = [w for w in windows if MIN_WINDOW <= w <= max_window_allowed]
        if not windows:
            # Primary period exceeds the data budget: single capped window.
            capped = min(primary_season, max_window_allowed)
            windows = [capped] if capped >= MIN_WINDOW else []
    else:
        windows = [min(GENERIC_WINDOW, max_window_allowed)]

    if not windows:
        return None

    # PACF-informed long window: strongest non-trivial lag, when distinct.
    pacf_window = _strongest_pacf_window(
        series_pacf        = series_pacf,
        max_window_allowed = max_window_allowed,
        existing_windows   = windows,
    )
    if pacf_window is not None:
        windows.append(pacf_window)

    windows = sorted(set(windows))

    # roll_std only on the shortest (most reactive) window; roll_mean on all.
    shortest = windows[0]
    wf_configs = [
        {
            "stats": ["mean", "std"] if w == shortest else ["mean"],
            "window_sizes": w,
        }
        for w in windows
    ]

    return wf_configs


def finalize_lags(
    series_pacf: list[SeriesPacf],
    task_type: str,
    n_observations: int,
    frequency: str | None,
    top_n: int = 10,
) -> list[int]:
    """
    Aggregate per-series PACF lags and post-process into a final lag list.

    First aggregates the per-series PACF primitive into a single
    importance-ordered candidate set, with a strategy that depends on how
    the chosen forecaster shares lags across series:

    - single-series (one series): that series' lags.
    - multi_series (global model): consensus — lags ranked by how many
      series they appear in, ties broken by summed `|PACF|`.
    - multivariate: union of the top-n `|PACF|` lags of each series.

    When no PACF primitive is available, a minimal recent-lag fallback
    (`1..min(5, n // 3)`) is returned. Otherwise applies `select_lags`.
    The primary seasonal period is computed internally so callers stay
    free of seasonality logic.

    Parameters
    ----------
    series_pacf : list of SeriesPacf
        Per-series PACF primitive from `compute_series_pacf`.
    task_type : str
        Forecasting task type implied by the chosen forecaster.
    n_observations : int
        Per-series number of observations (gating constraint).
    frequency : str, None
        Pandas frequency string.
    top_n : int, default 10
        Number of top lags taken per series for the multivariate union.

    Returns
    -------
    lags : list of int
        Final sorted lag list.
    
    """

    if not series_pacf:
        candidate_lags: list[int] = []
    elif task_type == "multi_series":
        candidate_lags = _aggregate_consensus(series_pacf)
    elif task_type == "multivariate":
        candidate_lags = _aggregate_top_n_union(series_pacf, top_n)
    else:
        # single_series (or any single-series primitive): pass through.
        candidate_lags = list(series_pacf[0].lags)

    seasonalities = estimate_seasonality(frequency)

    if not candidate_lags:
        # Fallback when no significant PACF lags are available (e.g. white
        # noise, or every lag filtered out by the significance threshold):
        # seed with a few recent lags so `select_lags` still applies the
        # safety net and seasonal enrichment.
        candidate_lags = list(range(1, min(5, max(n_observations // 3, 1)) + 1))

    lags = select_lags(
               candidate_lags = candidate_lags,
               n_observations = n_observations,
               seasonalities  = seasonalities,
           )

    return lags
