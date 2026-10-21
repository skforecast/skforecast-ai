# Unit test backtest_missing_values_messages recommendation/missing_values

from skforecast_ai.mcp._runtime import MAX_NOTICE_CHARS
from skforecast_ai.recommendation.missing_values import (
    BacktestMissingValues,
    backtest_missing_values_messages,
)

from ..fixtures_last_window import plan_h2o_exog_ridge


def test_backtest_missing_values_messages_output_when_target_and_exog():
    """
    Test that the messages say, each case as a condition, when the backtest
    fails on the missing values of the target and of the exogenous columns,
    and what avoids each error, one message for each so that both fit in a
    notice of the MCP server. The cases of every plan and profile are in
    `tests/test_warn_backtest_missing_values.py`.
    """
    missing_values = BacktestMissingValues(
        values         = True,
        gaps           = False,
        closed_days    = [],
        cannot_predict = (
            "ForecasterRecursive with Ridge cannot predict from a missing value"
        ),
        order          = 0,
        exog           = ["promo", "price"],
        estimator      = "RandomForestRegressor",
    )

    assert backtest_missing_values_messages(missing_values, plan_h2o_exog_ridge) == [
        "The target has missing values, and `backtest()` checks every test fold "
        "before running: it raises, naming the dates, when a test fold holds one, "
        "whatever the estimator, since no metric is computed on it; and when a test "
        "fold is predicted from one, since ForecasterRecursive with Ridge cannot "
        "predict from a missing value. `dropna_from_series` only drops the training "
        "rows that read one, and a training window left without rows raises too. An "
        "estimator that accepts missing values (such as 'RandomForestRegressor') "
        "avoids the error of a fold predicted from a missing value, not of a fold "
        "that holds one. Impute the target to backtest every fold.",
        "The exogenous columns 'promo', 'price' have missing values, and "
        "ForecasterRecursive with Ridge cannot predict from them: `backtest()` "
        "checks every test fold before running and raises, naming the dates, "
        "when the rows it predicts have one, and `dropna_from_series` only "
        "drops them from the training data. An estimator that accepts missing "
        "values (such as "
        "'RandomForestRegressor') predicts from them; otherwise, fill them in "
        "the data, after asking the user, or leave them out of `exog_columns` "
        "when profiling.",
    ]


def test_backtest_missing_values_messages_fit_in_a_notice_of_the_mcp_server():
    """
    Test that the longest message of the target (missing values and missing
    timestamps of daily data on the closed days with the longest names, the
    longest name of an estimator that does not accept them, the
    differentiation, and the estimator of the rules for small data) fits in
    a notice of the MCP server, which cuts the text after `MAX_NOTICE_CHARS`
    and would lose the last remedy. Daily data has at most three closed
    days: a frequency needs half of its dates observed.
    """
    missing_values = BacktestMissingValues(
        values         = True,
        gaps           = True,
        closed_days    = [2, 3, 5],
        cannot_predict = (
            "ForecasterRecursive with GradientBoostingRegressor cannot predict "
            "from a missing value"
        ),
        order          = 2,
        exog           = [],
        estimator      = "RandomForestRegressor",
    )

    messages = backtest_missing_values_messages(missing_values, plan_h2o_exog_ridge)

    assert len(messages) == 1
    assert len(messages[0]) <= MAX_NOTICE_CHARS
    assert messages[0].endswith(
        "If the business is closed on Wednesdays, Thursdays and Saturdays, fill "
        "them with 0 in the data, after asking the user, or impute the target to "
        "backtest every fold."
    )
