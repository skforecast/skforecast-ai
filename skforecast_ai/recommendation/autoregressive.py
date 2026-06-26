"""Lag and window feature selection rules."""

from __future__ import annotations
import math
import re
import warnings
import numpy as np
import pandas as pd
from scipy.stats import norm
from skforecast.stats import pacf
from ..schemas import DataProfile, SeriesPacf


def estimate_seasonality(frequency: str | None) -> list[int]:
    """
    Estimate seasonal periods from a known frequency string.

    Parameters
    ----------
    frequency : str, None
        Pandas frequency string. Handles base aliases (`'h'`, `'D'`),
        anchored offsets (`'W-SUN'`, `'QS-OCT'`), multiplied variants
        (`'15min'`, `'2h'`, `'2W'`), and legacy uppercase aliases.

    Returns
    -------
    seasonalities : list of int
        Up to two integer seasonal periods in ascending order (primary,
        then secondary). Returns an empty list when the frequency is
        None, unrecognized, or has no meaningful sub-period cycle.

    Notes
    -----
    The frequency is split into an optional integer multiplier and a base
    alias (e.g. ``'15min' -> (15, 'MIN')``, ``'2W' -> (2, 'W')``).

    Variable-length / non-fixed offsets (week, month, quarter, year and
    the business day) are read from a static heuristic table because
    their duration is not a fixed timedelta. The multiplier divides the
    tabulated periods, so ``'2W'`` (biweekly) yields ``[26]`` and
    ``'2MS'`` (bi-monthly) yields ``[6]``.

    All other offsets are resolved with
    ``pd.tseries.frequencies.to_offset``. Only ``Tick`` offsets have a
    true fixed duration; the interval in seconds is derived via
    ``pd.Timedelta`` and divided into the standard cycles (hour, day,
    week, 365-day year). The two shortest qualifying cycles (periods
    >= 2) are returned.
    """
    if frequency is None:
        return []

    # Seasonal periods for variable-length / non-fixed offsets, whose duration
    # is not a fixed timedelta (month length varies; business day skips
    # weekends). Read from this static heuristic table rather than computed.
    non_fixed_seasonality: dict[str, list[int]] = {
        "B":  [5, 252],
        "W":  [52],
        "MS": [12], "ME": [12], "M": [12],
        "QS": [4],  "QE": [4],  "Q": [4],
        "YS": [1],  "YE": [1],  "Y": [1], "A": [1],
    }
    # Standard cycle lengths in seconds (hour, day, week, 365-day year) used to
    # derive periods-per-cycle for fixed-interval offsets.
    cycle_seconds = [3_600, 86_400, 604_800, 31_536_000]

    # Split an optional integer multiplier from the alias, then strip any
    # anchor suffix (e.g. "W-SUN" -> "W", "QS-OCT" -> "QS").
    match = re.match(r"^(\d*)([A-Za-z].*)$", frequency.strip())
    if not match:
        return []
    multiplier = int(match.group(1)) if match.group(1) else 1
    base = match.group(2).upper().split("-")[0]

    # Variable-length / non-fixed offsets: read periods-per-cycle from the
    # table and divide by the multiplier. The >= 1 floor (not >= 2) keeps
    # the degenerate yearly period (e.g. "YE" -> [1]).
    if base in non_fixed_seasonality:
        return [
            p // multiplier
            for p in non_fixed_seasonality[base]
            if p // multiplier >= 1
        ]

    # Fixed-interval offsets: resolve to an exact timedelta and derive the
    # periods per standard cycle. Legacy uppercase aliases ("H", "T") still
    # resolve but emit a deprecation warning, which is intentional and
    # silenced here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        try:
            offset = pd.tseries.frequencies.to_offset(frequency)
        except (ValueError, TypeError):
            return []

    if not isinstance(offset, pd.tseries.offsets.Tick):
        return []

    interval_seconds = pd.Timedelta(offset).total_seconds()
    if interval_seconds <= 0:
        return []

    seasons = [
        int(c // interval_seconds)
        for c in cycle_seconds
        if c // interval_seconds >= 2
    ]
    return seasons[:2]


def compute_series_pacf(
    data: pd.DataFrame,
    profile: DataProfile,
    default_pacf_lags: int = 50,
    max_pacf_lags: int = 512,
    min_effect_size: float = 0.1
) -> list[SeriesPacf]:
    """
    Compute PACF-significant lags for every series in the dataset using
    Benjamini-Hochberg FDR correction and a minimum effect-size floor.

    Iterates the series implied by the data format (single, wide list of
    target columns, or long via `series_id_column`), runs PACF on each
    cleaned series, and applies a two-stage filter to retain only lags
    that are both statistically significant and practically meaningful.
    Results are ordered by descending `|PACF|` so downstream aggregation
    can take the top-n.

    Parameters
    ----------
    data : pandas DataFrame
        Raw input data the `profile` was built from.
    profile : DataProfile
        Universal data profile from Stage 1. Its `frequency` is used to
        derive the candidate PACF window so seasonal lags are never
        excluded.
    default_pacf_lags : int, default 50
        PACF horizon used when the frequency is unknown or carries no
        detectable seasonality.
    max_pacf_lags : int, default 512
        Hard cap on the PACF horizon. Bounds compute for fine-grained
        frequencies (e.g. minutely) where three seasonal cycles would
        otherwise require thousands of lags.
    min_effect_size : float, default 0.1
        Minimum absolute PACF magnitude a lag must exceed to be retained,
        applied after the statistical test. Prevents spurious far-lag
        spikes whose `|PACF|` is technically significant but negligible
        in magnitude from inflating `max(lags)`.

    Returns
    -------
    series_pacf : list of SeriesPacf
        One entry per valid series. Empty when no valid series exist.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`.

    NaN handling is delegated to `pacf`, which strips leading/trailing
    non-finite values and falls back to pairwise deletion for interior
    gaps. Runs one PACF per series, so wide datasets incur one PACF
    computation per column.

    Lag-selection pipeline (per series):

    1. Compute PACF for lags 1..`effective_n_lags`, where
       `effective_n_lags = min(3 * seasonalities[-1], max_pacf_lags)`
       when seasonality is known, or `default_pacf_lags` otherwise.
       Further clamped to `n_valid // 2 - 1` as required by the PACF
       estimator.
    2. Convert absolute PACF values to z-scores
       (`|pacf[k]| * sqrt(n_valid)`) and two-tailed p-values under the
       white-noise null (`pacf[k] ~ N(0, 1/n)`).
    3. Apply **Benjamini-Hochberg (BH) FDR correction** at `alpha = 0.05`
       across all `m = effective_n_lags` lags: sort p-values ascending,
       find the largest rank `k*` where `p_(k) <= (k/m) * 0.05`, then
       retain all lags with `p <= p_(k*)`.
    4. Apply the **effect-size floor**: discard lags with
       `|PACF| <= min_effect_size`, regardless of statistical significance.

    BH controls the expected proportion of false discoveries (FDR) rather
    than the per-comparison error rate. It is more powerful than Bonferroni
    for wide PACF horizons while still suppressing the spurious far-lag
    spikes that would inflate `max(lags)` and shrink the training window.

    """

    seasonalities = estimate_seasonality(profile.frequency)
    n_lags = (
        min(3 * seasonalities[-1], max_pacf_lags)
        if seasonalities else default_pacf_lags
    )

    if isinstance(profile.target, list):
        # Wide format: each target column is a series.
        series = [(col, data[col]) for col in profile.target]
    elif profile.series_id_column is not None:
        # Long format: group by series id.
        series = [
            (str(sid), group[profile.target])
            for sid, group in data.groupby(profile.series_id_column)
        ]
    else:
        # Single series.
        series = [(profile.target, data[profile.target])]

    results: list[SeriesPacf] = []
    for series_id, values in series:
        # At least non-NaN observations are needed to calculate PACF
        n_valid = int(values.count())
        if n_valid < 4:
            continue

        # PACF requires nlags < n_valid // 2; clamp without mutating the
        # outer cap so subsequent series still use the full horizon.
        effective_n_lags = max(min(n_lags, n_valid // 2 - 1), 1)
        pacf_values = pacf(values, nlags=effective_n_lags)
        lags_arr = np.arange(1, effective_n_lags + 1)
        pacf_abs = np.abs(pacf_values[1:])

        # Benjamini-Hochberg (FDR) correction
        z_scores = pacf_abs * np.sqrt(n_valid)
        p_values = 2 * (1 - norm.cdf(z_scores))
        sort_idx = np.argsort(p_values)
        sorted_p_values = p_values[sort_idx]
        alpha_fdr = 0.05
        m = effective_n_lags
        k_ranks = np.arange(1, m + 1)
        bh_critical_values = (k_ranks / m) * alpha_fdr
        valid_k_indices = np.where(sorted_p_values <= bh_critical_values)[0]
        if len(valid_k_indices) > 0:
            max_k_idx = valid_k_indices[-1]
            p_threshold = sorted_p_values[max_k_idx]
            stat_mask = p_values <= p_threshold
        else:
            # If nothing passes, the mask is entirely False
            stat_mask = np.zeros_like(p_values, dtype=bool)

        # Minimum effect-size mask
        min_effect_mask = pacf_abs > min_effect_size
        mask = stat_mask & min_effect_mask

        sel_lags = lags_arr[mask]
        sel_abs = pacf_abs[mask]
        # Order by descending |PACF| so downstream top-n aggregation is correct.
        order = np.argsort(-sel_abs, kind="stable")

        results.append(
            SeriesPacf(
                series_id      = str(series_id),
                n_observations = n_valid,
                lags           = sel_lags[order].astype(int).tolist(),
                pacf_abs       = sel_abs[order].astype(float).tolist(),
            )
        )

    return results


def _aggregate_lags_multiseries(
    series_pacf: list[SeriesPacf],
    consensus_threshold: float = 0.5,
) -> list[int]:
    """
    Aggregate lags for global multi-series models using a consensus approach.

    Lags are ranked by the number of series in which they are
    significant (descending), ties broken by summed `|PACF|`. Lags that
    appear in a minimum proportion of series (defined by the threshold)
    are kept; if that floor leaves no lags, the full ranked set is
    returned instead.

    Parameters
    ----------
    series_pacf : list of SeriesPacf
        Per-series PACF primitive.
    consensus_threshold : float, default 0.5
        Proportion of series in which a lag must be significant to be
        kept.

    Returns
    -------
    combined_lags : list of int
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

    floor = math.ceil(len(series_pacf) * consensus_threshold)
    combined_lags = [lag for lag in ranked if counts[lag] >= floor]

    if not combined_lags:
        combined_lags = ranked

    return combined_lags


def _aggregate_lags_multivariate(
    series_pacf: list[SeriesPacf],
    top_n: int,
) -> list[int]:
    """
    Aggregate lags for multivariate models using a top-n union approach.

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
    combined_lags : list of int
        Union lags ordered by descending importance.
    """
    magnitudes: dict[int, float] = {}
    for sp in series_pacf:
        for lag, mag in zip(sp.lags[:top_n], sp.pacf_abs[:top_n]):
            magnitudes[lag] = magnitudes.get(lag, 0.0) + mag

    if not magnitudes:
        return []

    combined_lags = sorted(magnitudes, key=lambda lag: magnitudes[lag], reverse=True)

    return combined_lags


def select_lags(
    candidate_lags: list[int],
    n_observations: int,
    seasonalities: list[int] | None = None,
    n_max_selected: int = 200,
) -> list[int]:
    """
    Post-process a candidate lag set into the final lag list.

    This function acts as a structural safety net for the forecasting model,
    ensuring that the statistically significant lags generated by the PACF
    analysis do not violate data budget constraints or leave the model without
    critical short-term momentum. 
    
    It applies the following sequence of rules:
    
    1. Maximum-lag constraint: Enforces a strict data budget where the maximum
       lag cannot exceed 1/3 of the total observations, ensuring enough data 
       remains for training.
    2. Very-short-series early return: If the series has fewer than 30 
       observations, it abandons the PACF candidates and returns a minimal 
       sequence of recent lags.
    3. Importance-ordered cap: Truncates the valid candidates to a maximum of
       `n_max_selected` lags to prevent an excess of features, dropping the weakest
       drivers first.
    4. Recent-lag safety net: Injects up to 5 recent lags (e.g., 1, 2, 3) if
       the PACF filtering left the model "blind" to immediate prior values.
    5. Seasonal enrichment: Forces the inclusion of the primary seasonal period
       (if it fits within the data budget) to capture foundational cyclicality.

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
    n_max_selected: int, default 200
        Maximum number of lags selected.

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

    if n_observations < 30:
        n_lags = min(5, max_lag_allowed)
        lags = list(range(1, n_lags + 1))
        return lags

    # Filter candidate lags by max_lag_allowed
    lags = [lag for lag in candidate_lags if 1 <= lag <= max_lag_allowed]
    # Limit the number of selected lags to maximum `n_max_selected`
    if len(lags) > n_max_selected:
        lags = lags[:n_max_selected]

    # Safety net: ensure at least 3 recent lags.
    if len(lags) < 3:
        min_recent = min(5, max_lag_allowed)
        lags.extend(range(1, min_recent + 1))

    # Seasonal enrichment
    if primary_season is not None and primary_season <= max_lag_allowed:
        if primary_season not in lags:
            lags.append(primary_season)

    return sorted(set(lags))


def _strongest_pacf_window(
    series_pacf: list[SeriesPacf],
    max_window_allowed: int,
    existing_windows: list[int],
    min_window: int = 3,
) -> int | None:
    """
    Pick a long rolling window from the strongest PACF lag.

    Scans every series' significant lags and returns the lag with the
    largest `|PACF|` (excluding lag 1, which the recent lags already
    cover) that fits the data budget and is distinct from the seasonal
    windows. Candidates are tried in descending `|PACF|` order, so a very
    short strongest lag (below `min_window`) does not block a weaker but
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
    min_window : int, default 3
        The smallest rolling window worth computing.

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
        if not (min_window <= lag <= max_window_allowed):
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
    min_window: int = 3,
    max_window_multiple: int = 3,
    generic_window: int = 7,
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
    min_window : int, default 3
        The smallest rolling window worth computing (a 1-2 period mean 
        adds no smoothing over the raw lags).
    max_window_multiple : int, default 3
        Caps the multi-scale ladder at this many multiples of the primary 
        seasonal period (e.g. daily -> 7, 14, 21) so the rolling windows 
        stay short relative to the training history.
    generic_window : int, default 7
        Fallback window size used when the frequency is non-seasonal.

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
      `max_window_multiple` multiples.
    - Extreme frequencies are handled by the bounds: sub-`min_window`
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
    if max_window_allowed < min_window:
        return None

    seasonalities = estimate_seasonality(frequency)
    primary_season = seasonalities[0] if seasonalities else None

    if primary_season is not None and primary_season >= min_window:
        # Multi-scale ladder: multiples of the primary seasonal period.
        windows = [primary_season * k for k in range(1, max_window_multiple + 1)]
        windows = [w for w in windows if min_window <= w <= max_window_allowed]
        if not windows:
            # Primary period exceeds the data budget: single capped window.
            capped = min(primary_season, max_window_allowed)
            windows = [capped] if capped >= min_window else []
    else:
        windows = [min(generic_window, max_window_allowed)]

    if not windows:
        return None

    # PACF-informed long window: strongest non-trivial lag, when distinct.
    pacf_window = _strongest_pacf_window(
        series_pacf        = series_pacf,
        max_window_allowed = max_window_allowed,
        existing_windows   = windows,
        min_window         = min_window,
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
    consensus_threshold: float = 0.5,
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
    consensus_threshold : float, default 0.5
        Threshold for multi-series lag consensus.

    Returns
    -------
    lags : list of int
        Final sorted lag list.
    
    """

    if not series_pacf:
        candidate_lags: list[int] = []
    elif task_type == "multi_series":
        candidate_lags = _aggregate_lags_multiseries(
            series_pacf, consensus_threshold=consensus_threshold
        )
    elif task_type == "multivariate":
        candidate_lags = _aggregate_lags_multivariate(series_pacf, top_n)
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
