"""Frequency inference and seasonality estimation utilities."""

import pandas as pd


def infer_frequency(index: pd.DatetimeIndex) -> str | None:
    """
    Infer the frequency of a DatetimeIndex.

    Parameters
    ----------
    index : pandas DatetimeIndex
        The datetime index to infer frequency from.

    Returns
    -------
    frequency : str, None
        Inferred pandas frequency string, or None if the frequency cannot
        be determined (e.g. too few observations or irregular spacing).
    """
    if len(index) < 3:
        return None

    try:
        freq = pd.infer_freq(index)
    except (TypeError, ValueError):
        return None

    return freq


def estimate_seasonality(frequency: str | None) -> list[int]:
    """
    Estimate seasonal periods from a known frequency string.

    Parameters
    ----------
    frequency : str, None
        Pandas frequency string (e.g. `'h'`, `'D'`, `'ME'`).

    Returns
    -------
    seasonalities : list
        List of integer seasonal periods inferred from the frequency.
        Returns an empty list if the frequency is None or unrecognized.

    Notes
    -----
    This is a heuristic mapping. It does not perform spectral analysis
    or autocorrelation-based detection.
    """
    if frequency is None:
        return []

    freq_upper = frequency.upper()

    seasonality_map: dict[str, list[int]] = {
        "T":    [60, 1440],
        "MIN":  [60, 1440],
        "H":    [24, 168],
        "D":    [7, 365],
        "B":    [5, 252],
        "W":    [52],
        "MS":   [12],
        "ME":   [12],
        "M":    [12],
        "QS":   [4],
        "QE":   [4],
        "Q":    [4],
        "YS":   [1],
        "YE":   [1],
        "Y":    [1],
        "A":    [1],
    }

    for key, seasons in seasonality_map.items():
        if freq_upper == key or freq_upper.endswith(key):
            return seasons

    return []
