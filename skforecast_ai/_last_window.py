################################################################################
#                           Last window of the target                          #
#                                                                              #
# Checks of the values of the target that forecast() and backtest() read       #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import copy
import warnings
from typing import NamedTuple
import numpy as np
import pandas as pd
from skforecast.model_selection import TimeSeriesFold

from ._constants import AUTOREG_FORECASTERS, DIRECT_FORECASTERS, NAN_TOLERANT_ESTIMATORS
from ._dates import row_dates, training_end
from ._future_exog import _SHOWN, _per_series, _shown, used_exog_columns
from .exceptions import DataContentError, InvalidInputError
from .profiling.data_profile import (
    _caller_stacklevel,
    _fmt_timestamp,
    closed_weekdays,
    count_test_observations,
    weekday_names,
)
from .recommendation.backtesting import training_length_needed
from .recommendation.missing_values import (
    backtest_missing_values,
    backtest_missing_values_messages,
    closed_days_remedy,
    nan_tolerant_estimator,
    tolerant_estimator_phrase,
)
from .schemas import DataProfile, ForecastPlan


def validate_last_window(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    final_rows: bool = True,
) -> None:
    """
    Check the last values of the target that the forecaster reads to predict
    (in prediction mode, or on the training partition of an evaluation with
    `final_rows=False`).

    The generated code puts the target on the grid of its frequency and the
    forecaster predicts from its last values, so final rows without a target
    value (future rows appended to carry the exogenous variables) moved the
    forecast past them, and a missing value read by a lag gave missing
    predictions, both without an error. The checks, in prediction mode:

    - Final rows: dates at the end of the data with no target value (in any
      series) raise, whatever the estimator, except for
      ForecasterRecursiveMultiSeries, which drops them and forecasts the
      dates after the last value, as without them: a warning names them and
      the rest of the window is checked. A series that ends before the
      others is not one of them: ForecasterRecursiveMultiSeries does not
      predict it, which the note "Series ending early" of the profile says.
      When the final dates are weekend days that never have a value in
      daily data, the message suggests dropping every weekend row instead.
    - Missing values that the predictions read: those a lag reads at some
      step (with the differentiation, the values each differenced value is
      made of), those of a window feature whose values are all missing (the
      rolling statistics skip missing values otherwise), those the inverse
      of the differentiation reads, and the equivalent dates of
      ForecasterEquivalentDate. They raise when the estimator is not in
      `NAN_TOLERANT_ESTIMATORS`, for ForecasterEquivalentDate (which repeats
      them as missing predictions) and when the inverse of the
      differentiation reads them (the predictions would be missing whatever
      the estimator); with an estimator that tolerates them a warning names
      them and the forecast runs as before. For
      ForecasterRecursiveMultiSeries, only the series it predicts.

    ForecasterStats fails on any missing value of the target and a
    ForecasterFoundation model takes them as they are, so only the final
    rows are checked for them. Data the generated code cannot read (an
    index that is neither dates nor a RangeIndex, long-format data without
    its date and series id columns, ForecasterDirectMultiVariate on several
    series in long format) is left to the error of the generated code.

    Parameters
    ----------
    data : pandas DataFrame
        Data the forecaster is trained on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan.
    final_rows : bool, default True
        Whether to check the final rows. False for the training partition
        of an evaluation (see `validate_evaluation_partition`): its end is
        set by `test_size`, so missing values there are values that the
        lags read, as any other.

    Returns
    -------
    None
    """
    if _per_series(plan, profile):
        _check_long(data, profile, plan, final_rows)
    elif profile.data_format != "long" or profile.n_series == 1:
        _check_wide(data, profile, plan, final_rows)


def _check_wide(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    final_rows: bool = True,
) -> None:
    """
    Check the target of single-series and wide-format data (and of a single
    series in long format), read as the generated code reads it.
    """
    frames = _target_frame(data, profile)
    if frames is None:
        return
    frame, present_index = frames
    present = frame.notna().to_numpy()
    with_value = np.flatnonzero(present.any(axis=1))
    if not len(with_value):
        return
    # The series the generated code builds ends without a value (dates
    # `asfreq` inserts included); the rows to drop are those of the data
    # after the last value.
    last_value = frame.index[with_value[-1]]
    if final_rows and with_value[-1] < len(frame) - 1:
        _final_rows(
            last_value  = last_value,
            after       = present_index[present_index > last_value],
            has_value   = pd.Series(present.any(axis=1), index=frame.index),
            profile     = profile,
            plan        = plan,
            long_format = False,
        )
        # ForecasterRecursiveMultiSeries drops them: its window ends on the
        # last value.
        frame = frame.iloc[:with_value[-1] + 1]
        present = present[:with_value[-1] + 1]

    positions, order, size = _read_positions(plan, limit=len(frame))
    if not size:
        return
    # The level of ForecasterDirectMultiVariate, as the generated code
    # writes it (`_get_target_str`).
    level = profile.target[0] if isinstance(profile.target, list) else profile.target
    missing, closed = {}, {}
    for column_position, column in enumerate(frame.columns):
        values = present[:, column_position]
        if plan.forecaster == "ForecasterRecursiveMultiSeries":
            if not values[-1]:
                # It ends before the last date and is not predicted.
                continue
            # The series starts at its first value.
            values = values[np.argmax(values):]
        read, by_differentiation = _missing_read(
            missing_window = ~values[::-1][:size],
            positions      = positions,
            order          = order,
            plan           = plan,
            # ForecasterDirectMultiVariate predicts its level only.
            inverse        = (
                plan.forecaster != "ForecasterDirectMultiVariate"
                or column == level
            ),
        )
        if read:
            missing[_plain(column)] = (
                frame.index[len(frame) - np.asarray(read)], by_differentiation
            )
            closed[_plain(column)] = _closed_weekdays_of(
                frame.index, present[:, column_position], profile
            )

    _report(missing, plan, profile, order, by_series=False, closed=closed)


def _target_frame(
    data: pd.DataFrame,
    profile: DataProfile,
    columns: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Index] | None:
    """
    Return the target columns as the generated code reads them (in date
    order, the first row of a repeated date, on the grid of the frequency,
    `asfreq` inserting the missing dates; without dates, in the order of the
    index), and the index of the rows of the data. None when the data has
    not the target or the generated code cannot read it. The index of the
    rows holds every row, repeated dates and rows off the grid included.
    `columns` reads other columns of the data the same way (the exogenous
    variables of wide-format data), instead of the target.
    """
    if columns is None:
        columns = (
            profile.target if isinstance(profile.target, list) else [profile.target]
        )
    targets = list(dict.fromkeys(
        column for column in columns if column in data.columns
    ))
    if not targets:
        return None
    date_column = profile.date_column
    try:
        if profile.index_type == "datetime":
            if date_column is not None:
                readable = date_column in data.columns
            else:
                readable = isinstance(data.index, pd.DatetimeIndex)
            if not readable:
                return None
            frame = pd.DataFrame(
                {target: data[target].to_numpy() for target in targets},
                index = pd.DatetimeIndex(
                            row_dates(data, date_column, profile.date_format)
                        ),
            )
            frame = frame.loc[frame.index.notna()]
            frame = frame.sort_index(kind="stable")
            present_index = frame.index
            frame = frame.loc[~frame.index.duplicated(keep="first")]
            if profile.frequency is not None:
                frame = frame.asfreq(profile.frequency)
        else:
            if not isinstance(data.index, pd.RangeIndex):
                return None
            frame = data[targets].sort_index(kind="stable")
            present_index = frame.index
    except (ValueError, TypeError):
        # The generated code fails on these dates with its own error.
        return None

    return frame, present_index


def _check_long(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    final_rows: bool = True,
) -> None:
    """
    Check the target of long-format data read per series (see
    `_per_series`), as `reshape_series_long_to_dict` reads it (the first row
    of a repeated date, each series on the grid of the frequency from its
    first date): the final dates, and for ForecasterRecursiveMultiSeries the
    last window of every series it predicts (those whose last value is on
    the last date with a value; it drops the missing values at the end of a
    series).
    """
    date_column = profile.date_column
    series_id = profile.series_id_column
    if (
        date_column not in data.columns
        or series_id not in data.columns
        or profile.target not in data.columns
    ):
        return
    try:
        dates = pd.DatetimeIndex(
            row_dates(data, date_column, profile.date_format)
        )
    except (ValueError, TypeError):
        # The generated code fails on these dates with its own error.
        return
    codes, names = pd.factorize(data[series_id])
    keep = (codes >= 0) & ~np.asarray(dates.isna())
    if not keep.any():
        return
    rows = pd.DataFrame({
        "code": codes[keep],
        "date": dates[keep],
        "value": pd.notna(data[profile.target].to_numpy()[keep]),
    })
    every_date = rows["date"]
    # The generated code keeps the first row of a repeated date of a series.
    rows = rows.drop_duplicates(["code", "date"], keep="first")
    if profile.frequency:
        try:
            rows = rows.loc[_on_series_grid(rows, profile.frequency)]
        except (ValueError, TypeError):
            # The generated code fails on this frequency with its own error.
            return
    if not rows["value"].any():
        return
    with_value = rows.loc[rows["value"]]
    last_value = with_value["date"].max()
    if final_rows and (rows["date"] > last_value).any():
        # Every row after the last value is to drop, repeated or off the grid.
        after = every_date[every_date > last_value]
        _final_rows(
            last_value  = last_value,
            after       = pd.DatetimeIndex(after.sort_values()),
            has_value   = rows.groupby("date")["value"].any(),
            profile     = profile,
            plan        = plan,
            long_format = True,
        )

    # A foundation model reads no lags, and without a frequency there is no
    # grid to read the window on.
    if plan.forecaster != "ForecasterRecursiveMultiSeries" or not profile.frequency:
        return
    ends = with_value.groupby("code")["date"].agg(["min", "max"])
    predicted = ends.loc[ends["max"] == last_value]
    try:
        # The window is cut at the dates of the longest series predicted.
        span = len(pd.date_range(
            predicted["min"].min(), last_value, freq=profile.frequency
        ))
        positions, order, size = _read_positions(plan, limit=span)
        if not size:
            return
        # Every series predicted ends on the last date with a value, on the
        # grid of the frequency, so their windows have the same dates.
        window = pd.date_range(
            end     = last_value,
            periods = size,
            freq    = profile.frequency,
            unit    = dates.unit,
        )
    except (ValueError, TypeError):
        return
    # Position 1 is the last date of the window.
    window_dates = window[::-1]
    recent = with_value.loc[
        (with_value["date"] >= window[0])
        & with_value["code"].isin(predicted.index)
    ]
    n_series, n_dates = len(predicted), len(window_dates)
    pairs = pd.MultiIndex.from_arrays([
        np.repeat(predicted.index.to_numpy(), n_dates),
        np.tile(window_dates, n_series),
    ])
    known = pd.MultiIndex.from_frame(recent[["code", "date"]])
    is_present = pairs.isin(known).reshape(n_series, n_dates)
    # Dates before the first value of a series are not in its window.
    in_series = (
        np.tile(window_dates, (n_series, 1))
        >= predicted["min"].to_numpy()[:, None]
    )
    missing, closed = {}, {}
    # The dates with a value of each series, grouped once: filtering them per
    # series was quadratic with thousands of series.
    value_dates = pd.DatetimeIndex(with_value["date"])
    positions_by_code = None
    for row, code in enumerate(predicted.index):
        window_present = is_present[row][in_series[row]]
        if window_present.all():
            continue
        read, by_differentiation = _missing_read(
            missing_window = ~window_present,
            positions      = positions,
            order          = order,
            plan           = plan,
            inverse        = True,
        )
        if read:
            missing[_plain(names[code])] = (
                window_dates[np.asarray(read) - 1], by_differentiation
            )
            if positions_by_code is None:
                positions_by_code = with_value.groupby("code").indices
            closed[_plain(names[code])] = closed_weekdays(
                value_dates[positions_by_code[code]], profile.frequency
            )

    _report(missing, plan, profile, order, by_series=True, closed=closed)


def _on_series_grid(rows: pd.DataFrame, frequency: str) -> np.ndarray:
    """
    Return whether each row (`code`, `date`) is on the grid of the frequency
    of its series, which starts at the first date of the series, as `asfreq`
    puts each series on it in `reshape_series_long_to_dict`. Series that
    start on the same date share one grid.
    """
    dates = pd.DatetimeIndex(rows["date"])
    starts = rows.groupby("code")["date"].transform("min").to_numpy()
    on_grid = np.zeros(len(rows), dtype=bool)
    for start in pd.unique(starts):
        same = starts == start
        grid = pd.date_range(start, dates.max(), freq=frequency, unit=dates.unit)
        on_grid[same] = dates[same].isin(grid)

    return on_grid


def _read_positions(
    plan: ForecastPlan,
    limit: int,
) -> tuple[np.ndarray, int, int]:
    """
    Return the positions of the last window (1 is the last value) whose
    missing values the lags (or the equivalent dates) read to predict the
    `steps` dates, the order of the differentiation, and the size of the
    window the forecaster reads, at most `limit` (the length of the longest
    series: skforecast fails on a series shorter than its window).

    For the lag forecasters, a position is read when a lag reads one of the
    differenced values made from it at some step: lag `k` reads the
    differenced value `k - h + 1` at step `h` of a recursive forecaster
    (a prediction when `k < h`), and the differenced value `k` at every step
    of a direct one; the differenced value `q` is made of the values `q` to
    `q + order`. The window features and the inverse of the differentiation
    are handled in `_missing_read`. For ForecasterEquivalentDate, the value
    `offset * j` dates before each date to forecast, `j` from 1 to
    `n_offsets`, with the defaults of the generated code. The other
    forecasters read none.
    """
    kwargs = plan.forecaster_kwargs
    steps = plan.steps
    none = np.array([], dtype=int)
    if plan.forecaster == "ForecasterEquivalentDate":
        offset = kwargs.get("offset", 1)
        n_offsets = kwargs.get("n_offsets", 1)
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 1
            for value in (offset, n_offsets)
        ):
            return none, 0, 0
        size = min(offset * n_offsets, limit)
        # Only the offsets inside the window can be read.
        n_inside = min(n_offsets, -(-size // offset))
        positions = sorted({
            offset * j - (h - 1) % offset
            for j in range(1, n_inside + 1)
            for h in range(1, min(steps, offset) + 1)
        })
        positions = [position for position in positions if position <= size]
        return np.array(positions, dtype=int), 0, size
    if plan.forecaster not in AUTOREG_FORECASTERS:
        return none, 0, 0

    lags = kwargs.get("lags")
    if isinstance(lags, int) and not isinstance(lags, bool):
        max_lag = lags
        # Lags beyond the window plus the steps read nothing.
        lags = range(1, min(lags, limit + steps) + 1)
    else:
        lags = [int(lag) for lag in lags or []]
        max_lag = max(lags, default=0)
    order = int(kwargs.get("differentiation") or 0)
    windows = _window_sizes(kwargs.get("window_features"))
    size = min(max([max_lag] + windows) + order, limit)
    if not size:
        return none, order, 0
    # Differenced positions read by the lags (1 is the last one).
    read = np.zeros(size + 1, dtype=bool)
    for lag in lags:
        if plan.forecaster in DIRECT_FORECASTERS:
            if lag <= size:
                read[lag] = True
        else:
            read[max(1, lag - steps + 1):min(lag, size) + 1] = True
    # Value p is read when a differenced value from p - order to p is.
    counts = np.cumsum(read)
    positions = np.arange(1, size + 1)
    first = np.maximum(positions - order, 1)
    reached = counts[positions] - counts[first - 1] > 0

    return positions[reached], order, size


def _window_sizes(window_features: object) -> list[int]:
    """Return the window size of each entry of `window_features`."""
    sizes = []
    for entry in window_features or []:
        size = entry.get("window_size") if isinstance(entry, dict) else None
        if isinstance(size, int) and not isinstance(size, bool):
            sizes.append(size)
        elif isinstance(size, (list, tuple)):
            sizes.extend(int(value) for value in size)

    return sizes


def _missing_read(
    missing_window: np.ndarray,
    positions: np.ndarray,
    order: int,
    plan: ForecastPlan,
    inverse: bool,
) -> tuple[list[int], bool]:
    """
    Return the positions (1 is the last value) of the missing values of a
    series that its predictions read, and whether the inverse of the
    differentiation reads one of them. `missing_window` holds whether each
    value is missing, the last value first; positions beyond it are not
    read (the series is shorter).

    Besides the positions of `_read_positions`, the inverse of the
    differentiation reads the last `order` values when `inverse` (the
    series is predicted), and a window feature whose differenced values are
    all missing at the first step gives a missing predictor (the rolling
    statistics skip missing values otherwise), so its values are read too.
    """
    length = len(missing_window)
    missing = np.concatenate([[False], np.asarray(missing_window, dtype=bool)])
    read = {
        int(position) for position in positions
        if position <= length and missing[position]
    }
    by_differentiation = False
    if inverse and order:
        last = np.flatnonzero(missing[1:min(order, length) + 1]) + 1
        by_differentiation = bool(len(last))
        read.update(int(position) for position in last)
    windows = _window_sizes(plan.forecaster_kwargs.get("window_features"))
    if plan.forecaster in AUTOREG_FORECASTERS and windows and length:
        # Differenced value q is missing when one of the values q to
        # q + order is; a window of size w is all missing when the first w
        # differenced values are.
        counts = np.cumsum(missing)
        quantities = np.arange(1, length + 1)
        ends = np.minimum(quantities + order, length)
        differenced = counts[ends] - counts[quantities - 1] > 0
        leading = length if differenced.all() else int(np.argmin(differenced))
        for size in windows:
            if 1 <= size <= leading:
                read.update(
                    position for position in range(1, min(size + order, length) + 1)
                    if missing[position]
                )

    return sorted(read), by_differentiation


def _plain(value: object) -> object:
    """Return a numpy scalar as the Python value it holds, for messages."""
    return value.item() if isinstance(value, np.generic) else value


def _closed_weekdays_of(
    dates: pd.Index,
    present: np.ndarray,
    profile: DataProfile,
) -> list[int]:
    """
    Return the days of the week on which a series never has a value (see
    `closed_weekdays`), from its dates and whether each one has a value; an
    empty list without dates.
    """
    if not isinstance(dates, pd.DatetimeIndex):
        return []

    return closed_weekdays(dates[np.asarray(present, dtype=bool)], profile.frequency)


def _report(
    missing: dict,
    plan: ForecastPlan,
    profile: DataProfile,
    order: int,
    by_series: bool,
    where: str = "",
    closed: dict | None = None,
) -> None:
    """
    Raise for the missing values read by the predictions, or warn when the
    estimator tolerates missing values, as for the future exogenous
    variables. `missing` maps each series (its id when `by_series`, its
    column otherwise) to the dates of its missing values read and whether
    the inverse of the differentiation reads one. `where` names the test
    folds of a backtest that read them. `closed` maps each series to the
    days of the week on which it never has a value (see
    `closed_weekdays`): when every missing value read falls on them, the
    error names those days and says that a business closed on them can
    fill them with 0, after asking the user, as the errors of the
    evaluated dates do.
    """
    if not missing:
        return
    found = [f"{name!r}: {_where(dates)}" for name, (dates, _) in missing.items()]
    shown = "; ".join(found[:_SHOWN])
    if len(found) > _SHOWN:
        shown += f"; and {len(found) - _SHOWN} more series"
    series = "series " if by_series else ""
    message = (
        f"The forecaster reads missing values of the target to predict"
        f"{where} ({series}{shown})."
    )
    days = _closed_days(missing, closed or {})
    if days is not None:
        owner = "the target never has" if len(missing) == 1 else (
            "those series never have"
        )
        message += f" All of them are on {days}, when {owner} a value."

    def remedy(fill: str) -> str:
        """
        Put the advice of a business closed on those days first, and then
        `fill`, which says "imputed" there instead of "filled in".
        """
        if days is None:
            return fill[:1].upper() + fill[1:]
        imputed = fill.replace("filled in", "imputed")
        return f"{closed_days_remedy(days)}; otherwise, {imputed}"

    if plan.forecaster == "ForecasterEquivalentDate":
        raise DataContentError(
            f"{message} {plan.forecaster} repeats them as missing predictions. "
            f"{remedy('those values have to be filled in before predicting.')}",
            field = "data",
        )
    if any(by_differentiation for _, by_differentiation in missing.values()):
        # The inverse of the differentiation starts from them, so the
        # predictions are missing whatever the estimator.
        raise DataContentError(
            f"{message} The differentiation of {plan.forecaster} reads the "
            f"last {order} value(s), so its predictions would be missing. "
            f"{remedy('those values have to be filled in before predicting.')}",
            field = "data",
        )
    if plan.estimator not in NAN_TOLERANT_ESTIMATORS:
        estimator = tolerant_estimator_phrase(nan_tolerant_estimator(plan, profile))
        raise DataContentError(
            f"{message} {plan.forecaster} with {plan.estimator} cannot use "
            f"them, so its predictions would be missing. "
            + remedy(
                f"either they are filled in, or the plan uses {estimator}."
            ),
            field = "data",
        )
    warnings.warn(
        f"{message} {plan.estimator} treats them as missing values; check "
        f"that they are meant to be missing.",
        UserWarning,
        stacklevel = _caller_stacklevel(),
    )


def _closed_days(missing: dict, closed: dict) -> str | None:
    """
    Name the days of the week of the missing values read (`'Sundays'`) when
    every one of them falls on a day on which its series never has a value
    (`closed`, by series), None otherwise.
    """
    weekdays: set[int] = set()
    for name, (dates, _) in missing.items():
        if not isinstance(dates, pd.DatetimeIndex) or not closed.get(name):
            return None
        if not np.isin(dates.dayofweek, closed[name]).all():
            return None
        weekdays.update(int(day) for day in dates.dayofweek)

    return weekday_names(sorted(weekdays))


def _where(dates: pd.Index) -> str:
    """Describe the missing values of a series: how many, and their dates."""
    dates = dates.sort_values()
    if isinstance(dates, pd.DatetimeIndex):
        shown = _shown([_fmt_timestamp(date) for date in dates])
    else:
        shown = "index " + _shown(dates.tolist())

    return f"{len(dates)} value(s), such as {shown}"


def _final_rows(
    last_value: object,
    after: pd.Index,
    has_value: pd.Series,
    profile: DataProfile,
    plan: ForecastPlan,
    long_format: bool,
) -> None:
    """
    Raise for final rows of the data without a target value, or warn for
    ForecasterRecursiveMultiSeries, which drops them and forecasts the dates
    after the last value, the same predictions as without them.
    `last_value` is the date (or index) of the last value, `after` the date
    (or index) of every row of the data after it, and `has_value` whether
    each date of the target, as the generated code reads it, has a value in
    some series. The advice on `exog` is given when the plan uses exogenous
    variables.
    """
    if isinstance(after, pd.DatetimeIndex):
        shown = [_fmt_timestamp(value) for value in (last_value, after[0], after[-1])]
        prefix, their = "", "their dates"
    else:
        shown = [repr(_plain(value)) for value in (last_value, after[0], after[-1])]
        prefix, their = "index ", "them"
    span = shown[1] if after[0] == after[-1] else f"{shown[1]} to {shown[2]}"
    where = " in any series" if long_format else ""
    uses_exog = plan.use_exog and profile.exog_columns
    weekends = _weekends_without_value(after, has_value, profile)

    if plan.forecaster == "ForecasterRecursiveMultiSeries":
        exog = (
            ", reading their exogenous variables from `exog`" if uses_exog else ""
        )
        warnings.warn(
            f"The data has no target value{where} after {prefix}{shown[0]}: "
            f"{plan.forecaster} ignores its last {len(after)} row(s) "
            f"({prefix}{span}) and forecasts the dates after "
            f"{prefix}{shown[0]}{exog}. Drop those rows to avoid this "
            f"warning.{weekends}",
            UserWarning,
            stacklevel = _caller_stacklevel(),
        )
        return

    exog = (
        f"; to forecast {their}, pass their exogenous variables in `exog`"
        if uses_exog else ""
    )
    raise DataContentError(
        f"The data has no target value{where} after {prefix}{shown[0]}: drop "
        f"its last {len(after)} row(s) ({prefix}{span}), so that it ends with "
        f"the last value of the target{exog}.{weekends}",
        field = "data",
    )


def _weekends_without_value(
    after: pd.Index,
    has_value: pd.Series,
    profile: DataProfile,
) -> str:
    """
    Return the advice to drop every weekend row when the final rows of daily
    data are weekend days and no weekend day has a value (at least two of
    them before the last value): dropping only the final rows forecasts the
    weekend first, from its missing values, while the business days alone
    have a frequency of their own ('B'). An empty string otherwise.
    """
    if profile.frequency != "D" or not isinstance(after, pd.DatetimeIndex):
        return ""
    if not (after.dayofweek >= 5).all():
        return ""
    dates = pd.DatetimeIndex(has_value.index)
    weekend = np.asarray(dates.dayofweek >= 5)
    values = has_value.to_numpy(dtype=bool)
    if weekend.sum() - len(after.unique()) < 2 or values[weekend].any():
        return ""

    return (
        " Saturdays and Sundays never have a value: to forecast the business "
        "days, drop every Saturday and Sunday row instead, so that the data "
        "has a business-day frequency."
    )


def validate_infinite_target(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    prediction: bool,
) -> None:
    """
    Reject infinite values of the target that the forecaster cannot use.

    The estimators reject them inside the script ("Input contains
    infinity"), ForecasterStats predicts missing values from them or fails,
    and ForecasterEquivalentDate repeats the ones it reads as infinite
    predictions, so they raise before anything runs:

    - for every forecaster that is trained, whatever the mode;
    - for ForecasterEquivalentDate, in prediction mode, when its
      predictions read one (in evaluation and backtesting the metrics fail
      on them with their own error). One it does not read changes nothing.

    A ForecasterFoundation model takes the values as they are, and is not
    checked.

    Parameters
    ----------
    data : pandas DataFrame
        Data the forecaster runs on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Plan to run.
    prediction : bool
        Whether the run forecasts the future (prediction mode).

    Returns
    -------
    None
    """
    if plan.task_type == "foundation":
        return
    targets = profile.target if isinstance(profile.target, list) else [profile.target]
    columns = [
        column for column in dict.fromkeys(targets)
        if column in data.columns
        and pd.api.types.is_numeric_dtype(data[column].dtype)
        and not pd.api.types.is_bool_dtype(data[column].dtype)
    ]
    if not columns:
        return
    infinite = np.isinf(data[columns].to_numpy(dtype=float)).any(axis=1)
    if not infinite.any():
        return

    if plan.forecaster == "ForecasterEquivalentDate":
        if not prediction:
            return
        dates = _infinite_values_read(data, profile, plan)
        if not len(dates):
            return
        raise InvalidInputError(
            f"The forecaster reads infinite values of the target to predict "
            f"({_where(dates)}). {plan.forecaster} repeats them as infinite "
            f"predictions: replace them.",
            field = "data",
            hint  = "Replace the infinite values of the target, for example with NaN.",
        )

    dates = row_dates(data, profile.date_column, profile.date_format)
    labels = data.index if dates is None else dates
    raise InvalidInputError(
        f"The target has infinite values ({_where(labels[infinite])}). "
        f"{plan.forecaster} cannot be trained on them: replace them.",
        field = "data",
        hint  = "Replace the infinite values of the target, for example with NaN.",
    )


def _infinite_values_read(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> pd.Index:
    """
    Return the dates of the infinite values of a single series that the
    predictions of ForecasterEquivalentDate read, read as `_check_wide`
    reads the missing ones (from the last value of the series).
    """
    frames = _target_frame(data, profile)
    if frames is None:
        return pd.Index([])
    frame, _ = frames
    values = frame.iloc[:, 0].to_numpy(dtype=float)
    with_value = np.flatnonzero(~np.isnan(values))
    if not len(with_value):
        return pd.Index([])
    end = with_value[-1] + 1
    values = values[:end]
    positions, _, size = _read_positions(plan, limit=end)
    window = np.isinf(values[::-1][:size])
    read = [int(p) for p in positions if p <= len(window) and window[p - 1]]

    return frame.index[end - np.asarray(read, dtype=int)]


def validate_series_lengths(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    end_train: str | None = None,
    cv: TimeSeriesFold | None = None,
) -> None:
    """
    Reject series that ForecasterRecursiveMultiSeries cannot be trained on
    (in a backtest, series it cannot forecast in any fold), and series
    without values given to a ForecasterFoundation model.

    skforecast trains each series from its first to its last value, and
    fails inside the script on a series without values ("All values of
    series ... are NaN") and on one whose values, from its first to its last
    one, are not more than the window the forecaster reads ("Length of ...
    must be greater than the maximum window size"). A ForecasterFoundation
    model on several series fails the same way on a series without values,
    and reads no window. Both are checked before running (code
    `'insufficient_data'`):

    - in prediction mode, on the whole data;
    - in evaluation mode, on the training partition (up to `end_train`);
    - in backtesting (`cv` given), series without any value, and series of
      ForecasterRecursiveMultiSeries that no fold forecasts (see
      `_series_never_forecast`). skforecast leaves a series out of a fold
      without a warning, even with `suppress_warnings=False`
      (skforecast#1406): a series that starts late is forecast in the
      later folds, but one that no fold forecasts had missing metrics, no
      predictions, and an average across series computed without it.

    Parameters
    ----------
    data : pandas DataFrame
        Data the forecaster runs on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Plan to run.
    end_train : str, default None
        Last date of the training partition, in evaluation mode.
    cv : TimeSeriesFold, default None
        Strategy of a backtest, as the script runs it: the series are
        checked on its folds instead of on the whole data.

    Returns
    -------
    None
    """
    foundation = _foundation_on_several_series(plan, profile)
    if plan.forecaster != "ForecasterRecursiveMultiSeries" and not foundation:
        return
    spans = _series_spans(data, profile)
    if spans is None:
        return
    _, _, window = _read_positions(plan, limit=np.iinfo(np.int64).max)
    empty, short = [], {}
    for name, (dates, present) in spans.items():
        if end_train is not None and isinstance(dates, pd.DatetimeIndex):
            inside = dates <= training_end(end_train, dates.tz)
            dates, present = dates[inside], present[inside]
        if not present.any():
            empty.append(_plain(name))
            continue
        # skforecast trims the missing values at both ends of a series.
        first = int(np.argmax(present))
        last = len(present) - 1 - int(np.argmax(present[::-1]))
        length = last - first + 1
        # A foundation model reads no window: any series with a value does.
        if cv is None and not foundation and length <= window:
            short[_plain(name)] = length

    where = f" up to the end of training ({end_train})" if end_train is not None else ""
    if empty:
        cannot = (
            "has no values to predict them from" if foundation
            else "cannot be trained on them"
        )
        raise InvalidInputError(
            f"Some series have no values{where} ({_shown(empty)}), so "
            f"{plan.forecaster} {cannot}. Remove them from the data.",
            code  = "insufficient_data",
            field = "data",
            hint  = "Remove the series without values from the data.",
        )
    if short:
        found = [f"{name!r}: {length}" for name, length in short.items()]
        shown = ", ".join(found[:_SHOWN])
        if len(found) > _SHOWN:
            shown += f" and {len(found) - _SHOWN} more"
        raise InvalidInputError(
            f"Some series have, from their first to their last value{where}, "
            f"no more values than the {window} that {plan.forecaster} reads "
            f"to build its predictors ({shown}), so it cannot be trained on "
            f"them. Use shorter lags and window features, or remove those "
            f"series.",
            code  = "insufficient_data",
            field = "data",
            hint  = (
                f"Use lags and window features of at most {window - 1} "
                f"observations, or remove the short series."
            ),
        )
    if cv is not None and not foundation:
        order = int(plan.forecaster_kwargs.get("differentiation") or 0)
        # skforecast drops from a fold a last window with missing values
        # unless the estimator accepts them, and always with differentiation.
        dropna = bool(order) or plan.estimator not in NAN_TOLERANT_ESTIMATORS
        never = _series_never_forecast(
            spans  = spans,
            cv     = cv,
            window = window,
            long   = profile.data_format == "long",
            dropna = dropna,
        )
        short = {
            name: (length, ended)
            for name, (length, ended, read) in never.items() if read is None
        }
        if short:
            _report_never_forecast(short, plan, window)
        if never:
            _report_missing_last_windows(
                missing = {name: read for name, (_, _, read) in never.items()},
                plan    = plan,
                profile = profile,
                spans   = spans,
                window  = window,
                order   = order,
            )


class _SeriesFolds(NamedTuple):
    """
    Where a backtest of ForecasterRecursiveMultiSeries forecasts a series
    (see `_series_in_folds`).

    Attributes
    ----------
    forecast : numpy ndarray
        Whether each fold forecasts the series, by its training window and
        the dates of its last window.
    clean : numpy ndarray
        Whether the last window of each fold has no missing value between
        the first and the last value of the series; True in every fold when
        skforecast keeps the last windows with missing values.
    length : int
        Number of observations from its first to its last value.
    ended : bool
        Whether it ends before the window of the last fold.
    absent : numpy ndarray
        Positions on the span of its missing values between its first and
        its last value, when skforecast drops the last windows with missing
        values (empty otherwise).
    """

    forecast: np.ndarray
    clean: np.ndarray
    length: int
    ended: bool
    absent: np.ndarray


def _series_in_folds(
    spans: dict,
    cv: TimeSeriesFold,
    window: int,
    long: bool,
    dropna: bool,
) -> tuple[pd.DatetimeIndex, list, dict] | None:
    """
    Return the span the folds of a backtest of ForecasterRecursiveMultiSeries
    are split on, its folds (`TimeSeriesFold.split` with `as_pandas=False`)
    and, for each series with a value, the folds that forecast it
    (`_SeriesFolds`).

    skforecast forecasts a series in a fold when it was trained on it and
    it has a last window before the fold:

    - Trained: the training window of the fold (that of the last refit, the
      initial one without refit) holds more values of the series than the
      window of the forecaster, counted from its first to its last value
      there. skforecast keeps a series with exactly the window and then
      fails on it ("must be greater than the maximum window size"), which
      is not a silent drop.
    - Last window: in long format each series is its own dates, and the
      window before the fold must be inside them; in wide format every
      series has the dates of the frame. When skforecast drops a last
      window with missing values (`dropna`), the window must also be
      inside the dates from the first to the last value of the series: a
      series that starts late, or ends before the fold, is left out, and
      so is a series with a missing value between its first and its last
      value in that window.

    A series whose dates are off the grid of the span is left out. It
    returns None when the strategy cannot be split on the dates of the
    data (the check of the first training window reports it).
    """
    # The folds are split on the dates of every series, from the earliest
    # first date to the latest last one, as skforecast splits a dict.
    grids = [dates for dates, _ in spans.values()]
    if long:
        try:
            first = min(grid[0] for grid in grids if len(grid))
            last = max(grid[-1] for grid in grids if len(grid))
            span = pd.date_range(first, last, freq=grids[0].freq)
        except (ValueError, TypeError, AttributeError):
            return None
    else:
        span = grids[0]
    n_observations = len(span)

    # The window of the forecaster, with its differentiation order, as
    # skforecast sets it on the strategy of a backtest.
    splitter = copy.deepcopy(cv)
    splitter.set_params({"window_size": window, "verbose": False})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            folds = splitter.split(
                X=pd.Series(np.zeros(n_observations), index=span), as_pandas=False
            )
    except (ValueError, TypeError):
        return None
    if not folds:
        return None
    train = np.array([fold[1] for fold in folds], dtype=int)
    last_window = np.array([fold[2] for fold in folds], dtype=int)

    series = {}
    for name, (dates, present) in spans.items():
        present = np.asarray(present, dtype=bool)
        if not present.any():
            continue
        start = 0
        if long:
            start = int(span.get_indexer([dates[0]])[0])
            if start < 0:
                # Dates off the grid of the span, which skforecast cannot
                # put on one index either: not checked here.
                continue
        offset = start
        stop = start + len(present)
        values = np.flatnonzero(present) + start
        # Values of the series from its first to its last one inside the
        # training window of each fold.
        first_in = np.searchsorted(values, train[:, 0])
        last_in = np.searchsorted(values, train[:, 1]) - 1
        has_values = last_in >= first_in
        lengths = np.where(
            has_values,
            values[np.minimum(last_in, len(values) - 1)]
            - values[np.minimum(first_in, len(values) - 1)] + 1,
            0,
        )
        forecast = lengths > window
        if dropna:
            start, stop = max(start, values[0]), min(stop, values[-1] + 1)
        if long or dropna:
            # Dates of the series (or with values) in the last window.
            inside = (
                np.minimum(last_window[:, 1], stop)
                - np.maximum(last_window[:, 0], start)
            )
            forecast &= inside >= window
        absent = np.array([], dtype=int)
        clean = np.ones(len(folds), dtype=bool)
        if dropna:
            # A missing value between the first and the last value of the
            # series in a last window drops it from that fold too.
            absent = np.flatnonzero(~present) + offset
            absent = absent[(absent > values[0]) & (absent < values[-1])]
            clean = (
                np.searchsorted(absent, last_window[:, 1])
                - np.searchsorted(absent, last_window[:, 0])
            ) == 0
        series[_plain(name)] = _SeriesFolds(
            forecast = forecast,
            clean    = clean,
            length   = int(values[-1] - values[0] + 1),
            ended    = bool(stop < last_window[-1, 1]),
            absent   = absent,
        )

    return span, folds, series


def _series_never_forecast(
    spans: dict,
    cv: TimeSeriesFold,
    window: int,
    long: bool,
    dropna: bool,
) -> dict:
    """
    Return the series that ForecasterRecursiveMultiSeries forecasts in no
    fold of a backtest (see `_series_in_folds`), mapped to their number of
    observations from the first to the last value, whether they end before
    the window of the last fold, and the missing values that left them out.

    A missing value between the first and the last value of a series in a
    last window drops it from that fold too (`dropna`): a series left out
    of every fold it could be forecast in only for that is mapped to the
    dates of those missing values as well (None for the others), so its
    error says what fills them. It returns an empty dict when the strategy
    cannot be split on the dates of the data (the check of the first
    training window reports it).
    """
    split = _series_in_folds(spans, cv, window, long, dropna)
    if split is None:
        return {}
    span, folds, series = split
    last_window = np.array([fold[2] for fold in folds], dtype=int)

    never = {}
    for name, info in series.items():
        if not info.forecast.any():
            never[name] = (info.length, info.ended, None)
            continue
        if dropna and not (info.forecast & info.clean).any():
            # The missing values that dropped it from the folds it would be
            # forecast in otherwise.
            read = np.unique(np.concatenate([
                info.absent[(info.absent >= low) & (info.absent < high)]
                for low, high in last_window[info.forecast]
            ]))
            never[name] = (info.length, info.ended, span[read])

    return never


def _report_never_forecast(never: dict, plan: ForecastPlan, window: int) -> None:
    """
    Raise for the series that a backtest of ForecasterRecursiveMultiSeries
    forecasts in no fold (see `_series_never_forecast`).
    """
    found = [f"{name!r}: {length}" for name, (length, _) in never.items()]
    shown = ", ".join(found[:_SHOWN])
    if len(found) > _SHOWN:
        shown += f" and {len(found) - _SHOWN} more"
    n_short = sum(length <= window for length, _ in never.values())
    if n_short == len(never):
        rejected = " `forecast()` of this plan rejects them too."
    elif n_short:
        rejected = (
            f" `forecast()` of this plan rejects those with no more than "
            f"{window} too."
        )
    else:
        rejected = ""
    remedies = "Remove those series, or use shorter lags and window features"
    if any(length > window and not ended for length, ended in never.values()):
        # A series longer than the window that does not end before the
        # folds is left out because the training windows of the folds hold
        # too few of its observations.
        remedies += (
            ", or a later `initial_train_size`, so that the training windows "
            "hold more of their observations"
        )
    raise InvalidInputError(
        f"Some series cannot be forecast in any fold of the backtest ({shown} "
        f"observations, from their first to their last value). "
        f"{plan.forecaster} forecasts a series in a fold only when the "
        f"training window of the fold has more than the {window} observations "
        f"of it that it reads to build its predictors, and the series has the "
        f"{window} dates before the fold; skforecast leaves the other series "
        f"out without a warning, so they would get no predictions and no "
        f"metrics, and the average across series would leave them out."
        f"{rejected} {remedies}.",
        code  = "insufficient_data",
        field = "data",
        hint  = f"{remedies}.",
    )


def _report_missing_last_windows(
    missing: dict,
    plan: ForecastPlan,
    profile: DataProfile,
    spans: dict,
    window: int,
    order: int,
) -> None:
    """
    Raise for the series that a backtest of ForecasterRecursiveMultiSeries
    forecasts in no fold because the last window before every fold it could
    forecast has a missing value, which skforecast drops from the fold with
    an estimator that does not accept missing values, and always with the
    differentiation (see `_series_never_forecast`). `missing` maps each
    series to the dates of those missing values. When all of them fall on
    days of the week on which their series never has a value, the message
    names those days and says that a business closed on them can fill them
    with 0, after asking the user.
    """
    found = [f"{name!r}: {_where(dates)}" for name, dates in missing.items()]
    shown = "; ".join(found[:_SHOWN])
    if len(found) > _SHOWN:
        shown += f"; and {len(found) - _SHOWN} more series"
    closed = {
        name: _closed_weekdays_of(*spans[name], profile)
        for name in missing
    }
    days = _closed_days(
        {name: (dates, False) for name, dates in missing.items()}, closed
    )
    if order:
        why = (
            f"with the differentiation, {plan.forecaster} cannot predict from "
            f"a missing value whatever the estimator"
        )
    else:
        why = f"{plan.forecaster} with {plan.estimator} cannot predict from them"
    estimator = tolerant_estimator_phrase(nan_tolerant_estimator(plan, profile))
    if not order:
        works = f"{estimator} predicts from them"
    elif plan.estimator in NAN_TOLERANT_ESTIMATORS:
        works = "a plan without the differentiation predicts from them"
    else:
        works = (
            f"a plan without the differentiation and with {estimator} predicts "
            f"from them"
        )
    remedy = (
        f"{closed_days_remedy(days)}; otherwise, {works}, or impute them, or "
        f"remove those series."
        if days is not None else
        f"{works[:1].upper()}{works[1:]}; otherwise, fill them in the data, "
        f"after asking the user, or remove those series."
    )
    raise DataContentError(
        f"Some series cannot be forecast in any fold of the backtest: the "
        f"{window} values before every fold they could be forecast in have a "
        f"missing value ({shown}), and {why}. skforecast leaves them out of "
        f"those folds without a warning, so they would get no predictions and "
        f"no metrics, and the average across series would leave them out. "
        f"{remedy}",
        field = "data",
    )


def _foundation_on_several_series(plan: ForecastPlan, profile: DataProfile) -> bool:
    """
    Return whether the plan runs a ForecasterFoundation model on several
    series, which the generated code passes as a dict, one entry per series.
    """
    return plan.task_type == "foundation" and profile.n_series > 1


def _series_spans(
    data: pd.DataFrame,
    profile: DataProfile,
) -> dict | None:
    """
    Return, for each series as the generated code reads it (wide: the target
    columns on the grid of the frequency; long: each series on the grid from
    its first to its last date), its dates and whether each one has a value.
    None when the generated code cannot read the data.
    """
    if profile.data_format != "long":
        frames = _target_frame(data, profile)
        if frames is None:
            return None
        frame, _ = frames
        present = frame.notna().to_numpy()
        return {
            column: (frame.index, present[:, position])
            for position, column in enumerate(frame.columns)
        }

    date_column, series_id = profile.date_column, profile.series_id_column
    if (
        date_column not in data.columns
        or series_id not in data.columns
        or profile.target not in data.columns
        or not profile.frequency
    ):
        return None
    try:
        dates = pd.DatetimeIndex(
            row_dates(data, date_column, profile.date_format)
        )
        rows = pd.DataFrame({
            "series": data[series_id].to_numpy(),
            "date": dates,
            "value": pd.notna(data[profile.target].to_numpy()),
        }).dropna(subset=["series", "date"])
        rows = rows.drop_duplicates(["series", "date"], keep="first")
        # Positions of the rows of each series instead of a frame per
        # series: the dates of a series are unique here, so placing its
        # values on the grid by position is what `reindex` did, at a
        # fraction of the cost with hundreds of series.
        row_dates_index = pd.DatetimeIndex(rows["date"])
        row_values = rows["value"].to_numpy(dtype=bool)
        spans = {}
        for name, positions in rows.groupby("series", sort=False).indices.items():
            dates_of_series = row_dates_index[positions]
            grid = pd.date_range(
                dates_of_series.min(), dates_of_series.max(), freq=profile.frequency
            )
            on_grid = grid.get_indexer(dates_of_series)
            found = on_grid >= 0
            present = np.zeros(len(grid), dtype=bool)
            present[on_grid[found]] = row_values[positions][found]
            spans[name] = (grid, present)
    except (ValueError, TypeError):
        # The generated code fails on these dates with its own error.
        return None

    return spans


def validate_evaluation_partition(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> None:
    """
    Check the training partition of an evaluation-mode forecast.

    The script trains on the dates up to `plan.end_train` and predicts the
    `steps` dates after it, which the metrics compare by position. Checked
    before running:

    - ForecasterRecursiveMultiSeries: every series needs a value on the last
      training date and on each of the `steps` test dates. A series that
      ends earlier is not predicted (the metrics fail with "inconsistent
      numbers of samples"); when no series has a value there, it forecasts
      from an earlier date and the metrics compare other dates, without an
      error; a missing test value makes the metrics fail with "Input
      contains NaN".
    - ForecasterFoundation on several series: every series needs a value on
      each of the `steps` test dates, as above. The model takes the missing
      values of the training partition as they are, so a series without a
      value on the last training date is evaluated; one whose rows end
      before it (long format) is predicted from its own last date and has
      no test dates to compare.
    - Every forecaster with a window but ForecasterRecursiveMultiSeries
      (whose series `validate_series_lengths` checks one by one): the
      training partition must have more observations than the window, and
      a direct forecaster at least the window plus `steps`
      (`training_length_needed`). Otherwise skforecast fails when it fits
      ("Length `y`: 30. Max window size: 36"); here it is
      `'insufficient_data'` on `test_size`, with the longest horizon that
      fits.
    - Every forecaster: the missing values of the training partition that
      the predictions read follow the rule of the prediction mode
      (`validate_last_window`): an error when the estimator does not
      tolerate them, a warning when it does. Its last dates are not final
      rows here: `test_size` sets them.

    Parameters
    ----------
    data : pandas DataFrame
        Data the forecaster runs on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan, in evaluation mode (`plan.end_train` is set).

    Returns
    -------
    None
    """
    if plan.end_train is None:
        return
    _check_training_partition_length(profile, plan)
    dates = row_dates(data, profile.date_column, profile.date_format)
    if dates is None:
        return
    end = training_end(plan.end_train, dates.tz)
    try:
        in_training = np.asarray(dates <= end)
    except TypeError:
        # The generated code fails on these dates with its own error.
        return

    if (
        plan.forecaster == "ForecasterRecursiveMultiSeries"
        or _foundation_on_several_series(plan, profile)
    ):
        _check_multiseries_evaluation(data, profile, plan, end)

    training = data.loc[in_training]
    if not _per_series(plan, profile) and not (dates == end).any():
        # The script slices the regular grid up to `end_train`, where a
        # missing date is a missing value: it is added so the window ends
        # there too.
        training = _with_row_at(training, end, profile)

    validate_last_window(
        data       = training,
        profile    = profile,
        plan       = plan,
        final_rows = False,
    )


def _check_training_partition_length(
    profile: DataProfile,
    plan: ForecastPlan,
) -> None:
    """
    Reject an evaluation whose training partition (the dates of the grid of
    the data up to `end_train`) is too short for the forecaster to be
    fitted, with the longest horizon that fits in the data.
    """
    needed = training_length_needed(plan)
    if needed is None or plan.forecaster == "ForecasterRecursiveMultiSeries":
        return
    needed, reason = needed
    n_observations = profile.span_index_length
    try:
        n_test = count_test_observations(
            start_date     = profile.span_start_date,
            frequency      = profile.frequency,
            n_observations = n_observations,
            end_train      = plan.end_train,
            time_zone      = profile.time_zone,
        )
    except (ValueError, TypeError):
        # An `end_train` that cannot be placed on the dates (with a time
        # zone, on dates without one): the generated code fails on it with
        # its own error.
        return
    if n_test is None:
        return
    n_train = n_observations - n_test
    if n_train >= needed:
        return

    window = needed - (plan.steps if plan.forecaster in DIRECT_FORECASTERS else 1)
    if plan.forecaster in DIRECT_FORECASTERS:
        # Each step less adds one training observation and needs one less.
        max_steps = (n_observations - window) // 2
    else:
        max_steps = n_observations - window - 1
    features = (
        ", fewer lags or smaller window features"
        if plan.forecaster in AUTOREG_FORECASTERS else ""
    )
    if max_steps >= 1:
        hint = (
            f"Keeping the rest of the plan, at most {max_steps} `steps` fit: "
            f"make a plan with that horizon and pass the same number as "
            f"`test_size`. Otherwise use more data{features}."
        )
    else:
        hint = (
            f"No horizon fits in {n_observations} observations with this "
            f"plan: use more data{features}."
        )
    raise InvalidInputError(
        f"The training partition of the evaluation, up to {plan.end_train}, "
        f"has {n_train} observations, and {plan.forecaster} needs at least "
        f"{needed} ({reason}), so skforecast would fail. Evaluate a shorter "
        f"horizon (fewer `steps`, with `test_size` equal to them){features}.",
        code  = "insufficient_data",
        field = "test_size",
        hint  = hint,
    )


def _with_row_at(
    data: pd.DataFrame,
    date: pd.Timestamp,
    profile: DataProfile,
) -> pd.DataFrame:
    """
    Append a row dated `date` without values, dated as the data is (the
    date column, or the index).
    """
    row = pd.DataFrame({column: [np.nan] for column in data.columns})
    if profile.date_column is not None and profile.date_column in data.columns:
        row[profile.date_column] = [date]
        return pd.concat([data, row], ignore_index=True)
    row.index = pd.DatetimeIndex([date], name=data.index.name)
    return pd.concat([data, row])


def _check_multiseries_evaluation(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    end: pd.Timestamp,
) -> None:
    """
    Reject an evaluation of several series (ForecasterRecursiveMultiSeries,
    or a ForecasterFoundation model) whose series do not all have a value on
    the test dates and, for ForecasterRecursiveMultiSeries, on the last
    training date. When the missing test values all fall on days of the
    week on which their series never has a value (shops closed on Sundays),
    the message names those days and says that a business closed on them
    can fill them with 0, after asking the user.
    """
    needs_last_value = plan.forecaster == "ForecasterRecursiveMultiSeries"
    spans = _series_spans(data, profile)
    if spans is None or not profile.frequency:
        return
    try:
        test_dates = pd.date_range(
            start   = end,
            periods = plan.steps + 1,
            freq    = profile.frequency,
        )[1:]
    except (ValueError, TypeError):
        return
    ending, missing, closed = [], {}, {}
    for name, (dates, present) in spans.items():
        if not isinstance(dates, pd.DatetimeIndex):
            return
        with_value = pd.Series(present, index=dates)
        if not with_value[with_value.index <= end].any():
            # No value to train on: `validate_series_lengths` says so.
            continue
        if needs_last_value and not with_value.get(end, False):
            ending.append(_plain(name))
            continue
        absent = [
            date for date in test_dates if not with_value.get(date, False)
        ]
        if absent:
            missing[_plain(name)] = pd.DatetimeIndex(absent)
            closed[_plain(name)] = closed_weekdays(
                dates[np.asarray(present, dtype=bool)], profile.frequency
            )

    if ending:
        raise DataContentError(
            f"Some series have no value on the last training date "
            f"({plan.end_train}): {_shown(ending)}. {plan.forecaster} does not "
            f"predict a series that ends before the others, and when no series "
            f"has a value there it starts the forecast earlier, so the "
            f"metrics would compare other dates. Choose another `test_size`, "
            f"or fill in those values.",
            field = "test_size",
            hint  = (
                "Choose a `test_size` whose last training date has a value in "
                "every series, or fill in the missing values."
            ),
        )
    if missing:
        found = [f"{name!r}: {_where(dates)}" for name, dates in missing.items()]
        shown = "; ".join(found[:_SHOWN])
        if len(found) > _SHOWN:
            shown += f"; and {len(found) - _SHOWN} more series"
        # A series that ends before the test split has nothing to impute.
        ended = [name for name, dates in missing.items() if len(dates) == plan.steps]
        without_test = (
            f" Series without any value in the test split ({_shown(ended)}) "
            f"end before it: remove them from the data, or evaluate on dates "
            f"they reach."
            if ended else ""
        )
        # Missing values all on days of the week without any value in their
        # series are those of a business closed on them.
        if all(
            np.isin(dates.dayofweek, closed[name]).all()
            for name, dates in missing.items()
        ):
            days = weekday_names(
                sorted({day for dates in missing.values() for day in dates.dayofweek})
            )
            raise DataContentError(
                f"The target has missing values in the test split ({shown}), "
                f"all of them on {days}, when those series never have a "
                f"value. skforecast cannot compute the metrics on them, "
                f"whatever the estimator. {closed_days_remedy(days)}; "
                f"otherwise, impute the target, or evaluate on dates without "
                f"missing values.",
                field = "data",
            )
        raise DataContentError(
            f"The target has missing values in the test split ({shown}). "
            f"skforecast cannot compute the metrics on them, whatever the "
            f"estimator. Impute the target, or evaluate on dates without "
            f"missing values.{without_test}",
            field = "data",
        )


def validate_backtest_windows(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    cv: TimeSeriesFold,
) -> None:
    """
    Check the values of the target that the forecaster reads to predict each
    test fold of a backtest of a single series, or of the series of
    ForecasterDirectMultiVariate.

    Every fold is predicted from the values before it, as a forecast is from
    the last ones, and `dropna_from_series` only drops the missing values
    from the training matrices. A missing value (or a missing timestamp,
    which `asfreq()` restores as one) that a lag reads in a fold gave
    missing predictions and the metrics failed on them with "Input contains
    NaN", although the same plan forecasts when its last values are
    complete. ForecasterDirectMultiVariate never leaves a series out of the
    window it predicts from, so a missing value of any series there gave
    missing predictions of its level, which the metrics left out without a
    warning. The rule is that of the prediction mode
    (`validate_last_window`), applied to the window of each fold: an error
    when the estimator does not tolerate missing values, for
    ForecasterEquivalentDate and when the inverse of the differentiation
    reads them (that of the level, for ForecasterDirectMultiVariate); a
    warning with an estimator that tolerates them.

    ForecasterRecursiveMultiSeries is not checked here: its backtest drops
    the missing values per series (see `validate_series_lengths`). Data the
    generated code cannot read and a strategy that cannot be split on it
    are left to the error of the generated code.

    Parameters
    ----------
    data : pandas DataFrame
        Data the backtest runs on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Plan to backtest.
    cv : TimeSeriesFold
        Strategy of the backtest.

    Returns
    -------
    None
    """
    multivariate = plan.forecaster == "ForecasterDirectMultiVariate"
    if multivariate:
        if profile.data_format == "long" and profile.n_series > 1:
            # The generated code cannot read it.
            return
    elif profile.n_series != 1 or not isinstance(profile.target, str):
        return
    if not profile.missing_target and not profile.has_gaps:
        return
    frames = _target_frame(data, profile)
    if frames is None:
        return
    frame = frames[0]
    absent = frame.isna().to_numpy()
    if not absent.any():
        return

    original_verbose = cv.verbose
    cv.verbose = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            folds = cv.split(
                X         = frame if multivariate else frame[profile.target],
                as_pandas = True,
            )
    except (ValueError, TypeError):
        # The generated script fails on this strategy with its own error.
        return
    finally:
        cv.verbose = original_verbose

    if not multivariate:
        _check_training_rows(frame.index, absent[:, 0], folds, plan, profile)

    # The level of ForecasterDirectMultiVariate, as the generated code
    # writes it (`_get_target_str`): the inverse of the differentiation
    # reads only its values.
    level = profile.target[0] if isinstance(profile.target, list) else profile.target
    # The positions read depend on the steps predicted from the window, the
    # gap included: fewer in an incomplete last fold.
    read_by_steps: dict[int, tuple[np.ndarray, int, int]] = {}
    read: dict[object, set[int]] = {}
    by_differentiation = False
    n_folds = 0
    order = 0
    for start, end in zip(folds["test_start"], folds["test_end"]):
        start, end = int(start), int(end)
        if not absent[:start].any():
            continue
        n_steps = end - start
        if n_steps not in read_by_steps:
            read_by_steps[n_steps] = _read_positions(
                plan.model_copy(update={"steps": n_steps}), limit=len(frame)
            )
        positions, order, size = read_by_steps[n_steps]
        if not size:
            return
        in_fold = False
        for column_position, column in enumerate(frame.columns):
            found, differentiation = _missing_read(
                missing_window = absent[:start, column_position][::-1][:size],
                positions      = positions,
                order          = order,
                plan           = plan,
                inverse        = column == level,
            )
            if found:
                in_fold = True
                by_differentiation = by_differentiation or differentiation
                read.setdefault(column, set()).update(
                    start - position for position in found
                )
        n_folds += in_fold

    if not read:
        return
    columns = list(frame.columns)
    _report(
        missing   = {
            _plain(column): (frame.index[sorted(read[column])], by_differentiation)
            for column in columns if column in read
        },
        plan      = plan,
        profile   = profile,
        order     = order,
        by_series = False,
        where     = f" {n_folds} of the {len(folds)} test folds",
        closed    = {
            _plain(column): _closed_weekdays_of(
                frame.index, ~absent[:, columns.index(column)], profile
            )
            for column in columns if column in read
        },
    )


def validate_backtest_exog(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    cv: TimeSeriesFold,
) -> None:
    """
    Check the values of the exogenous variables that the forecaster reads to
    predict each test fold of a backtest.

    `dropna_from_series` only drops the training rows that have a missing
    value, and an estimator that does not accept missing values gives a
    missing prediction from one: the metrics of a single series failed on
    it with "Input contains NaN", and those of several series were computed
    without it, without a warning. As `forecast()` does with the future
    values (`validate_future_exog`), it raises before running, naming the
    columns and the dates, when a prediction that the metrics score would
    be missing:

    - Every forecaster reads the row of each date it predicts. A direct
      forecaster (a strategy with a gap is rejected for it) and
      ForecasterStats read nothing else.
    - A recursive forecaster also predicts the dates of the gap, and a
      missing prediction is read again: by a lag, by a window feature all
      of whose values are missing (the rolling statistics skip missing
      values otherwise) and, with the differentiation, by every later step,
      since its inverse adds them up.
    - With several series, only the series a fold forecasts (see
      `_series_in_folds`) and the dates where they have a value count: the
      metrics leave out the others. In long format each series reads its
      own exogenous values; in wide format they share them, and
      ForecasterDirectMultiVariate is scored on its level.

    A missing timestamp, which `asfreq()` restores as a row without values,
    counts as a missing value of every column. An estimator that accepts
    missing values, a ForecasterFoundation model (which takes them as they
    are) and a baseline (which reads no exogenous variables) are not
    checked, nor data the generated code cannot read and a strategy that
    cannot be split on it. Unlike the future values of `forecast()`,
    nothing warns with an estimator that accepts missing values: the
    profile already notes the missing values of each column.

    Parameters
    ----------
    data : pandas DataFrame
        Data the backtest runs on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Plan to backtest.
    cv : TimeSeriesFold
        Strategy of the backtest, as the script runs it.

    Returns
    -------
    None
    """
    if (
        plan.estimator in NAN_TOLERANT_ESTIMATORS
        or plan.forecaster == "ForecasterFoundation"
    ):
        return
    columns = [
        column for column in used_exog_columns(plan, profile)
        if column in data.columns
    ]
    if not columns:
        return
    if not profile.has_gaps and not any(
        profile.missing_exog.get(column) for column in columns
    ):
        return
    read = _exog_folds(data, profile, plan, cv, columns)
    if read is None:
        return
    n_folds, found, inserted = read
    if not found:
        return
    n_columns = len({column for column, _ in found})
    found = [text for _, text in found]

    shown = "; ".join(found[:_SHOWN])
    if len(found) > _SHOWN:
        shown += f"; and {len(found) - _SHOWN} more"
    timestamps = (
        ", counting the missing timestamps that asfreq() restores as rows "
        "without values" if inserted else ""
    )
    several = plan.task_type in ("multi_series", "multivariate")
    scored = (
        ", and skforecast would compute the metrics without them, without a "
        "warning" if several else ""
    )
    estimator = tolerant_estimator_phrase(nan_tolerant_estimator(plan, profile))
    or_tolerant = (
        f", or the plan uses {estimator}"
        if plan.forecaster in AUTOREG_FORECASTERS else ""
    )
    left_out = "the column is left" if n_columns == 1 else "the columns are left"
    raise DataContentError(
        f"The forecaster reads missing values of the exogenous variables to "
        f"predict {n_folds} ({shown}){timestamps}. {plan.forecaster} with "
        f"{plan.estimator} cannot use them, so its predictions would be "
        f"missing{scored}. Either they are filled in, after asking the "
        f"user{or_tolerant}, or {left_out} out of `exog_columns` when "
        f"profiling.",
        field = "data",
    )


def _exog_folds(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    cv: TimeSeriesFold,
    columns: list[str],
) -> tuple[str, list[tuple[str, str]], bool] | None:
    """
    Find the missing exogenous values that make a scored prediction of a
    backtest missing (see `validate_backtest_exog`). Return the test folds
    they are in (`'2 of the 12 test folds'`), the missing values read of
    each column (and series, in long format), as the column and its text,
    and whether one of them is a missing timestamp; None when the data or
    the strategy cannot be read.
    """
    multiseries = plan.forecaster == "ForecasterRecursiveMultiSeries"
    long = profile.data_format == "long"
    if long and profile.n_series > 1 and not multiseries:
        # The generated code cannot read it.
        return None
    if multiseries:
        spans = _series_spans(data, profile)
        if spans is None:
            return None
        spans = {_plain(name): span_of for name, span_of in spans.items()}
        _, _, window = _read_positions(plan, limit=np.iinfo(np.int64).max)
        # The forecaster of the plan does not accept missing values, so
        # skforecast drops the last windows that have one.
        split = _series_in_folds(spans, cv, window, long, dropna=True)
        if split is None:
            return None
        span, folds, in_folds = split
        predicted = {
            name: info.forecast & info.clean for name, info in in_folds.items()
        }
    else:
        frames = _target_frame(data, profile)
        if frames is None:
            return None
        frame = frames[0]
        span = frame.index
        level = (
            profile.target[0] if isinstance(profile.target, list) else profile.target
        )
        spans = {level: (span, frame[level].notna().to_numpy())}
        original_verbose = cv.verbose
        cv.verbose = False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                folds = cv.split(X=frame[level], as_pandas=False)
        except (ValueError, TypeError):
            # The generated script fails on this strategy with its own error.
            return None
        finally:
            cv.verbose = original_verbose
        predicted = {level: np.ones(len(folds), dtype=bool)}

    exog = _exog_on_span(data, profile, columns, span, spans, long and multiseries)
    if exog is None:
        return None

    recursive = plan.forecaster in (
        "ForecasterRecursive", "ForecasterRecursiveMultiSeries"
    )
    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags")
    if isinstance(lags, int) and not isinstance(lags, bool):
        lags = list(range(1, lags + 1))
    else:
        lags = [int(lag) for lag in lags or []]
    windows = _window_sizes(kwargs.get("window_features"))
    order = int(kwargs.get("differentiation") or 0)

    # In wide format the series share the exogenous values (`None`).
    per_series = long and multiseries
    has_value = {
        name: _on_span(present, dates, span, per_series)
        for name, (dates, present) in spans.items()
        if name in predicted
    }
    fold_numbers: set[int] = set()
    read: dict[tuple, set[int]] = {}
    inserted_read = False
    for number, fold in enumerate(folds):
        (test_start, _), (scored_start, scored_end) = fold[3], fold[4]
        first = test_start if recursive else scored_start
        in_fold = [name for name in predicted if predicted[name][number]]
        for owner, (missing, inserted) in exog.items():
            series = in_fold if owner is None else [owner] if owner in in_fold else []
            if not series:
                continue
            rows = {
                column: values[first:scored_end] for column, values in missing.items()
            }
            any_row = np.logical_or.reduce(list(rows.values()))
            if not any_row.any():
                continue
            if recursive:
                lost = _missing_predictions(any_row, lags, windows, order)
            else:
                lost = any_row
            # The predictions the metrics score: those of the dates where a
            # series forecast has a value.
            scored = lost[scored_start - first:] & np.logical_or.reduce([
                has_value[name][scored_start:scored_end] for name in series
            ])
            if not scored.any():
                continue
            fold_numbers.add(number)
            last = scored_start + int(np.flatnonzero(scored)[-1])
            for column, values in rows.items():
                if recursive:
                    positions = first + np.flatnonzero(values[:last - first + 1])
                else:
                    positions = scored_start + np.flatnonzero(
                        values[scored_start - first:] & scored
                    )
                if len(positions):
                    read.setdefault((column, owner), set()).update(
                        int(position) for position in positions
                    )
                    inserted_read = inserted_read or bool(inserted[positions].any())

    found = []
    for column in columns:
        for (read_column, owner), positions in read.items():
            if read_column != column:
                continue
            of_series = "" if owner is None else f" of series {owner!r}"
            dates = span[sorted(positions)]
            found.append(
                (column, f"{_plain(column)!r}{of_series}: {_where(dates)}")
            )
    where = f"{len(fold_numbers)} of the {len(folds)} test folds"

    return where, found, inserted_read


def _missing_predictions(
    missing_rows: np.ndarray,
    lags: list[int],
    windows: list[int],
    order: int,
) -> np.ndarray:
    """
    Return which predictions of a recursive forecaster are missing, in the
    order it predicts them, from the dates whose exogenous values are
    missing (`missing_rows`): a missing prediction is read by the lags that
    reach it, by a window feature whose values are all predictions and all
    missing, and, with the differentiation, makes every later prediction
    missing, as the inverse of the differentiation adds them up. The values
    of the last window before the fold are taken as present: a missing one
    that the predictions read raises before (`validate_backtest_windows`).
    """
    lost = np.asarray(missing_rows, dtype=bool).copy()
    if order:
        if lost.any():
            lost[int(np.argmax(lost)):] = True
        return lost
    for position in range(len(lost)):
        if lost[position]:
            continue
        if any(lag <= position and lost[position - lag] for lag in lags) or any(
            1 <= size <= position and lost[position - size:position].all()
            for size in windows
        ):
            lost[position] = True

    return lost


def _on_span(
    values: np.ndarray,
    dates: pd.DatetimeIndex,
    span: pd.Index,
    long: bool,
) -> np.ndarray:
    """
    Return the values of a series on the positions of the span its backtest
    is split on (False outside its dates): a series of long format is on
    its own dates, every other on those of the span.
    """
    values = np.asarray(values, dtype=bool)
    if not long:
        return values
    on_span = np.zeros(len(span), dtype=bool)
    start = int(span.get_indexer([dates[0]])[0])
    if start >= 0:
        on_span[start:start + len(values)] = values[:len(span) - start]

    return on_span


def _exog_on_span(
    data: pd.DataFrame,
    profile: DataProfile,
    columns: list[str],
    span: pd.Index,
    spans: dict,
    long: bool,
) -> dict | None:
    """
    Return, for each series that reads its own exogenous values (long
    format, only those with a missing value) or under None for the values
    every series shares, the missing values of each column on the positions
    of the span, and which positions are missing timestamps (`asfreq()`
    restores them as rows without values). None when the generated code
    cannot read the data.
    """
    if not long:
        frames = _target_frame(data, profile, columns)
        if frames is None:
            return None
        frame, present_index = frames
        if len(frame) != len(span) or not frame.index.equals(span):
            return None
        inserted = (
            ~frame.index.isin(present_index)
            if isinstance(frame.index, pd.DatetimeIndex)
            else np.zeros(len(frame), dtype=bool)
        )
        missing = {
            column: frame[column].isna().to_numpy() for column in frame.columns
        }
        return {None: (missing, np.asarray(inserted, dtype=bool))}

    date_column, series_id = profile.date_column, profile.series_id_column
    try:
        dates = pd.DatetimeIndex(row_dates(data, date_column, profile.date_format))
        rows = pd.DataFrame({
            "series": data[series_id].to_numpy(),
            "date": dates,
            **{
                f"missing_{position}": data[column].isna().to_numpy()
                for position, column in enumerate(columns)
            },
        }).dropna(subset=["series", "date"])
        rows = rows.drop_duplicates(["series", "date"], keep="first")
    except (KeyError, ValueError, TypeError):
        return None
    row_dates_index = pd.DatetimeIndex(rows["date"])
    exog = {}
    for name, positions in rows.groupby("series", sort=False).indices.items():
        name = _plain(name)
        if name not in spans:
            continue
        flags = rows.iloc[positions]
        if not any(flags[f"missing_{i}"].any() for i in range(len(columns))) and (
            len(positions) == len(spans[name][0])
        ):
            # No missing value and no missing timestamp to read.
            continue
        grid = spans[name][0]
        on_grid = grid.get_indexer(row_dates_index[positions])
        found = on_grid >= 0
        start = int(span.get_indexer([grid[0]])[0])
        if start < 0:
            continue
        stop = min(start + len(grid), len(span))
        inserted = np.zeros(len(span), dtype=bool)
        inserted[start:stop] = True
        inserted[start + on_grid[found]] = False
        missing = {}
        for i, column in enumerate(columns):
            values = inserted.copy()
            values[start + on_grid[found]] = flags[f"missing_{i}"].to_numpy()[found]
            missing[column] = values
        exog[name] = (missing, inserted)

    return exog


def validate_training_rows(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> None:
    """
    Check that the forecast of a single series has rows to train on.

    The forecaster of a plan whose estimator does not accept missing values
    drops the training rows that read one (`dropna_from_series`), and
    skforecast fails inside the script with "All samples have been removed
    due to NaNs" when none is left, with an advice
    (`dropna_from_series=False`) that the plan rejects for that estimator.
    The rule is that of the folds of a backtest (see `_check_training_rows`),
    applied to the rows the script trains on: the whole data in prediction
    mode, the training partition (up to `plan.end_train`) in evaluation
    mode.

    Several series are not checked, nor data the generated code cannot
    read.

    Parameters
    ----------
    data : pandas DataFrame
        Data the forecaster runs on.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Plan to run.

    Returns
    -------
    None
    """
    if profile.n_series != 1 or not isinstance(profile.target, str):
        return
    if not profile.missing_target and not profile.has_gaps:
        return
    frames = _target_frame(data, profile)
    if frames is None:
        return
    frame = frames[0]
    if plan.end_train is not None:
        if not isinstance(frame.index, pd.DatetimeIndex):
            return
        frame = frame.loc[
            frame.index <= training_end(plan.end_train, frame.index.tz)
        ]
    absent = frame[profile.target].isna().to_numpy()
    if not absent.any():
        return

    _check_training_rows(
        index   = frame.index,
        absent  = absent,
        folds   = pd.DataFrame({
                      "train_start": [0],
                      "train_end": [len(frame)],
                      "fit_forecaster": [True],
                  }),
        plan    = plan,
        profile = profile,
        run     = "forecast",
    )


def _check_training_rows(
    index: pd.Index,
    absent: np.ndarray,
    folds: pd.DataFrame,
    plan: ForecastPlan,
    profile: DataProfile,
    run: str = "backtest",
) -> None:
    """
    Raise when every training row of a fold of a single series reads a
    missing value of the target and the plan drops those rows
    (`dropna_from_series`, which the plan sets for an estimator that does
    not accept missing values): skforecast is left with nothing to train
    on and fails with "All samples have been removed due to NaNs", whose
    advice (`dropna_from_series=False`) the plan rejects for that estimator.

    A training row of target date `t` reads the differenced values of its
    lags and of its window features (whose statistics need every value of
    the window when training) and is dropped when its target is missing
    too. The training windows are those of the folds that train the
    forecaster (a forecast is one fold, trained on all its rows). The
    exogenous variables are not checked: the rows they drop only make this
    check pass where skforecast fails, never the other way round. `run`
    names what is trained in the message (`'backtest'`, `'forecast'`).
    """
    kwargs = plan.forecaster_kwargs
    if (
        plan.forecaster not in {"ForecasterRecursive", "ForecasterDirect"}
        or kwargs.get("dropna_from_series") is not True
    ):
        return
    lags = kwargs.get("lags")
    if isinstance(lags, int) and not isinstance(lags, bool):
        lags = list(range(1, lags + 1))
    else:
        lags = [int(lag) for lag in lags or []]
    windows = _window_sizes(kwargs.get("window_features"))
    order = int(kwargs.get("differentiation") or 0)
    window_size = max(lags + windows, default=0) + order
    n_values = len(absent)
    if not window_size or window_size >= n_values:
        return

    # A differenced value is missing when one of the `order + 1` values it
    # is made of is; the first `order` ones are never read.
    counts = np.concatenate([[0], np.cumsum(absent)])
    positions = np.arange(n_values)
    differenced = counts[positions + 1] - counts[np.maximum(positions - order, 0)] > 0
    differenced[:order] = True
    missing_counts = np.concatenate([[0], np.cumsum(differenced)])
    # Whether the predictors of target position `t` read no missing value.
    readable = np.zeros(n_values, dtype=bool)
    targets = positions[window_size:]
    readable[targets] = True
    for lag in lags:
        readable[targets] &= ~differenced[targets - lag]
    for size in windows:
        readable[targets] &= (
            missing_counts[targets] - missing_counts[targets - size] == 0
        )

    steps = plan.steps if plan.forecaster == "ForecasterDirect" else 1
    for start, end, fit in zip(
        folds["train_start"], folds["train_end"], folds["fit_forecaster"]
    ):
        if not fit:
            continue
        start, end = int(start), int(end)
        first, last = start + window_size, end - steps
        if last < first:
            # Too short a window, which skforecast reports itself.
            continue
        rows = readable[first:last + 1]
        # Every step of a direct forecaster needs a row whose target, `step
        # - 1` positions later, is not missing.
        trainable = all(
            (rows & ~differenced[first + step:last + step + 1]).any()
            for step in range(steps)
        )
        if trainable:
            continue
        in_window = np.flatnonzero(absent[start:end]) + start
        dates = index[in_window]
        days = _closed_days(
            {0: (dates, False)}, {0: _closed_weekdays_of(index, ~absent, profile)}
        )
        estimator = tolerant_estimator_phrase(nan_tolerant_estimator(plan, profile))
        shorter = "use shorter lags and window features, which read fewer values"
        remedy = (
            f"{closed_days_remedy(days)}; otherwise, {estimator} trains on "
            f"them, or {shorter}, or impute them."
            if days is not None else
            f"{estimator[:1].upper()}{estimator[1:]} trains on them; otherwise, "
            f"{shorter}, or fill in the missing values, after asking the user."
        )
        span = (
            f"{_fmt_timestamp(index[start])} to {_fmt_timestamp(index[end - 1])}"
            if isinstance(index, pd.DatetimeIndex)
            else f"index {_plain(index[start])!r} to {_plain(index[end - 1])!r}"
        )
        raise DataContentError(
            f"Every training row of the {run} from {span} reads a missing "
            f"value of the target ({_where(dates)}): {plan.forecaster} with "
            f"{plan.estimator} drops the rows whose lags, window features or "
            f"target read one (`dropna_from_series`), so skforecast would have "
            f"no row to train on. {remedy}",
            field = "data",
        )


def warn_backtest_missing_values(plan: ForecastPlan, profile: DataProfile) -> None:
    """
    Warn when a strategy is built for a plan whose backtest can fail on the
    missing values of the data (see `backtest_missing_values`). Where they
    are is not known without the data, so the warning says when the
    backtest fails and what avoids it, each case a condition: `backtest()`
    checks every fold of the target and of the exogenous columns before
    running (see `_check_evaluated_target`, `validate_backtest_windows` and
    `validate_backtest_exog`).

    Parameters
    ----------
    plan : ForecastPlan
        Plan the strategy is built for.
    profile : DataProfile
        Profile of the data.

    Returns
    -------
    None
    """
    missing_values = backtest_missing_values(plan, profile)
    if missing_values is None:
        return
    for message in backtest_missing_values_messages(missing_values, plan):
        warnings.warn(message, UserWarning, stacklevel=3)
