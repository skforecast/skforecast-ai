# Unit test cp1252_note

import pytest

from skforecast_ai.profiling.csv_dialect import cp1252_note


@pytest.mark.parametrize(
    "field, remedy",
    [("data", "profile it again"), ("exog", "pass it again")],
    ids=["data", "exog"],
)
def test_cp1252_note_output(field, remedy):
    """
    Test that the note says the file was read as cp1252, which the script
    repeats and which cannot be checked, and how to fix wrong characters:
    the data file is profiled again, the future values are passed again.
    """
    expected = (
        f"The CSV file is not UTF-8: it was read as cp1252 (Windows-1252), the "
        f"encoding of the CSV files that Excel saves on Windows, and the "
        f"generated script reads it so. That encoding cannot be checked: if "
        f"column names or categories show wrong characters, save the file as "
        f"UTF-8 and {remedy}."
    )

    assert cp1252_note(field) == expected


def test_cp1252_note_output_is_for_the_data_by_default():
    """
    Test that the note is the one of the data when no field is given.
    """
    assert cp1252_note() == cp1252_note("data")
