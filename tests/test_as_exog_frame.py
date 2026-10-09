# Unit test as_exog_frame

import re
from pathlib import Path

import pandas as pd
import pytest

from skforecast_ai._future_exog import as_exog_frame
from skforecast_ai.exceptions import InvalidInputTypeError


def test_as_exog_frame_InvalidInputTypeError_when_unnamed_series():
    """
    Test that a pandas Series without a name raises: it cannot be matched
    with an exogenous column of the data.
    """
    err_msg = re.escape(
        "`exog` is a pandas Series without a name: give it the name of the "
        "exogenous variable, or pass a pandas DataFrame."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        as_exog_frame(pd.Series([1.0, 2.0]))

    assert exc_info.value.field == "exog"


@pytest.mark.parametrize(
    "exog, name",
    [
        ("exog.csv", "str"),
        # PosixPath, or WindowsPath on Windows.
        (Path("exog.csv"), type(Path()).__name__),
        ({"x": 1}, "dict"),
    ],
    ids=["str", "path", "dict"],
)
def test_as_exog_frame_InvalidInputTypeError_when_not_dataframe(exog, name):
    """
    Test that a path or another type raises with the type it got, instead of
    failing later with `AttributeError` (a path) or a message about the
    number of rows (the length of a str).
    """
    err_msg = re.escape(
        f"`exog` must be a pandas DataFrame with the future values of the "
        f"exogenous variables, not {name}. Read a CSV file with "
        f"pandas.read_csv first (the CLI reads it with --exog)."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg):
        as_exog_frame(exog)


def test_as_exog_frame_output():
    """
    Test that a named pandas Series becomes a DataFrame with one column of
    that name, and that a DataFrame and None are returned as they are.
    """
    index = pd.date_range("2023-01-01", periods=2)
    frame = pd.DataFrame({"x": [1.0, 2.0]}, index=index)

    pd.testing.assert_frame_equal(
        as_exog_frame(pd.Series([1.0, 2.0], index=index, name="x")), frame
    )
    assert as_exog_frame(frame) is frame
    assert as_exog_frame(None) is None
