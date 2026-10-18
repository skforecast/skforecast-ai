# Unit test backtest_missing_values_messages recommendation/missing_values

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
        closed_days    = False,
        cannot_predict = (
            "ForecasterRecursive with Ridge cannot predict from a missing value"
        ),
        order          = 0,
        exog           = ["promo", "price"],
        estimator      = "RandomForestRegressor",
    )

    assert backtest_missing_values_messages(missing_values, plan_h2o_exog_ridge) == [
        "The target has missing values, and `backtest()` of this plan checks "
        "every test fold before running: it raises, naming the dates, when a "
        "test fold holds one, since the metrics cannot be computed on it "
        "whatever the estimator; and when a test fold is predicted from one, "
        "since ForecasterRecursive with Ridge cannot predict from a missing "
        "value. `dropna_from_series` only drops the training rows that read "
        "one, and a training window left without rows raises too. An "
        "estimator that accepts missing values (such as "
        "'RandomForestRegressor') avoids the error of a test fold predicted "
        "from a missing value, not that of a test fold that holds one. Impute "
        "the target to backtest every fold.",
        "The exogenous columns 'promo', 'price' have missing values, and "
        "ForecasterRecursive with Ridge cannot predict from them: `backtest()` fails on a test fold whose "
        "rows have one, and `dropna_from_series` only drops them from the "
        "training data. An estimator that accepts missing values (such as "
        "'RandomForestRegressor') predicts from them; otherwise, fill them in "
        "the data, after asking the user, or leave them out of `exog_columns` "
        "when profiling.",
    ]
