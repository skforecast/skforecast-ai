# Unit test weekday_names

import pytest

from skforecast_ai.profiling.data_profile import weekday_names


@pytest.mark.parametrize(
    "weekdays, expected",
    [
        ([6], "Sundays"),
        ([6, 5], "Saturdays and Sundays"),
        ([0, 2, 6], "Mondays, Wednesdays and Sundays"),
    ],
    ids=["one", "two", "three"],
)
def test_weekday_names_output(weekdays, expected):
    """
    Test weekday_names names days of the week in plural, from Monday, joined
    with commas and a final 'and'.
    """
    result = weekday_names(weekdays)
    assert result == expected
