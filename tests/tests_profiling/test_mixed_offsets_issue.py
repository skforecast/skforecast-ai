# Unit test _mixed_offsets_issue

import pandas as pd

from skforecast_ai.profiling.data_profile import _mixed_offsets_issue


def test_mixed_offsets_issue_output_when_timestamps_of_several_offsets():
    """
    Test that parsed dates of several UTC offsets (an object column of
    Timestamps, as pandas returns them) name the offsets.
    """
    parsed = pd.Series(
        [
            pd.Timestamp("2020-03-28 01:00:00+01:00"),
            pd.Timestamp("2020-03-29 03:00:00+02:00"),
            pd.Timestamp("2020-03-29 04:00:00+02:00"),
        ],
        dtype=object,
    )

    summary, _ = _mixed_offsets_issue("date", parsed)

    assert summary == "The dates of column 'date' mix time zones (+01:00, +02:00)"


def test_mixed_offsets_issue_output_when_one_time_zone():
    """
    Test that dates of one time zone, or without one, have no issue.
    """
    one_zone = pd.Series(
        pd.date_range("2020-01-01", periods=3, freq="h", tz="UTC+01:00")
    )
    naive = pd.Series(pd.date_range("2020-01-01", periods=3, freq="h"))

    assert _mixed_offsets_issue("date", one_zone) is None
    assert _mixed_offsets_issue("date", naive) is None
