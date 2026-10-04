# Unit test unused_columns_note

import pytest

from skforecast_ai.profiling.data_profile import unused_columns_note


@pytest.mark.parametrize(
    "unused_columns, expected",
    [
        (
            ["a"],
            "Columns of the data that the profile leaves out are not used: ['a'].",
        ),
        (
            ["a", "b", "c", "d", "e", "f", "g"],
            "Columns of the data that the profile leaves out are not used: "
            "['a', 'b', 'c', 'd', 'e'] (first 5 of 7).",
        ),
    ],
    ids=["one", "more than five"],
)
def test_unused_columns_note_output(unused_columns, expected):
    """
    Test that the note names the columns left out, the first 5 of them and
    how many there are when there are more.
    """
    assert unused_columns_note(unused_columns) == expected
