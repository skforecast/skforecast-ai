# Unit test validate_training_rows

import re

import pytest
from skforecast.exceptions import MissingValuesWarning

import skforecast_ai.assistant as assistant_module
from skforecast_ai import ForecastingAssistant
from skforecast_ai._last_window import validate_training_rows
from skforecast_ai.exceptions import DataContentError, ForecastExecutionError

from tests.fixtures_last_window import (
    _assistant,
    _profile_h2o_no_forecast_row,
    _profile_single_closed,
    data_h2o_no_forecast_row,
    data_h2o_no_training_row,
    data_single_closed_sundays,
    data_wide,
    in_evaluation,
    plan_h2o_no_forecast_row_lgbm,
    plan_h2o_no_forecast_row_ridge,
    plan_h2o_no_training_row_ridge,
    plan_wide_ridge,
    plans_h2o_without_lags,
    profile_h2o_no_forecast_row,
    profile_h2o_no_training_row,
    profile_single_closed,
    profile_wide,
    with_missing,
)

REMEDY = (
    "An estimator that accepts missing values (such as "
    "'RandomForestRegressor') trains on them; otherwise, use shorter lags and "
    "window features, which read fewer values, or fill in the missing "
    "values, after asking the user."
)


def _message(span, found, remedy=REMEDY):
    """Return the error of a forecast without rows to train on."""
    return (
        f"Every training row of the forecast from {span} reads a missing value "
        f"of the target ({found}): ForecasterRecursive with Ridge drops the "
        f"rows whose lags, window features or target read one "
        f"(`dropna_from_series`), so skforecast would have no row to train "
        f"on. {remedy}"
    )


_FOUR = "4 value(s), such as '1999-08-01', '2002-07-01', '2005-06-01', '2006-04-01'"


@pytest.mark.parametrize(
    "plan, span",
    [
        (plan_h2o_no_forecast_row_ridge, "1998-07-01 to 2008-06-01"),
        (
            in_evaluation(plan_h2o_no_forecast_row_ridge, "2007-06-01"),
            "1998-07-01 to 2007-06-01",
        ),
    ],
    ids=["prediction", "evaluation"],
)
def test_validate_training_rows_DataContentError_when_every_row_reads_missing_value(
    plan, span
):
    """
    Test that a forecast whose training rows all read a missing value of
    the target (the rolling mean of 36 reaches one of the 4 missing values
    from every row) raises with the remedies, with field 'data': on the
    whole data in prediction mode, and up to `end_train` in evaluation
    mode.
    """
    expected = _message(span, _FOUR)
    with pytest.raises(DataContentError, match=re.escape(expected)) as exc_info:
        validate_training_rows(
            data_h2o_no_forecast_row, profile_h2o_no_forecast_row, plan
        )

    assert (exc_info.value.code, exc_info.value.field) == ("invalid_argument", "data")


def test_validate_training_rows_checks_training_partition_only():
    """
    Test that the data of c_06 of the audit (the target missing in 1999-08-01
    and 2002-09-01) trains on its whole data, whose last rows read no
    missing value, but raises in evaluation mode up to 2005-06-01, where
    every row reads one.
    """
    assert validate_training_rows(
        data_h2o_no_training_row, profile_h2o_no_training_row,
        plan_h2o_no_training_row_ridge,
    ) is None

    expected = _message(
        "1998-07-01 to 2005-06-01", "2 value(s), such as '1999-08-01', '2002-09-01'"
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_training_rows(
            data_h2o_no_training_row, profile_h2o_no_training_row,
            in_evaluation(plan_h2o_no_training_row_ridge, "2005-06-01"),
        )


def test_validate_training_rows_DataContentError_names_closed_days():
    """
    Test that the missing values of a shop closed on Sundays, which a
    rolling mean of 7 reads from every row, get the advice of the closed
    days first.
    """
    plan = _assistant.plan(
        _profile_single_closed,
        estimator       = "Ridge",
        steps           = 3,
        lags            = [1],
        window_features = [{"stats": ["mean"], "window_size": 7}],
    )

    expected = _message(
        "2023-01-02 to 2023-03-01",
        "8 value(s), such as '2023-01-08', '2023-01-15', '2023-01-22', "
        "'2023-01-29', '2023-02-05' and 3 more",
        remedy = (
            "If the business is closed on Sundays, fill them with 0 in the "
            "data, after asking the user; otherwise, an estimator that "
            "accepts missing values (such as 'RandomForestRegressor') trains "
            "on them, or use shorter lags and window features, which read "
            "fewer values, or impute them."
        ),
    )
    with pytest.raises(DataContentError, match=re.escape(expected)):
        validate_training_rows(data_single_closed_sundays, profile_single_closed, plan)


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (
            data_h2o_no_forecast_row, profile_h2o_no_forecast_row,
            plan_h2o_no_forecast_row_lgbm,
        ),
        (
            data_h2o_no_forecast_row, profile_h2o_no_forecast_row,
            plans_h2o_without_lags["stats"],
        ),
        (with_missing(data_wide, [2], column="item_1"), profile_wide, plan_wide_ridge),
    ],
    ids=["lgbm", "stats", "several_series"],
)
def test_validate_training_rows_passes_when_plan_is_not_concerned(data, profile, plan):
    """
    Test that an estimator that accepts missing values (the plan does not
    drop the rows that read one), a forecaster without lags and several
    series are not checked.
    """
    assert validate_training_rows(data, profile, plan) is None


@pytest.mark.parametrize("test_size", [None, 12], ids=["prediction", "evaluation"])
def test_validate_training_rows_matches_skforecast(monkeypatch, test_size):
    """
    Test that the script of the forecast fails inside skforecast with "All
    samples have been removed due to NaNs" where the check raises, in
    prediction mode and with `test_size`; skforecast warns first about the
    rows it drops.
    """
    profile = _profile_h2o_no_forecast_row
    plan = plan_h2o_no_forecast_row_ridge
    with pytest.raises(DataContentError, match="Every training row of the forecast"):
        ForecastingAssistant().forecast(
            data_h2o_no_forecast_row, profile=profile, plan=plan, test_size=test_size
        )

    monkeypatch.setattr(
        assistant_module, "validate_training_rows", lambda **kwargs: None
    )
    with pytest.warns(MissingValuesWarning, match="NaNs detected"):
        with pytest.raises(
            ForecastExecutionError, match="All samples have been removed"
        ):
            ForecastingAssistant().forecast(
                data_h2o_no_forecast_row, profile=profile, plan=plan,
                test_size=test_size,
            )
