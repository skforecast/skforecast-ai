# Unit test arima_seasonal_period
"""Tests for the seasonal period m of Auto-ARIMA."""

import pytest

from skforecast_ai.recommendation.autoregressive import arima_seasonal_period


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("D", 7),
        ("h", 24),
        ("MS", 12),
        ("ME", 12),
        ("W-SUN", 52),
        ("QS-OCT", 4),
        ("YS-JAN", 1),
        ("B", 5),
        ("min", 60),
        ("15min", 96),
        ("2D", 7),
        ("15T", 96),
    ],
    ids=lambda dt: f"frequency, expected: {dt}",
)
def test_arima_seasonal_period_output_when_frequency_in_table(frequency, expected):
    """
    Test that arima_seasonal_period returns the period of
    FREQUENCY_TO_SEASONAL_PERIOD for a frequency in it, also anchored or
    with an alias of pandas 2.1, whatever estimate_seasonality says.
    """
    assert arima_seasonal_period(frequency) == expected


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("2W-SUN", 26),
        ("4W-WED", 13),
        ("2MS", 6),
        ("4ME", 3),
        ("2M", 6),
        ("2QS-OCT", 2),
        ("5D", 73),
        ("3h", 8),
        ("3H", 8),
        ("12h", 2),
        ("14h", 12),
        ("2min", 30),
        ("20min", 3),
        ("s", 3600),
        ("S", 3600),
        ("10s", 360),
        ("45min", 32),
        ("us", 3_600_000_000),
    ],
    ids=lambda dt: f"frequency, expected: {dt}",
)
def test_arima_seasonal_period_output_when_whole_cycle_not_in_table(
    frequency, expected
):
    """
    Test that arima_seasonal_period returns the first period of
    estimate_seasonality for a frequency not in the table when it is a
    whole cycle: 2 weeks in a year of 52, 2 months in a year, 3 hours in a
    day, 14 hours in a week, a second in an hour, 45 minutes in a day and a
    microsecond in an hour (Auto-ARIMA fits a non-seasonal model when the
    series is shorter than two periods).
    """
    assert arima_seasonal_period(frequency) == expected


@pytest.mark.parametrize(
    "frequency",
    [
        "3D",
        "4D",
        "3W-SUN",
        "5MS",
        "7MS",
        "3QS-OCT",
        "2B",
        "5h",
        "7h",
        "15h",
        "7min",
        "7s",
        "ms",
        "2ms",
        "L",
        None,
        "unknown",
        "BQS-OCT",
    ],
    ids=lambda dt: f"frequency: {dt}",
)
def test_arima_seasonal_period_output_None_when_no_whole_cycle(frequency):
    """
    Test that arima_seasonal_period returns None when the first period of
    estimate_seasonality is not a whole cycle ('3D': 2 steps are 6 days;
    '7h': 3 steps are 21 hours, even though its second period, the week,
    is whole), is 1 ('7MS'), the business week is not split in two ('2B'), or there is none (no frequency, an unknown one,
    an offset without a fixed length outside the table). Milliseconds are
    never read as months ('ms' is not 'MS'), and the period of 'L' that the
    float division leaves one step short (3599999) is not a whole cycle.
    """
    assert arima_seasonal_period(frequency) is None


@pytest.mark.parametrize(
    "frequency",
    ["12MS", "4QS-OCT", "52W-SUN"],
    ids=lambda dt: f"frequency: {dt}",
)
def test_arima_seasonal_period_output_None_when_whole_cycle_of_one_step(frequency):
    """
    Test that arima_seasonal_period returns None when the cycle is a whole
    number of steps but a single one (12 months, 4 quarters or 52 weeks in
    a year): `m=1` is no seasonality, and is not written.
    """
    assert arima_seasonal_period(frequency) is None
