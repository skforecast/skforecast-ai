# Unit test missing_rate_warning

from skforecast_ai.profiling.data_profile import missing_rate_warning


def test_missing_rate_warning_output_when_rate_is_high():
    """
    Test that a missing value rate above 20% across the target and the
    exogenous columns with missing values returns the imputation warning
    with the rate.
    """
    warning = missing_rate_warning(
        n_observations = 100,
        missing_target = {"y": 30},
        missing_exog   = {"x": 20},
    )

    assert warning == (
        "High missing value rate (25.0%). Consider imputation before forecasting."
    )


def test_missing_rate_warning_output_when_rate_is_low():
    """
    Test that a missing value rate below 20% returns None.
    """
    warning = missing_rate_warning(
        n_observations = 100,
        missing_target = {"y": 5},
        missing_exog   = {},
    )

    assert warning is None


def test_missing_rate_warning_output_when_rate_is_exactly_20_percent():
    """
    Test that a missing value rate of exactly 20% returns None: the warning
    needs a rate above it.
    """
    warning = missing_rate_warning(
        n_observations = 100,
        missing_target = {"y": 20},
        missing_exog   = {},
    )

    assert warning is None


def test_missing_rate_warning_output_when_nothing_is_missing():
    """
    Test that no missing values (empty mappings) returns None.
    """
    warning = missing_rate_warning(
        n_observations = 100,
        missing_target = {},
        missing_exog   = {},
    )

    assert warning is None


def test_missing_rate_warning_output_when_only_exog_is_missing():
    """
    Test that the rate counts only the columns that have missing values: one
    exogenous column with 50 of 100 values missing gives 50.0%.
    """
    warning = missing_rate_warning(
        n_observations = 100,
        missing_target = {},
        missing_exog   = {"x": 50},
    )

    assert warning == (
        "High missing value rate (50.0%). Consider imputation before forecasting."
    )
