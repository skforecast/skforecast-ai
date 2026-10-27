# Unit test check_default_folds_fit

import re

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.recommendation.backtesting import check_default_folds_fit

from .fixtures_recommendation import forecasting_profile_h2o, window_12_kwargs


@pytest.mark.parametrize(
    "plan_arguments, max_steps",
    [
        ({"steps": 102, **window_12_kwargs}, 95),
        ({"steps": 150, **window_12_kwargs, "forecaster": "ForecasterDirect"}, 64),
        ({"steps": 102, "forecaster": "ForecasterStats"}, 101),
    ],
    ids=["recursive", "direct", "stats"],
)
def test_check_default_folds_fit_InvalidInputError_when_two_folds_do_not_fit(
    plan_arguments, max_steps
):
    """
    Test that a horizon of half the 204 observations or more, which leaves
    no room for two folds after the default `initial_train_size`, is
    `insufficient_data` on the plan, with the longest horizon whose two
    folds leave the first training window the forecaster needs (more than
    its window of 12; for a direct forecaster, the window plus `steps`;
    one observation for ForecasterStats), instead of an error on an
    `initial_train_size` that was not passed (V31).
    """
    plan = ForecastingAssistant().plan(forecasting_profile_h2o, **plan_arguments)
    steps = plan_arguments["steps"]

    err_msg = re.escape(
        f"The data has 204 observations, too few for a backtest of {steps} "
        f"steps: its two folds take {2 * steps}, and at least one observation "
        f"is needed before them to train on."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        check_default_folds_fit(plan, forecasting_profile_h2o.data_profile)

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "plan"
    assert exc_info.value.hint == (
        f"Keeping the rest of the plan, at most {max_steps} `steps` leave two "
        f"folds and the first training window it needs: make a plan with that "
        f"horizon, or use more data. To evaluate a single window, the last "
        f"`steps` observations, use `forecast` with `test_size` instead: one "
        f"hold-out, not a backtest."
    )


def test_check_default_folds_fit_output_when_two_folds_fit():
    """
    Test that nothing is raised when one observation is left before two
    folds (101 steps on 204 observations): the default bound applies.
    """
    plan = ForecastingAssistant().plan(forecasting_profile_h2o, steps=101, **window_12_kwargs)

    assert check_default_folds_fit(plan, forecasting_profile_h2o.data_profile) is None
