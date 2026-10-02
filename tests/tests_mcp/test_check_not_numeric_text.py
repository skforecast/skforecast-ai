# Unit test check_not_numeric_text

import re
import pytest

from skforecast_ai.mcp._errors import ServerError
from skforecast_ai.mcp._inputs import check_not_numeric_text


@pytest.mark.parametrize(
    "value",
    ["12", " 12 ", "+3", "-1", ".5", "1.", "1e5", "2.5E-3", "2012"],
    ids=lambda dt: f"value: {dt!r}"
)
def test_check_not_numeric_text_ServerError_when_number_written_as_text(value):
    """
    Test that a number written as text is `invalid_argument`, since the core
    would read it as a date.
    """
    err_msg = re.escape(
        f"`test_size` is the text {value!r}: pass a number (without quotes) for "
        f"a count of observations, or an ISO 8601 date such as '2012-01-01' for "
        f"a date."
    )
    with pytest.raises(ServerError, match=err_msg) as excinfo:
        check_not_numeric_text(value, "test_size")

    assert (excinfo.value.code, excinfo.value.field) == ("invalid_argument", "test_size")


@pytest.mark.parametrize(
    "value",
    [12, 0.2, None, "2012-01-01", "2012-01", "1e", "12 months", ""],
    ids=lambda dt: f"value: {dt!r}"
)
def test_check_not_numeric_text_accepts_numbers_and_dates(value):
    """
    Test that numbers, None and text that is not a number pass.
    """
    assert check_not_numeric_text(value, "test_size") is None
