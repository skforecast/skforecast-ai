# Unit test is_text

import pandas as pd
import pytest

from skforecast_ai._dates import is_text


@pytest.mark.parametrize(
    "values, expected",
    [
        (pd.Series(["2023-01-01", "2023-01-02"], dtype=object), True),
        (pd.Series(["2023-01-01", "2023-01-02"], dtype="string"), True),
        (pd.Series([pd.Timestamp("2023-01-01")], dtype=object), True),
        (pd.Index(["a", "b"]), True),
        (pd.Series(pd.to_datetime(["2023-01-01", "2023-01-02"])), False),
        (pd.Series([1.0, 2.0]), False),
    ],
    ids=["object", "string", "object_of_timestamps", "index", "datetime64", "float"],
)
def test_is_text_output(values, expected):
    """
    Test that object and string columns (and indexes) hold text, as the
    loader reads them, and datetime64 and numeric columns do not.
    """
    assert is_text(values) is expected
