# Unit test series_ids_as_text

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import series_ids_as_text

_DATES = pd.date_range("2020-01-01", periods=4, freq="D")


def _long_data(ids) -> pd.DataFrame:
    """
    Long-format data of four rows whose series ids are `ids`.
    """
    return pd.DataFrame(
        {"date": _DATES, "id": ids, "y": [1.0, 2.0, 3.0, 4.0]}
    )


@pytest.mark.parametrize(
    "ids, expected_ids",
    [
        (
            pd.Series([1, 2, 10, 1]),
            pd.Series(["1", "2", "10", "1"], dtype=object),
        ),
        (
            pd.Series([1, 2, 10, 1], dtype="int32"),
            pd.Series(["1", "2", "10", "1"], dtype=object),
        ),
        (
            pd.Series(["001", 1, 10, "a"], dtype=object),
            pd.Series(["001", "1", "10", "a"], dtype=object),
        ),
        (
            pd.Series([1.0, np.nan, 2.0, 10.0]),
            pd.Series(["1.0", np.nan, "2.0", "10.0"], dtype=object),
        ),
        (
            pd.Series(["a", None, 1, 1], dtype=object),
            pd.Series(["a", None, "1", "1"], dtype=object),
        ),
    ],
    ids=["integers", "int32", "mixed text and integers", "floats with NaN",
         "object with a missing id"],
)
def test_series_ids_as_text_output(ids, expected_ids):
    """
    Test that ids that are not text become text (`1` is `'1'`, `1.0` is
    `'1.0'`), that text ids in a column of mixed values are kept as they are,
    that a missing id stays missing, and that the other columns are not
    touched.
    """
    data = _long_data(ids)

    result = series_ids_as_text(data, "id")

    expected = _long_data(expected_ids)
    pd.testing.assert_frame_equal(result, expected)


def test_series_ids_as_text_output_when_ids_are_categorical():
    """
    Test that a categorical column of integer ids becomes a categorical
    column of text, with the categories in the same order.
    """
    data = _long_data(pd.Categorical([1, 2, 10, 1]))

    result = series_ids_as_text(data, "id")

    expected = _long_data(
        pd.Categorical(["1", "2", "10", "1"], categories=["1", "2", "10"])
    )
    pd.testing.assert_frame_equal(result, expected)


def test_series_ids_as_text_does_not_modify_input():
    """
    Test that the data given is not modified: the ids are converted in a
    copy.
    """
    data = _long_data([1, 2, 10, 1])
    data_copy = data.copy()

    result = series_ids_as_text(data, "id")

    pd.testing.assert_frame_equal(data, data_copy)
    assert result is not data


@pytest.mark.parametrize(
    "ids",
    [
        pd.Series(["001", "1", "10", "1"], dtype=object),
        pd.Series(["a", None, "b", "a"], dtype=object),
        pd.Series(["a", None, "b", "a"], dtype="string"),
        pd.Series([None, None, None, None], dtype=object),
    ],
    ids=["text", "text with a missing id", "string dtype", "all missing"],
)
def test_series_ids_as_text_returns_same_object_when_ids_are_text(ids):
    """
    Test that data whose ids are already text, or all missing, is returned
    as the same object, without a copy.
    """
    data = _long_data(ids)

    result = series_ids_as_text(data, "id")

    assert result is data


@pytest.mark.parametrize(
    "series_id_column",
    [None, "store"],
    ids=lambda dt: f"series_id_column: {dt}",
)
def test_series_ids_as_text_returns_same_object_when_no_series_id_column(
    series_id_column,
):
    """
    Test that data is returned as the same object when `series_id_column` is
    None, and when it is a column that the data does not hold, even if the
    data has integer columns.
    """
    data = _long_data([1, 2, 10, 1])

    result = series_ids_as_text(data, series_id_column)

    assert result is data


def test_series_ids_as_text_returns_same_object_when_column_name_is_repeated():
    """
    Test that data with two columns named like the series id column is
    returned as the same object, left to the checks that report it.
    """
    data = pd.DataFrame([[1, 2, 3.0]], columns=["id", "id", "y"])

    result = series_ids_as_text(data, "id")

    assert result is data
