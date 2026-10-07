# Unit test warn_backtest_missing_values

import re

import pytest

from skforecast_ai._last_window import warn_backtest_missing_values

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


def _create_strategy(plan, profile):
    """Stand in for `create_cv()`, the caller of `warn_backtest_missing_values`."""
    warn_backtest_missing_values(plan, profile)


def _message(who, estimator):
    return re.escape(
        f"The target has missing values or missing timestamps (asfreq() "
        f"restores them as missing values), and {who} a missing value: "
        f"`backtest()` of this plan raises when a test fold is predicted "
        f"from one, naming its dates. `dropna_from_series` only drops them "
        f"from the training data. Impute the target{estimator} to backtest "
        f"every fold."
    )


@pytest.mark.parametrize(
    "plan, profile, who, estimator",
    [
        (
            plan_h2o_ridge,
            profile_h2o_gaps,
            "ForecasterRecursive with Ridge cannot predict from",
            ", or choose an estimator that accepts missing values (for "
            "example 'LGBMRegressor')",
        ),
        (
            plan_h2o_ridge,
            profile_h2o_missing_target,
            "ForecasterRecursive with Ridge cannot predict from",
            ", or choose an estimator that accepts missing values (for "
            "example 'LGBMRegressor')",
        ),
        (
            plan_h2o_direct,
            profile_h2o_gaps,
            "ForecasterDirect with Ridge cannot predict from",
            ", or choose an estimator that accepts missing values (for "
            "example 'LGBMRegressor')",
        ),
        (
            plan_h2o_baseline,
            profile_h2o_gaps,
            "ForecasterEquivalentDate repeats",
            "",
        ),
    ],
    ids=["ridge_gaps", "ridge_missing_target", "direct", "baseline"],
)
def test_warn_backtest_missing_values_UserWarning_when_estimator_cannot_predict_from_missing(
    plan, profile, who, estimator
):
    """
    Test that a single series with missing values or timestamps warns for a
    lag forecaster whose estimator does not tolerate them (with the hint of
    an estimator that does) and for ForecasterEquivalentDate (without it),
    attributed to the caller of the caller of the helper.
    """
    with pytest.warns(UserWarning, match=_message(who, estimator)) as record:
        _create_strategy(plan, profile)

    assert len(record) == 1
    assert record[0].filename == __file__


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
def test_warn_backtest_missing_values_no_warning_when_nothing_to_report(
    plan, profile
):
    """
    Test that there is no warning (warnings are errors in this suite) with an
    estimator that tolerates missing values, a forecaster without lags,
    clean data or several series.
    """
    _create_strategy(plan, profile)
