# Unit test validate_backtest_exog

import re
import warnings

import numpy as np
import pandas as pd
import pytest
from skforecast.exceptions import MissingValuesWarning

import skforecast_ai.assistant as assistant_module
from skforecast_ai import ForecastingAssistant
from skforecast_ai._last_window import LEFT_OUT_OF_FOLDS, validate_backtest_exog
from skforecast_ai.exceptions import DataContentError, ForecastExecutionError

from tests.fixtures_last_window import (
    cv_h2o,
    cv_items_sales,
    data_h2o,
    data_h2o_exog,
    data_long_exog,
    data_wide_exog,
    long_starting_late,
    multiseries_exog_of,
    plan_exog_of,
    plan_h2o_exog_baseline,
    plan_h2o_exog_direct,
    plan_h2o_exog_foundation,
    plan_h2o_exog_lgbm,
    plan_h2o_exog_ridge,
    plan_h2o_exog_stats,
    profile_h2o_exog,
    with_missing_exog,
)

RIDGE = "Ridge cannot use them, so its predictions would be missing"
SCORED = (
    ", and skforecast would compute the metrics without them, without a "
    "warning"
)
TIMESTAMPS = (
    ", counting the missing timestamps that asfreq() restores as rows "
    "without values"
)


def _message(where, found, forecaster, remedy, scored="", timestamps=""):
    """Return the error of missing exogenous values read by a backtest."""
    return (
        f"The forecaster reads missing values of the exogenous variables to "
        f"predict {where} ({found}){timestamps}. {forecaster} with {RIDGE}"
        f"{scored}. Either they are filled in, after asking the user, "
        f"{remedy} out of `exog_columns` when profiling."
    )


def _tolerant(estimator):
    """Return the remedies of a lag forecaster, with the column."""
    return (
        f"or the plan uses an estimator that accepts missing values (such as "
        f"{estimator!r}), or the column is left"
    )


_IN_SECOND_FOLD = (
    "The forecaster reads missing values of the exogenous variables to predict "
    "1 of the 3 test folds ('promo': 1 value(s), such as '2006-11-01'). "
)


@pytest.mark.parametrize(
    "plan, expected",
    [
        (
            plan_h2o_exog_ridge,
            _IN_SECOND_FOLD
            + "ForecasterRecursive with Ridge cannot use them, so its "
            "predictions would be missing. Either they are filled in, after "
            "asking the user, or the plan uses an estimator that accepts "
            "missing values (such as 'RandomForestRegressor'), or the column "
            "is left out of `exog_columns` when profiling.",
        ),
        (
            plan_h2o_exog_direct,
            _IN_SECOND_FOLD
            + "ForecasterDirect with Ridge cannot use them, so its predictions "
            "would be missing. Either they are filled in, after asking the "
            "user, or the plan uses an estimator that accepts missing values "
            "(such as 'RandomForestRegressor'), or the column is left out of "
            "`exog_columns` when profiling.",
        ),
        (
            plan_h2o_exog_stats,
            _IN_SECOND_FOLD
            + "ForecasterStats with Arima cannot use them, so its predictions "
            "would be missing. Either they are filled in, after asking the "
            "user, or the column is left out of `exog_columns` when profiling.",
        ),
    ],
    ids=["recursive", "direct", "stats"],
)
def test_validate_backtest_exog_DataContentError_when_test_fold_reads_missing_exog(
    plan, expected
):
    """
    Test that a missing value of 'promo' in a row of the second test fold
    (2006-11-01) raises for a forecaster that cannot use it, naming the fold
    count, the column and the date, with field 'data'; the one of the
    training rows (1999-05-01) is not read. ForecasterStats has no
    estimator to switch to.
    """
    with pytest.raises(DataContentError, match=re.escape(expected)) as exc_info:
        validate_backtest_exog(data_h2o_exog, profile_h2o_exog, plan, cv_h2o())

    assert (exc_info.value.code, exc_info.value.field) == ("invalid_argument", "data")


@pytest.mark.parametrize(
    "plan",
    [
        plan_h2o_exog_foundation,
        plan_h2o_exog_baseline,
        plan_h2o_exog_ridge.model_copy(update={"use_exog": False}, deep=True),
    ],
    ids=["foundation", "baseline", "without_exog"],
)
def test_validate_backtest_exog_passes_when_plan_can_use_missing_exog(plan):
    """
    Test that the same missing value passes without a warning for a
    foundation model (which takes them as they are), a baseline (which
    reads no exogenous variables) and a plan that does not use them.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert validate_backtest_exog(
            data_h2o_exog, profile_h2o_exog, plan, cv_h2o()
        ) is None


def test_validate_backtest_exog_UserWarning_when_estimator_accepts_missing_exog():
    """
    Test that the missing value of 'promo' in the second test fold
    (2006-11-01) warns, without failing, for an estimator that accepts
    missing values (LGBMRegressor), naming the fold count, the column and
    the date, as `forecast()` warns about the future values. Before, nothing
    said it.
    """
    warn_msg = re.escape(
        _IN_SECOND_FOLD
        + "LGBMRegressor treats them as missing values; check that they are "
        "meant to be missing."
    )
    with pytest.warns(UserWarning, match=f"^{warn_msg}$"):
        result = validate_backtest_exog(
            data_h2o_exog, profile_h2o_exog, plan_h2o_exog_lgbm, cv_h2o()
        )

    assert result is None


def test_validate_backtest_exog_passes_when_missing_exog_is_in_training_rows():
    """
    Test that missing values of 'promo' only in the training rows (the
    plan drops them, `dropna_from_series`) pass.
    """
    data = with_missing_exog(data_h2o, [10, 50, 83])
    profile, plan = plan_exog_of(data)

    assert validate_backtest_exog(data, profile, plan, cv_h2o()) is None


@pytest.mark.parametrize(
    "position, kwargs, expected_date",
    [
        (84, {"lags": [13], "window_features": []}, "2005-07-01"),
        (84, {"lags": [1], "window_features": []}, "2005-07-01"),
        (85, {"lags": [13], "window_features": [], "differentiation": 1}, "2005-08-01"),
        (
            85,
            {"lags": [13], "window_features": [{"stats": ["mean"], "window_size": 1}]},
            "2005-08-01",
        ),
    ],
    ids=["lag_reaches_fold", "lag_1", "differentiation", "window_feature"],
)
def test_validate_backtest_exog_DataContentError_when_gap_row_reaches_fold(
    position, kwargs, expected_date
):
    """
    Test that, with a gap of 2, a missing value in a row of the gap (84 or
    85, before the scored rows 86 to 97 of the first fold) raises for a
    recursive forecaster when its missing prediction reaches a scored date:
    through a lag (13 from 84 is 97; 1 from either), the inverse of the
    differentiation (every later step) or a window feature all of whose
    values are missing.
    """
    data = with_missing_exog(data_h2o, [position])
    profile, plan = plan_exog_of(data, **kwargs)

    expected = _message(
        where      = "1 of the 3 test folds",
        found      = f"'promo': 1 value(s), such as '{expected_date}'",
        forecaster = "ForecasterRecursive",
        remedy     = _tolerant("RandomForestRegressor"),
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_backtest_exog(data, profile, plan, cv_h2o(gap=2))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lags": [13], "window_features": []},
        {"lags": [13], "window_features": [{"stats": ["mean"], "window_size": 2}]},
        {"forecaster": "ForecasterStats"},
    ],
    ids=["lag_beyond_fold", "window_with_values", "stats"],
)
def test_validate_backtest_exog_passes_when_gap_row_reaches_no_scored_date(kwargs):
    """
    Test that a missing value in the second row of the gap (85) passes when
    no scored prediction reads it: lag 13 reaches 98, after the fold; a
    window of 2 also holds the prediction of 84; ForecasterStats predicts
    each date from its own row.
    """
    data = with_missing_exog(data_h2o, [85])
    profile, plan = plan_exog_of(data, **kwargs)

    assert validate_backtest_exog(data, profile, plan, cv_h2o(gap=2)) is None


def test_validate_backtest_exog_DataContentError_names_missing_timestamps():
    """
    Test that a missing timestamp in a row of the gap (2005-07-01), which
    `asfreq()` restores as a row without values, is read as a missing
    exogenous value, and the message says so.
    """
    data = with_missing_exog(data_h2o, []).drop(index=data_h2o.index[[84]])
    profile, plan = plan_exog_of(data, lags=[1], window_features=[])

    expected = _message(
        where      = "1 of the 3 test folds",
        found      = "'promo': 1 value(s), such as '2005-07-01'",
        forecaster = "ForecasterRecursive",
        remedy     = _tolerant("RandomForestRegressor"),
        timestamps = TIMESTAMPS,
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_backtest_exog(data, profile, plan, cv_h2o(gap=2))


def test_validate_backtest_exog_DataContentError_lists_at_most_five_columns():
    """
    Test that six columns with a missing value each in the first test fold
    are listed up to five, then "and 1 more", with the plural remedy.
    """
    data = data_h2o.copy()
    columns = ["a", "b", "c", "d", "e", "f"]
    for number, column in enumerate(columns):
        data = with_missing_exog(data, [86 + number], column=column)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data, target="x", exog_columns=columns)
    plan = assistant.plan(profile, steps=12)

    expected = _message(
        where      = "1 of the 3 test folds",
        found      = (
            "'a': 1 value(s), such as '2005-09-01'; 'b': 1 value(s), such as "
            "'2005-10-01'; 'c': 1 value(s), such as '2005-11-01'; 'd': 1 "
            "value(s), such as '2005-12-01'; 'e': 1 value(s), such as "
            "'2006-01-01'; and 1 more"
        ),
        forecaster = "ForecasterRecursive",
        remedy     = (
            "or the plan uses an estimator that accepts missing values (such "
            "as 'RandomForestRegressor'), or the columns are left"
        ),
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_backtest_exog(data, profile.data_profile, plan, cv_h2o())


# =============================================================================
# Tests: several series
# =============================================================================
@pytest.mark.parametrize(
    "forecaster, estimator",
    [
        ("ForecasterRecursiveMultiSeries", "LGBMRegressor"),
        ("ForecasterDirectMultiVariate", "RandomForestRegressor"),
    ],
    ids=["multiseries", "multivariate"],
)
def test_validate_backtest_exog_DataContentError_when_wide_series_share_missing_exog(
    forecaster, estimator
):
    """
    Test that a missing value of 'promo' in a test fold of wide data
    (2012-04-10), which every series reads, raises: skforecast predicts a
    missing value from it and computes the metrics without it, without a
    warning. The estimator offered is the one of the rules for the data
    each forecaster is sized with.
    """
    data = with_missing_exog(data_wide_exog, [100])
    profile, plan = multiseries_exog_of(data, forecaster=forecaster)

    expected = _message(
        where      = "1 of the 12 test folds",
        found      = "'promo': 1 value(s), such as '2012-04-10'",
        forecaster = forecaster,
        remedy     = _tolerant(estimator),
        scored     = SCORED,
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_backtest_exog(data, profile, plan, cv_items_sales())


def test_validate_backtest_exog_DataContentError_when_wide_data_misses_timestamp():
    """
    Test that a missing timestamp of wide data inside a test fold
    (2012-04-10) raises: no series is scored on it, but the missing
    prediction of that date is read by the lag 1 of the next one.
    """
    data = data_wide_exog.drop(index=data_wide_exog.index[[100]])
    profile, plan = multiseries_exog_of(data)

    expected = _message(
        where      = "1 of the 12 test folds",
        found      = "'promo': 1 value(s), such as '2012-04-10'",
        forecaster = "ForecasterRecursiveMultiSeries",
        remedy     = _tolerant("LGBMRegressor"),
        scored     = SCORED,
        timestamps = TIMESTAMPS,
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_backtest_exog(data, profile, plan, cv_items_sales())


def test_validate_backtest_exog_passes_when_no_scored_prediction_is_missing():
    """
    Test that wide data passes with Ridge when the missing value of 'promo'
    is on the last date of a fold (2012-04-11) where no series has a value:
    that prediction is not scored and no later one of the fold reads it.
    """
    data = with_missing_exog(data_wide_exog, [101])
    data.iloc[101, :3] = np.nan
    profile, plan = multiseries_exog_of(data)

    assert validate_backtest_exog(data, profile, plan, cv_items_sales()) is None


def test_validate_backtest_exog_UserWarning_when_wide_series_with_lgbm_read_missing_exog():
    """
    Test that wide data with an estimator that accepts missing values warns,
    without failing, about the missing value of 'promo' that the series
    read on 2012-04-11.
    """
    data = with_missing_exog(data_wide_exog, [101])
    profile, plan = multiseries_exog_of(data, estimator="LGBMRegressor")

    warn_msg = re.escape(
        "The forecaster reads missing values of the exogenous variables to "
        "predict 1 of the 12 test folds ('promo': 1 value(s), such as "
        "'2012-04-11'). LGBMRegressor treats them as missing values; check "
        "that they are meant to be missing."
    )
    with pytest.warns(UserWarning, match=f"^{warn_msg}$"):
        assert validate_backtest_exog(
            data, profile, plan, cv_items_sales()
        ) is None


def test_validate_backtest_exog_DataContentError_names_series_of_long_data():
    """
    Test that, in long format, each series reads its own exogenous values:
    a missing value of 'promo' of 'item_2' in a test fold raises naming the
    series.
    """
    data = data_long_exog.copy()
    data.loc[data.index[data["series"] == "item_2"][100], "promo"] = np.nan
    profile, plan = multiseries_exog_of(data)

    expected = _message(
        where      = "1 of the 12 test folds",
        found      = "'promo' of series 'item_2': 1 value(s), such as '2012-04-10'",
        forecaster = "ForecasterRecursiveMultiSeries",
        remedy     = _tolerant("LGBMRegressor"),
        scored     = SCORED,
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_backtest_exog(data, profile, plan, cv_items_sales())


@pytest.mark.parametrize(
    "position, raises",
    [(2, False), (25, True)],
    ids=["before_forecast", "after_forecast"],
)
def test_validate_backtest_exog_checks_folds_that_forecast_long_series(position, raises):
    """
    Test that a series of long data that starts late ('item_2', its last
    30 days) is checked only in the folds that forecast it, with refit: a
    missing value of 'promo' on its third day (2012-04-02), when no training
    window holds enough of its values, passes; one on 2012-04-25 raises.
    """
    data = long_starting_late(data_long_exog, "item_2", 30)
    data.loc[data.index[data["series"] == "item_2"][position], "promo"] = np.nan
    profile, plan = multiseries_exog_of(data)

    if raises:
        with pytest.raises(DataContentError, match=re.escape("such as '2012-04-25'")):
            validate_backtest_exog(data, profile, plan, cv_items_sales(refit=True))
    else:
        assert validate_backtest_exog(
            data, profile, plan, cv_items_sales(refit=True)
        ) is None


def test_validate_backtest_exog_passes_when_strategy_cannot_be_split():
    """
    Test that a strategy whose initial training window is longer than the
    data is left to its own error.
    """
    assert validate_backtest_exog(
        data_h2o_exog, profile_h2o_exog, plan_h2o_exog_ridge,
        cv_h2o(initial_train_size=200),
    ) is None


# =============================================================================
# Tests: contrast with the backtest of skforecast
# =============================================================================
def _backtest_without_check(monkeypatch, data, profile, plan, cv):
    """
    Run `backtest()` with the check disabled, as skforecast runs the plan:
    return the predictions, or raise the error of the script.
    """
    monkeypatch.setattr(
        assistant_module, "validate_backtest_exog", lambda **kwargs: None
    )
    assistant = ForecastingAssistant()
    # A missing value of the target in a last window leaves a series out of
    # that fold, which a warning says; only the predictions are compared.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=re.escape(LEFT_OUT_OF_FOLDS), category=UserWarning
        )
        result = assistant.backtest(
            data, cv=cv, profile=_profile_result(data, profile), plan=plan,
            show_progress=False,
        )
    return result.predictions


def _profile_result(data, profile):
    """Return the `ForecastingProfile` of `data` for the `DataProfile` given."""
    assistant = ForecastingAssistant()
    kwargs = {"exog_columns": profile.exog_columns, "target": profile.target}
    if profile.data_format == "long":
        kwargs.update(
            date_column=profile.date_column, series_id_column=profile.series_id_column
        )
    # Profiling a target with missing values warns; only the profile is
    # needed.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=MissingValuesWarning)
        return assistant.profile(data, **kwargs)


def _scored_missing(predictions, data):
    """
    Return whether a prediction of the backtest is missing on a date where
    its series has a value (the predictions of several series).
    """
    if "series" in data.columns:
        actual = data.set_index(["series", "date"])["value"]
        keys = zip(predictions["level"], predictions.index)
        values = [actual.get(key, np.nan) for key in keys]
    else:
        values = [
            data.loc[date, level] if date in data.index else np.nan
            for date, level in zip(predictions.index, predictions["level"])
        ]
    observed = pd.notna(np.array(values, dtype=float))
    return bool((predictions["pred"].isna().to_numpy() & observed).any())


@pytest.mark.parametrize(
    "position, kwargs, gap",
    [
        (100, {}, 0),
        (100, {"forecaster": "ForecasterDirect"}, 0),
        (84, {"lags": [13], "window_features": []}, 2),
    ],
    ids=["recursive", "direct", "gap_row"],
)
def test_validate_backtest_exog_matches_skforecast_when_single_series_fails(
    monkeypatch, position, kwargs, gap
):
    """
    Test that the backtest of skforecast fails on the metrics (missing
    predictions at dates with observed values) exactly where the check
    raises before running.
    """
    data = with_missing_exog(data_h2o, [position])
    profile, plan = plan_exog_of(data, **kwargs)
    with pytest.raises(DataContentError):
        validate_backtest_exog(data, profile, plan, cv_h2o(gap=gap))

    err_msg = re.escape("backtesting predictions are NaN at dates with observed values")
    with pytest.raises(ForecastExecutionError, match=err_msg):
        _backtest_without_check(monkeypatch, data, profile, plan, cv_h2o(gap=gap))


def test_validate_backtest_exog_matches_skforecast_when_gap_row_is_not_read(monkeypatch):
    """
    Test that the backtest of skforecast runs without a missing prediction
    where the check passes: a missing value in a row of the gap that lag 13
    does not carry into the fold.
    """
    data = with_missing_exog(data_h2o, [85])
    profile, plan = plan_exog_of(data, lags=[13], window_features=[])
    validate_backtest_exog(data, profile, plan, cv_h2o(gap=2))

    predictions = _backtest_without_check(
        monkeypatch, data, profile, plan, cv_h2o(gap=2)
    )

    assert not predictions["pred"].isna().any()


@pytest.mark.parametrize(
    "case, raises",
    [
        ("wide", True),
        ("wide_unscored", False),
        ("multivariate", True),
        ("long", True),
        ("long_before_forecast", False),
    ],
)
def test_validate_backtest_exog_matches_skforecast_when_several_series(
    monkeypatch, case, raises
):
    """
    Test that the backtest of skforecast of several series gives a missing
    prediction on a date where its series has a value, which its metrics
    leave out without an error, exactly where the check raises.
    """
    cv = cv_items_sales()
    kwargs = {}
    if case.startswith("wide") or case == "multivariate":
        position = 101 if case == "wide_unscored" else 100
        data = with_missing_exog(data_wide_exog, [position])
        if case == "wide_unscored":
            data.iloc[101, :3] = np.nan
        if case == "multivariate":
            kwargs["forecaster"] = "ForecasterDirectMultiVariate"
    elif case == "long":
        data = data_long_exog.copy()
        data.loc[data.index[data["series"] == "item_2"][100], "promo"] = np.nan
    else:
        data = long_starting_late(data_long_exog, "item_2", 30)
        data.loc[data.index[data["series"] == "item_2"][2], "promo"] = np.nan
        cv = cv_items_sales(refit=True)
    profile, plan = multiseries_exog_of(data, **kwargs)

    try:
        validate_backtest_exog(data, profile, plan, cv)
        raised = False
    except DataContentError:
        raised = True
    predictions = _backtest_without_check(monkeypatch, data, profile, plan, cv)

    assert raised is raises
    assert _scored_missing(predictions, data) is raises
