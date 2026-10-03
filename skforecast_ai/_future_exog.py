################################################################################
#                            Future exogenous variables                        #
#                                                                              #
# Checks of the future exogenous variables of forecast()                      #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
import numpy as np
import pandas as pd

from ._constants import NAN_TOLERANT_ESTIMATORS
from ._dates import is_text, parse_text_dates, row_dates
from .exceptions import InvalidInputError, InvalidInputTypeError
from .execution.forecast_runner import exog_as_injected
from .profiling.data_profile import _caller_stacklevel, _fmt_timestamp
from .rendering._helpers import _get_numeric_exog
from .rendering.foundation import _get_foundation_exog
from .schemas import DataProfile, ForecastPlan

# Values listed in a message, at most.
_SHOWN = 5

# Forecasters trained on rows built from lags and window features: the first
# `window_size` values of each series only feed the lags of later rows.
_LAG_FORECASTERS = {
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
}


def as_exog_frame(exog: object) -> pd.DataFrame | None:
    """
    Return the future exogenous variables as a pandas DataFrame.

    A named pandas Series is one exogenous variable, as skforecast reads it.
    Any other type raises, instead of failing inside the generated code (a
    path to a CSV file failed with `AttributeError`).

    Parameters
    ----------
    exog : object
        Value of the `exog` argument.

    Returns
    -------
    exog : pandas DataFrame, None
        Future exogenous variables, or None when `exog` is None.
    """
    if exog is None or isinstance(exog, pd.DataFrame):
        return exog
    if isinstance(exog, pd.Series):
        if exog.name is None:
            raise InvalidInputTypeError(
                "`exog` is a pandas Series without a name: give it the name of "
                "the exogenous variable, or pass a pandas DataFrame.",
                field = "exog",
            )
        return exog.to_frame()

    raise InvalidInputTypeError(
        f"`exog` must be a pandas DataFrame with the future values of the "
        f"exogenous variables, not {type(exog).__name__}. Read a CSV file with "
        f"pandas.read_csv first (the CLI reads it with --exog).",
        field = "exog",
        hint  = "Pass the future exogenous values as a table indexed by their dates.",
    )


def used_exog_columns(plan: ForecastPlan, profile: DataProfile) -> list[str]:
    """
    Return the exogenous columns the generated code reads from the future
    exogenous variables.

    Parameters
    ----------
    plan : ForecastPlan
        Forecast plan.
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    columns : list of str
        Exogenous columns used by the plan.
    """
    if not plan.use_exog or not profile.exog_columns:
        return []
    if plan.task_type == "baseline":
        # The script of a baseline reads no exogenous variables.
        return []
    if plan.forecaster == "ForecasterStats":
        return _get_numeric_exog(profile)
    if plan.forecaster == "ForecasterFoundation":
        return _get_foundation_exog(plan, profile)[0]

    return list(profile.exog_columns)


def validate_future_exog(
    exog: pd.DataFrame,
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> None:
    """
    Check the future exogenous variables against the data and the plan.

    The generated code puts the future exogenous variables on the grid of the
    frequency of the data (`asfreq`) and skforecast reads the first `steps`
    rows, so a missing date became a row of missing values, a row off the
    grid was dropped, a new category was encoded as missing and a missing
    value gave missing predictions, all without an error. The checks:

    - Columns: every column the plan uses is present, once. A
      ForecasterFoundation model takes every column, so others raise.
    - Dates, read as the generated code reads them: no missing date, the
      time zone of the data, no repeated date, and the `steps` dates that
      follow the last date of the data (for ForecasterRecursiveMultiSeries
      the last date with a target value), with no row before them nor off
      their grid among them, as skforecast dates the forecast
      (`expand_index`). Rows off the grid of business days (weekends) are
      dropped by the generated code as before. In long format, the series
      and date columns, and every series the forecaster predicts, each with
      the dates that follow its last date (see `_check_long_dates`).
    - Values in the rows to forecast (the first `steps` rows in the order
      of the index when the data has no dates on a grid): a numeric
      variable holds numbers; for an ML forecaster, which encodes the
      categories, a categorical one holds the categories seen in the data
      (checked only when `data` holds the column, which a profile passed
      with other data may not). New categories (which the encoder reads as
      missing values), missing and infinite values raise when the estimator
      does not tolerate missing values; with one that does, a warning names
      them and the forecast runs as before.

    Parameters
    ----------
    exog : pandas DataFrame
        Future exogenous variables (see `as_exog_frame`).
    data : pandas DataFrame
        Data the forecaster is trained on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan, in prediction mode.

    Returns
    -------
    None
    """
    columns = used_exog_columns(plan, profile)
    if not columns:
        return
    per_series = _per_series(plan, profile)
    # Repeated columns the generated code does not read are harmless.
    keys = [profile.series_id_column, profile.date_column] if per_series else []
    duplicated = [
        column for column in dict.fromkeys(keys + columns)
        if column is not None and (exog.columns == column).sum() > 1
    ]
    if duplicated:
        raise InvalidInputError(
            f"`exog` has repeated column names: {_shown(duplicated)}.",
            field = "exog",
        )
    injected = exog_as_injected(exog, profile)
    _check_columns(injected, columns, plan, profile, per_series)
    if _takes_every_column(plan, profile, columns):
        # A historical column without future values is a past-only
        # covariate of the foundation model (or skforecast ignores it).
        columns = [column for column in columns if column in injected.columns]
    if profile.index_type != "datetime" or profile.frequency is None:
        if profile.data_format != "long":
            # Without dates on a grid, the generated code reads the first
            # `steps` rows in the order of the index (or of the dates).
            horizon, dates = _first_rows(injected, profile, plan.steps)
            _check_values(
                exog       = injected,
                horizon    = horizon,
                dates      = dates,
                data       = data,
                columns    = columns,
                plan       = plan,
                profile    = profile,
                per_series = per_series,
            )
        return
    if per_series and profile.date_column is None:
        # Long-format data dated by its index: the generated code cannot read
        # it and fails on its own, so there are no dates to check against.
        return
    exog_dates = _exog_dates(injected, profile, per_series)
    if per_series:
        horizon = _check_long_dates(injected, exog_dates, data, profile, plan)
    else:
        last = _last_date(data, profile, by_value=plan.task_type == "multi_series")
        expected = _forecast_dates(last, plan.steps, profile)
        exog_dates, zone = _in_data_zone(last, exog_dates)
        horizon = _check_dates(
            dates      = exog_dates,
            expected   = expected,
            profile    = profile,
            per_series = per_series,
            after      = "the data",
            by_date    = plan.forecaster == "ForecasterFoundation",
            zone       = zone,
        )
    _check_values(
        exog       = injected,
        horizon    = horizon,
        dates      = exog_dates,
        data       = data,
        columns    = columns,
        plan       = plan,
        profile    = profile,
        per_series = per_series,
    )


def _per_series(plan: ForecastPlan, profile: DataProfile) -> bool:
    """
    Return whether the generated code reads the future exogenous variables
    per series: long-format data with ForecasterRecursiveMultiSeries or a
    ForecasterFoundation model (`reshape_exog_long_to_dict`). Other plans
    on long-format data (a single series) read them as wide data.
    """
    return profile.data_format == "long" and plan.task_type in (
        "multi_series", "foundation"
    )


def _check_columns(
    exog: pd.DataFrame,
    columns: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
    per_series: bool,
) -> None:
    """
    Check that the future exogenous variables hold the columns the plan uses
    (and the series id and date columns when they are read per series), and
    only those for a ForecasterFoundation model that takes them all.
    """
    keys = []
    if per_series:
        keys = [
            column for column in (profile.series_id_column, profile.date_column)
            if column is not None
        ]
    takes_all = _takes_every_column(plan, profile, columns)
    missing = [
        column for column in keys + ([] if takes_all else columns)
        if column not in exog.columns
    ]
    if missing:
        with_keys = ""
        if per_series:
            with_keys = f", with the series id column {profile.series_id_column!r}"
            if profile.date_column is not None:
                with_keys += f" and the date column {profile.date_column!r}"
        raise InvalidInputError(
            f"`exog` has no column {_shown(missing)}. The future exogenous "
            f"variables must hold the columns {columns} that the plan "
            f"uses{with_keys}.",
            field = "exog",
        )
    if takes_all:
        # The generated code passes every column of the future exogenous
        # variables to the model, which rejects one without history.
        extra = [
            column for column in exog.columns
            if column not in columns and column != profile.date_column
        ]
        if extra:
            raise InvalidInputError(
                f"`exog` has columns that the data has no history of: "
                f"{_shown(extra)}. A ForecasterFoundation model takes every "
                f"column of the future exogenous variables; keep only "
                f"{columns}.",
                field = "exog",
            )


def _takes_every_column(
    plan: ForecastPlan,
    profile: DataProfile,
    columns: list[str],
) -> bool:
    """
    Return whether the generated code passes the future exogenous variables
    whole to the model: a ForecasterFoundation model on wide or single-series
    data that leaves no exogenous column out, of a profile that leaves no
    column of the data out (`unused_columns`).
    """
    return (
        plan.forecaster == "ForecasterFoundation"
        and profile.data_format != "long"
        and not set(profile.exog_columns) - set(columns)
        and not profile.unused_columns
    )


def _exog_dates(
    exog: pd.DataFrame,
    profile: DataProfile,
    per_series: bool,
) -> pd.DatetimeIndex:
    """
    Return the date of every row of the future exogenous variables, read as
    the generated code reads them.
    """
    date_column = profile.date_column
    if per_series:
        values = exog[date_column]
        if pd.api.types.infer_dtype(values, skipna=True) in (
            "string", "bytes", "mixed"
        ):
            # The generated code reshapes long-format exog without parsing
            # its dates, which turned every value into a missing one.
            raise InvalidInputError(
                f"The dates of `exog` (column {date_column!r}) are text: convert "
                f"them with pandas.to_datetime first.",
                field = "exog",
                hint  = "Give the future exogenous values dates, not text.",
            )
        try:
            # Python dates and datetimes, which pandas reads as dates.
            dates = pd.DatetimeIndex(pd.to_datetime(values))
        except (ValueError, TypeError) as exc:
            raise InvalidInputError(
                f"The dates of `exog` (column {date_column!r}) cannot be read "
                f"as dates: {exc}",
                field = "exog",
            ) from exc
    elif date_column:
        values = exog[date_column]
        try:
            dates = pd.DatetimeIndex(
                parse_text_dates(values) if is_text(values) else values
            )
        except (ValueError, TypeError) as exc:
            raise InvalidInputError(
                f"The dates of `exog` (column or index {date_column!r}) cannot be "
                f"read as the generated code reads them: {exc}",
                field = "exog",
            ) from exc
    else:
        index = exog.index
        if not isinstance(index, pd.DatetimeIndex) and pd.api.types.infer_dtype(
            index, skipna=True
        ) in ("date", "datetime"):
            # Python dates or datetimes, which pandas reads as dates.
            index = pd.DatetimeIndex(index)
        if not isinstance(index, pd.DatetimeIndex):
            raise InvalidInputError(
                f"The dates of `exog` must be its index, a pandas "
                f"DatetimeIndex, as in the data; its index is "
                f"{type(exog.index).__name__}.",
                field = "exog",
            )
        dates = index
    if dates.isna().any():
        positions = np.flatnonzero(dates.isna())
        raise InvalidInputError(
            f"`exog` has {len(positions)} row(s) without a date, at row "
            f"position(s) {_shown(positions.tolist())}: every row needs a date.",
            field = "exog",
        )

    return dates


def _last_date(
    data: pd.DataFrame,
    profile: DataProfile,
    by_value: bool = False,
) -> pd.Timestamp:
    """
    Return the last date of the data passed or, with `by_value`
    (ForecasterRecursiveMultiSeries, which drops the missing values at the
    end of each series), the last date with a target value.
    """
    dates = row_dates(data, profile.date_column)
    if dates is not None and by_value:
        targets = profile.target if isinstance(profile.target, list) else [
            profile.target
        ]
        targets = [target for target in targets if target in data.columns]
        if targets:
            dates = dates[data[targets].notna().any(axis=1).to_numpy()]
    last = dates.max() if dates is not None else None
    if last is None or pd.isna(last):
        raise InvalidInputError(
            "The last date of the data is unknown, so `exog` cannot be checked "
            "against the dates to forecast.",
            field = "exog",
        )

    return last


def _in_data_zone(
    last: pd.Timestamp,
    exog_dates: pd.DatetimeIndex,
) -> tuple[pd.DatetimeIndex, object]:
    """
    Return the dates of the future exogenous variables in the time zone of
    the data (skforecast compares dates by their instant), and the time zone
    of their clock when it differs from that of the data (the generated
    code puts them on the grid of the frequency in that zone; see
    `_check_dates`), or None. The same zone written another way (`tzutc()`
    for UTC, a fixed offset in winter) gives the same clock. Dates with a
    time zone against dates without one raise.
    """
    data_zone = getattr(last, "tz", None)
    if (data_zone is None) != (exog_dates.tz is None):
        raise _zone_error(exog_dates.tz, data_zone)
    if data_zone is None:
        return exog_dates, None
    converted = exog_dates.tz_convert(data_zone)
    if converted.tz_localize(None).equals(exog_dates.tz_localize(None)):
        return converted, None

    return converted, exog_dates.tz


def _zone_error(exog_zone: object, data_zone: object) -> InvalidInputError:
    """Return the error for future exog dates in another time zone."""
    return InvalidInputError(
        f"The dates of `exog` have the time zone {exog_zone}, those of the "
        f"data {data_zone}: use the time zone of the data.",
        field = "exog",
    )


def _forecast_dates(
    last: pd.Timestamp,
    steps: int,
    profile: DataProfile,
) -> pd.DatetimeIndex:
    """
    Return the `steps` dates to forecast that follow `last`, as skforecast
    builds them (`expand_index`).
    """
    offset = pd.tseries.frequencies.to_offset(profile.frequency)

    return pd.date_range(start=last + offset, periods=steps, freq=offset)


def _check_dates(
    dates: pd.DatetimeIndex,
    expected: pd.DatetimeIndex,
    profile: DataProfile,
    per_series: bool,
    after: str,
    series: object = None,
    by_date: bool = False,
    zone: object = None,
) -> np.ndarray:
    """
    Check the dates of the future exogenous variables of one series (in the
    time zone of the data; `zone` is that of their clock when it differs)
    against the dates to forecast, those after the last date of `after` (the
    data or the series), and return the positions of the rows of those
    dates.

    The generated code puts the rows on the grid of the frequency that
    starts at the first row, in the zone of their clock (asfreq, or the
    reshape of each series), so every date to forecast must lie on that
    grid. Rows before the dates to forecast raise unless `by_date`:
    skforecast reads the future exog of most forecasters by position, from
    the first row, but selects the dates to forecast from that of
    ForecasterRecursiveMultiSeries with a dict (long format) and of a
    ForecasterFoundation model.
    """
    of_series = "" if series is None else f" of series {str(series)!r}"
    for_series = "" if series is None else f" for series {str(series)!r}"
    repeated = dates[dates.duplicated()].unique()
    if len(repeated):
        raise InvalidInputError(
            f"`exog` repeats dates{of_series}: "
            f"{_shown([_fmt_timestamp(date) for date in repeated])}. Every date "
            f"must appear once.",
            field = "exog",
        )
    clock = dates if zone is None else dates.tz_convert(zone)
    on_grid = _on_business_grid(clock, profile, per_series)
    kept = dates[on_grid]
    before = kept[kept < expected[0]]
    if len(before) and not by_date:
        raise InvalidInputError(
            f"`exog` starts at {_fmt_timestamp(before.min())}{for_series}, before "
            f"the first date to forecast, {_fmt_timestamp(expected[0])} (the "
            f"date after the last date of {after}). Drop the rows before it.",
            field = "exog",
        )
    absent = expected[~expected.isin(dates)]
    if len(absent):
        raise InvalidInputError(
            f"`exog` has no row{of_series} for {len(absent)} of the {len(expected)} "
            f"dates to forecast, such as {_fmt_timestamp(absent[0])}. It must "
            f"hold the dates from {_fmt_timestamp(expected[0])} to "
            f"{_fmt_timestamp(expected[-1])} at frequency {profile.frequency!r}.",
            field = "exog",
        )
    within = (kept >= expected[0]) & (kept <= expected[-1])
    off_grid = kept[within & ~kept.isin(expected)]
    if len(off_grid):
        raise InvalidInputError(
            f"`exog` has dates{of_series} off the grid of frequency "
            f"{profile.frequency!r} among the dates to forecast, such as "
            f"{_fmt_timestamp(off_grid[0])}: the generated code drops them. "
            f"Give one row per date to forecast.",
            field = "exog",
        )
    if not (profile.has_duplicate_timestamps and not per_series):
        kept_clock = clock[on_grid]
        grid = pd.date_range(
            kept_clock.min(), kept_clock.max(), freq=profile.frequency
        )
        if dates.tz is not None:
            grid = grid.tz_convert(dates.tz)
        outside = expected[~expected.isin(grid)]
        if len(outside):
            if zone is not None:
                raise _zone_error(zone, dates.tz)
            raise InvalidInputError(
                f"`exog` starts at {_fmt_timestamp(kept.min())}{for_series}, off "
                f"the grid of frequency {profile.frequency!r} of the dates to "
                f"forecast: the generated code puts the rows on the grid that "
                f"starts at the first row, which leaves out the dates to "
                f"forecast, such as {_fmt_timestamp(outside[0])}. Drop the rows "
                f"before {_fmt_timestamp(expected[0])}.",
                field = "exog",
            )

    return np.flatnonzero(dates.isin(expected))


def _on_business_grid(
    dates: pd.DatetimeIndex,
    profile: DataProfile,
    per_series: bool,
) -> np.ndarray:
    """
    Return which dates the generated code keeps. It puts the rows on the grid
    (asfreq, or the reshape of each series), which drops the rows of
    calendar days or hours off a business-day or business-hour grid, as
    before; other rows off the grid are reported. Wide data with repeated
    timestamps is not put on the grid, so every row is kept.
    """
    offset = pd.tseries.frequencies.to_offset(profile.frequency)
    business = isinstance(
        offset,
        (
            pd.offsets.BusinessDay, pd.offsets.CustomBusinessDay,
            pd.offsets.BusinessHour, pd.offsets.CustomBusinessHour,
        ),
    )
    if not business or len(dates) == 0 or (
        profile.has_duplicate_timestamps and not per_series
    ):
        return np.ones(len(dates), dtype=bool)
    # The grid asfreq builds (`is_on_offset` also accepts the close of a
    # business hour, which the grid leaves out).
    grid = pd.date_range(dates.min(), dates.max(), freq=offset)

    return np.asarray(dates.isin(grid))


def _check_long_dates(
    exog: pd.DataFrame,
    dates: pd.DatetimeIndex,
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> np.ndarray:
    """
    Check the dates of every series of long-format future exogenous
    variables, and return the positions of the rows to forecast.

    ForecasterFoundation predicts every series from its own last date (that
    of its last row). ForecasterRecursiveMultiSeries predicts the series
    whose last value is at the last date of the data and leaves out those
    that end before it (the note "Series ending early" of the profile), so
    their future exogenous variables are not read and not checked.

    The rows are grouped by series once and checked together; each series
    that may fail is checked again on its own (`_check_dates`), which raises
    with the message and otherwise gives its rows to forecast.
    """
    series_id = profile.series_id_column
    foundation = plan.forecaster == "ForecasterFoundation"
    ends = _long_series_ends(data, profile, by_value=not foundation)
    if not ends:
        raise InvalidInputError(
            "The last date of the data is unknown, so `exog` cannot be checked "
            "against the dates to forecast.",
            field = "exog",
        )
    last = max(ends.values())
    predicted = {
        name: end for name, end in ends.items() if foundation or end == last
    }
    horizons = {
        end: _forecast_dates(end, plan.steps, profile)
        for end in set(predicted.values())
    }
    dates, zone = _in_data_zone(last, dates)

    codes, names = pd.factorize(exog[series_id])
    code_of = {name: code for code, name in enumerate(names)}
    # The reshape of each series fails on repeated dates, predicted or not.
    repeated = pd.DataFrame({"code": codes, "date": dates}).duplicated().to_numpy()
    repeated &= codes >= 0
    if repeated.any():
        code = codes[np.flatnonzero(repeated)[0]]
        _check_dates(
            dates      = dates[codes == code],
            expected   = next(iter(horizons.values())),
            profile    = profile,
            per_series = True,
            after      = "the data",
            series     = names[code],
            by_date    = True,
            zone       = zone,
        )
    absent = [name for name in predicted if name not in code_of]
    as_text = {str(name) for name in names}
    other_type = bool(absent) and all(str(name) in as_text for name in absent)
    if foundation and not other_type:
        # A series without future values takes its historical exogenous
        # columns as past-only covariates (or skforecast ignores them).
        predicted = {
            name: end for name, end in predicted.items() if name in code_of
        }
        absent = []
    if absent:
        hint = ""
        if other_type:
            hint = (
                f" The ids of `exog` are of another type "
                f"({exog[series_id].dtype}) than those of the data: use the "
                f"same type."
            )
        raise InvalidInputError(
            f"`exog` has no rows for {len(absent)} series of the data: "
            f"{_shown([str(name) for name in absent])}.{hint}",
            field = "exog",
        )

    # Rows of each series, in the order of `exog`.
    order = np.argsort(codes, kind="stable")
    bounds = np.searchsorted(codes[order], np.arange(len(names) + 1))
    clock = dates if zone is None else dates.tz_convert(zone)
    kept = _on_business_grid(clock, profile, True)
    in_horizon = np.zeros(len(dates), dtype=bool)
    suspect = set()
    for end, expected in horizons.items():
        group = [code_of[name] for name, value in predicted.items() if value == end]
        if not group:
            continue
        rows = np.concatenate(
            [order[bounds[code]:bounds[code + 1]] for code in group]
        )
        row_codes = codes[rows]
        row_dates = dates[rows]
        matches = np.asarray(row_dates.isin(expected))
        in_horizon[rows] = matches
        repeated = pd.DataFrame(
            {"code": row_codes, "date": row_dates}
        ).duplicated().to_numpy()
        within = np.asarray((row_dates >= expected[0]) & (row_dates <= expected[-1]))
        off_grid = kept[rows] & within & ~matches
        # Rows before the dates to forecast, or a clock in another zone, move
        # the grid of the reshape: checked on their own.
        early = kept[rows] & np.asarray(row_dates < expected[0])
        if zone is not None:
            early[:] = True
        suspect.update(row_codes[repeated | off_grid | early].tolist())
        found = pd.DataFrame(
            {"code": row_codes[matches], "date": row_dates[matches]}
        ).drop_duplicates()["code"].value_counts()
        suspect.update(
            code for code in group if found.get(code, 0) < len(expected)
        )

    for name, end in predicted.items():
        code = code_of[name]
        if code in suspect:
            rows = order[bounds[code]:bounds[code + 1]]
            found = _check_dates(
                dates      = dates[rows],
                expected   = horizons[end],
                profile    = profile,
                per_series = True,
                after      = f"series {str(name)!r}" if foundation else "the data",
                series     = name,
                by_date    = True,
                zone       = zone,
            )
            in_horizon[rows] = False
            in_horizon[rows[found]] = True

    return np.flatnonzero(in_horizon)


def _long_series_ends(
    data: pd.DataFrame,
    profile: DataProfile,
    by_value: bool,
) -> dict:
    """
    Return the last date of each series of long-format data: that of its last
    row, or of its last value when `by_value` (skforecast drops the missing
    values at the end of a series).
    """
    dates = row_dates(data, profile.date_column)
    ids = _row_ids(data, profile.series_id_column)
    if dates is None or ids is None:
        return {}
    keep = ~dates.isna() & ~pd.isna(ids)
    if by_value and profile.target in data.columns:
        keep &= data[profile.target].notna().to_numpy()
    frame = pd.DataFrame({"id": ids[keep], "date": dates[keep]})

    return frame.groupby("id", sort=False)["date"].max().to_dict()


def _row_ids(data: pd.DataFrame, series_id: str | None) -> np.ndarray | None:
    """
    Return the series id of every row of long-format data: its column, or a
    level of a MultiIndex (the first one when it has no name).
    """
    if series_id is not None and series_id in data.columns:
        return data[series_id].to_numpy()
    if isinstance(data.index, pd.MultiIndex):
        if series_id is not None and series_id in data.index.names:
            return data.index.get_level_values(series_id).to_numpy()
        if data.index.names[0] is None:
            return data.index.get_level_values(0).to_numpy()

    return None


def _first_rows(
    exog: pd.DataFrame,
    profile: DataProfile,
    steps: int,
) -> tuple[np.ndarray, pd.DatetimeIndex | None]:
    """
    Return the positions of the first `steps` rows in the order the generated
    code sorts them (by date when the data has a date column, otherwise by
    index; rows that cannot be ordered are taken as they come), and the date
    of every row when there are dates.
    """
    date_column = profile.date_column
    if date_column and date_column in exog.columns:
        keys = exog[date_column]
    else:
        keys = exog.index.to_series()
    dates = None
    try:
        if is_text(keys):
            keys = parse_text_dates(keys)
        if pd.api.types.is_datetime64_any_dtype(keys):
            dates = pd.DatetimeIndex(keys)
        order = np.argsort(keys.to_numpy(), kind="stable")
    except (ValueError, TypeError):
        order = np.arange(len(exog))

    return order[:steps], dates


def _check_values(
    exog: pd.DataFrame,
    horizon: np.ndarray,
    dates: pd.DatetimeIndex | None,
    data: pd.DataFrame,
    columns: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
    per_series: bool,
) -> None:
    """
    Check the values of the future exogenous variables in the rows of the
    dates to forecast (`horizon`, positions in `exog`; `dates` holds the date
    of every row, None when there are none) against the data the forecaster
    is trained on. A column the data has not (a profile passed with other
    data) is checked for its infinite and missing values only, among those
    that read as numbers: the profile does not tell a column of text (string
    dtype) from a numeric one.
    """
    rows = exog.iloc[horizon]
    row_dates_ = dates[horizon] if dates is not None else None
    series_id = profile.series_id_column if per_series else None
    foundation = plan.forecaster == "ForecasterFoundation"
    tolerant = plan.estimator in NAN_TOLERANT_ESTIMATORS or foundation
    fitted = _fitted_rows(data, profile, plan)
    learned = _learned_rows(data, profile, plan)
    # With a column of categories or objects, skforecast reads the exog as
    # objects and fails on pd.NA of a nullable numeric dtype too.
    with_categories = any(
        (column in data.columns and not pd.api.types.is_numeric_dtype(data[column]))
        or not pd.api.types.is_numeric_dtype(exog[column])
        for column in columns
    )
    with_missing = {}
    with_infinite = []
    with_new = {}
    with_unlearned = {}
    for column in columns:
        future = rows[column]
        if isinstance(future.dtype, pd.SparseDtype):
            future = future.sparse.to_dense()
        present = future.dropna()
        not_single = np.array(
            [not pd.api.types.is_scalar(value) for value in present.array],
            dtype=bool,
        )
        if not_single.any():
            raise InvalidInputError(
                f"`exog` column {column!r} holds values that are not single "
                f"values, such as {present[not_single].iloc[0]!r}.",
                field = "exog",
            )
        trained = data[column] if column in data.columns else None
        if trained is not None:
            categorical = not pd.api.types.is_numeric_dtype(trained)
        else:
            categorical = column in profile.categorical_exog
        # The ML forecasters encode the categories of the rows they are
        # fitted on; a foundation model takes the values as they are.
        if categorical and trained is not None and not foundation:
            known = trained[fitted].dropna() if fitted is not None else trained.dropna()
            seen = _categories(known)
            if (
                len(present)
                and pd.api.types.is_numeric_dtype(present)
                and not any(_is_number(value) for value in seen)
            ):
                raise InvalidInputError(
                    f"`exog` column {column!r} holds numbers, but it holds text "
                    f"in the data (categories such as {_shown(seen)}).",
                    field = "exog",
                )
            new = _categories(present[~present.isin(known)])
            if new and not tolerant:
                raise InvalidInputError(
                    f"`exog` column {column!r} holds categories that the data "
                    f"has not: {_shown(new)}. The data has "
                    f"{_shown(sorted(seen, key=str))}; the forecaster cannot "
                    f"use a new category.",
                    field = "exog",
                )
            if new:
                # The encoder reads a new category as a missing value, which
                # the estimator tolerates (question 6 of the plan).
                with_new[column] = new
            if learned is not None:
                rows_learned = learned if fitted is None else learned & fitted
                taught = trained[rows_learned].dropna()
                unlearned = _categories(
                    present[present.isin(known) & ~present.isin(taught)]
                )
                if unlearned:
                    # Encoded, but in no row the estimator is trained on.
                    with_unlearned[column] = unlearned
        elif not categorical:
            # pd.NA of a column of objects or text makes skforecast fail; a
            # nullable numeric dtype reads it as NaN, unless the exog also
            # holds categories.
            if (
                not foundation
                and (
                    pd.api.types.is_object_dtype(future)
                    or pd.api.types.is_string_dtype(future)
                    or with_categories
                )
                and any(value is pd.NA for value in future)
            ):
                raise InvalidInputError(
                    f"`exog` column {column!r} holds pd.NA (dtype "
                    f"{future.dtype}), which the forecaster cannot read: "
                    f"convert it to float, with NaN for the missing values.",
                    field = "exog",
                )
            if pd.api.types.infer_dtype(present, skipna=True) in (
                "datetime64", "datetime", "date", "timedelta64", "timedelta",
                "period",
            ):
                raise InvalidInputError(
                    f"`exog` column {column!r} holds dates or durations, such as "
                    f"{present.iloc[0]!r}, but it holds numbers in the data.",
                    field = "exog",
                )
            numbers = pd.to_numeric(present, errors="coerce")
            text = present[numbers.isna()]
            if len(text) and trained is not None:
                raise InvalidInputError(
                    f"`exog` column {column!r} holds values that are not "
                    f"numbers, such as {_shown(pd.unique(text).tolist())}, but "
                    f"it holds numbers in the data.",
                    field = "exog",
                )
            if np.isinf(numbers.to_numpy(dtype=float)).any():
                if not tolerant:
                    raise InvalidInputError(
                        f"`exog` column {column!r} holds infinite values, which "
                        f"{plan.forecaster} with {plan.estimator} cannot use.",
                        field = "exog",
                    )
                with_infinite.append(column)
        missing = future.isna().to_numpy()
        if missing.any():
            if (
                categorical and trained is not None and not foundation
                and missing.all()
                and pd.api.types.is_numeric_dtype(exog[column])
            ):
                # A column of missing values only reads as numbers, which the
                # encoder of the categories fails on.
                raise InvalidInputError(
                    f"`exog` column {column!r} has no value in the rows to "
                    f"forecast; the forecaster cannot encode it.",
                    field = "exog",
                )
            with_missing[column] = _missing_where(
                rows      = rows,
                missing   = missing,
                series_id = series_id,
                dates     = row_dates_,
            )

    if with_missing and not tolerant:
        found = "; ".join(
            f"{column!r}: {where}" for column, where in with_missing.items()
        )
        raise InvalidInputError(
            f"`exog` has missing values in the rows to forecast ({found}). "
            f"{plan.forecaster} with {plan.estimator} cannot use them, so its "
            f"predictions would be missing: fill them in.",
            field = "exog",
        )
    if with_missing:
        found = "; ".join(
            f"{column!r}: {where}" for column, where in with_missing.items()
        )
        # A foundation model receives them as they are: some backends
        # treat them as missing values, others reject them.
        reads = "receives them as they are" if foundation else (
            "treats them as missing values"
        )
        warnings.warn(
            f"`exog` has missing values in the rows to forecast ({found}). "
            f"{plan.estimator} {reads}; check that they are meant to be "
            f"missing.",
            UserWarning,
            stacklevel = _caller_stacklevel(),
        )
    if with_new:
        found = "; ".join(
            f"{column!r}: {_shown(new)}" for column, new in with_new.items()
        )
        warnings.warn(
            f"`exog` holds categories that the data has not ({found}). "
            f"{plan.estimator} reads them as missing values; check them.",
            UserWarning,
            stacklevel = _caller_stacklevel(),
        )
    if with_unlearned:
        found = "; ".join(
            f"{column!r}: {_shown(categories)}"
            for column, categories in with_unlearned.items()
        )
        warnings.warn(
            f"`exog` holds categories that the data has only in its first "
            f"rows, which the lags and window features take up ({found}): "
            f"{plan.forecaster} is not trained on them, so the predictions "
            f"cannot use them; check them.",
            UserWarning,
            stacklevel = _caller_stacklevel(),
        )
    if with_infinite:
        warnings.warn(
            f"`exog` column(s) {_shown(with_infinite)} hold infinite values in "
            f"the rows to forecast, which {plan.estimator} receives as they "
            f"are; check that they are meant to be there.",
            UserWarning,
            stacklevel = _caller_stacklevel(),
        )


def _fitted_rows(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> np.ndarray | None:
    """
    Return the rows of the data whose exogenous values the encoder of
    ForecasterRecursiveMultiSeries is fitted on: those from the first to the
    last target value of each series (it drops the missing values at the
    ends of a series, not those in between). None for the other forecasters,
    fitted on every row, and when the rows have no dates.

    The first rows of each series, which the lags and window features take
    up, are not left out: a category seen only there is known to the
    encoder (see `_learned_rows`).
    """
    if plan.task_type != "multi_series":
        return None
    dates = row_dates(data, profile.date_column)
    if dates is None:
        return None
    dates = pd.Series(dates, index=data.index)
    if profile.data_format == "long":
        if profile.target not in data.columns:
            return None
        ids = pd.Series(_row_ids(data, profile.series_id_column), index=data.index)
        valid_dates = dates.where(data[profile.target].notna())
        first = valid_dates.groupby(ids).transform("min")
        last = valid_dates.groupby(ids).transform("max")
        return ((dates >= first) & (dates <= last)).to_numpy()
    targets = profile.target if isinstance(profile.target, list) else [profile.target]
    fitted = np.zeros(len(data), dtype=bool)
    for target in targets:
        if target not in data.columns:
            continue
        valid = dates[data[target].notna()]
        if len(valid):
            fitted |= ((dates >= valid.min()) & (dates <= valid.max())).to_numpy()

    return fitted


def _learned_rows(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> np.ndarray | None:
    """
    Return the rows of the data the estimator of a lag forecaster is trained
    on: skforecast builds its training rows from the value after the first
    `window_size` values of each series (from its first value), so the
    categories of the rows before are encoded but never learned. None for
    the forecasters without lags and when the rows have neither dates nor a
    RangeIndex. Without dates, the rows are in the order of the index.
    """
    size = _window_size(plan)
    if not size:
        return None
    dates = row_dates(data, profile.date_column)
    if dates is not None:
        order = pd.Series(dates, index=data.index)
    elif isinstance(data.index, pd.RangeIndex):
        order = pd.Series(np.asarray(data.index), index=data.index)
    else:
        return None
    if profile.data_format == "long":
        if profile.target not in data.columns:
            return None
        ids = pd.Series(_row_ids(data, profile.series_id_column), index=data.index)
        first = order.where(data[profile.target].notna()).groupby(ids).transform("min")
        rank = order.where(order >= first).groupby(ids).rank(method="dense")
        return (rank > size).to_numpy()
    targets = profile.target if isinstance(profile.target, list) else [profile.target]
    learned = np.zeros(len(data), dtype=bool)
    for target in targets:
        if target not in data.columns:
            continue
        first = order[data[target].notna()].min()
        rank = order.where(order >= first).rank(method="dense")
        learned |= (rank > size).to_numpy()

    return learned


def _window_size(plan: ForecastPlan) -> int:
    """
    Return the number of first values of each series that a lag forecaster
    reads but does not train on, as skforecast computes its `window_size`:
    the largest lag or window feature, plus the order of the
    differentiation. 0 for the other forecasters.
    """
    if plan.forecaster not in _LAG_FORECASTERS:
        return 0
    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags")
    if isinstance(lags, int) and not isinstance(lags, bool):
        sizes = [lags]
    else:
        sizes = [int(lag) for lag in lags or []]
    for entry in kwargs.get("window_features") or []:
        size = entry.get("window_size") if isinstance(entry, dict) else None
        if isinstance(size, int) and not isinstance(size, bool):
            sizes.append(size)
        elif isinstance(size, (list, tuple)):
            sizes.extend(int(value) for value in size)
    if not sizes:
        return 0

    return max(sizes) + int(kwargs.get("differentiation") or 0)


def _categories(values: pd.Series) -> list:
    """
    Return the distinct values of a categorical column, without missing ones,
    as pandas holds them (dates as Timestamps).
    """
    return [
        value.item() if isinstance(value, np.generic) else value
        for value in values.dropna().unique()
    ]


def _is_number(value: object) -> bool:
    """Return whether a category is a number (booleans included)."""
    return isinstance(value, (int, float, np.number, np.bool_))


def _missing_where(
    rows: pd.DataFrame,
    missing: np.ndarray,
    series_id: str | None,
    dates: pd.DatetimeIndex | None,
) -> str:
    """
    Describe where the missing values of a column are: their series, their
    dates (`dates`, those of `rows`) or, without dates, their index.
    """
    count = int(missing.sum())
    if series_id is not None:
        names = pd.unique(rows[series_id].to_numpy()[missing])
        return f"{count} value(s), series {_shown([str(name) for name in names])}"
    if dates is None:
        return f"{count} value(s), at index {_shown(rows.index[missing].tolist())}"
    shown = _shown([_fmt_timestamp(date) for date in dates[missing] if pd.notna(date)])

    return f"{count} value(s), such as {shown}" if shown else f"{count} value(s)"


def _shown(values: list) -> str:
    """Return up to `_SHOWN` values for a message, and how many more there are."""
    shown = ", ".join(repr(value) for value in values[:_SHOWN])
    if len(values) > _SHOWN:
        shown += f" and {len(values) - _SHOWN} more"

    return shown
