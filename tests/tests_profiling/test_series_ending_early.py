# Unit test _series_ending_early

import numpy as np
import pandas as pd

from skforecast_ai.profiling.data_profile import _series_ending_early


def test_series_ending_early_output():
    """
    Test that the series whose last value comes before the last date are
    returned with that date, named as given (an integer id as text), and
    that rows without a value at the end of a series, without a date or
    without a series id are left out: series 'c' ends on 2023-01-02 because
    its last row has no value, and the row of 2023-01-05 has no series id.
    """
    data = pd.DataFrame({
        "date": pd.to_datetime([
            "2023-01-01", "2023-01-04", "2023-01-01", "2023-01-02",
            "2023-01-01", "2023-01-02", "2023-01-04", None, "2023-01-05",
        ]),
        "id": ["a", "a", 7, 7, "c", "c", "c", "a", None],
        "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, np.nan, 8.0, 9.0],
    })

    result = _series_ending_early(
        pd.DatetimeIndex(data["date"]), data["id"], data["value"]
    )

    assert result == ("2023-01-04", {"7": "2023-01-02", "c": "2023-01-02"})


def test_series_ending_early_output_when_every_series_reaches_last_date():
    """
    Test that None is returned when every series has a value on the last
    date of the data, also with categorical ids (an unused category is
    not a series), and when no row has a value.
    """
    data = pd.DataFrame({
        "date": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-02"]),
        "id": pd.Categorical([1, 1, 2], categories=[1, 2, 3]),
        "value": [1.0, 2.0, 3.0],
    })

    dates = pd.DatetimeIndex(data["date"])

    assert _series_ending_early(dates, data["id"], data["value"]) is None
    assert _series_ending_early(dates, data["id"], data["value"] * np.nan) is None
