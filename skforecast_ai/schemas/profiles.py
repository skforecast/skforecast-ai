################################################################################
#                              Profile schemas                                 #
#                                                                              #
# Profile schemas: data description and forecaster-specific analysis           #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import ClassVar, Literal
import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator
from .._display import DisplayMixin, render_profile
from .._validation import validate_frequency
from ._compat import PickleDefaultsMixin
from .explainable import ExplainableResult

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


class DataProfile(PickleDefaultsMixin, BaseModel):
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
    n_observations_display : int
        Task-agnostic observation count for display and summaries: the
        series length for a single series, `span_index_length` otherwise.
    time_zone : str, default None
        Name of the time zone of the dates (`'Europe/Madrid'`, `'UTC'`),
        or None when they have none or it cannot be rebuilt from its name.
        `start_date` is then written as local time, without its UTC
        offset, and the positions and the dates of a cross-validation
        strategy are counted on the local times of the data, which skip or
        repeat an hour at a daylight saving change.
    span_start_date : str, None
        First date of the span of `span_index_length`: `start_date`, or in
        long format the earliest first date of the series.
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
        Inferred pandas frequency string (e.g. `'h'`, `'D'`, `'ME'`). In long
        format, the frequency shared by every series.
    frequency_is_set : bool, default False
        Whether the index already has a frequency set (`index.freq`). False
        when the rows were not in date order.
    index_is_monotonic : bool, default True
        Whether the input was in ascending date order (within each series,
        for long format). Rows out of order are sorted before profiling,
        with a note in `warnings`, so the other fields describe the sorted
        data.
    has_gaps : bool, default False
        Whether the datetime index has missing timestamps within its range
        (in long format, whether any series has them within its own range).
    has_duplicate_timestamps : bool, default False
        Whether some timestamps appear in several identical rows, which the
        generated code drops. Timestamps repeated with different values
        raise a `ValueError` during profiling.
    exog_columns : list
        Names of exogenous predictor columns.
    categorical_exog : list
        Subset of `exog_columns` that are categorical.
    missing_exog : dict
        Mapping of exogenous column name to count of missing values.
        Only columns with at least one missing value are included.
    unused_columns : list, default []
        Columns of the data that are neither the target, the date, the
        series id nor an exogenous variable: left out with `exog_columns`
        of `profile()`, or columns of data passed with a saved profile that
        does not name them. The generated script does not read them.
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
    unused_columns: list[str] = Field(default_factory=list)

    # -- Source --
    data_path: str = "data.csv"

    # -- Train/test split --
    start_date: str | None = None
    time_zone: str | None = None

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

    @field_validator("frequency")
    @classmethod
    def _check_frequency(cls, value: str | None) -> str | None:
        """
        Check that `frequency` is a pandas frequency alias: it is written
        into the generated script, also from a profile loaded from JSON.
        """
        validate_frequency(value)
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

    @property
    def span_start_date(self) -> str | None:
        """
        First date of the span of the data, where `span_index_length`
        starts.

        It is `start_date`, except in long format, where `start_date` is
        the latest first date of the series and the span starts at the
        earliest one (the union index of the series). The earliest is
        taken only when `span_index_length` observations at `frequency`
        run from it to the last date of the series; otherwise (a span
        counted as the longest series, dates that mix time zones) it is
        `start_date`, as before.

        Returns
        -------
        span_start_date : str, None
            First date of the span, or None without dates.
        """
        if self.data_format != "long" or self.frequency is None:
            return self.start_date
        infos = list(self.series_lengths.values())
        try:
            starts = [pd.Timestamp(info.start) for info in infos if info.start]
            ends = [pd.Timestamp(info.end) for info in infos if info.end]
            if not starts or not ends:
                return self.start_date
            start, end = min(starts), max(ends)
            # The dates of the series carry the UTC offset of their day,
            # which differs across a daylight saving change: the span is
            # rebuilt in the zone and written as local time, as
            # `start_date` is.
            if self.time_zone is not None and start.tzinfo is not None:
                start = start.tz_convert(self.time_zone)
                end = end.tz_convert(self.time_zone)
            span = pd.date_range(start=start, end=end, freq=self.frequency)
            if self.time_zone is not None and start.tzinfo is not None:
                start = start.tz_localize(None)
        except (ValueError, TypeError):
            return self.start_date
        if len(span) != self.span_index_length:
            return self.start_date
        # Written as `start_date` is: the date alone at midnight.
        if start == start.normalize():
            return str(start.date())
        return str(start)

    @property
    def n_observations_display(self) -> int:
        """
        Task-agnostic observation count for display and summaries.

        Returns the series length for single-series data and the union
        span (`span_index_length`) for multi-series data.

        Returns
        -------
        n_observations : int
            Representative observation count for display.
        """
        if len(self.series_lengths) == 1:
            return next(iter(self.series_lengths.values())).length
        return self.span_index_length


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


class ForecastingProfile(
    PickleDefaultsMixin, DisplayMixin, ExplainableResult, BaseModel
):
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
        `'statistical'`, `'foundation'`.
    forecaster : str
        Selected skforecast forecaster class name.
    forecaster_candidates : list
        Ordered list of compatible forecaster class names. The first
        item is the preferred default.
    estimator : str, default None
        Selected estimator: a scikit-learn compatible estimator name,
        `'Arima'` for statistical tasks, or the Hugging Face model ID of
        the foundation model for foundation tasks. `None` for the
        baseline, which has no estimator.
    estimator_candidates : list
        Ordered list of compatible estimator names. Empty for the
        baseline.
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

    _explanation_title: ClassVar[str] = "Profile Explanation"

    data_profile: DataProfile
    task_type: Literal[
        "single_series",
        "multi_series",
        "multivariate",
        "statistical",
        "foundation",
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

    def _build_llm_context(self, *, send_data: bool, for_describe: bool = False):
        """
        Describe the profile to the LLM.

        Lets a profile be passed to `ForecastingAssistant.ask()` as
        `context` on its own, before any plan exists.

        Parameters
        ----------
        send_data : bool
            Whether raw data values may be included. Has no effect here:
            a profile holds summary statistics only. The parameter is part
            of the `ExplainableResult` interface.
        for_describe : bool, default False
            Whether the context is built for `describe()`, which leaves out
            the sentences addressed to the LLM of `ask()`.

        Returns
        -------
        context : LLMContext
            Context block covering the dataset and the profile decisions.
        """

        # Deferred imports: `results` and `llm.context` import this module.
        from ..llm.context import build_context_message
        from .results import LLMContext

        return LLMContext(
            text                = build_context_message(
                                      profile      = self,
                                      for_describe = for_describe,
                                  ),
            profile             = self,
            sends_result_values = False,
        )
