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
    alias (e.g. `'15min' -> (15, 'MIN')`, `'2W' -> (2, 'W')`).

    Variable-length / non-fixed offsets (week, month, quarter, year and
    the business day) are read from a static heuristic table because
    their duration is not a fixed timedelta. The multiplier divides the
    tabulated periods, so `'2W'` (biweekly) yields `[26]` and
    `'2MS'` (bi-monthly) yields `[6]`.

    All other offsets are resolved with
    `pd.tseries.frequencies.to_offset`. Only `Tick` offsets have a
    true fixed duration; the interval in seconds is derived via
    `pd.Timedelta` and divided into the standard cycles (hour, day,
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

        # Benjamini-Hochberg (FDR) correction. `norm.sf` (survival function)
        # is used instead of `1 - norm.cdf` to preserve precision in the far
        # tail where `1 - cdf` would lose significant digits.
        z_scores = pacf_abs * np.sqrt(n_valid)
        p_values = 2 * norm.sf(z_scores)
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


def _max_window_size_allowed(
    n_observations: int,
    max_fraction_allowed: float,
    n_reserved_rows: int = 0,
) -> int:
    """
    Compute the largest `window_size` the data budget can afford.

    The `window_size` is the number of leading observations a forecaster
    consumes before it can emit its first training row, i.e.
    `max(max(lags), max(window_sizes), differentiation)`. Lags and window
    features draw from this single shared budget rather than independent
    budgets: the forecaster's real `window_size` is the maximum of the two,
    not their sum, so capping each at the same value keeps the combined
    `window_size` within budget.

    The budget is `int(n * max_fraction_allowed)` (minus any
    `n_reserved_rows`), so at least `1 - max_fraction_allowed` of the
    observations always remain for training. Short series are protected
    separately by the `n < 30` (lags) and `n < 60` (window features) guards
    in their respective selectors.

    Parameters
    ----------
    n_observations : int
        Number of observations available for training (per series).
    max_fraction_allowed : float
        Maximum fraction of `n_observations` the `window_size` may span.
    n_reserved_rows : int, default 0
        Additional rows consumed beyond the `window_size` that must be left
        for training. For direct multi-step forecasters the last-step
        regressor loses `steps - 1` extra rows, so pass `steps - 1` to keep
        the effective training set within the same budget. Recursive
        forecasters reserve nothing.

    Returns
    -------
    max_window_size : int
        Largest `window_size` (in observations) that respects the budget,
        floored at 1.
    """
    budget = int(n_observations * max_fraction_allowed) - max(n_reserved_rows, 0)
    return max(budget, 1)


def select_lags(
    candidate_lags: list[int],
    n_observations: int,
    seasonalities: list[int] | None = None,
    n_max_selected: int = 200,
    max_fraction_allowed: float = 0.33,
    n_reserved_rows: int = 0,
) -> list[int]:
    """
    Post-process a candidate lag set into the final lag list.

    This function acts as a structural safety net for the forecasting model,
    ensuring that the statistically significant lags generated by the PACF
    analysis do not violate data budget constraints or leave the model without
    critical short-term momentum. 
    
    It applies the following sequence of rules:
    
    1. Maximum-lag constraint: Enforces a strict data budget where the maximum
       lag cannot exceed a specified fraction of the total observations
       (default 33%), ensuring enough data remains for training.
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
    max_fraction_allowed : float, default 0.33
        Maximum fraction of `n_observations` that a lag can span.
        Prevents features from consuming too much of the training data.
    n_reserved_rows : int, default 0
        Rows consumed beyond the `window_size` that must stay available for
        training, subtracted from the lag budget. For direct multi-step
        forecasters pass `steps - 1` (the last-step regressor loses that
        many extra rows); recursive forecasters reserve nothing.

    Returns
    -------
    lags : list of int
        Sorted list of lag indices to use as predictors.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`.

    Constraints:
    - `max(lags) < int(n_observations * max_fraction_allowed)` (leave enough training rows).
    - When the series is very short (< 30), only minimal lags are used.

    """

    max_lag_allowed = _max_window_size_allowed(
        n_observations, max_fraction_allowed, n_reserved_rows
    )
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


def select_window_features(
    task_type: str,
    n_observations: int,
    frequency: str | None,
    min_window: int = 3,
    max_window_multiple: int = 3,
    generic_window: int = 7,
    max_fraction_allowed: float = 0.33,
) -> list[dict] | None:
    """
    Build window feature configurations following the feature-engineering
    skill recommendations.

    Generates a multi-scale ladder of rolling window sizes designed to capture
    short-term reactivity, seasonal patterns, and long-term trends without
    exhausting the training data budget.

    Parameters
    ----------
    task_type : str
        Forecasting task type implied by the chosen forecaster.
    n_observations : int
        Number of observations available (per series).
    frequency : str, None
        Pandas frequency string used to determine seasonal periods.
    min_window : int, default 3
        The smallest rolling window worth computing (a 1-2 period mean 
        adds no smoothing over the raw lags).
    max_window_multiple : int, default 3
        Caps the multi-scale ladder at this many multiples of the primary 
        seasonal period so the rolling windows stay short relative to the 
        training history.
    generic_window : int, default 7
        Fallback window size used when the frequency is non-seasonal or
        when the primary seasonal period is extremely short.
    max_fraction_allowed : float, default 0.33
        Maximum fraction of `n_observations` that a window can span.
        Prevents rolling features from consuming too much training data.

    Returns
    -------
    window_features : list of dict, None
        List of window feature configurations (dicts with keys
        `'stats'` and `'window_size'`) suitable for constructing
        `RollingFeatures` instances. Returns None when the series is too
        short to benefit from rolling statistics, or if the chosen model
        does not support them.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    Selection Logic Progression:
    
    1. Data Budgeting: The absolute maximum allowed window is strictly
       capped at a fraction of the total observations (default 33%).
       If the series is too short (< 60 observations) or this cap is
       smaller than the `min_window`, no windows are generated.
    2. Short-term Reactivity: Always includes the `min_window` to
       capture immediate momentum and volatility.
    3. Seasonal Scaling: Adds the usable seasonal periods derived from the
       `frequency` (those at least `min_window` wide and within the data
       budget). A rolling mean over a full seasonal cycle is a low-pass filter,
       so these windows capture the *local level at the seasonal scale* (the
       deseasonalized trend-cycle), not the seasonal shape itself; the seasonal
       shape is carried by the lags selected in `select_lags`. The branch keys
       off the set of usable periods rather than only the shortest cycle, so a
       usable secondary period is kept even when the primary cycle is shorter
       than `min_window` (e.g. `"12h" -> [2, 14]` keeps 14).
    4. Trend Fallbacks: If the frequency is seasonal:
       - If two seasonal periods fit, the ladder is complete.
       - If only *one* fits, the algorithm searches backwards from
         `max_window_multiple` down to `2` to find the largest multiple of that
         period which still fits the data budget, creating a distinct
         long-term trend window. (The `max_fraction_allowed` budget already
         leaves ample history for training, so no extra cycle restriction is
         applied.)
       - If *no* period fits because every seasonal period exceeds the budget,
         it falls back to a single long window capped exactly at the data
         budget limit.
    5. Non-Seasonal Fallbacks: If the frequency has no seasonality (or only
       periods shorter than `min_window`), it adds the `generic_window`
       instead.
    6. Statistic Assignment: The standard deviation (`"std"`) is only
       computed on the shortest (most reactive) window in the ladder to avoid
       flattening out the volatility signal. All longer windows calculate
       only the `"mean"`.
    """

    if task_type in ("statistical", "foundation"):
        return None

    if n_observations < 60:
        return None

    # Windows draw from the same `window_size` budget as lags (see
    # `_max_window_size_allowed`); the forecaster's real `window_size` is the
    # max of the two, so sharing one cap keeps the combined `window_size`
    # within budget. This budget is horizon-agnostic: window features are
    # selected at profile time, before the forecast `steps` are known.
    max_window_allowed = _max_window_size_allowed(n_observations, max_fraction_allowed)
    if max_window_allowed < min_window:
        return None

    windows = [min_window]
    seasonalities = estimate_seasonality(frequency)
    # Seasonal periods that are usable as windows: at least `min_window` wide
    # and within the data budget. Branching on this set (rather than only the
    # smallest period) keeps a usable secondary period even when the primary
    # cycle is too short to be a window (e.g. "12h" -> [2, 14] keeps 14).
    usable_seasons = [s for s in seasonalities if min_window <= s <= max_window_allowed]

    if usable_seasons:
        primary_season = usable_seasons[0]
        windows.extend(usable_seasons)

        if len(usable_seasons) == 1:
            # Only the primary period fits: add a longer trend window at the
            # largest multiple of it that still fits the data budget.
            for k in range(max_window_multiple, 1, -1):
                multiple = primary_season * k
                if multiple <= max_window_allowed:
                    windows.append(multiple)
                    break
    elif any(s > max_window_allowed for s in seasonalities):
        # Seasonality exists but every period exceeds the data budget: a single
        # window capped at the budget proxies the long-term trend.
        windows.append(max_window_allowed)
    else:
        # No seasonality (or only periods shorter than min_window).
        windows.append(generic_window)

    # Clamp the generic fallback to the budget; every other entry is already in
    # range by construction.
    windows = sorted({w for w in windows if min_window <= w <= max_window_allowed})

    # roll_std only on the shortest (most reactive) window; roll_mean on all.
    shortest = windows[0]
    wf_configs = [
        {
            "stats": ["mean", "std"] if w == shortest else ["mean"],
            "window_size": w,
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
    n_max_selected: int = 200,
    max_fraction_allowed: float = 0.33,
    n_reserved_rows: int = 0,
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
    (`1..min(5, int(n * max_fraction))`) is returned. Otherwise applies
    `select_lags`. The primary seasonal period is computed internally so
    callers stay free of seasonality logic.

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
    n_max_selected : int, default 200
        Maximum number of lags selected, forwarded to `select_lags`.
    max_fraction_allowed : float, default 0.33
        Maximum fraction of `n_observations` that a lag can span.
    n_reserved_rows : int, default 0
        Rows consumed beyond the `window_size` that must stay available for
        training, forwarded to `select_lags`. For direct multi-step
        forecasters pass `steps - 1`; recursive forecasters reserve
        nothing.

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
        max_lag_allowed = _max_window_size_allowed(
            n_observations, max_fraction_allowed, n_reserved_rows
        )
        candidate_lags = list(range(1, min(5, max_lag_allowed) + 1))

    lags = select_lags(
               candidate_lags       = candidate_lags,
               n_observations       = n_observations,
               seasonalities        = seasonalities,
               n_max_selected       = n_max_selected,
               max_fraction_allowed = max_fraction_allowed,
               n_reserved_rows      = n_reserved_rows,
           )

    return lags
