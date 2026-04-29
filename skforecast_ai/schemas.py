"""Pydantic schemas for skforecast-ai data contracts."""

from typing import Literal

from pydantic import BaseModel, Field


class DataProfile(BaseModel):
    """
    Profile of the input time series dataset.

    Attributes
    ----------
    n_observations : int
        Total number of observations in the dataset.
    n_series : int
        Number of individual time series.
    index_type : str
        Type of the DataFrame index. One of `'datetime'`, `'range'`,
        `'other'`.
    frequency : str, default None
        Inferred pandas frequency string (e.g. `'h'`, `'D'`, `'ME'`).
    target : str
        Name of the target column.
    date_column : str, default None
        Name of the column containing timestamps.
    series_id_column : str, default None
        Name of the column identifying individual series.
    exog_columns : list
        Names of exogenous predictor columns.
    categorical_exog : list
        Subset of `exog_columns` that are categorical.
    missing_values : dict
        Mapping of column name to count of missing values.
    inferred_seasonalities : list
        Detected seasonal periods (in number of observations).
    warnings : list
        Human-readable warnings generated during profiling.
    """

    n_observations: int
    n_series: int
    index_type: Literal["datetime", "range", "other"]
    frequency: str | None = None
    target: str
    date_column: str | None = None
    series_id_column: str | None = None
    exog_columns: list[str] = Field(default_factory=list)
    categorical_exog: list[str] = Field(default_factory=list)
    missing_values: dict[str, int] = Field(default_factory=dict)
    inferred_seasonalities: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ForecastPlan(BaseModel):
    """
    Recommended forecasting plan produced by the recommendation engine.

    Attributes
    ----------
    task_type : str
        Forecasting task category. One of `'single_series'`,
        `'multi_series'`, `'multivariate'`, `'statistical'`,
        `'foundation'`, `'classification'`, `'baseline'`.
    forecaster : str
        Name of the skforecast forecaster class.
    estimator : str, default None
        Name of the scikit-learn compatible estimator.
    horizon : int
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
    use_exog : bool, default False
        Whether to include exogenous variables.
    data_requirements : list
        Conditions the data must meet before training.
    warnings : list
        Human-readable warnings about the plan.
    rationale : str
        Explanation of why this plan was chosen.
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
    horizon: int = Field(gt=0)
    frequency: str | None = None
    lags: int | list[int] | None = None
    metric: str
    backtesting_strategy: str
    interval_method: Literal["bootstrapping", "conformal"] | None = None
    use_exog: bool = False
    data_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rationale: str
