# Unit test _extract_datetime_index

import pandas as pd

from skforecast_ai.profiling.data_profile import _extract_datetime_index

_dates = pd.date_range("2023-01-01", periods=3, freq="D")


def test_extract_datetime_index_output_when_long_format_with_datetime_index():
    """
    Test that in long format with the dates in the index the index of
    the first series is returned.
    """
    data = pd.DataFrame(
        {"series_id": ["a", "a", "a", "b", "b", "b"], "value": range(6)},
        index=_dates.append(_dates),
    )

    result = _extract_datetime_index(data, None, "datetime", "long", "series_id")

    assert result.equals(_dates)


def test_extract_datetime_index_output_when_date_column_missing():
    """
    Test that a resolved date column that is absent from the frame yields
    no datetime index rather than an error.
    """
    data = pd.DataFrame({"value": range(3)})

    assert _extract_datetime_index(data, "date", "datetime", "single", None) is None


def test_extract_datetime_index_output_when_index_type_is_not_datetime():
    """
    Test that a non-datetime index type yields None regardless of the
    frame contents.
    """
    data = pd.DataFrame({"value": range(3)}, index=_dates)

    assert _extract_datetime_index(data, None, "range", "single", None) is None
