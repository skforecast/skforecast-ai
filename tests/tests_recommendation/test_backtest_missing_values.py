# Unit test backtest_missing_values recommendation/missing_values

import pytest

from skforecast_ai.recommendation.missing_values import (
    BacktestMissingValues,
    backtest_missing_values,
)

from ..fixtures_last_window import (
    plan_h2o_baseline,
    plan_h2o_direct,
    plan_h2o_exog_lgbm,
    plan_h2o_exog_ridge,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    plan_single_closed_ridge,
    plan_wide_ridge,
    plans_h2o_without_lags,
    profile_h2o,
    profile_h2o_exog,
    profile_h2o_exog_missing_target,
    profile_h2o_gaps,
    profile_h2o_missing_target,
    profile_single_closed,
    profile_wide,
)

_RIDGE = "ForecasterRecursive with Ridge cannot predict from a missing value"


@pytest.mark.parametrize(
    "plan, profile, expected",
    [
        (
            plan_h2o_ridge,
            profile_h2o_gaps,
            BacktestMissingValues(
                values=False, gaps=True, closed_days=False,
                cannot_predict=_RIDGE, order=0, exog=[],
                estimator="RandomForestRegressor",
            ),
        ),
        (
            plan_h2o_ridge,
            profile_h2o_missing_target,
            BacktestMissingValues(
                values=True, gaps=False, closed_days=False,
                cannot_predict=_RIDGE, order=0, exog=[],
                estimator="RandomForestRegressor",
            ),
        ),
        (
            plan_h2o_direct,
            profile_h2o_gaps,
            BacktestMissingValues(
                values=False, gaps=True, closed_days=False,
                cannot_predict=(
                    "ForecasterDirect with Ridge cannot predict from a missing "
                    "value"
                ),
                order=0, exog=[], estimator="RandomForestRegressor",
            ),
        ),
        (
            plan_h2o_baseline,
            profile_h2o_gaps,
            BacktestMissingValues(
                values=False, gaps=True, closed_days=False,
                cannot_predict=(
                    "ForecasterEquivalentDate repeats it as a missing prediction"
                ),
                order=0, exog=[], estimator=None,
            ),
        ),
        (
            plan_h2o_lgbm,
            profile_h2o_gaps,
            BacktestMissingValues(
                values=False, gaps=True, closed_days=False,
                cannot_predict=None, order=0, exog=[], estimator=None,
            ),
        ),
        (
            plan_h2o_lgbm.model_copy(
                update={
                    "forecaster_kwargs": {
                        **plan_h2o_lgbm.forecaster_kwargs, "differentiation": 2
                    }
                },
                deep=True,
            ),
            profile_h2o_missing_target,
            BacktestMissingValues(
                values=True, gaps=False, closed_days=False,
                cannot_predict=None, order=2, exog=[], estimator=None,
            ),
        ),
        (
            plan_h2o_exog_ridge,
            profile_h2o_exog,
            BacktestMissingValues(
                values=False, gaps=False, closed_days=False,
                cannot_predict=None, order=0, exog=["promo"],
                estimator="RandomForestRegressor",
            ),
        ),
        (
            plan_h2o_exog_ridge,
            profile_h2o_exog_missing_target,
            BacktestMissingValues(
                values=True, gaps=False, closed_days=False,
                cannot_predict=_RIDGE, order=0, exog=["promo"],
                estimator="RandomForestRegressor",
            ),
        ),
        (
            plan_single_closed_ridge,
            profile_single_closed,
            BacktestMissingValues(
                values=False, gaps=True, closed_days=True,
                cannot_predict=_RIDGE, order=0, exog=[],
                estimator="RandomForestRegressor",
            ),
        ),
    ],
    ids=[
        "ridge_gaps",
        "ridge_values",
        "direct",
        "baseline",
        "lgbm",
        "lgbm_differentiation",
        "ridge_exog",
        "ridge_target_and_exog",
        "closed_days_daily",
    ],
)
def test_backtest_missing_values_output_when_backtest_can_fail(plan, profile, expected):
    """
    Test what can make the backtest of a single series fail on missing
    values: every forecaster that predicts from past values can meet one
    inside a test fold; Ridge and ForecasterEquivalentDate cannot predict
    from one, and only the lag forecaster has an estimator of the rules
    (RandomForestRegressor, for 120 observations) to switch to; the
    differentiation is reported with its order; the exogenous columns with
    missing values count only for an estimator that cannot predict from
    them; the missing timestamps of daily data may be days the business is
    closed.
    """
    missing_values = backtest_missing_values(plan, profile)

    assert missing_values == expected
    assert missing_values.target is (expected.values or expected.gaps)


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
def test_backtest_missing_values_None_when_nothing_to_report(plan, profile):
    """
    Test that there is nothing to report with a forecaster without lags,
    clean data, missing exogenous values and an estimator that predicts from
    them, or several series, whose backtest drops them per series.
    """
    assert backtest_missing_values(plan, profile) is None
