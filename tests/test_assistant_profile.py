# Unit test profile ForecastingAssistant

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import IgnoredArgumentWarning, MissingValuesWarning

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import (
    DataNotFoundError,
    InvalidInputError,
    InvalidInputTypeError,
)
from skforecast_ai.schemas import DataProfile, ForecastingProfile
from skforecast_ai.profiling.csv_dialect import ENCODING_HINT
from skforecast_ai.profiling.data_profile import DAYFIRST_FRAME_HINT, DAYFIRST_HINT

from tests.fixtures_datasets import (
    df_h2o_text,
    df_iso_dates_with_and_without_time,
    df_items_sales_long,
    df_madrid_hourly_text,
    df_mixed_date_formats,
)
from tests.fixtures_csv_dialect import (
    df_dialect,
    df_dialect_cp1252,
    df_dialect_monthly,
    df_dialect_thousands,
    write_cp1252,
    write_dialect,
    write_thousands,
)
from tests.fixtures_assistant import (
    df_categorical_exog,
    df_single,
    df_no_exog,
    df_short,
    df_multi_long,
    df_multi_long_integer_ids,
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


def test_profile_series_pacf_when_long_format_multiindex_with_integer_ids():
    """
    Test that profile() computes the PACF of long-format data indexed by a
    (series_id, date) MultiIndex on the flat frame the profile describes:
    the integer ids are named and ordered as text ('1', '10', '2'), as those
    of the same data with the levels as columns. Before, the PACF read the
    MultiIndex and listed the series in numeric order ('1', '2', '10').
    """
    assistant = ForecastingAssistant()
    expected = assistant.profile(
        data             = df_multi_long_integer_ids,
        target           = "value",
        date_column      = "date",
        series_id_column = "series_id",
    )
    data = df_multi_long_integer_ids.set_index(["series_id", "date"])

    profile = assistant.profile(data=data, target="value")

    assert [
        (pacf.series_id, pacf.n_observations, pacf.lags)
        for pacf in profile.series_pacf
    ] == [
        ("1", 100, [1, 2, 3]),
        ("10", 100, [7, 5, 6, 8, 4, 3, 2]),
        ("2", 100, [1, 2, 3]),
    ]
    np.testing.assert_array_almost_equal(
        np.concatenate([pacf.pacf_abs for pacf in profile.series_pacf]),
        np.array([
            0.9497286304844792, 0.6156822781008228, 0.3799783360889658,
            0.7611519872802129, 0.549834183045989, 0.5300736984603612,
            0.46977843055323154, 0.4572166474212591, 0.37154322504876336,
            0.3292776741776512,
            0.9360758090523229, 0.8483403398362086, 0.42448197624098877,
        ]),
    )
    assert profile.series_pacf == expected.series_pacf
    assert profile.data_profile == expected.data_profile


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
    # The PACF uses only the pairs of finite values on NaN and says so.
    with pytest.warns(MissingValuesWarning, match="Only the pairs where both values are finite"):
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
            # The path as the platform writes it (backslashes on Windows).
            f"CSV file not found: '{Path('/nonexistent/data.csv')}'. Please "
            f"provide a valid file path.",
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
def test_profile_output_when_day_first_dates_after_one_that_reads_month_first(
    tmp_path, source
):
    """
    Test that day-first dates whose first date also reads month-first
    ('01/01/2023', then '13/01/2023') are read day first, the only order
    that reads every date, and that the profile records the format the
    generated script reads them with.
    """
    data = df_single.assign(date=df_single["date"].dt.strftime("%d/%m/%Y"))
    if source == "csv":
        data.to_csv(tmp_path / "dayfirst.csv", index=False)
        data = tmp_path / "dayfirst.csv"

    profile = ForecastingAssistant().profile(
        data=data, target="sales", date_column="date"
    )

    dp = profile.data_profile
    assert dp.date_format == "%d/%m/%Y"
    assert dp.frequency == "D"
    assert dp.start_date == "2023-01-01"
    assert dp.series_lengths["sales"].end == "2023-04-10"


@pytest.mark.parametrize(
    "source, fix, hint",
    [
        (
            "csv",
            "Profile the file saying which it is, with `dayfirst`.",
            DAYFIRST_HINT,
        ),
        (
            "dataframe",
            "Profile the data saying which it is, with `dayfirst`.",
            DAYFIRST_FRAME_HINT,
        ),
    ],
)
def test_profile_InvalidInputError_when_dates_read_day_first_and_month_first(
    tmp_path, source, fix, hint
):
    """
    Test that three monthly dates that all read both day first and month
    first (no day after the 12th) and are regular in both orders (monthly
    day first, daily month first) raise instead of being read month first,
    quoting a date whose two readings differ and both frequencies, with the
    code 'data_unreadable' and the hint that names `dayfirst`, for a CSV file
    and for a DataFrame.
    """
    data = pd.DataFrame({
        "date": ["01/01/2023", "01/02/2023", "01/03/2023"],
        "y": [1.0, 2.0, 4.0],
    })
    if source == "csv":
        data.to_csv(tmp_path / "monthly.csv", index=False)
        data = tmp_path / "monthly.csv"

    err_msg = re.escape(
        "The dates of column 'date' read both day first and month first: no "
        "day is after the 12th, so '01/02/2023' may be '2023-02-01' or "
        "'2023-01-02', and both readings have a regular frequency ('MS' day "
        f"first and 'D' month first), so the order is not guessed. {fix}"
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        ForecastingAssistant().profile(
            data=data, target="y", date_column="date", dayfirst=None
        )

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == hint


@pytest.mark.parametrize("source", ["csv", "dataframe"])
@pytest.mark.parametrize(
    "written, read, quoted",
    [
        ("%m/%d/%Y", "month", "'02/01/2019' is '2019-02-01' and not '2019-01-02'"),
        ("%d/%m/%Y", "day", "'01/02/2019' is '2019-02-01' and not '2019-01-02'"),
    ],
    ids=["us monthly", "spanish monthly"],
)
def test_profile_output_when_dates_read_both_ways_and_only_one_order_is_regular(
    tmp_path, source, written, read, quoted
):
    """
    Test that five years of monthly dates on the first of each month, which
    all read day first and month first, are profiled in the only order in
    which they have a regular frequency: month first for a US file
    ('02/01/2019'), which 0.5.x read right and still does, and day first for
    a Spanish one. Both are monthly from January 2019, the profile records
    the format, and `DataProfile.warnings` starts with the note that says
    the order was told from the regularity and how to give the other one.
    """
    dates = pd.date_range("2019-01-01", periods=60, freq="MS")
    data = pd.DataFrame({
        "date": dates.strftime(written),
        "y": np.round(10 + np.sin(np.arange(60)), 3),
    })
    if source == "csv":
        data.to_csv(tmp_path / "monthly.csv", index=False)
        data = tmp_path / "monthly.csv"

    profile = ForecastingAssistant().profile(
        data=data, target="y", date_column="date"
    )

    dp = profile.data_profile
    other = "day" if read == "month" else "month"
    dayfirst = other == "day"
    remedy = (
        f"profile the file again with `dayfirst={dayfirst}` in `profile()`, "
        f"`--{other}first` in the `profile` command or `dayfirst` "
        f"{str(dayfirst).lower()} in the `profile` tool of the MCP server"
        if source == "csv" else
        f"profile the data again with `dayfirst={dayfirst}`"
    )
    assert dp.date_format == written
    assert dp.frequency == "MS"
    assert dp.start_date == "2019-01-01"
    assert dp.series_lengths["y"].end == "2023-12-01"
    assert dp.warnings[0] == (
        f"The dates of column 'date' read both day first and month first (no "
        f"day is after the 12th): they were read {read} first, the only order "
        f"in which they have a regular frequency ('MS'), so {quoted}. If they "
        f"are written {other} first, {remedy}."
    )


@pytest.mark.parametrize(
    "dayfirst, expected_format, expected_frequency",
    [(True, "%d/%m/%Y", "MS"), (False, "%m/%d/%Y", "D")],
    ids=["day first", "month first"],
)
def test_profile_output_when_dayfirst_given_for_text_dates_of_a_dataframe(
    dayfirst, expected_format, expected_frequency
):
    """
    Test that `dayfirst` decides the order of the text dates of a DataFrame
    that read both ways, as for a CSV file: three dates regular in both
    orders are monthly day first and daily month first.
    """
    data = pd.DataFrame({
        "date": ["01/01/2023", "01/02/2023", "01/03/2023"],
        "y": [1.0, 2.0, 4.0],
    })

    profile = ForecastingAssistant().profile(
        data=data, target="y", date_column="date", dayfirst=dayfirst
    )

    assert profile.data_profile.date_format == expected_format
    assert profile.data_profile.frequency == expected_frequency


def test_profile_IgnoredArgumentWarning_when_dayfirst_and_dataframe_dates_are_datetime():
    """
    Test that `dayfirst` with a DataFrame whose dates are already datetime
    emits an IgnoredArgumentWarning saying that it does not apply, pointing
    at the call, and the profile is the one without it. A CSV file whose
    dates `dayfirst` reads emits no such warning.
    """
    warn_msg = re.escape(
        "`dayfirst` does not apply and is ignored: the dates of column 'date' "
        "are not text, so the order of their day and month is already set. It "
        "orders the day and the month of dates written as text, such as "
        "'01/02/2020'."
    )
    with pytest.warns(IgnoredArgumentWarning, match="^" + warn_msg) as record:
        profile = ForecastingAssistant().profile(
            data=df_single, target="sales", date_column="date", dayfirst=True
        )

    assert record[0].filename == __file__
    assert profile == ForecastingAssistant().profile(
        data=df_single, target="sales", date_column="date"
    )


@pytest.mark.parametrize(
    "dayfirst, start_date, frequency",
    [(True, "2023-01-01", "MS"), (False, "2023-01-01", None)],
    ids=["day first", "month first"],
)
def test_profile_output_when_dayfirst_given_for_dates_that_read_both_ways(
    tmp_path, dayfirst, start_date, frequency
):
    """
    Test that `dayfirst` decides the order of dates that read both ways:
    day first, the monthly data of the file; month first, the first twelve
    days of each January, irregular. The profile records the format either
    way, so the script and the other methods read the file in that order.
    """
    dates = pd.date_range("2023-01-01", periods=24, freq="MS")
    path = tmp_path / "monthly.csv"
    pd.DataFrame({
        "date": dates.strftime("%d/%m/%Y"),
        "y": np.arange(24, dtype=float),
    }).to_csv(path, index=False)

    profile = ForecastingAssistant().profile(data=path, target="y", dayfirst=dayfirst)

    dp = profile.data_profile
    assert dp.date_format == ("%d/%m/%Y" if dayfirst else "%m/%d/%Y")
    assert dp.start_date == start_date
    assert dp.frequency == frequency


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
    # Local time of the zone the profile names, without the UTC offset.
    assert profile.data_profile.start_date == "2012-03-23 23:00:00"
    assert profile.data_profile.time_zone == "UTC"


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


@pytest.mark.parametrize(
    "names",
    [[None, None], ["series_id", None], [None, "date"]],
    ids=lambda names: f"names: {names}",
)
def test_profile_InvalidInputError_when_multiindex_level_unnamed(names):
    """
    Test that profile() rejects long-format data indexed by a MultiIndex with
    a level without a name, with a hint to name the levels: the generated
    script reads the levels by name from the frame saved with `to_csv()`,
    which writes an empty header for them. Before, two unnamed levels raised
    KeyError: 'series_id', and an unnamed date level was profiled as a column
    'datetime' that the script did not have.
    """
    data = df_multi_long.set_index(["series_id", "date"]).rename_axis(names)
    err_msg = re.escape(
        f"`data` is indexed by a MultiIndex with levels without a name "
        f"(names {names})."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=data, target="value")

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Name the levels with text, as in "
        "`data.rename_axis(['series_id', 'date'])`, or turn them into columns "
        "with `data.reset_index()` and pass their names as `series_id_column` "
        "and `date_column`."
    )


@pytest.mark.parametrize(
    "levels, names, err_msg",
    [
        (
            ["series_id", "date", "region"],
            None,
            "`data` is indexed by a MultiIndex with 3 levels (names "
            "['series_id', 'date', 'region']). A MultiIndex is read as the "
            "series id and the date, `(series_id, date)`, so it must have two "
            "levels.",
        ),
        (
            ["region", "series_id", "date"],
            None,
            "`data` is indexed by a MultiIndex with 3 levels (names "
            "['region', 'series_id', 'date']).",
        ),
        (
            ["series_id", "date"],
            [0, "date"],
            "`data` is indexed by a MultiIndex with levels not named with text "
            "(names [0, 'date']).",
        ),
    ],
    ids=["three levels", "three levels, dates last", "level named with a number"],
)
def test_profile_InvalidInputError_when_multiindex_not_two_levels_named_with_text(
    levels, names, err_msg
):
    """
    Test that profile() rejects a MultiIndex that is not `(series_id, date)`,
    with a hint: a third level, which would otherwise be profiled as an
    exogenous variable when last and would shift the dates to the series ids
    when first, or a level named with a number, which raised a
    ValidationError of the profile.
    """
    data = df_multi_long.assign(region="north").set_index(levels)
    if names is not None:
        data = data.rename_axis(names)
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        ForecastingAssistant().profile(data=data, target="value")

    assert exc_info.value.field == "data"


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
            b"date,x\n2020-01-01,1\n2020-01-02,2,3,4\n2020-01-03,4\n",
            "Error tokenizing data. C error: Expected 2 fields in line 3, saw 4",
        ),
    ],
    ids=["empty", "more fields than the header"],
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
        "Pass a text file in UTF-8 separated by ',', ';' or tabulators, with a "
        "header row and the same number of fields in every row."
    )


@pytest.mark.parametrize("name", ["excel.csv", "excel.csv.gz"], ids=["plain", "gzip"])
def test_profile_output_when_csv_is_cp1252(tmp_path, name):
    """
    Test that profile() of the CSV that Excel saves on Windows in Spanish
    (cp1252, ';', ',' as decimal mark, 'año' as target and accents in the
    categories of 'zona') records the encoding with the dialect, reads the
    names and the categories right and says first among the warnings that
    the encoding cannot be checked; also compressed with gzip.
    """
    csv_path = write_cp1252(tmp_path, name=name)

    profile = ForecastingAssistant().profile(data=csv_path, target="año")

    data_profile = profile.data_profile
    assert data_profile.csv_encoding == "cp1252"
    assert (data_profile.csv_sep, data_profile.csv_decimal) == (";", ",")
    assert data_profile.date_format == "%d/%m/%Y"
    assert data_profile.exog_columns == ["zona"]
    assert data_profile.categorical_exog == ["zona"]
    assert data_profile.warnings[0] == (
        "The CSV file is not UTF-8: it was read as cp1252 (Windows-1252), the "
        "encoding of the CSV files that Excel saves on Windows, and the "
        "generated script reads it so. That encoding cannot be checked: if "
        "column names or categories show wrong characters, save the file as "
        "UTF-8 and profile it again."
    )


def test_profile_output_when_csv_is_utf8_with_bom(tmp_path):
    """
    Test that profile() of a UTF-8 file with a byte order mark records UTF-8
    and gives no note on the encoding.
    """
    csv_path = tmp_path / "bom.csv"
    df_dialect_cp1252.to_csv(
        csv_path, index=False, sep=";", decimal=",", encoding="utf-8-sig"
    )

    profile = ForecastingAssistant().profile(data=csv_path, target="año")

    assert profile.data_profile.csv_encoding == "utf-8"
    assert profile.data_profile.exog_columns == ["zona"]
    assert not any("UTF-8" in warning for warning in profile.data_profile.warnings)


def test_profile_InvalidInputError_when_csv_is_utf16(tmp_path):
    """
    Test that profile() of a file in UTF-16, which cp1252 would read with
    null bytes, raises an InvalidInputError with the code 'data_unreadable'
    and the hint that asks for a copy in UTF-8.
    """
    csv_path = tmp_path / "unicode.csv"
    df_dialect_cp1252.to_csv(
        csv_path, index=False, sep=";", decimal=",", encoding="utf-16"
    )

    err_msg = re.escape(
        f"The CSV file '{csv_path}' could not be read: it is written in UTF-16"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=csv_path, target="año")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == ENCODING_HINT


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


def test_profile_output_when_target_almost_all_infinite():
    """
    Test that profile() of a target with only 2 finite values (the rest
    infinite) returns a profile without PACF instead of failing inside the
    PACF, and that forecast() then rejects the infinite values.
    """
    data = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=60, freq="D"),
        "y": np.r_[np.full(58, np.inf), [1.0, 2.0]],
    })
    assistant = ForecastingAssistant()

    with pytest.warns(RuntimeWarning, match="invalid value encountered"):
        profile = assistant.profile(data=data, target="y", date_column="date")
    err_msg = re.escape(
        "The target has infinite values (58 value(s), such as '2020-01-01', "
        "'2020-01-02', '2020-01-03', '2020-01-04', '2020-01-05' and 53 more). "
        "ForecasterRecursive cannot be trained on them: replace them."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        assistant.forecast(data=data, profile=profile, steps=3)

    assert profile.series_pacf == []


def test_profile_output_time_zone_of_the_dates():
    """
    Test that the profile keeps the name of the time zone of the dates, and
    None for dates without one. A profile saved without it (an earlier
    version) is profiled again by forecast() without a note.
    """
    assistant = ForecastingAssistant()
    index = pd.date_range("2023-01-01", periods=100, freq="D")
    data = pd.DataFrame({"y": np.arange(100, dtype=float) % 7}, index=index)
    madrid = data.set_axis(index.tz_localize("Europe/Madrid"))
    utc = data.set_axis(index.tz_localize("UTC"))

    profile = assistant.profile(data=madrid, target="y")
    saved = profile.model_copy(update={
        "data_profile": profile.data_profile.model_copy(update={"time_zone": None})
    })
    result = assistant.forecast(data=madrid, profile=saved, steps=3)

    assert assistant.profile(data=data, target="y").data_profile.time_zone is None
    assert assistant.profile(data=utc, target="y").data_profile.time_zone == "UTC"
    assert profile.data_profile.time_zone == "Europe/Madrid"
    assert result.profile.data_profile.time_zone == "Europe/Madrid"
    assert result.profile.data_profile.warnings == []


# =============================================================================
# Tests: CSV dialects (separator and decimal mark)
# =============================================================================
def test_profile_reads_csv_with_semicolon_and_decimal_comma(tmp_path):
    """
    Test that a CSV written with `to_csv(sep=';', decimal=',')` (what Excel
    writes in Spanish, German or French) is profiled instead of raising,
    records its dialect, and gives the same profile as the same frame written
    with the default `to_csv`, but for the path and the dialect. The day first
    dates on the first of each month read both ways, so `dayfirst` gives
    their order in both files, and the frequency is monthly.
    """
    semicolon_path = tmp_path / "eu.csv"
    comma_path = tmp_path / "us.csv"
    df_dialect_monthly.to_csv(semicolon_path, sep=";", decimal=",", index=False)
    df_dialect_monthly.to_csv(comma_path, index=False)
    assistant = ForecastingAssistant()

    result = assistant.profile(semicolon_path, target="y", dayfirst=True)
    expected = assistant.profile(comma_path, target="y", dayfirst=True)

    dp = result.data_profile
    assert dp.csv_sep == ";"
    assert dp.csv_decimal == ","
    assert dp.data_path == str(semicolon_path)
    assert dp.date_format == "%d/%m/%Y"
    assert dp.frequency == "MS"
    assert dp.n_total_observations == 48
    assert expected.data_profile.csv_sep == ","
    assert expected.data_profile.csv_decimal == "."
    left = result.data_profile.model_dump()
    right = expected.data_profile.model_dump()
    for name in ("data_path", "csv_sep", "csv_decimal"):
        del left[name], right[name]
    assert left == right
    assert result.model_dump(exclude={"data_profile"}) == expected.model_dump(
        exclude={"data_profile"}
    )


@pytest.mark.parametrize(
    "name, expected",
    [
        ("semicolon_dot", (";", ".")),
        ("semicolon_comma", (";", ",")),
        ("tab_dot", ("\t", ".")),
        ("tab_comma", ("\t", ",")),
        ("tsv", ("\t", ".")),
        ("gz_comma_dot", (",", ".")),
        ("gz_semicolon_comma", (";", ",")),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_profile_records_the_dialect_of_the_csv_file(tmp_path, name, expected):
    """
    Test that profile() detects and records the separator and the decimal
    mark of ';', tab, '.tsv' and gzip files, and gives the same description
    of the data in every dialect.
    """
    path = write_dialect(tmp_path, df_dialect, name)
    assistant = ForecastingAssistant()

    result = assistant.profile(path, target="y")

    assert (result.data_profile.csv_sep, result.data_profile.csv_decimal) == expected
    assert result.data_profile.data_path == path
    assert result.data_profile.n_total_observations == 60
    assert result.data_profile.frequency == "D"
    assert result.data_profile.start_date == "2023-01-01"
    assert result.data_profile.target_stats["y"]["mean"] == pytest.approx(
        df_dialect["y"].mean(), abs=1e-9
    )


@pytest.mark.parametrize(
    "sep, decimal, expected",
    [(";", None, (";", ",")), (None, ",", (";", ",")), (";", ",", (";", ","))],
    ids=["sep", "decimal", "both"],
)
def test_profile_output_when_sep_or_decimal_given(tmp_path, sep, decimal, expected):
    """
    Test that the `sep` and `decimal` of profile() are recorded, and the one
    not given is detected.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")

    result = ForecastingAssistant().profile(path, target="y", sep=sep, decimal=decimal)

    assert (result.data_profile.csv_sep, result.data_profile.csv_decimal) == expected


def test_profile_sep_and_decimal_are_ignored_for_data_in_memory():
    """
    Test that a DataFrame is profiled with the default dialect whatever
    `sep` and `decimal` say, because there is no file to read.
    """
    result = ForecastingAssistant().profile(
        df_dialect.assign(date=pd.to_datetime(df_dialect["date"])),
        target="y",
        sep=";",
        decimal=",",
    )

    assert result.data_profile.csv_sep == ","
    assert result.data_profile.csv_decimal == "."
    assert result.data_profile.data_path == "data.csv"


@pytest.mark.parametrize(
    "sep, decimal, message, field",
    [
        (
            "|",
            None,
            "`sep` must be ',', ';' or a tabulator ('\\t'), got '|'.",
            "sep",
        ),
        (None, "x", "`decimal` must be '.' or ',', got 'x'.", "decimal"),
        (
            ",",
            ",",
            "`decimal` cannot be ',' when `sep` is ',': the same character "
            "would separate the fields and the decimals.",
            "decimal",
        ),
    ],
    ids=["sep", "decimal", "decimal comma with sep comma"],
)
def test_profile_InvalidInputError_when_sep_or_decimal_not_valid(
    tmp_path, sep, decimal, message, field
):
    """
    Test that profile() raises InvalidInputError naming the argument when
    `sep` or `decimal` is not valid, or when the decimal mark is the
    separator.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")

    with pytest.raises(InvalidInputError, match=re.escape(message)) as exc_info:
        ForecastingAssistant().profile(path, target="y", sep=sep, decimal=decimal)

    assert exc_info.value.field == field


def test_profile_InvalidInputError_when_separator_of_the_file_is_ambiguous(tmp_path):
    """
    Test that a file whose separator cannot be told raises an
    InvalidInputError with the code 'data_unreadable', the field 'data' and a
    hint that names `sep` and `decimal`; giving `sep` reads it.
    """
    path = tmp_path / "ambiguous.csv"
    df_dialect.rename(columns={"y": "y,x"}).to_csv(
        path, sep=";", decimal=",", index=False
    )
    assistant = ForecastingAssistant()

    err_msg = re.escape(
        f"The separator of the CSV file '{path}' cannot be told: its header "
        f"reads with ',' (2 columns) and ';' (2 columns)."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        assistant.profile(path, target="y,x")
    result = assistant.profile(path, target="y,x", sep=";")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Profile the file saying how it is written, with `sep` (',', ';' or "
        "a tabulator) and `decimal` ('.' or ',') in `profile()`, `--sep` and "
        "`--decimal` in the `profile` command, or `sep` and `decimal` in the "
        "`profile` tool of the MCP server, and use that profile."
    )
    assert result.data_profile.csv_sep == ";"
    assert result.data_profile.csv_decimal == ","


def test_profile_InvalidInputError_when_decimal_of_the_file_is_ambiguous(tmp_path):
    """
    Test that numbers written with ',' and with '.' raise an
    InvalidInputError with the code 'data_unreadable', and that giving
    `decimal` reads the file.
    """
    path = tmp_path / "ambiguous.csv"
    path.write_text(
        "date;y;z\n"
        + "".join(f"2023-01-{day:02d};{day},5;{day}.25\n" for day in range(1, 29))
    )
    assistant = ForecastingAssistant()

    err_msg = re.escape(
        f"The decimal mark of the CSV file '{path}' cannot be told: it holds "
        f"numbers written with ',' (such as '1,5') and with '.' (such as "
        f"'1.25')."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        assistant.profile(path, target="z")
    result = assistant.profile(path, target="z", decimal=".")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert result.data_profile.csv_decimal == "."


def test_profile_output_of_a_comma_csv_is_unchanged_by_the_dialect_fields(tmp_path):
    """
    Test that a comma CSV records the default dialect and that the profile
    of its file dumps as the profile of the same frame in memory does but for
    the path: the dialect fields are the only addition.
    """
    path = tmp_path / "us.csv"
    df_dialect.to_csv(path, index=False)
    in_memory = df_dialect.assign(date=pd.to_datetime(df_dialect["date"]))
    assistant = ForecastingAssistant()

    from_file = assistant.profile(path, target="y").data_profile.model_dump()
    expected = assistant.profile(in_memory, target="y").data_profile.model_dump()

    assert from_file["csv_sep"] == ","
    assert from_file["csv_decimal"] == "."
    assert from_file["data_path"] == str(path)
    assert expected["data_path"] == "data.csv"
    assert expected["csv_sep"] == ","
    assert expected["csv_decimal"] == "."
    for name in ("data_path", "index_type", "date_column"):
        del from_file[name], expected[name]
    assert from_file == expected


def test_profile_InvalidInputError_when_sep_not_valid_for_data_in_memory():
    """
    Test that an invalid `sep` or `decimal` raises also for a DataFrame,
    where valid values are ignored.
    """
    data = df_dialect.assign(date=pd.to_datetime(df_dialect["date"]))

    err_msg = re.escape("`sep` must be ',', ';' or a tabulator ('\\t'), got 'x'.")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data, target="y", sep="x")

    assert exc_info.value.field == "sep"


@pytest.mark.parametrize(
    "decimals, expected",
    [
        (True, {"min": 870.0, "max": 2048.71, "mean": 1458.6779166666665}),
        (False, {"min": 870.0, "max": 2049.0, "mean": 1458.7083333333333}),
    ],
    ids=["thousands and decimal comma", "whole numbers with and without separator"],
)
def test_profile_records_the_thousands_separator_of_the_csv_file(
    tmp_path, decimals, expected
):
    """
    Test that profile() reads a ';' file with '.' between thousands as the
    amounts it holds and records ';', ',' and '.' as its dialect.
    """
    path = write_thousands(tmp_path, df_dialect_thousands, decimals=decimals)

    result = ForecastingAssistant().profile(path, target="y")

    data_profile = result.data_profile
    assert (data_profile.csv_sep, data_profile.csv_decimal) == (";", ",")
    assert data_profile.csv_thousands == "."
    assert data_profile.target_dtype == "numeric"
    for name, value in expected.items():
        assert data_profile.target_stats["y"][name] == pytest.approx(value)


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"thousands": "."}, (",", ".", [1870.0, 1020.0])),
        ({"decimal": ","}, (",", ".", [1870.0, 1020.0])),
        ({"decimal": "."}, (".", None, [1.87, 1.02])),
    ],
    ids=["thousands", "decimal comma", "decimal point"],
)
def test_profile_output_when_thousands_ambiguous_and_dialect_given(
    tmp_path, kwargs, expected
):
    """
    Test that a file whose numbers all read both as thousands and as three
    decimals raises an InvalidInputError with the code 'data_unreadable',
    and that profile() reads it as the caller says: `thousands` '.' or
    `decimal` ',' as thousands, `decimal` '.' as three decimals. A decimal
    mark ',' given that reads '1.870' as text no longer leaves the target as
    text.
    """
    path = tmp_path / "thousands.csv"
    path.write_text(
        "date;y\n" + "".join(
            f"2020-{month:02d}-01;{'1.870' if month % 2 else '1.020'}\n"
            for month in range(1, 13)
        )
    )
    decimal, thousands, values = expected
    assistant = ForecastingAssistant()

    err_msg = re.escape(
        f"The thousands separator of the CSV file '{path}' cannot be told: its "
        f"numbers with a '.' (such as '1.870') read both as thousands and as "
        f"numbers with three decimals."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        assistant.profile(path, target="y")
    result = assistant.profile(path, target="y", **kwargs)

    assert exc_info.value.code == "data_unreadable"
    assert result.data_profile.csv_decimal == decimal
    assert result.data_profile.csv_thousands == thousands
    assert result.data_profile.target_dtype == "numeric"
    assert result.data_profile.target_stats["y"]["max"] == pytest.approx(values[0])
    assert result.data_profile.target_stats["y"]["min"] == pytest.approx(values[1])


def test_profile_thousands_is_ignored_for_data_in_memory():
    """
    Test that a DataFrame is profiled without thousands separator whatever
    `thousands` says, because there is no file to read.
    """
    result = ForecastingAssistant().profile(
        df_dialect.assign(date=pd.to_datetime(df_dialect["date"])),
        target="y",
        thousands=".",
    )

    assert result.data_profile.csv_thousands is None
    assert result.data_profile.csv_decimal == "."


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"thousands": ","}, "`thousands` must be '.', got ','."),
        (
            {"thousands": ".", "decimal": "."},
            "`thousands` cannot be '.' when `decimal` is '.': the same "
            "character would separate the thousands and the decimals.",
        ),
    ],
    ids=["comma", "with decimal point"],
)
def test_profile_InvalidInputError_when_thousands_not_valid(tmp_path, kwargs, message):
    """
    Test that profile() raises InvalidInputError naming `thousands` when it
    is not '.', or when it is the decimal mark.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")

    with pytest.raises(InvalidInputError, match=re.escape(message)) as exc_info:
        ForecastingAssistant().profile(path, target="y", **kwargs)

    assert exc_info.value.field == "thousands"


def test_profile_reads_thousands_of_a_series_after_the_sample(tmp_path, monkeypatch):
    """
    Test that a long-format ';' file sorted by series, whose first series
    holds amounts below 1,000 in the lines the dialect is told from and
    whose second series holds amounts written as '1.020' after them, is
    profiled with '.' as thousands separator and the amounts of both series.
    """
    monkeypatch.setattr("skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 400)
    dates = pd.date_range("2020-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
    path = tmp_path / "long.csv"
    path.write_text(
        "series;date;y\n"
        + "".join(f"a;{date};{800 + i}\n" for i, date in enumerate(dates))
        + "".join(f"b;{date};1.{100 + i}\n" for i, date in enumerate(dates))
    )
    assert len(path.read_bytes()) > 400

    result = ForecastingAssistant().profile(
        path, target="y", series_id_column="series"
    )

    data_profile = result.data_profile
    assert data_profile.csv_thousands == "."
    assert data_profile.target_stats["a"]["max"] == 829.0
    assert data_profile.target_stats["b"]["min"] == 1100.0
    assert data_profile.target_stats["b"]["max"] == 1129.0


def test_profile_InvalidInputError_when_target_list_and_multiindex():
    """
    Test that profile() of data indexed by a `(series_id, date)` MultiIndex
    with a list of targets raises with the field 'target', not about the
    `series_id_column` that the first level fills and the caller did not
    pass, and that the name of the column of values still profiles them.
    """
    data = df_items_sales_long.set_index(["series", "date"])
    err_msg = re.escape(
        "`target` is a list of columns (['value']), but `data` is indexed by "
        "a MultiIndex (levels ['series', 'date']), which is long format: the "
        "series are stacked in rows, told apart by the first level. Pass "
        "`target` as the name of the column of values, not as a list."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        ForecastingAssistant().profile(data=data, target=["value"])

    assert exc_info.value.field == "target"
    profile = ForecastingAssistant().profile(data=data, target="value")
    assert profile.data_profile.data_format == "long"
    assert profile.data_profile.n_series == 3
