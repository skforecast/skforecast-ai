# Unit test missing_dates

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._dates import missing_dates


@pytest.mark.parametrize(
    "values, expected",
    [
        (
            pd.Series(["2023-01-01", None, np.nan, "2023-01-04"], dtype=object),
            [False, True, True, False],
        ),
        (
            pd.Series(["2023-01-01", "", "  ", "\t"], dtype=object),
            [False, True, True, True],
        ),
        (
            pd.Series(["2023-01-01", "NaT", "nat", "nan"], dtype=object),
            [False, True, True, True],
        ),
        (
            pd.Series(["2023-01-01", pd.NA, " "], dtype="string"),
            [False, True, True],
        ),
        (
            pd.Series(pd.to_datetime(["2023-01-01", None])),
            [False, True],
        ),
        (
            pd.Series(["2023-01-01", "-", "?", "None"], dtype=object),
            [False, False, False, False],
        ),
    ],
    ids=["nulls", "blanks", "nat_text", "string_dtype", "datetime64", "not_empty"],
)
def test_missing_dates_output(values, expected):
    """
    Test that missing values, text made only of blanks and the text pandas
    parses as a missing date ('NaT', 'nan') hold no date, and that any
    other text does.
    """
    np.testing.assert_array_equal(missing_dates(values), expected)
