# Unit test _format_split_ts

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _format_split_ts


@pytest.mark.parametrize(
    "ts, expected",
    [
        (pd.Timestamp("2023-03-01"), "2023-03-01"),
        (pd.Timestamp("2023-03-01 23:00:00"), "2023-03-01 23:00:00"),
    ],
    ids=["midnight: date only", "with time: full timestamp"],
)
def test_format_split_ts_output(ts, expected):
    """
    Test that a midnight boundary is rendered as a date and any other
    boundary as a full timestamp.
    """
    assert _format_split_ts(ts) == expected
