# Unit test count_test_observations

import pytest

from skforecast_ai.profiling.data_profile import count_test_observations


@pytest.mark.parametrize(
    "start_date, frequency, n_observations, end_train, expected",
    [
        ("2023-01-01", "D", 100, "2023-04-03", 7),
        ("2023-06-01 03:00:00", "h", 25, "2023-06-02 00:00:00", 3),
        ("2023-06-01 03:00:00+02:00", "h", 25, "2023-06-02 00:00:00", 3),
        ("2023-06-01 03:00:00+02:00", "h", 25, "2023-06-02", 3),
        ("2023-06-01 03:00:00+02:00", "h", 25, "2023-06-02 00:00:00+02:00", 3),
    ],
    ids=["daily", "hourly", "hourly_tz", "hourly_tz_date_only", "hourly_tz_aware_end"],
)
def test_count_test_observations_output(
    start_date, frequency, n_observations, end_train, expected
):
    """
    Test that the observations after `end_train` are counted, also on tz-aware
    dates with an `end_train` written without a time zone (it raised
    TypeError), read in the zone of the data.
    """
    result = count_test_observations(
        start_date, frequency, n_observations, end_train
    )

    assert result == expected


def test_count_test_observations_output_when_time_zone_of_the_profile():
    """
    Test that, with the time zone of the profile, the observations are
    counted on the local times of the data, as `resolve_end_train` places
    the boundary: 2023-03-26 has no 02:00 in Madrid.
    """
    with_zone = count_test_observations(
        "2023-03-26", "h", 6, "2023-03-26 03:00:00", time_zone="Europe/Madrid"
    )
    without_zone = count_test_observations("2023-03-26", "h", 6, "2023-03-26 03:00:00")

    assert with_zone == 3
    assert without_zone == 2


@pytest.mark.parametrize(
    "start_date, frequency",
    [(None, "D"), ("2023-01-01", None)],
    ids=["no_start_date", "no_frequency"],
)
def test_count_test_observations_output_None_when_grid_cannot_be_rebuilt(
    start_date, frequency
):
    """
    Test that None is returned without a start date or without a frequency.
    """
    assert count_test_observations(start_date, frequency, 100, "2023-03-26") is None
