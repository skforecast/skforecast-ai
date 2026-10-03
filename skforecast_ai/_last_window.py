################################################################################
#                           Last window of the target                          #
#                                                                              #
# Checks of the last values of the target that forecast() reads                #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
import numpy as np
import pandas as pd

from ._constants import NAN_TOLERANT_ESTIMATORS
from ._dates import row_dates
from ._future_exog import _SHOWN, _per_series, _shown
from .exceptions import InvalidInputError
from .profiling.data_profile import _caller_stacklevel, _fmt_timestamp
from .schemas import DataProfile, ForecastPlan

# Forecasters whose model of each step reads the same last window: the lags
# never read a prediction.
_DIRECT_FORECASTERS = {"ForecasterDirect", "ForecasterDirectMultiVariate"}

# Forecasters whose predictors are lags, window features and differentiation.
_LAG_FORECASTERS = _DIRECT_FORECASTERS | {
    "ForecasterRecursive",
    "ForecasterRecursiveMultiSeries",
}

def validate_last_window(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> None:
    """
    Check the last values of the target that the forecaster reads to predict.

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
        Forecast plan, in prediction mode.

    Returns
    -------
    None
    """
    if _per_series(plan, profile):
        _check_long(data, profile, plan)
    elif profile.data_format != "long" or profile.n_series == 1:
        _check_wide(data, profile, plan)


def _check_wide(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
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
    if with_value[-1] < len(frame) - 1:
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
    missing = {}
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

    _report(missing, plan, order, by_series=False)


def _target_frame(
    data: pd.DataFrame,
    profile: DataProfile,
) -> tuple[pd.DataFrame, pd.Index] | None:
    """
    Return the target columns as the generated code reads them (in date
    order, the first row of a repeated date, on the grid of the frequency,
    `asfreq` inserting the missing dates; without dates, in the order of the
    index), and the index of the rows of the data. None when the data has
    not the target or the generated code cannot read it. The index of the
    rows holds every row, repeated dates and rows off the grid included.
    """
    targets = profile.target if isinstance(profile.target, list) else [profile.target]
    targets = list(dict.fromkeys(
        target for target in targets if target in data.columns
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
                index = pd.DatetimeIndex(row_dates(data, date_column)),
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
        dates = pd.DatetimeIndex(row_dates(data, date_column))
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
    if (rows["date"] > last_value).any():
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
    missing = {}
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

    _report(missing, plan, order, by_series=True)


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
    if plan.forecaster not in _LAG_FORECASTERS:
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
        if plan.forecaster in _DIRECT_FORECASTERS:
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
    if plan.forecaster in _LAG_FORECASTERS and windows and length:
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


def _report(
    missing: dict,
    plan: ForecastPlan,
    order: int,
    by_series: bool,
) -> None:
    """
    Raise for the missing values read by the predictions, or warn when the
    estimator tolerates missing values, as for the future exogenous
    variables. `missing` maps each series (its id when `by_series`, its
    column otherwise) to the dates of its missing values read and whether
    the inverse of the differentiation reads one.
    """
    if not missing:
        return
    found = [f"{name!r}: {_where(dates)}" for name, (dates, _) in missing.items()]
    shown = "; ".join(found[:_SHOWN])
    if len(found) > _SHOWN:
        shown += f"; and {len(found) - _SHOWN} more series"
    series = "series " if by_series else ""
    message = (
        f"The forecaster reads missing values of the target to predict "
        f"({series}{shown})."
    )
    if plan.forecaster == "ForecasterEquivalentDate":
        raise InvalidInputError(
            f"{message} {plan.forecaster} repeats them as missing predictions: "
            f"fill them in.",
            field = "data",
        )
    if any(by_differentiation for _, by_differentiation in missing.values()):
        # The inverse of the differentiation starts from them, so the
        # predictions are missing whatever the estimator.
        raise InvalidInputError(
            f"{message} The differentiation of {plan.forecaster} reads the "
            f"last {order} value(s), so its predictions would be missing: fill "
            f"them in.",
            field = "data",
        )
    if plan.estimator not in NAN_TOLERANT_ESTIMATORS:
        raise InvalidInputError(
            f"{message} {plan.forecaster} with {plan.estimator} cannot use "
            f"them, so its predictions would be missing: fill them in.",
            field = "data",
        )
    warnings.warn(
        f"{message} {plan.estimator} treats them as missing values; check "
        f"that they are meant to be missing.",
        UserWarning,
        stacklevel = _caller_stacklevel(),
    )


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
    raise InvalidInputError(
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

    dates = row_dates(data, profile.date_column)
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
