# Unit test _is_datetime_like

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _is_datetime_like


@pytest.mark.parametrize(
    "values, expected",
    [
        (pd.Series(pd.date_range("2023-01-01", periods=3)), True),
        (pd.Series(["2023-01-01", "2023-01-02", "2023-01-03"]), True),
        (pd.Series([1.0, 2.0, 3.0]), False),
        (pd.Series(["2023-01-01", "not a date", "2023-01-03"]), False),
    ],
    ids=["datetime dtype", "parseable strings", "numeric", "unparseable strings"],
)
def test_is_datetime_like_output(values, expected):
    """
    Test that datetime dtypes and fully parseable strings are datetime
    like, while numeric values and partially parseable strings are not.
    """
    assert _is_datetime_like(values) is expected
