# Unit test _reading_frequency

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _reading_frequency

# Monthly dates on the first of each month. Read in the wrong order, they are
# the first twelve days of January of every year: five years (60 rows) and 18
# months with three missing fill a few hundredths of the daily grid, and one
# year with a missing month fills almost all of it.
_MONTHS = pd.date_range("2015-01-01", periods=60, freq="MS")
_MONTHS_WITH_GAPS = pd.date_range("2015-01-01", periods=18, freq="MS").delete(
    [4, 9, 14]
)
_YEAR_WITH_GAP = pd.date_range("2015-01-01", periods=12, freq="MS").delete([5])


@pytest.mark.parametrize(
    "dates, written, expected",
    [
        (_MONTHS, "%d/%m/%Y", {"%d/%m/%Y": "MS", "%m/%d/%Y": None}),
        (_MONTHS, "%m/%d/%Y", {"%d/%m/%Y": None, "%m/%d/%Y": "MS"}),
        (_MONTHS_WITH_GAPS, "%d/%m/%Y", {"%d/%m/%Y": "MS", "%m/%d/%Y": None}),
        (_MONTHS_WITH_GAPS, "%m/%d/%Y", {"%d/%m/%Y": None, "%m/%d/%Y": "MS"}),
        (_YEAR_WITH_GAP, "%d/%m/%Y", {"%d/%m/%Y": "MS", "%m/%d/%Y": "D"}),
        (_YEAR_WITH_GAP, "%m/%d/%Y", {"%d/%m/%Y": "D", "%m/%d/%Y": "MS"}),
    ],
    ids=[
        "spanish 60 months", "us 60 months", "spanish months with gaps",
        "us months with gaps", "spanish year with a gap", "us year with a gap",
    ],
)
def test_reading_frequency_output_when_monthly_dates_read_in_both_orders(
    dates, written, expected
):
    """
    Test the frequency of monthly dates read day first and month first:
    five years of a Spanish file are 'MS' day first and have no frequency
    month first (January 1st to 12th of every year), and those of a US file
    the other way. Months with gaps, which leave no ten months in a row,
    are 'MS' in their order and still have no frequency in the other one,
    whose daily grid is mostly empty. A year with a missing month is
    regular in both readings, so its order stays unknown.
    """
    values = pd.Series(dates.strftime(written))

    result = {
        date_format: _reading_frequency(values, date_format)
        for date_format in ("%d/%m/%Y", "%m/%d/%Y")
    }

    assert result == expected
