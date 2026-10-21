# Unit test validate_backtest_windows

import re
import warnings

import numpy as np
import pytest
from skforecast.exceptions import MissingValuesWarning
from skforecast.model_selection import TimeSeriesFold

import skforecast_ai.assistant as assistant_module
from skforecast_ai import ForecastingAssistant
from skforecast_ai._last_window import validate_backtest_windows
from skforecast_ai.exceptions import DataContentError, InvalidInputError

from tests.fixtures_last_window import (
    _assistant,
    cv_h2o,
    cv_items_sales,
    data_h2o,
    data_h2o_gaps,
    data_h2o_no_training_row,
    data_single_closed_sundays,
    data_wide,
    plan_h2o_baseline,
    plan_h2o_direct,
    plan_h2o_lgbm,
    plan_h2o_no_training_row_lgbm,
    plan_h2o_no_training_row_ridge,
    plan_h2o_ridge,
    plan_single_closed_ridge,
    plan_wide_multivariate,
    plan_wide_ridge,
    plans_h2o_without_lags,
    profile_h2o,
    profile_h2o_gaps,
    profile_h2o_no_training_row,
    profile_of,
    profile_single_closed,
    profile_wide,
    profile_of_wide,
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
        "would be missing. "
        "Either they are filled in, or the plan uses an estimator that "
        "accepts missing values (such as 'RandomForestRegressor')."
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
        "would be missing. "
        "Either they are filled in, or the plan uses an estimator that "
        "accepts missing values (such as 'RandomForestRegressor')."
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
        "ForecasterEquivalentDate repeats them as missing predictions. Those "
        "values have to be filled in before predicting."
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


def test_validate_backtest_windows_DataContentError_when_fold_reads_missing():
    """
    Test that the error for a missing value that a test fold reads is a
    DataContentError, the class that tells a problem of the content of the
    data from an argument to correct, with the code and the field of an
    InvalidInputError.
    """
    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict 1 of "
        "the 3 test folds ('x': 1 value(s), such as '2004-10-01'). "
        "ForecasterRecursive with Ridge cannot use them, so its predictions "
        "would be missing. "
        "Either they are filled in, or the plan uses an estimator that "
        "accepts missing values (such as 'RandomForestRegressor')."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_backtest_windows(
            data_h2o_gaps, profile_h2o_gaps, plan_h2o_ridge, cv_h2o()
        )

    assert type(exc_info.value) is DataContentError
    assert (exc_info.value.code, exc_info.value.field) == (
        "invalid_argument", "data"
    )


# =============================================================================
# Tests: training rows
# =============================================================================
def test_validate_backtest_windows_DataContentError_when_no_training_row_is_left():
    """
    Test that a strategy whose first training window (84 months) has no row
    that reads no missing value raises before running, for a plan with
    Ridge that drops those rows (`dropna_from_series`): skforecast failed
    inside the script with "All samples have been removed due to NaNs" and
    the advice `dropna_from_series=False`, which the plan rejects for Ridge
    (c_06 of the audit). The remedy names the estimator of the rules for 120
    observations.
    """
    err_msg = re.escape(
        "Every training row of the backtest from 1998-07-01 to 2005-06-01 "
        "reads a missing value of the target (2 value(s), such as "
        "'1999-08-01', '2002-09-01'): ForecasterRecursive with Ridge drops "
        "the rows whose lags, window features or target read one "
        "(`dropna_from_series`), so skforecast would have no row to train on. "
        "An estimator that accepts missing values (such as "
        "'RandomForestRegressor') trains on them; otherwise, use shorter lags "
        "and window features, which read fewer values, or fill in the missing "
        "values, after asking the user."
    )
    with pytest.raises(DataContentError, match=err_msg) as exc_info:
        validate_backtest_windows(
            data_h2o_no_training_row,
            profile_h2o_no_training_row,
            plan_h2o_no_training_row_ridge,
            cv_h2o(),
        )

    assert (exc_info.value.code, exc_info.value.field) == (
        "invalid_argument", "data"
    )


@pytest.mark.parametrize(
    "plan, cv",
    [
        (plan_h2o_no_training_row_lgbm, cv_h2o()),
        (plan_h2o_no_training_row_ridge, cv_h2o(initial_train_size=96)),
    ],
    ids=["estimator_accepts_missing_values", "later_window_with_rows"],
)
def test_validate_backtest_windows_no_error_when_training_rows_are_left(plan, cv):
    """
    Test that the same data passes with LGBMRegressor, which keeps the rows
    with missing values (`dropna_from_series=False`), and with Ridge on a
    training window of 96 months, whose rows of targets 87 to 95 read none.
    """
    validate_backtest_windows(
        data_h2o_no_training_row, profile_h2o_no_training_row, plan, cv
    )


def test_validate_backtest_windows_DataContentError_names_closed_days_of_training_rows():
    """
    Test that, when the missing values that leave no training row are days
    the target never has a value on (daily data without Sundays, a rolling
    mean of 7 that always holds one), the advice of the closed days comes
    first (D9).
    """
    plan = plan_single_closed_ridge.model_copy(
        update={
            "forecaster_kwargs": {
                **plan_single_closed_ridge.forecaster_kwargs,
                "window_features": [{"stats": ["mean"], "window_size": 7}],
            }
        },
        deep=True,
    )

    err_msg = re.escape(
        "Every training row of the backtest from 2023-01-02 to 2023-02-10 "
        "reads a missing value of the target (5 value(s), such as "
        "'2023-01-08', '2023-01-15', '2023-01-22', '2023-01-29', '2023-02-05'): "
        "ForecasterRecursive with Ridge drops the rows whose lags, window "
        "features or target read one (`dropna_from_series`), so skforecast "
        "would have no row to train on. If the business is closed on Sundays, "
        "fill them with 0 in the data, after asking the user; otherwise, an "
        "estimator that accepts missing values (such as "
        "'RandomForestRegressor') trains on them, or use shorter lags and "
        "window features, which read fewer values, or impute them."
    )
    with pytest.raises(DataContentError, match=err_msg):
        validate_backtest_windows(
            data_single_closed_sundays,
            profile_single_closed,
            plan,
            TimeSeriesFold(steps=3, initial_train_size=40, verbose=False),
        )


# =============================================================================
# Tests: ForecasterDirectMultiVariate
# =============================================================================
# The plan of ForecasterDirectMultiVariate on the three items_sales series
# (level 'item_1') reads the lags 1 and 5 of every series; the 12 test
# folds of `cv_items_sales()` start at the positions 84, 87, ..., 117, so a
# value at the position 97 (2012-04-07) is lag 5 of the fold that starts at
# 102, and the one at 98 (2012-04-08) is the last value before the fold
# that starts at 99.
plan_wide_multivariate_lgbm = plan_wide_multivariate.model_copy(
    update={"estimator": "LGBMRegressor"}, deep=True
)
plan_wide_multivariate_lgbm_differenced = plan_wide_multivariate_lgbm.model_copy(
    update={
        "forecaster_kwargs": {
            **plan_wide_multivariate_lgbm.forecaster_kwargs, "differentiation": 1
        }
    },
    deep=True,
)


def _wide_missing(column, position):
    """
    Return items_sales in wide format with `column` missing at `position`
    (counting from 0), and its profile.
    """
    data = data_wide.copy()
    data.iloc[position, data.columns.get_loc(column)] = np.nan
    with warnings.catch_warnings():
        # Profiling a target with missing values warns; only the profile is
        # needed.
        warnings.simplefilter("ignore", category=MissingValuesWarning)
        profile = profile_of_wide(data)
    return data, profile


def _multivariate_message(column, date, why):
    """Return the error of a missing value that a fold of DMV reads."""
    return (
        f"The forecaster reads missing values of the target to predict 1 of "
        f"the 12 test folds ({column!r}: 1 value(s), such as '{date}'). {why}"
    )


@pytest.mark.parametrize("column", ["item_1", "item_2"], ids=["level", "other_series"])
def test_validate_backtest_windows_DataContentError_when_multivariate_window_has_missing(
    column,
):
    """
    Test that a missing value in the window of a fold of
    ForecasterDirectMultiVariate raises for Ridge, in its level and in any
    other series: skforecast never leaves a series out of the window, so
    the predictions of the level would be missing, and its metrics would
    leave them out without a warning.
    """
    data, profile = _wide_missing(column, 97)

    expected = _multivariate_message(
        column, "2012-04-07",
        "ForecasterDirectMultiVariate with Ridge cannot use them, so its "
        "predictions would be missing. Either they are filled in, or the plan "
        "uses an estimator that accepts missing values (such as "
        "'RandomForestRegressor').",
    )
    with pytest.raises(DataContentError, match=re.escape(expected)) as exc_info:
        validate_backtest_windows(
            data, profile, plan_wide_multivariate, cv_items_sales()
        )

    assert (exc_info.value.code, exc_info.value.field) == ("invalid_argument", "data")


@pytest.mark.parametrize(
    "plan, column, position",
    [
        (plan_wide_multivariate_lgbm, "item_2", 97),
        (plan_wide_multivariate_lgbm_differenced, "item_2", 98),
    ],
    ids=["lgbm", "lgbm_differentiation_other_series"],
)
def test_validate_backtest_windows_UserWarning_when_multivariate_estimator_tolerates(
    plan, column, position
):
    """
    Test that LGBMRegressor only warns, also with the differentiation when
    the missing value is the last one of a series other than the level,
    whose inverse is not computed.
    """
    data, profile = _wide_missing(column, position)

    expected = (
        f"The forecaster reads missing values of the target to predict 1 of "
        f"the 12 test folds ({column!r}: 1 value(s), such as "
        f"'{data.index[position].date()}'). LGBMRegressor treats them as "
        f"missing values; check that they are meant to be missing."
    )
    with pytest.warns(UserWarning, match=re.escape(expected)):
        validate_backtest_windows(data, profile, plan, cv_items_sales())


def test_validate_backtest_windows_DataContentError_when_multivariate_inverse_reads_missing():
    """
    Test that, with the differentiation, the last value of the level before
    a fold raises whatever the estimator: the inverse of the
    differentiation starts from it.
    """
    data, profile = _wide_missing("item_1", 98)

    expected = _multivariate_message(
        "item_1", "2012-04-08",
        "The differentiation of ForecasterDirectMultiVariate reads the last 1 "
        "value(s), so its predictions would be missing. Those values have to "
        "be filled in before predicting.",
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_backtest_windows(
            data, profile, plan_wide_multivariate_lgbm_differenced, cv_items_sales()
        )


def test_validate_backtest_windows_passes_when_multivariate_missing_is_not_read():
    """
    Test that a missing value of ForecasterDirectMultiVariate that no window
    reads (in the first training rows) passes.
    """
    data, profile = _wide_missing("item_2", 30)

    validate_backtest_windows(
        data, profile, plan_wide_multivariate, cv_items_sales()
    )


@pytest.mark.parametrize(
    "plan, column, position, missing",
    [
        (plan_wide_multivariate, "item_2", 97, True),
        (plan_wide_multivariate_lgbm, "item_2", 97, False),
        (plan_wide_multivariate_lgbm_differenced, "item_1", 98, True),
        (plan_wide_multivariate_lgbm_differenced, "item_2", 98, False),
    ],
    ids=["ridge", "lgbm", "lgbm_differentiation_level", "lgbm_differentiation_other"],
)
def test_validate_backtest_windows_matches_skforecast_for_multivariate(
    monkeypatch, plan, column, position, missing
):
    """
    Test that the backtest of skforecast predicts a missing value of the
    level, which its metrics leave out without an error, exactly where the
    check raises (with a tolerant estimator, it only warns).
    """
    data, profile = _wide_missing(column, position)
    monkeypatch.setattr(
        assistant_module, "validate_backtest_windows", lambda **kwargs: None
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=MissingValuesWarning)
        profile_result = _assistant.profile(data, target=list(data.columns))

    result = ForecastingAssistant().backtest(
        data, cv=cv_items_sales(), profile=profile_result, plan=plan,
        show_progress=False,
    )

    predictions = result.predictions
    scored = data["item_1"].reindex(predictions.index).notna().to_numpy()
    assert bool((predictions["pred"].isna().to_numpy() & scored).any()) is missing
