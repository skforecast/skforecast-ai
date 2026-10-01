################################################################################
#                               data profile                                   #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

import datetime
import os
import re
import sys
import warnings as _warnings
from pathlib import Path
import numpy as np
import pandas as pd
from dateutil import parser as dateutil_parser
from .._dates import (
    date_positions,
    guess_datetime_format,
    guessed_date_format,
    is_missing_date,
    is_text,
    missing_dates,
    parse_text_dates,
    row_dates,
    time_zones,
)
from ..schemas import DataProfile
from ..exceptions import InvalidInputError, InvalidInputTypeError

# TODO: Performance & Data Integrity - Lookahead Sampling
# Refactor `_try_parse_first_date_column` to test a small sample (e.g., 50 rows)
# before parsing the whole column. `pd.to_datetime` with `format="mixed"` is
# computationally expensive and can accidentally parse categorical text IDs as dates.

# TODO: Long Format Robustness - Fallback Series ID
# In `_extract_datetime_index`, if frequency inference fails on the first series ID,
# iterate through a few alternative series IDs before defaulting to None.

# TODO: Memory Optimization - Mask Filtering
# Optimize `_extract_datetime_index` to avoid creating heavy boolean masks 
# (e.g., `data[data[series_id] == id]`) on the entire DataFrame. Consider using
# lazy evaluation or `groupby().get_group()` to isolate the sample.

# TODO: Multi-Target Logic - Check All Target Dtypes
# In `create_data_profile`, `target_dtype` only checks the first target column. 
# For wide-format multi-series, it should verify if dtypes are mixed across targets 
# or return a dictionary mapping each target to its dtype.


# Consecutive timestamps per window when the frequency is inferred from the
# stretches between gaps. Long enough to tell a business day from a calendar
# day (a window must cross a weekend) and capped in number so the cost does
# not grow with the length of the series.
_FREQUENCY_WINDOW = 10
_MAX_FREQUENCY_WINDOWS = 200

# Minimum share of the regular grid that must be observed to accept a
# frequency inferred despite gaps. Below it the spacing is irregular rather
# than regular with missing timestamps.
_MIN_FREQUENCY_COVERAGE = 0.5


def infer_frequency(index: pd.DatetimeIndex) -> str | None:
    """
    Infer the frequency of a DatetimeIndex, tolerating missing timestamps.

    `pd.infer_freq` needs a gap-free index. When it fails, the frequency is
    inferred on windows of consecutive timestamps (the stretches between
    gaps), and the most frequent answer is accepted when every timestamp
    lies on its regular grid and at least half of that grid is observed.
    The missing timestamps are then reported by `detect_gaps()` and
    become NaN rows after `asfreq()`.

    Parameters
    ----------
    index : pandas DatetimeIndex
        The datetime index to infer frequency from.

    Returns
    -------
    frequency : str, None
        Inferred pandas frequency string, or None if the frequency cannot
        be determined (too few observations, or spacing that is irregular
        rather than regular with gaps).
    """
    if len(index) < 3:
        return None

    try:
        freq = pd.infer_freq(index)
    except (TypeError, ValueError):
        freq = None
    if freq is not None:
        return freq

    return _infer_frequency_with_gaps(index)


def _infer_frequency_with_gaps(index: pd.DatetimeIndex) -> str | None:
    """
    Infer a frequency from the gap-free stretches of a DatetimeIndex.

    Parameters
    ----------
    index : pandas DatetimeIndex
        Datetime index whose frequency `pd.infer_freq` could not infer.

    Returns
    -------
    frequency : str, None
        Frequency whose grid contains every timestamp and is at least
        `_MIN_FREQUENCY_COVERAGE` observed, or None.
    """
    index = pd.DatetimeIndex(index.dropna().unique()).sort_values()
    if len(index) < _FREQUENCY_WINDOW:
        return None

    starts = range(0, len(index) - _FREQUENCY_WINDOW + 1, _FREQUENCY_WINDOW)
    if len(starts) > _MAX_FREQUENCY_WINDOWS:
        positions = np.linspace(0, len(starts) - 1, _MAX_FREQUENCY_WINDOWS)
        starts = [starts[int(i)] for i in positions]

    candidates: dict[str, int] = {}
    for start in starts:
        try:
            freq = pd.infer_freq(index[start:start + _FREQUENCY_WINDOW])
        except (TypeError, ValueError):
            continue
        if freq is not None:
            candidates[freq] = candidates.get(freq, 0) + 1

    for freq in sorted(candidates, key=candidates.get, reverse=True):
        try:
            grid = pd.date_range(index[0], index[-1], freq=freq)
        except ValueError:
            continue
        if (
            len(index) >= _MIN_FREQUENCY_COVERAGE * len(grid)
            and index.isin(grid).all()
        ):
            return freq

    return None


def create_data_profile(
    data: pd.DataFrame | str | Path,
    target: str | list[str],
    date_column: str | None = None,
    series_id_column: str | None = None,
    data_path: str = "data.csv",
) -> DataProfile:
    """
    Generate a deterministic data profile from a dataset.

    Parameters
    ----------
    data : pandas DataFrame, str, Path
        Input dataset. If a string or Path, it is treated as a CSV file path
        and loaded with `pandas.read_csv`.
    target : str, list
        Name of the column to forecast. For wide-format multi-series data,
        pass a list of column names where each column is a series.
    date_column : str, default None
        Name of the column containing timestamps. If None, the function
        attempts to detect it from the index or columns.
    series_id_column : str, default None
        Name of the column identifying individual series in long format.
        If None and target is a string, the dataset is treated as a
        single series.
    data_path : str, default 'data.csv'
        Path to the source CSV file used in generated scripts.

    Returns
    -------
    profile : DataProfile
        Validated profile containing metadata, detected features, and
        warnings about the dataset.

    Notes
    -----
    A timestamp that appears in more than one row of the same series with
    different values raises a `ValueError` (for example long-format data
    profiled without `series_id_column`). Timestamps repeated in identical
    rows are dropped (the first row is kept, as in the generated script)
    and reported in `warnings`.

    Rows that are not in date order (within each series, for long format)
    are sorted before the frequency, the start date and the gaps are
    inferred, as the generated script sorts them, and a note is added to
    `warnings`. `index_is_monotonic` describes the input as given (False in
    that case), and `frequency_is_set` is False too: a frequency the input
    index carried (negative for descending dates) is not the one of the
    data.

    A CSV date column with empty cells, or whose dates mix UTC offsets,
    raises a `ValueError` that says so (see `_try_parse_first_date_column`).
    """
    if isinstance(data, (str, Path)):
        data = pd.read_csv(data)
        # Attempt to parse the first object-dtype column as datetime.
        # This handles CSVs exported with df.to_csv() where the date
        # index becomes a regular column.
        data = _try_parse_first_date_column(data, date_column)

    # Normalize a MultiIndex (level 0 = series_id, level 1 = datetime) into
    # flat long format so every downstream helper sees named columns.
    data, date_column, series_id_column = _normalize_multiindex(
        data, date_column, series_id_column
    )

    # Determine data format from user input
    data_format = _resolve_data_format(target, series_id_column)

    # Validate target columns exist
    _validate_target_exists(data, target)

    date_col, index_type = detect_date_column(data, date_column)

    # Text dates are parsed once, as the generated script parses the whole
    # column, so every check below reads the same dates. Parsed one by one,
    # '01/02/2012' is read month-first in a column of day-first dates.
    data = _parse_text_date_column(data, date_col)

    # Repeated timestamps are resolved before anything is measured: rows
    # that differ cannot be merged without losing data, and identical rows
    # are dropped here as the generated script drops them, so the profile
    # describes the data that is modeled.
    n_duplicate_timestamps, keep_mask = _check_duplicate_timestamps(
        data             = data,
        target           = target,
        date_col         = date_col,
        index_type       = index_type,
        data_format      = data_format,
        series_id_column = series_id_column,
    )
    if keep_mask is not None:
        data = data[keep_mask]
    has_duplicate_timestamps = n_duplicate_timestamps > 0

    # Extract a datetime index suitable for quality checks (frequency,
    # gaps, duplicates, monotonicity). For long format, use a single
    # representative series to avoid stacked dates breaking inference.
    datetime_index = _extract_datetime_index(
        data, date_col, index_type, data_format, series_id_column
    )
    # Both describe the index as it was given; see below for sorted rows.
    index_is_monotonic = _check_monotonic(datetime_index, data)
    frequency_is_set = _check_frequency_is_set(datetime_index, data)

    # Rows out of date order are sorted before anything is measured, as the
    # generated script sorts them: inferring the frequency, the start date
    # or the PACF on unsorted rows gives a wrong answer without any error
    # (a negative frequency and a zero span on descending dates).
    data, rows_sorted = _sort_rows_by_date(
                            data             = data,
                            date_col         = date_col,
                            index_type       = index_type,
                            data_format      = data_format,
                            series_id_column = series_id_column,
                        )
    if rows_sorted:
        # The index given was not in order, so a frequency it carried (a
        # negative one for descending dates) is not the one of the data.
        index_is_monotonic = False
        frequency_is_set = False
        datetime_index = _extract_datetime_index(
            data, date_col, index_type, data_format, series_id_column
        )

    frequency = infer_frequency(datetime_index) if datetime_index is not None else None

    # Compute n_series and per-series ranges (start, end, length)
    n_series, series_lengths = _compute_series_metrics(
        data, target, series_id_column, date_col, data_format, index_type
    )

    # Representative per-series length (shortest series) for data-quality
    # warnings such as the short-series check.
    representative_n = min(info["length"] for info in series_lengths.values())

    # Target dtype (use first target column for multi)
    first_target = target[0] if isinstance(target, list) else target
    target_dtype = detect_target_dtype(data, first_target)

    n_missing_timestamps = count_missing_timestamps(datetime_index, frequency)
    has_gaps = n_missing_timestamps > 0

    # Early stop: constant target makes forecasting meaningless
    if _check_target_is_constant(data, first_target):
        raise InvalidInputError(
            f"Target column '{first_target}' is constant (zero variance). "
            "Forecasting a constant series is not meaningful.",
            field = "target",
        )

    exog_columns = detect_exog_columns(
        data, target, date_col, series_id_column
    )
    categorical_exog = detect_categorical_exog(data, exog_columns)
    missing_target, missing_exog = count_missing_values(
        data, target, exog_columns, data_format, series_id_column
    )
    target_stats = compute_target_stats(data, target, data_format, series_id_column)

    warnings = generate_warnings(
        representative_n,
        frequency,
        missing_target,
        missing_exog,
        index_type,
        n_missing_timestamps   = n_missing_timestamps,
        n_duplicate_timestamps = n_duplicate_timestamps,
        rows_sorted            = rows_sorted,
        long_format            = data_format == "long",
    )

    # Compute start_date: the reference start for position-to-date
    # conversion.  For long format with multiple series that may have
    # different start dates, use the latest (max) start date so that
    # n_observations positions from start_date gives a date that
    # guarantees enough training data for the most constrained series.
    start_date: str | None = None
    if datetime_index is not None and len(datetime_index) > 0:
        ts = _resolve_start_date(
            data=data,
            datetime_index=datetime_index,
            data_format=data_format,
            series_id_column=series_id_column,
            date_col=date_col,
        )
        if ts.hour != 0 or ts.minute != 0 or ts.second != 0:
            start_date = str(ts)
        else:
            start_date = str(ts.date())

    return DataProfile(
        # Structure / Format
        data_format=data_format,
        n_series=n_series,
        series_lengths=series_lengths,
        # Target
        target=target,
        target_dtype=target_dtype,
        target_stats=target_stats,
        missing_target=missing_target,
        # Index / Time
        date_column=date_col,
        series_id_column=series_id_column,
        index_type=index_type,
        frequency=frequency,
        frequency_is_set=frequency_is_set,
        index_is_monotonic=index_is_monotonic,
        has_gaps=has_gaps,
        has_duplicate_timestamps=has_duplicate_timestamps,
        # Exogenous
        exog_columns=exog_columns,
        categorical_exog=categorical_exog,
        missing_exog=missing_exog,
        # Source
        data_path=data_path,
        # Train/test split
        start_date=start_date,
        # Diagnostics
        warnings=warnings,
    )


def _try_parse_first_date_column(
    data: pd.DataFrame,
    date_column: str | None = None,
) -> pd.DataFrame:
    """
    Try to convert the first object or string dtype column to datetime.

    When a CSV is exported via `DataFrame.to_csv()` the DatetimeIndex
    becomes a regular column with object or string dtype (e.g. `"Unnamed: 0"` or
    `"date"`). `pd.read_csv(parse_dates=True)` often fails to
    auto-parse these. This helper converts the first parseable column
    in-place so that downstream `detect_date_column` can identify it. The
    dates are parsed as the generated script parses them (see
    `parse_text_dates`).

    A column of dates with empty cells or with UTC offsets that change
    cannot be the date column (see `_read_date_column`). When it is the
    `date_column`, or no later column is converted, an error says why. When
    a later column is converted instead, a warning names the columns. The
    `date_column` is checked even when an earlier column was converted.

    Parameters
    ----------
    data : pandas DataFrame
        DataFrame loaded from CSV.
    date_column : str, default None
        Name of the date column, when the caller gives it.

    Returns
    -------
    data : pandas DataFrame
        DataFrame with the first date-like column converted (if found).
    """
    skipped = []
    for col in data.columns:
        if not is_text(data[col]):
            continue
        parsed, issue = _read_date_column(col, data[col], named=col == date_column)
        if issue is not None:
            if col == date_column:
                raise InvalidInputError("".join(issue), field="data")
            if date_column is None:
                skipped.append(issue)
            continue
        if parsed is None or parsed.isna().any():
            continue
        # A column without a day (times of day) does not take the place of a
        # date column that cannot be used.
        if skipped and not _has_date_part(_first_value(data[col])):
            continue
        data[col] = parsed
        if skipped:
            # The skipped columns may be exogenous variables, so the warning
            # says what was found and not how to fix a date column.
            found = " ".join(f"{summary}." for summary, _ in skipped)
            _warnings.warn(
                f"{found} Column {col!r} is used as the date column instead; "
                f"pass `date_column` to choose another one.",
                UserWarning,
                stacklevel=_caller_stacklevel(),
            )
        break
    else:
        if skipped:
            raise InvalidInputError(
                f"{''.join(skipped[0])} If the dates are in another column, "
                f"pass its name as `date_column`.",
                field = "data",
            )

    # The named column is checked even when an earlier column was parsed,
    # as with a saved profile nothing else checks it before the script runs.
    if (
        date_column is not None
        and date_column in data.columns
        and is_text(data[date_column])
    ):
        _, issue = _read_date_column(date_column, data[date_column], named=True)
        if issue is not None:
            raise InvalidInputError("".join(issue), field="data")

    return data


def _read_date_column(
    name: str,
    values: pd.Series,
    named: bool,
) -> tuple[pd.Series | None, tuple[str, str] | None]:
    """
    Parse a text column as the generated script does, and say why it cannot
    be the date column when its dates have empty cells or UTC offsets that
    change.

    Parameters
    ----------
    name : str
        Name of the column, for the message.
    values : pandas Series
        Values of the column: text, or date objects.
    named : bool
        Whether the caller named this column as the date column (see
        `_text_dates_issue`).

    Returns
    -------
    parsed : pandas Series, None
        The column parsed as `parse_text_dates` parses it (with NaT for the
        values that hold no date), or None when it does not parse or has an
        issue.
    issue : tuple, None
        Why the column holds dates but cannot be the date column, as what was
        found and how to fix it (see `_text_dates_issue`), or None.
    """
    # Most date columns parse with the format of their first date, with no
    # empty cell and one time zone: no further check needed.
    parsed = _parse_with_guessed_format(values)
    if parsed is not None:
        return parsed, None
    issue = _text_dates_issue(name, values, named)
    if issue is not None:
        return None, issue
    # Mixed offsets are reported below, so the pandas warning about them
    # would only repeat it.
    with _warnings.catch_warnings():
        _warnings.filterwarnings(
            action   = "ignore",
            message  = ".*mixed time zones",
            category = FutureWarning,
        )
        try:
            parsed = parse_text_dates(values)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return None, None
    # Offsets in a spelling `time_zones` does not read give pandas
    # Timestamps of several offsets.
    issue = _mixed_offsets_issue(name, parsed)

    return (None, issue) if issue is not None else (parsed, None)


def _parse_with_guessed_format(values: pd.Series) -> pd.Series | None:
    """
    Parse text dates with the format guessed from the first date, when every
    value follows it and the dates share one time zone; None otherwise.
    """
    date_format = guessed_date_format(values)
    if date_format is None:
        return None
    # Offsets that change give an object column, with a pandas warning.
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        try:
            parsed = pd.to_datetime(values, format=date_format)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return None
    if not pd.api.types.is_datetime64_any_dtype(parsed) or parsed.isna().any():
        return None

    return parsed


def _text_dates_issue(
    name: str,
    values: pd.Series,
    named: bool,
) -> tuple[str, str] | None:
    """
    Say why a column of dates cannot be the date column, from its text.

    A column holds dates when every cell that is not empty parses as a
    timestamp. It can be the date column only when no cell is empty and its
    dates share one UTC offset: a row without a date cannot be placed in the
    series, and dates written in local time change offset at a daylight
    saving time change, which pandas cannot place on one time axis.

    Parameters
    ----------
    name : str
        Name of the column, for the message.
    values : pandas Series
        Values of the column: text, or date objects.
    named : bool
        Whether the caller named this column as the date column. When
        False, the column must also look like a date column: its first date
        must clearly be one (see `_is_clearly_date`), so times of day,
        durations, codes or version numbers that pandas could read as dates
        do not count, and at least half of its cells must hold dates, so a
        sparse date-valued column (the end date of a promotion) stays an
        exogenous variable.

    Returns
    -------
    issue : tuple, None
        Why the column holds dates but cannot be the date column: what was
        found, and how to fix it, which joined make the message. None when
        it can, or when it does not hold dates.
    """
    # A cheap test first: the first value that is not empty must be a date.
    first = _first_value(values)
    if (
        first is None
        or (not named and not _is_clearly_date(first))
        or not _parses_as_date(pd.Series([first], dtype=object))
    ):
        return None

    try:
        missing = missing_dates(values)
        n_missing = int(missing.sum())
        present = values[~missing] if n_missing > 0 else values
        zones = time_zones(present)
        distinct = pd.Series(pd.unique(present.to_numpy()), dtype=object)
    except TypeError:
        # Unhashable values (lists) are not dates.
        return None
    if len(zones) <= 1 and n_missing == 0:
        return None
    if not named and 2 * n_missing > len(values):
        return None
    if not _parses_as_date(distinct):
        return None

    if len(zones) > 1:
        return _mixed_zones_message(name, zones)

    positions = np.flatnonzero(missing)
    shown = ", ".join(str(position) for position in positions[:5])
    if n_missing > 5:
        shown += f" and {n_missing - 5} more"

    return (
        f"The dates of column {name!r} have {n_missing} empty cell(s), at row "
        f"position(s) {shown} (counting from 0, header excluded)",
        ": every row needs a date. Fill in or drop those rows.",
    )


def _mixed_zones_message(name: str, zones: list[str]) -> tuple[str, str]:
    """
    Return the issue of dates of several time zones: what was found, and the
    advice that fits them.
    """
    shown = ", ".join(zones[:4]) + (", ..." if len(zones) > 4 else "")
    advice = (
        "in UTC for data recorded within the day, or without the time zone "
        "for daily or coarser data."
    )
    if "no time zone" in zones:
        advice += (
            " Some dates have no time zone that pandas reads (it drops zone "
            "names such as 'CET'), so they must be given one first."
        )
    elif all(zone[0] in "+-" for zone in zones):
        advice = (
            "in UTC for data recorded within the day "
            "(pandas.to_datetime(values, utc=True) converts them), or "
            "without the time zone for daily or coarser data."
        )

    return (
        f"The dates of column {name!r} mix time zones ({shown})",
        f", so they cannot be placed on one time axis (local time does that "
        f"across a daylight saving time change). Write every date in one time "
        f"zone: {advice}",
    )


def _mixed_offsets_issue(name: str, parsed: pd.Series) -> tuple[str, str] | None:
    """
    Say whether parsed dates hold several UTC offsets, which pandas returns
    as an object column of Timestamps.
    """
    if pd.api.types.is_datetime64_any_dtype(parsed):
        return None
    offsets: list[str] = []
    try:
        for value in pd.unique(parsed.dropna().to_numpy()):
            offset = value.utcoffset() if hasattr(value, "utcoffset") else None
            label = "no time zone" if offset is None else _format_offset(offset)
            if label not in offsets:
                offsets.append(label)
    except TypeError:
        return None

    return _mixed_zones_message(name, offsets) if len(offsets) > 1 else None


def _format_offset(offset: datetime.timedelta) -> str:
    """
    Return a UTC offset as '+HH:MM'.
    """
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    hours, minutes = divmod(abs(minutes), 60)

    return f"{sign}{hours:02d}:{minutes:02d}"


def _parses_as_date(values: pd.Series) -> bool:
    """
    Return whether every value parses as a timestamp.

    Only text and date objects count as dates. They are parsed in UTC, so
    the check passes for mixed time zones, without pandas warnings. The
    format of the first date is tried first, read month-first and
    day-first, as it is fast; each date is parsed on its own only when
    neither fits.
    """
    if not all(isinstance(value, (str, datetime.date)) for value in values.iloc[:1]):
        return False
    text = values.astype(str)
    first = text.iloc[0]
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        date_formats = [
            guess_datetime_format(first, dayfirst=dayfirst)
            for dayfirst in (False, True)
        ]
        for date_format in [*dict.fromkeys(date_formats), "mixed"]:
            if date_format is None:
                continue
            try:
                parsed = pd.to_datetime(text, utc=True, format=date_format)
            except (ValueError, TypeError, AttributeError, OverflowError):
                continue
            if parsed.notna().all():
                return True

    return False


# Day, month and a year of four digits, as numbers ('13/01/2012',
# '2012.01.13') or with the name of the month ('13 Jan 2012').
_DAY_MONTH_YEAR = re.compile(
    r"(?<!\d)(?:\d{1,2}[/.-]\d{1,2}[/.-](?:1[6-9]|2\d)\d{2}"
    r"|(?:1[6-9]|2\d)\d{2}[/.-]\d{1,2}[/.-]\d{1,2})(?!\d)"
    r"|(?i:\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b)"
    r".*(?<!\d)(?:1[6-9]|2\d)\d{2}(?!\d)"
)
# Directory of the package, to tell its frames from those of the caller.
_PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep


def _is_clearly_date(value: object) -> bool:
    """
    Return whether a value is clearly a date: a date object, or text with a
    day, a month and a year of four digits (the format pandas guesses for
    it holds '%Y' and a month, or the text reads so). Times of day
    ('09:30'), durations ('01:30 hrs'), codes ('2019/1'), years ('1990')
    and version numbers ('4.17.21') are not.
    """
    if not isinstance(value, str):
        return isinstance(value, datetime.date)
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        date_format = guessed_date_format(pd.Series([value], dtype=object))
    if date_format is not None:
        return "%Y" in date_format and any(
            directive in date_format for directive in ("%m", "%b", "%B")
        )

    return bool(_DAY_MONTH_YEAR.search(value))


def _has_date_part(value: object) -> bool:
    """
    Return whether a value holds a date, not only a time of day ('09:30').

    The text is parsed with two default dates: a year that changes with the
    default was not written. Text that dateutil cannot parse counts as a
    date, as pandas may read it.
    """
    if not isinstance(value, str):
        return True
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        try:
            first = dateutil_parser.parse(value, default=datetime.datetime(2000, 1, 1))
            second = dateutil_parser.parse(value, default=datetime.datetime(2001, 2, 2))
        except (ValueError, OverflowError, TypeError, AttributeError):
            return True

    return first.year == second.year


def _first_value(values: pd.Series) -> object:
    """
    Return the first value that is not empty, or None.
    """

    return next((value for value in values if not is_missing_date(value)), None)


def _caller_stacklevel() -> int:
    """
    Return the stacklevel of the first frame outside skforecast_ai, so a
    warning raised here points at the call of the user, and is shown once
    however many times the package reads the data.
    """
    level, frame = 1, sys._getframe(1)
    while frame is not None and frame.f_code.co_filename.startswith(_PACKAGE_DIR):
        level += 1
        frame = frame.f_back

    return level


def _is_datetime_like(values: pd.Series | pd.Index) -> bool:
    """
    Check whether a Series or Index holds (or parses to) datetimes.

    Parameters
    ----------
    values : pandas Series, pandas Index
        Values to inspect.

    Returns
    -------
    is_datetime_like : bool
        True if the values are already datetime-typed, or if every value
        is parseable as a datetime. False otherwise.
    """
    if pd.api.types.is_datetime64_any_dtype(values):
        return True
    if not (
        pd.api.types.is_object_dtype(values)
        or pd.api.types.is_string_dtype(values)
    ):
        return False
    try:
        parsed = pd.to_datetime(values, format="mixed", errors="coerce")
    except (ValueError, TypeError):
        return False
    return bool(parsed.notna().all())


def _unparsable_dates(values: pd.Series, n: int = 3) -> list[str]:
    """
    Quote the first values that cannot be parsed as timestamps.

    Parameters
    ----------
    values : pandas Series
        Values of the column or index named as the date source.
    n : int, default 3
        Largest number of values to quote.

    Returns
    -------
    examples : list of str
        Up to `n` distinct values that do not parse, or the first values
        when the column is not text (numbers are not read as dates) or
        every value parses (text dates in an index that was not converted).
    """
    if not (
        pd.api.types.is_object_dtype(values)
        or pd.api.types.is_string_dtype(values)
    ):
        return [str(value) for value in values.head(n)]
    parsed = pd.to_datetime(values, format="mixed", errors="coerce")
    failed = values[parsed.isna() & values.notna()]
    if failed.empty:
        return [str(value) for value in values.head(n)]

    return [str(value) for value in failed.unique()[:n]]


def detect_date_column(
    data: pd.DataFrame,
    date_column: str | None,
) -> tuple[str | None, str]:
    """
    Detect the datetime column and determine the index type.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    date_column : str, default None
        User-specified date column name.

    Returns
    -------
    resolved_column : str, None
        Name of the date column if a datetime-like column is used, None if
        the index is the datetime source or no datetime is found.
    index_type : str
        One of `'datetime'`, `'range'`, `'other'`.

    Raises
    ------
    ValueError
        If `date_column` is provided but matches neither a column nor the
        index name, or does not hold dates.

    Notes
    -----
    Passing `date_column` does not assume the source is datetime. The
    referenced column or index is validated with `_is_datetime_like`; when
    it does not hold dates a `ValueError` quotes values that could not be
    parsed, instead of treating the column as an exogenous variable. A text
    column of dates with empty cells or with time zones that change raises
    a `ValueError` that says so.
    """
    if date_column is not None:
        if date_column in data.columns:
            values = data[date_column]
            if is_text(values):
                # Checked first: a column with empty cells or mixed time
                # zones holds dates, so the message below would be wrong.
                _, issue = _read_date_column(date_column, values, named=True)
                if issue is not None:
                    raise InvalidInputError("".join(issue), field="data")
            if _is_datetime_like(values):
                return date_column, "datetime"
            raise InvalidInputError(
                f"date_column='{date_column}' does not hold dates: values "
                f"such as {_unparsable_dates(data[date_column])} could not be "
                f"parsed as timestamps. Pass the column that holds the dates, "
                f"or convert it with pandas.to_datetime before profiling.",
                field = "date_column",
            )
        if data.index.name == date_column:
            # The user pointed `date_column` at the index (e.g. after
            # `set_index(date_column)`). Downstream uses the index only
            # when it is a real DatetimeIndex.
            if isinstance(data.index, pd.DatetimeIndex):
                return None, "datetime"
            raise InvalidInputError(
                f"date_column='{date_column}' names the index, which is not a "
                f"DatetimeIndex (values such as "
                f"{_unparsable_dates(data.index.to_series())}). Convert it "
                f"with pandas.to_datetime before profiling, or omit "
                f"date_column.",
                field = "date_column",
            )
        available = list(data.columns)
        raise InvalidInputError(
            f"date_column='{date_column}' was not found in the data. It "
            f"matches neither a column {available} nor the index name "
            f"('{data.index.name}'). Pass a valid column name, set it as "
            "the index, or omit date_column to use an existing "
            "DatetimeIndex.",
            field = "date_column",
        )

    if isinstance(data.index, pd.DatetimeIndex):
        return None, "datetime"

    for col in data.columns:
        if pd.api.types.is_datetime64_any_dtype(data[col]):
            return col, "datetime"

    if isinstance(data.index, pd.RangeIndex):
        return None, "range"

    return None, "other"


def _normalize_multiindex(
    data: pd.DataFrame,
    date_column: str | None,
    series_id_column: str | None,
) -> tuple[pd.DataFrame, str | None, str | None]:
    """
    Flatten a MultiIndex DataFrame into long format.

    A two-level MultiIndex is interpreted as `(series_id, datetime)`:
    level 0 identifies the series and level 1 is the datetime index.
    The levels are reset into regular columns so that all downstream
    profiling helpers operate on a flat long-format DataFrame.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset. Returned unchanged if its index is not a
        MultiIndex with at least two levels.
    date_column : str, None
        User-specified date column name. Filled from level 1 when None.
    series_id_column : str, None
        User-specified series identifier column. Filled from level 0
        when None.

    Returns
    -------
    data : pandas DataFrame
        Flattened DataFrame (or the original if no MultiIndex).
    date_column : str, None
        Resolved date column name.
    series_id_column : str, None
        Resolved series identifier column name.
    """
    if not isinstance(data.index, pd.MultiIndex) or data.index.nlevels < 2:
        return data, date_column, series_id_column

    names = list(data.index.names)
    id_name = names[0] if names[0] is not None else "series_id"
    date_name = names[1] if names[1] is not None else "datetime"

    data = data.copy()
    data.index = data.index.set_names([id_name, date_name])
    data = data.reset_index()

    if series_id_column is None:
        series_id_column = id_name
    if date_column is None:
        date_column = date_name

    return data, date_column, series_id_column


def _resolve_data_format(
    target: str | list[str],
    series_id_column: str | None,
) -> str:
    """
    Derive the data format from user-provided arguments.

    Parameters
    ----------
    target : str, list
        Target column name(s).
    series_id_column : str, None
        Series identifier column for long format.

    Returns
    -------
    data_format : str
        One of `'single'`, `'wide'`, `'long'`.
    """
    if isinstance(target, list):
        return "wide"
    if series_id_column is not None:
        return "long"
    return "single"


def _fmt_timestamp(ts: pd.Timestamp) -> str:
    """
    Format a timestamp as a date string, keeping the time part if present.

    Parameters
    ----------
    ts : pandas Timestamp
        Timestamp to format.

    Returns
    -------
    formatted : str
        `'YYYY-MM-DD'` when the time component is midnight, otherwise the
        full timestamp string.
    """
    ts = pd.Timestamp(ts)
    if ts.hour != 0 or ts.minute != 0 or ts.second != 0:
        return str(ts)
    return str(ts.date())


def _frame_index_bounds(
    frame: pd.DataFrame,
    date_col: str | None,
    datetime_available: bool,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """
    Return the first and last timestamps of a frame's datetime source.

    Parameters
    ----------
    frame : pandas DataFrame
        Frame (or per-series group) to inspect.
    date_col : str, None
        Resolved date column name. When None, the frame index is used.
    datetime_available : bool
        Whether a datetime source exists at all.

    Returns
    -------
    start : pandas Timestamp, None
        Minimum timestamp, or None when no datetime source exists.
    end : pandas Timestamp, None
        Maximum timestamp, or None when no datetime source exists.
    """
    if not datetime_available:
        return None, None
    if date_col is not None and date_col in frame.columns:
        col = pd.to_datetime(frame[date_col])
        return col.min(), col.max()
    if isinstance(frame.index, pd.DatetimeIndex):
        return frame.index.min(), frame.index.max()
    return None, None


def _compute_series_metrics(
    data: pd.DataFrame,
    target: str | list[str],
    series_id_column: str | None,
    date_col: str | None,
    data_format: str,
    index_type: str,
) -> tuple[int, dict[str, dict]]:
    """
    Compute the number of series and per-series index ranges.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Target column name(s).
    series_id_column : str, None
        Series identifier column for long format.
    date_col : str, None
        Resolved date column name.
    data_format : str
        One of `'single'`, `'wide'`, `'long'`.
    index_type : str
        One of `'datetime'`, `'range'`, `'other'`.

    Returns
    -------
    n_series : int
        Number of individual time series.
    series_lengths : dict
        Mapping of series name to a dict with keys `'start'`, `'end'`,
        and `'length'`. Always populated, including single series.
    
    """

    datetime_available = index_type == "datetime"

    def _range(frame: pd.DataFrame, length: int) -> dict:
        start, end = _frame_index_bounds(frame, date_col, datetime_available)
        return {
            "start": _fmt_timestamp(start) if start is not None else None,
            "end": _fmt_timestamp(end) if end is not None else None,
            "length": int(length),
        }

    if data_format == "wide":
        target_cols = target if isinstance(target, list) else [target]
        # All series share the same index, so each spans the full frame.
        series_lengths = {col: _range(data, len(data)) for col in target_cols}
        return len(target_cols), series_lengths

    if (
        data_format == "long"
        and series_id_column is not None
        and series_id_column in data.columns
    ):
        series_lengths = {
            str(name): _range(group, len(group))
            for name, group in data.groupby(series_id_column)
        }
        return len(series_lengths), series_lengths

    # Single series (or long fallback when series_id_column is absent)
    target_name = target[0] if isinstance(target, list) else target
    series_lengths = {str(target_name): _range(data, len(data))}
    return 1, series_lengths


def _parse_text_date_column(data: pd.DataFrame, date_col: str | None) -> pd.DataFrame:
    """
    Return `data` with its text date column parsed as the generated script
    parses it, or `data` itself when the dates are not text.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    date_col : str, None
        Resolved date column name.

    Returns
    -------
    data : pandas DataFrame
        A copy with the parsed dates, or the same object.
    """
    if date_col is None or date_col not in data.columns:
        return data
    values = data[date_col]
    if not (
        pd.api.types.is_object_dtype(values) or pd.api.types.is_string_dtype(values)
    ):
        return data

    data = data.copy()
    data[date_col] = parse_text_dates(values, mixed=False)

    return data


def _sort_rows_by_date(
    data: pd.DataFrame,
    date_col: str | None,
    index_type: str,
    data_format: str,
    series_id_column: str | None,
) -> tuple[pd.DataFrame, bool]:
    """
    Sort the rows by date when they are not in date order.

    Rows count as unsorted when a date is earlier than a previous one (of
    the same series, for long format); missing dates are ignored. Sorted
    data is returned unchanged, so profiling it gives the same result as
    before. Unsorted data is sorted with a stable sort: by date, and for
    long format by series (in order of first appearance, rows without a
    series id last) and then by date, so the first series stays the same.
    When the rows are sorted, those without a date go last.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset, without repeated timestamps.
    date_col : str, None
        Resolved date column name. When None, the DataFrame index is used.
    index_type : str
        One of `'datetime'`, `'range'`, `'other'`.
    data_format : str
        One of `'single'`, `'wide'`, `'long'`.
    series_id_column : str, None
        Series identifier column (only relevant for long format).

    Returns
    -------
    data : pandas DataFrame
        The input, sorted by date when it was not.
    rows_sorted : bool
        Whether the rows were out of date order and were sorted.
    """
    dates = row_dates(data, date_col) if index_type == "datetime" else None
    if dates is None:
        return data, False

    missing = np.asarray(dates.isna())
    positions = date_positions(dates)
    if (
        data_format == "long"
        and series_id_column is not None
        and series_id_column in data.columns
    ):
        # Rows without a series id (code -1) belong to no series: they are
        # left out of the check, as the series ignore them.
        codes = pd.factorize(data[series_id_column])[0]
        checked = ~missing & (codes >= 0)
        steps = (
            pd.Series(positions[checked])
            .groupby(codes[checked])
            .diff()
        )
        unsorted = bool((steps < 0).any())
        # Rows without an id go after every series, so the series of the
        # first row, which stands for the data, is still a real one.
        keys = (positions, np.where(codes < 0, codes.max() + 1, codes))
    else:
        unsorted = bool((np.diff(positions[~missing]) < 0).any())
        keys = (positions,)
    if not unsorted:
        return data, False

    # `np.lexsort` sorts by the last key first and is stable.
    order = np.lexsort(keys)
    data = data.iloc[order]
    if date_col is not None and date_col in data.columns:
        # The parsed dates are kept: text dates parsed again from another
        # first row could be read with another format.
        data = data.copy()
        data[date_col] = dates[order]

    return data, True


def _extract_datetime_index(
    data: pd.DataFrame,
    date_col: str | None,
    index_type: str,
    data_format: str,
    series_id_column: str | None,
) -> pd.DatetimeIndex | None:
    """
    Extract a representative DatetimeIndex for quality checks.

    For single and wide formats, the index comes directly from the
    DataFrame's index or a detected date column. For long format,
    uses the first series to avoid stacked dates from multiple series
    breaking frequency inference and duplicate detection.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    date_col : str, None
        Resolved date column name.
    index_type : str
        One of `'datetime'`, `'range'`, `'other'`.
    data_format : str
        One of `'single'`, `'wide'`, `'long'`.
    series_id_column : str, None
        Series identifier column (only relevant for long format).

    Returns
    -------
    datetime_index : pandas DatetimeIndex, None
        A DatetimeIndex representing one series, suitable for frequency
        inference and quality checks. None if no datetime source exists.
    """
    if index_type != "datetime":
        return None

    if data_format == "long" and series_id_column is not None:
        # Extract dates from the first series only
        if series_id_column in data.columns:
            first_id = data[series_id_column].iloc[0]
            sample = data[data[series_id_column] == first_id]
            if date_col is not None and date_col in sample.columns:
                return pd.DatetimeIndex(sample[date_col])
            if isinstance(sample.index, pd.DatetimeIndex):
                return sample.index
        return None

    # Single or wide format
    if date_col is None:
        # DatetimeIndex is already the DataFrame index
        return data.index if isinstance(data.index, pd.DatetimeIndex) else None

    if date_col in data.columns:
        return pd.DatetimeIndex(data[date_col])

    return None


def _resolve_start_date(
    data: pd.DataFrame,
    datetime_index: pd.DatetimeIndex,
    data_format: str,
    series_id_column: str | None,
    date_col: str | None,
) -> pd.Timestamp:
    """
    Determine the reference start date for position-to-date conversion.

    For single and wide formats, returns the first element of the
    datetime index. For long format with multiple series that may have
    different start dates, returns the **latest** first date across all
    series so that position calculations align with the most
    constrained (latest-starting) series.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    datetime_index : pandas DatetimeIndex
        Representative datetime index (from the first series for long
        format).
    data_format : str
        One of `'single'`, `'wide'`, `'long'`.
    series_id_column : str, None
        Series identifier column (only relevant for long format).
    date_col : str, None
        Resolved date column name.

    Returns
    -------
    start : pandas Timestamp
        The reference start date.
    """
    if data_format != "long" or series_id_column is None:
        return datetime_index[0]

    if series_id_column not in data.columns:
        return datetime_index[0]

    # Find the latest (max) first date across all series
    if date_col is not None and date_col in data.columns:
        first_dates = data.groupby(series_id_column)[date_col].min()
    elif isinstance(data.index, pd.DatetimeIndex):
        first_dates = data.index.to_series().groupby(
            data[series_id_column].to_numpy()
        ).min()
    else:
        return datetime_index[0]

    return first_dates.max()


def detect_exog_columns(
    data: pd.DataFrame,
    target: str | list[str],
    date_column: str | None,
    series_id_column: str | None,
) -> list[str]:
    """
    Identify exogenous columns (everything except target, date, series_id).

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s).
    date_column : str, default None
        Name of the date column.
    series_id_column : str, default None
        Name of the series identifier column.

    Returns
    -------
    exog_columns : list
        Names of exogenous predictor columns.
    """
    excluded: set[str] = set()
    if isinstance(target, list):
        excluded.update(target)
    else:
        excluded.add(target)
    if date_column is not None:
        excluded.add(date_column)
    if series_id_column is not None:
        excluded.add(series_id_column)

    return [col for col in data.columns if col not in excluded]


def detect_categorical_exog(
    data: pd.DataFrame,
    exog_columns: list[str],
) -> list[str]:
    """
    Identify categorical columns among exogenous variables.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    exog_columns : list
        Names of exogenous columns to check.

    Returns
    -------
    categorical_exog : list
        Subset of `exog_columns` with dtype `object`, `category`, or `bool`.
    """
    categorical = []
    for col in exog_columns:
        if isinstance(data[col].dtype, pd.CategoricalDtype):
            categorical.append(col)
        elif pd.api.types.is_object_dtype(data[col]):
            categorical.append(col)
        elif pd.api.types.is_bool_dtype(data[col]):
            categorical.append(col)

    return categorical


def count_missing_values(
    data: pd.DataFrame,
    target: str | list[str],
    exog_columns: list[str],
    data_format: str = "single",
    series_id_column: str | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Count missing values separately for target and exogenous columns.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s).
    exog_columns : list
        Names of exogenous columns.
    data_format : str, default 'single'
        One of `'single'`, `'wide'`, `'long'`.
    series_id_column : str, default None
        Series identifier column (only for long format).

    Returns
    -------
    missing_target : dict
        Mapping of target column or series name to NaN count.
        Only entries with at least one missing value are included.
    missing_exog : dict
        Mapping of exogenous column name to count of missing values.
        Only columns with at least one missing value are included.
    """
    target_cols = target if isinstance(target, list) else [target]

    if data_format == "long" and series_id_column is not None:
        # Count NaN in target per series_id
        target_col = target_cols[0]
        missing_per_series = (
            data[target_col].isna().groupby(data[series_id_column]).sum()
        )
        missing_target = {
            str(name): int(count)
            for name, count in missing_per_series.items()
            if count > 0
        }
    else:
        # Single or wide: each target column is a key
        missing_target = {}
        for col in target_cols:
            count = int(data[col].isna().sum())
            if count > 0:
                missing_target[col] = count

    missing_exog = {}
    for col in exog_columns:
        count = int(data[col].isna().sum())
        if count > 0:
            missing_exog[col] = count

    return missing_target, missing_exog


def compute_target_stats(
    data: pd.DataFrame,
    target: str | list[str],
    data_format: str = "single",
    series_id_column: str | None = None,
) -> dict[str, dict[str, float]]:
    """
    Compute descriptive statistics (min, max, mean, std) for each target series.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s).
    data_format : str, default 'single'
        One of `'single'`, `'wide'`, `'long'`.
    series_id_column : str, default None
        Series identifier column (only for long format).

    Returns
    -------
    target_stats : dict
        Mapping of series/column name to a dict with keys `'min'`,
        `'max'`, `'mean'`, `'std'`. Series with no valid
        observations are omitted.
    """
    target_cols = target if isinstance(target, list) else [target]
    stats: dict[str, dict[str, float]] = {}

    if data_format == "long" and series_id_column is not None:
        target_col = target_cols[0]
        for series_name, group in data.groupby(series_id_column):
            series_stats = _series_stats(group[target_col])
            if series_stats is not None:
                stats[str(series_name)] = series_stats
    else:
        for col in target_cols:
            col_stats = _series_stats(data[col])
            if col_stats is not None:
                stats[col] = col_stats

    return stats


def _series_stats(series: pd.Series) -> dict[str, float] | None:
    """
    Compute min, max, mean, std from a pandas Series, ignoring NaN.

    Returns None if the series is non-numeric or has no valid values.
    """
    if not pd.api.types.is_numeric_dtype(series):
        return None
    values = series.to_numpy(dtype=float, na_value=np.nan)
    return _array_stats(values)


def _array_stats(values: np.ndarray) -> dict[str, float] | None:
    """
    Compute min, max, mean, std from a 1-D numpy array, ignoring NaN.

    Returns None if no valid (non-NaN) values exist.
    """
    mask = ~np.isnan(values)
    clean = values[mask]
    if len(clean) == 0:
        return None
    return {
        "min": float(np.min(clean)),
        "max": float(np.max(clean)),
        "mean": float(np.mean(clean)),
        "std": float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0,
    }


def generate_warnings(
    n_observations: int,
    frequency: str | None,
    missing_target: dict[str, int],
    missing_exog: dict[str, int],
    index_type: str,
    n_missing_timestamps: int = 0,
    n_duplicate_timestamps: int = 0,
    rows_sorted: bool = False,
    long_format: bool = False,
) -> list[str]:
    """
    Generate human-readable warnings about potential data issues.

    Parameters
    ----------
    n_observations : int
        Total number of observations.
    frequency : str, None
        Inferred frequency string.
    missing_target : dict
        Mapping of target/series name to NaN count.
    missing_exog : dict
        Mapping of exogenous column name to count of missing values.
    index_type : str
        Type of the index (`'datetime'`, `'range'`, `'other'`).
    n_missing_timestamps : int, default 0
        Number of timestamps missing from the regular grid of the index.
    n_duplicate_timestamps : int, default 0
        Number of timestamps (per series) repeated in identical rows, which
        the generated code drops.
    rows_sorted : bool, default False
        Whether the rows were not in date order (within a series, for long
        format) and were sorted before profiling.
    long_format : bool, default False
        Whether the data is in long format, to word the note on sorting.

    Returns
    -------
    warnings : list
        List of warning messages.
    """
    warnings: list[str] = []

    if n_observations < 50:
        warnings.append(
            f"Short series: only {n_observations} observations. "
            "Results may be unreliable with fewer than 50 observations."
        )

    if index_type != "datetime":
        warnings.append(
            "No datetime index detected. Frequency inference and "
            "seasonality estimation are unavailable."
        )

    if frequency is None and index_type == "datetime":
        warnings.append(
            "Could not infer frequency from the datetime index: the "
            "spacing is irregular, or there are too few timestamps."
        )

    if n_missing_timestamps > 0:
        warnings.append(
            f"Missing timestamps: {n_missing_timestamps} timestamps of "
            f"frequency '{frequency}' are missing from the date range. "
            f"asfreq() inserts them as rows with missing values."
        )

    if n_duplicate_timestamps > 0:
        warnings.append(
            f"Duplicate timestamps: identical rows repeat "
            f"{n_duplicate_timestamps} "
            f"timestamp{'s' if n_duplicate_timestamps != 1 else ''}. The "
            f"generated code keeps the first row of each."
        )

    if rows_sorted:
        within = " within each series" if long_format else ""
        warnings.append(
            f"Rows not in date order{within}: they were sorted by date before "
            f"profiling, as the generated code sorts them."
        )

    total_target_missing = sum(missing_target.values())
    total_exog_missing = sum(missing_exog.values())
    total_missing = total_target_missing + total_exog_missing
    if total_missing > 0:
        n_cols = len(missing_target) + len(missing_exog)
        if n_cols == 0:
            n_cols = 1
        missing_rate = total_missing / (n_observations * n_cols)
        if missing_rate > 0.2:
            warnings.append(
                f"High missing value rate ({missing_rate:.1%}). "
                "Consider imputation before forecasting."
            )

    return warnings


def _validate_target_exists(data: pd.DataFrame, target: str | list[str]) -> None:
    """
    Validate that the target column(s) exist in the DataFrame.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s).
    """
    targets = target if isinstance(target, list) else [target]
    missing = [col for col in targets if col not in data.columns]
    if missing:
        raise InvalidInputError(
            f"Target column(s) {missing} not found in the DataFrame. "
            f"Available columns: {list(data.columns)}",
            field = "target",
        )


def detect_target_dtype(data: pd.DataFrame, target: str) -> str:
    """
    Determine the data type category of the target column.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str
        Name of the target column.

    Returns
    -------
    target_dtype : str
        One of `'numeric'`, `'categorical'`, `'other'`.
    """
    dtype = data[target].dtype

    if pd.api.types.is_numeric_dtype(dtype):
        return "numeric"
    if isinstance(dtype, pd.CategoricalDtype):
        return "categorical"
    if pd.api.types.is_object_dtype(dtype) or pd.api.types.is_bool_dtype(dtype):
        return "categorical"

    return "other"


def count_missing_timestamps(
    datetime_index: pd.DatetimeIndex | None,
    frequency: str | None,
) -> int:
    """
    Count the timestamps missing from the regular grid of the index.

    Parameters
    ----------
    datetime_index : pandas DatetimeIndex, None
        The datetime index to check.
    frequency : str, None
        Inferred frequency string.

    Returns
    -------
    n_missing : int
        Number of timestamps of the regular grid between the first and the
        last timestamp that the index does not contain. 0 when the
        frequency is unknown.
    """
    if datetime_index is None or frequency is None:
        return 0

    if len(datetime_index) < 2:
        return 0

    try:
        expected = pd.date_range(
            start=datetime_index.min(),
            end=datetime_index.max(),
            freq=frequency,
        )
    except ValueError:
        return 0

    return int((~expected.isin(datetime_index)).sum())


def detect_gaps(
    datetime_index: pd.DatetimeIndex | None,
    frequency: str | None,
) -> bool:
    """
    Detect whether the datetime index has missing timestamps.

    Parameters
    ----------
    datetime_index : pandas DatetimeIndex, None
        The datetime index to check.
    frequency : str, None
        Inferred frequency string.

    Returns
    -------
    has_gaps : bool
        True if there are missing timestamps within the date range.

    Notes
    -----
    This function requires a known `frequency` to compare actual vs
    expected timestamps. `infer_frequency()` tolerates gaps, so it is
    None only for irregular spacing; this function then returns False,
    meaning "gaps not detected", not "no gaps exist", and the profiler
    warns that the frequency could not be inferred.
    """
    return count_missing_timestamps(datetime_index, frequency) > 0


def _check_duplicate_timestamps(
    data: pd.DataFrame,
    target: str | list[str],
    date_col: str | None,
    index_type: str,
    data_format: str,
    series_id_column: str | None,
) -> tuple[int, np.ndarray | None]:
    """
    Check repeated timestamps and decide whether they can be dropped.

    A timestamp is repeated when it appears in more than one row of the
    same series (the row timestamp for single and wide formats, the pair
    series identifier and date for long format). Repeated rows that are
    identical can be dropped without losing data; repeated rows whose
    values differ cannot, since keeping any one of them would silently
    discard the others.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s). Used to suggest a series
        identifier column in the error message.
    date_col : str, None
        Resolved date column name. When None, the DataFrame index is used.
    index_type : str
        One of `'datetime'`, `'range'`, `'other'`.
    data_format : str
        One of `'single'`, `'wide'`, `'long'`.
    series_id_column : str, None
        Series identifier column (only relevant for long format).

    Returns
    -------
    n_duplicate_timestamps : int
        Number of timestamps (per series) that appear in more than one
        identical row.
    keep_mask : numpy ndarray, None
        Boolean mask that keeps the first row of each repeated timestamp.
        None when no timestamp is repeated.

    Notes
    -----
    A repeated timestamp whose rows have different values raises a
    `ValueError` that says how to fix the input. Rows with a missing date
    are left out of the check. Two missing values in the same column count
    as identical.
    """
    if index_type != "datetime":
        return 0, None

    dates = row_dates(data, date_col)
    if dates is None:
        return 0, None

    long_format = (
        data_format == "long"
        and series_id_column is not None
        and series_id_column in data.columns
    )

    # Columns are labelled by position so a data column cannot clash with
    # the key columns: 0 is the date, 1 the series identifier (long format).
    keys = pd.DataFrame({0: dates.to_numpy()})
    if long_format:
        keys[1] = data[series_id_column].to_numpy()
    key_cols = list(keys.columns)

    valid = dates.notna()
    repeated = keys.duplicated(keep=False).to_numpy() & valid
    if not repeated.any():
        return 0, None

    # The raw date and identifier columns are left out of the comparison:
    # the keys already hold them, parsed, so two spellings of the same
    # timestamp do not count as different values.
    value_cols = [
        col for col in data.columns if col not in (date_col, series_id_column)
    ]
    values = data[value_cols].reset_index(drop=True)
    values.columns = range(len(key_cols), len(key_cols) + len(value_cols))
    rows = pd.concat([keys, values], axis=1)[repeated]

    repeated_keys = rows[key_cols].drop_duplicates()
    try:
        distinct = rows.drop_duplicates()
        conflicts = distinct.loc[
            distinct.duplicated(subset=key_cols, keep=False), key_cols
        ].drop_duplicates()
    except TypeError:
        # Unhashable cells (lists, dicts) cannot be compared, so every
        # repeated timestamp is treated as a conflict rather than dropped.
        conflicts = repeated_keys

    if not conflicts.empty:
        raise InvalidInputError(
            _duplicate_timestamps_message(
                conflicts   = conflicts,
                data        = data,
                dates       = dates,
                target      = target,
                date_col    = date_col,
                data_format = data_format,
                long_format = long_format,
            ),
            field = "data",
        )

    keep_mask = ~(keys.duplicated(keep="first").to_numpy() & valid)

    return len(repeated_keys), keep_mask


def _duplicate_timestamps_message(
    conflicts: pd.DataFrame,
    data: pd.DataFrame,
    dates: pd.DatetimeIndex,
    target: str | list[str],
    date_col: str | None,
    data_format: str,
    long_format: bool,
) -> str:
    """
    Build the error message for timestamps repeated with different values.

    Parameters
    ----------
    conflicts : pandas DataFrame
        One row per conflicting timestamp: column 0 holds the date and, for
        long format, column 1 the series identifier.
    data : pandas DataFrame
        Input dataset.
    dates : pandas DatetimeIndex
        Parsed timestamps of `data`, row by row.
    target : str, list
        Name(s) of the target column(s).
    date_col : str, None
        Resolved date column name.
    data_format : str
        One of `'single'`, `'wide'`, `'long'`.
    long_format : bool
        Whether the rows are keyed by series identifier and date.

    Returns
    -------
    message : str
        Error message saying how many timestamps conflict, one example, and
        how to fix the input.
    """
    n = len(conflicts)
    plural = "s" if n != 1 else ""
    # The earliest conflict is the example; series identifiers are sorted as
    # text so mixed types cannot break the ordering.
    order = conflicts.astype({1: str}) if long_format else conflicts
    first = conflicts.loc[order.sort_values(by=list(order.columns)).index[0]]
    example = _fmt_timestamp(first[0])

    if long_format:
        series = sorted(conflicts[1].astype(str).unique())
        shown = series[:5]
        more = f" and {len(series) - 5} more" if len(series) > 5 else ""
        return (
            f"Found {n} date{plural} with more than one row and different "
            f"values within the same series, for example '{example}' in series "
            f"'{first[1]}' (affected series: {shown}{more}). Each series "
            f"needs one row per date, and keeping only one of them would "
            f"silently discard data. Aggregate or remove the repeated rows of "
            f"each series before profiling."
        )

    found = (
        f"Found {n} timestamp{plural} with more than one row and different "
        f"values, for example '{example}'."
    )
    if data_format == "wide":
        return (
            f"{found} Wide format needs one row per timestamp, with one column "
            f"per series, and keeping only one of them would silently discard "
            f"data. Aggregate or remove the repeated rows before profiling."
        )

    found = (
        f"{found} A single series needs one row per timestamp, and keeping "
        f"only one of them would silently discard data."
    )
    excluded = {target} if isinstance(target, str) else set(target)
    if date_col is not None:
        excluded.add(date_col)
    candidates = _find_series_id_candidates(
        data     = data,
        dates    = dates,
        excluded = excluded,
    )
    if candidates:
        return (
            f"{found} If the rows belong to different series, pass "
            f"`series_id_column` (candidate columns: {candidates}) to profile "
            f"the data in long format. Otherwise, aggregate or remove the "
            f"repeated rows before profiling."
        )

    return (
        f"{found} Aggregate or remove the repeated rows before profiling, or "
        f"pass `series_id_column` if a column identifies different series."
    )


def _find_series_id_candidates(
    data: pd.DataFrame,
    dates: pd.DatetimeIndex,
    excluded: set[str],
) -> list[str]:
    """
    Find columns that could identify the series of long-format data.

    A column is a candidate when every timestamp appears at most once per
    value of the column (identical repeated rows aside), it is not a float
    column, and it has at most half as many distinct values as rows, which
    leaves out continuous variables and row identifiers.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    dates : pandas DatetimeIndex
        Parsed timestamps of `data`, row by row.
    excluded : set of str
        Columns that cannot identify series (target and date column).

    Returns
    -------
    candidates : list of str
        Candidate column names, in column order.
    """
    columns = [col for col in data.columns if col not in excluded]
    values = data[columns].reset_index(drop=True)
    values.columns = range(1, len(columns) + 1)
    frame = pd.concat([pd.DataFrame({0: dates.to_numpy()}), values], axis=1)
    frame = frame[dates.notna()]

    try:
        distinct = frame.drop_duplicates()
    except TypeError:
        return []

    candidates = []
    for position, col in enumerate(columns, start=1):
        if pd.api.types.is_float_dtype(data[col]):
            continue
        try:
            if data[col].nunique(dropna=False) > len(data) // 2:
                continue
            if not distinct.duplicated(subset=[0, position]).any():
                candidates.append(col)
        except TypeError:
            continue

    return candidates


def _check_monotonic(
    datetime_index: pd.DatetimeIndex | None,
    data: pd.DataFrame,
) -> bool:
    """
    Check whether the index is monotonically increasing.

    Parameters
    ----------
    datetime_index : pandas DatetimeIndex, None
        The datetime index (if available).
    data : pandas DataFrame
        The input DataFrame (used when no datetime index is available).

    Returns
    -------
    is_monotonic : bool
        True if the index is sorted in ascending order.
    """
    if datetime_index is not None:
        return bool(datetime_index.is_monotonic_increasing)
    return bool(data.index.is_monotonic_increasing)


def _check_frequency_is_set(
    datetime_index: pd.DatetimeIndex | None,
    data: pd.DataFrame,
) -> bool:
    """
    Check whether the index already has a frequency attribute set.

    When the datetime source is a regular column (not the index),
    the constructed DatetimeIndex will never have `.freq` set;
    this correctly indicates that `asfreq()` is still needed.

    Parameters
    ----------
    datetime_index : pandas DatetimeIndex, None
        The datetime index (if available).
    data : pandas DataFrame
        The input DataFrame.

    Returns
    -------
    frequency_is_set : bool
        True if `index.freq` is not None.
    """
    if datetime_index is not None:
        return datetime_index.freq is not None
    if isinstance(data.index, pd.DatetimeIndex):
        return data.index.freq is not None
    return False


def _check_target_is_constant(data: pd.DataFrame, target: str) -> bool:
    """
    Check whether the target column has zero variance.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str
        Name of the target column.

    Returns
    -------
    is_constant : bool
        True if the target has zero variance or only one unique value.
    """
    series = data[target].dropna()
    if len(series) == 0:
        return True
    if not pd.api.types.is_numeric_dtype(series.dtype):
        return series.nunique() <= 1
    return bool(series.std() == 0)


def _format_split_ts(ts: pd.Timestamp) -> str:
    """
    Format a split-boundary timestamp as a string literal.

    For sub-daily frequencies the full timestamp is returned to avoid
    ambiguity between partial-string `.loc` slicing (which includes all
    hours on a given date) and boolean comparison (which treats a date
    string as midnight).

    Parameters
    ----------
    ts : pandas Timestamp
        The split-boundary timestamp.

    Returns
    -------
    end_train : str
        Date-only string (e.g. `'2005-03-01'`) when the timestamp falls
        on midnight, otherwise a full timestamp string (e.g.
        `'2012-08-07 23:00:00'`).
    """
    if ts.hour != 0 or ts.minute != 0 or ts.second != 0:
        return str(ts)
    return str(ts.date())


def resolve_end_train(
    start_date: str | None,
    frequency: str | None,
    n_observations: int,
    test_size: int | float | str | pd.Timestamp,
) -> str:
    """
    Resolve a ``test_size`` specification into an ``end_train`` boundary.

    Rebuilds the datetime index from ``start_date``, ``frequency`` and
    ``n_observations`` (the same reconstruction convention used elsewhere
    for date-based cross-validation), then converts ``test_size`` into the
    last training timestamp.

    Parameters
    ----------
    start_date : str, None
        First timestamp of the dataset.
    frequency : str, None
        Pandas frequency string of the index.
    n_observations : int
        Number of observations spanned by the index.
    test_size : int, float, str, pandas Timestamp
        Size or start of the test set.

        - int: the last ``test_size`` observations form the test set.
        - float in ``(0, 1)``: the last fraction ``test_size`` of the
          observations form the test set.
        - str or pandas Timestamp: the first timestamp of the test set
          (the split boundary).

    Returns
    -------
    end_train : str
        Last datetime (inclusive) of the training set, formatted with
        `_format_split_ts`.

    Raises
    ------
    ValueError
        If a datetime index cannot be reconstructed, or ``test_size`` is
        out of range or leaves an empty train or test set.
    """
    if start_date is None or frequency is None:
        raise InvalidInputError(
            "`test_size` requires a datetime index with a known frequency. "
            "Set the index frequency (e.g. `data.asfreq(...)`) before "
            "forecasting.",
            field = "test_size",
        )

    index = pd.date_range(start=start_date, periods=n_observations, freq=frequency)
    n = len(index)

    # bool is a subclass of int; reject it explicitly to avoid silent misuse.
    if isinstance(test_size, bool):
        raise InvalidInputTypeError(
            "`test_size` must be an int, float, str or Timestamp, not bool.",
            field = "test_size",
        )

    if isinstance(test_size, int):
        if not 1 <= test_size < n:
            raise InvalidInputError(
                f"Integer `test_size` must be between 1 and {n - 1} "
                f"(number of observations is {n}), got {test_size}.",
                field = "test_size",
            )
        boundary_idx = n - test_size - 1
    elif isinstance(test_size, float):
        if not 0.0 < test_size < 1.0:
            raise InvalidInputError(
                f"Float `test_size` must be in the open interval (0, 1), "
                f"got {test_size}.",
                field = "test_size",
            )
        n_test = round(n * test_size)
        n_test = max(1, min(n_test, n - 1))
        boundary_idx = n - n_test - 1
    elif isinstance(test_size, (str, pd.Timestamp)):
        ts = pd.Timestamp(test_size)
        if not index[0] < ts <= index[-1]:
            raise InvalidInputError(
                f"Timestamp `test_size` ({ts}) must fall within the data "
                f"range, after {index[0]} and no later than {index[-1]}, so "
                f"that both train and test sets are non-empty.",
                field = "test_size",
            )
        train_positions = (index < ts).nonzero()[0]
        boundary_idx = int(train_positions[-1])
    else:
        raise InvalidInputTypeError(
            f"`test_size` must be an int, float, str or Timestamp, "
            f"got {type(test_size).__name__}.",
            field = "test_size",
        )

    return _format_split_ts(index[boundary_idx])


def count_test_observations(
    start_date: str | None,
    frequency: str | None,
    n_observations: int,
    end_train: str,
) -> int | None:
    """
    Count the observations after a train/test split boundary.

    Rebuilds the same date grid as `resolve_end_train`, so the count
    matches the test set that boundary defines.

    Parameters
    ----------
    start_date : str, None
        First timestamp of the dataset.
    frequency : str, None
        Inferred pandas frequency string.
    n_observations : int
        Number of observations spanned by the dataset.
    end_train : str
        Last timestamp of the training set.

    Returns
    -------
    n_test : int, None
        Number of observations after `end_train`, or None when the date grid
        cannot be rebuilt (no start date or no frequency).
    """
    if start_date is None or frequency is None:
        return None

    index = pd.date_range(start=start_date, periods=n_observations, freq=frequency)

    return int((index > pd.Timestamp(end_train)).sum())
