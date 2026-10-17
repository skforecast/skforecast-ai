# Unit test validate_series_lengths

import re

import numpy as np
import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai._last_window import validate_series_lengths
from skforecast_ai.exceptions import InvalidInputError

from tests.fixtures_last_window import (
    cv_items_sales,
    data_long,
    data_single,
    data_wide,
    data_wide_many,
    long_ending_early,
    long_starting_late,
    plan_long_foundation,
    plan_long_lgbm,
    plan_long_ridge,
    plan_single_ridge,
    plan_wide_lgbm,
    plan_wide_multivariate,
    plan_wide_ridge,
    plans_single_without_lags,
    profile_long,
    profile_single,
    profile_wide,
    profile_wide_many,
    with_leading_missing,
)

_assistant = ForecastingAssistant()

# The plans of the fixtures have lags [1, 5] and a rolling mean of 3: the
# forecaster reads a window of 5 values. The wide and long data end on
# 2012-04-29.
_NO_MORE = "no more values than the 5 that ForecasterRecursiveMultiSeries reads"
_USE = "Use shorter lags and window features, or remove those series."


def _short_message(found, where=""):
    """Return the message for series with `found` ('item_2': 5) values."""
    return (
        f"Some series have, from their first to their last value{where}, {_NO_MORE} to build "
        f"its predictors ({found}), so it cannot be trained on them. {_USE}"
    )


# =============================================================================
# Tests: prediction mode
# =============================================================================
@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_leading_missing(data_wide, "item_2", 5), profile_wide, plan_wide_ridge),
        (long_starting_late(data_long, "item_2", 5), profile_long, plan_long_ridge),
    ],
    ids=["wide", "long"],
)
def test_validate_series_lengths_InvalidInputError_when_series_has_window_values(
    data, profile, plan
):
    """
    Test that a series with as many values as the window (5) from its first
    one is rejected in prediction mode, in wide and long data: skforecast
    fails when `len(y) <= window_size`.
    """
    err_msg = re.escape(_short_message("'item_2': 5"))
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_series_lengths(data, profile, plan)

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Use lags and window features of at most 4 observations, or remove "
        "the short series."
    )


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_leading_missing(data_wide, "item_2", 6), profile_wide, plan_wide_ridge),
        (long_starting_late(data_long, "item_2", 6), profile_long, plan_long_ridge),
    ],
    ids=["wide", "long"],
)
def test_validate_series_lengths_passes_when_series_has_one_more_value_than_window(
    data, profile, plan
):
    """
    Test that a series with one more value than the window (6 against 5) is
    accepted: the boundary matches skforecast's `len(y) <= window_size`.
    """
    assert validate_series_lengths(data, profile, plan) is None


def test_validate_series_lengths_counts_missing_values_between_first_and_last():
    """
    Test that the length of a series is measured from its first to its last
    value, as skforecast trims the missing values at both ends: a missing
    value inside it does not shorten it (6 values from the first to the last
    one, one of them missing, pass; with 5 they are rejected).
    """
    data = with_leading_missing(data_wide, "item_2", 6)
    data.loc[data.index[-3], "item_2"] = np.nan

    assert validate_series_lengths(data, profile_wide, plan_wide_ridge) is None

    data = with_leading_missing(data_wide, "item_2", 5)
    data.loc[data.index[-3], "item_2"] = np.nan
    err_msg = re.escape(_short_message("'item_2': 5"))
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_series_lengths(data, profile_wide, plan_wide_ridge)


@pytest.mark.parametrize("n_trailing", [1, 30])
def test_validate_series_lengths_InvalidInputError_when_series_ends_with_missing_values(
    n_trailing,
):
    """
    Test that a series with values only at its start (5 values, then
    missing to the end) is rejected: trailing missing values shorten it.
    """
    data = data_wide.assign(item_2=np.nan)
    data.iloc[-n_trailing - 5:-n_trailing, data.columns.get_loc("item_2")] = 1.0

    err_msg = re.escape(_short_message("'item_2': 5"))
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_series_lengths(data, profile_wide, plan_wide_ridge)

    assert exc_info.value.code == "insufficient_data"


def test_validate_series_lengths_InvalidInputError_lists_at_most_five_series():
    """
    Test that the message names the first 5 short series and counts the
    others (7 series with 3 values each).
    """
    found = ", ".join(f"'s{number}': 3" for number in range(1, 6))
    err_msg = re.escape(_short_message(f"{found} and 2 more"))
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_series_lengths(data_wide_many, profile_wide_many, plan_wide_ridge)


# =============================================================================
# Tests: series without values
# =============================================================================
@pytest.mark.parametrize("cv", [None, cv_items_sales()], ids=["pred_eval", "backtest"])
@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (
            data_wide.assign(item_2=np.nan), profile_wide, plan_wide_ridge,
        ),
        (
            data_long.assign(
                value=np.where(data_long["series"] == "item_2", np.nan,
                               data_long["value"])
            ),
            profile_long, plan_long_ridge,
        ),
    ],
    ids=["wide", "long"],
)
def test_validate_series_lengths_InvalidInputError_when_series_has_no_values(
    data, profile, plan, cv
):
    """
    Test that a series with every value missing is rejected in wide and long
    data, also in backtesting, where the series are checked on the folds.
    """
    err_msg = re.escape(
        "Some series have no values ('item_2'), so "
        "ForecasterRecursiveMultiSeries cannot be trained on them. Remove "
        "them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_series_lengths(data, profile, plan, cv=cv)

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == "Remove the series without values from the data."


def test_validate_series_lengths_InvalidInputError_lists_at_most_five_empty_series():
    """
    Test that the message names the first 5 series without values and counts
    the others (7 series).
    """
    data = data_wide_many.assign(**{c: np.nan for c in data_wide_many.columns})

    err_msg = re.escape(
        "Some series have no values ('s1', 's2', 's3', 's4', 's5' and 2 more), "
        "so ForecasterRecursiveMultiSeries cannot be trained on them. Remove "
        "them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_series_lengths(data, profile_wide_many, plan_wide_ridge)


def test_validate_series_lengths_reports_empty_series_before_short_ones():
    """
    Test that, with an empty and a short series, the empty one is reported.
    """
    data = with_leading_missing(data_wide, "item_1", 3).assign(item_2=np.nan)

    err_msg = re.escape("Some series have no values ('item_2')")
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_series_lengths(data, profile_wide, plan_wide_ridge)


# =============================================================================
# Tests: evaluation mode
# =============================================================================
def test_validate_series_lengths_InvalidInputError_when_series_has_no_values_up_to_end_train():
    """
    Test that, in evaluation mode, a series whose only values come after the
    end of training (2012-04-24, 5 values in the test partition) is
    rejected.
    """
    data = with_leading_missing(data_wide, "item_2", 5)

    err_msg = re.escape(
        "Some series have no values up to the end of training (2012-04-24) "
        "('item_2'), so ForecasterRecursiveMultiSeries cannot be trained on "
        "them. Remove them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_series_lengths(
            data, profile_wide, plan_wide_ridge, end_train="2012-04-24"
        )

    assert exc_info.value.field == "data"


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_leading_missing(data_wide, "item_2", 10), profile_wide, plan_wide_ridge),
        (long_starting_late(data_long, "item_2", 10), profile_long, plan_long_ridge),
    ],
    ids=["wide", "long"],
)
def test_validate_series_lengths_checks_training_partition_only(data, profile, plan):
    """
    Test that in evaluation mode the length of a series is that of its
    training partition: with 10 values in the whole data and the end of
    training at 2012-04-24, it has 5 values there and is rejected; the same
    data is accepted in prediction mode.
    """
    assert validate_series_lengths(data, profile, plan) is None

    err_msg = re.escape(
        _short_message("'item_2': 5", " up to the end of training (2012-04-24)")
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_series_lengths(data, profile, plan, end_train="2012-04-24")


def test_validate_series_lengths_passes_when_training_partition_is_long_enough():
    """
    Test that in evaluation mode a series with 6 values up to the end of
    training (2012-04-24) is accepted.
    """
    data = with_leading_missing(data_wide, "item_2", 11)

    assert validate_series_lengths(
        data, profile_wide, plan_wide_ridge, end_train="2012-04-24"
    ) is None


# =============================================================================
# Tests: backtesting (cv)
# =============================================================================
def _never_message(found, short, late):
    """
    Return the message for series that no fold forecasts, `found` as
    "'item_2': 30", with the sentences of series no longer than the window
    (`short`) and of longer ones (`late`).
    """
    rejected = (
        " `forecast()` of this plan rejects them too." if short and not late
        else " `forecast()` of this plan rejects those with no more than 5 too."
        if short else ""
    )
    later = (
        ", or a later `initial_train_size`, so that the training windows hold "
        "more of their observations"
        if late else ""
    )
    return (
        f"Some series cannot be forecast in any fold of the backtest ({found} "
        f"observations, from their first to their last value). "
        f"ForecasterRecursiveMultiSeries forecasts a series in a fold only when "
        f"the training window of the fold has more than the 5 observations of "
        f"it that it reads to build its predictors, and the series has the 5 "
        f"dates before the fold; skforecast leaves the other series out without "
        f"a warning, so they would get no predictions and no metrics, and the "
        f"average across series would leave them out.{rejected} Remove those "
        f"series, or use shorter lags and window features{later}."
    )


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_leading_missing(data_wide, "item_2", 30), profile_wide, plan_wide_ridge),
        (with_leading_missing(data_wide, "item_2", 30), profile_wide, plan_wide_lgbm),
        (long_starting_late(data_long, "item_2", 30), profile_long, plan_long_ridge),
    ],
    ids=["wide", "wide_lgbm", "long"],
)
def test_validate_series_lengths_InvalidInputError_when_series_starts_after_training(
    data, profile, plan
):
    """
    Test that, in a backtest without refit, a series whose 30 values start
    after the first 84 days, where the forecaster is trained once, is
    rejected in wide and long data: skforecast does not forecast it in any
    fold. It is accepted in prediction mode (30 values against a window of
    5).
    """
    assert validate_series_lengths(data, profile, plan) is None

    expected = _never_message("'item_2': 30", short=False, late=True)
    with pytest.raises(InvalidInputError, match=re.escape(expected)) as exc_info:
        validate_series_lengths(data, profile, plan, cv=cv_items_sales())

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Remove those series, or use shorter lags and window features, or a "
        "later `initial_train_size`, so that the training windows hold more of "
        "their observations."
    )


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_leading_missing(data_wide, "item_2", 5), profile_wide, plan_wide_ridge),
        (long_starting_late(data_long, "item_2", 5), profile_long, plan_long_ridge),
    ],
    ids=["wide", "long"],
)
@pytest.mark.parametrize("refit", [False, True], ids=["no_refit", "refit"])
def test_validate_series_lengths_InvalidInputError_when_series_is_not_longer_than_window(
    data, profile, plan, refit
):
    """
    Test that, in a backtest, a series with as many values as the window (5)
    is rejected, with or without refit, in wide and long data, and that the
    message says that `forecast()` of the plan rejects it too.
    """
    expected = _never_message("'item_2': 5", short=True, late=False)
    with pytest.raises(InvalidInputError, match=re.escape(expected)) as exc_info:
        validate_series_lengths(data, profile, plan, cv=cv_items_sales(refit=refit))

    assert exc_info.value.hint == (
        "Remove those series, or use shorter lags and window features."
    )


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_leading_missing(data_wide, "item_2", 30), profile_wide, plan_wide_ridge),
        (long_starting_late(data_long, "item_2", 30), profile_long, plan_long_ridge),
    ],
    ids=["wide", "long"],
)
def test_validate_series_lengths_passes_when_series_starts_late_and_a_fold_forecasts_it(
    data, profile, plan
):
    """
    Test that a series that starts late (30 values, from position 90) passes
    a backtest with refit, which trains on it in the later folds, and one
    without refit whose first training window holds more than the window of
    its values (100 days, 10 of them).
    """
    assert validate_series_lengths(
        data, profile, plan, cv=cv_items_sales(refit=True)
    ) is None
    assert validate_series_lengths(
        data, profile, plan, cv=cv_items_sales(initial_train_size=100)
    ) is None


def test_validate_series_lengths_InvalidInputError_names_short_and_late_series():
    """
    Test that a series no longer than the window (4 values) and a longer one
    that starts after the training window (30 values) are named together,
    with the sentences of both.
    """
    data = with_leading_missing(
        with_leading_missing(data_wide, "item_2", 30), "item_3", 4
    )

    expected = _never_message("'item_2': 30, 'item_3': 4", short=True, late=True)
    with pytest.raises(InvalidInputError, match=re.escape(expected)):
        validate_series_lengths(
            data, profile_wide, plan_wide_ridge, cv=cv_items_sales()
        )


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (data_wide.assign(item_2=np.nan), profile_wide, plan_wide_ridge),
        (long_ending_early(data_long, "item_2", 60), profile_long, plan_long_ridge),
        (long_ending_early(data_long, "item_2", 60), profile_long, plan_long_lgbm),
    ],
    ids=["wide", "long", "long_lgbm"],
)
def test_validate_series_lengths_InvalidInputError_when_series_ends_before_folds(
    data, profile, plan
):
    """
    Test that a series whose values end before the folds (its first 60 days)
    is rejected in a backtest: in long format, whatever the estimator, its
    dates do not reach the window before any fold; in wide format, with an
    estimator that does not accept missing values, the window of every fold
    is missing. A later `initial_train_size` is not offered: it does not
    help a series that has ended.
    """
    if profile.data_format == "wide":
        data.iloc[:60, data.columns.get_loc("item_2")] = data_wide["item_2"].iloc[:60]

    expected = _never_message("'item_2': 60", short=False, late=False)
    with pytest.raises(InvalidInputError, match=re.escape(expected)) as exc_info:
        validate_series_lengths(data, profile, plan, cv=cv_items_sales())

    assert exc_info.value.hint == (
        "Remove those series, or use shorter lags and window features."
    )


def test_validate_series_lengths_passes_when_wide_series_ends_before_folds_with_lgbm():
    """
    Test that, in wide format, a series whose values end before the folds
    passes with an estimator that accepts missing values: skforecast keeps
    its window, all missing, and forecasts it.
    """
    data = data_wide.copy()
    data.iloc[60:, data.columns.get_loc("item_2")] = np.nan

    assert validate_series_lengths(
        data, profile_wide, plan_wide_lgbm, cv=cv_items_sales()
    ) is None


def test_validate_series_lengths_InvalidInputError_lists_at_most_five_never_forecast():
    """
    Test that the message names the first 5 series that no fold forecasts
    and counts the others (7 series with 3 values each).
    """
    found = ", ".join(f"'s{number}': 3" for number in range(1, 6))
    expected = _never_message(f"{found} and 2 more", short=True, late=False)
    with pytest.raises(InvalidInputError, match=re.escape(expected)):
        validate_series_lengths(
            data_wide_many, profile_wide_many, plan_wide_ridge,
            cv=cv_items_sales(initial_train_size=40),
        )


def test_validate_series_lengths_passes_when_strategy_cannot_be_split():
    """
    Test that a strategy that cannot be split on the data (an initial
    training window longer than the data) is not checked: the check of the
    first training window reports it.
    """
    data = with_leading_missing(data_wide, "item_2", 5)

    assert validate_series_lengths(
        data, profile_wide, plan_wide_ridge,
        cv=cv_items_sales(initial_train_size=200),
    ) is None


# =============================================================================
# Tests: not checked
# =============================================================================
@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (data_wide.assign(item_2=np.nan), profile_wide, plan_wide_multivariate),
        (
            long_starting_late(data_long, "item_2", 1),
            profile_long, plan_long_foundation,
        ),
        (data_single.assign(y=np.nan), profile_single, plan_single_ridge),
        (
            data_single.assign(y=np.nan), profile_single,
            plans_single_without_lags["foundation"],
        ),
    ],
    ids=["multivariate", "foundation", "recursive", "foundation_single"],
)
def test_validate_series_lengths_passes_when_forecaster_is_not_multiseries(
    data, profile, plan
):
    """
    Test that the plans of other forecasters are not checked, whatever their
    series: a ForecasterFoundation model reads no window, so a series with
    one value passes, and on a single series it is not checked at all.
    """
    assert validate_series_lengths(data, profile, plan) is None


# =============================================================================
# Tests: ForecasterFoundation on several series
# =============================================================================
@pytest.mark.parametrize(
    "kwargs, where",
    [
        ({}, ""),
        ({"cv": cv_items_sales()}, ""),
        ({"end_train": "2012-04-22"}, " up to the end of training (2012-04-22)"),
    ],
    ids=["prediction", "backtesting", "evaluation"],
)
def test_validate_series_lengths_InvalidInputError_when_foundation_series_has_no_values(
    kwargs, where
):
    """
    Test that a series without values is rejected for a ForecasterFoundation
    plan on several series, in prediction, backtesting and evaluation mode,
    where skforecast failed inside the script ("All values of series
    'item_2' are NaN").
    """
    data = data_long.assign(
        value=np.where(data_long["series"] == "item_2", np.nan, data_long["value"])
    )

    err_msg = re.escape(
        f"Some series have no values{where} ('item_2'), so ForecasterFoundation "
        "has no values to predict them from. Remove them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_series_lengths(data, profile_long, plan_long_foundation, **kwargs)

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == "Remove the series without values from the data."


def test_validate_series_lengths_InvalidInputError_when_foundation_series_starts_in_test():
    """
    Test that, in evaluation mode, a series of a ForecasterFoundation plan
    whose first value comes after the end of training (2012-04-22, 5 values
    in the test split) is rejected, and accepted in prediction mode.
    """
    data = long_starting_late(data_long, "item_2", 5)

    assert validate_series_lengths(data, profile_long, plan_long_foundation) is None
    err_msg = re.escape(
        "Some series have no values up to the end of training (2012-04-22) "
        "('item_2'), so ForecasterFoundation has no values to predict them from."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_series_lengths(
            data, profile_long, plan_long_foundation, end_train="2012-04-22"
        )


def test_validate_series_lengths_passes_when_long_data_cannot_be_read():
    """
    Test that long-format data the generated code cannot read (a profile
    without frequency) is not checked: the script fails with its own error.
    """
    profile = profile_long.model_copy(update={"frequency": None})
    data = long_starting_late(data_long, "item_2", 1)

    assert validate_series_lengths(data, profile, plan_long_ridge) is None


# =============================================================================
# Tests: time zone of the dates
# =============================================================================
def test_validate_series_lengths_compares_end_train_in_time_zone_of_dates():
    """
    Test that `end_train`, written without a time zone, is compared in the
    time zone of a UTC daily index in evaluation mode: no TypeError, and the
    training partition (up to 2012-04-24) is the one checked.
    """
    data = with_leading_missing(data_wide, "item_2", 10)
    data.index = data.index.tz_localize("UTC")
    profile = _assistant.profile(data, target=list(data.columns)).data_profile

    assert validate_series_lengths(data, profile, plan_wide_ridge) is None
    err_msg = re.escape(
        _short_message("'item_2': 5", " up to the end of training (2012-04-24)")
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_series_lengths(
            data, profile, plan_wide_ridge, end_train="2012-04-24"
        )
