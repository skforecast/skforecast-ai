# Unit test generate_warnings

from skforecast_ai.profiling.data_profile import generate_warnings


def test_generate_warnings_output_when_missing_rate_is_high():
    """
    Test that a missing value rate above 20% across target and exogenous
    columns produces the imputation warning with the rate.
    """
    warnings = generate_warnings(
        n_observations = 100,
        frequency      = "D",
        missing_target = {"y": 30},
        missing_exog   = {"x": 20},
        index_type     = "datetime",
    )

    assert warnings == [
        "High missing value rate (25.0%). Consider imputation before forecasting."
    ]


def test_generate_warnings_output_when_missing_rate_is_low():
    """
    Test that a missing value rate at or below 20% produces no warning.
    """
    warnings = generate_warnings(
        n_observations = 100,
        frequency      = "D",
        missing_target = {"y": 5},
        missing_exog   = {},
        index_type     = "datetime",
    )

    assert warnings == []
