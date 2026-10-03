# Unit test training_end

import pandas as pd
import pytest

from skforecast_ai._dates import training_end


@pytest.mark.parametrize(
    "end_train, tz, expected",
    [
        ("2023-02-26", None, pd.Timestamp("2023-02-26")),
        ("2023-02-26", "UTC", pd.Timestamp("2023-02-26", tz="UTC")),
        (
            "2023-02-26",
            "Europe/Madrid",
            pd.Timestamp("2023-02-26", tz="Europe/Madrid"),
        ),
        (
            "2023-02-26 10:00:00",
            "UTC",
            pd.Timestamp("2023-02-26 10:00:00", tz="UTC"),
        ),
    ],
    ids=["no_tz", "utc", "madrid", "with_time"],
)
def test_training_end_output_when_date_without_time_zone(end_train, tz, expected):
    """
    Test that `end_train`, written without a time zone, is returned as a
    naive timestamp for dates without one, and localized to the time zone of
    the dates otherwise.
    """
    result = training_end(end_train, tz)

    assert result == expected
    assert result.tz == expected.tz


def test_training_end_output_when_date_already_has_time_zone():
    """
    Test that an `end_train` that already has a time zone is returned
    unchanged, whatever the time zone of the dates, and without a time zone
    of the dates.
    """
    end_train = "2023-02-26 00:00:00+01:00"

    for tz in (None, "UTC", "Europe/Madrid"):
        result = training_end(end_train, tz)

        assert result == pd.Timestamp("2023-02-26 00:00:00+01:00")
        assert str(result) == "2023-02-26 00:00:00+01:00"
