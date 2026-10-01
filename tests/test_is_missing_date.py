# Unit test is_missing_date

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._dates import is_missing_date


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, True),
        (np.nan, True),
        (pd.NaT, True),
        (pd.NA, True),
        ("", True),
        ("   ", True),
        ("NaT", True),
        ("nan", True),
        ("2023-01-01", False),
        ("today", False),
        (pd.Timestamp("2023-01-01"), False),
        ([1, 2], False),
    ],
    ids=[
        "none", "nan", "nat", "na", "empty_text", "blank_text", "nat_text",
        "nan_text", "date_text", "today", "timestamp", "list",
    ],
)
def test_is_missing_date_output(value, expected):
    """
    Test that one value holds no date when it is missing, made only of
    blanks or reads 'NaT' or 'nan', and holds one otherwise, also when it is
    not a scalar.
    """
    assert is_missing_date(value) is expected
