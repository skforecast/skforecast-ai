# Unit test _forecast_dates

import pandas as pd
import pytest

from skforecast_ai._future_exog import _forecast_dates

from tests.fixtures_future_exog import profile_dst


@pytest.mark.parametrize(
    "index, frequency, expected",
    [
        (
            pd.date_range(end="2021-03-28", periods=60, freq="D"),
            "D",
            ["2021-03-29 00:00:00", "2021-03-30 00:00:00", "2021-03-31 00:00:00"],
        ),
        (
            pd.date_range(end="2021-02-01", periods=24, freq="MS"),
            "MS",
            ["2021-03-01 00:00:00", "2021-04-01 00:00:00", "2021-05-01 00:00:00"],
        ),
        (
            pd.date_range(end="2021-03-28", periods=60, freq="D", tz="Europe/Madrid"),
            "D",
            [
                "2021-03-29 00:00:00+02:00",
                "2021-03-30 00:00:00+02:00",
                "2021-03-31 00:00:00+02:00",
            ],
        ),
        (
            pd.date_range(end="2021-03-26", periods=60, freq="D", tz="Europe/Madrid"),
            "D",
            [
                "2021-03-27 00:00:00+01:00",
                "2021-03-28 00:00:00+01:00",
                "2021-03-29 00:00:00+02:00",
            ],
        ),
        (
            pd.date_range(end="2021-03-26", periods=60, freq="D", tz="UTC")
            .tz_convert("Europe/Madrid"),
            "D",
            [
                "2021-03-27 01:00:00+01:00",
                "2021-03-28 01:00:00+01:00",
                "2021-03-29 02:00:00+02:00",
            ],
        ),
        (
            pd.date_range(
                end="2021-03-28 00:00", periods=48, freq="h", tz="Europe/Madrid"
            ),
            "h",
            [
                "2021-03-28 01:00:00+01:00",
                "2021-03-28 03:00:00+02:00",
                "2021-03-28 04:00:00+02:00",
            ],
        ),
    ],
    ids=[
        "days", "month starts", "local days after the day of the change",
        "local days across the change", "days of UTC across the change",
        "hours across the change",
    ],
)
def test_forecast_dates_output(index, frequency, expected):
    """
    Test that the dates to forecast are those skforecast builds, with
    pandas 2 and with pandas 3: the steps of the frequency after the last
    date and, through a daylight saving time change, the same time of day,
    local (midnight after the day of the change, which lasts 23 hours, not
    24 hours later) or that of UTC for dates at midnight in UTC, while
    hours follow one another.
    """
    profile = profile_dst.model_copy(update={"frequency": frequency})

    result = _forecast_dates(index[0], index[-1], 3, profile)

    assert [str(date) for date in result] == expected
