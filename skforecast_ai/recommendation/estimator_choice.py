################################################################################
#                     Recommendations: estimator choice                        #
#                                                                              #
# Whether a plan runs the estimator that the rules recommend for it            #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import NamedTuple
from .._constants import AUTOREG_FORECASTERS, NAN_TOLERANT_ESTIMATORS
from ..schemas import DataProfile, ForecastPlan
from .forecaster_selection import (
    estimator_n_observations,
    select_estimator_and_candidates,
)
from .missing_values import select_nan_tolerant_estimator


class EstimatorChange(NamedTuple):
    """
    Estimator of a plan, chosen by the user, that is not the one the rules
    recommend for its forecaster (see `estimator_change`).

    Attributes
    ----------
    estimator : str
        Estimator of the plan.
    recommended : str
        Estimator the rules choose for the forecaster of the plan and the
        size of the data.
    forecaster : str
        Forecaster of the plan.
    missing_values : bool
        Whether the estimator is the one that accepts missing values that
        the advice on the missing values of the data names
        (`select_nan_tolerant_estimator`), the data have missing values and
        the recommended estimator does not accept them.
    """

    estimator: str
    recommended: str
    forecaster: str
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
    Find whether a plan runs an estimator that the user chose instead of the
    one the rules recommend for its forecaster (see
    `recommended_estimator`).

    The user chose it when the plan records it in
    `ForecastPlan.overridden_fields`: passed to `plan()` or to
    `refine_plan()`, or listed in the `candidates` of `compare()`. The plan
    of a candidate of `compare()` without `candidates` does not record it:
    a comparison among candidates of the rules chose it, and measured it.

    Parameters
    ----------
    plan : ForecastPlan
        Plan that runs.
    profile : DataProfile
        Profile of the data.

    Returns
    -------
    change : EstimatorChange, None
        None when the estimator is the one of the rules or was not chosen
        by the user, and for the forecasters without an estimator to
        choose.
    """

    recommended = recommended_estimator(plan, profile)
    if (
        recommended is None
        or plan.estimator in (None, recommended)
        or "estimator" not in plan.overridden_fields
    ):
        return None
    tolerant = select_nan_tolerant_estimator(
        task_type      = plan.task_type,
        n_observations = estimator_n_observations(plan.task_type, profile),
    )

    return EstimatorChange(
        estimator      = plan.estimator,
        recommended    = recommended,
        forecaster     = plan.forecaster,
        missing_values = (
            plan.estimator == tolerant
            and recommended not in NAN_TOLERANT_ESTIMATORS
            and _has_missing_values(plan, profile)
        ),
    )
