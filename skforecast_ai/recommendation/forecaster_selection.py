################################################################################
#                    Recommendations: forecaster_selection                     #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Literal
from .._constants import (
    FORECASTER_TASK_TYPES,
    FREQUENCY_TO_SEASONAL_PERIOD,
    MAX_STATS_SEASONAL_PERIOD,
)
from ..schemas import DataProfile


def _auto_arima_is_practical(frequency: str | None) -> bool:
    """
    Check whether an Auto-ARIMA search is affordable for a frequency.

    The search fits many seasonal state-space models, and its cost grows
    with the seasonal period, so high-frequency data (hourly or finer,
    weekly) makes it impractical.

    Parameters
    ----------
    frequency : str, default None
        Inferred pandas frequency string.

    Returns
    -------
    is_practical : bool
        `False` when the seasonal period implied by `frequency` reaches
        `MAX_STATS_SEASONAL_PERIOD`, `True` otherwise (including unknown
        frequencies).
    """
    if frequency is None:
        return True

    m = FREQUENCY_TO_SEASONAL_PERIOD.get(frequency)

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
    """
    
    if profile.n_series > 1:
        
        preferred = "ForecasterRecursiveMultiSeries"
        candidates = [
            "ForecasterRecursiveMultiSeries",
            "ForecasterDirectMultiVariate"
        ]            

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
        raise ValueError(f"Unknown forecaster '{forecaster}'.")

    return FORECASTER_TASK_TYPES[forecaster]


def select_estimator_and_candidates(
    task_type: str,
    n_observations: int,
) -> tuple[str, list[str]]:
    """
    Select the preferred estimator and ordered compatible candidates.

    Parameters
    ----------
    task_type : str
        Forecasting task category.
    n_observations : int
        Number of observations in the dataset.

    Returns
    -------
    preferred : str
        Name of the recommended estimator class.
    candidates : list of str
        Ordered list of compatible estimator class names.
        The first item matches `preferred`.

    Notes
    -----
    Source: `skforecast_ai/skills/forecasting-single-series/SKILL.md`.
    """

    if task_type == "statistical":
        return "Arima", ["Arima"]
    
    if task_type == "foundation":
        return "Chronos-2", ["Chronos-2"]

    if n_observations < 250:
        return "Ridge", ["Ridge", "RandomForestRegressor", "LGBMRegressor"]
    
    preferred = "LGBMRegressor"
    candidates = [
        "LGBMRegressor",
        "XGBRegressor",
        "Ridge",
    ]

    return preferred, candidates
