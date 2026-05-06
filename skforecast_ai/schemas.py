"""Pydantic schemas for skforecast-ai data contracts."""

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
        this equals ``len(data)``. For long format this is the length
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
        ``'min'``, ``'max'``, ``'mean'``, ``'std'`` computed on non-NaN
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
        Whether the index already has a frequency set (``index.freq``).
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

    # -- Diagnostics --
    warnings: list[str] = Field(default_factory=list)


class AnalysisContext(BaseModel):
    """
    Forecaster-specific analysis computed after selecting the forecaster type.

    Attributes
    ----------
    effective_n_observations : int
        Number of observations to use for lag/backtesting decisions.
        For multi-series, this is ``min_series_length``; for single
        series, this equals ``n_observations``.
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
    viable_context_length : int, default None
        Usable context length for foundation models.
    """

    effective_n_observations: int
    min_series_length: int | None = None
    max_series_length: int | None = None
    series_length_ratio: float | None = None
    short_series: list[str] | None = None
    target_has_trend: bool | None = None
    target_variance: float | None = None
    viable_context_length: int | None = None


class ForecasterProfile(BaseModel):
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
        `'statistical'`, `'foundation'`, `'classification'`, `'baseline'`.
    forecaster : str
        Selected skforecast forecaster class name.
    forecaster_candidates : list
        Ordered list of compatible forecaster class names. The first
        item is the preferred default.
    estimator : str, default None
        Selected scikit-learn compatible estimator name. `None` for
        forecaster families that do not use an external estimator
        (statistical, foundation, baseline).
    estimator_candidates : list
        Ordered list of compatible estimator names. Empty when the
        selected forecaster does not use an external estimator.
    analysis_context : AnalysisContext
        Forecaster-specific analysis (per-series stats, viable context
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
        "classification",
        "baseline",
    ]
    forecaster: str
    forecaster_candidates: list[str] = Field(default_factory=list)
    estimator: str | None = None
    estimator_candidates: list[str] = Field(default_factory=list)
    analysis_context: AnalysisContext
    explanation: str


class PreprocessingStep(BaseModel):
    """
    A preprocessing action required before forecasting.

    Attributes
    ----------
    action : str
        Identifier for the preprocessing operation (e.g.
        `'sort_index'`, `'asfreq'`, `'reshape_long_to_dict'`).
    reason : str
        Human-readable explanation of why this step is needed.
    code_snippet : str
        Python code template that implements this step. May contain
        format placeholders (e.g. ``{frequency}``, ``{date_column}``).
    blocking : bool, default True
        Whether skforecast will fail without this step. Non-blocking
        steps are recommended but optional.
    """

    action: str
    reason: str
    code_snippet: str
    blocking: bool = True


class ForecastPlan(BaseModel):
    """
    Detailed forecasting plan produced from a `ForecasterProfile`.

    Carries every concrete decision needed to fit, evaluate and predict:
    lag structure, metric, backtesting strategy, prediction intervals,
    NaN handling, exogenous usage and preprocessing steps.

    Attributes
    ----------
    task_type : str
        Forecasting task category (mirrored from the source
        `ForecasterProfile`). One of `'single_series'`,
        `'multi_series'`, `'multivariate'`, `'statistical'`,
        `'foundation'`, `'classification'`, `'baseline'`.
    forecaster : str
        Name of the skforecast forecaster class.
    estimator : str, default None
        Name of the scikit-learn compatible estimator.
    steps : int
        Number of steps ahead to predict. Must be greater than 0.
    frequency : str, default None
        Pandas frequency string for the series.
    lags : int, list, default None
        Lag structure to use as predictors.
    metric : str
        Name of the evaluation metric.
    backtesting_strategy : str
        Name of the backtesting fold strategy.
    interval_method : str, default None
        Method for prediction intervals. One of `'bootstrapping'`,
        `'conformal'`.
    dropna_from_series : bool, default None
        Whether to drop NaN rows from training matrices. `None` when
        not applicable (statistical, foundation). `True` when the
        estimator does not support NaN. `False` when NaN-tolerant.
    use_exog : bool, default False
        Whether to include exogenous variables.
    preprocessing_steps : list
        Ordered list of preprocessing steps required before forecasting.
    data_requirements : list
        Conditions the data must meet before training.
    warnings : list
        Human-readable warnings about the plan.
    explanation : str
        Explanation of the plan-level decisions.
    """

    task_type: Literal[
        "single_series",
        "multi_series",
        "multivariate",
        "statistical",
        "foundation",
        "classification",
        "baseline",
    ]
    forecaster: str
    estimator: str | None = None
    steps: int = Field(gt=0)
    frequency: str | None = None
    lags: int | list[int] | None = None
    metric: str
    backtesting_strategy: str
    interval_method: Literal["bootstrapping", "conformal"] | None = None
    dropna_from_series: bool | None = None
    use_exog: bool = False
    preprocessing_steps: list[PreprocessingStep] = Field(default_factory=list)
    data_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation: str


class GenerateResult(BaseModel):
    """
    Result of the `generate_code` workflow.

    Attributes
    ----------
    forecaster_profile : ForecasterProfile
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan.
    code : str
        Generated Python script.
    """

    forecaster_profile: ForecasterProfile
    plan: ForecastPlan
    code: str


class AskResult(BaseModel):
    """
    Result of the `ask` workflow (requires LLM).

    Attributes
    ----------
    forecaster_profile : ForecasterProfile, default None
        Profile of the input dataset and high-level modeling decisions,
        if data was provided.
    plan : ForecastPlan, default None
        Detailed forecasting plan, if the agent produced one.
    code : str, default None
        Generated Python script, if the agent produced one.
    explanation : str
        LLM-generated explanation or response.
    """

    forecaster_profile: ForecasterProfile | None = None
    plan: ForecastPlan | None = None
    code: str | None = None
    explanation: str


class RunResult(BaseModel):
    """
    Result of the `forecast` workflow (executes the pipeline end-to-end).

    Attributes
    ----------
    forecaster_profile : ForecasterProfile
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan that was executed.
    code : str
        Generated Python script equivalent to the execution.
    metric_value : float
        Backtesting metric value.
    metric_name : str
        Name of the metric used for evaluation.
    predictions : pandas DataFrame
        Forecasted values for the requested steps.
    intervals : pandas DataFrame, default None
        Prediction intervals or quantile predictions when available.
    warnings : list
        Warnings generated during validation and execution.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    forecaster_profile: ForecasterProfile
    plan: ForecastPlan
    code: str
    metric_value: float
    metric_name: str
    predictions: Any  # pd.DataFrame
    intervals: Any = None  # pd.DataFrame | None
    warnings: list[str] = Field(default_factory=list)
