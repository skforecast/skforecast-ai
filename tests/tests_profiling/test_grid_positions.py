# Unit test _grid_positions

import numpy as np
import pandas as pd

from skforecast_ai.profiling.data_profile import _grid_positions

_GRID = pd.DatetimeIndex(["2023-01-02", "2023-01-03", "2023-01-04"]).asi8


def test_grid_positions_output():
    """
    Test the position of each date in the grid and whether it lies on it:
    a date on the grid, one between two timestamps and one after the end.
    """
    dates = pd.DatetimeIndex(["2023-01-03", "2023-01-03 12:00", "2023-01-05"])

    positions, on_grid = _grid_positions(dates.asi8, _GRID)

    np.testing.assert_array_equal(positions, np.array([1, 2, 3]))
    np.testing.assert_array_equal(on_grid, np.array([True, False, False]))


def test_grid_positions_output_when_grid_is_empty():
    """
    Test that no date lies on an empty grid (dates in the middle of a single
    month for a month-start frequency).
    """
    positions, on_grid = _grid_positions(
        pd.DatetimeIndex(["2023-01-03"]).asi8, _GRID[:0]
    )

    np.testing.assert_array_equal(positions, np.array([0]))
    np.testing.assert_array_equal(on_grid, np.array([False]))
