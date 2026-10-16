# Unit test thousands_after_sample

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import (
    DOTTED_VALUES_HINT,
    EXOG_DIALECT_HINT,
)
from skforecast_ai.profiling.data_profile import thousands_after_sample


@pytest.mark.parametrize(
    "values",
    [
        ["870", "1.705"],
        ["1.234.567", "5"],
        ["870", "1.705,11"],
        [" -1.705,11 ", "x"],
        ["+1.705", "x"],
        ["1.705", None],
        [None, "1.705"],
    ],
    ids=[
        "one group",
        "two groups",
        "with decimals",
        "sign and spaces",
        "plus sign",
        "missing value after",
        "missing value before",
    ],
)
def test_thousands_after_sample_output_point_when_text_column_has_dot_thousands(
    values,
):
    """
    Test that '.' is returned when a column read as text holds a number with
    '.' between thousands, with decimals after a ',' or none, with an
    optional sign and spaces around, and missing values are ignored.
    """
    frame = pd.DataFrame({"y": [1, 2], "x": values})

    result = thousands_after_sample(frame, "data.csv", "data")

    assert result == "."


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"y": [1, 2], "x": [1.5, 1705.0]}),
        pd.DataFrame({"y": [1, 2], "x": ["a.b", "x"]}),
        pd.DataFrame({"y": [1, 2], "x": ["0.5", "0.5"]}),
        pd.DataFrame({"y": [1, 2], "x": ["12.34", "7"]}),
        pd.DataFrame({"y": [1, 2], "x": ["1,234", "2,5"]}),
        pd.DataFrame({"y": [1, 2], "x": ["15.01.2020", "01.02.2020"]}),
        pd.DataFrame({"y": [1.0, np.nan], "x": [None, None]}),
        pd.DataFrame({"y": [1, 2]}),
    ],
    ids=[
        "numeric columns",
        "text without numbers",
        "point decimals",
        "two decimals",
        "numbers with commas",
        "dates",
        "missing values",
        "integers",
    ],
)
def test_thousands_after_sample_output_none_when_no_dot_thousands(frame):
    """
    Test that None is returned when no column read as text holds a number
    with '.' between thousands: numeric columns only, text without such
    numbers, numbers with decimals or with a ',' and dates.
    """
    result = thousands_after_sample(frame, "data.csv", "data")

    assert result is None


def test_thousands_after_sample_output_point_when_other_column_holds_dotted_text():
    """
    Test that text with a '.' that is not a number ('a.b') in another column
    does not raise next to numbers with '.' between thousands.
    """
    frame = pd.DataFrame(
        {"y": [1, 2], "name": ["a.b", "x"], "x": ["870", "1.705"]}
    )

    result = thousands_after_sample(frame, "data.csv", "data")

    assert result == "."


@pytest.mark.parametrize(
    "frame, thousands, other",
    [
        (
            pd.DataFrame({"x": ["1.705", "870"], "d": ["15.01.2020", "a"]}),
            "1.705",
            "15.01.2020",
        ),
        (
            pd.DataFrame({"x": ["870", "1.705"], "d": ["a", "0.5"]}),
            "1.705",
            "0.5",
        ),
        (
            pd.DataFrame({"x": ["1.705", "0.5"]}),
            "1.705",
            "0.5",
        ),
        (
            pd.DataFrame({"x": ["1.705", " 12.34 "]}),
            "1.705",
            "12.34",
        ),
        (
            pd.DataFrame({"d": ["15.01.2020", "b"], "x": ["1.705,11", "870"]}),
            "1.705,11",
            "15.01.2020",
        ),
        (
            pd.DataFrame({"x": ["1.234.567", "x"], "d": ["0.5", "12.34"]}),
            "1.234.567",
            "0.5",
        ),
    ],
    ids=[
        "date in another column",
        "decimals in another column",
        "same column",
        "two decimals and spaces",
        "date column first",
        "first of several",
    ],
)
@pytest.mark.parametrize(
    "field, hint",
    [("data", DOTTED_VALUES_HINT), ("exog", EXOG_DIALECT_HINT)],
    ids=lambda dt: f"{dt[:4]}",
)
def test_thousands_after_sample_InvalidInputError_when_dotted_values(
    frame, thousands, other, field, hint
):
    """
    Test that a column read as text that holds a value with a '.' that does
    not separate thousands ('15.01.2020', '0.5'), next to numbers with '.'
    between thousands in the same or in another column, raises an
    InvalidInputError (a CsvDialectError) with the code 'data_unreadable',
    an example of each, the argument that named the file and its hint.
    """
    err_msg = re.escape(
        f"The CSV file 'data.csv' cannot be read: it holds numbers with '.' "
        f"between the thousands (such as {thousands!r}) and values with a '.' "
        f"that does not separate thousands (such as {other!r}), which pandas "
        f"would read as numbers without it."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        thousands_after_sample(frame, "data.csv", field)

    assert type(exc_info.value).__name__ == "CsvDialectError"
    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint
