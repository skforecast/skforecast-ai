################################################################################
#                              Profile schemas                                 #
#                                                                              #
# Profile schemas: data description and forecaster-specific analysis           #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Literal
import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator
from .._display import DisplayMixin, render_profile

class SeriesLengthInfo(BaseModel):
    """
    Per-series index range and observation count.

    Attributes
    ----------
    start : str, default None
        First timestamp of the series as a string (e.g. `'2020-01-01'`).
        None when the index is not datetime.
    end : str, default None
        Last timestamp of the series as a string. None when the index is
        not datetime.
    length : int
        Number of observations in the series.
    """

    start: str | None = None
    end: str | None = None
    length: int


def _resolve_observation_counts(
    series_lengths: dict[str, SeriesLengthInfo],
    frequency: str | None,
) -> tuple[int, int]:
    """
    Resolve the span index length and the total number of observations.

    Merges the two quantities the assistant needs from the per-series
    ranges: the length of the union datetime index that spans every
    series (used for lag, window, and cross-validation sizing) and the
    pooled total number of observations (used for estimator sizing).

    Parameters
    ----------
    series_lengths : dict
        Mapping of series name to its `SeriesLengthInfo`.
    frequency : str, default None
        Inferred pandas frequency string. When None, or when datetime
        bounds are missing, the span falls back to the longest individual
        series.

    Returns
    -------
    span_index_length : int
        Number of observations in the union index from the earliest start
        to the latest end at `frequency`.
    n_total_observations : int
        Sum of every series length.
    """
    infos = list(series_lengths.values())
    n_total_observations = sum(info.length for info in infos)

    starts = [info.start for info in infos if info.start is not None]
    ends = [info.end for info in infos if info.end is not None]
    if not starts or not ends or frequency is None:
        return max(info.length for info in infos), n_total_observations

    start = min(pd.Timestamp(s) for s in starts)
    end = max(pd.Timestamp(e) for e in ends)
    try:
        span_index_length = len(
            pd.date_range(start=start, end=end, freq=frequency)
        )
    except (ValueError, TypeError):
        span_index_length = max(info.length for info in infos)

    return span_index_length, n_total_observations


class DataProfile(BaseModel):
    """
    Profile of the input time series dataset.

    Attributes
    ----------
    data_format : str, default 'single'
        Layout of the dataset. One of `'single'`, `'wide'`, `'long'`.
    n_series : int
        Number of individual time series.
    series_lengths : dict
        Mapping of series name to its `SeriesLengthInfo` (start, end,
        and length). Always populated, including single series (keyed by
        the target name). The task-aware effective number of
        observations is derived from this mapping (span for
        `multi_series`, common length for `multivariate`, single length
        otherwise).
    span_index_length : int
        Length of the union datetime index spanning every series, from
        the earliest start to the latest end at `frequency`. Falls back
        to the longest individual series when datetime bounds or
        frequency are unavailable. Computed automatically from
        `series_lengths`.
    n_total_observations : int
        Pooled total number of observations across all series (the sum of
        every series length). Computed automatically from
        `series_lengths`.
    target : str, list
        Name(s) of the target column(s). A single string for single
        series and long format. A list of strings for wide format where
        each element is a series column.
    target_dtype : str, default 'numeric'
        Data type category of the target column. One of `'numeric'`,
        `'categorical'`, `'other'`.
    target_stats : dict
        Mapping of target column (or series name) to a dict with keys
        `'min'`, `'max'`, `'mean'`, `'std'` computed on non-NaN
        values. Empty dict if no valid observations exist.
    missing_target : dict
        Mapping of target column (or series name) to count of NaN values.
        Only entries with at least one missing value are included.
    date_column : str, default None
        Name of the column containing timestamps.
    series_id_column : str, default None
        Name of the column identifying individual series.
    index_type : str
        Type of the DataFrame index. One of `'datetime'`, `'range'`,
        `'other'`.
    frequency : str, default None
        Inferred pandas frequency string (e.g. `'h'`, `'D'`, `'ME'`).
    frequency_is_set : bool, default False
        Whether the index already has a frequency set (`index.freq`).
    index_is_monotonic : bool, default True
        Whether the index is sorted in ascending order.
    has_gaps : bool, default False
        Whether the datetime index has missing timestamps within its range.
    has_duplicate_timestamps : bool, default False
        Whether the index contains duplicate timestamps.
    exog_columns : list
        Names of exogenous predictor columns.
    categorical_exog : list
        Subset of `exog_columns` that are categorical.
    missing_exog : dict
        Mapping of exogenous column name to count of missing values.
        Only columns with at least one missing value are included.
    data_path : str, default 'data.csv'
        Path to the source CSV file. Derived automatically during
        profiling: if the input is a file path, this stores it; if the
        input is a DataFrame, defaults to `'data.csv'`.
    warnings : list
        Human-readable warnings generated during profiling.
    """

    # -- Structure / Format --
    data_format: Literal["single", "wide", "long"] = "single"
    n_series: int
    series_lengths: dict[str, SeriesLengthInfo]
    span_index_length: int = 0
    n_total_observations: int = 0

    # -- Target --
    target: str | list[str]
    target_dtype: Literal["numeric", "categorical", "other"] = "numeric"
    target_stats: dict[str, dict[str, float]] = Field(default_factory=dict)
    missing_target: dict[str, int] = Field(default_factory=dict)

    # -- Index / Time --
    date_column: str | None = None
    series_id_column: str | None = None
    index_type: Literal["datetime", "range", "other"]
    frequency: str | None = None
    frequency_is_set: bool = False
    index_is_monotonic: bool = True
    has_gaps: bool = False
    has_duplicate_timestamps: bool = False

    # -- Exogenous --
    exog_columns: list[str] = Field(default_factory=list)
    categorical_exog: list[str] = Field(default_factory=list)
    missing_exog: dict[str, int] = Field(default_factory=dict)

    # -- Source --
    data_path: str = "data.csv"

    # -- Train/test split --
    start_date: str | None = None

    # -- Diagnostics --
    warnings: list[str] = Field(default_factory=list)

    @field_validator("series_lengths", mode="before")
    @classmethod
    def _coerce_series_lengths(cls, value: object) -> object:
        """Coerce `int` values into `SeriesLengthInfo(length=int)`."""
        if isinstance(value, dict):
            return {
                key: ({"length": v} if isinstance(v, int) else v)
                for key, v in value.items()
            }
        return value

    @model_validator(mode="after")
    def _populate_observation_counts(self) -> "DataProfile":
        """Derive `span_index_length` and `n_total_observations`."""
        if self.series_lengths:
            span, total = _resolve_observation_counts(
                self.series_lengths, self.frequency
            )
            self.span_index_length = span
            self.n_total_observations = total
        return self

class SeriesPacf(BaseModel):
    """
    PACF-significant lags for a single series.

    Attributes
    ----------
    series_id : str
        Name of the series (target column for single/wide, series id for
        long format).
    n_observations : int
        Number of non-NaN observations in the series (all NaNs, edge and
        interior, are excluded by the count). Used as the sample size for
        the PACF significance test. Not the raw column length.
    lags : list of int
        Significant lags retained by Benjamini-Hochberg FDR correction
        and the minimum effect-size floor, ordered by descending `|PACF|`
        (importance order, not ascending index).
    pacf_abs : list of float
        Absolute PACF magnitude aligned element-wise with `lags`
        (same order).
    """

    series_id: str
    n_observations: int
    lags: list[int] = Field(default_factory=list)
    pacf_abs: list[float] = Field(default_factory=list)


class ForecastingProfile(DisplayMixin, BaseModel):
    """
    High-level profile of the forecasting problem.

    Combines the dataset profile with the *coarse* modeling decisions:
    which forecaster family to use, which estimator to pair with it,
    and the alternative candidates the user could switch to. Detailed
    configuration (lags, metric, intervals, NaN handling, preprocessing)
    is left to `ForecastPlan`.

    Attributes
    ----------
    data_profile : DataProfile
        Profile of the input dataset (independent of the forecasting
        decisions).
    task_type : str
        Forecasting task category implied by the selected forecaster.
        One of `'single_series'`, `'multi_series'`, `'multivariate'`,
        `'statistical'`, `'foundation'`, `'classification'`.
    forecaster : str
        Selected skforecast forecaster class name.
    forecaster_candidates : list
        Ordered list of compatible forecaster class names. The first
        item is the preferred default.
    estimator : str, default None
        Selected scikit-learn compatible estimator name. `None` for
        forecaster families that do not use an external estimator
        (statistical, foundation).
    estimator_candidates : list
        Ordered list of compatible estimator names. Empty when the
        selected forecaster does not use an external estimator.
    series_pacf : list of SeriesPacf
        Per-series PACF-significant lags (the forecaster-invariant lag
        primitive). Empty for statistical and foundation tasks. The
        final lag set is derived in `plan()` by aggregating these
        primitives for the chosen forecaster.
    window_features : list of dict, default None
        Window feature configurations (dicts with keys `'stats'` and
        `'window_size'`). Computed eagerly at profile time as they are
        forecaster-invariant. None when the series is too short or the
        task is statistical/foundation.
    calendar_features : list of str, default None
        Recommended calendar feature names (a subset of those supported
        by `skforecast.preprocessing.CalendarFeatures`). Computed eagerly
        at profile time as they depend only on the index frequency and
        series length. None when the frequency is unknown, the series is
        too short, the frequency has no sub-period seasonality, or the
        task is statistical/foundation. The encoding is chosen later in
        `plan()` based on the resolved estimator.
    explanation : str
        Human-readable explanation of why this forecaster + estimator
        combination was chosen.
    """

    data_profile: DataProfile
    task_type: Literal[
        "single_series",
        "multi_series",
        "multivariate",
        "statistical",
        "foundation",
        "classification",
    ]
    forecaster: str
    forecaster_candidates: list[str] = Field(default_factory=list)
    estimator: str | None = None
    estimator_candidates: list[str] = Field(default_factory=list)
    series_pacf: list[SeriesPacf] = Field(default_factory=list)
    window_features: list[dict] | None = None
    calendar_features: list[str] | None = None
    explanation: str

    def _rich_body(self, console, options):
        yield render_profile(self)
