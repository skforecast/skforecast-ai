# Unit test _without_column

import pytest

from skforecast_ai.profiling.csv_dialect import _without_column

_ROWS = [
    ["store", "date", "y"],
    ["1.001", "2020-01-01", "870"],
    ["1.002", "2020-01-02", "1.020"],
]


@pytest.mark.parametrize(
    "name, expected",
    [
        (
            "store",
            [["date", "y"], ["2020-01-01", "870"], ["2020-01-02", "1.020"]],
        ),
        (
            "date",
            [["store", "y"], ["1.001", "870"], ["1.002", "1.020"]],
        ),
        (
            "y",
            [["store", "date"], ["1.001", "2020-01-01"], ["1.002", "2020-01-02"]],
        ),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test__without_column_output(name, expected):
    """
    Test that the fields of the column named in the header are left out of
    every record, header included, and the other fields keep their order.
    """
    assert _without_column(_ROWS, name) == expected


def test__without_column_output_when_name_is_repeated_in_the_header():
    """
    Test that every column with that name in the header is left out.
    """
    rows = [["id", "y", "id"], ["a", "1", "b"], ["c", "2", "d"]]

    assert _without_column(rows, "id") == [["y"], ["1"], ["2"]]


@pytest.mark.parametrize("name", ["other", "STORE"], ids=lambda dt: f"{dt!r}")
def test__without_column_returns_same_object_when_name_not_in_header(name):
    """
    Test that the records are returned as the same object when no header field
    has that name (the match is exact).
    """
    assert _without_column(_ROWS, name) is _ROWS


def test__without_column_does_not_modify_input():
    """
    Test that the records given are not modified.
    """
    rows = [list(row) for row in _ROWS]

    _without_column(rows, "store")

    assert rows == _ROWS
