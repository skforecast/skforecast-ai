################################################################################
#                    Recommendations: forecaster_selection                     #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Literal
from .._constants import (
    DEFAULT_FOUNDATION_MODEL_ID,
    FORECASTER_TASK_TYPES,
    MAX_STATS_SEASONAL_PERIOD,
)
from ..schemas import DataProfile
from ..exceptions import InvalidInputError
from .autoregressive import arima_seasonal_period


def _auto_arima_is_practical(frequency: str | None) -> bool:
    """
    Check whether an Auto-ARIMA search is affordable for a frequency.

    The search fits many seasonal state-space models, and its cost grows
    with the seasonal period, so data with a long one (hourly or finer,
    weekly) makes it impractical. A frequency that is not in
    `FREQUENCY_TO_SEASONAL_PERIOD` never has a long one
    (`MAX_UNTABULATED_ARIMA_PERIOD`).

    Parameters
    ----------
    frequency : str, default None
        Inferred pandas frequency string.

    Returns
    -------
    is_practical : bool
        `False` when the seasonal period of Auto-ARIMA for `frequency`
        (`arima_seasonal_period`) reaches `MAX_STATS_SEASONAL_PERIOD`,
        `True` otherwise (including frequencies without one).
    """
    m = arima_seasonal_period(frequency)

    return m is None or m < MAX_STATS_SEASONAL_PERIOD


def select_forecaster_and_candidates(
    profile: DataProfile
) -> tuple[str, list[str]]:
    """
    Select the preferred forecaster and ordered compatible candidates.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    preferred : str
        Name of the recommended forecaster class.
    candidates : list of str
        Ordered list of compatible forecaster class names. First item matches `preferred`.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md`.

    `ForecasterStats` is only offered as a candidate when the seasonal
    period implied by the frequency keeps the Auto-ARIMA search
    affordable. It can still be selected explicitly in `plan()`.

    `ForecasterDirectMultiVariate` is only offered for several series in
    wide format: `plan()` rejects it on long-format data.
    """
    
    if profile.n_series > 1:
        
        preferred = "ForecasterRecursiveMultiSeries"
        candidates = [
            "ForecasterRecursiveMultiSeries",
            "ForecasterDirectMultiVariate",
            "ForecasterFoundation",
        ]
        # `plan()` rejects ForecasterDirectMultiVariate on long-format data
        # with several series, whose generated script always failed.
        if profile.data_format == "long":
            candidates.remove("ForecasterDirectMultiVariate")

    else:
        
        preferred = "ForecasterRecursive"
        candidates = [
            "ForecasterRecursive",
            "ForecasterDirect",
            "ForecasterFoundation",
        ]
        if _auto_arima_is_practical(profile.frequency):
            candidates.append("ForecasterStats")

    return preferred, candidates


def select_task_type_from_forecaster(
    forecaster: str,
) -> Literal[
    "single_series",
    "multi_series",
    "multivariate",
    "statistical",
    "foundation",
    "baseline",
]:
    """
    Resolve the task type implied by a selected forecaster.

    Parameters
    ----------
    forecaster : str
        Name of the selected skforecast forecaster class.

    Returns
    -------
    task_type : str
        Forecasting task category associated with `forecaster`.
    """
    if forecaster not in FORECASTER_TASK_TYPES:
        raise InvalidInputError(
            f"Unknown forecaster '{forecaster}'.",
            field = "forecaster",
        )

    return FORECASTER_TASK_TYPES[forecaster]


def estimator_n_observations(
    task_type: str,
    data_profile: DataProfile,
) -> int:
    """
    Number of observations that sizes the estimator of a task type.

    Parameters
    ----------
    task_type : str
        Forecasting task category.
    data_profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    n_observations : int
        `span_index_length` for the `'multivariate'` task,
        `n_total_observations` otherwise.

    Notes
    -----
    `ForecasterDirectMultiVariate` trains one model per step on one row
    per date that the series share, so the observations pooled across the
    series overstate its training data: a gradient boosting model chosen
    for them finds no split and predicts a constant.
    `ForecasterRecursiveMultiSeries` trains one model on the series
    pooled, and a single series has both counts equal.
    """

    if task_type == "multivariate":
        return data_profile.span_index_length

    return data_profile.n_total_observations


def select_estimator_and_candidates(
    task_type: str,
    n_observations: int,
) -> tuple[str | None, list[str]]:
    """
    Select the preferred estimator and ordered compatible candidates.

    Parameters
    ----------
    task_type : str
        Forecasting task category.
    n_observations : int
        Number of observations that sizes the estimator, see
        `estimator_n_observations`.

    Returns
    -------
    preferred : str, None
        Name of the recommended estimator class. None for the baseline,
        which has no estimator.
    candidates : list of str
        Ordered list of compatible estimator class names.
        The first item matches `preferred`. Empty for the baseline.

    Notes
    -----
    Source: `skforecast_ai/skills/forecasting-single-series/SKILL.md`.

    For foundation tasks the estimator is the Hugging Face model ID of the
    foundation model, and the default is `'autogluon/chronos-2-small'`. No
    rule ranks the foundation models against each other; any other model
    supported by skforecast is chosen by passing its ID as `estimator`.
    """

    if task_type == "statistical":
        return "Arima", ["Arima"]
    
    if task_type == "foundation":
        return DEFAULT_FOUNDATION_MODEL_ID, [DEFAULT_FOUNDATION_MODEL_ID]

    if task_type == "baseline":
        return None, []

    if n_observations < 250:
        return "Ridge", ["Ridge", "RandomForestRegressor", "LGBMRegressor"]
    
    preferred = "LGBMRegressor"
    candidates = [
        "LGBMRegressor",
        "XGBRegressor",
        "Ridge",
    ]

    return preferred, candidates
