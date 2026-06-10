################################################################################
#                               data_profile                                   #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from pathlib import Path
import numpy as np
import pandas as pd
from ..schemas import DataProfile

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

# TODO: Seasonality Logic - Handle Multipliers
# Update `estimate_seasonality` to handle numeric frequency multipliers 
# (e.g., "2H" or "15T"). Extract the multiplier and scale the base seasonal periods.

# TODO: Magic Numbers - Parameterize Train Split
# `_compute_end_train` hardcodes an 80% split (`idx = int(len(idx) * 0.8) - 1`). 
# Parameterize this by adding a `train_fraction` argument with a default of 0.8 
# so users can customize the split boundary.

# TODO: Multi-Target Logic - Check All Target Dtypes
# In `create_data_profile`, `target_dtype` only checks the first target column. 
# For wide-format multi-series, it should verify if dtypes are mixed across targets 
# or return a dictionary mapping each target to its dtype.

# TODO: Bug Fix - Prevent Data Leakage in Sub-daily Splits
# `_compute_end_train` checks only the split timestamp for a time component. 
# If a sub-daily index happens to split exactly at midnight, it returns a 
# date string, causing pandas `.loc` to include the rest of the day 
# (up to 23:59:59), leaking test data into the train set. 

def infer_frequency(index: pd.DatetimeIndex) -> str | None:
    """
    Infer the frequency of a DatetimeIndex.

    Parameters
    ----------
    index : pandas DatetimeIndex
        The datetime index to infer frequency from.

    Returns
    -------
    frequency : str, None
        Inferred pandas frequency string, or None if the frequency cannot
        be determined (e.g. too few observations or irregular spacing).
    """
    if len(index) < 3:
        return None

    try:
        freq = pd.infer_freq(index)
    except (TypeError, ValueError):
        return None

    return freq


def estimate_seasonality(frequency: str | None) -> list[int]:
    """
    Estimate seasonal periods from a known frequency string.

    Parameters
    ----------
    frequency : str, None
        Pandas frequency string (e.g. `'h'`, `'D'`, `'ME'`).

    Returns
    -------
    seasonalities : list
        List of integer seasonal periods inferred from the frequency.
        Returns an empty list if the frequency is None or unrecognized.

    Notes
    -----
    This is a heuristic mapping. It does not perform spectral analysis
    or autocorrelation-based detection.
    """
    if frequency is None:
        return []

    # Drop anchor suffixes from offset aliases (e.g. 'W-SUN', 'QS-OCT',
    # 'A-DEC') so anchored frequencies returned by `pd.infer_freq` match
    # the base keys below.
    freq_upper = frequency.upper().split("-")[0]

    seasonality_map: dict[str, list[int]] = {
        "T":    [60, 1440],
        "MIN":  [60, 1440],
        "H":    [24, 168],
        "D":    [7, 365],
        "B":    [5, 252],
        "W":    [52],
        "MS":   [12],
        "ME":   [12],
        "M":    [12],
        "QS":   [4],
        "QE":   [4],
        "Q":    [4],
        "YS":   [1],
        "YE":   [1],
        "Y":    [1],
        "A":    [1],
    }

    for key, seasons in seasonality_map.items():
        if freq_upper == key or freq_upper.endswith(key):
            return seasons

    return []


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
    """
    if isinstance(data, (str, Path)):
        data = pd.read_csv(data)
        # Attempt to parse the first object-dtype column as datetime.
        # This handles CSVs exported with df.to_csv() where the date
        # index becomes a regular column.
        data = _try_parse_first_date_column(data)

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

    # Extract a datetime index suitable for quality checks (frequency,
    # gaps, duplicates, monotonicity). For long format, use a single
    # representative series to avoid stacked dates breaking inference.
    datetime_index = _extract_datetime_index(
        data, date_col, index_type, data_format, series_id_column
    )

    frequency = infer_frequency(datetime_index) if datetime_index is not None else None

    has_duplicate_timestamps = detect_duplicate_timestamps(datetime_index)

    # If frequency inference failed due to duplicates, retry on deduplicated index
    if frequency is None and has_duplicate_timestamps and datetime_index is not None:
        deduped_index = datetime_index[~datetime_index.duplicated(keep="first")]
        frequency = infer_frequency(deduped_index)

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

    has_gaps = detect_gaps(datetime_index, frequency)
    index_is_monotonic = _check_monotonic(datetime_index, data)
    frequency_is_set = _check_frequency_is_set(datetime_index, data)

    # Early stop: constant target makes forecasting meaningless
    if _check_target_is_constant(data, first_target):
        raise ValueError(
            f"Target column '{first_target}' is constant (zero variance). "
            "Forecasting a constant series is not meaningful."
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
        representative_n, frequency, missing_target, missing_exog, index_type
    )

    # Compute end_train: the datetime at the 80% mark of the index
    end_train = _compute_end_train(datetime_index)

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
        end_train=end_train,
        # Diagnostics
        warnings=warnings,
    )


def _try_parse_first_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """
    Try to convert the first object or string dtype column to datetime.

    When a CSV is exported via `DataFrame.to_csv()` the DatetimeIndex
    becomes a regular column with object or string dtype (e.g. `"Unnamed: 0"` or
    `"date"`). `pd.read_csv(parse_dates=True)` often fails to
    auto-parse these. This helper converts the first parseable column
    in-place so that downstream `detect_date_column` can identify it.

    Parameters
    ----------
    data : pandas DataFrame
        DataFrame loaded from CSV.

    Returns
    -------
    data : pandas DataFrame
        DataFrame with the first date-like column converted (if found).
    """
    for col in data.columns:
        if pd.api.types.is_object_dtype(data[col]) or pd.api.types.is_string_dtype(data[col]):
            try:
                parsed = pd.to_datetime(data[col], format="mixed")
                if parsed.notna().all():
                    data[col] = parsed
                    break
            except (ValueError, TypeError):
                continue
    return data


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
        Name of the date column if found in columns, None if the index
        is used as the datetime source or no datetime is found.
    index_type : str
        One of `'datetime'`, `'range'`, `'other'`.
    """
    if date_column is not None:
        if date_column in data.columns:
            return date_column, "datetime"
        return None, "other"

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
    date_name = names[1] if names[1] is not None else "date"

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
        first_dates = data.groupby(series_id_column).apply(
            lambda g: g.index.min()
        )
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
            "Could not infer frequency from the datetime index. "
            "The series may have irregular spacing or gaps."
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
        raise ValueError(
            f"Target column(s) {missing} not found in the DataFrame. "
            f"Available columns: {list(data.columns)}"
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
    expected timestamps. When `pd.infer_freq` returns None (often
    because the gaps themselves prevent inference), this function
    returns False — meaning "gaps not detected", not "no gaps exist".
    In such cases, a separate warning about uninferable frequency is
    emitted by the profiler.
    """
    if datetime_index is None or frequency is None:
        return False

    if len(datetime_index) < 2:
        return False

    try:
        expected = pd.date_range(
            start=datetime_index.min(),
            end=datetime_index.max(),
            freq=frequency,
        )
    except ValueError:
        return False

    return len(expected) > len(datetime_index)


def detect_duplicate_timestamps(
    datetime_index: pd.DatetimeIndex | None,
) -> bool:
    """
    Detect whether the index contains duplicate timestamps.

    Parameters
    ----------
    datetime_index : pandas DatetimeIndex, None
        The datetime index to check.

    Returns
    -------
    has_duplicates : bool
        True if duplicate timestamps exist.
    """
    if datetime_index is None:
        return False

    return bool(datetime_index.duplicated().any())


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
    the constructed DatetimeIndex will never have `.freq` set —
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


def _compute_end_train(
    datetime_index: pd.DatetimeIndex | None,
) -> str | None:
    """
    Compute the end-of-training date at the 80 % mark of the index.

    For sub-daily frequencies the full timestamp is returned to avoid
    ambiguity between partial-string `.loc` slicing (which includes all
    hours on a given date) and boolean comparison (which treats a date
    string as midnight).

    Parameters
    ----------
    datetime_index : pandas DatetimeIndex, None
        The sorted datetime index of the dataset.

    Returns
    -------
    end_train : str, None
        ISO-formatted date or datetime string at the 80 % position.
        Date-only (e.g. `'2005-03-01'`) for daily or coarser
        frequencies; full timestamp (e.g. `'2012-08-07 23:00:00'`) for
        sub-daily frequencies. None if no datetime index is available.
    """
    if datetime_index is None or len(datetime_index) == 0:
        return None
    idx = int(len(datetime_index) * 0.8) - 1
    idx = max(0, min(idx, len(datetime_index) - 1))
    ts = datetime_index[idx]
    # Sub-daily: return full timestamp to avoid .loc vs > comparison mismatch
    if ts.hour != 0 or ts.minute != 0 or ts.second != 0:
        return str(ts)
    return str(ts.date())
