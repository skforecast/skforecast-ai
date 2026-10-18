################################################################################
#                     Recommendations: estimator choice                        #
#                                                                              #
# Whether a plan runs the estimator that the rules recommend for it            #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
from typing import NamedTuple
from .._constants import AUTOREG_FORECASTERS, NAN_TOLERANT_ESTIMATORS
from ..exceptions import EstimatorNotRecommendedWarning
from ..schemas import DataProfile, ForecastPlan
from .forecaster_selection import (
    estimator_n_observations,
    select_estimator_and_candidates,
)
from .missing_values import select_nan_tolerant_estimator


class EstimatorChange(NamedTuple):
    """
    Estimator of a plan that is not the one the rules recommend for its
    forecaster (see `estimator_change`).

    Attributes
    ----------
    estimator : str
        Estimator of the plan.
    recommended : str
        Estimator the rules choose for the forecaster of the plan and the
        size of the data.
    forecaster : str
        Forecaster of the plan.
    chosen_by_user : bool
        Whether the plan records the estimator as a decision of the user
        (`ForecastPlan.overridden_fields`): passed to `plan()` or to
        `refine_plan()`, or listed in the `candidates` of `compare()`.
    missing_values : bool
        Whether the estimator is the one that accepts missing values that
        the advice on the missing values of the data names
        (`select_nan_tolerant_estimator`), the data have missing values and
        the recommended estimator does not accept them.
    """

    estimator: str
    recommended: str
    forecaster: str
    chosen_by_user: bool
    missing_values: bool


def recommended_estimator(
    plan: ForecastPlan,
    profile: DataProfile,
) -> str | None:
    """
    Estimator the rules of `plan()` choose for the forecaster of a plan.

    It is the one of the task type of the plan, not of the profile: the
    estimator of a `ForecasterDirectMultiVariate` plan is sized with the
    dates the series share (see `estimator_n_observations`), so it can
    differ from the one the profile recommends for
    `ForecasterRecursiveMultiSeries`.

    Parameters
    ----------
    plan : ForecastPlan
        Plan whose forecaster the estimator is for.
    profile : DataProfile
        Profile of the data.

    Returns
    -------
    estimator : str, None
        Name of the estimator class. None for the forecasters without a
        machine learning estimator to choose: `ForecasterStats`,
        `ForecasterFoundation` and the baseline.
    """

    if plan.forecaster not in AUTOREG_FORECASTERS:
        return None
    estimator, _ = select_estimator_and_candidates(
        task_type      = plan.task_type,
        n_observations = estimator_n_observations(plan.task_type, profile),
    )

    return estimator


def _has_missing_values(plan: ForecastPlan, profile: DataProfile) -> bool:
    """
    Whether the data of a plan have missing values that its estimator reads:
    in the target (missing timestamps included) or in the exogenous columns
    the plan uses.
    """

    if profile.has_gaps or any(profile.missing_target.values()):
        return True

    return plan.use_exog and any(
        profile.missing_exog.get(column) for column in profile.exog_columns
    )


def estimator_change(
    plan: ForecastPlan,
    profile: DataProfile,
) -> EstimatorChange | None:
    """
    Find whether a plan runs an estimator other than the one the rules
    recommend for its forecaster (see `recommended_estimator`), and who
    chose it.

    Parameters
    ----------
    plan : ForecastPlan
        Plan that runs.
    profile : DataProfile
        Profile of the data.

    Returns
    -------
    change : EstimatorChange, None
        None when the estimator is the one of the rules, and for the
        forecasters without an estimator to choose.
    """

    recommended = recommended_estimator(plan, profile)
    if recommended is None or plan.estimator in (None, recommended):
        return None
    tolerant = select_nan_tolerant_estimator(
        task_type      = plan.task_type,
        n_observations = estimator_n_observations(plan.task_type, profile),
    )

    return EstimatorChange(
        estimator      = plan.estimator,
        recommended    = recommended,
        forecaster     = plan.forecaster,
        chosen_by_user = "estimator" in plan.overridden_fields,
        missing_values = (
            plan.estimator == tolerant
            and recommended not in NAN_TOLERANT_ESTIMATORS
            and _has_missing_values(plan, profile)
        ),
    )


def estimator_change_message(change: EstimatorChange) -> str:
    """
    Text of the `EstimatorNotRecommendedWarning` of an estimator change.

    Parameters
    ----------
    change : EstimatorChange
        Estimator change found by `estimator_change`.

    Returns
    -------
    message : str
        The estimator of the plan, who chose it and the estimator the rules
        recommend.
    """

    origin = (
        "chosen by the user" if change.chosen_by_user else
        "not recorded in `overridden_fields`: a candidate of `compare()`, or a "
        "plan edited by hand"
    )
    message = (
        f"The estimator of the plan, {change.estimator!r} ({origin}), is not "
        f"the one the rules recommend for {change.forecaster} on these data: "
        f"{change.recommended!r}."
    )
    if change.missing_values:
        message += (
            f" {change.estimator!r} is the estimator that accepts missing "
            f"values that the advice on the missing values of the data names."
        )

    return message


def warn_estimator_not_recommended(
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """
    Warn with `EstimatorNotRecommendedWarning` when a plan runs an estimator
    other than the one the rules recommend for its forecaster (see
    `estimator_change`).

    Parameters
    ----------
    plan : ForecastPlan
        Plan that runs.
    profile : DataProfile
        Profile of the data.

    Returns
    -------
    None
    """

    change = estimator_change(plan, profile)
    if change is not None:
        warnings.warn(
            estimator_change_message(change),
            EstimatorNotRecommendedWarning,
            stacklevel=3,
        )
