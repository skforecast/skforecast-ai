# Unit test fixed_step_nanos

import pandas as pd
import pytest

from skforecast_ai._dates import fixed_step_nanos


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("30min", 1_800_000_000_000),
        ("h", 3_600_000_000_000),
        ("D", 86_400_000_000_000),
        ("2D", 172_800_000_000_000),
    ],
    ids=lambda value: f"{value}",
)
def test_fixed_step_nanos_output_when_fixed_step(frequency, expected):
    """
    Test that a fixed step gives its length in nanoseconds, days included:
    pandas 3 no longer makes `Day` a `Tick`, and a day still lasts 24 hours.
    """
    offset = pd.tseries.frequencies.to_offset(frequency)

    assert fixed_step_nanos(offset) == expected


@pytest.mark.parametrize(
    "frequency",
    ["W", "W-MON", "B", "bh", "MS", "QE"],
    ids=lambda frequency: f"{frequency}",
)
def test_fixed_step_nanos_output_is_None_when_calendar_step(frequency):
    """
    Test that a calendar step (weeks, business days and hours, months,
    quarters) has no fixed length.
    """
    offset = pd.tseries.frequencies.to_offset(frequency)

    assert fixed_step_nanos(offset) is None
