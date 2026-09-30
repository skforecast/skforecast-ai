# Unit test select_baseline_config
"""Tests for the select_baseline_config recommendation function."""

import pytest

from skforecast_ai.recommendation import select_baseline_config
from skforecast_ai.schemas import DataProfile


def _make_profile(frequency: str | None, n_observations: int) -> DataProfile:
    """Build a single-series DataProfile with the given frequency and length."""
    return DataProfile(
        n_series       = 1,
        series_lengths = {"y": n_observations},
        target         = "y",
        index_type     = "datetime",
        frequency      = frequency,
    )


@pytest.mark.parametrize(
    "frequency, n_observations, expected_offset",
    [
        ("D", 365, 7),
        ("h", 720, 24),
        ("MS", 120, 12),
        ("W-SUN", 520, 52),
        ("15min", 2880, 96),
        ("30min", 1440, 48),
        ("2W", 260, 26),
    ],
    ids=lambda dt: f"frequency, n_observations, expected_offset: {dt}",
)
def test_select_baseline_config_output_when_seasonal_period_fits(
    frequency, n_observations, expected_offset
):
    """
    Test that the offset is the seasonal period of the frequency when one
    period fits in the lag budget: the daily cycle for sub-hourly data (not
    the hourly one), and the primary period of `estimate_seasonality()` for
    frequencies missing from `FREQUENCY_TO_SEASONAL_PERIOD` (`'2W'`).
    """
    kwargs, explanation = select_baseline_config(
        _make_profile(frequency, n_observations)
    )

    assert kwargs == {"offset": expected_offset, "n_offsets": 1}
    assert explanation == (
        f"Baseline: seasonal naive, each step repeats the value observed "
        f"{expected_offset} steps earlier (one seasonal period)."
    )


def test_select_baseline_config_output_when_seasonal_period_exceeds_budget():
    """
    Test that the baseline falls back to a naive forecast when one seasonal
    period spans more than a third of the observations.
    """
    kwargs, explanation = select_baseline_config(_make_profile("MS", 24))

    assert kwargs == {"offset": 1, "n_offsets": 1}
    assert explanation == (
        "Baseline: naive, each step repeats the last observed value (the "
        "seasonal period (12) spans more than 33% of the observations)."
    )


@pytest.mark.parametrize(
    "frequency",
    [None, "YS"],
    ids=lambda frequency: f"frequency: {frequency}",
)
def test_select_baseline_config_output_when_no_seasonal_period(frequency):
    """
    Test that the baseline falls back to a naive forecast when the frequency
    is unknown or has no sub-period cycle.
    """
    kwargs, explanation = select_baseline_config(_make_profile(frequency, 100))

    assert kwargs == {"offset": 1, "n_offsets": 1}
    assert explanation == (
        "Baseline: naive, each step repeats the last observed value (no "
        "seasonal period is known for this frequency)."
    )
