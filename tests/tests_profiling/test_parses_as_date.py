# Unit test _parses_as_date

import warnings

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _parses_as_date


@pytest.mark.parametrize(
    "values, expected",
    [
        (["2023-01-01", "2023-01-02"], True),
        (["2012-03-25T01:00:00+01:00", "2012-03-25T03:00:00+02:00"], True),
        (["2012-03-20 00:00:00 CET", "2012-03-28 09:00:00 CEST"], True),
        ([pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2023-01-02")], True),
        (["2023-01-01", "b"], False),
        ([1, 2], False),
        (["Jan", "Feb"], False),
    ],
    ids=[
        "dates", "mixed_offsets", "zone_names", "timestamps", "text",
        "numbers", "month_names",
    ],
)
def test_parses_as_date_output(values, expected):
    """
    Test that text and datetime objects that are all dates parse, also with
    mixed or unrecognized time zones, and without any pandas warning, while
    numbers do not count as dates.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = _parses_as_date(pd.Series(values, dtype=object))

    assert result is expected
