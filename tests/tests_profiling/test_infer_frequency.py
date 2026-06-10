# Unit test infer_frequency

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import estimate_seasonality, infer_frequency


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
        ("h", [24, 168]),
        ("D", [7, 365]),
        ("W", [52]),
        ("W-SUN", [52]),
        ("MS", [12]),
        ("ME", [12]),
        ("QS", [4]),
        ("QE", [4]),
        ("QS-OCT", [4]),
        ("QE-DEC", [4]),
        ("A-DEC", [1]),
        ("YE-DEC", [1]),
        (None, []),
        ("UNKNOWN", []),
    ],
    ids=lambda x: f"{x}",
)
def test_estimate_seasonality_output(freq, expected_seasonalities):
    """
    Test estimate_seasonality returns the correct heuristic seasonal periods
    for known frequency strings and empty list for unknown or None.
    """
    result = estimate_seasonality(freq)
    assert result == expected_seasonalities
