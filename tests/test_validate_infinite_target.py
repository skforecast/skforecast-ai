# Unit test validate_infinite_target

import re

import numpy as np
import pytest

from skforecast_ai._last_window import validate_infinite_target
from skforecast_ai.exceptions import InvalidInputError

from tests.fixtures_last_window import (
    data_long,
    data_single,
    data_wide,
    plan_long_foundation,
    plan_long_ridge,
    plan_single_baseline,
    plan_single_ridge,
    plans_single_without_lags,
    profile_long,
    profile_single,
    profile_wide,
    plan_wide_ridge,
    with_infinite,
    with_missing,
)

_HINT = "Replace the infinite values of the target, for example with NaN."


@pytest.mark.parametrize("prediction", [True, False], ids=["prediction", "evaluation"])
@pytest.mark.parametrize(
    "plan, forecaster",
    [
        (plan_single_ridge, "ForecasterRecursive"),
        (plans_single_without_lags["stats"], "ForecasterStats"),
    ],
    ids=["ridge", "stats"],
)
def test_validate_infinite_target_InvalidInputError_when_trained_forecaster(
    plan, forecaster, prediction
):
    """
    Test that an infinite value of the target raises for a forecaster that is
    trained, whatever the mode and the position of the value in the series.
    """
    data = with_infinite(data_single, [30, 10])

    err_msg = re.escape(
        "The target has infinite values (2 value(s), such as '2023-01-31', "
        f"'2023-02-20'). {forecaster} cannot be trained on them: replace them."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_infinite_target(data, profile_single, plan, prediction)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == _HINT


def test_validate_infinite_target_InvalidInputError_when_negative_infinity():
    """
    Test that negative infinity is rejected like positive infinity.
    """
    data = data_single.copy()
    data.loc[0, "y"] = -np.inf

    err_msg = re.escape(
        "The target has infinite values (1 value(s), such as '2023-01-01'). "
        "ForecasterRecursive cannot be trained on them: replace them."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_infinite_target(data, profile_single, plan_single_ridge, True)


@pytest.mark.parametrize(
    "data, profile, plan, date",
    [
        (
            with_infinite(data_wide, [2], "item_1"),
            profile_wide,
            plan_wide_ridge,
            "2012-04-28",
        ),
        (data_long.assign(value=np.where(
            data_long.index == 5, np.inf, data_long["value"]
        )), profile_long, plan_long_ridge, "2012-01-06"),
    ],
    ids=["wide", "long"],
)
def test_validate_infinite_target_InvalidInputError_when_multi_series(
    data, profile, plan, date
):
    """
    Test that an infinite value in one series of wide or long data raises,
    naming its date.
    """
    err_msg = re.escape(
        f"The target has infinite values (1 value(s), such as '{date}'). "
        "ForecasterRecursiveMultiSeries cannot be trained on them: replace them."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_infinite_target(data, profile, plan, True)

    assert exc_info.value.field == "data"


@pytest.mark.parametrize("position", [5, 6, 7])
def test_validate_infinite_target_InvalidInputError_when_baseline_reads_it(position):
    """
    Test that ForecasterEquivalentDate (offset 7, 3 steps: it reads positions
    7, 6 and 5) raises in prediction mode when it reads an infinite value.
    """
    data = with_infinite(data_single, [position])
    date = str(data["date"].iloc[-position].date())

    err_msg = re.escape(
        f"The forecaster reads infinite values of the target to predict (1 "
        f"value(s), such as '{date}'). ForecasterEquivalentDate repeats them "
        f"as infinite predictions: replace them."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_infinite_target(data, profile_single, plan_single_baseline, True)

    assert exc_info.value.field == "data"
    assert exc_info.value.hint == _HINT


@pytest.mark.parametrize(
    "positions, prediction",
    [([1, 2, 8, 30], True), ([5], False), ([7], False)],
    ids=["not read", "evaluation, read", "evaluation, read at 7"],
)
def test_validate_infinite_target_output_when_baseline_does_not_fail(
    positions, prediction
):
    """
    Test that ForecasterEquivalentDate is not rejected for an infinite value
    it does not read, nor in evaluation mode, where the metrics fail on them
    with their own error.
    """
    data = with_infinite(data_single, positions)

    result = validate_infinite_target(
        data, profile_single, plan_single_baseline, prediction
    )

    assert result is None


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (data_single, profile_single, plan_single_ridge),
        (with_missing(data_single, [1, 5]), profile_single, plan_single_ridge),
        (
            with_infinite(data_single, [1]),
            profile_single,
            plans_single_without_lags["foundation"],
        ),
        (
            data_long.assign(value=np.where(
                data_long.index == 5, np.inf, data_long["value"]
            )),
            profile_long,
            plan_long_foundation,
        ),
    ],
    ids=["finite", "missing", "foundation", "foundation long"],
)
def test_validate_infinite_target_output_when_no_infinite_value_to_reject(
    data, profile, plan
):
    """
    Test that finite and missing values pass, and that a ForecasterFoundation
    plan is not checked.
    """
    assert validate_infinite_target(data, profile, plan, True) is None
