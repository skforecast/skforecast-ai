# Unit test _missing_values_notices

from types import SimpleNamespace

from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _missing_values_notices

from ..fixtures_last_window import (
    plan_h2o_baseline,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    profile_h2o,
    profile_h2o_gaps,
)

LEAVE = (
    "The missing values of the target are data of the user: do not fill in, "
    "drop or write any of them yourself, in their file or in a copy of it, "
    "unless they asked for exactly that. Ask before you do."
)
ESTIMATOR = (
    " Without touching the data, an estimator that accepts missing values "
    "(such as 'LGBMRegressor', with `refine_plan` and a new `create_cv`) lets "
    "`backtest` run on every fold: if you switch to it, say in your answer "
    "that you changed the estimator and why."
)
NO_BACKTEST = (
    " If you forecast without a backtest, say in your answer that the "
    "forecast has no measure of error and why."
)


def test_missing_values_notices_estimator_that_cannot_predict_from_a_gap():
    """
    Test that a plan whose estimator cannot predict from a missing value, on
    data with missing timestamps, gets one notice (source 'data') that
    leaves the values to the user, names the estimator that avoids the
    error and asks to say it, and to say when no backtest was run.
    """
    notices = _missing_values_notices(
        plan_h2o_ridge, SimpleNamespace(data_profile=profile_h2o_gaps)
    )

    assert notices == [
        ToolNotice(
            source   = "data",
            category = "MissingValuesNotice",
            message  = LEAVE + ESTIMATOR + NO_BACKTEST,
            count    = 1,
        )
    ]


def test_missing_values_notices_baseline_has_no_estimator_to_switch_to():
    """
    Test that the notice of ForecasterEquivalentDate, which no estimator
    saves from a missing value, does not name one.
    """
    notices = _missing_values_notices(
        plan_h2o_baseline, SimpleNamespace(data_profile=profile_h2o_gaps)
    )

    assert [notice.message for notice in notices] == [LEAVE + NO_BACKTEST]


def test_missing_values_notices_empty_when_the_backtest_cannot_fail_on_them():
    """
    Test that there is no notice with an estimator that accepts missing
    values nor with data without them.
    """
    gaps = SimpleNamespace(data_profile=profile_h2o_gaps)
    clean = SimpleNamespace(data_profile=profile_h2o)

    assert _missing_values_notices(plan_h2o_lgbm, gaps) == []
    assert _missing_values_notices(plan_h2o_ridge, clean) == []
