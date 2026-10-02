# Unit test validate_future_exog

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.preprocessing import reshape_exog_long_to_dict

from skforecast_ai import ForecastingAssistant
from skforecast_ai._future_exog import used_exog_columns, validate_future_exog
from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.execution.forecast_runner import (
    exog_as_injected,
    render_forecast_script,
)

from tests.fixtures_future_exog import (
    data_bh,
    data_business,
    data_daily,
    data_dst,
    data_long,
    data_long_early,
    data_long_single,
    data_range,
    data_wide,
    data_wide_closed,
    data_wide_kind,
    exog_bh,
    exog_calendar_days,
    exog_daily,
    exog_dst,
    exog_long,
    exog_long_early,
    exog_range,
    exog_wide,
    plan_bh,
    plan_business,
    plan_business_lgbm,
    plan_daily_lgbm,
    plan_daily_ridge,
    plan_dst,
    plan_long_early_foundation,
    plan_long_early_ridge,
    plan_long_ridge,
    plan_long_single,
    plan_range_ridge,
    plan_wide_kind,
    plan_wide_ridge,
    plans_daily_by_forecaster,
    profile_bh,
    profile_business,
    profile_daily,
    profile_dst,
    profile_long,
    profile_long_early,
    profile_long_single,
    profile_range,
    profile_wide,
    profile_wide_kind,
)


def _with_dates(exog: pd.DataFrame, dates: list) -> pd.DataFrame:
    """Return `exog` indexed by `dates`."""
    return exog.set_axis(pd.DatetimeIndex(dates))


@pytest.mark.parametrize(
    "exog, err_msg",
    [
        (
            exog_daily[["promo"]],
            "`exog` has no column 'weekday'. The future exogenous variables must "
            "hold the columns ['promo', 'weekday'] that the plan uses.",
        ),
        (
            pd.concat([exog_daily, exog_daily[["promo"]]], axis=1),
            "`exog` has repeated column names: 'promo'.",
        ),
    ],
    ids=["missing_column", "repeated_column"],
)
def test_validate_future_exog_InvalidInputError_when_columns_wrong(exog, err_msg):
    """
    Test that a column the plan uses that is missing, or a repeated column
    name, raises before the generated code fails on them.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        validate_future_exog(exog, data_daily, profile_daily, plan_daily_ridge)

    assert exc_info.value.field == "exog"


@pytest.mark.parametrize(
    "exog, err_msg",
    [
        (
            _with_dates(exog_daily, [
                "2023-04-11", "2023-04-12", None, "2023-04-14", "2023-04-15",
                "2023-04-16", "2023-04-17",
            ]),
            "`exog` has 1 row(s) without a date, at row position(s) 2: every "
            "row needs a date.",
        ),
        (
            exog_daily.tz_localize("UTC"),
            "The dates of `exog` have the time zone UTC, those of the data None: "
            "use the time zone of the data.",
        ),
        (
            _with_dates(exog_daily, [
                "2023-04-11", "2023-04-12", "2023-04-13", "2023-04-13",
                "2023-04-15", "2023-04-16", "2023-04-17",
            ]),
            "`exog` repeats dates: '2023-04-13'. Every date must appear once.",
        ),
        (
            exog_daily.set_axis(exog_daily.index - pd.Timedelta(days=1)),
            "`exog` starts at 2023-04-10, before the first date to forecast, "
            "2023-04-11 (the date after the last date of the data). Drop the "
            "rows before it.",
        ),
        (
            exog_daily.drop(index=exog_daily.index[3]),
            "`exog` has no row for 1 of the 7 dates to forecast, such as "
            "2023-04-14. It must hold the dates from 2023-04-11 to 2023-04-17 "
            "at frequency 'D'.",
        ),
        (
            pd.concat([
                exog_daily,
                _with_dates(exog_daily.iloc[[2]], ["2023-04-13 12:00"]),
            ]),
            "`exog` has dates off the grid of frequency 'D' among the dates to "
            "forecast, such as 2023-04-13 12:00:00: the generated code drops "
            "them. Give one row per date to forecast.",
        ),
    ],
    ids=["missing_date", "time_zone", "repeated_date", "starts_early", "gap",
         "off_grid"],
)
def test_validate_future_exog_InvalidInputError_when_dates_wrong(exog, err_msg):
    """
    Test that dates the generated code would turn into missing values, drop
    or fail on raise: a row without a date, another time zone, a repeated
    date, a start before the first date to forecast, a missing date to
    forecast and a date off the daily grid.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        validate_future_exog(exog, data_daily, profile_daily, plan_daily_ridge)

    assert exc_info.value.field == "exog"


def test_validate_future_exog_InvalidInputError_when_day_first_dates():
    """
    Test that the missing values are dated as the generated code reads the
    dates (day first, guessed from the first date, 17/04/2023), not read
    again on their own (12/04/2023 alone reads as 4 December).
    """
    exog = (
        exog_daily.assign(promo=[0.0, np.nan, 0.0, 1.0, 0.0, 1.0, 0.0])
        .rename_axis("date")
        .reset_index()
        .assign(date=lambda frame: frame["date"].dt.strftime("%d/%m/%Y"))
        .iloc[::-1]
    )

    err_msg = re.escape(
        "`exog` has missing values in the rows to forecast ('promo': 1 "
        "value(s), such as '2023-04-12')."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data_daily, profile_daily, plan_daily_ridge)


@pytest.mark.parametrize(
    "exog, data, profile, plan, err_msg",
    [
        (
            exog_wide.set_axis(exog_wide.index + pd.Timedelta(days=2)),
            data_wide, profile_wide, plan_wide_ridge,
            "`exog` has no row for 2 of the 7 dates to forecast, such as "
            "2012-04-28. It must hold the dates from 2012-04-28 to 2012-05-04 "
            "at frequency 'D'.",
        ),
        (
            exog_dst.set_axis(
                pd.date_range("2021-03-29", periods=7, freq="D", tz="Europe/Madrid")
            ),
            data_dst, profile_dst, plan_dst,
            "`exog` starts at 2021-03-29, before the first date to forecast, "
            "2021-03-29 01:00:00+02:00 (the date after the last date of the "
            "data).",
        ),
        (
            exog_dst.set_axis(
                pd.date_range("2021-03-26", periods=7, freq="D", tz="Europe/Madrid")
                .tz_convert("UTC")
            ),
            data_dst.loc[:"2021-03-25"], profile_dst, plan_dst,
            "The dates of `exog` have the time zone UTC, those of the data "
            "Europe/Madrid: use the time zone of the data.",
        ),
    ],
    ids=["multiseries_last_value_before_last_row", "daylight_saving_last_day",
         "other_time_zone_across_daylight_saving_change"],
)
def test_validate_future_exog_InvalidInputError_when_dates_or_values_of_skforecast(
    exog, data, profile, plan, err_msg
):
    """
    Test the dates as skforecast reads them: ForecasterRecursiveMultiSeries
    forecasts from the last date with a target value (the exog of the last
    row of the data starts two days late), a forecast after a daylight
    saving time change starts 24 hours after the last date (01:00, not
    midnight), and daily exog in another time zone across a daylight saving
    time change, whose grid of days (asfreq in its own zone) moves by an
    hour after the change.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        validate_future_exog(exog, data, profile, plan)


@pytest.mark.parametrize(
    "exog, data, profile, plan, err_msg",
    [
        (
            exog_long.assign(
                date=exog_long["date"].astype("datetime64[s]"),
                price=[np.nan, *exog_long["price"][1:]],
            ),
            data_long, profile_long, plan_long_ridge,
            "`exog` has missing values in the rows to forecast ('price': 1 "
            "value(s), series 'item_1').",
        ),
        (
            exog_wide.assign(kind=["zz", "a", "b", "a", "b", "a", "b"]),
            data_wide_kind, profile_wide_kind, plan_wide_kind,
            "`exog` column 'kind' holds categories that the data has not: 'zz'.",
        ),
        (
            exog_daily.astype({"promo": object}).assign(
                promo=[0.0, pd.NA, 0.0, 1.0, 0.0, 1.0, 0.0]
            ),
            data_daily, profile_daily, plan_daily_lgbm,
            "`exog` column 'promo' holds pd.NA (dtype object), which the "
            "forecaster cannot read",
        ),
        (
            exog_daily.assign(
                promo=pd.array([0.0, None, 0.0, 1.0, 0.0, 1.0, 0.0], dtype="Float64")
            ),
            data_daily, profile_daily, plan_daily_lgbm,
            "`exog` column 'promo' holds pd.NA (dtype Float64), which the "
            "forecaster cannot read",
        ),
        (
            exog_daily.assign(promo=pd.Timestamp("2020-01-01")),
            data_daily, profile_daily, plan_daily_ridge,
            "`exog` column 'promo' holds dates or durations, such as "
            "Timestamp('2020-01-01 00:00:00'), but it holds numbers in the data.",
        ),
        (
            exog_daily.assign(promo=[[1.0]] * 7),
            data_daily, profile_daily, plan_daily_ridge,
            "`exog` column 'promo' holds values that are not single values, "
            "such as [1.0].",
        ),
    ],
    ids=["long_dates_in_seconds", "category_only_in_rows_without_target",
         "pd_na_object_lightgbm", "pd_na_nullable_with_categories_lightgbm",
         "timestamps_for_numbers", "lists_in_cells"],
)
def test_validate_future_exog_InvalidInputError_when_values_read_by_skforecast(
    exog, data, profile, plan, err_msg
):
    """
    Test value checks that depend on how skforecast reads the values: dates
    in seconds are compared with those to forecast (the missing value is
    found), ForecasterRecursiveMultiSeries encodes only the categories of
    the rows with a target value, pd.NA makes skforecast fail even with
    LightGBM (in a column of objects, or next to a categorical column),
    timestamps are not numbers (pandas would read them as
    nanoseconds), and a list in a cell raises instead of a `TypeError`.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        validate_future_exog(exog, data, profile, plan)


def test_validate_future_exog_InvalidInputError_when_other_zone_month_starts():
    """
    Test that, for a calendar frequency (month starts), the future exog in
    another time zone raises even with the same instants: the generated code
    puts it on the grid of month starts of its own zone, which drops them.
    """
    profile = profile_dst.model_copy(update={"frequency": "MS"})
    exog = exog_dst.set_axis(
        pd.date_range("2021-04-01", periods=7, freq="MS", tz="Europe/Madrid")
        .tz_convert("UTC")
    )

    err_msg = re.escape(
        "The dates of `exog` have the time zone UTC, those of the data "
        "Europe/Madrid: use the time zone of the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data_dst, profile, plan_dst)


@pytest.mark.parametrize(
    "exog, plan, err_msg",
    [
        (
            pd.concat([
                exog_long,
                exog_long.iloc[[0]].assign(date=pd.Timestamp("2012-04-29 12:00")),
            ], ignore_index=True),
            plan_long_ridge,
            "`exog` starts at 2012-04-29 12:00:00 for series 'item_1', off the "
            "grid of frequency 'D' of the dates to forecast: the generated code "
            "puts the rows on the grid that starts at the first row, which leaves "
            "out the dates to forecast, such as 2012-04-30. Drop the rows before "
            "2012-04-30.",
        ),
        (
            exog_long.assign(series=exog_long["series"].astype("category")).astype(
                {"series": object}
            ).assign(series=lambda frame: frame["series"].str.replace("item_", "")),
            plan_long_ridge,
            "`exog` has no rows for 3 series of the data",
        ),
        (
            pd.concat([
                exog_long,
                exog_long.iloc[[0, 0]].assign(series="item_9"),
            ], ignore_index=True),
            plan_long_ridge,
            "`exog` repeats dates of series 'item_9': '2012-04-30'.",
        ),
        (
            pd.concat([exog_long, exog_long[["series"]]], axis=1),
            plan_long_ridge,
            "`exog` has repeated column names: 'series'.",
        ),
    ],
    ids=["off_grid_row_before_dates_to_forecast", "series_absent",
         "repeated_dates_of_other_series", "repeated_series_id_column"],
)
def test_validate_future_exog_InvalidInputError_when_long_grid_wrong(
    exog, plan, err_msg
):
    """
    Test long-format checks of the grid the reshape of each series builds:
    a row off the grid before the dates to forecast (allowed before them)
    moves the grid that starts at the first row, so the dates to forecast
    fall off it; repeated dates of a series the forecaster does not predict
    still make the reshape fail; a repeated series id column raises as
    such.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        validate_future_exog(exog, data_long, profile_long, plan)


def test_validate_future_exog_InvalidInputError_when_long_history_across_dst():
    """
    Test that long-format exog in another time zone with rows of history
    before a daylight saving time change raises: the reshape builds the grid
    of days from the first row in that zone, which moves by an hour after
    the change, so the dates to forecast (in UTC) fall off it.
    """
    data = data_long.assign(date=data_long["date"].dt.tz_localize("UTC"))
    profile = ForecastingAssistant().profile(
        data, target="value", date_column="date", series_id_column="series"
    ).data_profile
    history = pd.DataFrame({
        "series": "item_1",
        "date": pd.date_range("2012-03-20", "2012-04-29", freq="D", tz="UTC"),
        "price": 1.0,
    })
    exog = pd.concat([
        history, exog_long.assign(date=exog_long["date"].dt.tz_localize("UTC"))
    ], ignore_index=True).assign(
        date=lambda frame: frame["date"].dt.tz_convert("Europe/Madrid")
    )

    err_msg = re.escape(
        "The dates of `exog` have the time zone Europe/Madrid, those of the "
        "data UTC: use the time zone of the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data, profile, plan_long_ridge)


def test_validate_future_exog_InvalidInputError_when_foundation_ids_of_another_type():
    """
    Test that, for a ForecasterFoundation model, which takes a series without
    future values, series ids of another type than those of the data still
    raise with the hint, instead of leaving every series without its future
    values.
    """
    data = data_long_early.assign(series=data_long_early["series"].str[-1])
    profile = ForecastingAssistant().profile(
        data, target="value", date_column="date", series_id_column="series"
    ).data_profile
    exog = exog_long_early.assign(
        series=exog_long_early["series"].str[-1].astype(int)
    )

    err_msg = re.escape(
        "The ids of `exog` are of another type (int64) than those of the data: "
        "use the same type."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data, profile, plan_long_early_foundation)


def test_validate_future_exog_InvalidInputError_when_pd_na_and_column_of_objects():
    """
    Test that pd.NA of a nullable numeric dtype raises with LightGBM when
    another column of the future exog holds objects: skforecast then reads
    the exog as objects and fails on pd.NA.
    """
    data = data_business.assign(z=np.arange(60.0) % 4)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data, target="y")
    plan = assistant.plan(profile, steps=7, estimator="LGBMRegressor")
    exog = exog_calendar_days.assign(
        x=pd.array([0.0, 1.0, None] + [1.0] * 8, dtype="Float64"),
        z=pd.Series([1.0] * 11, dtype=object).to_numpy(),
    )

    err_msg = re.escape(
        "`exog` column 'x' holds pd.NA (dtype Float64), which the forecaster "
        "cannot read"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data, profile.data_profile, plan)


def test_validate_future_exog_InvalidInputError_when_index_not_dates():
    """
    Test that future exogenous variables of data indexed by date must be
    indexed by date too: text dates in the index became missing values.
    """
    exog = exog_calendar_days.set_axis(
        exog_calendar_days.index.strftime("%Y-%m-%d")
    )

    err_msg = re.escape(
        "The dates of `exog` must be its index, a pandas DatetimeIndex, as in "
        "the data; its index is Index."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data_business, profile_business, plan_business)


@pytest.mark.parametrize(
    "exog, plan, err_msg",
    [
        (
            exog_daily.assign(weekday=["Funday", *exog_daily["weekday"][1:]]),
            plan_daily_ridge,
            "`exog` column 'weekday' holds categories that the data has not: "
            "'Funday'. The data has 'Friday', 'Monday', 'Saturday', 'Sunday', "
            "'Thursday' and 2 more; the forecaster cannot use a new category.",
        ),
        (
            exog_daily.assign(weekday=range(7)),
            plan_daily_ridge,
            "`exog` column 'weekday' holds numbers, but it holds text in the data "
            "(categories such as 'Sunday', 'Monday', 'Tuesday', 'Wednesday', "
            "'Thursday' and 2 more).",
        ),
        (
            exog_daily.assign(promo=["n/a", *exog_daily["promo"][1:]]),
            plan_daily_ridge,
            "`exog` column 'promo' holds values that are not numbers, such as "
            "'n/a', but it holds numbers in the data.",
        ),
        (
            exog_daily.assign(promo=[np.inf, *exog_daily["promo"][1:]]),
            plan_daily_ridge,
            "`exog` column 'promo' holds infinite values, which "
            "ForecasterRecursive with Ridge cannot use.",
        ),
        (
            exog_daily.assign(promo=[np.nan, *exog_daily["promo"][1:]]),
            plan_daily_ridge,
            "`exog` has missing values in the rows to forecast ('promo': 1 "
            "value(s), such as '2023-04-11'). ForecasterRecursive with Ridge "
            "cannot use them, so its predictions would be missing: fill them in.",
        ),
        (
            exog_daily.assign(weekday=np.nan),
            plan_daily_lgbm,
            "`exog` column 'weekday' has no value in the rows to forecast; the "
            "forecaster cannot encode it.",
        ),
    ],
    ids=["new_category", "numbers_for_categories", "text_for_numbers",
         "infinite_ridge", "missing_ridge", "categories_all_missing"],
)
def test_validate_future_exog_InvalidInputError_when_values_wrong(
    exog, plan, err_msg
):
    """
    Test that values the forecaster would read as missing or fail on raise:
    a new category, numbers for a categorical variable, text for a numeric
    one, infinite and missing values with Ridge, and a categorical variable
    without values (LightGBM fails to encode it).
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        validate_future_exog(exog, data_daily, profile_daily, plan)


def test_validate_future_exog_InvalidInputError_when_column_not_in_data():
    """
    Test that a column the profile records and the data passed has not (a
    profile built from other data) is checked for its missing values, with
    Ridge an error, instead of a `KeyError` on the data.
    """
    exog = exog_daily.assign(promo=[np.nan, *exog_daily["promo"][1:]])

    err_msg = re.escape(
        "`exog` has missing values in the rows to forecast ('promo': 1 "
        "value(s), such as '2023-04-11'). ForecasterRecursive with Ridge "
        "cannot use them, so its predictions would be missing: fill them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(
            exog, data_daily.drop(columns="promo"), profile_daily, plan_daily_ridge
        )


def test_validate_future_exog_InvalidInputError_when_data_without_dates():
    """
    Test that, for data without dates (RangeIndex), the first `steps` rows
    in the order of the index, those skforecast reads, are checked: a
    missing value with Ridge raises, naming its index, where the forecast
    gave missing predictions without an error.
    """
    exog = exog_range.assign(x=[0.0, np.nan, 2.0, 3.0, 4.0, 5.0, 6.0]).iloc[::-1]

    err_msg = re.escape(
        "`exog` has missing values in the rows to forecast ('x': 1 value(s), "
        "at index 61). ForecasterRecursive with Ridge cannot use them, so its "
        "predictions would be missing: fill them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data_range, profile_range, plan_range_ridge)


@pytest.mark.parametrize(
    "exog, err_msg",
    [
        (
            exog_long[exog_long["series"] != "item_3"],
            "`exog` has no rows for 1 series of the data: 'item_3'.",
        ),
        (
            exog_long.drop(index=8),
            "`exog` has no row of series 'item_2' for 1 of the 7 dates to "
            "forecast, such as 2012-05-01.",
        ),
        (
            exog_long.assign(date=exog_long["date"].dt.strftime("%Y-%m-%d")),
            "The dates of `exog` (column 'date') are text: convert them with "
            "pandas.to_datetime first.",
        ),
        (
            exog_long.drop(columns="series"),
            "`exog` has no column 'series'. The future exogenous variables must "
            "hold the columns ['price'] that the plan uses, with the series id "
            "column 'series' and the date column 'date'.",
        ),
        (
            exog_long.set_index(["series", "date"]).rename_axis(["series", "day"]),
            "`exog` has no column 'date'. The future exogenous variables must "
            "hold the columns ['price'] that the plan uses, with the series id "
            "column 'series' and the date column 'date'.",
        ),
        (
            exog_long.assign(price=[np.nan, *exog_long["price"][1:]]),
            "`exog` has missing values in the rows to forecast ('price': 1 "
            "value(s), series 'item_1').",
        ),
    ],
    ids=["missing_series", "series_with_gap", "text_dates", "no_series_id",
         "no_date_column", "missing_value"],
)
def test_validate_future_exog_InvalidInputError_when_long_exog_wrong(exog, err_msg):
    """
    Test that long-format future exogenous variables must hold every series
    of the data with its dates to forecast, dates as dates (the generated
    code does not parse them), the series id column and the date column (a
    level named otherwise is not it), and that a missing value names its
    series.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        validate_future_exog(exog, data_long, profile_long, plan_long_ridge)


def test_validate_future_exog_InvalidInputError_when_long_ids_of_another_type():
    """
    Test that long-format future exogenous variables whose series ids are
    numbers, where the data has them as text, raise with a hint on the type.
    """
    data = data_long.assign(series=data_long["series"].str[-1])
    profile = ForecastingAssistant().profile(
        data, target="value", date_column="date", series_id_column="series"
    ).data_profile
    exog = exog_long.assign(series=exog_long["series"].str[-1].astype(int))

    err_msg = re.escape(
        "`exog` has no rows for 3 series of the data: '1', '2', '3'. The ids of "
        "`exog` are of another type (int64) than those of the data: use the same "
        "type."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_future_exog(exog, data, profile, plan_long_ridge)


@pytest.mark.parametrize(
    "exog, data, err_msg",
    [
        (
            exog_long, data_long_early,
            "`exog` has no row of series 'item_3' for 3 of the 7 dates to "
            "forecast, such as 2012-04-27. It must hold the dates from "
            "2012-04-27 to 2012-05-03 at frequency 'D'.",
        ),
    ],
    ids=["dates_of_data"],
)
def test_validate_future_exog_InvalidInputError_when_foundation_series_ends_early(
    exog, data, err_msg
):
    """
    Test that a ForecasterFoundation model, which predicts a series that ends
    before the others from its own last date, needs the future exogenous
    variables of that series, from the date after it: at the dates that
    follow the last date of the data, the model fills the first three with
    missing values.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        validate_future_exog(
            exog, data, profile_long_early, plan_long_early_foundation
        )


def test_validate_future_exog_UserWarning_when_missing_values_and_lightgbm():
    """
    Test that a missing value with LightGBM, which tolerates missing values,
    only warns (the forecast runs as before) and says where it is.
    """
    exog = exog_daily.assign(promo=[np.nan, *exog_daily["promo"][1:]])

    warn_msg = re.escape(
        "`exog` has missing values in the rows to forecast ('promo': 1 value(s), "
        "such as '2023-04-11'). LGBMRegressor treats them as missing values; "
        "check that they are meant to be missing."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_future_exog(exog, data_daily, profile_daily, plan_daily_lgbm)


@pytest.mark.parametrize(
    "exog, data, profile, plan",
    [
        (
            exog_calendar_days.assign(
                x=pd.array([0.0, 1.0, None] + [1.0] * 8, dtype="Float64")
            ),
            data_business, profile_business, plan_business_lgbm,
        ),
        (
            exog_daily.assign(
                weekday=np.full(7, None, dtype=object),
                promo=[0.0, np.nan, 0.0, 1.0, 0.0, 1.0, 0.0],
            ),
            data_daily, profile_daily, plan_daily_lgbm,
        ),
    ],
    ids=["nullable_float_pd_na", "categories_all_missing_as_objects"],
)
def test_validate_future_exog_UserWarning_when_missing_values_read_as_nan(
    exog, data, profile, plan
):
    """
    Test that, with LightGBM, `pd.NA` of a nullable numeric dtype in numeric
    exog (which skforecast reads as NaN) and a categorical column of objects
    without any value in the rows to forecast (which the encoder reads as
    missing) only warn, as missing values do.
    """
    warn_msg = re.escape("`exog` has missing values in the rows to forecast (")
    with pytest.warns(UserWarning, match=warn_msg):
        validate_future_exog(exog, data, profile, plan)


def test_validate_future_exog_UserWarning_when_new_category_and_lightgbm():
    """
    Test that a new category with LightGBM, which the encoder reads as a
    missing value that LightGBM tolerates, warns instead of raising.
    """
    exog = exog_daily.assign(weekday=["Funday", *exog_daily["weekday"][1:]])

    warn_msg = re.escape(
        "`exog` holds categories that the data has not ('weekday': 'Funday'). "
        "LGBMRegressor reads them as missing values; check them."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_future_exog(exog, data_daily, profile_daily, plan_daily_lgbm)


def test_validate_future_exog_UserWarning_when_missing_values_and_foundation():
    """
    Test that a missing value with a foundation model warns without saying
    that the model treats it as missing (some backends reject it).
    """
    exog = exog_daily.assign(promo=[np.nan, *exog_daily["promo"][1:]])

    warn_msg = re.escape(
        "`exog` has missing values in the rows to forecast ('promo': 1 value(s), "
        "such as '2023-04-11'). autogluon/chronos-2-small receives them as they "
        "are; check that they are meant to be missing."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_future_exog(
            exog, data_daily, profile_daily, plans_daily_by_forecaster["foundation"]
        )


def test_validate_future_exog_UserWarning_when_infinite_values_and_lightgbm():
    """
    Test that an infinite value with LightGBM, which does not reject it,
    warns instead of passing without a word.
    """
    exog = exog_daily.assign(promo=[np.inf, *exog_daily["promo"][1:]])

    warn_msg = re.escape(
        "`exog` column(s) 'promo' hold infinite values in the rows to forecast, "
        "which LGBMRegressor receives as they are; check that they are meant to "
        "be there."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_future_exog(exog, data_daily, profile_daily, plan_daily_lgbm)


@pytest.mark.parametrize(
    "exog, data, profile, plan",
    [
        pytest.param(
            exog_daily, data_daily, profile_daily, plan_daily_ridge, id="valid"
        ),
        pytest.param(
            pd.concat([exog_daily, exog_daily[["promo"]].set_axis(
                ["note"], axis=1
            ), exog_daily[["promo"]].set_axis(["note"], axis=1)], axis=1),
            data_daily, profile_daily, plan_daily_ridge,
            id="repeated_column_not_used",
        ),
        pytest.param(
            pd.concat([
                exog_daily,
                _with_dates(exog_daily.iloc[[0]], ["2023-04-18"]),
            ]).assign(other=1.0).iloc[::-1],
            data_daily, profile_daily, plan_daily_ridge,
            id="extra_column_more_rows_unsorted",
        ),
        pytest.param(
            exog_daily.set_axis(exog_daily.index.strftime("%Y-%m-%d")),
            data_daily, profile_daily, plan_daily_ridge,
            id="text_dates_for_date_column",
        ),
        pytest.param(
            exog_daily.rename_axis("date").reset_index(),
            data_daily, profile_daily, plan_daily_ridge,
            id="date_column",
        ),
        pytest.param(
            exog_calendar_days, data_business, profile_business, plan_business,
            id="calendar_days_for_business_days",
        ),
        pytest.param(
            exog_calendar_days.set_axis(
                [date.date() for date in exog_calendar_days.index]
            ),
            data_business, profile_business, plan_business,
            id="python_dates_index",
        ),
        pytest.param(
            exog_dst, data_dst, profile_dst, plan_dst,
            id="daylight_saving_last_day",
        ),
        pytest.param(
            exog_dst.tz_convert("UTC"), data_dst, profile_dst, plan_dst,
            id="same_instants_other_time_zone_daily",
        ),
        pytest.param(
            exog_dst.tz_convert("dateutil/Europe/Madrid"),
            data_dst, profile_dst, plan_dst,
            id="same_time_zone_other_name",
        ),
        pytest.param(
            pd.DataFrame(
                {"x": np.arange(7.0)},
                index=pd.date_range(
                    "2022-01-01", periods=7, freq="MS", tz="UTC"
                ).tz_convert("Asia/Kolkata"),
            ),
            pd.DataFrame(
                {"y": np.arange(24.0), "x": np.arange(24.0)},
                index=pd.date_range("2020-01-01", periods=24, freq="MS", tz="UTC"),
            ),
            profile_dst.model_copy(update={"frequency": "MS"}),
            plan_dst,
            id="month_starts_other_time_zone_same_grid",
        ),
        pytest.param(
            exog_daily.assign(promo=pd.arrays.SparseArray([0.0, 1.0] * 3 + [0.0])),
            data_daily, profile_daily, plan_daily_ridge,
            id="sparse_column",
        ),
        pytest.param(
            exog_wide.assign(kind=["closed", "a", "b", "a", "b", "a", "b"]),
            data_wide_closed, profile_wide_kind, plan_wide_kind,
            id="multiseries_category_on_rows_without_target_inside",
        ),
        pytest.param(
            exog_bh, data_bh, profile_bh, plan_bh,
            id="calendar_hours_for_business_hours",
        ),
        pytest.param(
            pd.concat([exog_range, exog_range.iloc[[0]].set_axis([90]).assign(
                x=np.nan
            )]),
            data_range, profile_range, plan_range_ridge,
            id="data_without_dates_more_rows",
        ),
        pytest.param(
            exog_daily.assign(weekday=range(7)),
            data_daily.assign(
                weekday=pd.Categorical(np.arange(len(data_daily)) % 7)
            ),
            profile_daily, plan_daily_ridge,
            id="integer_categories",
        ),
        pytest.param(
            exog_daily.assign(weekday=[True, False, True, False, True, False, True]),
            data_daily.assign(
                weekday=pd.Series([True, False, np.nan] * 34, dtype=object)[
                    : len(data_daily)
                ].to_numpy()
            ),
            profile_daily, plan_daily_ridge,
            id="bool_categories",
        ),
        pytest.param(
            exog_daily.assign(promo=exog_daily["promo"].astype("Float64")),
            data_daily, profile_daily, plan_daily_lgbm,
            id="nullable_float_complete",
        ),
        pytest.param(
            exog_daily.assign(weekday=["Funday", *exog_daily["weekday"][1:]]),
            data_daily, profile_daily, plans_daily_by_forecaster["foundation"],
            id="foundation_new_category",
        ),
        pytest.param(
            exog_daily[["promo"]],
            data_daily, profile_daily, plans_daily_by_forecaster["foundation"],
            id="foundation_past_only_covariate",
        ),
        pytest.param(
            exog_daily.assign(weekday=pd.Timestamp("2023-01-02")),
            data_daily.assign(
                weekday=pd.to_datetime(["2023-01-02", "2023-02-06"] * 50)
            ),
            profile_daily, plan_daily_ridge,
            id="dates_as_categories",
        ),
        pytest.param(exog_wide, data_wide, profile_wide, plan_wide_ridge,
                     id="multiseries_last_value"),
        pytest.param(exog_long, data_long, profile_long, plan_long_ridge, id="long"),
        pytest.param(
            exog_long.assign(date=exog_long["date"].dt.date),
            data_long, profile_long, plan_long_ridge,
            id="long_python_dates",
        ),
        pytest.param(
            exog_long.set_index("date"), data_long, profile_long, plan_long_ridge,
            id="long_indexed",
        ),
        pytest.param(
            exog_long.set_index(["series", "date"]),
            data_long, profile_long, plan_long_ridge,
            id="long_multiindex",
        ),
        pytest.param(
            exog_long[exog_long["series"] == "item_1"].drop(columns="series")
            .assign(date=lambda frame: frame["date"].dt.strftime("%Y-%m-%d")),
            data_long_single, profile_long_single, plan_long_single,
            id="long_single_series",
        ),
        pytest.param(
            exog_long.drop(columns="date"),
            data_long.set_index("date"),
            profile_long.model_copy(update={"date_column": None}),
            plan_long_ridge,
            id="long_dated_by_index",
        ),
        pytest.param(
            pd.DataFrame({
                "series": np.repeat(["item_1", "item_2", "item_3"], 9),
                "date": np.tile(pd.date_range("2012-04-30", periods=9), 3),
                "price": 1.0,
            }),
            data_long,
            profile_long.model_copy(
                update={"frequency": "B", "has_duplicate_timestamps": True}
            ),
            plan_long_ridge,
            id="long_business_days_repeated_timestamps",
        ),
        pytest.param(
            exog_long[exog_long["series"] != "item_3"],
            data_long_early, profile_long_early, plan_long_early_ridge,
            id="multiseries_series_ending_early_left_out",
        ),
        pytest.param(
            exog_long, data_long_early, profile_long_early, plan_long_early_ridge,
            id="multiseries_series_ending_early_at_last_date",
        ),
        pytest.param(
            exog_long_early,
            data_long_early, profile_long_early, plan_long_early_ridge,
            id="multiseries_series_ending_early_at_own_date",
        ),
        pytest.param(
            exog_long_early,
            data_long_early, profile_long_early, plan_long_early_foundation,
            id="foundation_series_ending_early",
        ),
        pytest.param(
            exog_long_early[exog_long_early["series"] != "item_3"],
            data_long_early, profile_long_early, plan_long_early_foundation,
            id="foundation_series_without_future_values",
        ),
        pytest.param(
            pd.concat([
                exog_long_early,
                exog_long_early.iloc[[14]].assign(date=pd.Timestamp("2012-04-26")),
            ], ignore_index=True),
            data_long_early, profile_long_early, plan_long_early_foundation,
            id="foundation_rows_before_dates_to_forecast",
        ),
        pytest.param(
            pd.concat([
                exog_long,
                exog_long.iloc[[0, 7, 14]].assign(date=pd.Timestamp("2012-04-29")),
            ], ignore_index=True),
            data_long, profile_long, plan_long_ridge,
            id="multiseries_long_rows_before_dates_to_forecast",
        ),
    ],
)
def test_validate_future_exog_output_when_exog_valid(exog, data, profile, plan):
    """
    Test that valid future exogenous variables pass without a warning. Wide data: a
    repeated column the plan does not use, an extra column, rows after the dates to
    forecast and in another order, text dates for data with a date column (the
    generated code parses them), a date column, calendar days for business-day data
    (the generated code drops the weekends), an index of Python dates, a forecast
    after a daylight saving time change (24 hours after the last date), the first
    `steps` rows only for data without dates, integer categories (category dtype)
    given as integers, booleans for the categories True and False, a nullable dtype
    without missing values, a category the data has not for a foundation model (it
    does not encode them), a foundation model without the future values of a column
    (a past-only covariate), dates as categories, ForecasterRecursiveMultiSeries
    forecasting from the last date with a target value, the same time zone written
    another way, the same instants in another time zone whose grid holds the dates
    to forecast (daily, or month starts with a fixed offset), a sparse column, a
    category of ForecasterRecursiveMultiSeries seen on rows without target between
    the target values (the encoder is fitted on them) and calendar hours for
    business-hour data, closes of business included (asfreq drops them). Long
    format: as columns, indexed by date or by series and date, Python dates in the
    date column, one series read as wide data (no series id, text dates parsed),
    data dated by its index (which the generated code cannot read, so not checked
    against dates), and the weekends of business-day data dropped by the reshape of
    each series even with repeated timestamps. A series that ends before the others
    is not predicted by ForecasterRecursiveMultiSeries, so its future exogenous
    variables are not read (absent, or at any dates), and a ForecasterFoundation
    model takes them from the date after its own last date. Rows before the dates to
    forecast are ignored by the forecasters that select the dates
    (ForecasterRecursiveMultiSeries in long format, foundation models), and a
    foundation model takes the historical columns of a series without future values
    as past-only covariates.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        validate_future_exog(exog, data, profile, plan)


def _prepared_by_script(exog, profile, plan):
    """
    Run on `exog` the statements of the generated forecast script that
    prepare the future exogenous variables, as `forecast()` injects them.
    """
    code = render_forecast_script(profile=profile, plan=plan).core
    statements, depth = [], 0
    for line in code.splitlines():
        if depth == 0 and not line.startswith("exog_future"):
            continue
        statements.append(line)
        depth += line.count("(") - line.count(")")
    namespace = {
        "pd": pd,
        "reshape_exog_long_to_dict": reshape_exog_long_to_dict,
        "exog_future": exog_as_injected(exog, profile),
    }
    exec("\n".join(statements), namespace)

    return namespace.get("exog_future_dict", namespace["exog_future"])


@pytest.mark.parametrize(
    "exog, data, profile, plan, first_dates",
    [
        (exog_daily, data_daily, profile_daily, plan_daily_ridge, {None: "2023-04-11"}),
        (
            pd.concat([
                exog_daily,
                _with_dates(exog_daily.iloc[[0]], ["2023-04-18"]),
            ]).assign(other=1.0).iloc[::-1],
            data_daily, profile_daily, plan_daily_ridge, {None: "2023-04-11"},
        ),
        (
            exog_daily.set_axis(exog_daily.index.strftime("%Y-%m-%d")),
            data_daily, profile_daily, plan_daily_ridge, {None: "2023-04-11"},
        ),
        (
            exog_calendar_days, data_business, profile_business, plan_business,
            {None: "2023-03-27"},
        ),
        (
            exog_long, data_long, profile_long, plan_long_ridge,
            {"item_1": "2012-04-30", "item_2": "2012-04-30", "item_3": "2012-04-30"},
        ),
        (
            exog_long_early, data_long_early, profile_long_early,
            plan_long_early_foundation,
            {"item_1": "2012-04-30", "item_2": "2012-04-30", "item_3": "2012-04-27"},
        ),
    ],
    ids=["valid", "extra_column_more_rows_unsorted", "text_dates_for_date_column",
         "calendar_days_for_business_days", "long", "foundation_series_ending_early"],
)
def test_validate_future_exog_output_when_valid_exog_read_by_generated_code(
    exog, data, profile, plan, first_dates
):
    """
    Test that future exogenous variables that pass the checks give, once the
    generated script has prepared them, the `steps` dates to forecast of each
    series (or of the data) in their first rows, without missing values: the
    rows skforecast reads. This ties the checks of the dates to the rendering.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        validate_future_exog(exog, data, profile, plan)
    prepared = _prepared_by_script(exog, profile, plan)
    columns = used_exog_columns(plan, profile)

    for name, first in first_dates.items():
        frame = prepared if name is None else prepared[name]
        rows = frame.iloc[: plan.steps]
        expected = pd.date_range(first, periods=plan.steps, freq=profile.frequency)
        pd.testing.assert_index_equal(rows.index, expected, check_names=False)
        assert rows[columns].notna().all(axis=None)
