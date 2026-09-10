# Unit test _array_stats

import numpy as np

from skforecast_ai.profiling.data_profile import _array_stats


def test_array_stats_output_when_all_nan():
    """
    Test that an array without valid values yields no statistics.
    """
    assert _array_stats(np.array([np.nan, np.nan])) is None


def test_array_stats_output_when_single_value():
    """
    Test that a single valid value has zero standard deviation instead of
    the undefined sample deviation.
    """
    assert _array_stats(np.array([np.nan, 5.0])) == {
        "min": 5.0, "max": 5.0, "mean": 5.0, "std": 0.0
    }
