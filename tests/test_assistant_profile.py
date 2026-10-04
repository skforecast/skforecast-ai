# Unit test profile ForecastingAssistant

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import (
    DataNotFoundError,
    InvalidInputError,
    InvalidInputTypeError,
)
from skforecast_ai.schemas import DataProfile, ForecastingProfile

from tests.fixtures_datasets import (
    df_h2o_text,
    df_iso_dates_with_and_without_time,
    df_items_sales_long,
    df_madrid_hourly_text,
    df_mixed_date_formats,
)
from tests.fixtures_assistant import (
    df_categorical_exog,
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
            "`date_column`; if 'date' is an exogenous variable and the data has "
            "no dates, read the CSV with pandas and pass the DataFrame instead "
            "of its path.",
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


_MIXED_FORMATS_CASES = pytest.mark.parametrize(
    "data, other",
    [
        (df_mixed_date_formats, "2017/07/01 00:00"),
        (df_iso_dates_with_and_without_time, "2017-07-01 00:00:00"),
    ],
    ids=["slashes_and_time", "iso_with_and_without_time"],
)


@_MIXED_FORMATS_CASES
def test_profile_InvalidInputError_when_csv_dates_in_more_than_one_format(
    tmp_path, data, other
):
    """
    Test that a CSV whose dates are written in more than one format raises
    an error that quotes two of them and asks for one format. Before, the
    dates were parsed one by one and profiled, and the generated script,
    which reads them with the format of the first date, failed.
    """
    csv_path = tmp_path / "mixed.csv"
    data.to_csv(csv_path, index=False)

    err_msg = re.escape(
        f"The dates of column 'date' do not all follow the format of the "
        f"first one ('%Y-%m-%d', read from '2015-01-01'), such as '{other}': "
        f"the generated script reads every date with the format of the first "
        f"one. Write every date in the same format, such as '2017-07-01'."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=csv_path, target="y", date_column="date")

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Write every date of the column in the same format, such as "
        "'2017-07-01'."
    )


@_MIXED_FORMATS_CASES
def test_profile_InvalidInputError_when_dataframe_dates_in_more_than_one_format(
    data, other
):
    """
    Test that a DataFrame whose `date_column` holds text dates in more than
    one format raises the same error as a CSV, instead of the raw pandas
    `ValueError` raised before.
    """
    err_msg = re.escape(
        f"The dates of column 'date' do not all follow the format of the "
        f"first one ('%Y-%m-%d', read from '2015-01-01'), such as '{other}': "
        f"the generated script reads every date with the format of the first "
        f"one. Write every date in the same format, such as '2017-07-01'."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=data, target="y", date_column="date")

    assert exc_info.value.field == "data"


def test_profile_InvalidInputError_quotes_date_of_another_format_when_day_first():
    """
    Test that, when the first date reads month-first and the column also
    holds a date in another format, the error quotes that date, which fits
    neither reading of the first one, and not a day-first date written as
    the first one ('13/02/2023').
    """
    data = pd.DataFrame({
        "date": ["01/02/2023", "13/02/2023", "14/02/2023", "2023-02-15"],
        "y": [1.0, 2.0, 3.0, 4.0],
    })

    err_msg = re.escape(
        "The dates of column 'date' do not all follow the format of the first "
        "one ('%m/%d/%Y', read from '01/02/2023'), such as '2023-02-15': the "
        "generated script reads every date with the format of the first one. "
        "Write every date in the same format, such as '2023-02-15'."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        ForecastingAssistant().profile(data=data, target="y", date_column="date")


def test_profile_InvalidInputError_when_month_names_read_as_full_names():
    """
    Test that dates in one format that pandas reads otherwise from the first
    one ('01 May 2015' gives a full month name, which '01 Jun 2015' is not)
    raise an error that quotes the format read and an ISO 8601 example with
    the time of the dates, instead of saying they are in several formats.
    """
    dates = pd.date_range("2015-05-01 06:00", periods=24, freq="MS")
    data = pd.DataFrame({
        "date": dates.strftime("%d %b %Y %H:%M"),
        "y": np.arange(24, dtype=float),
    })

    err_msg = re.escape(
        "The dates of column 'date' do not all follow the format of the first "
        "one ('%d %B %Y %H:%M', read from '01 May 2015 06:00'), such as "
        "'01 Jun 2015 06:00': the generated script reads every date with the "
        "format of the first one. Write every date in the same format, such "
        "as '2015-06-01 06:00:00'."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=data, target="y", date_column="date")

    assert exc_info.value.hint == (
        "Write every date of the column in the same format, such as "
        "'2015-06-01 06:00:00'."
    )


@pytest.mark.parametrize("source", ["csv", "dataframe"])
def test_profile_InvalidInputError_when_day_first_dates_read_month_first(
    tmp_path, source
):
    """
    Test that day-first dates whose first date also reads month-first
    ('01/01/2023', then '13/01/2023') raise with the day-first advice: the
    script reads them all month-first, and a later date proves that reading
    wrong. The hint asks for ISO 8601 without the pandas call.
    """
    data = df_single.assign(date=df_single["date"].dt.strftime("%d/%m/%Y"))
    if source == "csv":
        data.to_csv(tmp_path / "dayfirst.csv", index=False)
        data = tmp_path / "dayfirst.csv"

    err_msg = re.escape(
        "The dates of column 'date' are written day first, but the first one, "
        "'01/01/2023', also reads month first ('%m/%d/%Y'), the format the "
        "generated script reads every date with, and '13/01/2023' does not "
        "fit it: write the dates in ISO 8601, such as '2023-01-13', or read "
        "them with pandas.to_datetime(..., dayfirst=True) before passing them."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=data, target="sales", date_column="date")

    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Write the dates of the column in ISO 8601, such as '2023-01-13'."
    )


def test_profile_output_when_day_first_dates_also_read_month_first():
    """
    Test that day-first dates that all read month-first too (no day after
    the 12th) are profiled as the script reads them, month-first: nothing
    proves that reading wrong.
    """
    dates = pd.date_range("2023-01-01", periods=12, freq="MS")
    data = pd.DataFrame({
        "date": dates.strftime("%d/%m/%Y"),
        "y": np.arange(12, dtype=float),
    })

    profile = ForecastingAssistant().profile(data=data, target="y", date_column="date")

    assert profile.data_profile.frequency == "D"
    assert profile.data_profile.start_date == "2023-01-01"


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


# =============================================================================
# Tests: early input checks
# =============================================================================
@pytest.mark.parametrize(
    "series_id_column, err_msg",
    [
        (
            "missing",
            "series_id_column='missing' was not found in the data. Available "
            "columns: ['date', 'series_id', 'value'].",
        ),
        (
            "value",
            "series_id_column='value' is also the target: pass the column "
            "that identifies the series, other than the values to forecast.",
        ),
        (
            "date",
            "series_id_column='date' is also the date column: pass the column "
            "that identifies the series, other than the dates.",
        ),
    ],
    ids=["not a column", "the target", "the date column"],
)
def test_profile_InvalidInputError_when_series_id_column_invalid(
    series_id_column, err_msg
):
    """
    Test that profile() rejects a `series_id_column` that is not a column or
    is the target or the date column, with the field 'series_id_column'.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        ForecastingAssistant().profile(
            data             = df_multi_long,
            target           = "value",
            date_column      = "date",
            series_id_column = series_id_column,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "series_id_column"


def test_profile_InvalidInputError_when_target_is_empty_list():
    """
    Test that profile() rejects an empty list of targets, with the field
    'target'.
    """
    err_msg = re.escape(
        "`target` is an empty list: pass the name of the column to forecast, "
        "or a list with the column of each series."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(
            data=df_multi_wide, target=[], date_column="date"
        )

    assert exc_info.value.field == "target"


def test_profile_InvalidInputError_when_target_has_no_values():
    """
    Test that profile() rejects a target with every value missing, with the
    code 'insufficient_data'.
    """
    data = df_single.assign(sales=np.nan)

    err_msg = re.escape("Target column 'sales' has no values: every row is missing.")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(
            data=data, target="sales", date_column="date"
        )

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "target"


_TARGET_NOT_NUMERIC_HINT = (
    "Leave the cells of missing values empty instead of marking them with "
    "text such as '-' or '?', and check that the target is the column of "
    "values to forecast."
)


def test_profile_InvalidInputError_when_target_not_numeric():
    """
    Test that profile() rejects a target with text that is not a number,
    listing the values, before the lags are selected.
    """
    data = df_single.assign(sales=df_single["sales"].astype(object))
    data.loc[3, "sales"] = "abc"

    err_msg = re.escape(
        "Target column 'sales' is not numeric: values such as ['abc'] are "
        "not numbers."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(
            data=data, target="sales", date_column="date"
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "target"
    assert exc_info.value.hint == _TARGET_NOT_NUMERIC_HINT


def test_profile_InvalidInputError_when_csv_target_has_placeholders(tmp_path):
    """
    Test that profile() of a CSV whose missing values are marked with '-'
    rejects the target, quoting the placeholder.
    """
    data = df_h2o_text.copy()
    data["x"] = data["x"].astype(object)
    data.loc[[3, 5], "x"] = "-"
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "Target column 'x' is not numeric: values such as ['-'] are not numbers."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=csv_path, target="x")

    assert exc_info.value.field == "target"
    assert exc_info.value.hint == _TARGET_NOT_NUMERIC_HINT


def test_profile_output_when_target_is_numeric_strings():
    """
    Test that profile() does not reject a target of text that holds numbers.
    """
    data = df_single.assign(sales=df_single["sales"].astype(str))

    profile = ForecastingAssistant().profile(
        data=data, target="sales", date_column="date"
    )

    assert profile.data_profile.target == "sales"


@pytest.mark.parametrize(
    "content, reason",
    [
        (b"", "No columns to parse from file"),
        (
            bytes(range(256)),
            "'utf-8' codec can't decode byte 0x80 in position 128: invalid "
            "start byte",
        ),
        (
            b"date,x\n2020-01-01,1\n2020-01-02,2,3,4\n2020-01-03,4\n",
            "Error tokenizing data. C error: Expected 2 fields in line 3, saw 4",
        ),
        (
            "date,x,name\n2020-01-01,1,caf\xe9\n".encode("latin-1"),
            "'utf-8' codec can't decode byte 0xe9 in position 28: invalid "
            "continuation byte",
        ),
    ],
    ids=["empty", "binary", "more fields than the header", "latin-1"],
)
def test_profile_InvalidInputError_when_csv_unreadable(tmp_path, content, reason):
    """
    Test that profile() of a file that is not a readable CSV raises an
    InvalidInputError (a ValueError) with the code 'data_unreadable', the
    field 'data' and a hint.
    """
    csv_path = tmp_path / "data.csv"
    csv_path.write_bytes(content)

    err_msg = re.escape(f"The CSV file '{csv_path}' could not be read: {reason}")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=csv_path, target="x")

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Pass a comma-separated text file in UTF-8 with a header row, and the "
        "same number of fields in every row."
    )


@pytest.mark.parametrize(
    "data, type_name", [([1.0, 2.0, 3.0], "list"), (5, "int")], ids=["list", "int"]
)
def test_profile_InvalidInputTypeError_when_data_wrong_type(data, type_name):
    """
    Test that profile() raises InvalidInputTypeError (a TypeError) with the
    field 'data' when it is not a DataFrame, a Series or a path.
    """
    err_msg = re.escape(
        f"`data` must be a pandas DataFrame, a pandas Series, or the path or "
        f"URL of a CSV file, got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=data, target="sales")

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "data"


def test_profile_hint_when_csv_date_column_has_an_empty_cell(tmp_path):
    """
    Test that the error of a CSV date column with an empty cell carries the
    remedy as the hint.
    """
    data = df_h2o_text.copy()
    data.loc[100, "date"] = None
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path, index=False)

    with pytest.raises(InvalidInputError) as exc_info:
        ForecastingAssistant().profile(data=csv_path, target="x", date_column="date")

    assert exc_info.value.hint == (
        "Every row needs a date: fill in or drop the rows without one."
    )


@pytest.mark.parametrize(
    "date_column, advice",
    [
        (None, ""),
        ("date", ""),
    ],
    ids=["date_column: None", "date_column: date"],
)
def test_profile_hint_when_csv_dates_change_time_zone(
    tmp_path, date_column, advice
):
    """
    Test that the error of CSV dates in several time zones carries the time
    zone remedy as the hint (followed, without `date_column`, by the advice
    about a column of dates that is an exogenous variable).
    """
    csv_path = tmp_path / "madrid.csv"
    df_madrid_hourly_text.to_csv(csv_path, index=False)

    with pytest.raises(InvalidInputError) as exc_info:
        ForecastingAssistant().profile(
            data=csv_path, target="users", date_column=date_column
        )

    assert exc_info.value.hint == (
        "Write every date in one time zone: in UTC for data recorded within "
        "the day, or without the time zone for daily or coarser data." + advice
    )


# =============================================================================
# Tests: exog_columns
# =============================================================================
@pytest.mark.parametrize(
    "exog_columns, expected_exog, expected_categorical, expected_unused",
    [
        (["promo"], ["promo"], [], ["weekday"]),
        (["weekday", "promo"], ["promo", "weekday"], ["weekday"], []),
        ([], [], [], ["promo", "weekday"]),
        (("weekday",), ["weekday"], ["weekday"], ["promo"]),
    ],
    ids=["subset", "all in another order", "none", "tuple"],
)
def test_profile_output_when_exog_columns(
    exog_columns, expected_exog, expected_categorical, expected_unused
):
    """
    Test that profile() with `exog_columns` keeps those exogenous columns in
    the order of the data, lists the others in `unused_columns` and names
    them in a note of `warnings`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data         = df_categorical_exog,
        target       = "sales",
        date_column  = "date",
        exog_columns = exog_columns,
    )

    data_profile = profile.data_profile
    assert data_profile.exog_columns == expected_exog
    assert data_profile.categorical_exog == expected_categorical
    assert data_profile.unused_columns == expected_unused
    expected_warnings = (
        [
            f"Columns of the data that the profile leaves out are not used: "
            f"{expected_unused}."
        ]
        if expected_unused else []
    )
    assert data_profile.warnings == expected_warnings


def test_profile_output_when_exog_columns_none_is_the_default():
    """
    Test that profile() with `exog_columns=None` returns the profile of a
    call without it: every column that is not the target or the date.
    """
    assistant = ForecastingAssistant()

    default = assistant.profile(
        data        = df_categorical_exog,
        target      = "sales",
        date_column = "date",
    )
    explicit = assistant.profile(
        data         = df_categorical_exog,
        target       = "sales",
        date_column  = "date",
        exog_columns = None,
    )

    assert explicit == default
    assert default.data_profile.exog_columns == ["promo", "weekday"]
    assert default.data_profile.unused_columns == []


def test_profile_output_when_exog_columns_leave_out_more_than_five():
    """
    Test that the note of the columns left out names the first 5 and how
    many there are.
    """
    data = df_no_exog.assign(**{f"x{i}": float(i) for i in range(7)})
    assistant = ForecastingAssistant()

    profile = assistant.profile(
        data         = data,
        target       = "sales",
        date_column  = "date",
        exog_columns = ["x6"],
    )

    assert profile.data_profile.unused_columns == [f"x{i}" for i in range(6)]
    assert profile.data_profile.warnings == [
        "Columns of the data that the profile leaves out are not used: "
        "['x0', 'x1', 'x2', 'x3', 'x4'] (first 5 of 6)."
    ]


def test_profile_output_when_exog_columns_of_wide_and_long_data():
    """
    Test that `exog_columns` selects the exogenous columns of wide data
    (the series of `target` are not exogenous) and of long data (the series
    id column is not either).
    """
    assistant = ForecastingAssistant()
    wide = assistant.profile(
        data         = df_multi_wide.assign(promo=1.0, price=2.0),
        target       = ["series_a", "series_b"],
        date_column  = "date",
        exog_columns = ["price"],
    )
    long = assistant.profile(
        data             = df_multi_long.assign(promo=1.0, price=2.0),
        target           = "value",
        date_column      = "date",
        series_id_column = "series_id",
        exog_columns     = [],
    )

    assert wide.data_profile.exog_columns == ["price"]
    assert wide.data_profile.unused_columns == ["promo"]
    assert long.data_profile.exog_columns == []
    assert long.data_profile.unused_columns == ["promo", "price"]


@pytest.mark.parametrize(
    "exog_columns",
    ["promo", [1], [["promo"]], {"promo": 1}],
    ids=lambda dt: f"{dt!r}",
)
def test_profile_InvalidInputTypeError_when_exog_columns_not_a_list_of_names(
    exog_columns,
):
    """
    Test that profile() raises InvalidInputTypeError (a TypeError) with the
    field 'exog_columns' when it is not a list of column names.
    """
    assistant = ForecastingAssistant()

    err_msg = re.escape(
        f"`exog_columns` must be a list of column names, got {exog_columns!r}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        assistant.profile(
            data         = df_categorical_exog,
            target       = "sales",
            date_column  = "date",
            exog_columns = exog_columns,
        )

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "exog_columns"


@pytest.mark.parametrize(
    "exog_columns, err_msg",
    [
        (
            ["promo", "promo"],
            "`exog_columns` names a column more than once: ['promo'].",
        ),
        (
            ["sales", "promo"],
            "`exog_columns` names the target, the date or the series id "
            "column: ['sales']. An exogenous variable is any other column of "
            "the data.",
        ),
        (
            ["date"],
            "`exog_columns` names the target, the date or the series id "
            "column: ['date']. An exogenous variable is any other column of "
            "the data.",
        ),
        (
            ["price", "promo"],
            "`exog_columns` names columns that are not in the data: "
            "['price']. Columns of the data: ['date', 'sales', 'promo', "
            "'weekday'].",
        ),
    ],
    ids=["repeated", "target", "date", "missing"],
)
def test_profile_InvalidInputError_when_exog_columns_invalid(exog_columns, err_msg):
    """
    Test that profile() raises InvalidInputError (a ValueError) with the
    field 'exog_columns' when it repeats a column, names the target or the
    date column, or names a column that is not in the data.
    """
    assistant = ForecastingAssistant()

    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        assistant.profile(
            data         = df_categorical_exog,
            target       = "sales",
            date_column  = "date",
            exog_columns = exog_columns,
        )

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.field == "exog_columns"


def test_profile_InvalidInputError_when_exog_columns_name_series_id_column():
    """
    Test that profile() raises InvalidInputError when `exog_columns` names
    the series id column of long data.
    """
    assistant = ForecastingAssistant()

    err_msg = re.escape(
        "`exog_columns` names the target, the date or the series id column: "
        "['series_id']. An exogenous variable is any other column of the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        assistant.profile(
            data             = df_multi_long,
            target           = "value",
            date_column      = "date",
            series_id_column = "series_id",
            exog_columns     = ["series_id"],
        )


def test_profile_output_when_repeated_rows_differ_only_in_left_out_column():
    """
    Test that a timestamp repeated in rows that differ only in a column left
    out by `exog_columns` is dropped as a duplicate (the generated script
    keeps the first row), instead of raising as with every column.
    """
    data = pd.concat(
        [df_categorical_exog, df_categorical_exog.iloc[[10]].assign(weekday="x")]
    )
    assistant = ForecastingAssistant()

    profile = assistant.profile(
        data         = data,
        target       = "sales",
        date_column  = "date",
        exog_columns = ["promo"],
    )

    err_msg = re.escape(
        "Found 1 timestamp with more than one row and different values, for "
        "example '2023-01-11'."
    )
    assert profile.data_profile.has_duplicate_timestamps is True
    with pytest.raises(InvalidInputError, match=err_msg):
        assistant.profile(data=data, target="sales", date_column="date")


def test_profile_output_when_exog_columns_leave_out_column_not_named_by_text():
    """
    Test that a column whose name is not a string (an integer) can be left
    out by `exog_columns`, and is listed by its text.
    """
    data = df_no_exog.assign(promo=1.0, **{"5": 2.0}).rename(columns={"5": 5})
    assistant = ForecastingAssistant()

    profile = assistant.profile(
        data         = data,
        target       = "sales",
        date_column  = "date",
        exog_columns = ["promo"],
    )

    assert profile.data_profile.exog_columns == ["promo"]
    assert profile.data_profile.unused_columns == ["5"]
