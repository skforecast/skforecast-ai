################################################################################
#                                  Dates                                       #
#                                                                              #
# Date helpers shared by profiling and recommendation                          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
import numpy as np
import pandas as pd

try:
    from pandas.tseries.api import guess_datetime_format
except ImportError:  # pragma: no cover, pandas < 2.2
    from pandas._libs.tslibs.parsing import guess_datetime_format

# Text pandas skips when it looks for the date to guess the format from.
_SKIPPED_TEXT = {"", "NaT", "nat", "NAT", "nan", "NaN", "NAN", "now", "today"}


def parse_text_dates(values: pd.Series, mixed: bool = True) -> pd.Series:
    """
    Parse text dates as the generated script parses them.

    The format is guessed from the first date, as `pandas.to_datetime(values)`
    does, so day-first dates such as '13/01/2012' are read day-first
    throughout. The warning pandas emits for that guess is not shown.

    Parameters
    ----------
    values : pandas Series
        Text dates.
    mixed : bool, default True
        What to do when no format can be guessed, or a date does not follow
        it. When True, every date is parsed on its own (`format='mixed'`),
        as the CSV loader did; the generated script may then read them
        differently, a known limitation for mixed formats. When False,
        `pandas.to_datetime(values)` is called, which raises as the script
        does.

    Returns
    -------
    dates : pandas Series
        Parsed dates.
    """
    first = _first_date(values)
    date_format = None
    # pandas guesses a format only when its first date is exactly a str (not
    # a numpy str, a Timestamp or a date), and so does the script.
    if type(first) is str:
        # The guess warns about day-first formats; the script parses with
        # the same guess, and the warning would only repeat it here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            date_format = guess_datetime_format(first)
    if date_format is not None:
        try:
            return pd.to_datetime(values, format=date_format)
        except (ValueError, TypeError):
            pass

    return pd.to_datetime(values, format="mixed") if mixed else pd.to_datetime(values)


def _first_date(values: pd.Series | pd.Index) -> object:
    """
    Return the value pandas guesses the date format from.

    It is the first value that is not missing, skipping the text pandas reads
    as no date or as the current time ('', 'NaT', 'nan', 'now', 'today').
    """
    for value in values:
        if isinstance(value, str):
            if value not in _SKIPPED_TEXT:
                return value
        elif not (pd.api.types.is_scalar(value) and pd.isna(value)):
            return value

    return None


def _as_dates(values: pd.Series | pd.Index) -> pd.DatetimeIndex:
    """
    Return the values as dates, parsing text as the generated script does.
    """
    if pd.api.types.is_object_dtype(values) or pd.api.types.is_string_dtype(values):
        values = parse_text_dates(pd.Series(values), mixed=False)

    return pd.DatetimeIndex(pd.to_datetime(values))


def row_dates(data: pd.DataFrame, date_column: str | None) -> pd.DatetimeIndex | None:
    """
    Return the date of every row.

    The dates come from the date column (text parsed as the generated script
    parses it), a level of a MultiIndex or the DatetimeIndex, in that order.
    Profiling (sorting and repeated timestamps) and lag selection read the
    dates through this function.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    date_column : str, None
        Name of the date column, or of the MultiIndex level holding the
        dates (the second level when it has no name). When None, the
        DatetimeIndex is used.

    Returns
    -------
    dates : pandas DatetimeIndex, None
        One date per row (NaT when missing), or None when the data has no
        datetime source.
    """
    if date_column is not None and date_column in data.columns:
        return _as_dates(data[date_column])
    if date_column is not None and isinstance(data.index, pd.MultiIndex):
        # An unnamed date level is the second one, as profiling reads it.
        if date_column in data.index.names:
            level = date_column
        elif data.index.nlevels >= 2 and data.index.names[1] is None:
            level = 1
        else:
            level = None
        if level is not None:
            return _as_dates(data.index.get_level_values(level))
    if isinstance(data.index, pd.DatetimeIndex):
        return data.index

    return None


def date_positions(dates: pd.DatetimeIndex) -> np.ndarray:
    """
    Return the dates as integers that sort like the dates.

    The missing dates go after every other date.

    Parameters
    ----------
    dates : pandas DatetimeIndex
        Dates to order. Time zone aware dates are compared in UTC.

    Returns
    -------
    positions : numpy ndarray
        Time since the epoch in the unit of the dates, as int64, with NaT
        mapped to the largest int64.
    """
    positions = dates.asi8.copy()
    positions[np.asarray(dates.isna())] = np.iinfo(np.int64).max

    return positions
