# Unit test plan_data_warnings

import numpy as np
import pandas as pd

from skforecast_ai.profiling import create_data_profile
from skforecast_ai.profiling.data_profile import plan_data_warnings
from skforecast_ai.schemas import DataProfile

_RATE_35 = "High missing value rate (35.0%). Consider imputation before forecasting."
_RATE_40 = "High missing value rate (40.0%). Consider imputation before forecasting."
_EXOG_MISSING = (
    "Missing values in exogenous columns: 'x': 30. An estimator that does not "
    "accept missing values fails when it reads them."
)
_EXOG_TEXT = "Numbers written as text in exogenous column 'x': all of them."
_OTHER = "Missing timestamps: 3 timestamps are missing."

_index = pd.date_range("2023-01-01", periods=100, freq="D")
_target_40_missing = np.arange(100, dtype=float)
_target_40_missing[:40] = np.nan
_target_10_missing = np.arange(100, dtype=float)
_target_10_missing[:10] = np.nan
_exog_30_missing = np.arange(100, dtype=float)
_exog_30_missing[50:80] = np.nan

# Single series: 40 target and 30 exog values missing (35.0% together, 40.0% in
# the target alone); 10 target and 30 exog missing (20.0% together); no target
# value missing and 30 exog missing (30.0% in the exog alone).
profile_single_target_40 = create_data_profile(
    data   = pd.DataFrame(
        {"y": _target_40_missing, "x": _exog_30_missing}, index=_index
    ),
    target = "y",
)
profile_single_target_10 = create_data_profile(
    data   = pd.DataFrame(
        {"y": _target_10_missing, "x": _exog_30_missing}, index=_index
    ),
    target = "y",
)
profile_single_only_exog = create_data_profile(
    data   = pd.DataFrame(
        {"y": np.arange(100, dtype=float), "x": _exog_30_missing}, index=_index
    ),
    target = "y",
)
profile_single_no_exog = create_data_profile(
    data   = pd.DataFrame({"y": _target_40_missing}, index=_index),
    target = "y",
)


def _profile(data_format, series_lengths, span_index_length, missing_target):
    """
    Profile of long or wide data with one exogenous column with 30 values
    missing and the warnings the profile would hold.
    """
    return DataProfile(
        data_format       = data_format,
        n_series          = len(series_lengths),
        series_lengths    = series_lengths,
        span_index_length = span_index_length,
        target            = "value" if data_format == "long" else list(series_lengths),
        index_type        = "datetime",
        frequency         = "D",
        missing_target    = missing_target,
        exog_columns      = ["x"],
        missing_exog      = {"x": 30},
        warnings          = [
            "High missing value rate (placeholder). Consider imputation.",
            _EXOG_MISSING,
            _EXOG_TEXT,
            _OTHER,
        ],
    )


# Long: the shortest series has 50 observations, so 30 target values missing
# in it are 60.0% (the rate counts the shortest series).
profile_long = _profile("long", {"a": 100, "b": 50}, 100, {"b": 30})
# Wide: 100 dates in the span, 30 target values missing in "a" are 30.0%.
profile_wide = _profile("wide", {"a": 80, "b": 80}, 100, {"a": 30})
# Wide with the target at the limit: 20 of 100 dates is 20.0%, not above it.
profile_wide_at_limit = _profile("wide", {"a": 80, "b": 80}, 100, {"a": 20})


def test_plan_data_warnings_output_when_use_exog_is_true():
    """
    Test that the warnings of the profile are returned unchanged when the
    plan uses the exogenous variables.
    """
    result = plan_data_warnings(profile_single_target_40, True)

    assert result == [_RATE_35, _EXOG_MISSING]
    assert result == profile_single_target_40.warnings


def test_plan_data_warnings_output_when_use_exog_is_true_returns_a_copy():
    """
    Test that the list returned is not the list of the profile.
    """
    result = plan_data_warnings(profile_single_target_40, True)
    result.append("another")

    assert profile_single_target_40.warnings == [_RATE_35, _EXOG_MISSING]


def test_plan_data_warnings_output_when_there_are_no_exog_columns():
    """
    Test that the warnings are returned unchanged when the data has no
    exogenous columns, whatever `use_exog`.
    """
    assert profile_single_no_exog.warnings == [
        "High missing value rate (40.0%). Consider imputation before forecasting."
    ]
    assert plan_data_warnings(profile_single_no_exog, False) == [_RATE_40]


def test_plan_data_warnings_output_when_single_series_target_rate_is_high():
    """
    Test that, without exogenous variables, the missing values of the
    exogenous column are left out and the rate is recomputed on the target
    alone: 40 of 100 values (40.0%), not the 35.0% of target and exog.
    """
    result = plan_data_warnings(profile_single_target_40, False)

    assert result == [_RATE_40]


def test_plan_data_warnings_output_when_target_rate_is_low():
    """
    Test that the rate warning is dropped when the target alone is at or
    below 20% (10 of 100 values), leaving no warning once the missing
    values of the exogenous column are left out too.
    """
    assert profile_single_target_10.warnings == [_EXOG_MISSING]
    assert plan_data_warnings(profile_single_target_10, False) == []


def test_plan_data_warnings_output_when_only_exog_has_missing_values():
    """
    Test that a rate warning caused by the exogenous column alone (30 of 100
    values) is dropped, together with the missing values of that column.
    """
    assert profile_single_only_exog.warnings == [
        "High missing value rate (30.0%). Consider imputation before forecasting.",
        _EXOG_MISSING,
    ]
    assert plan_data_warnings(profile_single_only_exog, False) == []


def test_plan_data_warnings_output_when_numbers_written_as_text():
    """
    Test that the warning about numbers written as text in an exogenous
    column is left out without exogenous variables, and the warnings that
    do not concern the exogenous columns are kept in their order.
    """
    result = plan_data_warnings(profile_long, False)

    assert _EXOG_TEXT not in result
    assert _EXOG_MISSING not in result
    assert result[-1] == _OTHER


def test_plan_data_warnings_output_when_long_format_counts_shortest_series():
    """
    Test that, for long data, the rate is counted on the observations of the
    shortest series: 30 of 50 values (60.0%).
    """
    result = plan_data_warnings(profile_long, False)

    assert result == [
        "High missing value rate (60.0%). Consider imputation before forecasting.",
        _OTHER,
    ]


def test_plan_data_warnings_output_when_wide_format_counts_span_index_length():
    """
    Test that, for wide data, the rate is counted on the dates of the span
    (`span_index_length`, 100), not on the length of the series (80): 30 of
    100 values (30.0%).
    """
    result = plan_data_warnings(profile_wide, False)

    assert result == [
        "High missing value rate (30.0%). Consider imputation before forecasting.",
        _OTHER,
    ]


def test_plan_data_warnings_output_when_wide_rate_is_at_the_limit():
    """
    Test that, for wide data, a target rate of exactly 20% drops the rate
    warning.
    """
    assert plan_data_warnings(profile_wide_at_limit, False) == [_OTHER]
