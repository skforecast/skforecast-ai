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
        ("2MS", 6),
        ("4ME", 3),
        ("2M", 6),
        ("2QS-OCT", 2),
        ("13W-SUN", 4),
        ("3h", 8),
        ("3H", 8),
        ("12h", 2),
        ("14h", 12),
        ("6min", 10),
        ("12min", 5),
        ("20min", 3),
    ],
    ids=lambda dt: f"frequency, expected: {dt}",
)
def test_arima_seasonal_period_output_when_whole_cycle_not_in_table(
    frequency, expected
):
    """
    Test that arima_seasonal_period returns the first period of
    estimate_seasonality for a frequency not in the table when it is a
    whole cycle of 2 to 12 steps (MAX_UNTABULATED_ARIMA_PERIOD): 2 months
    in a year, 13 weeks in a year of 52, 3 hours in a day, 14 hours in a
    week (12, the limit) and 6 minutes in an hour.
    """
    assert arima_seasonal_period(frequency) == expected


@pytest.mark.parametrize(
    "frequency",
    [
        "4W-SUN",
        "4W-WED",
        "4min",
        "3min",
        "90min",
        "60min",
        "2W-SUN",
        "2min",
        "45min",
        "5D",
        "10s",
        "s",
        "S",
        "us",
    ],
    ids=lambda dt: f"frequency: {dt}",
)
def test_arima_seasonal_period_output_None_when_whole_cycle_above_limit(frequency):
    """
    Test that arima_seasonal_period returns None for a frequency not in
    the table whose first period is a whole cycle of more than 12 steps
    (MAX_UNTABULATED_ARIMA_PERIOD), from 13 ('4W-SUN') to the 3600 of
    seconds, including the 24 of '60min' that the table gives to 'h': the
    seasonal search is too costly to run without being asked for.
    """
    assert arima_seasonal_period(frequency) is None


@pytest.mark.parametrize(
    "frequency, expected",
    [("h", 24), ("W-SUN", 52), ("30min", 48), ("5min", 288)],
    ids=lambda dt: f"frequency, expected: {dt}",
)
def test_arima_seasonal_period_output_when_tabulated_period_above_limit(
    frequency, expected
):
    """
    Test that the limit of 12 steps (MAX_UNTABULATED_ARIMA_PERIOD) does not
    apply to the frequencies of FREQUENCY_TO_SEASONAL_PERIOD: hourly,
    weekly and sub-hourly data keep their period of 24 or more.
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
