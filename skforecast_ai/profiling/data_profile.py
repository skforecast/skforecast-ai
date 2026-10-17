################################################################################
#                               data profile                                   #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

import datetime
import functools
import os
import re
import sys
import warnings as _warnings
from pathlib import Path
import numpy as np
import pandas as pd
from dateutil import parser as dateutil_parser
from skforecast.exceptions import IgnoredArgumentWarning
from .._dates import (
    date_positions,
    day_month_formats,
    first_date,
    guess_datetime_format,
    guessed_date_format,
    is_missing_date,
    is_text,
    missing_dates,
    parse_text_dates,
    row_dates,
    short_year_format,
    time_zones,
    training_end,
)
from ..schemas import DataProfile
from ..exceptions import DataContentError, InvalidInputError, InvalidInputTypeError
from .csv_dialect import (
    DECIMAL_NUMBERS,
    NUMERIC_DATE,
    DECOMPRESSION_ERRORS,
    DEFAULT_CSV_DECIMAL,
    CP1252,
    DEFAULT_CSV_ENCODING,
    DEFAULT_CSV_SEP,
    DOT_THOUSANDS,
    DOTTED_NUMBER,
    SHORT_WHOLE_NUMBER,
    THOUSANDS,
    WHOLE_NUMBER,
    ambiguous_thousands_error,
    check_csv_dialect,
    cp1252_note,
    decimal_in_both_error,
    detect_csv_dialect,
    dotted_values_error,
    only_thousands_error,
    read_row_lengths,
    read_sample,
    sample_date_column,
    sample_holds_file,
    undefined_byte_error,
)

# TODO: Memory Optimization - Mask Filtering
# Optimize `_extract_datetime_index` to avoid creating heavy boolean masks 
# (e.g., `data[data[series_id] == id]`) on the entire DataFrame. Consider using
# lazy evaluation or `groupby().get_group()` to isolate the sample.

# TODO: Multi-Target Logic - Check All Target Dtypes
# In `create_data_profile`, `target_dtype` only checks the first target column. 
# For wide-format multi-series, it should verify if dtypes are mixed across targets 
# or return a dictionary mapping each target to its dtype.


# Durations in nanoseconds, the unit of `DateOffset.nanos`. Written out:
# `pd.Timedelta(days=1)` emits a DeprecationWarning with numpy 2.5 (the
# generic timedelta unit), which a user running with warnings as errors
# would get from `profile()`. A year is 365.2425 days.
_HOUR_NANOS = 3_600 * 10**9
_DAY_NANOS = 24 * _HOUR_NANOS
_YEAR_NANOS = 31_556_952 * 10**9

# Consecutive timestamps per window when the frequency is inferred from the
# stretches between gaps. Long enough to tell a business day from a calendar
# day (a window must cross a weekend) and capped in number so the cost does
# not grow with the length of the series.
_FREQUENCY_WINDOW = 10
_MAX_FREQUENCY_WINDOWS = 200
# When gaps leave no such window (daily data without Sundays), the frequency
# is inferred on windows of three consecutive timestamps, the fewest pandas
# infers one from. A long index is read in blocks of consecutive windows:
# single windows evenly spaced may all fall on the same phase of a periodic
# pattern of gaps (every one starting on a Saturday).
_GAPS_WINDOW = 3
_GAPS_WINDOW_BLOCK = 20

# Minimum share of the regular grid that must be observed to accept a
# frequency inferred despite gaps. Below it the spacing is irregular rather
# than regular with missing timestamps.
_MIN_FREQUENCY_COVERAGE = 0.5
# Dates of a series of long-format data read to infer its own frequency. A
# series with fewer dates than a window above does not tell a frequency of
# its own: a few rows a week apart may be a sparse daily series.
_OWN_FREQUENCY_DATES = 30
# Series with gaps, longest first, on which a frequency is inferred with gaps
# until one gives it, to bound the cost when none does.
_MAX_SERIES_WITH_GAPS = 10
# A sparse series of n dates whose steps are all multiples of k steps of the
# grid has them by chance with a probability of about k ** -(n - 1). It is
# taken for a series of a coarser frequency only when that probability, over
# all the series of the data, is below one in a million, so a few sales on
# even days are not.
_COARSER_EVIDENCE = np.log(1e6)
# Candidate frequencies checked against every series, to bound the cost when
# the series have many frequencies of their own.
_MAX_CANDIDATES = 20


def infer_frequency(
    index: pd.DatetimeIndex,
    regular_gaps: bool = True,
) -> str | None:
    """
    Infer the frequency of a DatetimeIndex, tolerating missing timestamps.

    `pd.infer_freq` needs a gap-free index. When it fails, the frequency is
    inferred on windows of consecutive timestamps (the stretches between
    gaps), and the most frequent answer is accepted when every timestamp
    lies on its regular grid and at least half of that grid is observed.
    Gaps so regular or frequent that no stretch gives a frequency (daily
    data without Sundays, a day in four missing at random) are told on
    windows of three timestamps, with the same conditions and one more (see
    `_frequency_with_regular_gaps`). The missing timestamps are then counted
    by `count_missing_timestamps()` and become NaN rows after `asfreq()`.

    Parameters
    ----------
    index : pandas DatetimeIndex
        The datetime index to infer frequency from.
    regular_gaps : bool, default True
        Whether gaps that leave no gap-free stretch are told on windows of
        three timestamps. False bounds the cost of a call on every series
        of long-format data: on irregular dates, pandas takes a fraction of
        a millisecond per window.

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

    return _infer_frequency_with_gaps(index, regular_gaps)


def _infer_frequency_with_gaps(
    index: pd.DatetimeIndex,
    regular_gaps: bool = True,
) -> str | None:
    """
    Infer a frequency from a DatetimeIndex with missing timestamps.

    The frequency is inferred first on the gap-free stretches of the index,
    and the most frequent answer whose grid fits is accepted. When no
    stretch gives one, because the gaps are regular or frequent, it is
    inferred on windows of three timestamps (see
    `_frequency_with_regular_gaps`).

    Parameters
    ----------
    index : pandas DatetimeIndex
        Datetime index whose frequency `pd.infer_freq` could not infer.
    regular_gaps : bool, default True
        Whether to infer it on windows of three timestamps when no stretch
        gives one.

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
        if _fitting_grid(index, freq) is not None:
            return freq
    if candidates or not regular_gaps:
        # The stretches tell the frequency, and its grid does not fit: there
        # are timestamps off it (a Saturday among business days), or too
        # few on it. A finer frequency with gaps would hide that.
        return None

    return _frequency_with_regular_gaps(index)


def _frequency_with_regular_gaps(index: pd.DatetimeIndex) -> str | None:
    """
    Infer the frequency of a sorted DatetimeIndex whose gaps leave no
    stretch of `_FREQUENCY_WINDOW` consecutive timestamps that gives one.

    pandas infers a frequency from three timestamps, so windows of three
    give the candidates: `'D'` from a Monday, Tuesday and Wednesday of daily
    data without Sundays. A candidate fits when its grid holds every
    timestamp and is at least `_MIN_FREQUENCY_COVERAGE` observed (see
    `_fitting_grid`), and when the most common step between consecutive
    timestamps is one period of the grid. That last condition rejects a
    frequency finer than the data: a stray timestamp at noon among daily
    ones gives `'12h'` on two windows, whose grid is half observed, but the
    other timestamps are two periods of it apart. Of the candidates that
    fit, the coarsest is the frequency: business days with gaps also fit
    the daily grid, and stay `'B'`, a candidate whenever `'D'` is one.

    Parameters
    ----------
    index : pandas DatetimeIndex
        Sorted datetime index of distinct timestamps, at least
        `_FREQUENCY_WINDOW` of them.

    Returns
    -------
    frequency : str, None
        The coarsest frequency that fits, or None.
    """
    n_windows = len(index) - _GAPS_WINDOW + 1
    if n_windows > _MAX_FREQUENCY_WINDOWS:
        n_blocks = _MAX_FREQUENCY_WINDOWS // _GAPS_WINDOW_BLOCK
        firsts = np.linspace(0, n_windows - _GAPS_WINDOW_BLOCK, n_blocks).astype(int)
        starts = np.unique(firsts[:, None] + np.arange(_GAPS_WINDOW_BLOCK))
    else:
        starts = np.arange(n_windows)

    candidates = set()
    for start in starts:
        try:
            freq = pd.infer_freq(index[start:start + _GAPS_WINDOW])
        except (TypeError, ValueError):
            continue
        if freq is not None:
            candidates.add(freq)
    if "D" in candidates:
        # pandas infers business days only from three that cross a weekend,
        # which data closed on Fridays too never has.
        candidates.add("B")

    found, found_size = None, 0
    for freq in sorted(candidates):
        grid = _fitting_grid(index, freq)
        if grid is None:
            continue
        # Searched as timestamps: the grid is in nanoseconds, the index may
        # be in seconds or microseconds.
        steps = np.diff(grid.searchsorted(index))
        if np.bincount(steps).argmax() != 1:
            continue
        if found is None or len(grid) < found_size:
            found, found_size = freq, len(grid)

    return found


def _fitting_grid(index: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex | None:
    """
    Return the grid of `frequency` from the first to the last timestamp of a
    sorted DatetimeIndex when it holds every timestamp and at least
    `_MIN_FREQUENCY_COVERAGE` of it is observed, or None.

    A grid estimated at twice the size the minimum coverage allows is not
    built: a few dates a second apart among dates a day apart would build
    a grid of every second of the range.
    """
    largest = len(index) / _MIN_FREQUENCY_COVERAGE
    try:
        span = (index[-1] - index[0]).value / _YEAR_NANOS
        if span * _periods_per_year(frequency) > 2 * largest:
            return None
        grid = pd.date_range(index[0], index[-1], freq=frequency)
    except ValueError:
        return None
    if len(index) < _MIN_FREQUENCY_COVERAGE * len(grid) or not index.isin(grid).all():
        return None

    return grid


def create_data_profile(
    data: pd.DataFrame | str | Path,
    target: str | list[str],
    date_column: str | None = None,
    series_id_column: str | None = None,
    data_path: str = "data.csv",
    exog_columns: list[str] | None = None,
    sep: str | None = None,
    decimal: str | None = None,
    thousands: str | None = None,
    dayfirst: bool | None = None,
    date_format: str | None = None,
    encoding: str | None = None,
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
        pass a list of column names where each column is a series, each
        named once and without `series_id_column`.
    date_column : str, default None
        Name of the column containing timestamps. If None, the function
        attempts to detect it from the index or columns.
    series_id_column : str, default None
        Name of the column identifying individual series in long format,
        where `target` is the name of one column. If None and target is a
        string, the dataset is treated as a single series (or as long
        format with the ids of the first level of a MultiIndex). The ids
        are text, as the generated script reads them: a CSV file is read
        with this column as text (`'001'`), and the ids of a DataFrame are
        turned into text (`1` becomes `'1'`).
    data_path : str, default 'data.csv'
        Path to the source CSV file used in generated scripts.
    exog_columns : list of str, default None
        Columns used as exogenous variables. If None, every column that is
        not the target, the date or the series id. Otherwise a subset of
        them (an empty list for none), kept in the order of the data; the
        other columns are listed in `unused_columns`, with a note in
        `warnings`, and are not described by the profile.
    sep : str, default None
        Separator of the fields of the CSV file: `','`, `';'` or a
        tabulator. If None, it is detected when `data` is a path, and `','`
        is recorded for a DataFrame. The profile records it as `csv_sep`.
    decimal : str, default None
        Decimal mark of the CSV file: `'.'` or `','`. If None, it is
        detected when `data` is a path, and `'.'` is recorded for a
        DataFrame. The profile records it as `csv_decimal`.
    thousands : str, default None
        Thousands separator of the CSV file: `'.'`, with `','` as decimal
        mark. If None, it is detected when `data` is a path, and none is
        recorded for a DataFrame. The profile records it as
        `csv_thousands`.
    dayfirst : bool, default None
        Order of the day and the month of dates written as text that read in
        both (`'01/02/2020'`), those of a CSV file or the text `date_column`
        of a DataFrame: True for day first, False for month first. If None,
        it is told from the dates (see Notes). Ignored for dates whose
        format leaves no doubt (`'2020-02-01'`, `'01 Feb 2020'`); for a
        DataFrame whose dates are not text (already datetime), an
        `IgnoredArgumentWarning` says that it does not apply.
    date_format : str, default None
        Format the text dates of `data` were read with, when it is a
        DataFrame read from a CSV file (see `_try_parse_first_date_column`),
        recorded as `date_format`; for text dates still in `data`, the
        format of a profile of the data, which decides the order of dates
        that read in both.
    encoding : str, default None
        Encoding of the CSV file `data` was read from, when it is a
        DataFrame read from one (see `read_csv_with_dialect`): `'utf-8'` or
        `'cp1252'`, recorded as `csv_encoding`. If None, `'utf-8'`. The
        encoding of a path is always told from the file.

    Returns
    -------
    profile : DataProfile
        Validated profile containing metadata, detected features, and
        warnings about the dataset.

    Notes
    -----
    A DataFrame indexed by a `(series_id, date)` MultiIndex is read as long
    format, with its levels as columns of the same name, which fill
    `series_id_column` and `date_column` when they are None. A MultiIndex
    of another number of levels, or with a level without a name or not
    named with text, raises `InvalidInputError` (see
    `check_multiindex_levels`).

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

    A CSV date column with empty cells raises a `ValueError` that says so,
    as does one whose dates mix UTC offsets or are written in more than one
    format (see `_try_parse_first_date_column` and `_read_date_column`).
    Dates that write the day and the month as numbers before the year are
    read in the only order that reads every date (a day after the 12th
    settles day first), and the profile records the format the generated
    script reads them with (`date_format`). When every date reads in both
    orders, `dayfirst` gives it; without it, the dates are read in both
    orders, and when only one of the readings has a regular frequency
    (monthly data of a US file, `'02/01/2015'`, are `'MS'` month first and
    have no frequency day first), it is the order, with a note in
    `warnings` that says so and how to give the other one with `dayfirst`.
    When both readings have a frequency (a few dates: `'D'` and `'MS'`),
    or neither has one, the order is not guessed: `InvalidInputError` with
    code `'data_unreadable'` and a hint that names `dayfirst`. Whole numbers
    that are all dates of eight digits (`20200131`) are dates, recorded
    with `date_format` `'%Y%m%d'`.

    In long format, the frequency of every series is read: series of
    different frequencies, or with timestamps off the grid of the others,
    raise a `ValueError` (see `_infer_long_frequency`); the missing
    timestamps of every series are counted, and a note in `warnings` names
    the series whose last value comes before the last date with a value,
    which `ForecasterRecursiveMultiSeries` does not predict. The same note
    is given for wide-format data, where the series are the columns of
    `target`. Time zone aware dates are read in local time for a frequency
    of a day or coarser and in UTC for a finer one, as pandas puts them on a
    grid.

    A CSV file that is not UTF-8 is read as cp1252 (Windows-1252, the "CSV"
    that Excel saves on Windows), recorded as `csv_encoding`, with a note
    first in `warnings`: that encoding cannot be checked (see
    `read_csv_with_dialect`).
    """
    check_csv_dialect(sep, decimal, thousands)
    # Notes on how the dates were read, first among the warnings.
    date_notes: list[str] = []
    in_memory = not isinstance(data, (str, Path))
    if not in_memory:
        data, sep, decimal, thousands, encoding = read_csv_with_dialect(
                                            path             = data,
                                            sep              = sep,
                                            decimal          = decimal,
                                            thousands        = thousands,
                                            series_id_column = series_id_column,
                                            date_column      = date_column,
                                        )
        # Attempt to parse the first object-dtype column as datetime.
        # This handles CSVs exported with df.to_csv() where the date
        # index becomes a regular column.
        data, date_format = _try_parse_first_date_column(
                                data             = data,
                                date_column      = date_column,
                                series_id_column = series_id_column,
                                dayfirst         = dayfirst,
                                date_format      = date_format,
                                notes            = date_notes,
                            )

    # Before a MultiIndex fills `series_id_column`: only the one the caller
    # passed contradicts a list of targets.
    _validate_target_format(target, series_id_column)

    # Normalize a MultiIndex (level 0 = series_id, level 1 = datetime) into
    # flat long format so every downstream helper sees named columns. Other
    # levels, or levels not named with text, raise: the script reads the
    # levels by name.
    data, date_column, series_id_column = _normalize_multiindex(
        data, date_column, series_id_column
    )
    # The series are named with text, as the generated script names them.
    data = series_ids_as_text(data, series_id_column)

    # Determine data format from user input
    data_format = _resolve_data_format(target, series_id_column)

    # Validate target columns exist
    _validate_target_exists(data, target)
    _validate_series_id_column(data, target, date_column, series_id_column)
    _validate_target_has_values(data, target)

    # The dates of a CSV file were read above, in the order of `dayfirst`.
    frame_dayfirst = dayfirst if in_memory else None
    date_col, index_type = detect_date_column(
                               data        = data,
                               date_column = date_column,
                               date_format = date_format,
                               dayfirst    = frame_dayfirst,
                           )
    if frame_dayfirst is not None:
        _warn_dayfirst_not_applied(data, date_col)

    # Text dates are parsed once, as the generated script parses the whole
    # column, so every check below reads the same dates. Parsed one by one,
    # '01/02/2012' is read month-first in a column of day-first dates.
    data, date_format = _parse_text_date_column(
                            data        = data,
                            date_col    = date_col,
                            date_format = date_format,
                            dayfirst    = frame_dayfirst,
                            notes       = date_notes,
                        )

    detected_exog = detect_exog_columns(
        data, target, date_col, series_id_column
    )
    exog_columns, unused_columns = _select_exog_columns(
        detected         = detected_exog,
        selected         = exog_columns,
        data             = data,
        target           = target,
        date_column      = date_col,
        series_id_column = series_id_column,
    )

    # Repeated timestamps are resolved before anything is measured: rows
    # that differ cannot be merged without losing data, and identical rows
    # are dropped here as the generated script drops them, so the profile
    # describes the data that is modeled. The script keeps the first row,
    # so columns left out by `exog_columns` may differ.
    n_duplicate_timestamps, keep_mask = _check_duplicate_timestamps(
        data             = data,
        target           = target,
        date_col         = date_col,
        index_type       = index_type,
        data_format      = data_format,
        series_id_column = series_id_column,
        ignored_columns  = unused_columns,
    )
    if keep_mask is not None:
        data = data[keep_mask]
    has_duplicate_timestamps = n_duplicate_timestamps > 0

    # Extract a datetime index suitable for quality checks (monotonicity,
    # the start date, and the frequency and gaps of single and wide data).
    # For long format, a single representative series avoids stacked dates;
    # the frequency and the gaps of every series are read further down.
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

    long_series = (
        data_format == "long"
        and index_type == "datetime"
        and series_id_column is not None
        and series_id_column in data.columns
    )
    long_dates = row_dates(data, date_col) if long_series else None
    series_dates = (
        _long_series_dates(long_dates, data[series_id_column])
        if long_dates is not None else None
    )
    if series_dates is not None:
        # Every series is read: the frequency of the first one alone
        # resampled the others to it, with only the warning of skforecast
        # that a series is incomplete, and their gaps were not counted.
        if long_dates.tz is None:
            frequency, n_missing_timestamps = _infer_long_frequency(series_dates)
        else:
            frequency, n_missing_timestamps = _infer_aware_long_frequency(
                local_dates = series_dates,
                utc_dates   = _long_series_dates(
                                  long_dates.tz_convert("UTC"), data[series_id_column]
                              ),
            )
    else:
        frequency = (
            infer_frequency(datetime_index) if datetime_index is not None else None
        )
        n_missing_timestamps = count_missing_timestamps(datetime_index, frequency)
    has_gaps = n_missing_timestamps > 0

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

    # Early stop: constant target makes forecasting meaningless
    if _check_target_is_constant(data, first_target):
        raise InvalidInputError(
            f"Target column '{first_target}' is constant (zero variance). "
            "Forecasting a constant series is not meaningful.",
            field = "target",
        )

    categorical_exog = detect_categorical_exog(data, exog_columns)
    numbers_as_text = detect_numbers_as_text(
        data         = data,
        exog_columns = categorical_exog,
        decimal      = DEFAULT_CSV_DECIMAL if decimal is None else decimal,
    )
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
        series_ending_early    = (
            _series_ending_early(
                dates  = long_dates,
                ids    = data[series_id_column],
                values = data[first_target],
            )
            if series_dates is not None
            else _wide_series_ending_early(data, target, date_col)
            if data_format == "wide" and index_type == "datetime"
            and len(target) > 1
            else None
        ),
        numbers_as_text        = numbers_as_text,
        gap_weekdays           = (
            regular_gap_weekdays(
                series_dates if series_dates is not None else datetime_index,
                frequency,
            )
            if has_gaps else None
        ),
    )
    # How the file was read comes first: its encoding, then its dates.
    if encoding == CP1252:
        date_notes.insert(0, cp1252_note())
    warnings[:0] = date_notes
    if long_dates is not None and series_dates is None:
        warnings.append(
            "Long-format dates outside the years 1677 to 2262: the frequency "
            "and the missing timestamps were read from the first series only, "
            "so the other series were not checked."
        )
    if unused_columns:
        warnings.append(unused_columns_note(unused_columns))

    # Compute start_date: the first date of the data, and in long format
    # the latest first date of the series (the one every series has
    # reached). Positions are converted to dates from
    # `DataProfile.span_start_date`, which in long format is the earliest
    # first date, where `span_index_length` starts (when the span can be
    # rebuilt from it).
    start_date: str | None = None
    time_zone = _time_zone_name(datetime_index)
    if datetime_index is not None and len(datetime_index) > 0:
        ts = _resolve_start_date(
            data=data,
            datetime_index=datetime_index,
            data_format=data_format,
            series_id_column=series_id_column,
            date_col=date_col,
        )
        # With a time zone the profile names (`time_zone`), the date is
        # written as local time without its UTC offset, as the date alone
        # at midnight already is: the offset of the first date does not
        # hold across a daylight saving change, and a strategy placed from
        # it failed in the script.
        if ts.tzinfo is not None and time_zone is not None:
            ts = ts.tz_localize(None)
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
        unused_columns=unused_columns,
        # Source
        data_path=data_path,
        csv_sep=DEFAULT_CSV_SEP if sep is None else sep,
        csv_decimal=DEFAULT_CSV_DECIMAL if decimal is None else decimal,
        csv_thousands=thousands,
        csv_encoding=DEFAULT_CSV_ENCODING if encoding is None else encoding,
        date_format=date_format,
        # Train/test split
        start_date=start_date,
        time_zone=time_zone,
        # Diagnostics
        warnings=warnings,
    )


def _try_parse_first_date_column(
    data: pd.DataFrame,
    date_column: str | None = None,
    series_id_column: str | None = None,
    dayfirst: bool | None = None,
    date_format: str | None = None,
    source: str = "file",
    notes: list[str] | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """
    Try to convert the first object or string dtype column to datetime.

    When a CSV is exported via `DataFrame.to_csv()` the DatetimeIndex
    becomes a regular column with object or string dtype (e.g. `"Unnamed: 0"` or
    `"date"`). `pd.read_csv(parse_dates=True)` often fails to
    auto-parse these. This helper converts the first parseable column
    in-place so that downstream `detect_date_column` can identify it. The
    dates are parsed as the generated script parses them (see
    `parse_text_dates`), day first when they read only so, and in the order
    of `dayfirst` or `date_format` when they read in both (see
    `_day_month_order`). A column of whole numbers that are all dates of
    eight digits ('20200131') is a column of dates too, in the same order of
    columns (see `_compact_dates`).

    A column of dates with empty cells, with UTC offsets that change or
    written in more than one format cannot be the date column (see
    `_read_date_column`). When it is the `date_column`, or no later column
    is converted, an error says why. When
    a later column is converted instead, a warning names the columns. The
    `date_column` is checked even when an earlier column was converted, and
    converted itself. Dates whose day and month read in both orders, with
    neither `dayfirst` nor `date_format` to decide, are read in the only
    order in which they have a regular frequency, with a note in `notes`;
    when both orders or neither have one, they raise `InvalidInputError`
    with code `'data_unreadable'` and a hint that names `dayfirst`, and so
    do dates that `dayfirst` contradicts (field `'dayfirst'`), also when a
    later column holds dates: such a column holds every date, so it is the
    date column.

    Parameters
    ----------
    data : pandas DataFrame
        DataFrame loaded from CSV.
    date_column : str, default None
        Name of the date column, when the caller gives it.
    series_id_column : str, default None
        Name of the column of series ids, read as text, which is never the
        date column: ids such as `'2001'` read as dates.
    dayfirst : bool, default None
        Order of the day and the month given by the caller, for dates that
        read in both.
    date_format : str, default None
        Format recorded by a profile of the data, which decides the order of
        dates that read in both.
    source : str, default 'file'
        Where the data come from: `'file'` for the CSV file of the data,
        `'exog'` for that of the future exogenous variables (see
        `_day_month_order`).
    notes : list of str, default None
        List the note of an order of the day and the month told from the
        regularity of the dates of the converted column is appended to
        (see `_day_month_order`).

    Returns
    -------
    data : pandas DataFrame
        DataFrame with the first date-like column converted (if found).
    date_format : str, None
        Format the generated script reads the dates of the date column with
        (`DataProfile.date_format`), or None when it needs none.
    """
    skipped = []
    converted, found_format, found_notes = None, None, []
    for col in data.columns:
        if col == series_id_column:
            continue
        col_notes = []
        if is_text(data[col]):
            parsed, issue, col_format = _read_date_column(
                                            name        = col,
                                            values      = data[col],
                                            named       = col == date_column,
                                            dayfirst    = dayfirst,
                                            date_format = date_format,
                                            source      = source,
                                            notes       = col_notes,
                                        )
        else:
            parsed, issue = _compact_dates(data[col]), None
            col_format = COMPACT_DATE_FORMAT
            if parsed is None:
                continue
        if issue is not None:
            if col == date_column or getattr(issue, "order", False):
                # A column whose order cannot be told holds every date: it is
                # the date column, and no later column takes its place.
                raise date_issue_error(issue)
            if date_column is None:
                skipped.append((col, issue))
            continue
        if parsed is None or parsed.isna().any():
            continue
        # A column without a day (times of day) does not take the place of a
        # date column that cannot be used.
        if skipped and not _has_date_part(_first_value(data[col])):
            continue
        data[col] = parsed
        converted, found_format, found_notes = col, col_format, col_notes
        if skipped:
            # The skipped columns may be exogenous variables, so the warning
            # says what was found and not how to fix a date column.
            found = " ".join(f"{summary}." for _, (summary, _) in skipped)
            _warnings.warn(
                f"{found} Column {col!r} is used as the date column instead; "
                f"pass `date_column` to choose another one.",
                UserWarning,
                stacklevel=_caller_stacklevel(),
            )
        break
    else:
        if skipped:
            col, issue = skipped[0]
            # A sparse column of dates may be an exogenous variable of data
            # without dates, which only a DataFrame can pass.
            raise date_issue_error(
                issue,
                f"{''.join(issue)} If the dates are in another column, pass its "
                f"name as `date_column`; if {col!r} is an exogenous variable "
                f"and the data has no dates, read the CSV with pandas and pass "
                f"the DataFrame instead of its path.",
            )

    # The named column is checked even when an earlier column was parsed,
    # as with a saved profile nothing else checks it before the script runs,
    # and it is converted here, with the order of its own dates.
    if (
        date_column is not None
        and date_column in data.columns
        and date_column != converted
    ):
        found_format, found_notes = None, []
        values = data[date_column]
        if is_text(values):
            col_notes = []
            parsed, issue, col_format = _read_date_column(
                                            name        = date_column,
                                            values      = values,
                                            named       = True,
                                            dayfirst    = dayfirst,
                                            date_format = date_format,
                                            source      = source,
                                            notes       = col_notes,
                                        )
            if issue is not None:
                raise date_issue_error(issue)
            if parsed is not None and not parsed.isna().any():
                data[date_column] = parsed
                found_format, found_notes = col_format, col_notes
        else:
            parsed = _compact_dates(values)
            if parsed is not None:
                data[date_column] = parsed
                found_format = COMPACT_DATE_FORMAT
    if notes is not None:
        notes.extend(found_notes)

    return data, found_format


def _read_date_column(
    name: str,
    values: pd.Series,
    named: bool,
    dayfirst: bool | None = None,
    date_format: str | None = None,
    source: str = "file",
    notes: list[str] | None = None,
) -> tuple[pd.Series | None, tuple[str, str] | None, str | None]:
    """
    Parse a text column as the generated script does, and say why it cannot
    be the date column when its dates have empty cells, UTC offsets that
    change, more than one format, or a day and a month whose order cannot
    be told.

    Parameters
    ----------
    name : str
        Name of the column, for the message.
    values : pandas Series
        Values of the column: text, or date objects.
    named : bool
        Whether the caller named this column as the date column (see
        `_text_dates_issue`).
    dayfirst : bool, default None
        Order of the day and the month given by the caller, for dates that
        read in both (see `_day_month_order`).
    date_format : str, default None
        Format recorded by a profile of these data, which decides the order
        of dates that read in both.
    source : str, default 'file'
        Where the column comes from, for the remedy of an issue and of a
        note (see `_day_month_order`).
    notes : list of str, default None
        List the note of an order of the day and the month told from the
        regularity of the dates is appended to, when the column is read
        (see `_day_month_order`).

    Returns
    -------
    parsed : pandas Series, None
        The column parsed as the generated script parses it (with NaT for
        the values that hold no date), or None when it does not parse or
        has an issue.
    issue : tuple, None
        Why the column holds dates but cannot be the date column, as what was
        found and how to fix it (see `_text_dates_issue`,
        `_mixed_formats_issue` and `_day_month_order`), or None.
    date_format : str, None
        Format the generated script reads the dates with
        (`DataProfile.date_format`), or None when it reads them without one.
    """
    found_notes: list[str] = []
    parsed, issue, recorded = _read_date_column_in_order(
                                  name        = name,
                                  values      = values,
                                  named       = named,
                                  dayfirst    = dayfirst,
                                  date_format = date_format,
                                  source      = source,
                                  notes       = found_notes,
                              )
    if parsed is not None and notes is not None:
        # Only the notes of a column that is read: one with an issue is not
        # the date column.
        notes.extend(found_notes)

    return parsed, issue, recorded


def _read_date_column_in_order(
    name: str,
    values: pd.Series,
    named: bool,
    dayfirst: bool | None,
    date_format: str | None,
    source: str,
    notes: list[str],
) -> tuple[pd.Series | None, tuple[str, str] | None, str | None]:
    """
    Do the work of `_read_date_column`, whose parameters and returns it
    takes, appending to `notes` the note of the order of the day and the
    month even when the column then has an issue.
    """
    chosen, recorded, issue = _day_month_order(
                                  name        = name,
                                  values      = values,
                                  named       = named,
                                  dayfirst    = dayfirst,
                                  date_format = date_format,
                                  source      = source,
                                  notes       = notes,
                              )
    if issue is not None:
        return None, issue, None
    if chosen is not None and chosen != guessed_date_format(values):
        # Day first after a first date that reads month first: pandas would
        # guess the other order from it.
        issue = _text_dates_issue(name, values, named)
        if issue is not None:
            return None, issue, None
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            parsed = pd.to_datetime(values, format=chosen)
        issue = _mixed_offsets_issue(name, parsed)
        return (None, issue, None) if issue is not None else (parsed, None, recorded)

    # Most date columns parse with the format of their first date, with no
    # empty cell and one time zone: no further check needed.
    parsed = _parse_with_guessed_format(values)
    if parsed is not None:
        if guessed_date_format(values) == COMPACT_DATE_FORMAT:
            # '20200131' read as text (with a thousands separator) is named as
            # the same dates read as whole numbers are.
            recorded = COMPACT_DATE_FORMAT
        return parsed, None, recorded
    issue = _text_dates_issue(name, values, named)
    if issue is not None:
        return None, issue, None
    # Mixed offsets are reported below, so the pandas warning about them
    # would only repeat it; so would its note that, without a format, it
    # parses each date on its own.
    with _warnings.catch_warnings():
        _warnings.filterwarnings(
            action   = "ignore",
            message  = ".*mixed time zones",
            category = FutureWarning,
        )
        _warnings.filterwarnings(
            action   = "ignore",
            message  = "Could not infer format",
            category = UserWarning,
        )
        try:
            parsed = parse_text_dates(values)
        except (ValueError, TypeError, AttributeError, OverflowError):
            # The generated script cannot read them either.
            parsed, issue = _read_dates_one_by_one(name, values, named)
            return parsed, issue, recorded if parsed is not None else None
    # Offsets in a spelling `time_zones` does not read give pandas
    # Timestamps of several offsets.
    issue = _mixed_offsets_issue(name, parsed)

    return (None, issue, None) if issue is not None else (parsed, None, recorded)


def _read_dates_one_by_one(
    name: str,
    values: pd.Series,
    named: bool,
) -> tuple[pd.Series | None, tuple[str, str] | None]:
    """
    Parse each date of a column on its own, for a column the generated
    script cannot read, and say why it cannot be the date column.

    Parameters
    ----------
    name : str
        Name of the column, for the message.
    values : pandas Series
        Values of the column: text, or date objects.
    named : bool
        Whether the caller named this column as the date column.

    Returns
    -------
    parsed : pandas Series, None
        The dates, read one by one, when the column is in one format the
        script reads otherwise and nothing proves that reading wrong; None
        when it does not parse or has an issue (day-first dates whose first
        date reads month-first and a later one does not, see
        `_day_first_issue`).
    issue : tuple, None
        Why the column holds dates but cannot be the date column (see
        `_mixed_formats_issue`), or None.
    """
    with _warnings.catch_warnings():
        _warnings.filterwarnings(
            action   = "ignore",
            message  = ".*mixed time zones",
            category = FutureWarning,
        )
        try:
            each = pd.to_datetime(values, format="mixed")
        except (ValueError, TypeError, AttributeError, OverflowError):
            return None, None
    issue = _mixed_offsets_issue(name, each)
    if issue is None:
        issue = _mixed_formats_issue(name, values, named, each)

    return (None, issue) if issue is not None else (each, None)


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

    return DateIssue(
        f"The dates of column {name!r} have {n_missing} empty cell(s), at row "
        f"position(s) {shown} (counting from 0, header excluded)",
        ": every row needs a date. Fill in or drop those rows.",
        hint = "Every row needs a date: fill in or drop the rows without one.",
    )


def _mixed_formats_issue(
    name: str,
    values: pd.Series,
    named: bool,
    each: pd.Series,
) -> tuple[str, str] | None:
    """
    Say why a column of dates written in more than one format cannot be the
    date column.

    The generated script reads the column with `pandas.to_datetime`, which
    takes the format of the first date for all of them and fails on a date
    written otherwise ('2015-01-01' and '2015/01/02', or a date with and
    without a time). Read one by one (`format='mixed'`), the profile would
    describe dates the script cannot read, so the column is rejected: a
    single format is what makes the reading unambiguous. The same holds for
    dates in one format that pandas reads otherwise from the first one
    ('01 May 2015' is read with a full month name, which '01 Jun 2015' is
    not), so the message quotes the format read and an ISO 8601 example. Zone names that
    change at a daylight saving time change ('CET', then 'CEST') are
    reported as time zones. Day-first dates whose first date reads
    month-first ('01/02/2023', then '13/02/2023') are read day first before
    this check (see `_day_month_order`); a format whose year comes first
    and whose day reads before its month ('2023-13-02') does not fit the
    format pandas guesses either, and the message says the dates are
    day-first (see `_day_first_issue`).

    Parameters
    ----------
    name : str
        Name of the column, for the message.
    values : pandas Series
        Values of the column, which the script cannot read.
    named : bool
        Whether the caller named this column as the date column. When
        False, its first date must clearly be one (see `_is_clearly_date`),
        as in `_text_dates_issue`.
    each : pandas Series
        The values parsed one by one.

    Returns
    -------
    issue : tuple, None
        What was found and how to fix it, or None when the column is not
        made of dates in more than one format.
    """
    first = first_date(values)
    if not isinstance(first, str) or (not named and not _is_clearly_date(first)):
        return None
    date_format = guessed_date_format(values)
    if date_format is None or each.isna().any():
        return None
    present = values.notna()
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        day_first = guess_datetime_format(first, dayfirst=True)
        misfit = present & pd.to_datetime(
            values, format=date_format, errors="coerce"
        ).isna()
        if day_first not in (None, date_format):
            read_day_first = pd.to_datetime(
                values, format=day_first, errors="coerce"
            )
            misfit_day_first = present & read_day_first.isna()
            if not misfit_day_first.any():
                if not misfit.any():
                    return None
                return _day_first_issue(
                    name           = name,
                    first          = first,
                    date_format    = date_format,
                    other          = values[misfit].iloc[0],
                    read_day_first = read_day_first,
                    date           = read_day_first[misfit].iloc[0],
                )
            # The date to quote fits neither reading of the first one.
            if (misfit & misfit_day_first).any():
                misfit = misfit & misfit_day_first
    if not misfit.any():
        return None
    zones = _changing_zone_names(values)
    if zones is not None:
        return _mixed_zones_message(name, zones)
    other = values[misfit].iloc[0]
    example = _iso_example(each, each[misfit].iloc[0])

    # Not "more than one format": '01 May 2015' and '01 Jun 2015' are in
    # one, and pandas still reads 'May' as a full month name ('%B').
    return DateIssue(
        f"The dates of column {name!r} do not all follow the format of the "
        f"first one ({date_format!r}, read from {_shown_date(first)!r}), "
        f"such as {_shown_date(other)!r}",
        f": the generated script reads every date with the format of the "
        f"first one. Write every date in the same format, such as "
        f"{example!r}.",
        hint = (
            f"Write every date of the column in the same format, such as "
            f"{example!r}."
        ),
    )


def _day_first_issue(
    name: str,
    first: str,
    date_format: str,
    other: str,
    read_day_first: pd.Series,
    date: object,
) -> "DateIssue":
    """
    Say why day-first dates whose first date also reads month-first cannot
    be the date column: the generated script reads them with the month-first
    format of the first one, and `other` does not fit it.

    Parameters
    ----------
    name : str
        Name of the column, for the message.
    first : str
        First date of the column.
    date_format : str
        Month-first format pandas guesses from the first date.
    other : str
        A date of the column that does not fit `date_format`.
    read_day_first : pandas Series
        The column read day-first, for the ISO 8601 example.
    date : object
        `other` read day-first.

    Returns
    -------
    issue : DateIssue
        What was found and how to fix it.
    """
    example = _iso_example(read_day_first, date)

    return DateIssue(
        f"The dates of column {name!r} are written day first, but the first "
        f"one, {_shown_date(first)!r}, also reads month first "
        f"({date_format!r}), the format the generated script reads every "
        f"date with, and {_shown_date(other)!r} does not fit it",
        f": write the dates in ISO 8601, such as {example!r}, or read them "
        f"with pandas.to_datetime(..., dayfirst=True) before passing them.",
        hint = (
            f"Write the dates of the column in ISO 8601, such as {example!r}."
        ),
    )


def _iso_example(each: pd.Series, date: object) -> str:
    """
    Return a date of the column written in ISO 8601, as the example of a
    format every row can follow: without a time when no date of the column
    has one, with it (and its offset) otherwise.
    """
    date = pd.Timestamp(date)
    try:
        has_time = bool((each != each.dt.normalize()).any())
    except (AttributeError, TypeError):
        has_time = True

    return date.isoformat(sep=" ") if has_time else date.strftime("%Y-%m-%d")


# A zone name written after the time ('2012-03-24 00:00:00 CET').
_ZONE_NAME = re.compile(r"^(.*\S)\s+([A-Za-z]{2,5})$")


def _changing_zone_names(values: pd.Series) -> list[str] | None:
    """
    Return the zone names of dates in one format but for a zone name that
    changes ('CET', then 'CEST'), in order of appearance; None otherwise.
    """
    text = values[values.notna()].astype(str)
    matches = text.str.extract(_ZONE_NAME)
    if matches.isna().any().any():
        return None
    zones = list(dict.fromkeys(matches[1]))
    if len(zones) < 2:
        return None
    dates = matches[0]
    date_format = guessed_date_format(dates)
    if date_format is None:
        return None
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        parsed = pd.to_datetime(dates, format=date_format, errors="coerce")

    return zones if parsed.notna().all() else None


def _shown_date(value: object) -> str:
    """
    Return a date of the data for a message, cut in the middle when long:
    what differs between formats (a time, a zone name) is often at the end.
    """
    text = str(value)
    return text if len(text) <= 60 else f"{text[:28]}...{text[-28:]}"


class DateIssue(tuple):
    """
    Why a column of dates cannot be the date column: what was found and how
    to fix it, which joined make the message, plus `hint`, the remedy
    without the pandas calls that only apply in Python, the `code` and
    `field` of the error (None for the default code, and `'data'`), and
    whether it is about the order of the day and the month (`order`): such
    a column holds every date, so it is the date column, and another one is
    never used in its place.
    """

    hint: str
    code: str | None
    field: str
    order: bool

    def __new__(
        cls,
        found: str,
        fix: str,
        hint: str,
        code: str | None = None,
        field: str = "data",
        order: bool = False,
    ) -> "DateIssue":
        issue = super().__new__(cls, (found, fix))
        issue.hint = hint
        issue.code = code
        issue.field = field
        issue.order = order
        return issue


def date_issue_hint(issue: tuple[str, str]) -> str | None:
    """
    Return the remedy of a date issue of `_read_date_column` as a hint.
    """
    return getattr(issue, "hint", None)


def date_issue_error(
    issue: tuple[str, str],
    message: str | None = None,
) -> InvalidInputError:
    """
    Return the error of a date issue of `_read_date_column`, with its code,
    its field and its hint.

    Parameters
    ----------
    issue : tuple
        What was found and how to fix it, a `DateIssue` or a plain tuple.
    message : str, default None
        Message of the error. If None, the joined issue.

    Returns
    -------
    error : InvalidInputError
        Error with the code (`'invalid_argument'` by default), the field
        (`'data'` by default) and the hint of the issue.
    """
    return InvalidInputError(
        "".join(issue) if message is None else message,
        code  = getattr(issue, "code", None),
        field = getattr(issue, "field", "data"),
        hint  = date_issue_hint(issue),
    )


# Remedy of a CSV file whose dates read both day first and month first,
# which only whoever wrote them can tell.
DAYFIRST_HINT = (
    "Profile the file saying the order of its dates, with `dayfirst` (True "
    "when they are written day first, as '31/01/2024', False when month "
    "first, as '01/31/2024') in `profile()`, `--dayfirst` or `--monthfirst` "
    "in the `profile` command, or `dayfirst` (true or false) in the "
    "`profile` tool of the MCP server, and use that profile. The dates do "
    "not tell it: ask whoever wrote the file if it is not known."
)

# Remedy of the same dates in a DataFrame, which only the Python API takes.
DAYFIRST_FRAME_HINT = (
    "Profile the data saying the order of its dates, with `dayfirst` in "
    "`profile()` (True when they are written day first, as '31/01/2024', "
    "False when month first, as '01/31/2024'), and use that profile. The "
    "dates do not tell it: ask whoever wrote them if it is not known."
)

# Remedy of a file of future exogenous variables whose dates read both day
# first and month first, when the format of the data does not decide it.
EXOG_DATES_HINT = (
    "Write the dates of the future exogenous values in ISO 8601, such as "
    "'2024-01-31', which reads one way only."
)

# Format of the dates written as whole numbers of eight digits, year, month
# and day ('20200131'), as many exports write them.
COMPACT_DATE_FORMAT = "%Y%m%d"


def _reads_with(values: pd.Series, date_format: str) -> pd.Series:
    """
    Return which values read as a date with a format.
    """
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        try:
            parsed = pd.to_datetime(values, format=date_format, errors="coerce")
        except (ValueError, TypeError, AttributeError, OverflowError):
            return pd.Series(False, index=values.index)

    return pd.Series(pd.notna(parsed), index=values.index)


def _day_month_order(
    name: str,
    values: pd.Series,
    named: bool,
    dayfirst: bool | None = None,
    date_format: str | None = None,
    source: str = "file",
    notes: list[str] | None = None,
) -> tuple[str | None, str | None, "DateIssue | None"]:
    """
    Tell the order of the day and the month of text dates that write both
    as numbers before the year ('01/02/2020'), which pandas reads month
    first unless told otherwise.

    The order is told when every date reads in only one of them (a day
    after the 12th, '13/02/2020', settles day first). When every date reads
    in both, it is never guessed: `date_format` (the format of a profile of
    these data) or `dayfirst` decide it; otherwise, the dates are read in
    both orders, and when only one of the readings has a regular frequency
    (`infer_frequency` on the sorted dates: monthly data of five years
    written '02/01/2015' reads `'MS'` month first and none day first), it
    is the order, with a note that says so and how to give the other one.
    When both readings are regular (three dates, `'D'` and `'MS'`), or
    neither is, the order is an issue. `dayfirst` against the dates is an
    issue too.

    Parameters
    ----------
    name : str
        Name of the column, for the message.
    values : pandas Series
        Values of the column: text, or date objects.
    named : bool
        Whether the caller named this column as the date column. When
        False, its first date must clearly be one (see `_is_clearly_date`).
    dayfirst : bool, default None
        Order given by the caller: True for day first, False for month
        first. None when it is not given.
    date_format : str, default None
        Format a profile of the data recorded (`DataProfile.date_format`),
        which decides the order of dates that read in both.
    source : str, default 'file'
        Where the column comes from, for the remedy of the issue and of the
        note: `'file'` for the CSV file of the data (`dayfirst` in every
        interface), `'frame'` for data passed in memory (`dayfirst` in
        `profile()`) and `'exog'` for the CSV file of the future exogenous
        variables (dates in ISO 8601), whose order `date_format`, the
        format of the data, decides when it can.
    notes : list of str, default None
        List the note of an order told from the regularity of the dates is
        appended to (see `_regular_order_note`).

    Returns
    -------
    chosen : str, None
        Format to read the dates with, or None when their order is not in
        question (other formats, or dates that read in neither order).
    recorded : str, None
        Format the generated script names (`DataProfile.date_format`): the
        chosen one, in either order (pandas reads day-first dates month
        first unless told, even when their first date says so, and a file
        of future exogenous variables whose dates read in both is read in
        the order of the data), or None when the order is not in question.
    issue : DateIssue, None
        Why the order cannot be told, or None.
    """
    first = first_date(values)
    if type(first) is not str:
        return None, None, None
    # pandas guesses no format for a year of two digits ('01/02/18'), and
    # reads such dates one by one, month first when it can.
    short_year = short_year_format(first)
    if not named and short_year is None and not _is_clearly_date(first):
        return None, None, None
    guessed = guessed_date_format(values)
    formats = day_month_formats(guessed if guessed is not None else short_year)
    if formats is None:
        return None, None, None
    month_first, day_first = formats
    present = values[~missing_dates(values)]
    by_month = _reads_with(present, month_first)
    by_day = _reads_with(present, day_first)
    if by_month.all() and by_day.all():
        if _same_dates(present, formats):
            # Each day is its month ('01/01/2000' every year): either order
            # gives the same dates, so there is nothing to tell.
            return None, None, None
        if date_format in formats:
            chosen = date_format
        elif dayfirst is not None:
            chosen = day_first if dayfirst else month_first
        else:
            frequencies = [_reading_frequency(present, fmt) for fmt in formats]
            regular = [fmt for fmt, freq in zip(formats, frequencies) if freq]
            if len(regular) != 1:
                return None, None, _ambiguous_order_issue(
                    name, present, formats, source, frequencies
                )
            chosen = regular[0]
            if notes is not None:
                notes.append(
                    _regular_order_note(
                        name      = name,
                        values    = present,
                        formats   = formats,
                        chosen    = chosen,
                        frequency = frequencies[formats.index(chosen)],
                        source    = source,
                    )
                )
        return chosen, chosen, None
    if not by_month.all() and not by_day.all():
        return None, None, None
    chosen = day_first if by_day.all() else month_first
    if dayfirst is not None and dayfirst != (chosen == day_first):
        other = present[~(by_month if dayfirst is False else by_day)].iloc[0]
        return None, None, _order_contradiction_issue(name, dayfirst, other)

    # Named in either order: the future exogenous variables, whose dates may
    # read in both, are read in the order of the data.
    return chosen, chosen, None


def _same_dates(values: pd.Series, formats: tuple[str, str]) -> bool:
    """
    Return whether text dates read the same in both orders of the day and
    the month: every day is its month.
    """
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        readings = [
            pd.to_datetime(values, format=date_format) for date_format in formats
        ]

    return bool((readings[0] == readings[1]).all())


def _reading_frequency(values: pd.Series, date_format: str) -> str | None:
    """
    Return the frequency of text dates read with a format, as the profile
    infers it on the sorted dates (`infer_frequency`), or None when they
    have none.
    """
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        try:
            dates = pd.to_datetime(values, format=date_format)
            index = pd.DatetimeIndex(dates.drop_duplicates()).sort_values()
        except (ValueError, TypeError, AttributeError, OverflowError):
            # Offsets that change: the dates are rejected further on.
            return None

    return infer_frequency(index)


def _first_two_readings(
    values: pd.Series,
    formats: tuple[str, str],
) -> tuple[object, list[str]]:
    """
    Return the first date whose day is not its month, as written, with its
    readings day first and month first.
    """
    month_first, day_first = formats
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        by_day = pd.to_datetime(values, format=day_first)
        by_month = pd.to_datetime(values, format=month_first)
    differ = np.flatnonzero((by_day != by_month).to_numpy())
    position = differ[0] if len(differ) else 0
    readings = [by_day.iloc[position], by_month.iloc[position]]
    has_time = any(reading != reading.normalize() for reading in readings)
    shown = [
        reading.isoformat(sep=" ") if has_time else reading.strftime("%Y-%m-%d")
        for reading in readings
    ]

    return values.iloc[position], shown


def _ambiguous_order_issue(
    name: str,
    values: pd.Series,
    formats: tuple[str, str],
    source: str,
    frequencies: list[str | None],
) -> "DateIssue":
    """
    Say that the dates of a column read both day first and month first,
    with the two readings of the first one whose day is not its month, and
    that the regularity of the dates does not tell the order either: both
    readings have a frequency (`frequencies`, month first and day first),
    or neither has one.
    """
    date, shown = _first_two_readings(values, formats)
    by_month, by_day = frequencies
    regularity = (
        f"both readings have a regular frequency ({by_day!r} day first and "
        f"{by_month!r} month first)"
        if by_month and by_day else
        "neither reading has a regular frequency"
    )
    found = (
        f"The dates of column {name!r} read both day first and month first: "
        f"no day is after the 12th, so {_shown_date(date)!r} may be "
        f"{shown[0]!r} or {shown[1]!r}, and {regularity}, so the order is not "
        f"guessed"
    )
    if source == "exog":
        return DateIssue(
            found,
            ". Write them in ISO 8601, which reads one way only.",
            hint  = EXOG_DATES_HINT,
            code  = "data_unreadable",
            field = "exog",
            order = True,
        )
    noun = "file" if source == "file" else "data"

    return DateIssue(
        found,
        f". Profile the {noun} saying which it is, with `dayfirst`.",
        hint  = DAYFIRST_HINT if source == "file" else DAYFIRST_FRAME_HINT,
        code  = "data_unreadable",
        order = True,
    )


def _regular_order_note(
    name: str,
    values: pd.Series,
    formats: tuple[str, str],
    chosen: str,
    frequency: str,
    source: str,
) -> str:
    """
    Say that the order of the day and the month of dates that read in both
    was told from their regularity: only the reading in `chosen` has a
    regular frequency. The note says how to give the other order.
    """
    date, shown = _first_two_readings(values, formats)
    day_first = chosen == formats[1]
    read, other = ("day", "month") if day_first else ("month", "day")
    if not day_first:
        shown = shown[::-1]
    if source == "exog":
        remedy = f"write them in ISO 8601 (such as {shown[1]!r})"
    elif source == "file":
        remedy = (
            f"profile the file again with `dayfirst={not day_first}` in "
            f"`profile()`, `--{other}first` in the `profile` command or "
            f"`dayfirst` {str(not day_first).lower()} in the `profile` tool "
            f"of the MCP server"
        )
    else:
        remedy = f"profile the data again with `dayfirst={not day_first}`"

    return (
        f"The dates of column {name!r} read both day first and month first "
        f"(no day is after the 12th): they were read {read} first, the only "
        f"order in which they have a regular frequency ({frequency!r}), so "
        f"{_shown_date(date)!r} is {shown[0]!r} and not {shown[1]!r}. If they "
        f"are written {other} first, {remedy}."
    )


def _order_contradiction_issue(
    name: str,
    dayfirst: bool,
    other: str,
) -> "DateIssue":
    """
    Say that the dates of a column do not read in the order `dayfirst`
    gives, quoting one that does not.
    """
    given, read = ("day", "month") if dayfirst else ("month", "day")

    return DateIssue(
        f"`dayfirst` is {dayfirst}, but the dates of column {name!r} do not "
        f"read {given} first: {_shown_date(other)!r} only reads {read} first",
        ". Leave `dayfirst` out to tell the order from the dates.",
        hint  = "Leave `dayfirst` out, so the order is told from the dates.",
        field = "dayfirst",
        order = True,
    )


def _compact_dates(values: pd.Series) -> pd.Series | None:
    """
    Return a column of whole numbers that are all dates of eight digits,
    year, month and day ('20200131'), read as dates; None otherwise.

    Whole numbers only (no missing value), of eight digits, and each a
    real day that pandas can hold (years 1677 to 2262): amounts, counts and
    codes are not dates.
    """
    if pd.api.types.is_bool_dtype(values) or not pd.api.types.is_integer_dtype(values):
        return None
    if values.empty or values.isna().any():
        return None
    numbers = values.astype("int64")
    if not ((numbers >= 10_000_101) & (numbers <= 99_991_231)).all():
        return None
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        parsed = pd.to_datetime(numbers, format=COMPACT_DATE_FORMAT, errors="coerce")

    return parsed if parsed.notna().all() else None


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

    return DateIssue(
        f"The dates of column {name!r} mix time zones ({shown})",
        f", so they cannot be placed on one time axis (local time does that "
        f"across a daylight saving time change). Write every date in one time "
        f"zone: {advice}",
        hint = (
            "Write every date in one time zone: in UTC for data recorded "
            "within the day, or without the time zone for daily or coarser "
            "data."
        ),
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
    date_format: str | None = None,
    dayfirst: bool | None = None,
) -> tuple[str | None, str]:
    """
    Detect the datetime column and determine the index type.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    date_column : str, default None
        User-specified date column name.
    date_format : str, default None
        Format recorded by a profile of the data, which decides the order of
        text dates whose day and month read in both (see
        `_day_month_order`).
    dayfirst : bool, default None
        Order of the day and the month of those dates given by the caller:
        True for day first, False for month first.

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
    column of dates with empty cells, with time zones that change, written
    in more than one format, or whose day and month read in both orders
    with nothing to tell which (see `_day_month_order`) raises a
    `ValueError` that says so. Whole numbers that are all dates of eight
    digits ('20200131') are dates (see `_compact_dates`).
    """
    if date_column is not None:
        if date_column in data.columns:
            values = data[date_column]
            if is_text(values):
                # Checked first: a column with empty cells or mixed time
                # zones holds dates, so the message below would be wrong.
                # Text dates here come from a DataFrame: those of a CSV file
                # were read already.
                _, issue, _ = _read_date_column(
                                  name        = date_column,
                                  values      = values,
                                  named       = True,
                                  dayfirst    = dayfirst,
                                  date_format = date_format,
                                  source      = "frame",
                              )
                if issue is not None:
                    raise date_issue_error(issue)
            elif _compact_dates(values) is not None:
                return date_column, "datetime"
            if _is_datetime_like(values):
                return date_column, "datetime"
            raise InvalidInputError(
                f"date_column='{date_column}' does not hold dates: values "
                f"such as {_unparsable_dates(data[date_column])} could not be "
                f"parsed as timestamps. Pass the column that holds the dates, "
                f"or convert it with pandas.to_datetime before profiling.",
                field = "date_column",
                hint  = "Write the dates in ISO 8601, such as '2023-03-01'.",
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
                hint  = "Make the index a DatetimeIndex, or omit date_column.",
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


_MULTIINDEX_LEVELS_HINTS = {
    "data": (
        "Keep the series id and the date in the index and move the other "
        "levels into columns with `data.reset_index(level=...)`, or turn every "
        "level into a column with `data.reset_index()` and pass "
        "`series_id_column` and `date_column`."
    ),
    "exog": (
        "Keep the series id and the date in the index and move the other "
        "levels into columns with `exog.reset_index(level=...)`, or turn every "
        "level into a column with `exog.reset_index()`."
    ),
}
_MULTIINDEX_NAMES_HINTS = {
    "data": (
        "Name the levels with text, as in "
        "`data.rename_axis(['series_id', 'date'])`, or turn them into columns "
        "with `data.reset_index()` and pass their names as `series_id_column` "
        "and `date_column`."
    ),
    "exog": (
        "Name the levels as the series id and date columns of the data, as in "
        "`exog.rename_axis(['series_id', 'date'])`, and pass it as it is or "
        "with `reset_index()`."
    ),
}


def check_multiindex_levels(
    data: pd.DataFrame | pd.Series | None,
    field: str = "data",
) -> None:
    """
    Check that a MultiIndex has two levels named with text,
    `(series_id, date)`.

    The levels of the MultiIndex are read as the series id and the date
    columns, of the same names, and the generated script reads them from
    the frame saved with `to_csv()`. That file leaves the header of a level
    without a name empty (`pd.read_csv` reads it back as `'Unnamed: 0'`),
    and the script names its columns with text, so a level without a name,
    or named with a number, would run here on one column and in the script
    on another. Other levels than those two would be read as columns too,
    and in the order given. Each is rejected instead of guessed.

    Parameters
    ----------
    data : pandas DataFrame, pandas Series, None
        Data, or future exogenous variables, to check. Nothing is checked
        when it has no MultiIndex (None included).
    field : str, default 'data'
        Argument that passed `data`: `'data'` or `'exog'`, reported with
        the error.

    Returns
    -------
    None

    Raises
    ------
    InvalidInputError
        When the MultiIndex does not have two levels, or a level has no
        name or a name that is not text.
    """
    if not isinstance(getattr(data, "index", None), pd.MultiIndex):
        return
    names = list(data.index.names)
    if len(names) != 2:
        message = (
            f"`{field}` is indexed by a MultiIndex with {len(names)} "
            f"level{'s' if len(names) != 1 else ''} (names {names}). A "
            f"MultiIndex is read as the series id and the date, "
            f"`(series_id, date)`, so it must have two levels."
        )
        hint = _MULTIINDEX_LEVELS_HINTS[field]
    elif any(name is None for name in names):
        message = (
            f"`{field}` is indexed by a MultiIndex with levels without a name "
            f"(names {names}). The levels are read as columns of the same "
            f"name, and `to_csv()` writes an empty header for a level without "
            f"a name, so the generated script could not read it from the "
            f"saved file."
        )
        hint = _MULTIINDEX_NAMES_HINTS[field]
    elif not all(isinstance(name, str) for name in names):
        message = (
            f"`{field}` is indexed by a MultiIndex with levels not named with "
            f"text (names {names}). The levels are read as columns of the same "
            f"name, and the generated script names its columns with text."
        )
        hint = _MULTIINDEX_NAMES_HINTS[field]
    else:
        return

    raise InvalidInputError(message, field=field, hint=hint)


def _normalize_multiindex(
    data: pd.DataFrame,
    date_column: str | None,
    series_id_column: str | None,
) -> tuple[pd.DataFrame, str | None, str | None]:
    """
    Flatten a MultiIndex DataFrame into long format.

    A two-level MultiIndex is interpreted as `(series_id, datetime)`:
    level 0 identifies the series and level 1 is the datetime index.
    The levels are reset into regular columns of the same name so that all
    downstream profiling helpers operate on a flat long-format DataFrame.
    A MultiIndex of another number of levels, or with a level without a
    name or not named with text, raises (see `check_multiindex_levels`).

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset. Returned unchanged if its index is not a
        MultiIndex.
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

    Raises
    ------
    InvalidInputError
        When the MultiIndex does not have two levels named with text.
    """
    check_multiindex_levels(data, field="data")
    if not isinstance(data.index, pd.MultiIndex):
        return data, date_column, series_id_column

    id_name, date_name = data.index.names
    data = data.reset_index()

    if series_id_column is None:
        series_id_column = id_name
    if date_column is None:
        date_column = date_name

    return data, date_column, series_id_column


def _validate_target_format(
    target: str | list[str],
    series_id_column: str | None,
) -> None:
    """
    Validate that a list of targets comes without `series_id_column`.

    A list of target columns is wide format and `series_id_column` is long
    format. Read as wide, long data failed with an error about repeated
    timestamps that blamed the file, and wide data dropped the id column
    without a word.

    Parameters
    ----------
    target : str, list
        Name(s) of the target column(s).
    series_id_column : str, None
        Series identifier column the caller passed (not the one filled from
        a MultiIndex).
    """
    if not isinstance(target, list) or series_id_column is None:
        return
    raise InvalidInputError(
        f"`target` is a list of columns ({target}) and series_id_column="
        f"{series_id_column!r} was also given: a list of columns is wide "
        f"format (one column per series) and `series_id_column` is long "
        f"format (the series stacked in rows, told apart by that column). "
        f"For long format, pass `target` as the name of the column of "
        f"values, not as a list; for wide format, leave out "
        f"`series_id_column`.",
        field = "series_id_column",
    )


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
        col = frame[date_col]
        # Converting a column of dates again gives the same values, and per
        # series of long data it cost more than the rest of the profile.
        if not pd.api.types.is_datetime64_any_dtype(col):
            col = pd.to_datetime(col)
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


def _long_series_dates(
    dates: pd.DatetimeIndex,
    ids: pd.Series,
) -> dict[object, np.ndarray] | None:
    """
    Return the sorted, distinct dates of each series of long-format data, as
    nanoseconds since the epoch, in order of first appearance.

    Rows without a date or a series id, and series without rows (unused
    categories), are left out, as the generated script leaves them out.
    Time zone aware dates are read in their local time (pass them converted
    to UTC to read them in UTC).

    Parameters
    ----------
    dates : pandas DatetimeIndex
        Date of each row.
    ids : pandas Series
        Series id of each row.

    Returns
    -------
    series_dates : dict, None
        Dates of each series, keyed by its id. None when the dates do not
        fit in nanoseconds (before 1677 or after 2262), which leaves the
        frequency to the first series, with a note.
    """
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    try:
        dates = dates.as_unit("ns")
    except pd.errors.OutOfBoundsDatetime:
        return None
    codes, names = pd.factorize(ids)
    keep = (codes >= 0) & ~np.asarray(dates.isna())
    if not keep.any():
        return {}
    codes, positions = codes[keep], dates.asi8[keep]
    order = np.lexsort((positions, codes))
    codes, positions = codes[order], positions[order]
    repeated = np.r_[
        False, (codes[1:] == codes[:-1]) & (positions[1:] == positions[:-1])
    ]
    codes, positions = codes[~repeated], positions[~repeated]
    starts = np.r_[0, np.flatnonzero(np.diff(codes)) + 1]

    return {
        names[code]: chunk
        for code, chunk in zip(codes[starts], np.split(positions, starts[1:]))
    }


def _series_ending_early(
    dates: pd.DatetimeIndex,
    ids: pd.Series,
    values: pd.Series,
) -> tuple[str, dict[str, str]] | None:
    """
    Find the series of long-format data whose last value comes before the
    last date of the data.

    Rows without a value are left out, as skforecast drops the missing
    values at the end of a series, and so are rows without a date or a
    series id.

    Parameters
    ----------
    dates : pandas DatetimeIndex
        Date of each row.
    ids : pandas Series
        Series id of each row.
    values : pandas Series
        Target value of each row.

    Returns
    -------
    series_ending_early : tuple, None
        Last date with a value in the data and the series whose last value
        comes before it, mapped to the date of that value. None when every
        series reaches the last date.
    """
    codes, names = pd.factorize(ids)
    keep = (codes >= 0) & ~np.asarray(dates.isna()) & values.notna().to_numpy()
    if not keep.any():
        return None
    ends = pd.Series(dates[keep]).groupby(codes[keep]).max()
    last = ends.max()
    early = {
        str(names[code]): _fmt_timestamp(end)
        for code, end in ends.items() if end < last
    }
    if not early:
        return None

    return _fmt_timestamp(last), early


def _wide_series_ending_early(
    data: pd.DataFrame,
    target: list[str],
    date_col: str | None,
) -> tuple[str, dict[str, str]] | None:
    """
    Find the series of wide-format data (one target column per series) whose
    last value comes before the last date with a value, as
    `_series_ending_early` does for long-format data, from the missing
    values of each column only.

    Parameters
    ----------
    data : pandas DataFrame
        Wide-format data, dated by `date_col` or by its index.
    target : list of str
        Target columns, one per series.
    date_col : str, None
        Date column, or None when the index holds the dates.

    Returns
    -------
    series_ending_early : tuple, None
        Last date with a value in the data and the series whose last value
        comes before it, mapped to the date of that value. None when every
        series reaches the last date, or when the columns or the dates
        cannot be read one per series.
    """
    dates = row_dates(data, date_col)
    values = data[target]
    if dates is None or values.shape[1] != len(target):
        return None
    dates = pd.DatetimeIndex(dates)
    present = values.notna().to_numpy() & ~np.asarray(dates.isna())[:, None]
    has_value = present.any(axis=0)
    if not has_value.any():
        return None
    # The last value of each column, in date order (NaT first).
    order = np.argsort(dates.asi8, kind="stable")
    present = present[order]
    last_rows = len(present) - 1 - np.argmax(present[::-1], axis=0)
    ends = dates[order][last_rows]
    last = ends[has_value].max()
    early = {
        str(column): _fmt_timestamp(end)
        for column, end, valid in zip(target, ends, has_value)
        if valid and end < last
    }
    if not early:
        return None

    return _fmt_timestamp(last), early


def _finer_than_a_day(frequency: str | None) -> bool:
    """
    Return whether a frequency is a fixed step shorter than a day (hours,
    minutes).
    """
    if frequency is None:
        return False
    offset = pd.tseries.frequencies.to_offset(frequency)

    return (
        isinstance(offset, pd.offsets.Tick)
        and offset.nanos < _DAY_NANOS
    )


@functools.lru_cache(maxsize=256)
def _periods_per_year(frequency: str) -> float:
    """
    Return how many timestamps of a frequency fall in a year, to tell a finer
    frequency from a coarser one.
    """
    offset = pd.tseries.frequencies.to_offset(frequency)
    if isinstance(offset, pd.offsets.Tick):
        return 365 * _DAY_NANOS / offset.nanos

    # Forty years, so that steps of several years are counted too.
    return len(pd.date_range("2001-01-01", "2040-12-31", freq=offset)) / 40


def _own_frequencies(series_dates: dict[object, np.ndarray]) -> dict[object, str]:
    """
    Return the frequency of each series that pandas infers on its first
    dates (`_OWN_FREQUENCY_DATES`), when they are regular and the whole
    series fills at least half of its grid.

    Reading only the first dates bounds the cost on long series, and the
    results are reused for series whose first dates have the same steps and
    start on the same weekday and time of day, and for periods of half a
    month or more on the same day of the month and month (the series of a
    panel usually do). Series with steps of several lengths that
    no frequency pandas infers can have (gaps) are not passed to pandas. A
    series whose later dates are sparser or denser than its first ones
    (daily then weekly, every two hours then hourly) has no frequency of its
    own. The other dates are checked against the grid of the frequency of
    the data.
    """
    day = _DAY_NANOS
    year = _YEAR_NANOS
    cache: dict[tuple, str | None] = {}
    own = {}
    for name, dates in series_dates.items():
        if len(dates) < _FREQUENCY_WINDOW:
            continue
        head = dates[:_OWN_FREQUENCY_DATES]
        steps = np.diff(head)
        # Steps of several lengths are regular only for business days (one
        # or three days) and for calendar periods of half a month or more;
        # other ones are gaps, which pandas would reject at a cost.
        if steps.min() != steps.max() and not (
            ((steps == day) | (steps == 3 * day)).all()
            or (steps.min() >= 13 * day and not (steps % day).any())
        ):
            continue
        # What pandas infers depends on the steps, the weekday and the time of
        # day of the first date, and for periods of half a month or more on
        # its day of the month and month.
        first = pd.Timestamp(head[0])
        key = (steps.tobytes(), first.dayofweek, int(head[0] % day)) + (
            (first.day, first.month) if steps.min() >= 13 * day else ()
        )
        if key not in cache:
            cache[key] = pd.infer_freq(pd.DatetimeIndex(head))
        frequency = cache[key]
        if frequency is None:
            continue
        # The whole series must fill at least half of the grid of that
        # frequency, and not hold many more dates than the grid (a few stray
        # ones at most): a series that turns sparser (daily, then weekly) or
        # finer (every two hours, then hourly) has no frequency of its own.
        size = (dates[-1] - dates[0]) / year * _periods_per_year(frequency) + 1
        if _MIN_FREQUENCY_COVERAGE * size <= len(dates) <= 1.1 * size + 2:
            own[name] = frequency

    return own


def _grid(
    dates: np.ndarray,
    frequency: str,
) -> tuple[pd.DateOffset, np.ndarray | int]:
    """
    Return the grid of `frequency` that most of the dates lie on.

    For a fixed step, the grid is the phase shared by most dates (an int, in
    nanoseconds). For a calendar frequency (business days, weeks, months),
    it is the timestamps of the grid at the time of day shared by most
    dates and, for a multiple (every second week), on the one of its grids
    that holds most dates. `dates` holds the dates of every series, repeated
    ones included, so a long series off the grid of many shorter ones does
    not set the grid.
    """
    offset = pd.tseries.frequencies.to_offset(frequency)
    if isinstance(offset, pd.offsets.Tick):
        phases, counts = np.unique(dates % offset.nanos, return_counts=True)
        return offset, int(phases[np.argmax(counts)])

    day = _DAY_NANOS
    times, counts = np.unique(dates % day, return_counts=True)
    first, last = pd.Timestamp(dates.min()), pd.Timestamp(dates.max())
    start = first.normalize() + pd.Timedelta(int(times[np.argmax(counts)]))
    if start > first:
        start -= pd.Timedelta(1, "D")
    grid = pd.date_range(start, last, freq=offset.base).asi8
    if offset.n > 1:
        positions, on_grid = _grid_positions(dates, grid)
        phases, counts = np.unique(positions[on_grid] % offset.n, return_counts=True)
        if len(phases):
            grid = grid[int(phases[np.argmax(counts)])::offset.n]

    return offset, grid


def _grid_positions(
    dates: np.ndarray,
    grid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Return the position of each date in the timestamps of a calendar grid,
    and whether the date lies on it.
    """
    positions = np.searchsorted(grid, dates)
    if len(grid) == 0:
        return positions, np.zeros(len(dates), dtype=bool)
    on_grid = grid[np.minimum(positions, len(grid) - 1)] == dates

    return positions, on_grid


def _longest_series(
    series_dates: dict[object, np.ndarray],
    names: list,
) -> object:
    """
    Return the series with the most dates among `names`; on a tie, the one
    that starts first, then ends first, then comes first by name, so the
    order of the rows does not decide.
    """

    return min(
        names,
        key=lambda name: (
            -len(series_dates[name]), series_dates[name][0], series_dates[name][-1],
            str(name),
        ),
    )


def _coarser_frequency(
    dates: np.ndarray,
    positions: np.ndarray,
    own_frequency: str | None,
    offset: pd.DateOffset,
    frequency: str,
    evidence: float,
) -> str | None:
    """
    Return the coarser frequency of a series whose dates lie on the grid of
    `frequency`, or None when the series is of that frequency with gaps.

    A series is of a coarser frequency when it has one of its own with no
    two of its first dates one step of the grid apart (a weekly series,
    also with a stray date later on). Otherwise a series with two dates one
    step apart (business days among daily ones), or with fewer than
    `_FREQUENCY_WINDOW` dates (three rows a week apart may be a sparse
    daily series), is of the frequency of the grid. The others are of a
    coarser frequency when they are made of month starts or month ends
    only (named by the step in months), when all their steps are multiples
    of one step and chance cannot explain it (`evidence`, see
    `_COARSER_EVIDENCE`), or when pandas infers one with gaps on calendar
    steps (half a month or more). Sparse series that none of these names
    count as gaps.

    Parameters
    ----------
    dates : numpy ndarray
        Dates of the series, in nanoseconds.
    positions : numpy ndarray
        Position of each date on the grid.
    own_frequency : str, None
        Frequency of the series on its first dates (see `_own_frequencies`).
    offset : pandas DateOffset
        Offset of `frequency`.
    frequency : str
        Candidate frequency of the data.
    evidence : float
        Threshold of `(n - 1) * log(k)` for a series of n dates whose steps
        are all multiples of k steps of the grid.

    Returns
    -------
    coarser_frequency : str, None
        Frequency of the series, or None when it is `frequency`.
    """
    if len(dates) < _FREQUENCY_WINDOW:
        return None
    steps = np.diff(positions)
    if own_frequency is not None and steps[:_OWN_FREQUENCY_DATES - 1].min() > 1:
        return own_frequency
    if steps.min() == 1:
        return None

    day = _DAY_NANOS
    timestamps = pd.DatetimeIndex(dates)
    coarser = None
    if (dates % day == dates[0] % day).all():
        anchor = (
            "MS" if timestamps.is_month_start.all()
            else "ME" if timestamps.is_month_end.all()
            else None
        )
        if anchor is not None:
            months = np.diff(timestamps.year * 12 + timestamps.month)
            coarser = _frequency_name(
                timestamps[0], pd.tseries.frequencies.to_offset(anchor) * int(
                    np.gcd.reduce(months)
                )
            )
    if coarser is None:
        step = int(np.gcd.reduce(steps))
        if step > 1 and (len(dates) - 1) * np.log(step) > evidence:
            coarser = _frequency_name(timestamps[0], offset * step)
    if coarser is None:
        # pandas infers a frequency with gaps from calendar steps that the
        # checks above do not name (half months, business month ends). Only
        # on gap-free stretches: windows of three on every sparse series
        # would cost seconds on a thousand of them.
        raw_steps = np.diff(dates)
        if raw_steps.min() >= 13 * day and not (raw_steps % day).any():
            coarser = infer_frequency(timestamps, regular_gaps=False)
    if coarser is not None and _periods_per_year(coarser) < _periods_per_year(
        frequency
    ):
        return coarser

    return None


def _frequency_name(start: pd.Timestamp, offset: pd.DateOffset) -> str:
    """
    Return the name pandas gives to the frequency of dates from `start` every
    `offset` (`'W-MON'` for five business days, `'YS-JAN'` for twelve month
    starts), or the name of the offset when pandas gives none.
    """
    name = pd.infer_freq(pd.date_range(start, periods=3, freq=offset))

    return name if name is not None else offset.freqstr


def _check_long_frequency(
    series_dates: dict[object, np.ndarray],
    all_dates: np.ndarray,
    own: dict[object, str],
    frequency: str,
) -> tuple[int | None, str | None, list[str], int, bool]:
    """
    Check that every series fits the grid of `frequency`.

    Every date must lie on the grid, and no series may be of a coarser
    frequency (see `_coarser_frequency`). A series off the grid is of
    another frequency when it has one of its own; the others off the grid
    are, when pandas infers one with gaps on the longest of them, and have
    stray timestamps otherwise.

    Parameters
    ----------
    series_dates : dict
        Dates of each series (see `_long_series_dates`).
    all_dates : numpy ndarray
        Dates of every series, together.
    own : dict
        Frequency of each series that is regular on its first dates (see
        `_own_frequencies`).
    frequency : str
        Candidate frequency of the data.

    Returns
    -------
    n_missing : int, None
        Timestamps missing from the grid within the range of each series,
        summed, or None when the series do not fit.
    message : str, None
        Why the series do not fit, or None.
    others : list of str
        Frequencies of the series that do not fit, to try instead.
    n_blamed : int
        Number of dates of the series that do not fit, to report the error
        that blames the fewest.
    differ : bool
        Whether the message is about series of another frequency, rather
        than about stray timestamps.
    """
    offset, grid = _grid(all_dates, frequency)
    tick = isinstance(offset, pd.offsets.Tick)
    evidence = _COARSER_EVIDENCE + np.log(len(series_dates))

    n_missing = 0
    other_frequencies: dict[object, str] = {}
    off_grid: dict[object, np.ndarray] = {}
    for name, dates in series_dates.items():
        if tick:
            on_grid = dates % offset.nanos == grid
            positions = (dates - grid) // offset.nanos
        else:
            positions, on_grid = _grid_positions(dates, grid)
        if not on_grid.all():
            if own.get(name, frequency) != frequency:
                other_frequencies[name] = own[name]
            else:
                off_grid[name] = dates[~on_grid]
            continue
        other = _coarser_frequency(
            dates         = dates,
            positions     = positions,
            own_frequency = own.get(name),
            offset        = offset,
            frequency     = frequency,
            evidence      = evidence,
        )
        if other is not None:
            other_frequencies[name] = other
            continue
        n_missing += int(positions[-1] - positions[0]) + 1 - len(dates)

    if not other_frequencies and not off_grid:
        return n_missing, None, [], 0, False

    # The series off the grid are of another frequency when pandas infers
    # one with gaps on the longest of them (daily series off the grid of
    # business days); otherwise they have stray timestamps.
    if off_grid:
        longest = _longest_series(series_dates, list(off_grid))
        found = infer_frequency(pd.DatetimeIndex(series_dates[longest]))
        if found is not None and found != frequency:
            other_frequencies.setdefault(longest, found)

    failing = set(other_frequencies) | set(off_grid)
    n_blamed = sum(len(series_dates[name]) for name in failing)
    others = sorted(
        set(other_frequencies.values()),
        key=lambda freq: (-_periods_per_year(freq), freq),
    )
    if other_frequencies:
        name = _longest_series(series_dates, list(other_frequencies))
        # Named next to the longest series that fits, preferring one regular
        # at `frequency`.
        fitting = [key for key in series_dates if key not in failing]
        pool = fitting or [key for key in series_dates if key != name] or [name]
        regular = [key for key in pool if own.get(key) == frequency]
        reference = _longest_series(series_dates, regular or pool)
        message = _frequencies_differ(
            frequency, reference, other_frequencies[name], name
        )
        return None, message, others, n_blamed, True

    name = _longest_series(series_dates, list(off_grid))
    which = (
        f"Series {str(name)!r} has" if len(off_grid) == 1
        else f"{len(off_grid)} series, such as {str(name)!r}, have"
    )
    example = _fmt_timestamp(pd.Timestamp(off_grid[name][0]))
    message = (
        f"{which} timestamps off the {frequency!r} grid, for example "
        f"{example}. Every series of long-format data must have the same "
        f"frequency on the same grid: correct or drop those timestamps, or "
        f"forecast those series separately."
    )

    return None, message, others, n_blamed, False


def _in_hours(frequency: str | None) -> str | None:
    """
    Return a fixed step (days, weeks) as a number of hours (`'24h'`,
    `'168h'`), which pandas keeps in UTC on time zone aware dates, or None
    when the frequency is not a fixed step (months, business days).
    """
    if frequency is None:
        return None
    offset = pd.tseries.frequencies.to_offset(frequency)
    hour = _HOUR_NANOS
    if isinstance(offset, pd.offsets.Tick):
        nanos = offset.nanos
    elif isinstance(offset, pd.offsets.Week):
        nanos = offset.n * 7 * _DAY_NANOS
    else:
        return None
    if nanos % hour:
        return None

    return f"{nanos // hour}h"


def _infer_long_frequency(
    series_dates: dict[object, np.ndarray],
) -> tuple[str | None, int]:
    """
    Infer the frequency shared by the series of long-format data and count
    their missing timestamps, raising an `InvalidInputError` when they do
    not share one (see `_search_long_frequency`).

    Parameters
    ----------
    series_dates : dict
        Dates of each series (see `_long_series_dates`).

    Returns
    -------
    frequency : str, None
        Frequency of the data, or None when it cannot be inferred.
    n_missing_timestamps : int
        Number of timestamps missing from the grid between the first and the
        last date of each series, summed over the series. 0 when the
        frequency is None.
    """
    frequency, n_missing, error = _search_long_frequency(series_dates)
    if error is not None:
        raise InvalidInputError(error[1], field="data")

    return frequency, n_missing


def _search_long_frequency(
    series_dates: dict[object, np.ndarray],
) -> tuple[str | None, int, tuple[int, str, bool] | None]:
    """
    Search the frequency shared by the series of long-format data and count
    their missing timestamps.

    Parameters
    ----------
    series_dates : dict
        Dates of each series (see `_long_series_dates`).

    Returns
    -------
    frequency : str, None
        Frequency of the data, or None when it cannot be inferred.
    n_missing_timestamps : int
        Number of timestamps missing from the grid between the first and the
        last date of each series, summed over the series. 0 when the
        frequency is None.
    error : tuple, None
        When no candidate fits: the number of dates blamed, the message and
        whether it is about series of another frequency (see
        `_check_long_frequency`). None otherwise.

    Notes
    -----
    The candidates are the frequencies of the series that are regular on
    their first dates and the one inferred with gaps on the longest of the
    other series that gives one (or, when none does, on the dates of every
    series), ranked by the number of dates of their series (the finest one
    on a tie, so the order of the series does not matter). The first
    candidate that every series fits is the frequency of the data (see
    `_check_long_frequency`); the frequency of a series off its grid is
    also tried (its own, or the one inferred with gaps on the longest such
    series), so daily series next to business-day ones are daily whatever
    their order and gaps, up to `_MAX_CANDIDATES` candidates. When no
    candidate fits, the error that blames the
    fewest dates is returned: the generated script puts every series on one
    frequency, so a series of another frequency was resampled to it (with
    only the warning of skforecast that the series is incomplete), and
    timestamps off its grid were dropped.
    """
    if not series_dates:
        return None, 0, None
    all_dates = np.concatenate(list(series_dates.values()))
    own = _own_frequencies(series_dates)
    weights: dict[str, int] = {}
    for name, frequency in own.items():
        weights[frequency] = weights.get(frequency, 0) + len(series_dates[name])
    # Longest first; on a tie, by their dates, so the order of the rows does
    # not decide.
    with_gaps = sorted(
        (name for name in series_dates if name not in own),
        key=lambda name: (
            -len(series_dates[name]), series_dates[name][0], series_dates[name][-1],
            str(name),
        ),
    )
    for name in with_gaps[:_MAX_SERIES_WITH_GAPS]:
        frequency = infer_frequency(pd.DatetimeIndex(series_dates[name]))
        if frequency is not None:
            weights[frequency] = weights.get(frequency, 0) + len(series_dates[name])
            break
    if not weights:
        union = np.unique(all_dates)
        frequency = infer_frequency(pd.DatetimeIndex(union))
        if frequency is None:
            return None, 0, None
        weights[frequency] = len(union)

    candidates = sorted(
        weights, key=lambda freq: (-weights[freq], -_periods_per_year(freq), freq)
    )
    error = None
    tried = set()
    while candidates and len(tried) < _MAX_CANDIDATES:
        frequency = candidates.pop(0)
        if frequency in tried:
            continue
        tried.add(frequency)
        n_missing, message, others, n_blamed, differ = _check_long_frequency(
            series_dates = series_dates,
            all_dates    = all_dates,
            own          = own,
            frequency    = frequency,
        )
        if message is None:
            return frequency, n_missing, None
        if error is None or n_blamed < error[0]:
            error = (n_blamed, message, differ)
        candidates += [other for other in others if other not in tried]

    return None, 0, error


def _infer_aware_long_frequency(
    local_dates: dict[object, np.ndarray],
    utc_dates: dict[object, np.ndarray] | None,
) -> tuple[str | None, int]:
    """
    Infer the frequency of long-format data with time zone aware dates.

    pandas keeps the local time of a daily or coarser grid across a daylight
    saving time change, but puts a step shorter than a day, or a step given
    in hours, in UTC. So the dates are read in both: in UTC when that gives
    a step shorter than a day (raising a series of another frequency found
    in local time, such as a daily series among hourly ones, whose steps of
    23 to 25 hours hide it in UTC), and in local time otherwise. A step
    shorter than a day found only in local time (dates at the same local
    hours) raises the error of the UTC reading, as `asfreq` would drop rows
    across the change, or gives no frequency when that reading found none
    without an error; days or weeks found only in UTC (dates at the same UTC
    hour) are given in hours (`'24h'`, `'168h'`). When neither reading
    fits, the error that blames the fewest dates is raised.

    Parameters
    ----------
    local_dates : dict
        Dates of each series in local time (see `_long_series_dates`).
    utc_dates : dict, None
        Dates of each series in UTC.

    Returns
    -------
    frequency : str, None
        Frequency of the data, or None when it cannot be inferred.
    n_missing_timestamps : int
        Number of missing timestamps, summed over the series.
    """
    utc_note = (
        " The timestamps are in UTC: pandas puts a step shorter than a day on "
        "a grid in UTC, so dates at the same local hours change step across a "
        "daylight saving time change."
    )
    utc_frequency, utc_missing, utc_error = (
        _search_long_frequency(utc_dates) if utc_dates is not None
        else (None, 0, None)
    )
    local_frequency, local_missing, local_error = _search_long_frequency(
        local_dates
    )
    if _finer_than_a_day(utc_frequency):
        if local_error is not None and local_error[2]:
            raise InvalidInputError(local_error[1], field="data")
        return utc_frequency, utc_missing
    if local_frequency is not None:
        if not _finer_than_a_day(local_frequency):
            return local_frequency, local_missing
        if utc_error is not None:
            raise InvalidInputError(utc_error[1] + utc_note, field="data")
        return None, 0
    hours = _in_hours(utc_frequency)
    if hours is not None:
        return hours, utc_missing
    # The timestamps of a message of the UTC reading are in UTC.
    errors = [
        (error[0], index, error[1] + ("" if error[2] else note))
        for index, (error, note) in enumerate(
            [(local_error, ""), (utc_error, " The timestamps are in UTC.")]
        )
        if error is not None
    ]
    if errors:
        raise InvalidInputError(min(errors)[2], field="data")

    return None, 0


def _frequencies_differ(
    frequency: str,
    reference: object,
    other_frequency: str,
    other: object,
) -> str:
    """
    Return the message for series of long-format data of different
    frequencies.
    """

    return (
        f"The series do not share one frequency: {frequency!r} (series "
        f"{str(reference)!r}), {other_frequency!r} (series {str(other)!r}). "
        f"Every series of long-format data must have the same frequency; "
        f"forecast the series of each frequency separately."
    )


def _parse_text_date_column(
    data: pd.DataFrame,
    date_col: str | None,
    date_format: str | None = None,
    dayfirst: bool | None = None,
    notes: list[str] | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """
    Return `data` with its text date column parsed as the generated script
    parses it, or `data` itself when the dates are not text.

    Text dates here come from a DataFrame (those of a CSV file were read
    already): day-first dates are read day first, and dates whose day and
    month read in both orders are read in the order of `date_format` or
    `dayfirst`, or else in the only one in which they have a regular
    frequency, and raise when neither or both have one (see
    `_day_month_order`). Whole numbers that are all dates of eight digits
    are read with `'%Y%m%d'`.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    date_col : str, None
        Resolved date column name.
    date_format : str, default None
        Format the dates of a CSV file were read with, or recorded by a
        profile of the data.
    dayfirst : bool, default None
        Order of the day and the month of the text dates given by the
        caller: True for day first, False for month first.
    notes : list of str, default None
        List the note of an order told from the regularity of the dates is
        appended to.

    Returns
    -------
    data : pandas DataFrame
        A copy with the parsed dates, or the same object.
    date_format : str, None
        Format the generated script reads the dates with
        (`DataProfile.date_format`): the one of the text, `'%Y%m%d'` for
        whole numbers, `date_format` for dates already parsed, and None
        without a date column.
    """
    if date_col is None or date_col not in data.columns:
        return data, None
    values = data[date_col]
    if is_text(values):
        parsed, issue, found = _read_date_column(
                                   name        = date_col,
                                   values      = values,
                                   named       = True,
                                   dayfirst    = dayfirst,
                                   date_format = date_format,
                                   source      = "frame",
                                   notes       = notes,
                               )
        if issue is not None:
            raise date_issue_error(issue)
        if parsed is None:
            # Raises as the generated script does.
            parsed = parse_text_dates(values)
        data = data.copy()
        data[date_col] = parsed
        return data, found
    compact = _compact_dates(values)
    if compact is not None:
        data = data.copy()
        data[date_col] = compact
        return data, COMPACT_DATE_FORMAT

    return data, date_format


def _warn_dayfirst_not_applied(data: pd.DataFrame, date_col: str | None) -> None:
    """
    Warn that `dayfirst`, given for a DataFrame, does not apply: its dates
    are not text (a datetime column or index, whole numbers of eight
    digits), or it has none. Text dates are read in its order.
    """
    if date_col is not None and is_text(data[date_col]):
        return
    if date_col is not None:
        where = f"column {date_col!r}"
    elif isinstance(data.index, pd.DatetimeIndex):
        where = "the index"
    else:
        where = None
    reason = (
        f"the dates of {where} are not text, so the order of their day and "
        f"month is already set"
        if where is not None else
        "the data has no dates written as text (a text column of dates is "
        "read when `date_column` names it)"
    )
    _warnings.warn(
        f"`dayfirst` does not apply and is ignored: {reason}. It orders the day "
        f"and the month of dates written as text, such as '01/02/2020'.",
        IgnoredArgumentWarning,
        stacklevel=_caller_stacklevel(),
    )


def frame_date_format(
    data: object,
    date_column: str | None,
    date_format: str | None = None,
) -> str | None:
    """
    Return the format the generated script reads the dates of data passed
    in memory with, as `DataProfile.date_format` records it.

    The script runs on the DataFrame as it was passed, so the format is the
    one of its own dates: that of its text (see `_parse_text_date_column`),
    `'%Y%m%d'` for whole numbers of eight digits, and None for dates already
    parsed, whatever the profile passed with them says.

    Parameters
    ----------
    data : object
        Data as the caller passed it.
    date_column : str, None
        Date column of the profile, or the MultiIndex level of the dates.
    date_format : str, default None
        Format recorded by the profile, which decides the order of text
        dates whose day and month read in both.

    Returns
    -------
    date_format : str, None
        Format of the dates, or None when the script reads them without one.
    """
    if not isinstance(data, pd.DataFrame) or date_column is None:
        return None
    if date_column in data.columns:
        values = data[date_column]
    elif isinstance(data.index, pd.MultiIndex) and date_column in data.index.names:
        values = pd.Series(data.index.get_level_values(date_column))
    else:
        return None
    if isinstance(values, pd.DataFrame):
        # A repeated column name: left to the checks that report it.
        return None

    if not is_text(values) and _compact_dates(values) is None:
        return None
    frame = pd.DataFrame({date_column: values.reset_index(drop=True)})

    return _parse_text_date_column(frame, date_column, date_format)[1]


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
    DataFrame's index or a detected date column. For long format, it is
    the first series with a series id, so stacked dates from several series
    do not break the checks that read one index (the frequency and the gaps
    of every series are read by `_infer_long_frequency`).

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
        # Extract dates from the first series only. Rows without a series id
        # are left out, as the generated script leaves them out.
        if series_id_column in data.columns:
            ids = data[series_id_column].dropna()
            if ids.empty:
                return None
            sample = data[data[series_id_column] == ids.iloc[0]]
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


def _time_zone_name(datetime_index: pd.DatetimeIndex | None) -> str | None:
    """
    Return the name of the time zone of the dates, or None when they have
    none or pandas cannot rebuild the zone from its name (the positions of
    a strategy are then counted without it, as for dates without zone).
    """
    time_zone = getattr(datetime_index, "tz", None)
    if time_zone is None:
        return None
    name = str(time_zone)
    try:
        pd.date_range("2000-01-01", periods=1, freq="D", tz=name)
    except Exception:
        return None

    return name


def _resolve_start_date(
    data: pd.DataFrame,
    datetime_index: pd.DatetimeIndex,
    data_format: str,
    series_id_column: str | None,
    date_col: str | None,
) -> pd.Timestamp:
    """
    Determine `DataProfile.start_date`.

    For single and wide formats, returns the first element of the
    datetime index. For long format with multiple series that may have
    different start dates, returns the **latest** first date across all
    series, the first date every series has reached. Positions are
    converted to dates from `DataProfile.span_start_date` instead, which
    in long format is the earliest first date when the span can be rebuilt
    from it.

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


def _select_exog_columns(
    detected: list[str],
    selected: list[str] | tuple[str, ...] | None,
    data: pd.DataFrame,
    target: str | list[str],
    date_column: str | None,
    series_id_column: str | None,
) -> tuple[list[str], list[str]]:
    """
    Keep the exogenous columns the caller chose.

    Parameters
    ----------
    detected : list of str
        Exogenous columns detected in the data (`detect_exog_columns`).
    selected : list of str, tuple of str, None
        Columns the caller chose, or None for every detected column.
    data : pandas DataFrame
        Input dataset, to tell a column that does not exist from one that
        is the target, the date or the series id.
    target : str, list
        Name(s) of the target column(s).
    date_column : str, None
        Resolved date column name.
    series_id_column : str, None
        Series identifier column.

    Returns
    -------
    exog_columns : list of str
        Chosen columns, in the order of the data.
    unused_columns : list of str
        Detected columns that were not chosen, in the order of the data.

    Raises
    ------
    TypeError
        When `selected` is not a list of str.
    ValueError
        When `selected` repeats a column, names a column that is not in the
        data, or names the target, the date or the series id column.
    """
    if selected is None:
        return detected, []
    if not isinstance(selected, (list, tuple)) or not all(
        isinstance(column, str) for column in selected
    ):
        raise InvalidInputTypeError(
            f"`exog_columns` must be a list of column names, got "
            f"{selected!r}.",
            field = "exog_columns",
        )
    repeated = sorted({c for c in selected if list(selected).count(c) > 1})
    if repeated:
        raise InvalidInputError(
            f"`exog_columns` names a column more than once: {repeated}.",
            field = "exog_columns",
        )
    targets = target if isinstance(target, list) else [target]
    reserved = [
        column for column in selected
        if column in targets or column in (date_column, series_id_column)
    ]
    if reserved:
        raise InvalidInputError(
            f"`exog_columns` names the target, the date or the series id "
            f"column: {reserved}. An exogenous variable is any other column "
            f"of the data.",
            field = "exog_columns",
        )
    missing = [column for column in selected if column not in detected]
    if missing:
        shown = missing[:5]
        more = f" (first 5 of {len(missing)})" if len(missing) > 5 else ""
        raise InvalidInputError(
            f"`exog_columns` names columns that are not in the data: "
            f"{shown}{more}. Columns of the data: "
            f"{[str(column) for column in data.columns[:20]]}"
            f"{' (first 20)' if len(data.columns) > 20 else ''}.",
            field = "exog_columns",
        )

    chosen = set(selected)
    exog_columns = [column for column in detected if column in chosen]
    # As text, as `_refresh_profile` records them: a column name that is not
    # a string (an integer) can be left out too.
    unused_columns = [str(column) for column in detected if column not in chosen]

    return exog_columns, unused_columns


def unused_columns_note(unused_columns: list[str]) -> str:
    """
    Note of `DataProfile.warnings` that names the columns left out.

    Parameters
    ----------
    unused_columns : list of str
        Columns of the data that the profile does not use.

    Returns
    -------
    note : str
        Note naming the first 5 columns.
    """
    shown = [str(column) for column in unused_columns[:5]]
    more = (
        f" (first 5 of {len(unused_columns)})" if len(unused_columns) > 5 else ""
    )

    return (
        f"Columns of the data that the profile leaves out are not used: "
        f"{shown}{more}."
    )


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


# Share of the values of a text exogenous column (missing values aside) that
# must read as numbers, once a final '%' and the cells made only of dashes
# are set aside, for the profile to warn that it holds numbers written as
# text. True categories ('A', 'B', codes such as 'P-001' or '007') read as
# no numbers at all; 90 % leaves room for an odd marker of missing values
# ('?', 'n.d.') among numbers, which fails the backtest the same way.
_NUMBERS_AS_TEXT_SHARE = 0.9

# A number as text: no thousands separators, no '1_000' nor 'inf' (which
# `float` reads), and no leading zero ('007', '01'), which marks a code.
_NUMBER_TEXT = re.compile(r"[+-]?(?!0\d)(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_DASHES_TEXT = re.compile(r"-*")


def detect_numbers_as_text(
    data: pd.DataFrame,
    exog_columns: list[str],
    decimal: str = ".",
) -> dict[str, tuple[int, int, list, int]]:
    """
    Find text exogenous columns that hold numbers written as text, such as
    percentages ('12%') or a '-' for a missing value.

    Such a column is used as a categorical variable, with one level per
    distinct value: a numeric regressor becomes a nominal one, and with
    levels that the training rows of a fold do not hold the backtest fails
    with missing values. Nothing is converted; the profile warns (see
    `generate_warnings`).

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    exog_columns : list
        Names of exogenous columns to check. Only those of dtype `object`
        are read: a `category` dtype was chosen on purpose.
    decimal : str, default '.'
        Decimal mark of the CSV file, which the values written as text keep.

    Returns
    -------
    numbers_as_text : dict
        Mapping of each column that holds numbers written as text to the
        number of its values that read as numbers (cells of dashes or
        spaces included), the number of its values (missing values aside),
        what makes it text (among `"numbers with a final '%'"`,
        `"cells of '-'"`, `"blank cells"` and `"numbers with spaces"`; none
        for numbers stored as text) and its number of levels. No value of
        the data is quoted: the warnings of the profile reach the LLM.

    Notes
    -----
    A value reads as a number when, once its spaces and a final `'%'` are
    removed, it is a number without thousands separators nor a leading zero
    (`'007'` is a code), or when it is made only of dashes or spaces (a
    marker of a missing value). The column is reported when at least one
    value is a number and at least `_NUMBERS_AS_TEXT_SHARE` (90 %) of its
    values read as numbers.
    """
    found = {}
    for col in exog_columns:
        values = data[col]
        if not pd.api.types.is_object_dtype(values):
            continue
        counts = values.dropna().value_counts(sort=False)
        if counts.empty:
            continue
        raw = [str(value) for value in counts.index]
        texts = [re.sub(r"\s+", "", text) for text in raw]
        bodies = [text.removesuffix("%").replace(decimal, ".") for text in texts]
        numbers = np.array([bool(_NUMBER_TEXT.fullmatch(body)) for body in bodies])
        dashes = np.array([bool(_DASHES_TEXT.fullmatch(text)) for text in texts])
        n_values = int(counts.sum())
        n_read = int(counts.to_numpy()[numbers | dashes].sum())
        if not numbers.any() or n_read < _NUMBERS_AS_TEXT_SHARE * n_values:
            continue
        # What makes the column text is described, not quoted: the values
        # of the data do not reach the LLM (the warnings of the profile are
        # part of its context).
        kinds = [
            kind
            for kind, present in (
                (
                    "numbers with a final '%'",
                    any(n and t.endswith("%") for n, t in zip(numbers, texts)),
                ),
                ("cells of '-'", any(d and t for d, t in zip(dashes, texts))),
                ("blank cells", any(not t for t in texts)),
                (
                    "numbers with spaces",
                    any(n and r != t for n, r, t in zip(numbers, raw, texts)),
                ),
            )
            if present
        ]
        found[col] = (n_read, n_values, kinds, len(counts))

    return found


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
    series_ending_early: tuple[str, dict[str, str]] | None = None,
    numbers_as_text: dict[str, tuple[int, int, list, int]] | None = None,
    gap_weekdays: list[int] | None = None,
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
        Whether the data is in long format, to word the note on sorting and
        the end of the note on series ending early (what the forecasters do
        with those series differs between long and wide format).
    series_ending_early : tuple, default None
        Last date with a value of multi-series data (long or wide format) and
        the series whose last value comes before it, mapped to the date of
        that value (see `_series_ending_early` and
        `_wide_series_ending_early`).
    numbers_as_text : dict, default None
        Text exogenous columns that hold numbers written as text (see
        `detect_numbers_as_text`).
    gap_weekdays : list of int, default None
        Days of the week (0 for Monday) that every missing timestamp falls
        on, when the data (each series, for long format) has no date on
        them (see `regular_gap_weekdays`). The note on missing timestamps
        then names them, says that a forecast predicts them too, and that
        a business closed on them can fill them with 0, after asking the
        user: nothing is filled in.

    Returns
    -------
    warnings : list
        List of warning messages.

    Notes
    -----
    Missing values of the exogenous columns are named from the first one:
    the rate above 20 % alone let a few of them through, and an estimator
    that does not accept them failed when the script ran.
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

    if n_missing_timestamps > 0 and gap_weekdays:
        days = weekday_names(gap_weekdays)
        owners = (
            "the series that miss them never have a date" if long_format
            else "the data never has a date"
        )
        warnings.append(
            f"Missing timestamps: {n_missing_timestamps} timestamps of "
            f"frequency '{frequency}' are missing from the date range, all "
            f"of them on {days}, when {owners}. asfreq() inserts them as "
            f"rows with missing values, and a forecast predicts {days} too. "
            f"If the business is closed on {days}, they can be filled with 0 "
            f"in the data, after asking the user."
        )
    elif n_missing_timestamps > 0:
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

    if series_ending_early:
        last_date, early = series_ending_early
        shown = ", ".join(f"{name!r} ({end})" for name, end in list(early.items())[:5])
        if len(early) > 5:
            shown += f" and {len(early) - 5} more"
        verb = "ends" if len(early) == 1 else "end"
        # In long format a foundation model reads each series up to its last
        # row; in wide format the other forecasters read every series up to
        # the last date, so its last values are missing values for them.
        others = (
            "ForecasterFoundation predicts each one after its own last row, "
            "rows without a value included"
            if long_format else
            "the other forecasters read their last values as missing values, "
            "which not every estimator or foundation model can use"
        )
        warnings.append(
            f"Series ending early: {len(early)} series {verb} before the last "
            f"date with a value ({last_date}): {shown}. "
            f"ForecasterRecursiveMultiSeries does not predict them, and "
            f"{others}."
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

    if missing_exog:
        shown = ", ".join(
            f"{name!r}: {count}" for name, count in list(missing_exog.items())[:5]
        )
        if len(missing_exog) > 5:
            shown += f" (first 5 of {len(missing_exog)})"
        warnings.append(
            f"Missing values in exogenous columns: {shown}. An estimator that "
            f"does not accept missing values fails when it reads them."
        )

    for column, (n_read, n_values, kinds, n_levels) in (numbers_as_text or {}).items():
        share = (
            "all of its values" if n_read == n_values
            else f"{n_read} of its {n_values} values"
        )
        kinds = list(kinds) or ["numbers stored as text"]
        if n_read < n_values:
            other = n_values - n_read
            kinds.append(f"{other} value{'s' if other != 1 else ''} of other text")
        held = kinds[0] if len(kinds) == 1 else (
            f"{', '.join(kinds[:-1])} and {kinds[-1]}"
        )
        warnings.append(
            f"Numbers written as text in exogenous column {column!r}: {share} "
            f"are numbers, once a final '%' and spaces are removed, or markers "
            f"of missing values (it holds {held}), so it is used as a "
            f"categorical variable with {n_levels} levels. If it is a numeric "
            f"variable, write its values as plain numbers in the data, without "
            f"'%' and with empty cells instead of '-' for missing values (ask "
            f"the user before changing their file); if it holds categories, "
            f"nothing needs to change."
        )

    return warnings


# Most column names quoted in a message, so a typo in data with thousands of
# columns does not give a message of thousands of names.
_MAX_LISTED_COLUMNS = 20

# Most values of the data quoted in a message.
_MAX_QUOTED_VALUES = 5

# Remedy of a DataFrame whose series are columns named with numbers.
_TEXT_COLUMNS_HINT = (
    "Rename the columns of the DataFrame to text, for example with "
    "`data.columns = data.columns.astype(str)`, and pass their names as "
    "text in `target`."
)


def csv_read_kwargs(
    sep: str,
    decimal: str,
    thousands: str | None = None,
    series_id_column: str | None = None,
    date_column: str | None = None,
    encoding: str = DEFAULT_CSV_ENCODING,
) -> dict[str, object]:
    """
    Return the arguments `pandas.read_csv` needs to read a CSV file written
    with a separator, a decimal mark and a thousands separator, as the
    generated script passes them: none for `','`, `'.'` and no thousands
    separator, `sep` and `decimal` otherwise, and `thousands` when there is
    one; `encoding` only when it is not UTF-8. The column of series ids is
    read as text (`dtype`), so `'001'` keeps its zeros and the thousands
    separator does not touch it, and so is the column of the dates when
    there is a thousands separator: with `'.'`, pandas would read
    `'15.01.2020'` as the number 15012020.

    Parameters
    ----------
    sep : str
        Separator of the fields.
    decimal : str
        Decimal mark.
    thousands : str, default None
        Thousands separator, or None for none.
    series_id_column : str, default None
        Column of the series ids of long-format data, or None for none.
    date_column : str, default None
        Column of the dates, or None for none.
    encoding : str, default 'utf-8'
        Encoding of the file: `'utf-8'` or `'cp1252'`.

    Returns
    -------
    kwargs : dict
        Empty, or `sep` and `decimal`, with `thousands` when it is given,
        `encoding` when it is `'cp1252'`, and `dtype` when
        `series_id_column` is given, or `date_column` with `thousands`.
    """
    kwargs: dict[str, object] = {}
    if (
        sep != DEFAULT_CSV_SEP
        or decimal != DEFAULT_CSV_DECIMAL
        or thousands is not None
    ):
        kwargs = {"sep": sep, "decimal": decimal}
        if thousands is not None:
            kwargs["thousands"] = thousands
    if encoding != DEFAULT_CSV_ENCODING:
        kwargs["encoding"] = encoding
    text = [series_id_column]
    if thousands is not None:
        text.append(date_column)
    text = [column for column in dict.fromkeys(text) if column is not None]
    if text:
        kwargs["dtype"] = {column: str for column in text}
    return kwargs


def frame_date_column(
    data: pd.DataFrame,
    series_id_column: str | None = None,
) -> str | None:
    """
    Return the first column of a CSV file read as text, but the series ids,
    whose values are all dates written with numbers (`'15.01.2020'`), as
    `sample_date_column` finds it in the first lines; None when there is
    none.

    Parameters
    ----------
    data : pandas DataFrame
        Content of the file.
    series_id_column : str, default None
        Column of the series ids, never the dates.

    Returns
    -------
    date_column : str, None
        Name of the column, or None.
    """
    for column in data.columns:
        values = data[column]
        if column == series_id_column or not is_text(values):
            continue
        values = values.dropna().astype(str).str.strip()
        if len(values) and values.str.fullmatch(NUMERIC_DATE.pattern).all():
            return column
    return None


def without_series_ids(
    data: pd.DataFrame,
    series_id_column: str | None,
    date_column: str | None = None,
) -> pd.DataFrame:
    """
    Return the columns of a CSV file read with `csv_read_kwargs` whose
    numbers tell how it is written: every column but the series ids, which
    are read as text and never as numbers, and but the dates, which are not
    numbers either (`'15.01.2020'`).

    Parameters
    ----------
    data : pandas DataFrame
        Content of the file.
    series_id_column : str, None
        Column of the series ids. None, or a column that `data` does not
        hold, keeps every column.
    date_column : str, default None
        Column of the dates, left out in the same way.

    Returns
    -------
    data : pandas DataFrame
        `data`, or a copy without the column of series ids and of dates.
    """
    dropped = [
        column for column in (series_id_column, date_column)
        if column is not None and column in data.columns
    ]
    if not dropped:
        return data
    return data.drop(columns=list(dict.fromkeys(dropped)))


def series_ids_as_text(
    data: pd.DataFrame,
    series_id_column: str | None,
) -> pd.DataFrame:
    """
    Return long-format data with its series ids as text, as the generated
    script turns them (`map(str, na_action='ignore')`).

    skforecast names the series with text and looks them up with the ids of
    the data, so integer ids (`1`, `10`) fail inside it (skforecast issue
    #1357); a CSV file is read with its ids as text, and data passed in
    memory gets them here. A missing id stays missing: its rows are left
    out, as before.

    Parameters
    ----------
    data : pandas DataFrame
        Long-format data, or any other data, returned as it is.
    series_id_column : str, None
        Column of the series ids. None, or a column that `data` does not
        hold, returns `data` as it is.

    Returns
    -------
    data : pandas DataFrame
        `data`, or a copy with the series ids as text.
    """
    if series_id_column is None or series_id_column not in data.columns:
        return data
    ids = data[series_id_column]
    if isinstance(ids, pd.DataFrame):
        # A repeated column name: left to the checks that report it.
        return data
    if pd.api.types.infer_dtype(ids, skipna=True) in ("string", "empty"):
        return data
    data = data.copy()
    data[series_id_column] = ids.map(str, na_action="ignore")
    return data


def decimal_after_sample(
    data: pd.DataFrame,
    source: str,
    field: str,
    sep: str = ";",
) -> str:
    """
    Tell the decimal mark of a CSV file read with `'.'` and another
    separator than `','`, from every value and not only from its first
    lines.

    The decimal mark is detected from the start of the file. A column
    that holds whole numbers there and `'2,5'` further down is read as
    text, and would be taken for a categorical variable without a word.
    The columns read as text are looked up for numbers written with `','`,
    or with `'.'` between thousands in a way that cannot read with `'.'` as
    decimal mark (`'1.705,11'`, `'1.234.567'`): when there are some, the
    file is to be read again with `','` (see `thousands_after_sample` for
    the thousands).

    Parameters
    ----------
    data : pandas DataFrame
        Content of the file, read with `'.'` as decimal mark.
    source : str
        Path or URL of the file, named by the error.
    field : str
        Argument that named the file, reported with the error.
    sep : str, default ';'
        Separator the file was read with.

    Returns
    -------
    decimal : str
        `','` when a column holds numbers written with it, `'.'`
        otherwise.

    Notes
    -----
    As in `detect_csv_dialect`, numbers written with both marks, numbers
    with `'.'` between thousands next to numbers with decimals after a
    `'.'`, or (in a file separated by tabulators) numbers with a `','` that
    all read as thousands too, raise `InvalidInputError` with code
    `'data_unreadable'`.
    """
    with_comma = grouped = None
    only_thousands = True
    for values in _text_values(data):
        # Only the values with a ',' or a '.' are matched: a column of dates
        # or names holds many and none is a number with them.
        has_comma = values.str.contains(",", regex=False)
        dotted = values[values.str.contains(".", regex=False)]
        # '1.705,11' and '1.234.567' do not read with '.' as decimal mark;
        # the first also has ',' as decimal mark, the second has none.
        sure = dotted[
            dotted.str.fullmatch(DOT_THOUSANDS.pattern)
            & ~dotted.str.fullmatch(DECIMAL_NUMBERS["."].pattern)
        ]
        with_mark = values[has_comma]
        found = with_mark[
            with_mark.str.fullmatch(DECIMAL_NUMBERS[","].pattern)
            | with_mark.index.isin(sure.index)
        ]
        if with_comma is None and not found.empty:
            with_comma = found.iloc[0]
        if not found.str.fullmatch(THOUSANDS.pattern).all():
            only_thousands = False
        if grouped is None and not sure.empty:
            grouped = sure.iloc[0]
    if with_comma is None and grouped is None:
        return DEFAULT_CSV_DECIMAL
    for column in data.columns:
        values = data[column]
        if not pd.api.types.is_float_dtype(values):
            continue
        values = values[np.isfinite(values)]
        with_point = values[values % 1 != 0]
        if not with_point.empty:
            point = repr(float(with_point.iloc[0]))
            if with_comma is None:
                raise dotted_values_error(source, field, point, grouped)
            raise decimal_in_both_error(source, field, with_comma, point)
    if with_comma is not None and only_thousands and sep == "\t":
        raise only_thousands_error(source, field, with_comma)

    return ","


def thousands_after_sample(
    data: pd.DataFrame,
    source: str,
    field: str,
) -> str | None:
    """
    Tell whether a CSV file read with `','` as decimal mark and no
    thousands separator has `'.'` between thousands, from every value and
    not only from its first lines.

    With `','` as decimal mark, a number such as `'1.705'` or `'1.705,11'`
    only reads with `'.'` between thousands. pandas leaves its column as
    text, which would be taken for a categorical variable without a word:
    when a column read as text holds one, the file is to be read again with
    `'.'` as thousands separator.

    Parameters
    ----------
    data : pandas DataFrame
        Content of the file, read with `','` as decimal mark and no
        thousands separator.
    source : str
        Path or URL of the file, named by the error.
    field : str
        Argument that named the file, reported with the error.

    Returns
    -------
    thousands : str, None
        `'.'` when a column holds numbers written with it, None otherwise.

    Notes
    -----
    A column read as text that also holds a value with a `'.'` that does
    not separate thousands (`'15.01.2020'`, `'0.5'`), which pandas would
    read as a number without it, raises `InvalidInputError` with code
    `'data_unreadable'`.
    """
    texts = _text_values(data)
    grouped = None
    for values in texts:
        dotted = values[values.str.contains(".", regex=False)]
        found = dotted[dotted.str.fullmatch(DOT_THOUSANDS.pattern)]
        if not found.empty:
            grouped = found.iloc[0]
            break
    if grouped is None:
        return None
    other = _dotted_text(texts)
    if other is not None:
        raise dotted_values_error(source, field, other, grouped)

    return "."


def thousands_beyond_sample(
    path: str | Path,
    data: pd.DataFrame,
    source: str,
    field: str,
    sep: str,
    encoding: str = DEFAULT_CSV_ENCODING,
) -> str | None:
    """
    Tell whether a CSV file read with `'.'` as decimal mark and no
    thousands separator has `'.'` between thousands in the rows after the
    lines its dialect was told from.

    pandas reads `'1.020'` as the number 1.02, so a column of whole numbers
    whose amounts of 1,000 or more only come after those lines (the long
    format of several series, sorted by series) would hold wrong values
    without a word. The columns read as numbers with decimals are read again
    as text and told as `detect_csv_dialect` tells the sample: `'.'`
    separates thousands when a column holds whole numbers of at most three
    digits next to numbers such as `'1.020'`, and nothing does when another
    number has decimals after a `'.'` (`'0.5'`).

    Parameters
    ----------
    path : str, Path
        Path of the CSV file.
    data : pandas DataFrame
        Content of the file, read with `'.'` as decimal mark and no
        thousands separator.
    source : str
        Path of the file, named by the error.
    field : str
        Argument that named the file, reported with the error.
    sep : str
        Separator the file was read with.
    encoding : str, default 'utf-8'
        Encoding the file was read with.

    Returns
    -------
    thousands : str, None
        `'.'` when the file is to be read again with it (and `','` as
        decimal mark), None otherwise.

    Notes
    -----
    Numbers whose only `'.'` is followed by three digits, with nothing that
    settles it, raise `InvalidInputError` with code `'data_unreadable'`, as
    does a file whose `'.'` separates thousands in one column and is the
    decimal mark in another, or appears in values that are not numbers
    (`'15.01.2020'`). A frame whose first column was read as its index (a
    header one field short) is not looked at.
    """
    if not isinstance(data.index, pd.RangeIndex):
        return None
    # The numbers already read tell which columns to read again: '1.020' was
    # read as 1.02, at least 1, below 1,000 and with three decimals at most.
    # A number below 1 or with more decimals only reads with '.' as decimal
    # mark, and so does a column that cannot mix whole numbers of at most
    # three digits with thousands: without such a column nothing changes.
    candidates, others = set(), set()
    mixable, point = False, None
    for column in data.columns:
        values = data[column]
        if not pd.api.types.is_float_dtype(values):
            continue
        values = values[np.isfinite(values)]
        whole = values % 1 == 0
        fraction = values[~whole]
        size = fraction.abs()
        scaled = size * 1000
        grouped_like = (
            (size >= 1) & (size < 1000) & ((scaled - scaled.round()).abs() < 1e-6)
        )
        if point is None and not grouped_like.all():
            point = repr(float(fraction[~grouped_like].iloc[0]))
        if not grouped_like.any():
            others.add(str(column))
            continue
        candidates.add(str(column))
        wholes = values[whole]
        if len(wholes) and (wholes.abs() < 1000).all():
            mixable = True
    if not candidates or (point is not None and not mixable):
        return None

    grouped = mixed = None
    for values in _text_values(_read_text_columns(path, sep, candidates, encoding)):
        dotted = values.str.contains(".", regex=False)
        with_point = values[dotted]
        with_groups = with_point.str.fullmatch(DOT_THOUSANDS.pattern)
        if point is None:
            # One number with '.' as decimal mark is enough: stop at it.
            point = next(
                (
                    value for value in with_point[~with_groups]
                    if DECIMAL_NUMBERS["."].fullmatch(value)
                ),
                None,
            )
        if not with_groups.any():
            continue
        if grouped is None:
            grouped = with_point[with_groups].iloc[0]
        plain = values[~dotted]
        wholes = plain[plain.str.fullmatch(WHOLE_NUMBER.pattern)]
        if (
            mixed is None
            and not wholes.empty
            and wholes.str.fullmatch(SHORT_WHOLE_NUMBER.pattern).all()
        ):
            mixed = with_point[with_groups].iloc[0]
    if grouped is None:
        return None
    if mixed is not None:
        # Every '.' is checked before it is read as thousands: the other
        # columns of numbers may hold '870.0', which pandas would read as
        # 8700.
        other = point or _dotted_text(_text_values(data))
        if other is None and others:
            other_columns = _read_text_columns(path, sep, others, encoding)
            other = _dotted_text(_text_values(other_columns))
        if other is not None:
            raise dotted_values_error(source, field, other, mixed)
        return "."
    if point is not None:
        return None
    raise ambiguous_thousands_error(source, field, grouped)


def _read_text_columns(
    path: str | Path,
    sep: str,
    columns: set[str],
    encoding: str = DEFAULT_CSV_ENCODING,
) -> pd.DataFrame:
    """
    Read some columns of a CSV file as text, to look at how their numbers
    are written.
    """
    return pd.read_csv(
               path,
               sep      = sep,
               dtype    = str,
               usecols  = lambda name: str(name) in columns,
               encoding = encoding,
           )


def _text_values(data: pd.DataFrame) -> list[pd.Series]:
    """
    Return the values of every column read as text, without missing values
    and without the spaces around them.
    """
    return [
        data[column].dropna().astype(str).str.strip()
        for column in data.columns
        if is_text(data[column])
    ]


def _dotted_text(texts: list[pd.Series]) -> str | None:
    """
    Return the first value with a `'.'` that does not separate thousands
    and that pandas would read as a number without it when `'.'` separates
    the thousands ('15.01.2020', '0.5'), or None.
    """
    for values in texts:
        dotted = values[values.str.contains(".", regex=False)]
        other = dotted[
            dotted.str.fullmatch(DOTTED_NUMBER.pattern)
            & ~dotted.str.fullmatch(DOT_THOUSANDS.pattern)
        ]
        if not other.empty:
            return other.iloc[0]
    return None


# Remedy of a CSV file whose rows have more fields than its header, read by
# people and agents alike. The file belongs to whoever gave it, so a copy is
# written only with their consent.
ROW_FIELDS_HINT = (
    "Every row needs as many fields as the header. Write a copy of the file "
    "without the extra fields (or with a name for the first column in the "
    "header) and pass that copy; if the file is not yours, ask its owner "
    "before writing it."
)

# Remedy of a CSV file with a column without name and values.
EMPTY_COLUMN_HINT = (
    "Write a copy of the file without that column (often the separator at "
    "the end of every line) and pass that copy; if the file is not yours, "
    "ask its owner before writing it."
)


def check_csv_fields(
    data: pd.DataFrame,
    source: str,
    field: str = "data",
    index_first: bool = False,
    row_lengths: list[int] | None = None,
) -> None:
    """
    Check that the rows of a CSV file read with `pandas.read_csv` have the
    fields of its header.

    When the first row has more fields than the header, pandas reads the
    first columns as the index and moves every other column: a separator at
    the end of every row empties the last column, and a field too many in
    the first row only fills it with missing values. A separator at the end
    of every line, the header included, gives instead a column without name
    and values (`'Unnamed: 2'`). Both are checked here, as the generated
    script would read the file the same way; rows longer than the header
    further down already make pandas fail.

    Parameters
    ----------
    data : pandas DataFrame
        Content of the file, read without `index_col`.
    source : str
        Path or URL of the file, named by the error.
    field : str, default 'data'
        Argument that named the file, reported with the error.
    index_first : bool, default False
        Whether a header one field short (`to_csv(index_label=False)`) is
        read, with the first field of every row as the index, as the future
        exogenous variables are. It is when every row has one field more
        than the header and the last column is not empty.
    row_lengths : list of int, default None
        Number of fields of every row after the header (see
        `read_row_lengths`), to tell a header one field short from a field
        too many in some rows. If None, only the last column is looked at.

    Returns
    -------
    None

    Notes
    -----
    Both problems raise `InvalidInputError` with code `'data_unreadable'`.
    """
    n_header = len(data.columns)
    if not isinstance(data.index, pd.RangeIndex):
        last_empty = n_header > 0 and bool(data.iloc[:, -1].isna().all())
        header_one_short = (
            index_first
            and data.index.nlevels == 1
            and not last_empty
            and (
                row_lengths is None
                or all(length == n_header + 1 for length in row_lengths)
            )
        )
        if not header_one_short:
            cause = (
                "the rows end with separators that the header does not have"
                if last_empty else
                "a field too many in the first row, or a header without a "
                "name for the first column"
            )
            raise InvalidInputError(
                f"The CSV file '{source}' could not be read: its header has "
                f"{n_header} field{'s' if n_header != 1 else ''} and its first "
                f"row {n_header + data.index.nlevels}, so the first column "
                f"would be read as the row labels and every other column "
                f"would move one place ({cause}).",
                code  = "data_unreadable",
                field = field,
                hint  = ROW_FIELDS_HINT,
            )

    # pandas names a column without a name in the header after its position.
    empty = [
        column for position, column in enumerate(data.columns)
        if column == f"Unnamed: {position}" and data[column].isna().all()
    ]
    if empty:
        names = ", ".join(repr(column) for column in empty)
        plural = len(empty) > 1
        raise InvalidInputError(
            f"The CSV file '{source}' could not be read: column"
            f"{'s' if plural else ''} {names} {'have' if plural else 'has'} "
            f"no name in the header and no values (often a separator at the "
            f"end of every line, the header included).",
            code  = "data_unreadable",
            field = field,
            hint  = EMPTY_COLUMN_HINT,
        )


def read_csv_with_dialect(
    path: str | Path,
    field: str = "data",
    sep: str | None = None,
    decimal: str | None = None,
    thousands: str | None = None,
    index_first: bool = False,
    series_id_column: str | None = None,
    date_column: str | None = None,
) -> tuple[pd.DataFrame, str, str, str | None, str]:
    """
    Read a CSV file with `pandas.read_csv`, as the generated script reads
    it, and return how it is written.

    The separator (`','`, `';'` or a tabulator), the decimal mark (`'.'`
    or `','`) and the thousands separator (none or `'.'`) are told from the
    first lines of the file unless they are given (see
    `detect_csv_dialect`). A file written with `','` and `'.'` is read with
    the same call as before. A file with another separator whose numbers
    with `','` only come after those lines is read again with `','` as
    decimal mark (see `decimal_after_sample`), and one with `','` as
    decimal mark whose numbers with `'.'` between thousands only come after
    them, or whose decimal mark `','` is given, is read again with `'.'` as
    thousands separator (see `thousands_after_sample`). When those lines do
    not hold the whole file and its decimal mark `'.'` was detected, its
    columns of numbers are read again as text to tell whether `'.'`
    separates thousands after them (see `thousands_beyond_sample`).

    The encoding is told from the first lines too, always: UTF-8, with or
    without a byte order mark, or cp1252 (Windows-1252, the "CSV" that
    Excel saves on Windows) when they are not UTF-8 (see
    `sample_encoding`). A file whose bytes that are not UTF-8 only come
    after those lines is read again as cp1252.

    Parameters
    ----------
    path : str, Path
        Path of the CSV file.
    field : str, default 'data'
        Argument that named the file, reported with the error.
    sep : str, default None
        Separator of the fields. If None, it is detected.
    decimal : str, default None
        Decimal mark. If None, it is detected.
    thousands : str, default None
        Thousands separator. If None, it is detected, except when `decimal`
        is `'.'`: the file then has none.
    index_first : bool, default False
        Whether a header one field short (`to_csv(index_label=False)`) is
        read, with the first field of every row as the index (see
        `check_csv_fields`).
    series_id_column : str, default None
        Column of the series ids of long-format data, read as text
        (`'001'` keeps its zeros), as the generated script reads it. Its
        values are not numbers, so they do not tell how the file is
        written.
    date_column : str, default None
        Column of the dates, when the caller gives it; otherwise the column
        of dates of the first lines (see `sample_date_column`). Its values
        do not tell how the file is written, and it is read as text with a
        thousands separator, as the generated script reads it.

    Returns
    -------
    data : pandas DataFrame
        Content of the file.
    sep : str
        Separator the file was read with.
    decimal : str
        Decimal mark the file was read with.
    thousands : str, None
        Thousands separator the file was read with, or None for none.
    encoding : str
        Encoding the file was read with: `'utf-8'` or `'cp1252'`.

    Notes
    -----
    With a thousands separator, the column of the dates is read as text,
    as the generated script reads it: pandas would read `'15.01.2020'` as
    the number 15012020.

    A file in UTF-16 or UTF-32, with null bytes, or with a byte that is not
    UTF-8 and that cp1252 does not define raises `InvalidInputError` with
    code `'data_unreadable'` and a hint that asks for a copy saved as UTF-8
    (see `sample_encoding`). Whether a file that is not UTF-8 is cp1252
    cannot be checked: the caller says so in a warning (see `cp1252_note`).
    A file that pandas cannot read as a CSV (empty, binary, with rows of
    more fields than the others, or compressed and damaged) raises
    `InvalidInputError` with code `'data_unreadable'`, still a `ValueError`
    as the errors of pandas were, and so do a file whose separator,
    decimal mark or thousands separator cannot be told, a file whose first
    row has more fields than its header and a file with a column without
    name and values (see `check_csv_fields`).
    """
    check_csv_dialect(sep, decimal, thousands)
    decimal_given = decimal is not None
    unchecked = False
    whole_sample = False
    dates = date_column
    # Always sampled: the encoding is told from the first lines whatever
    # the caller gives.
    sample = read_sample(path, field=field)
    encoding = DEFAULT_CSV_ENCODING if sample is None else sample.encoding
    # A thousands separator given is checked against the first lines too:
    # pandas drops every '.' of a value such as '0.5'.
    if sep is None or decimal is None or thousands is not None:
        if sample is None:
            # Left for pandas to report, or read as before. The defaults are
            # checked once pandas reads the file, so a file it cannot read
            # is reported as such and not as a dialect that does not fit.
            unchecked = True
            sep = DEFAULT_CSV_SEP if sep is None else sep
            decimal = DEFAULT_CSV_DECIMAL if decimal is None else decimal
            decimal = "," if thousands is not None else decimal
        else:
            sep, decimal, thousands = detect_csv_dialect(
                                          sample           = sample.text,
                                          source           = str(path),
                                          field            = field,
                                          sep              = sep,
                                          decimal          = decimal,
                                          thousands        = thousands,
                                          series_id_column = series_id_column,
                                          date_column      = date_column,
                                      )
            check_csv_dialect(sep, decimal, thousands)
            whole_sample = sample_holds_file(path)
            dates = sample_date_column(
                        sample.text, sep, series_id_column, date_column
                    )

    def read(sep: str, decimal: str, thousands: str | None = None) -> pd.DataFrame:
        nonlocal encoding
        try:
            return pd.read_csv(
                       path,
                       **csv_read_kwargs(
                           sep, decimal, thousands, series_id_column, dates, encoding
                       ),
                   )
        except UnicodeDecodeError:
            # A file whose first lines were not sampled is read as before.
            if sample is None or encoding != DEFAULT_CSV_ENCODING:
                raise
        # Bytes that are not UTF-8 after the first lines: cp1252, whose
        # undefined bytes pandas reports.
        encoding = CP1252
        return pd.read_csv(
                   path,
                   **csv_read_kwargs(
                       sep, decimal, thousands, series_id_column, dates, encoding
                   ),
               )

    try:
        data = read(sep, decimal, thousands)
        if unchecked:
            check_csv_dialect(sep, decimal, thousands)
        # Checked before the decimal mark: a column moved one place would
        # be looked up for numbers that are not its own.
        row_lengths = None
        if index_first and not isinstance(data.index, pd.RangeIndex):
            row_lengths = read_row_lengths(path, sep, encoding)
        check_csv_fields(
            data        = data,
            source      = str(path),
            field       = field,
            index_first = index_first,
            row_lengths = row_lengths,
        )
        if (
            not decimal_given
            and sep != DEFAULT_CSV_SEP
            and decimal == DEFAULT_CSV_DECIMAL
            and decimal_after_sample(
                    without_series_ids(data, series_id_column, dates),
                    str(path),
                    field,
                    sep,
                ) != decimal
        ):
            # Numbers with ',' beyond the lines the dialect was told from.
            decimal = ","
            data = read(sep, decimal)
        if thousands is None and decimal == "," and dates is None:
            # Without the first lines (`sep` and `decimal` given), the dates
            # are found in the file read.
            dates = frame_date_column(data, series_id_column)
        if (
            thousands is None
            and decimal == ","
            and thousands_after_sample(
                    without_series_ids(data, series_id_column, dates),
                    str(path),
                    field,
                ) is not None
        ):
            # '1.705' beyond those lines, or with ',' given as decimal mark.
            thousands = "."
            data = read(sep, decimal, thousands)
        beyond = (
            not decimal_given
            and not whole_sample
            and thousands is None
            and sep != DEFAULT_CSV_SEP
            and decimal == DEFAULT_CSV_DECIMAL
        )
        if beyond and thousands_beyond_sample(
            path,
            without_series_ids(data, series_id_column, dates),
            str(path),
            field,
            sep,
            encoding,
        ):
            # '870' in the sample and '1.020' after it, read as 1.02.
            decimal, thousands = ",", "."
            data = read(sep, decimal, thousands)
    except UnicodeDecodeError as exc:
        if encoding == CP1252:
            byte = exc.object[exc.start:exc.start + 1]
            raise undefined_byte_error(str(path), field, byte) from exc
        raise _unreadable_error(path, field, exc) from exc
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        *DECOMPRESSION_ERRORS,
    ) as exc:
        raise _unreadable_error(path, field, exc) from exc

    return data, sep, decimal, thousands, encoding


def _unreadable_error(
    path: str | Path,
    field: str,
    exc: Exception,
) -> InvalidInputError:
    """
    Return the error of a CSV file that pandas cannot read, with the first
    line of the reason pandas gives.
    """
    reason = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    return InvalidInputError(
        f"The CSV file '{path}' could not be read: {reason}",
        code  = "data_unreadable",
        field = field,
        hint  = (
            "Pass a text file in UTF-8 separated by ',', ';' or "
            "tabulators, with a header row and the same number of "
            "fields in every row."
        ),
    )


def read_csv_file(
    path: str | Path,
    field: str = "data",
    sep: str | None = None,
    decimal: str | None = None,
    thousands: str | None = None,
) -> pd.DataFrame:
    """
    Read a CSV file with `pandas.read_csv`, as the generated script reads it.

    Parameters
    ----------
    path : str, Path
        Path of the CSV file.
    field : str, default 'data'
        Argument that named the file, reported with the error.
    sep : str, default None
        Separator of the fields: `','`, `';'` or a tabulator. If None, it
        is detected from the first lines of the file.
    decimal : str, default None
        Decimal mark: `'.'` or `','`. If None, it is detected.
    thousands : str, default None
        Thousands separator: `'.'`, with `','` as decimal mark. If None, it
        is detected.

    Returns
    -------
    data : pandas DataFrame
        Content of the file.

    Notes
    -----
    See `read_csv_with_dialect` for the errors.
    """
    return read_csv_with_dialect(
               path      = path,
               field     = field,
               sep       = sep,
               decimal   = decimal,
               thousands = thousands,
           )[0]


def _listed_columns(columns: list) -> str:
    """Quote at most `_MAX_LISTED_COLUMNS` column names, saying how many."""
    if len(columns) <= _MAX_LISTED_COLUMNS:
        return str(columns)
    return (
        f"{columns[:_MAX_LISTED_COLUMNS]} (first {_MAX_LISTED_COLUMNS} of "
        f"{len(columns)})"
    )


def _validate_series_id_column(
    data: pd.DataFrame,
    target: str | list[str],
    date_column: str | None,
    series_id_column: str | None,
) -> None:
    """
    Validate that `series_id_column` is a column of the data, other than
    the target and the date column.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s).
    date_column : str, None
        Name of the date column, when given.
    series_id_column : str, None
        Name of the series identifier column, when given.
    """
    if series_id_column is None:
        return
    if series_id_column not in data.columns:
        raise InvalidInputError(
            f"series_id_column={series_id_column!r} was not found in the "
            f"data. Available columns: {_listed_columns(list(data.columns))}.",
            field = "series_id_column",
        )
    targets = target if isinstance(target, list) else [target]
    if series_id_column in targets:
        raise InvalidInputError(
            f"series_id_column={series_id_column!r} is also the target: pass "
            f"the column that identifies the series, other than the values "
            f"to forecast.",
            field = "series_id_column",
        )
    if date_column is not None and series_id_column == date_column:
        raise InvalidInputError(
            f"series_id_column={series_id_column!r} is also the date column: "
            f"pass the column that identifies the series, other than the "
            f"dates.",
            field = "series_id_column",
        )


def _validate_target_has_values(
    data: pd.DataFrame,
    target: str | list[str],
) -> None:
    """
    Validate that each target column holds at least one value.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s), already known to exist.
    """
    targets = target if isinstance(target, list) else [target]
    for column in dict.fromkeys(targets):
        values = data[column]
        if isinstance(values, pd.DataFrame):
            # Repeated column names are rejected elsewhere.
            continue
        if not values.notna().any():
            raise InvalidInputError(
                f"Target column {column!r} has no values: every row is "
                f"missing.",
                code  = "insufficient_data",
                field = "target",
            )


# Numbers written in a format that pandas does not read: with a thousands
# separator ('10,025.1', '1.705,11') or with '%' ('12.5%').
_THOUSANDS_NUMBER = re.compile(
    rf"{THOUSANDS.pattern}(?:\.\d+)?|{DOT_THOUSANDS.pattern}"
)
_PERCENT_NUMBER = re.compile(r"[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)\s*%")


def validate_target_numeric(data: pd.DataFrame, target: str | list[str]) -> None:
    """
    Validate that each target column holds numbers.

    A column of text holds numbers when every value converts to one (as
    `pandas.to_numeric` reads it); the forecasters cannot be trained on any
    other text, which failed while the lags were selected with an error
    that did not name the column. Called by `ForecastingAssistant.profile()`;
    `create_data_profile` still describes a categorical target.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s), already known to exist.

    Returns
    -------
    None

    Notes
    -----
    When every value of a column that is not a number is a number written
    with a thousands separator (`'10,025.1'`, `'1.705,11'`) or with `'%'`
    (`'12.5%'`), it raises `DataContentError` for `data`, with a message
    that names the format: the file is at fault, not the target chosen. Any
    other text raises `InvalidInputError` for `target`.
    """
    targets = target if isinstance(target, list) else [target]
    for column in dict.fromkeys(targets):
        values = data[column]
        if isinstance(values, pd.DataFrame) or pd.api.types.is_numeric_dtype(
            values.dtype
        ):
            continue
        objects = values.astype(object)
        converted = pd.to_numeric(objects, errors="coerce")
        not_numbers = objects[objects.notna() & converted.isna()]
        if len(not_numbers):
            shown = [
                _quoted_value(value)
                for value in not_numbers.unique()[:_MAX_QUOTED_VALUES]
            ]
            texts = pd.Series(not_numbers.unique()).astype(str).str.strip()
            with_thousands = texts.str.fullmatch(_THOUSANDS_NUMBER.pattern)
            with_percent = texts.str.fullmatch(_PERCENT_NUMBER.pattern)
            if (with_thousands | with_percent).all():
                written = " or ".join(
                    name for name, found in (
                        ("with a thousands separator", with_thousands.any()),
                        ("with '%'", with_percent.any()),
                    )
                    if found
                )
                # A file separated by ';' or tabulators already reads '.'
                # between thousands: what reaches here (a ',' file, data in
                # memory) is read only once written as plain numbers.
                raise DataContentError(
                    f"Target column {column!r} is not numeric: values such as "
                    f"{shown} are numbers written {written}, a format that is "
                    f"not read. Write them as plain numbers.",
                    field = "data",
                )
            raise InvalidInputError(
                f"Target column {column!r} is not numeric: values such as "
                f"{shown} are not numbers.",
                field = "target",
                hint  = (
                    "Leave the cells of missing values empty instead of "
                    "marking them with text such as '-' or '?', and check "
                    "that the target is the column of values to forecast."
                ),
            )


# Characters of a value of the data quoted in a message.
_MAX_QUOTED_CHARS = 20


def _quoted_value(value: object) -> object:
    """
    Return a value of the data for a message: a numpy scalar as the Python
    value it holds, and text cut at `_MAX_QUOTED_CHARS` characters.
    """
    value = value.item() if isinstance(value, np.generic) else value
    if isinstance(value, str) and len(value) > _MAX_QUOTED_CHARS:
        return value[:_MAX_QUOTED_CHARS] + "..."
    return value


def _validate_target_exists(data: pd.DataFrame, target: str | list[str]) -> None:
    """
    Validate that the target column(s) exist in the DataFrame, and that a
    list of targets is not empty and names each column once.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str, list
        Name(s) of the target column(s).
    """
    if isinstance(target, list) and not target:
        raise InvalidInputError(
            "`target` is an empty list: pass the name of the column to "
            "forecast, or a list with the column of each series.",
            field = "target",
        )
    targets = target if isinstance(target, list) else [target]
    # skforecast names the series with text and looks them up with the
    # column names (skforecast issue #1357): integer names fail inside it.
    not_text = [col for col in targets if not isinstance(col, str)]
    if not_text:
        raise InvalidInputError(
            f"Target column(s) {not_text} are not named with text: the series "
            f"are named after their columns, and their names must be text.",
            field = "target",
            hint  = _TEXT_COLUMNS_HINT,
        )
    repeated = list(dict.fromkeys(c for c in targets if targets.count(c) > 1))
    if repeated:
        raise InvalidInputError(
            f"`target` names a column more than once: {repeated}. A list of "
            f"targets holds one column per series: name each one once.",
            field = "target",
        )
    missing = [col for col in targets if col not in data.columns]
    if missing:
        named = {str(col) for col in data.columns if not isinstance(col, str)}
        as_numbers = all(col in named for col in missing)
        raise InvalidInputError(
            f"Target column(s) {missing} not found in the DataFrame. "
            f"Available columns: {list(data.columns)}",
            field = "target",
            hint  = _TEXT_COLUMNS_HINT if as_numbers else None,
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


_WEEKDAY_NAMES = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)


def _daily_or_finer(frequency: str | None) -> tuple[bool, bool]:
    """
    Return whether a frequency puts a timestamp on every day it covers (a
    step of a day or less, or business days), and whether it is business
    days, whose grid has no Saturday or Sunday.
    """
    if frequency is None:
        return False, False
    try:
        offset = pd.tseries.frequencies.to_offset(frequency)
    except ValueError:
        return False, False
    if isinstance(offset, pd.offsets.BusinessDay) and offset.n == 1:
        return True, True

    return isinstance(offset, pd.offsets.Tick) and offset.nanos <= _DAY_NANOS, False


def _open_every_weekday(dates: pd.DatetimeIndex, business: bool) -> bool:
    """
    Return whether dates fall on every day of the week of their grid (Monday
    to Friday for business days), so that none of them can be closed. It
    spares sorting the dates of most data, whose gaps are not closed days.
    """
    days = np.asarray(pd.DatetimeIndex(dates).dayofweek, dtype=float)
    counts = np.bincount(days[~np.isnan(days)].astype(np.int64), minlength=7)

    return bool(counts[:5 if business else 7].all())


def _wall_nanoseconds(dates: pd.DatetimeIndex) -> np.ndarray | None:
    """
    Return the sorted, distinct dates as nanoseconds of their wall time (the
    local time of time zone aware dates), or None when they do not fit in
    nanoseconds.
    """
    dates = pd.DatetimeIndex(dates).dropna()
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    try:
        nanoseconds = dates.as_unit("ns").asi8
    except (OverflowError, ValueError):
        return None
    # Most indexes are already sorted and distinct: no sort is needed.
    if (np.diff(nanoseconds) > 0).all():
        return nanoseconds

    return np.unique(nanoseconds)


def _closed_weekdays_ns(dates: np.ndarray, business: bool) -> np.ndarray:
    """
    Return the days of the week (0 for Monday) on which no date of `dates`
    (sorted wall times in nanoseconds) falls, although at least two of them
    lie within their range.
    """
    days = dates // _DAY_NANOS
    first, n_days = days[0], days[-1] - days[0] + 1
    # 1970-01-01, day 0, was a Thursday.
    counts = np.full(7, n_days // 7)
    counts[(first + 3 + np.arange(n_days % 7)) % 7] += 1
    if business:
        counts[5:] = 0
    counts[np.unique((days + 3) % 7)] = 0

    return np.flatnonzero(counts >= 2)


def _gap_weekdays_ns(
    dates: np.ndarray,
    frequency: str,
    business: bool,
) -> list[int] | None:
    """
    Return the days of the week that every timestamp missing from the grid
    of `frequency` falls on, when the dates never fall on them (see
    `_closed_weekdays_ns`): an empty list when no timestamp is missing, and
    None when some missing timestamp falls on another day.
    """
    if len(dates) < 2:
        return []
    offset = pd.tseries.frequencies.to_offset(frequency)
    if not business:
        steps = (dates - dates[0]) // offset.nanos
        if steps[-1] + 1 == len(dates):
            return []
    closed = _closed_weekdays_ns(dates, business)
    if len(closed) == 0:
        return None
    if business:
        grid = pd.date_range(
            pd.Timestamp(dates[0]), pd.Timestamp(dates[-1]), freq=frequency
        ).asi8
        missing = np.setdiff1d(grid, dates, assume_unique=True)
    else:
        missing = dates[0] + offset.nanos * np.setdiff1d(
            np.arange(steps[-1] + 1), steps, assume_unique=True
        )
    if len(missing) == 0:
        return []
    if not np.isin((missing // _DAY_NANOS + 3) % 7, closed).all():
        return None

    return [int(weekday) for weekday in closed]


def closed_weekdays(
    dates: pd.DatetimeIndex,
    frequency: str | None,
) -> list[int]:
    """
    Return the days of the week on which dates of a daily or finer frequency
    never fall, although their range holds at least two of each (a shop
    closed on Sundays).

    Parameters
    ----------
    dates : pandas DatetimeIndex
        Dates of a series, with a value or a row. Time zone aware dates are
        read in their local time.
    frequency : str, None
        Frequency of the dates.

    Returns
    -------
    weekdays : list of int
        Days of the week (0 for Monday), or an empty list when the frequency
        is coarser than a day, or not known.
    """
    daily, business = _daily_or_finer(frequency)
    if not daily or _open_every_weekday(dates, business):
        return []
    nanoseconds = _wall_nanoseconds(dates)
    if nanoseconds is None or len(nanoseconds) < 2:
        return []

    return [int(day) for day in _closed_weekdays_ns(nanoseconds, business)]


def regular_gap_weekdays(
    dates: pd.DatetimeIndex | dict[object, np.ndarray],
    frequency: str | None,
) -> list[int]:
    """
    Return the days of the week that every missing timestamp of a daily or
    finer frequency falls on, when those days have no date at all (a shop
    closed on Sundays): the gaps are regular, rather than missing at random.

    Parameters
    ----------
    dates : pandas DatetimeIndex, dict
        Dates of a single series (or of the rows of wide-format data), or
        the dates of each series of long-format data as wall times in
        nanoseconds (see `_long_series_dates`), each series checked on its
        own range.
    frequency : str, None
        Frequency of the data.

    Returns
    -------
    weekdays : list of int
        Days of the week (0 for Monday) of the missing timestamps, or an
        empty list when none is missing, when one falls on a day of the
        week that has dates (in its series), or when the frequency is
        coarser than a day, or not known.
    """
    daily, business = _daily_or_finer(frequency)
    if not daily:
        return []
    if isinstance(dates, dict):
        series = list(dates.values())
    elif _open_every_weekday(dates, business):
        return []
    else:
        nanoseconds = _wall_nanoseconds(dates)
        if nanoseconds is None:
            return []
        series = [nanoseconds]
    weekdays: set[int] = set()
    for nanoseconds in series:
        found = _gap_weekdays_ns(nanoseconds, frequency, business)
        if found is None:
            return []
        weekdays.update(found)

    return sorted(weekdays)


def weekday_names(weekdays: list[int]) -> str:
    """
    Name days of the week in plural (`'Saturdays and Sundays'`).
    """
    names = [f"{_WEEKDAY_NAMES[day]}s" for day in sorted(weekdays)]
    if len(names) == 1:
        return names[0]

    return ", ".join(names[:-1]) + " and " + names[-1]


def _check_duplicate_timestamps(
    data: pd.DataFrame,
    target: str | list[str],
    date_col: str | None,
    index_type: str,
    data_format: str,
    series_id_column: str | None,
    ignored_columns: list[str] | None = None,
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
    ignored_columns : list of str, default None
        Columns the profile leaves out, whose values may differ between
        repeated rows (the first row is kept).

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
    ignored = set(ignored_columns or [])
    value_cols = [
        col for col in data.columns
        if col not in (date_col, series_id_column) and str(col) not in ignored
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
        message = _duplicate_timestamps_message(
            conflicts   = conflicts,
            data        = data,
            dates       = dates,
            target      = target,
            date_col    = date_col,
            data_format = data_format,
            long_format = long_format,
        )
        # The other problems of the same read, so they are all solved in
        # one pass instead of one per attempt.
        message += _other_date_problems_note(
            n_identical = len(repeated_keys) - len(conflicts),
            dates       = dates[valid],
            ids         = data[series_id_column][valid] if long_format else None,
        )
        raise InvalidInputError(message, field="data")

    keep_mask = ~(keys.duplicated(keep="first").to_numpy() & valid)

    return len(repeated_keys), keep_mask


def _other_date_problems_note(
    n_identical: int,
    dates: pd.DatetimeIndex,
    ids: pd.Series | None,
) -> str:
    """
    Describe what else is wrong with the dates of data rejected for
    timestamps repeated with different values.

    The profile stops at those timestamps, so the timestamps repeated in
    identical rows and the missing ones would only show in a later attempt,
    after the user has already been asked about the first problem.

    Parameters
    ----------
    n_identical : int
        Number of timestamps (per series) repeated in identical rows.
    dates : pandas DatetimeIndex
        Date of every row that has one.
    ids : pandas Series, None
        Series id of each of those rows, for long format; None otherwise.

    Returns
    -------
    note : str
        Sentence to append to the error message, starting with a space, or
        an empty string when nothing else was found. The missing timestamps
        are counted on the distinct dates, as they will be once the repeated
        rows are solved; they are left out when no frequency can be inferred
        from them.
    """
    if ids is None:
        distinct = pd.DatetimeIndex(dates.unique()).sort_values()
        frequency = infer_frequency(distinct)
        n_missing = count_missing_timestamps(distinct, frequency)
    else:
        series_dates = _long_series_dates(dates, ids)
        frequency, n_missing = None, 0
        # Time zone aware dates of several series need the search in UTC of
        # the profile; their gaps are left to it.
        if series_dates is not None and dates.tz is None:
            frequency, n_missing, error = _search_long_frequency(series_dates)
            if error is not None:
                frequency, n_missing = None, 0

    found = []
    if n_identical > 0:
        plural = "s" if n_identical != 1 else ""
        found.append(
            f"{n_identical} other timestamp{plural} repeated in identical "
            f"rows (profiling keeps one of them)"
        )
    if frequency is not None and n_missing > 0:
        plural = "s" if n_missing != 1 else ""
        found.append(
            f"{n_missing} timestamp{plural} missing at the '{frequency}' "
            f"frequency, which will still be missing once the repeated rows "
            f"are solved"
        )
    if not found:
        return ""

    return f" The same data also has {' and '.join(found)}."


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


def _format_split_ts(ts: pd.Timestamp, with_time: bool = False) -> str:
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
    with_time : bool, default False
        Whether to write the time also at midnight: True when the dates
        are not all at midnight (sub-daily data), where a date-only
        `end_train` made `.loc[:end_train]` train on the whole day.

    Returns
    -------
    end_train : str
        Date-only string (e.g. `'2005-03-01'`) when the timestamp falls
        on midnight and `with_time` is False, otherwise a full timestamp
        string (e.g. `'2012-08-07 23:00:00'`).
    """
    if with_time or ts.hour != 0 or ts.minute != 0 or ts.second != 0:
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
            hint  = (
                "Give the data a datetime index with a regular frequency, "
                "or a date column whose dates follow one."
            ),
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
        try:
            # A date without time zone is read in the zone of the data.
            ts = training_end(test_size, index.tz)
        except (ValueError, TypeError) as exc:
            raise InvalidInputError(
                f"`test_size` is text that is not a date: {test_size!r}. Pass "
                f"an integer, a fraction in (0, 1) or the first date of the "
                f"test set, such as '2023-03-01'.",
                field = "test_size",
            ) from exc
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

    return _format_split_ts(
        index[boundary_idx], with_time=bool((index != index.normalize()).any())
    )


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

    return int((index > training_end(end_train, index.tz)).sum())
