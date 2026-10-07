# Unit test validate_backtest_windows

import re

import pytest

from skforecast_ai._last_window import validate_backtest_windows
from skforecast_ai.exceptions import InvalidInputError

from tests.fixtures_last_window import (
    cv_h2o,
    data_h2o,
    data_h2o_gaps,
    data_wide,
    plan_h2o_baseline,
    plan_h2o_direct,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    plan_wide_ridge,
    plans_h2o_without_lags,
    profile_h2o,
    profile_h2o_gaps,
    profile_of,
    profile_wide,
    with_missing,
    without_months,
)


def test_validate_backtest_windows_InvalidInputError_when_estimator_cannot_use_missing():
    """
    Test that a missing timestamp (2004-10-01) that a lag reads to predict a
    test fold raises for Ridge, naming the fold count and the date, with
    field 'data'. The other two (positions 30 and 31) are read by no fold.
    """
    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict 1 of "
        "the 3 test folds ('x': 1 value(s), such as '2004-10-01'). "
        "ForecasterRecursive with Ridge cannot use them, so its predictions "
        "would be missing: fill them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_backtest_windows(
            data_h2o_gaps, profile_h2o_gaps, plan_h2o_ridge, cv_h2o()
        )

    assert exc_info.value.field == "data"


def test_validate_backtest_windows_InvalidInputError_when_missing_value_in_incomplete_last_fold():
    """
    Test that the last fold, incomplete (7 steps of 12), is checked with the
    positions its steps read: a value 3 rows before it (2007-04-01) is read by
    the complete fold but not by the incomplete one, which reads 6 to 12 rows
    before it.
    """
    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict 1 of "
        "the 3 test folds ('x': 1 value(s), such as '2007-04-01'). "
        "ForecasterRecursive with Ridge cannot use them, so its predictions "
        "would be missing: fill them in."
    )
    data = without_months(data_h2o, [105])
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_backtest_windows(
            data, profile_of(data), plan_h2o_ridge, cv_h2o()
        )

    incomplete = without_months(data_h2o.iloc[:-5], [105])
    validate_backtest_windows(
        incomplete, profile_of(incomplete), plan_h2o_ridge, cv_h2o()
    )


def test_validate_backtest_windows_InvalidInputError_when_forecaster_is_baseline():
    """
    Test that ForecasterEquivalentDate raises for a missing value it repeats,
    with its own wording.
    """
    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict 1 of "
        "the 3 test folds ('x': 1 value(s), such as '2004-10-01'). "
        "ForecasterEquivalentDate repeats them as missing predictions: fill "
        "them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_backtest_windows(
            data_h2o_gaps, profile_h2o_gaps, plan_h2o_baseline, cv_h2o()
        )

    assert exc_info.value.field == "data"


def test_validate_backtest_windows_UserWarning_when_estimator_tolerates_missing():
    """
    Test that LGBMRegressor, which tolerates missing values, only warns, with
    the same fold count and date as the error of Ridge.
    """
    warn_msg = re.escape(
        "The forecaster reads missing values of the target to predict 1 of "
        "the 3 test folds ('x': 1 value(s), such as '2004-10-01'). "
        "LGBMRegressor treats them as missing values; check that they are "
        "meant to be missing."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_backtest_windows(
            data_h2o_gaps, profile_h2o_gaps, plan_h2o_lgbm, cv_h2o()
        )


@pytest.mark.parametrize(
    "positions",
    [[30, 31], [10], [70]],
    ids=["early_in_training", "first_position", "inside_rolling_window_only"],
)
def test_validate_backtest_windows_no_error_when_missing_value_not_read(positions):
    """
    Test that missing timestamps no fold reads (early in the training data,
    or only inside the rolling windows, which skip them) pass for Ridge.
    """
    data = without_months(data_h2o, positions)

    validate_backtest_windows(data, profile_of(data), plan_h2o_ridge, cv_h2o())


def test_validate_backtest_windows_no_error_when_direct_lags_do_not_reach_value():
    """
    Test that a ForecasterDirect does not raise for the value 2004-10-01 that
    a recursive forecaster reads (a direct one reads lag k at every step, so
    it is not read from the fold that starts at position 84).
    """
    validate_backtest_windows(
        data_h2o_gaps, profile_h2o_gaps, plan_h2o_direct, cv_h2o()
    )


@pytest.mark.parametrize(
    "plan",
    list(plans_h2o_without_lags.values()),
    ids=list(plans_h2o_without_lags),
)
def test_validate_backtest_windows_returns_when_forecaster_without_lags(plan):
    """
    Test that ForecasterStats and ForecasterFoundation, which read no lags,
    return without error.
    """
    validate_backtest_windows(data_h2o_gaps, profile_h2o_gaps, plan, cv_h2o())


def test_validate_backtest_windows_returns_when_no_missing_values():
    """
    Test that complete data returns without error.
    """
    validate_backtest_windows(data_h2o, profile_h2o, plan_h2o_ridge, cv_h2o())


def test_validate_backtest_windows_returns_when_several_series():
    """
    Test that several series, with a missing value in the last rows, return
    without error: their backtest drops the missing values per series.
    """
    data = with_missing(data_wide, [1], column=data_wide.columns[0])

    validate_backtest_windows(
        data, profile_wide, plan_wide_ridge, cv_h2o(initial_train_size=84)
    )


def test_validate_backtest_windows_returns_when_strategy_cannot_be_split():
    """
    Test that a strategy that cannot be split on the data returns without
    error (the generated script fails with its own).
    """
    validate_backtest_windows(
        data_h2o_gaps, profile_h2o_gaps, plan_h2o_ridge, cv_h2o(500)
    )


def test_validate_backtest_windows_does_not_modify_cv_verbose():
    """
    Test that the `verbose` option of the strategy is restored after the
    check, also when it raises.
    """
    cv = cv_h2o()
    cv.verbose = True

    with pytest.raises(InvalidInputError):
        validate_backtest_windows(data_h2o_gaps, profile_h2o_gaps, plan_h2o_ridge, cv)

    assert cv.verbose is True
