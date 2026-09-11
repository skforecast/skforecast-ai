# Unit test _position_to_date recommendation/backtesting

import pytest

from skforecast_ai.recommendation.backtesting import _position_to_date


@pytest.mark.parametrize(
    "start_date, frequency",
    [(None, "D"), ("2023-01-01", None), (None, None)],
    ids=lambda dt: f"{dt}",
)
def test_position_to_date_output_when_no_datetime_reference(start_date, frequency):
    """
    Test that the position is returned unchanged when there is no start
    date or no frequency to convert it with.
    """
    assert _position_to_date(10, start_date, frequency) == 10


@pytest.mark.parametrize(
    "frequency, expected",
    [("D", "2023-01-10"), ("h", "2023-01-01 09:00:00")],
    ids=["daily: date only", "hourly: full timestamp"],
)
def test_position_to_date_output_when_datetime_reference(frequency, expected):
    """
    Test that a position is converted to the date of that observation,
    rendered as a date when it falls on midnight and as a full timestamp
    otherwise.
    """
    assert _position_to_date(10, "2023-01-01", frequency) == expected


def test_position_to_date_output_when_frequency_is_invalid():
    """
    Test that an unparsable frequency falls back to the raw position
    instead of raising.
    """
    assert _position_to_date(10, "2023-01-01", "not-a-frequency") == 10
