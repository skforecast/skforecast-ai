# Unit test _missing_values_notices

from types import SimpleNamespace

import pytest

from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _missing_values_notices

from ..fixtures_last_window import (
    plan_h2o_baseline,
    plan_h2o_exog_lgbm,
    plan_h2o_exog_ridge,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    plan_wide_ridge,
    profile_h2o,
    profile_h2o_exog,
    profile_h2o_exog_missing_target,
    profile_h2o_gaps,
    profile_wide,
)


def _leave(owners):
    return (
        f"The missing values of {owners} are data of the user: do not fill "
        f"in, drop or write any of them yourself, in their file or in a copy "
        f"of it, unless they asked for exactly that. Ask before you do."
    )


RUN = (
    " `backtest` checks every test fold before running anything and names "
    "the dates that make it fail: run it before changing the plan or asking "
    "the user about the values."
)
SWITCH = (
    " Without touching the data, switching with `refine_plan` and a new "
    "`create_cv` to an estimator that accepts missing values (such as "
    "'RandomForestRegressor') {does}: if you switch to it, say in your "
    "answer that you changed the estimator and why."
)
TARGET_SCOPE = (
    "avoids the error of a fold predicted from a missing value, not of a fold "
    "that holds one"
)
NO_BACKTEST = (
    " If you forecast without a backtest, say in your answer that the "
    "forecast has no measure of error and why."
)


@pytest.mark.parametrize(
    "plan, data_profile, expected",
    [
        (
            plan_h2o_ridge,
            profile_h2o_gaps,
            _leave("the target") + RUN + SWITCH.format(does=TARGET_SCOPE)
            + NO_BACKTEST,
        ),
        (
            plan_h2o_lgbm,
            profile_h2o_gaps,
            _leave("the target") + RUN + NO_BACKTEST,
        ),
        (
            plan_h2o_baseline,
            profile_h2o_gaps,
            _leave("the target") + RUN + NO_BACKTEST,
        ),
        (
            plan_h2o_exog_ridge,
            profile_h2o_exog,
            _leave("the exogenous columns") + RUN
            + SWITCH.format(
                does="lets the plan predict from the missing exogenous values"
            )
            + NO_BACKTEST,
        ),
        (
            plan_h2o_exog_ridge,
            profile_h2o_exog_missing_target,
            _leave("the target and the exogenous columns") + RUN
            + SWITCH.format(
                does=(
                    "lets the plan predict from the missing exogenous values "
                    "and, for the target, " + TARGET_SCOPE
                )
            )
            + NO_BACKTEST,
        ),
    ],
    ids=[
        "ridge_gap", "lgbm_gap", "baseline_gap", "ridge_exog", "ridge_target_and_exog"
    ],
)
def test_missing_values_notices_output_when_backtest_can_fail_on_them(
    plan, data_profile, expected
):
    """
    Test that a plan whose backtest can fail on missing values gets one
    notice (source 'data') that leaves the values to the user, says that
    `backtest` checks the folds before running (those of the target and of
    the exogenous columns), names the
    estimator of the rules (RandomForestRegressor, for 120 observations)
    only when the plan's cannot use them, with what it does not avoid (V16:
    a missing value inside a test fold fails with any estimator), and asks
    to say when no backtest was run. With LGBMRegressor and the baseline,
    no estimator is offered.
    """
    notices = _missing_values_notices(
        plan, SimpleNamespace(data_profile=data_profile)
    )

    assert notices == [
        ToolNotice(
            source   = "data",
            category = "MissingValuesNotice",
            message  = expected,
            count    = 1,
        )
    ]


@pytest.mark.parametrize(
    "plan, data_profile",
    [
        (plan_h2o_ridge, profile_h2o),
        (plan_h2o_exog_lgbm, profile_h2o_exog),
        (plan_wide_ridge, profile_wide),
    ],
    ids=["clean_data", "lgbm_exog", "several_series"],
)
def test_missing_values_notices_empty_when_the_backtest_cannot_fail_on_them(
    plan, data_profile
):
    """
    Test that there is no notice with data without missing values, with
    missing exogenous values and an estimator that predicts from them, nor
    with several series, whose backtest drops them per series.
    """
    notices = _missing_values_notices(
        plan, SimpleNamespace(data_profile=data_profile)
    )

    assert notices == []
