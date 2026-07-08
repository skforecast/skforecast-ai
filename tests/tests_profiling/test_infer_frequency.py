# Unit test infer_frequency

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import infer_frequency
from skforecast_ai.recommendation.autoregressive import estimate_seasonality


@pytest.mark.parametrize(
    "freq, expected",
    [
        ("h", "h"),
        ("D", "D"),
        ("W", "W-SUN"),
        ("MS", "MS"),
        ("ME", "ME"),
        ("QS", "QS-OCT"),
    ],
    ids=lambda x: f"{x}",
)
def test_infer_frequency_output_when_regular_series(freq, expected):
    """
    Test infer_frequency returns the correct frequency string for a
    regularly-spaced DatetimeIndex.
    """
    index = pd.date_range("2023-01-01", periods=100, freq=freq)
    result = infer_frequency(index)
    assert result == expected


def test_infer_frequency_output_when_irregular_series():
    """
    Test infer_frequency returns None when the DatetimeIndex has irregular
    spacing.
    """
    index = pd.DatetimeIndex(["2023-01-01", "2023-01-03", "2023-01-08", "2023-01-20"])
    result = infer_frequency(index)
    assert result is None


def test_infer_frequency_output_when_too_few_observations():
    """
    Test infer_frequency returns None when the index has fewer than 3
    observations.
    """
    index = pd.date_range("2023-01-01", periods=2, freq="D")
    result = infer_frequency(index)
    assert result is None


@pytest.mark.parametrize(
    "freq, expected_seasonalities",
    [
        # --- Base aliases (pandas 2.x lowercase) ---
        ("s",   [3_600, 86_400]),
        ("min", [60, 1_440]),
        ("h",   [24, 168]),
        ("D",   [7, 365]),
        # --- Legacy uppercase aliases ---
        ("T",   [60, 1_440]),
        ("H",   [24, 168]),
        # --- Business day (non-fixed, heuristic table) ---
        ("B",   [5, 252]),
        # --- Weekly (non-fixed, heuristic table) ---
        ("W",     [52]),
        ("W-SUN", [52]),
        # --- Monthly / quarterly / yearly (variable-length) ---
        ("MS",     [12]),
        ("ME",     [12]),
        ("QS",     [4]),
        ("QE",     [4]),
        ("QS-OCT", [4]),
        ("QE-DEC", [4]),
        ("A-DEC",  [1]),
        ("YE-DEC", [1]),
        # --- Multiplied sub-daily (previously wrong or missing) ---
        ("15min", [4, 96]),    # 15-min: 4/hour, 96/day
        ("15T",   [4, 96]),    # same via legacy alias
        ("30min", [2, 48]),    # 30-min: 2/hour, 48/day
        ("30s",   [120, 2_880]),  # 30-sec: 120/hour, 2880/day
        ("2h",    [12, 84]),   # 2-hour: 12/day, 84/week
        ("2H",    [12, 84]),   # same via legacy alias
        ("6h",    [4, 28]),    # 6-hour: 4/day, 28/week
        # --- Multiplied variable offsets (multiplier divides the table) ---
        ("2W",  [26]),   # biweekly: 26/year
        ("2MS", [6]),    # bi-monthly: 6/year
        ("2ME", [6]),    # same via period-end alias
        ("2QS", [2]),    # semi-annual: 2/year
        # --- Edge cases ---
        (None,      []),
        ("UNKNOWN", []),
    ],
    ids=lambda x: f"{x}",
)
def test_estimate_seasonality_output(freq, expected_seasonalities):
    """
    Test estimate_seasonality returns correct seasonal periods for base
    aliases, anchored offsets, legacy uppercase aliases, multiplied
    variants, and an empty list for unknown or None inputs.
    """
    result = estimate_seasonality(freq)
    assert result == expected_seasonalities
