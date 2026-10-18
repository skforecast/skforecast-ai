# Unit test missing_values_advice recommendation/missing_values

import pytest

from skforecast_ai.recommendation.missing_values import missing_values_advice
from skforecast_ai.schemas import DataProfile


def _profile(**kwargs):
    """
    Return the profile of a monthly series of 120 observations (or of three
    series of 120, `n_series=3`), with the missing values of `kwargs`.
    """
    n_series = kwargs.pop("n_series", 1)
    names = ["y"] if n_series == 1 else [f"s{number}" for number in range(n_series)]
    return DataProfile(
        data_format          = "single" if n_series == 1 else "wide",
        n_series             = n_series,
        series_lengths       = {name: 120 for name in names},
        span_index_length    = 120,
        n_total_observations = 120 * n_series,
        target               = names[0] if n_series == 1 else names,
        index_type           = "datetime",
        frequency            = "MS",
        **kwargs,
    )


_SCORED = (
    " A missing value on a date that a backtest or `test_size` scores fails "
    "with any estimator."
)
_IMPUTE = " Imputing the target, after asking the user, avoids these errors."
_SNIPPET_RIDGE = (
    "# Option 1: an estimator that accepts missing values, "
    "estimator='RandomForestRegressor'\n"
    "# Option 2: impute them in the data, after asking the user"
)
_SNIPPET_LGBM = (
    "# LGBMRegressor accepts missing values. Impute them only if needed,\n"
    "# after asking the user, for example:\n"
    "# data[column] = data[column].interpolate()"
)
_EXOG_RIDGE = (
    "The exogenous column 'promo' has missing values: ForecasterRecursive with "
    "Ridge cannot predict from them, and `dropna_from_series` only drops the "
    "training rows that have one. An estimator that accepts missing values "
    "(such as 'RandomForestRegressor') predicts from them; otherwise, fill "
    "them in the data, after asking the user, or leave it out of "
    "`exog_columns` when profiling."
)


@pytest.mark.parametrize(
    "profile, forecaster, estimator, task_type, differentiation, expected",
    [
        (
            _profile(missing_target={"y": 3}),
            "ForecasterRecursive", "Ridge", "single_series", None,
            (
                "The target has missing values: ForecasterRecursive with Ridge "
                "cannot predict from them, and `dropna_from_series` only drops "
                "the training rows that read one. An estimator that accepts "
                "missing values (such as 'RandomForestRegressor') predicts from "
                "them." + _SCORED + _IMPUTE,
                _SNIPPET_RIDGE,
            ),
        ),
        (
            _profile(has_gaps=True),
            "ForecasterRecursive", "LGBMRegressor", "single_series", None,
            (
                "The target has missing timestamps (asfreq() restores them as "
                "missing values): LGBMRegressor trains and predicts with them."
                + _SCORED + _IMPUTE,
                _SNIPPET_LGBM,
            ),
        ),
        (
            _profile(missing_target={"y": 3}),
            "ForecasterRecursive", "LGBMRegressor", "single_series", 1,
            (
                "The target has missing values: LGBMRegressor trains and "
                "predicts with them." + _SCORED + " With the differentiation, a "
                "missing value among the last 1 value(s) before a prediction "
                "gives missing predictions whatever the estimator." + _IMPUTE,
                _SNIPPET_LGBM,
            ),
        ),
        (
            _profile(n_series=3, missing_target={"s0": 3}),
            "ForecasterRecursiveMultiSeries", "Ridge", "multi_series", None,
            (
                "The target has missing values: ForecasterRecursiveMultiSeries "
                "with Ridge cannot predict from them (a backtest leaves a series "
                "out of the folds predicted from one), and `dropna_from_series` "
                "only drops the training rows that read one. An estimator that "
                "accepts missing values (such as 'LGBMRegressor') predicts from "
                "them. A missing value on a date that `test_size` scores fails "
                "with any estimator." + _IMPUTE,
                "# Option 1: an estimator that accepts missing values, "
                "estimator='LGBMRegressor'\n"
                "# Option 2: impute them in the data, after asking the user",
            ),
        ),
        (
            _profile(exog_columns=["promo"], missing_exog={"promo": 2}),
            "ForecasterRecursive", "Ridge", "single_series", None,
            (
                _EXOG_RIDGE,
                _SNIPPET_RIDGE + "\n# Option 3: leave the exogenous columns "
                "with missing values out of exog_columns",
            ),
        ),
        (
            _profile(exog_columns=["promo"], missing_exog={"promo": 2}),
            "ForecasterRecursive", "LGBMRegressor", "single_series", None,
            (
                "The exogenous column 'promo' has missing values: LGBMRegressor "
                "trains and predicts with them.",
                _SNIPPET_LGBM,
            ),
        ),
        (
            _profile(
                missing_target={"y": 1}, exog_columns=["promo"],
                missing_exog={"promo": 2},
            ),
            "ForecasterStats", "Arima", "statistical", None,
            (
                "ForecasterStats fails on a missing value of the target and "
                "gives missing predictions from a missing value of the "
                "exogenous column 'promo'. Impute them in the data, after "
                "asking the user, or leave the exogenous columns out of "
                "`exog_columns` when profiling.",
                "# Impute the missing values in the data, after asking the "
                "user,\n# for example: data[column] = data[column].interpolate()",
            ),
        ),
    ],
    ids=[
        "target_ridge",
        "gaps_lgbm",
        "differentiation_lgbm",
        "several_series_ridge",
        "exog_ridge",
        "exog_lgbm",
        "stats",
    ],
)
def test_missing_values_advice_output(
    profile, forecaster, estimator, task_type, differentiation, expected
):
    """
    Test that the advice says only what works for the estimator of the plan
    (V11): `dropna_from_series`, which only drops training rows, is never
    the remedy; an estimator that cannot predict from missing values gets
    the one of the rules (RandomForestRegressor for 120 observations,
    LGBMRegressor for 360 pooled) and filling them in, after asking the
    user; a missing exogenous column can also be left out of
    `exog_columns`. A missing value that an evaluation scores fails with any
    estimator (a backtest of several series drops them), and with the
    differentiation so does one of the last values before a prediction.
    ForecasterStats, without estimator or `dropna_from_series`, is told to
    impute.
    """
    assert missing_values_advice(
        profile         = profile,
        forecaster      = forecaster,
        estimator       = estimator,
        task_type       = task_type,
        differentiation = differentiation,
    ) == expected


def test_missing_values_advice_without_estimator_names_estimators_that_cannot_use_them():
    """
    Test that, without the estimator of the plan, the advice says what an
    estimator that does not accept missing values cannot do, instead of
    naming None.
    """
    reason, _ = missing_values_advice(
        profile    = _profile(missing_target={"y": 3}),
        forecaster = "ForecasterRecursive",
        estimator  = None,
        task_type  = "single_series",
    )

    assert reason.startswith(
        "The target has missing values: ForecasterRecursive with an estimator "
        "that does not accept them cannot predict from them, and "
        "`dropna_from_series` only drops the training rows that read one."
    )


def test_missing_values_advice_None_when_nothing_is_missing():
    """
    Test that a profile without missing values, missing timestamps or missing
    exogenous values gives no advice.
    """
    assert missing_values_advice(
        profile    = _profile(),
        forecaster = "ForecasterRecursive",
        estimator  = "Ridge",
        task_type  = "single_series",
    ) is None
