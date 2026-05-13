"""Stage 3: Forecaster-specific analysis context."""

from __future__ import annotations

import pandas as pd

from .._constants import (
    FOUNDATION_FORECASTERS,
    MULTI_SERIES_FORECASTERS,
    MULTIVARIATE_FORECASTERS,
    SINGLE_ML_FORECASTERS,
    STATS_FORECASTERS,
)
from ..schemas import ForecasterAnalysis, DataProfile


def create_forecaster_analysis(
    data: pd.DataFrame | None,
    profile: DataProfile,
    forecaster: str,
) -> ForecasterAnalysis:
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
    context : ForecasterAnalysis
        Analysis results tailored to the selected forecaster type.
    """
    if forecaster in MULTI_SERIES_FORECASTERS:
        return _analyze_multi_series(data, profile)
    if forecaster in MULTIVARIATE_FORECASTERS:
        return _analyze_multivariate(data, profile)
    if forecaster in SINGLE_ML_FORECASTERS:
        return _analyze_single_ml(data, profile)
    if forecaster in FOUNDATION_FORECASTERS:
        return _analyze_foundation(data, profile)
    if forecaster in STATS_FORECASTERS:
        return _analyze_stats(data, profile)

    return ForecasterAnalysis(effective_n_observations=profile.n_observations)


def _analyze_multi_series(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> ForecasterAnalysis:
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
    context : ForecasterAnalysis
        Includes per-series length statistics.
    """
    # Use series_lengths from the profile (already computed in Stage 1)
    if profile.series_lengths is not None:
        lengths = profile.series_lengths
        total_len = sum(lengths.values())
        min_len = min(lengths.values())
        max_len = max(lengths.values())
        ratio = max_len / min_len if min_len > 0 else None
        short = [name for name, n in lengths.items() if n < 50]

        # Pick first target series for PACF-based lag selection
        target_series = None
        if data is not None:
            if isinstance(profile.target, list):
                # Wide format: columns are series
                for col in profile.target:
                    if col in data.columns:
                        s = _prepare_series_for_pacf(data[col])
                        if len(s) > 0:
                            target_series = s
                            break
            elif (
                isinstance(profile.target, str)
                and profile.series_id_column is not None
                and profile.series_id_column in data.columns
                and profile.target in data.columns
            ):
                # Long format: extract target from first series group
                first_id = data[profile.series_id_column].iloc[0]
                subset = data.loc[
                    data[profile.series_id_column] == first_id, profile.target
                ]
                s = _prepare_series_for_pacf(subset.reset_index(drop=True))
                if len(s) > 0:
                    target_series = s

        return ForecasterAnalysis(
            effective_n_observations=total_len,
            min_series_length=min_len,
            max_series_length=max_len,
            series_length_ratio=ratio,
            short_series=short if short else None,
            target_series=target_series,
        )

    # Fallback: no series_lengths available
    return ForecasterAnalysis(
        effective_n_observations=profile.n_observations,
        min_series_length=None,
        max_series_length=None,
        series_length_ratio=None,
    )


def _analyze_multivariate(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> ForecasterAnalysis:
    """
    Compute analysis context for multivariate forecasters.

    For `ForecasterDirectMultiVariate`, the effective number of
    observations is the length of the target series (all series share
    the same time axis and the target is what constrains training).

    Parameters
    ----------
    data : pandas DataFrame, None
        Raw input data.
    profile : DataProfile
        Universal data profile.

    Returns
    -------
    context : ForecasterAnalysis
        Context based on target series length.
    """
    # n_observations in DataProfile already reflects per-series length
    # for wide-format data (all columns share the same index).
    return ForecasterAnalysis(
        effective_n_observations=profile.n_observations,
    )


def _analyze_single_ml(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> ForecasterAnalysis:
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
    context : ForecasterAnalysis
        Includes trend and variance indicators.
    """
    target_has_trend = None
    target_variance = None
    target_series = None

    if data is not None:
        target_col = (
            profile.target[0] if isinstance(profile.target, list)
            else profile.target
        )
        if target_col in data.columns:
            target_series = _prepare_series_for_pacf(data[target_col])
            if len(target_series) > 0:
                target_variance = float(target_series.var())

    return ForecasterAnalysis(
        effective_n_observations=profile.n_observations,
        target_has_trend=target_has_trend,
        target_variance=target_variance,
        target_series=target_series,
    )


def _analyze_foundation(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> ForecasterAnalysis:
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
    context : ForecasterAnalysis
        Includes viable context length.
    """
    # TODO: compute viable_context_length based on model defaults
    # (e.g. Chronos-2 max 8192, TimesFM 512, Moirai 2048)
    viable_context_length = min(profile.n_observations, 2048)

    return ForecasterAnalysis(
        effective_n_observations=profile.n_observations,
        viable_context_length=viable_context_length,
    )


def _analyze_stats(
    data: pd.DataFrame | None,
    profile: DataProfile,
) -> ForecasterAnalysis:
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
    context : ForecasterAnalysis
        Basic context for statistical models.
    """
    # TODO: seasonal order candidates, stationarity hints
    return ForecasterAnalysis(
        effective_n_observations=profile.n_observations,
    )


def _prepare_series_for_pacf(series: pd.Series) -> pd.Series:
    """
    Prepare a series for PACF computation by trimming edge NaNs and
    interpolating interior ones.

    Dropping interspersed NaNs would collapse the temporal structure,
    making lag relationships meaningless. Instead, leading/trailing NaNs
    are stripped and interior gaps are filled with linear interpolation.

    Parameters
    ----------
    series : pandas Series
        Raw target series (may contain NaN).

    Returns
    -------
    clean : pandas Series
        Series without NaN, preserving temporal ordering.
    """
    # Strip leading and trailing NaNs
    first_valid = series.first_valid_index()
    last_valid = series.last_valid_index()

    if first_valid is None:
        return series.iloc[0:0]  # empty series

    trimmed = series.loc[first_valid:last_valid]

    # Interpolate interior NaNs (linear preserves temporal structure)
    if trimmed.isna().any():
        trimmed = trimmed.interpolate(method="linear")

    return trimmed
