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
