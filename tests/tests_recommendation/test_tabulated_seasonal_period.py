# Unit test tabulated_seasonal_period
"""Tests for the seasonal period read from FREQUENCY_TO_SEASONAL_PERIOD."""

import pytest

from skforecast_ai.recommendation.autoregressive import tabulated_seasonal_period


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("D", 7),
        ("h", 24),
        ("MS", 12),
        ("W-SUN", 52),
        ("W-WED", 52),
        ("QS-OCT", 4),
        ("QE-DEC", 4),
        ("YE-DEC", 1),
        ("YS-JAN", 1),
        ("M", 12),
        ("Q-DEC", 4),
        ("A-DEC", 1),
        ("AS-JAN", 1),
        ("H", 24),
        ("15T", 96),
    ],
    ids=lambda dt: f"frequency, expected: {dt}",
)
def test_tabulated_seasonal_period_output_when_base_alias_in_table(
    frequency, expected
):
    """
    Test that tabulated_seasonal_period returns the period of the table for
    a frequency in it, and the period of the base alias for an anchored
    frequency that is not ('W-WED' as 'W', 'QS-OCT' as 'QS'), also for the
    aliases pandas 2.1 infers ('M', 'Q-DEC', 'A-DEC', 'H', '15T').
    """
    assert tabulated_seasonal_period(frequency) == expected


@pytest.mark.parametrize(
    "frequency",
    [None, "2W", "2MS", "3h", "BQS-OCT", "unknown"],
    ids=lambda dt: f"frequency: {dt}",
)
def test_tabulated_seasonal_period_output_None_when_not_in_table(frequency):
    """
    Test that tabulated_seasonal_period returns None for no frequency, for
    multiplied frequencies and for aliases whose base is not in the table.
    """
    assert tabulated_seasonal_period(frequency) is None
