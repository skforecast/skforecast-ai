"""Data profiling: inspect a DataFrame and produce a DataProfile."""

from pathlib import Path

import pandas as pd

from ..schemas import DataProfile
from .frequency import estimate_seasonality, infer_frequency


def create_data_profile(
    data: pd.DataFrame | str | Path,
    target: str,
    date_column: str | None = None,
    series_id_column: str | None = None,
) -> DataProfile:
    """
    Generate a deterministic data profile from a dataset.

    Parameters
    ----------
    data : pandas DataFrame, str, Path
        Input dataset. If a string or Path, it is treated as a CSV file path
        and loaded with `pandas.read_csv`.
    target : str
        Name of the column to forecast.
    date_column : str, default None
        Name of the column containing timestamps. If None, the function
        attempts to detect it from the index or columns.
    series_id_column : str, default None
        Name of the column identifying individual series in long format.
        If None, the dataset is treated as a single series.

    Returns
    -------
    profile : DataProfile
        Validated profile containing metadata, detected features, and
        warnings about the dataset.
    """
    if isinstance(data, (str, Path)):
        data = pd.read_csv(data, parse_dates=True, index_col=0)

    date_col, index_type = detect_date_column(data, date_column)

    if index_type == "datetime" and date_col is None:
        datetime_index = data.index
    elif date_col is not None and date_col in data.columns:
        datetime_index = pd.DatetimeIndex(data[date_col])
    else:
        datetime_index = None

    frequency = infer_frequency(datetime_index) if datetime_index is not None else None

    n_series, resolved_series_id = detect_series_structure(
        data, target, date_col, series_id_column
    )

    exog_columns = detect_exog_columns(data, target, date_col, resolved_series_id)
    categorical_exog = detect_categorical_exog(data, exog_columns)
    missing_values = count_missing_values(data)
    inferred_seasonalities = estimate_seasonality(frequency)

    n_observations = len(data)
    warnings = generate_warnings(
        n_observations, frequency, missing_values, index_type
    )

    return DataProfile(
        n_observations=n_observations,
        n_series=n_series,
        index_type=index_type,
        frequency=frequency,
        target=target,
        date_column=date_col,
        series_id_column=resolved_series_id,
        exog_columns=exog_columns,
        categorical_exog=categorical_exog,
        missing_values=missing_values,
        inferred_seasonalities=inferred_seasonalities,
        warnings=warnings,
    )


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


def detect_series_structure(
    data: pd.DataFrame,
    target: str,
    date_column: str | None,
    series_id_column: str | None,
) -> tuple[int, str | None]:
    """
    Determine the number of series and the series identifier column.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str
        Name of the target column.
    date_column : str, default None
        Name of the date column.
    series_id_column : str, default None
        User-specified series identifier column.

    Returns
    -------
    n_series : int
        Number of individual time series detected.
    series_id_column : str, None
        Resolved name of the series identifier column.
    """
    if series_id_column is not None and series_id_column in data.columns:
        n_series = data[series_id_column].nunique()
        return n_series, series_id_column

    return 1, None


def detect_exog_columns(
    data: pd.DataFrame,
    target: str,
    date_column: str | None,
    series_id_column: str | None,
) -> list[str]:
    """
    Identify exogenous columns (everything except target, date, series_id).

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    target : str
        Name of the target column.
    date_column : str, default None
        Name of the date column.
    series_id_column : str, default None
        Name of the series identifier column.

    Returns
    -------
    exog_columns : list
        Names of exogenous predictor columns.
    """
    excluded = {target}
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


def count_missing_values(data: pd.DataFrame) -> dict[str, int]:
    """
    Count missing values per column.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.

    Returns
    -------
    missing : dict
        Mapping of column name to count of missing values. Only columns
        with at least one missing value are included.
    """
    counts = data.isna().sum()
    return {col: int(count) for col, count in counts.items() if count > 0}


def generate_warnings(
    n_observations: int,
    frequency: str | None,
    missing_values: dict[str, int],
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
    missing_values : dict
        Mapping of column name to count of missing values.
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

    if missing_values:
        total_missing = sum(missing_values.values())
        missing_rate = total_missing / (n_observations * len(missing_values))
        if missing_rate > 0.2:
            warnings.append(
                f"High missing value rate ({missing_rate:.1%}). "
                "Consider imputation before forecasting."
            )

    return warnings
