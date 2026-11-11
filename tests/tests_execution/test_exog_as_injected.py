# Unit test exog_as_injected

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.execution.forecast_runner import exog_as_injected

from tests.fixtures_future_exog import (
    exog_long,
    profile_business,
    profile_daily,
    profile_long,
    profile_wide,
)

_DATES = pd.date_range("2023-04-11", periods=3, freq="D")


def test_exog_as_injected_output_when_data_has_date_column():
    """
    Test that, when the data has a date column, the index of the future
    exogenous variables becomes that column (whatever its name), as the
    generated code sets it as the index, and the input is not modified.
    """
    exog = pd.DataFrame(
        {"promo": [0.0, 1.0, 0.0]}, index=_DATES.rename("fecha")
    )

    result = exog_as_injected(exog, profile_daily)

    expected = pd.DataFrame({"date": _DATES, "promo": [0.0, 1.0, 0.0]})
    pd.testing.assert_frame_equal(result, expected)
    assert exog.index.name == "fecha"


def test_exog_as_injected_output_when_exog_has_date_column():
    """
    Test that future exogenous variables that already hold the date column
    of the data are returned as they are.
    """
    exog = pd.DataFrame({"date": _DATES, "promo": [0.0, 1.0, 0.0]})

    result = exog_as_injected(exog, profile_daily)

    assert result is exog


def test_exog_as_injected_output_when_data_has_no_date_column():
    """
    Test that, when the data is indexed by date (no date column), the future
    exogenous variables are returned as they are, indexed by date.
    """
    exog = pd.DataFrame({"x": [0.0, 1.0, 0.0]}, index=_DATES)

    result = exog_as_injected(exog, profile_business)

    assert result is exog


@pytest.mark.parametrize(
    "ids, expected_ids",
    [
        (np.repeat([1, 2, 10], 7), np.repeat(["1", "2", "10"], 7)),
        (np.repeat([1.0, 2.0, 10.0], 7), np.repeat(["1.0", "2.0", "10.0"], 7)),
        (
            np.repeat(np.array(["001", 1, 10], dtype=object), 7),
            np.repeat(["001", "1", "10"], 7),
        ),
    ],
    ids=["integers", "floats", "text and integers"],
)
def test_exog_as_injected_output_when_long_data_has_integer_series_ids(
    ids, expected_ids
):
    """
    Test that, for long-format data, the series ids of the future exogenous
    variables become text, as those of the data (a CSV file read with them as
    text, a DataFrame turned into text), and the input is not modified.
    """
    exog = exog_long.assign(series=ids)
    exog_copy = exog.copy()

    result = exog_as_injected(exog, profile_long)

    expected = exog_long.assign(series=pd.Series(expected_ids, dtype=object))
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(exog, exog_copy)


def test_exog_as_injected_output_when_long_data_and_exog_indexed_by_date():
    """
    Test that, for long-format data, future exogenous variables indexed by
    date get the date column back, and their integer series ids become text.
    """
    exog = exog_long.assign(series=np.repeat([1, 2, 10], 7))
    exog = exog.set_index("date").rename_axis("fecha")

    result = exog_as_injected(exog, profile_long)

    expected = exog_long.assign(series=np.repeat(["1", "2", "10"], 7))[
        ["date", "series", "price"]
    ]
    pd.testing.assert_frame_equal(result, expected)
    assert exog.index.name == "fecha"


def test_exog_as_injected_output_when_long_data_and_series_ids_are_text():
    """
    Test that future exogenous variables of long-format data whose series ids
    are already text are returned as they are.
    """
    result = exog_as_injected(exog_long, profile_long)

    assert result is exog_long


def test_exog_as_injected_output_when_data_is_not_long():
    """
    Test that a column of future exogenous variables that looks like series
    ids is left untouched for single-series data (whose date index becomes the
    date column) and for wide data, which have no series ids.
    """
    exog_single = pd.DataFrame(
        {"series": [1, 2, 3]}, index=pd.date_range("2023-04-11", periods=3)
    )
    exog_wide = pd.DataFrame(
        {"series": [1, 2, 3]}, index=pd.date_range("2012-04-28", periods=3)
    )

    result_single = exog_as_injected(exog_single, profile_daily)
    result_wide = exog_as_injected(exog_wide, profile_wide)

    expected_single = pd.DataFrame(
        {"date": pd.date_range("2023-04-11", periods=3), "series": [1, 2, 3]}
    )
    pd.testing.assert_frame_equal(result_single, expected_single)
    assert result_wide is exog_wide
    assert result_wide["series"].tolist() == [1, 2, 3]
