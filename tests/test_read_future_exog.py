# Unit test read_future_exog

import pandas as pd
import pytest

from skforecast_ai._future_exog import read_future_exog
from skforecast_ai.schemas import FutureExogFile

from tests.fixtures_future_exog import (
    data_daily,
    data_range,
    profile_daily,
    profile_range,
)


@pytest.mark.parametrize(
    "data, expected_index",
    [
        (data_range, pd.RangeIndex(60, 63)),
        (data_range.set_axis(pd.RangeIndex(50, 110)), pd.RangeIndex(110, 113)),
        (None, pd.RangeIndex(0, 3)),
    ],
    ids=["data", "data with an offset", "no data"],
)
def test_read_future_exog_output_when_data_without_dates_and_rows_by_position(
    tmp_path, data, expected_index
):
    """
    Test that a file of future values of data without dates that has no
    column of positions is read by position, its rows numbered from the
    position after the last row of the data (`data.index[-1] + 1`, as the
    script numbers them), and keep the numbers of the file without data
    (`forecast_code()`, which only needs how the file is written).
    """
    path = tmp_path / "futuro.csv"
    path.write_text("x\n0.5\n1.5\n2.5\n")

    exog, exog_file = read_future_exog(path, data, profile_range)

    expected = pd.DataFrame({"x": [0.5, 1.5, 2.5]}, index=expected_index)
    pd.testing.assert_frame_equal(exog, expected)
    assert exog_file == FutureExogFile(path=str(path), by_position=True)


def test_read_future_exog_output_when_data_without_dates_and_column_of_positions(
    tmp_path,
):
    """
    Test that a file of future values of data without dates with a first
    column without a name keeps its positions, which are not renumbered:
    `validate_future_exog` checks that they follow the data.
    """
    path = tmp_path / "futuro.csv"
    path.write_text(",x\n0,0.5\n1,1.5\n2,2.5\n")

    exog, exog_file = read_future_exog(path, data_range, profile_range)

    expected = pd.DataFrame({"x": [0.5, 1.5, 2.5]}, index=pd.RangeIndex(0, 3))
    pd.testing.assert_frame_equal(exog, expected)
    assert exog_file == FutureExogFile(path=str(path))


def test_read_future_exog_output_when_dates_read_with_the_profile(tmp_path):
    """
    Test that the future values of dated data are read with the date column
    of the profile and its format: dates written day first with a semicolon
    as separator are indexed by those dates, and the file keeps how it is
    written for the script.
    """
    path = tmp_path / "futuro.csv"
    path.write_text("date;promo\n11/04/2023;0.5\n12/04/2023;1.5\n13/04/2023;0.0\n")
    profile = profile_daily.model_copy(update={"date_format": "%d/%m/%Y"})

    exog, exog_file = read_future_exog(path, data_daily, profile)

    expected = pd.DataFrame(
        {"promo": [0.5, 1.5, 0.0]},
        index=pd.DatetimeIndex(
            ["2023-04-11", "2023-04-12", "2023-04-13"], name="date"
        ),
    )
    pd.testing.assert_frame_equal(exog, expected)
    assert exog_file == FutureExogFile(
        path        = str(path),
        sep         = ";",
        date_format = "%d/%m/%Y",
        date_column = "date",
    )
