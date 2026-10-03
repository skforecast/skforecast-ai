# Unit test validate_evaluation_partition

import re

import numpy as np
import pytest

from skforecast_ai._last_window import validate_evaluation_partition
from skforecast_ai.exceptions import InvalidInputError

from tests.fixtures_last_window import (
    data_long,
    data_single,
    data_wide,
    data_wide_seven,
    in_evaluation,
    plan_long_multiseries_eval,
    plan_single_lgbm_eval,
    plan_single_ridge,
    plan_single_ridge_eval,
    plan_wide_multiseries_eval,
    plan_wide_seven_eval,
    profile_long,
    profile_single,
    profile_wide,
    profile_wide_seven,
    with_missing,
    with_missing_long,
)
from skforecast_ai import ForecastingAssistant

_END_MESSAGE = (
    "ForecasterRecursiveMultiSeries does not predict a series that ends before "
    "the others, and when no series has a value there it starts the forecast "
    "earlier, so the metrics would compare other dates. Choose another "
    "`test_size`, or fill in those values."
)
_TEST_MESSAGE = (
    "skforecast cannot compute the metrics on them, whatever the estimator. "
    "Impute the target, or evaluate on dates without missing values."
)
_READS_RIDGE = (
    "ForecasterRecursive with Ridge cannot use them, so its predictions would "
    "be missing: fill them in."
)
_READS_LGBM = (
    "LGBMRegressor treats them as missing values; check that they are meant "
    "to be missing."
)


# =============================================================================
# Tests: training partition of a single series
# =============================================================================
@pytest.mark.parametrize(
    "positions, date",
    [([4], "2023-02-26"), ([8], "2023-02-22")],
    ids=["last_training_date", "read_by_lag_5"],
)
def test_validate_evaluation_partition_InvalidInputError_when_ridge_reads_missing(
    positions, date
):
    """
    Test that a missing value of the training partition that a lag reads
    raises with an estimator that does not tolerate it (Ridge), and that the
    last training date is not a final row: the error is the one of the values
    read by the lags, not the one that asks to drop final rows.
    """
    err_msg = re.escape(
        f"The forecaster reads missing values of the target to predict ('y': 1 "
        f"value(s), such as '{date}'). {_READS_RIDGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_evaluation_partition(
            data    = with_missing(data_single, positions),
            profile = profile_single,
            plan    = plan_single_ridge_eval,
        )

    assert exc_info.value.field == "data"
    assert exc_info.value.code == "invalid_argument"


def test_validate_evaluation_partition_UserWarning_when_lightgbm_reads_missing():
    """
    Test that the same missing value only warns with an estimator that
    tolerates missing values (LGBMRegressor).
    """
    warn_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('y': 1 "
        f"value(s), such as '2023-02-26'). {_READS_LGBM}"
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_evaluation_partition(
            data    = with_missing(data_single, [4]),
            profile = profile_single,
            plan    = plan_single_lgbm_eval,
        )


@pytest.mark.parametrize(
    "positions",
    [[], [2], [20]],
    ids=["clean", "test_split", "far_in_the_past"],
)
def test_validate_evaluation_partition_no_error_when_no_missing_value_is_read(
    positions
):
    """
    Test that nothing is raised or warned when the target is complete, when
    the missing value is in the test split (left for `_check_evaluated_target`)
    or when no lag reads it.
    """
    result = validate_evaluation_partition(
        data    = with_missing(data_single, positions),
        profile = profile_single,
        plan    = plan_single_ridge_eval,
    )

    assert result is None


def test_validate_evaluation_partition_no_check_when_plan_without_end_train():
    """
    Test that a plan in prediction mode (`end_train` is None) is not checked:
    the function returns before reading the data.
    """
    result = validate_evaluation_partition(
        data    = with_missing(data_single, [4]),
        profile = profile_single,
        plan    = plan_single_ridge,
    )

    assert result is None


def test_validate_evaluation_partition_no_error_when_end_train_has_other_time_zone():
    """
    Test that an `end_train` with a time zone on dates without one is not
    checked: the generated code fails on it with its own error.
    """
    plan = in_evaluation(plan_single_ridge, "2023-02-26 00:00:00+00:00")

    result = validate_evaluation_partition(
        data    = with_missing(data_single, [4]),
        profile = profile_single,
        plan    = plan,
    )

    assert result is None


def test_validate_evaluation_partition_InvalidInputError_when_dates_have_time_zone():
    """
    Test that `end_train`, written without a time zone, is read in the time
    zone of the dates: the missing value of the last training date is found.
    """
    data = data_single.copy()
    data["date"] = data["date"].dt.tz_localize("Europe/Madrid")
    profile = ForecastingAssistant().profile(
        data, target="y", date_column="date"
    ).data_profile
    data = with_missing(data, [4])

    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('y': 1 "
        f"value(s), such as '2023-02-26'). {_READS_RIDGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = data,
            profile = profile,
            plan    = plan_single_ridge_eval,
        )


def test_validate_evaluation_partition_InvalidInputError_when_last_training_date_absent():
    """
    Test that a last training date missing from the data (a gap, not a NaN)
    is a missing value read by the lags: Ridge raises, and LGBMRegressor
    warns. A gap that no lag reads is accepted.
    """
    data = data_single[data_single["date"] != "2023-02-26"]

    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('y': 1 "
        f"value(s), such as '2023-02-26'). {_READS_RIDGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_evaluation_partition(
            data    = data,
            profile = profile_single,
            plan    = plan_single_ridge_eval,
        )
    assert exc_info.value.field == "data"

    warn_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('y': 1 "
        f"value(s), such as '2023-02-26'). {_READS_LGBM}"
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_evaluation_partition(
            data    = data,
            profile = profile_single,
            plan    = plan_single_lgbm_eval,
        )

    far = data_single[data_single["date"] != "2023-02-10"]
    result = validate_evaluation_partition(
        data    = far,
        profile = profile_single,
        plan    = plan_single_ridge_eval,
    )
    assert result is None


# =============================================================================
# Tests: ForecasterRecursiveMultiSeries
# =============================================================================
@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (data_wide, profile_wide, plan_wide_multiseries_eval),
        (data_long, profile_long, plan_long_multiseries_eval),
    ],
    ids=["wide", "long"],
)
def test_validate_evaluation_partition_no_error_when_all_series_have_values(
    data, profile, plan
):
    """
    Test that complete series, with a value on the last training date and on
    the 7 test dates, are accepted.
    """
    result = validate_evaluation_partition(data=data, profile=profile, plan=plan)

    assert result is None


def test_validate_evaluation_partition_InvalidInputError_when_series_ends_early_wide():
    """
    Test that a series without a value on the last training date is named,
    with the field `test_size`, in wide format.
    """
    err_msg = re.escape(
        "Some series have no value on the last training date (2012-04-22): "
        f"'item_1'. {_END_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_evaluation_partition(
            data    = with_missing(data_wide, [8], "item_1"),
            profile = profile_wide,
            plan    = plan_wide_multiseries_eval,
        )

    assert exc_info.value.field == "test_size"
    assert exc_info.value.code == "invalid_argument"


def test_validate_evaluation_partition_InvalidInputError_when_series_ends_early_long():
    """
    Test that a series without a value on the last training date is named in
    long format, whether its target is missing or its row is absent.
    """
    err_msg = re.escape(
        "Some series have no value on the last training date (2012-04-22): "
        f"'item_1'. {_END_MESSAGE}"
    )
    absent = data_long.drop(
        index=data_long.index[
            (data_long["series"] == "item_1") & (data_long["date"] == "2012-04-22")
        ]
    )
    for data in (with_missing_long(data_long, "item_1", [8]), absent):
        with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
            validate_evaluation_partition(
                data    = data,
                profile = profile_long,
                plan    = plan_long_multiseries_eval,
            )

        assert exc_info.value.field == "test_size"


def test_validate_evaluation_partition_InvalidInputError_names_all_series_when_none_ends():
    """
    Test that every series is named when none has a value on the last training
    date, and that five are listed at most.
    """
    data = data_wide.copy()
    data.loc["2012-04-22"] = np.nan
    err_msg = re.escape(
        "Some series have no value on the last training date (2012-04-22): "
        f"'item_1', 'item_2', 'item_3'. {_END_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = data,
            profile = profile_wide,
            plan    = plan_wide_multiseries_eval,
        )

    data = data_wide_seven.copy()
    data.loc["2023-02-22"] = np.nan
    err_msg = re.escape(
        "Some series have no value on the last training date (2023-02-22): "
        f"'s1', 's2', 's3', 's4', 's5' and 2 more. {_END_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = data,
            profile = profile_wide_seven,
            plan    = plan_wide_seven_eval,
        )


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_missing(data_wide, [3], "item_2"), profile_wide,
         plan_wide_multiseries_eval),
        (with_missing_long(data_long, "item_2", [3]), profile_long,
         plan_long_multiseries_eval),
    ],
    ids=["wide", "long"],
)
def test_validate_evaluation_partition_InvalidInputError_when_test_split_missing(
    data, profile, plan
):
    """
    Test that a missing value of one series in the test split raises with the
    field `data`, in wide and long format.
    """
    err_msg = re.escape(
        "The target has missing values in the test split ('item_2': 1 value(s), "
        f"such as '2012-04-27'). {_TEST_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_evaluation_partition(data=data, profile=profile, plan=plan)

    assert exc_info.value.field == "data"
    assert exc_info.value.code == "invalid_argument"


def test_validate_evaluation_partition_InvalidInputError_lists_dates_of_test_split():
    """
    Test that a long series without rows on several test dates reports all of
    them.
    """
    err_msg = re.escape(
        "The target has missing values in the test split ('item_2': 2 value(s), "
        f"such as '2012-04-25', '2012-04-27'). {_TEST_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = with_missing_long(data_long, "item_2", [3, 5]),
            profile = profile_long,
            plan    = plan_long_multiseries_eval,
        )


def test_validate_evaluation_partition_InvalidInputError_lists_five_series_at_most():
    """
    Test that the message about the test split lists five series at most.
    """
    data = data_wide_seven.copy()
    data.iloc[-3] = np.nan
    err_msg = re.escape(
        "The target has missing values in the test split ("
        + "; ".join(
            f"'s{number}': 1 value(s), such as '2023-02-27'"
            for number in range(1, 6)
        )
        + f"; and 2 more series). {_TEST_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = data,
            profile = profile_wide_seven,
            plan    = plan_wide_seven_eval,
        )


def test_validate_evaluation_partition_InvalidInputError_series_end_before_test_split():
    """
    Test that the series that end early are reported before the missing values
    of the test split.
    """
    data = with_missing(with_missing(data_wide, [3], "item_2"), [8], "item_1")
    err_msg = re.escape(
        "Some series have no value on the last training date (2012-04-22): "
        f"'item_1'. {_END_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = data,
            profile = profile_wide,
            plan    = plan_wide_multiseries_eval,
        )


def test_validate_evaluation_partition_no_error_when_series_without_values_up_to_end():
    """
    Test that a series without any value up to the end of training is left to
    `validate_series_lengths`, which names it with its own message.
    """
    data = data_wide.copy()
    data["item_3"] = data["item_3"].where(data.index > "2012-04-22")

    result = validate_evaluation_partition(
        data    = data,
        profile = profile_wide,
        plan    = plan_wide_multiseries_eval,
    )

    assert result is None


def test_validate_evaluation_partition_InvalidInputError_when_multiseries_reads_missing():
    """
    Test that the missing values that the lags of a multiseries forecaster
    read in the training partition raise as in prediction mode.
    """
    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict "
        "('item_1': 1 value(s), such as '2012-04-21'). "
        "ForecasterRecursiveMultiSeries with Ridge cannot use them, so its "
        "predictions would be missing: fill them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = with_missing(data_wide, [9], "item_1"),
            profile = profile_wide,
            plan    = plan_wide_multiseries_eval,
        )


def test_validate_evaluation_partition_InvalidInputError_when_dates_have_time_zone_multiseries():
    """
    Test that the checks of a multiseries forecaster read `end_train` in the
    time zone of a tz-aware index.
    """
    data = data_wide.copy()
    data.index = data.index.tz_localize("Europe/Madrid")
    profile = ForecastingAssistant().profile(
        data, target=list(data.columns)
    ).data_profile
    data = with_missing(data, [8], "item_1")

    err_msg = re.escape(
        "Some series have no value on the last training date (2012-04-22): "
        f"'item_1'. {_END_MESSAGE}"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_evaluation_partition(
            data    = data,
            profile = profile,
            plan    = plan_wide_multiseries_eval,
        )
