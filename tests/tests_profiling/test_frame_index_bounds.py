# Unit test _frame_index_bounds

import pandas as pd

from skforecast_ai.profiling.data_profile import _frame_index_bounds


def test_frame_index_bounds_output_when_date_column():
    """
    Test that the bounds come from the date column when one is given.
    """
    frame = pd.DataFrame({"date": ["2023-01-03", "2023-01-01", "2023-01-02"], "y": [1, 2, 3]})

    start, end = _frame_index_bounds(frame, "date", datetime_available=True)

    assert start == pd.Timestamp("2023-01-01")
    assert end == pd.Timestamp("2023-01-03")


def test_frame_index_bounds_output_when_datetime_index():
    """
    Test that the bounds come from the index when no date column is
    given and the index is a DatetimeIndex.
    """
    frame = pd.DataFrame({"y": [1, 2, 3]}, index=pd.date_range("2023-01-01", periods=3))

    assert _frame_index_bounds(frame, None, datetime_available=True) == (
        pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-03")
    )


def test_frame_index_bounds_output_when_no_datetime_source():
    """
    Test that no bounds are reported when there is no datetime source,
    whether declared unavailable or simply absent from the frame.
    """
    frame = pd.DataFrame({"y": [1, 2, 3]})

    assert _frame_index_bounds(frame, None, datetime_available=False) == (None, None)
    assert _frame_index_bounds(frame, None, datetime_available=True) == (None, None)
