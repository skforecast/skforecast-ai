# Unit test _resolve_start_date

import pandas as pd

from skforecast_ai.profiling.data_profile import _resolve_start_date

_dates_a = pd.date_range("2023-01-01", periods=3, freq="D")
_dates_b = pd.date_range("2023-01-05", periods=3, freq="D")


def test_resolve_start_date_output_when_long_format_with_date_column():
    """
    Test that the latest first date across series is used in long format,
    so position-based splits are valid for every series.
    """
    data = pd.DataFrame({
        "series_id": ["a"] * 3 + ["b"] * 3,
        "date": list(_dates_a) + list(_dates_b),
        "value": range(6),
    })

    assert _resolve_start_date(data, _dates_a, "long", "series_id", "date") == pd.Timestamp("2023-01-05")


def test_resolve_start_date_output_when_long_format_with_datetime_index():
    """
    Test that the latest first date is found through the index when the
    dates are not a column.
    """
    data = pd.DataFrame(
        {"series_id": ["a"] * 3 + ["b"] * 3, "value": range(6)},
        index=_dates_a.append(_dates_b),
    )

    assert _resolve_start_date(data, _dates_a, "long", "series_id", None) == pd.Timestamp("2023-01-05")


def test_resolve_start_date_output_when_series_id_column_missing():
    """
    Test that the first element of the representative index is used when
    the series identifier column is not in the frame.
    """
    data = pd.DataFrame({"value": range(3)}, index=_dates_a)

    assert _resolve_start_date(data, _dates_a, "long", "series_id", None) == pd.Timestamp("2023-01-01")
