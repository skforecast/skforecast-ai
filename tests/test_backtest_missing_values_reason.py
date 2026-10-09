# Unit test backtest_missing_values_reason

import pytest

from skforecast_ai._last_window import backtest_missing_values_reason

from tests.fixtures_last_window import (
    plan_h2o_baseline,
    plan_h2o_direct,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    plans_h2o_without_lags,
    profile_h2o,
    profile_h2o_gaps,
    profile_h2o_missing_target,
    profile_wide,
    plan_wide_ridge,
)


@pytest.mark.parametrize(
    "plan, profile, expected",
    [
        (
            plan_h2o_ridge,
            profile_h2o_gaps,
            ("ForecasterRecursive with Ridge cannot predict from", True),
        ),
        (
            plan_h2o_ridge,
            profile_h2o_missing_target,
            ("ForecasterRecursive with Ridge cannot predict from", True),
        ),
        (
            plan_h2o_direct,
            profile_h2o_gaps,
            ("ForecasterDirect with Ridge cannot predict from", True),
        ),
        (
            plan_h2o_baseline,
            profile_h2o_gaps,
            ("ForecasterEquivalentDate repeats", False),
        ),
    ],
    ids=["ridge_gaps", "ridge_missing_target", "direct", "baseline"],
)
def test_backtest_missing_values_reason_when_forecaster_cannot_use_a_missing_value(
    plan, profile, expected
):
    """
    Test that a single series with missing values or timestamps gives who
    cannot use them, and that only a lag forecaster has an estimator that
    would avoid it.
    """
    assert backtest_missing_values_reason(plan, profile) == expected


@pytest.mark.parametrize(
    "plan, profile",
    [
        (plan_h2o_lgbm, profile_h2o_gaps),
        (plans_h2o_without_lags["stats"], profile_h2o_gaps),
        (plans_h2o_without_lags["foundation"], profile_h2o_gaps),
        (plan_h2o_ridge, profile_h2o),
        (plan_wide_ridge, profile_wide),
    ],
    ids=["lgbm", "stats", "foundation", "clean_data", "several_series"],
)
def test_backtest_missing_values_reason_None_when_nothing_to_report(plan, profile):
    """
    Test that there is no reason with an estimator that tolerates missing
    values, a forecaster without lags, clean data or several series.
    """
    assert backtest_missing_values_reason(plan, profile) is None
