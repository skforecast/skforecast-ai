# Unit test generate_warnings

import pytest

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


def test_generate_warnings_output_when_timestamps_are_missing():
    """
    Test that missing timestamps produce a warning with their count and
    frequency, saying that `asfreq()` turns them into missing values.
    """
    warnings = generate_warnings(
        n_observations       = 100,
        frequency            = "D",
        missing_target       = {},
        missing_exog         = {},
        index_type           = "datetime",
        n_missing_timestamps = 3,
    )

    assert warnings == [
        "Missing timestamps: 3 timestamps of frequency 'D' are missing from "
        "the date range. asfreq() inserts them as rows with missing values."
    ]


def test_generate_warnings_output_when_timestamps_are_duplicated():
    """
    Test that timestamps repeated in identical rows produce a warning with
    their count, saying that the generated code keeps the first row.
    """
    warnings = generate_warnings(
        n_observations         = 100,
        frequency              = "D",
        missing_target         = {},
        missing_exog           = {},
        index_type             = "datetime",
        n_duplicate_timestamps = 5,
    )

    assert warnings == [
        "Duplicate timestamps: identical rows repeat 5 timestamps. The "
        "generated code keeps the first row of each."
    ]


def test_generate_warnings_output_when_frequency_cannot_be_inferred():
    """
    Test that a datetime index whose frequency cannot be inferred produces
    the irregular spacing warning.
    """
    warnings = generate_warnings(
        n_observations = 100,
        frequency      = None,
        missing_target = {},
        missing_exog   = {},
        index_type     = "datetime",
    )

    assert warnings == [
        "Could not infer frequency from the datetime index: the spacing is "
        "irregular, or there are too few timestamps."
    ]


@pytest.mark.parametrize(
    "long_format, expected",
    [
        (
            False,
            "Rows not in date order: they were sorted by date before "
            "profiling, as the generated code sorts them.",
        ),
        (
            True,
            "Rows not in date order within each series: they were sorted by "
            "date before profiling, as the generated code sorts them.",
        ),
    ],
    ids=["single", "long"],
)
def test_generate_warnings_output_when_rows_were_sorted(long_format, expected):
    """
    Test that rows sorted before profiling produce a note, worded per series
    for long format.
    """
    warnings = generate_warnings(
        n_observations = 100,
        frequency      = "D",
        missing_target = {},
        missing_exog   = {},
        index_type     = "datetime",
        rows_sorted    = True,
        long_format    = long_format,
    )

    assert warnings == [expected]
