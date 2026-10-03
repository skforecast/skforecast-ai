################################################################################
#                                  Dates                                       #
#                                                                              #
# Date helpers shared by profiling and recommendation                          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import re
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
    date_format = guessed_date_format(values)
    if date_format is not None:
        try:
            return pd.to_datetime(values, format=date_format)
        except (ValueError, TypeError):
            pass

    return pd.to_datetime(values, format="mixed") if mixed else pd.to_datetime(values)


def guessed_date_format(values: pd.Series) -> str | None:
    """
    Return the format pandas guesses for text dates, from their first date.

    pandas guesses a format only when its first date is exactly a str (not a
    numpy str, a Timestamp or a date), and so does the generated script.

    Parameters
    ----------
    values : pandas Series
        Text dates.

    Returns
    -------
    date_format : str, None
        The guessed format, or None when there is none.
    """
    first = _first_date(values)
    if type(first) is not str:
        return None
    # The guess warns about day-first formats; the script parses with the
    # same guess, and the warning would only repeat it here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        date_format = guess_datetime_format(first)

    return date_format


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


def training_end(end_train: str, tz: object = None) -> pd.Timestamp:
    """
    Return `end_train` as a timestamp comparable with dates of time zone
    `tz`.

    A plan writes `end_train` without the time zone of the data (the script
    slices `.loc[:end_train]`, where pandas reads it in the zone of the
    index), so it is localized to `tz` when it has none.

    Parameters
    ----------
    end_train : str
        Last training date of an evaluation-mode plan.
    tz : tzinfo, str, default None
        Time zone of the dates it is compared with.

    Returns
    -------
    end : pandas Timestamp
        Last training date, in the time zone of the dates.
    """
    end = pd.Timestamp(end_train)
    if tz is not None and end.tz is None:
        end = end.tz_localize(tz)

    return end


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


# A time zone written after the time of a date ('10:00:00+01:00', '10:00 AM
# -0500', '10:00 GMT+01:00', 'T100000+0100', '10:00:00 +0100 2012'): 'Z', a
# UTC offset or a name of UTC that pandas reads ('UTC', 'GMT'). The time
# before it tells an offset from the year of a date such as '25-03-2012'.
_WRITTEN_ZONE = re.compile(
    r"(?::\d{2}|T\d{4,6})(?:[.,]\d+)?\s*(?:[AaPp]\.?[Mm]\.?\s*)?"
    r"(?:(?:GMT|UTC)\s*(?=[+-]))?([Zz]|[+-]\d{1,2}(?::?\d{2})?|[A-Za-z]{2,5})"
    r"(?:\s+\d{4})?$"
)
# Endings that may hold a time zone, a cheap filter before the pattern above.
_ZONE_ENDING = re.compile(
    r"(?:[Zz]|[+-]\d{1,2}:?\d{0,2}|[A-Za-z]{2,5})(?:\s+\d{4})?$"
)
# Characters of the ending read to find the zone: an offset and a year.
_ENDING_LENGTH = 11
# Names that stand for UTC itself. Other zone names ('CET') are left to
# pandas, which drops them with a warning of its own.
_UTC_NAMES = {"Z", "UTC", "GMT"}
# Text that pandas reads as a missing date.
_MISSING_TEXT = {"", "nat", "nan"}


def is_text(values: pd.Series | pd.Index) -> bool:
    """
    Return whether a column holds text (object or string dtype).

    Parameters
    ----------
    values : pandas Series, pandas Index
        Values of a column.

    Returns
    -------
    text : bool
        True for object or string dtype.
    """

    return pd.api.types.is_object_dtype(values) or pd.api.types.is_string_dtype(values)


def missing_dates(values: pd.Series) -> np.ndarray:
    """
    Return which values hold no date.

    Missing values (NaN, None, NaT) hold no date, and so does text made only
    of blanks, or reading 'NaT' or 'nan' (which pandas parses as a missing
    date).

    Parameters
    ----------
    values : pandas Series
        Values of a date column.

    Returns
    -------
    missing : numpy ndarray
        Boolean mask, True where the value holds no date.
    """
    missing = values.isna().to_numpy()
    if not is_text(values):
        return missing
    try:
        text = values.str.strip().str.lower()
    except AttributeError:
        # No text in the column: nothing can be blank.
        return missing

    return missing | text.isin(_MISSING_TEXT).to_numpy(dtype=bool)


def is_missing_date(value: object) -> bool:
    """
    Return whether one value holds no date, as `missing_dates` reads it.

    Parameters
    ----------
    value : object
        Value of a date column.

    Returns
    -------
    missing : bool
        True when the value holds no date.
    """
    if isinstance(value, str):
        return value.strip().lower() in _MISSING_TEXT

    return bool(pd.api.types.is_scalar(value) and pd.isna(value))


def time_zones(values: pd.Series) -> list[str]:
    """
    Return the distinct time zones written in text dates, in order of use.

    The zone is read as written after the time: a UTC offset (`'Z'`,
    `'UTC'`, `'GMT'` and `'-00:00'` count as `'+00:00'`, `'+0100'` as
    `'+01:00'`). A word (a zone name such as `'CET'`, which pandas drops with
    a warning of its own, or a weekday) is not read as a time zone. Dates
    without a time zone count as `'no time zone'`. Values that are not text
    (datetime objects) are left out: pandas reads their time zones when it
    parses them.

    Parameters
    ----------
    values : pandas Series
        Values of a date column without missing values.

    Returns
    -------
    zones : list of str
        Distinct time zones, such as `'+01:00'` or `'no time zone'`.
    """
    zones: dict[str, None] = {}
    texts = pd.Series(
        [
            value.rstrip() for value in pd.unique(values.to_numpy())
            if isinstance(value, str)
        ],
        dtype=object,
    )
    if len(texts) > 0:
        # The zone of a date depends only on its last characters, so one
        # date per distinct ending is read with the full pattern.
        endings = texts.str[-_ENDING_LENGTH:]
        for ending, text in texts.groupby(endings, sort=False).first().items():
            if _ZONE_ENDING.search(ending):
                zones[_written_zone(text)] = None
            else:
                zones["no time zone"] = None

    return list(zones)


def _written_zone(text: str) -> str:
    """
    Return the time zone written after the time of a date: an offset as
    `'+HH:MM'`, or `'no time zone'` (also for a zone name other than UTC).
    """
    match = _WRITTEN_ZONE.search(text)
    if match is None:
        return "no time zone"
    zone = match.group(1).upper()
    if zone.isalpha():
        return "+00:00" if zone in _UTC_NAMES else "no time zone"
    digits = zone[1:].replace(":", "")
    hours, minutes = (digits[:-2], digits[-2:]) if len(digits) > 2 else (digits, "00")
    offset = f"{zone[0]}{int(hours):02d}:{minutes}"

    return "+00:00" if offset == "-00:00" else offset
