# Unit test check_csv_fields

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import check_csv_fields

# A header one field short, as pandas reads it: the first field of every row
# is the index.
_HEADER_ONE_SHORT = pd.DataFrame(
    {"temp": [1.0, 2.0]}, index=pd.Index(["2023-01-01", "2023-01-02"])
)

# A separator at the end of every row, as pandas reads it: the last column
# is empty.
_SEPARATOR_AT_ROW_END = pd.DataFrame(
    {"date": [1, 2], "temp": [None, None]},
    index=pd.Index(["2023-01-01", "2023-01-02"]),
)


def test_check_csv_fields_passes_when_rows_fit_the_header():
    """
    Test that a frame read with a RangeIndex and named columns passes, also
    with a column without name that holds values.
    """
    data = pd.DataFrame({"Unnamed: 0": ["a", None], "y": [1.0, None]})

    assert check_csv_fields(data, "data.csv") is None


@pytest.mark.parametrize(
    "data",
    [
        _HEADER_ONE_SHORT,
        _SEPARATOR_AT_ROW_END,
        pd.DataFrame(
            {"temp": [1.0]},
            index=pd.MultiIndex.from_tuples([("2023-01-01", "a")]),
        ),
    ],
    ids=["header one field short", "separator at row end", "two fields more"],
)
def test_check_csv_fields_InvalidInputError_when_first_row_longer_than_header(data):
    """
    Test that a frame read with the first columns as the index raises with
    the code 'data_unreadable' and the field given.
    """
    with pytest.raises(InvalidInputError) as exc_info:
        check_csv_fields(data, "data.csv", field="exog")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"


@pytest.mark.parametrize(
    "row_lengths", [None, [2, 2]], ids=["lengths unknown", "every row one longer"]
)
def test_check_csv_fields_passes_when_index_first_and_header_one_field_short(
    row_lengths,
):
    """
    Test that, with `index_first`, a header one field short passes when every
    row has one field more than the header, or when the lengths are unknown.
    """
    assert check_csv_fields(
        _HEADER_ONE_SHORT, "exog.csv", index_first=True, row_lengths=row_lengths
    ) is None


@pytest.mark.parametrize(
    "data, row_lengths",
    [
        (_HEADER_ONE_SHORT, [2, 1]),
        (_HEADER_ONE_SHORT, [2, 3]),
        (_SEPARATOR_AT_ROW_END, None),
        (_SEPARATOR_AT_ROW_END, [3, 3]),
    ],
    ids=["field too many in the first row", "two fields more in a row",
         "separator at row end", "separator at row end with lengths"],
)
def test_check_csv_fields_InvalidInputError_when_index_first_and_rows_differ(
    data, row_lengths
):
    """
    Test that, with `index_first`, rows that do not all have one field more
    than the header, or an empty last column (a separator at the end of every
    row), still raise.
    """
    with pytest.raises(InvalidInputError) as exc_info:
        check_csv_fields(data, "exog.csv", index_first=True, row_lengths=row_lengths)

    assert exc_info.value.code == "data_unreadable"


def test_check_csv_fields_InvalidInputError_when_column_without_name_and_values():
    """
    Test that a column named by pandas after its position, without values,
    raises naming it, while a column with that name elsewhere does not.
    """
    data = pd.DataFrame({"Unnamed: 1": [None, None], "y": [1, 2]})
    check_csv_fields(data, "data.csv")

    data = pd.DataFrame({"y": [1, 2], "Unnamed: 1": [None, None]})
    with pytest.raises(InvalidInputError, match="column 'Unnamed: 1' has no name"):
        check_csv_fields(data, "data.csv")
