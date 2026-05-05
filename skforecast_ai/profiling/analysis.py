"""Stage 3: Forecaster-specific analysis context."""

from __future__ import annotations

import pandas as pd

from .._constants import (
    FOUNDATION_FORECASTERS,
    MULTI_SERIES_FORECASTERS,
    SINGLE_ML_FORECASTERS,
    STATS_FORECASTERS,
)
from ..schemas import AnalysisContext, DataProfile


def create_analysis_context(
    data: pd.DataFrame | None,
    profile: DataProfile,
    forecaster: str,
) -> AnalysisContext:
    """
    Compute forecaster-specific analysis from the data and profile.

    Parameters
    ----------
    data : pandas DataFrame, None
        Raw input data. When None, only profile-based defaults are used.
    profile : DataProfile
        Universal data profile from Stage 1.
    forecaster : str
        Forecaster class name selected in Stage 2.

    Returns
    -------
    context : AnalysisContext
        Analysis results tailored to the selected forecaster type.
    """
    if forecaster in MULTI_SERIES_FORECASTERS:
        return _analyze_multi_series(data, profile)
    if forecaster in SINGLE_ML_FORECASTERS:
        return _analyze_single_ml(data, profile)
    if forecaster in FOUNDATION_FORECASTERS:
        return _analyze_foundation(data, profile)
    if forecaster in STATS_FORECASTERS:
        return _analyze_stats(data, profile)

    return AnalysisContext(effective_n_observations=profile.n_observations)


def _analyze_multi_series(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> AnalysisContext:
    """
    Compute analysis context for multi-series forecasters.

    Parameters
    ----------
    data : pandas DataFrame, None
        Raw input data.
    profile : DataProfile
        Universal data profile.

    Returns
    -------
    context : AnalysisContext
        Includes per-series length statistics.
    """
    # Use series_lengths from the profile (already computed in Stage 1)
    if profile.series_lengths is not None:
        lengths = profile.series_lengths
        min_len = min(lengths.values())
        max_len = max(lengths.values())
        ratio = max_len / min_len if min_len > 0 else None
        short = [name for name, n in lengths.items() if n < 50]

        return AnalysisContext(
            effective_n_observations=min_len,
            min_series_length=min_len,
            max_series_length=max_len,
            series_length_ratio=ratio,
            short_series=short if short else None,
        )

    # Fallback: no series_lengths available
    return AnalysisContext(
        effective_n_observations=profile.n_observations,
        min_series_length=None,
        max_series_length=None,
        series_length_ratio=None,
    )


def _analyze_single_ml(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> AnalysisContext:
    """
    Compute analysis context for single-series ML forecasters.

    Parameters
    ----------
    data : pandas DataFrame, None
        Raw input data.
    profile : DataProfile
        Universal data profile.

    Returns
    -------
    context : AnalysisContext
        Includes trend and variance indicators.
    """
    target_has_trend = None
    target_variance = None

    if data is not None:
        target_col = (
            profile.target[0] if isinstance(profile.target, list)
            else profile.target
        )
        if target_col in data.columns:
            target_series = data[target_col].dropna()
            if len(target_series) > 0:
                target_variance = float(target_series.var())
            # TODO: trend detection (compare mean of first/second half,
            #       or Mann-Kendall heuristic)

    return AnalysisContext(
        effective_n_observations=profile.n_observations,
        target_has_trend=target_has_trend,
        target_variance=target_variance,
    )


def _analyze_foundation(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> AnalysisContext:
    """
    Compute analysis context for foundation model forecasters.

    Parameters
    ----------
    data : pandas DataFrame, None
        Raw input data.
    profile : DataProfile
        Universal data profile.

    Returns
    -------
    context : AnalysisContext
        Includes viable context length.
    """
    # TODO: compute viable_context_length based on model defaults
    # (e.g. Chronos-2 max 8192, TimesFM 512, Moirai 2048)
    viable_context_length = min(profile.n_observations, 2048)

    return AnalysisContext(
        effective_n_observations=profile.n_observations,
        viable_context_length=viable_context_length,
    )


def _analyze_stats(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> AnalysisContext:
    """
    Compute analysis context for statistical model forecasters.

    Parameters
    ----------
    data : pandas DataFrame, None
        Raw input data.
    profile : DataProfile
        Universal data profile.

    Returns
    -------
    context : AnalysisContext
        Basic context for statistical models.
    """
    # TODO: seasonal order candidates, stationarity hints
    return AnalysisContext(
        effective_n_observations=profile.n_observations,
    )
