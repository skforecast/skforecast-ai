# Unit test first_row_longer_than_header

import pytest

from skforecast_ai.profiling.csv_dialect import first_row_longer_than_header


@pytest.mark.parametrize(
    "text, sep, expected",
    [
        ("y,z\n60,1.5,10\n61,2.5,20\n", ",", True),
        ("y;z\n60;1,5;10\n", ";", True),
        ("y,z\n\n60,1.5,10\n", ",", True),
        ("t,y,z\n60,1.5,10\n61,2.5,20\n", ",", False),
        ('y,z\n"1,5",10\n', ",", False),
        ("y,z\n", ",", False),
        ("", ",", False),
    ],
    ids=["one field more", "semicolon", "blank line first", "same fields",
         "quoted separator", "header only", "empty"],
)
def test_first_row_longer_than_header_output(text, sep, expected):
    """
    Test that a first row with more fields than the header is told, as
    pandas splits the fields: blank lines are left out, a separator between
    quotes splits nothing, and text without a row after the header has no
    longer row.
    """
    assert first_row_longer_than_header(text, sep) is expected


def test_first_row_longer_than_header_output_is_False_when_row_cannot_be_split():
    """
    Test that a first row that the `csv` module cannot split (a field over
    its size limit) is not a longer row: the file is left to the checks
    that read it whole.
    """
    text = "y,z\n" + "1" * 140_000 + ",2,3\n"

    assert first_row_longer_than_header(text, ",") is False
