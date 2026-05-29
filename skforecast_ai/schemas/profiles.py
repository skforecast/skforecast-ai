"""Profile schemas: data description and forecaster-specific analysis."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DataProfile(BaseModel):
    """
    Profile of the input time series dataset.

    Attributes
    ----------
    data_format : str, default 'single'
        Layout of the dataset. One of `'single'`, `'wide'`, `'long'`.
    n_series : int
        Number of individual time series.
    n_observations : int
        Number of observations per series. For single and wide formats
        this equals `len(data)`. For long format this is the length
        of the shortest series (the limiting factor for lags and
        backtesting decisions).
    series_lengths : dict, default None
        Mapping of series name to number of observations. Only populated
        for multi-series datasets (wide or long). None for single series.
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
    end_train : str, default None
        Last datetime (inclusive) of the training set as a string
        (e.g. `'2005-03-01'`). Computed during profiling at the 80%
        mark of the datetime index. Used by code generation to emit a
        date-based train/test split.
    warnings : list
        Human-readable warnings generated during profiling.
    """

    # -- Structure / Format --
    data_format: Literal["single", "wide", "long"] = "single"
    n_series: int
    n_observations: int
    series_lengths: dict[str, int] | None = None

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
    end_train: str | None = None

    # -- Diagnostics --
    warnings: list[str] = Field(default_factory=list)


class ForecastingAnalysis(BaseModel):
    """
    Forecaster-specific analysis computed after selecting the forecaster type.

    Attributes
    ----------
    effective_n_observations : int
        Number of observations to use for lag/backtesting decisions.
        For multi-series, this is `min_series_length`; for single
        series, this equals `n_observations`.
    min_series_length : int, default None
        Length of the shortest series (multi-series only).
    max_series_length : int, default None
        Length of the longest series (multi-series only).
    series_length_ratio : float, default None
        Ratio of max to min series length (multi-series only).
    short_series : list, default None
        Names of series with fewer than 50 observations (multi-series
        only). Useful for targeted warnings and code generation filters.
    target_has_trend : bool, default None
        Whether the target exhibits a monotonic trend (single ML only).
    target_variance : float, default None
        Variance of the target column (single ML only).
    target_series : pandas Series, default None
        Target series (NaN-free) used for data-aware lag selection via
        PACF analysis. Excluded from serialization.
    viable_context_length : int, default None
        Usable context length for foundation models.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    effective_n_observations: int
    min_series_length: int | None = None
    max_series_length: int | None = None
    series_length_ratio: float | None = None
    short_series: list[str] | None = None
    target_has_trend: bool | None = None
    target_variance: float | None = None
    target_series: Any = Field(default=None, exclude=True)
    viable_context_length: int | None = None


class ForecastingProfile(BaseModel):
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
        Selected scikit-learn compatible estimator name. `None` for
        forecaster families that do not use an external estimator
        (statistical, foundation).
    estimator_candidates : list
        Ordered list of compatible estimator names. Empty when the
        selected forecaster does not use an external estimator.
    analysis_context : ForecastingAnalysis
        Forecasting-specific analysis (per-series stats, viable context
        length, etc.).
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
    ]
    forecaster: str
    forecaster_candidates: list[str] = Field(default_factory=list)
    estimator: str | None = None
    estimator_candidates: list[str] = Field(default_factory=list)
    analysis_context: ForecastingAnalysis
    explanation: str
