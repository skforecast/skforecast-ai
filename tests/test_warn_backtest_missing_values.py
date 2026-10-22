# Unit test warn_backtest_missing_values

import pytest

from skforecast_ai._last_window import warn_backtest_missing_values

from tests.fixtures_last_window import (
    plan_h2o_baseline,
    plan_h2o_direct,
    plan_h2o_exog_lgbm,
    plan_h2o_exog_ridge,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    plan_single_closed_ridge,
    plan_single_random_gaps_ridge,
    plans_h2o_without_lags,
    profile_h2o,
    profile_h2o_exog,
    profile_h2o_exog_missing_target,
    profile_h2o_gaps,
    profile_h2o_missing_target,
    profile_single_closed,
    profile_single_random_gaps,
    profile_wide,
    plan_wide_ridge,
)

# ForecasterRecursive with LGBMRegressor and a differentiation of order 1.
plan_h2o_lgbm_differenced = plan_h2o_lgbm.model_copy(
    update={
        "forecaster_kwargs": {
            **plan_h2o_lgbm.forecaster_kwargs, "differentiation": 1
        }
    },
    deep=True,
)

GAPS = "missing timestamps (asfreq() restores them as missing values)"
HOLDS = (
    "a test fold holds one, whatever the estimator, since no metric is "
    "computed on it"
)
TRAINING_ROWS = (
    " `dropna_from_series` only drops the training rows that read one, and "
    "a training window left without rows raises too. "
    "An estimator that accepts missing values (such as "
    "'RandomForestRegressor') avoids the error of a fold predicted from a "
    "missing value, not of a fold that holds one."
)
IMPUTE = " Impute the target to backtest every fold."
EXOG = (
    "The exogenous column 'promo' has missing values, and ForecasterRecursive "
    "with Ridge cannot predict from them: `backtest()` checks every test fold "
    "before running and raises, naming the dates, when the rows it predicts "
    "have one, and `dropna_from_series` only drops them from the training "
    "data. An estimator that accepts missing values (such as "
    "'RandomForestRegressor') predicts from them; otherwise, fill them in the "
    "data, after asking the user, or leave it out of `exog_columns` when "
    "profiling."
)


def _target(what, when):
    return (
        f"The target has {what}, and `backtest()` checks every test fold "
        f"before running: it raises, naming the dates, when {when}."
    )


def _create_strategy(plan, profile):
    """Stand in for `create_cv()`, the caller of `warn_backtest_missing_values`."""
    warn_backtest_missing_values(plan, profile)


@pytest.mark.parametrize(
    "plan, profile, expected",
    [
        (
            plan_h2o_ridge,
            profile_h2o_gaps,
            _target(
                GAPS,
                f"{HOLDS}; and when a test fold is predicted from one, since "
                f"ForecasterRecursive with Ridge cannot predict from a missing "
                f"value",
            ) + TRAINING_ROWS + IMPUTE,
        ),
        (
            plan_h2o_ridge,
            profile_h2o_missing_target,
            _target(
                "missing values",
                f"{HOLDS}; and when a test fold is predicted from one, since "
                f"ForecasterRecursive with Ridge cannot predict from a missing "
                f"value",
            ) + TRAINING_ROWS + IMPUTE,
        ),
        (
            plan_h2o_direct,
            profile_h2o_gaps,
            _target(
                GAPS,
                f"{HOLDS}; and when a test fold is predicted from one, since "
                f"ForecasterDirect with Ridge cannot predict from a missing "
                f"value",
            ) + TRAINING_ROWS + IMPUTE,
        ),
        (
            plan_h2o_baseline,
            profile_h2o_gaps,
            _target(
                GAPS,
                f"{HOLDS}; and when a test fold is predicted from one, since "
                f"ForecasterEquivalentDate repeats it as a missing prediction",
            ) + IMPUTE,
        ),
        (
            plan_h2o_lgbm,
            profile_h2o_gaps,
            _target(GAPS, HOLDS) + IMPUTE,
        ),
        (
            plan_h2o_lgbm_differenced,
            profile_h2o_gaps,
            _target(
                GAPS,
                f"{HOLDS}; and when one of the last 1 value(s) before a test "
                f"fold is missing, whatever the estimator, since the inverse of "
                f"the differentiation starts from them",
            ) + IMPUTE,
        ),
        (
            plan_h2o_exog_ridge,
            profile_h2o_exog,
            EXOG,
        ),
        (
            plan_h2o_exog_ridge,
            profile_h2o_exog_missing_target,
            (
                _target(
                    "missing values",
                    f"{HOLDS}; and when a test fold is predicted from one, since "
                    f"ForecasterRecursive with Ridge cannot predict from a "
                    f"missing value",
                ) + TRAINING_ROWS + IMPUTE,
                EXOG,
            ),
        ),
        (
            plan_single_closed_ridge,
            profile_single_closed,
            _target(
                GAPS,
                f"{HOLDS}; and when a test fold is predicted from one, since "
                f"ForecasterRecursive with Ridge cannot predict from a missing "
                f"value",
            )
            + TRAINING_ROWS
            + " If the business is closed on Sundays, fill them with 0 in the "
              "data, after asking the user, or impute the target to backtest "
              "every fold.",
        ),
        (
            plan_single_random_gaps_ridge,
            profile_single_random_gaps,
            _target(
                GAPS,
                f"{HOLDS}; and when a test fold is predicted from one, since "
                f"ForecasterRecursive with Ridge cannot predict from a missing "
                f"value",
            ) + TRAINING_ROWS + IMPUTE,
        ),
    ],
    ids=[
        "nan_before_folds_ridge_gaps",
        "nan_before_folds_ridge_values",
        "nan_before_folds_direct",
        "nan_before_folds_baseline",
        "nan_in_test_fold_lgbm",
        "differentiation_lgbm",
        "nan_in_exog_ridge",
        "nan_in_target_and_exog_ridge",
        "closed_days_daily",
        "random_gaps_daily",
    ],
)
def test_warn_backtest_missing_values_UserWarning_when_backtest_can_fail_on_them(
    plan, profile, expected
):
    """
    Test that a single series whose backtest can fail on missing values
    warns, attributed to the caller of the caller of the helper, with every
    case as a condition (the profile does not say where the values are):
    a missing value inside a test fold fails whatever the estimator; a fold
    predicted from one fails with Ridge and ForecasterEquivalentDate; with
    the differentiation, one of the last values before a fold fails even
    with LGBMRegressor; a missing exogenous value fails with Ridge, in a
    warning of its own after the one of the target. The estimator offered is the one of the rules for 120 observations
    (RandomForestRegressor), and only where it avoids the error; daily data
    whose missing timestamps all fall on a day of the week without dates
    gets the advice of the closed days, naming the day, and daily data with
    missing timestamps on other days does not.
    """
    expected = [expected] if isinstance(expected, str) else list(expected)
    # Every warning is compared below: a `match` would re-emit the others.
    with pytest.warns(UserWarning) as record:
        _create_strategy(plan, profile)

    assert [str(warning.message) for warning in record] == expected
    assert all(warning.filename == __file__ for warning in record)


@pytest.mark.parametrize(
    "plan, profile",
    [
        (plans_h2o_without_lags["stats"], profile_h2o_gaps),
        (plans_h2o_without_lags["foundation"], profile_h2o_gaps),
        (plan_h2o_ridge, profile_h2o),
        (plan_h2o_exog_lgbm, profile_h2o_exog),
        (plan_wide_ridge, profile_wide),
    ],
    ids=["stats", "foundation", "clean_data", "lgbm_exog", "several_series"],
)
def test_warn_backtest_missing_values_no_warning_when_nothing_to_report(
    plan, profile
):
    """
    Test that there is no warning (warnings are errors in this suite) with a
    forecaster without lags, clean data, missing exogenous values and an
    estimator that predicts from them, or several series.
    """
    _create_strategy(plan, profile)
