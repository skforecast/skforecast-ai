# Unit test validate_series_lengths

import re

import numpy as np
import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai._last_window import validate_series_lengths
from skforecast_ai.exceptions import InvalidInputError

from tests.fixtures_last_window import (
    data_long,
    data_single,
    data_wide,
    data_wide_many,
    long_starting_late,
    plan_long_foundation,
    plan_long_ridge,
    plan_single_ridge,
    plan_wide_multivariate,
    plan_wide_ridge,
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
@pytest.mark.parametrize("whole_data", [False, True], ids=["pred_eval", "backtest"])
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
    data, profile, plan, whole_data
):
    """
    Test that a series with every value missing is rejected in wide and long
    data, also when only series without values are checked (backtesting).
    """
    err_msg = re.escape(
        "Some series have no values ('item_2'), so "
        "ForecasterRecursiveMultiSeries cannot be trained on them. Remove "
        "them from the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_series_lengths(data, profile, plan, whole_data=whole_data)

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
# Tests: backtesting (whole_data)
# =============================================================================
@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_leading_missing(data_wide, "item_2", 2), profile_wide, plan_wide_ridge),
        (long_starting_late(data_long, "item_2", 1), profile_long, plan_long_ridge),
    ],
    ids=["wide", "long"],
)
def test_validate_series_lengths_passes_when_whole_data_and_series_starts_late(
    data, profile, plan
):
    """
    Test that with `whole_data=True` a short series that is not empty passes
    (skforecast leaves it out of the first folds), though it is rejected in
    prediction mode.
    """
    assert validate_series_lengths(data, profile, plan, whole_data=True) is None
    with pytest.raises(InvalidInputError, match="Some series have, from their"):
        validate_series_lengths(data, profile, plan)


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
    ],
    ids=["multivariate", "foundation", "recursive"],
)
def test_validate_series_lengths_passes_when_forecaster_is_not_multiseries(
    data, profile, plan
):
    """
    Test that the plans of other forecasters are not checked, whatever their
    series.
    """
    assert validate_series_lengths(data, profile, plan) is None


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
