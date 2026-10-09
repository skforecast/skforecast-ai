# Unit test _date_order

import numpy as np
import pandas as pd

from skforecast_ai.recommendation.autoregressive import _date_order

_dates = pd.date_range("2023-01-01", periods=3, freq="D")


def test_date_order_output_keeps_first_repeated_row_and_drops_missing_dates():
    """
    Test that the order reads the rows in date order, keeps the first row of
    a repeated timestamp and leaves out the rows without a date.
    """
    dates = pd.DatetimeIndex([_dates[2], _dates[0], pd.NaT, _dates[2], _dates[1]])
    values = pd.Series([3.0, 1.0, 9.0, 30.0, 2.0])

    order = _date_order(dates)

    np.testing.assert_array_equal(order, [1, 4, 0])
    np.testing.assert_array_equal(values.iloc[order].to_numpy(), [1.0, 2.0, 3.0])


def test_date_order_output_when_dates_in_order():
    """
    Test that dates already in order give the positions as they are.
    """
    np.testing.assert_array_equal(_date_order(_dates), [0, 1, 2])


def test_date_order_output_when_no_dates():
    """
    Test that data without dates has no order, so its rows are read as
    given.
    """
    assert _date_order(None) is None
