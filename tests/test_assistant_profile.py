# Unit test profile ForecastingAssistant

import re
from pathlib import Path

import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import DataNotFoundError, InvalidInputError
from skforecast_ai.schemas import DataProfile, ForecastingProfile

from tests.fixtures_datasets import (
    df_h2o_text,
    df_items_sales_long,
    df_madrid_hourly_text,
)
from tests.fixtures_assistant import (
    df_single,
    df_no_exog,
    df_short,
    df_multi_long,
    df_multi_wide,
    df_with_missing,
    df_constant_target,
    series_single,
    series_unnamed,
)


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_profile_ValueError_when_target_column_not_found():
    """
    Test that profile() raises ValueError when the target column does not
    exist in the DataFrame.
    """
    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="not found"):
        assistant.profile(
            data=df_single, target="nonexistent", date_column="date"
        )


def test_profile_ValueError_when_constant_target():
    """
    Test that profile() raises ValueError when the target column has zero
    variance (constant series).
    """
    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="constant"):
        assistant.profile(
            data=df_constant_target, target="sales", date_column="date"
        )


# =============================================================================
# Tests: basic output
# =============================================================================
def test_profile_output_when_single_series():
    """
    Test that profile() returns a ForecastingProfile with correct DataProfile
    for a single-series DataFrame.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_single, target="sales", date_column="date"
    )

    assert isinstance(profile, ForecastingProfile)
    assert isinstance(profile.data_profile, DataProfile)
    assert profile.data_profile.target == "sales"
    assert profile.data_profile.series_lengths["sales"].length == 100
    assert profile.data_profile.n_series == 1
    assert profile.data_profile.index_type == "datetime"
    assert "promo" in profile.data_profile.exog_columns
    assert profile.forecaster_candidates
    assert profile.forecaster == profile.forecaster_candidates[0]


def test_profile_output_when_no_exog():
    """
    Test that profile() returns a ForecastingProfile with empty exog_columns
    when no exogenous variables are present.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_no_exog, target="sales", date_column="date"
    )

    assert profile.data_profile.exog_columns == []
    assert profile.data_profile.n_series == 1


# =============================================================================
# Tests: pandas Series input
# =============================================================================
def test_profile_output_when_named_series():
    """
    Test that profile() accepts a named pandas Series and derives the
    target from the Series name.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=series_single)

    assert isinstance(profile, ForecastingProfile)
    assert profile.data_profile.target == "sales"
    assert profile.data_profile.n_series == 1
    assert profile.data_profile.index_type == "datetime"
    assert profile.data_profile.exog_columns == []


def test_profile_warns_and_uses_y_when_unnamed_series():
    """
    Test that profile() warns and uses 'y' as the target when the input
    Series has no name.
    """
    assistant = ForecastingAssistant()
    with pytest.warns(UserWarning, match="using 'y'"):
        profile = assistant.profile(data=series_unnamed)

    assert profile.data_profile.target == "y"


def test_profile_ValueError_when_series_target_mismatch():
    """
    Test that profile() raises ValueError when a target is provided that
    does not match the Series name.
    """
    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="must match the Series name"):
        assistant.profile(data=series_single, target="revenue")


def test_profile_ValueError_when_dataframe_and_target_none():
    """
    Test that profile() raises ValueError when a non-Series input is
    provided without a target.
    """
    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="`target` is required"):
        assistant.profile(data=df_single, date_column="date")


# =============================================================================
# Tests: feature-rich / multi-series
# =============================================================================
def test_profile_output_when_multi_series_long_format():
    """
    Test that profile() correctly identifies a long-format multi-series
    dataset with series_id_column.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )

    assert profile.data_profile.n_series == 2
    assert profile.data_profile.data_format == "long"
    assert profile.forecaster == "ForecasterRecursiveMultiSeries"


def test_profile_output_when_multi_series_wide_format():
    """
    Test that profile() correctly identifies a wide-format multi-series
    dataset with multiple target columns.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide,
        target=["series_a", "series_b"],
        date_column="date",
    )

    assert profile.data_profile.n_series == 2
    assert profile.data_profile.data_format == "wide"
    assert profile.forecaster == "ForecasterRecursiveMultiSeries"


def test_profile_output_when_data_has_missing_values():
    """
    Test that profile() succeeds when data has NaN values and populates
    the missing_target field in DataProfile.
    """
    assistant = ForecastingAssistant()
    # The PACF falls back to pairwise deletion on NaN and says so.
    with pytest.warns(MissingValuesWarning, match="pairwise deletion"):
        profile = assistant.profile(
            data=df_with_missing, target="sales", date_column="date"
        )

    assert isinstance(profile, ForecastingProfile)
    assert profile.data_profile.missing_target != {}


def test_profile_output_when_short_series():
    """
    Test that profile() handles a short time series (25 observations)
    without errors.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_short, target="sales", date_column="date"
    )

    assert isinstance(profile, ForecastingProfile)
    assert profile.data_profile.series_lengths["sales"].length == 25


# =============================================================================
# Tests: input type variants
# =============================================================================
@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_profile_output_when_csv_path(tmp_path, path_type):
    """
    Test that profile() accepts CSV file paths as str or Path objects.
    """
    csv_path = tmp_path / "data.csv"
    df_single.to_csv(csv_path, index=False)

    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=path_type(csv_path), target="sales", date_column="date"
    )

    assert isinstance(profile, ForecastingProfile)
    assert profile.data_profile.target == "sales"
    assert profile.data_profile.series_lengths["sales"].length == 100


# =============================================================================
# Tests: error code and field
# =============================================================================
@pytest.mark.parametrize(
    "kwargs, error_class, expected_code, expected_field, err_msg",
    [
        (
            {"data": df_single, "target": "missing", "date_column": "date"},
            InvalidInputError, "invalid_argument", "target",
            "Target column(s) ['missing'] not found in the DataFrame. "
            "Available columns: ['date', 'sales', 'promo']",
        ),
        (
            {"data": df_single, "target": "sales", "date_column": "missing"},
            InvalidInputError, "invalid_argument", "date_column",
            "date_column='missing' was not found in the data. It matches "
            "neither a column ['date', 'sales', 'promo'] nor the index name "
            "('None'). Pass a valid column name, set it as the index, or omit "
            "date_column to use an existing DatetimeIndex.",
        ),
        (
            {"data": "/nonexistent/data.csv", "target": "sales"},
            DataNotFoundError, "data_not_found", "data",
            "CSV file not found: '/nonexistent/data.csv'. Please provide a "
            "valid file path.",
        ),
    ],
    ids=["target", "date_column", "csv_path"],
)
def test_profile_error_code_and_field(
    kwargs, error_class, expected_code, expected_field, err_msg
):
    """
    Test that the errors of profile() carry the code of the error and the
    argument at fault, with the message they had before.
    """
    with pytest.raises(error_class, match=re.escape(err_msg)) as exc_info:
        ForecastingAssistant().profile(**kwargs)

    assert exc_info.value.code == expected_code
    assert exc_info.value.field == expected_field


@pytest.mark.parametrize(
    "date_column, advice",
    [
        (
            None,
            " If the dates are in another column, pass its name as "
            "`date_column`.",
        ),
        ("date", ""),
    ],
    ids=["date_column: None", "date_column: date"],
)
def test_profile_ValueError_when_csv_date_column_has_an_empty_cell(
    tmp_path, date_column, advice
):
    """
    Test that a CSV whose date column has one empty cell (h2o, row 100)
    raises an error that says where it is, with the advice to pass
    `date_column` only when it was not passed. Before, the dates became an
    exogenous variable with one category per row (without `date_column`) or
    were said not to be dates (with it).
    """
    data = df_h2o_text.copy()
    data.loc[100, "date"] = None
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows." + advice
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        ForecastingAssistant().profile(
            data        = csv_path,
            target      = "x",
            date_column = date_column,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"


def test_profile_ValueError_when_long_csv_date_column_has_an_empty_cell(tmp_path):
    """
    Test that a long-format CSV whose date column has one empty cell raises
    the same error. Before, the date became an exogenous variable and the
    generated code failed on a column that does not exist.
    """
    data = df_items_sales_long.assign(
        date=df_items_sales_long["date"].dt.strftime("%Y-%m-%d")
    )
    data.loc[250, "date"] = None
    csv_path = tmp_path / "items.csv"
    data.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "250"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        ForecastingAssistant().profile(
            data             = csv_path,
            target           = "value",
            series_id_column = "series",
        )


def test_profile_ValueError_when_csv_dates_change_time_zone(tmp_path):
    """
    Test that a CSV of hourly dates in local time across a daylight saving
    time change ('+01:00' then '+02:00') raises an error that names the time
    zones. Before, the dates became an exogenous variable with one category
    per row, with a pandas FutureWarning.
    """
    csv_path = tmp_path / "madrid.csv"
    df_madrid_hourly_text.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "The dates of column 'date' mix time zones (+01:00, +02:00), so they "
        "cannot be placed on one time axis (local time does that across a "
        "daylight saving time change)."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=csv_path, target="users")

    assert exc_info.value.field == "data"


def test_profile_output_when_csv_dates_in_utc(tmp_path):
    """
    Test that the same dates written in UTC, as the message asks, are
    profiled as an hourly date column.
    """
    data = df_madrid_hourly_text.assign(
        date=pd.to_datetime(df_madrid_hourly_text["date"], utc=True)
    )
    csv_path = tmp_path / "utc.csv"
    data.to_csv(csv_path, index=False)

    profile = ForecastingAssistant().profile(data=csv_path, target="users")

    assert profile.data_profile.date_column == "date"
    assert profile.data_profile.frequency == "h"
    assert profile.data_profile.start_date == "2012-03-23 23:00:00+00:00"


def test_profile_UserWarning_points_at_the_call_when_later_column_used(tmp_path):
    """
    Test that the warning about a column of dates with empty cells before
    the date column ('contract_end') points at the call of the user, not at
    the package.
    """
    data = df_h2o_text.copy()
    data.insert(0, "contract_end", data["date"])
    data.loc[list(range(10)), "contract_end"] = None
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path, index=False)

    warn_msg = re.escape(
        "The dates of column 'contract_end' have 10 empty cell(s), at row "
        "position(s) 0, 1, 2, 3, 4 and 5 more (counting from 0, header "
        "excluded). Column 'date' is used as the date column instead; pass "
        "`date_column` to choose another one."
    )
    with pytest.warns(UserWarning, match=warn_msg) as record:
        profile = ForecastingAssistant().profile(data=csv_path, target="x")

    assert profile.data_profile.date_column == "date"
    assert profile.data_profile.exog_columns == ["contract_end"]
    assert record[0].filename == __file__
