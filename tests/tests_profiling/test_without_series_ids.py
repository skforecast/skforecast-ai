# Unit test without_series_ids

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import without_series_ids

_DATA = pd.DataFrame(
    {
        "id": ["001", "1", "10"],
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "y": [1.5, 2.5, 3.5],
    }
)


def test_without_series_ids_output():
    """
    Test that the column of series ids is left out and the other columns keep
    their order, and that the data given is not modified.
    """
    data = _DATA.copy()

    result = without_series_ids(data, "id")

    expected = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "y": [1.5, 2.5, 3.5],
        }
    )
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(data, _DATA)


@pytest.mark.parametrize(
    "series_id_column",
    [None, "store"],
    ids=lambda dt: f"series_id_column: {dt}",
)
def test_without_series_ids_returns_same_object_when_no_series_id_column(
    series_id_column,
):
    """
    Test that the data is returned as the same object when `series_id_column`
    is None or a column that the data does not hold.
    """
    result = without_series_ids(_DATA, series_id_column)

    assert result is _DATA
