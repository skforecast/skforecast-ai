# Unit test resolve_end_train

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling import resolve_end_train


# Reference daily index: 100 observations starting 2023-01-01
_N = 100
_START = "2023-01-01"
_FREQ = "D"
_INDEX = pd.date_range(_START, periods=_N, freq=_FREQ)


# =============================================================================
# Tests: valid resolutions
# =============================================================================
def test_resolve_end_train_output_when_int():
    """
    Test that an integer test_size marks the last N observations as test:
    end_train is the observation just before the final N.
    """
    end_train = resolve_end_train(
        start_date=_START, frequency=_FREQ, n_observations=_N, test_size=20
    )

    assert end_train == str(_INDEX[_N - 20 - 1].date())


def test_resolve_end_train_output_when_float():
    """
    Test that a float test_size marks the last fraction as test.
    """
    end_train = resolve_end_train(
        start_date=_START, frequency=_FREQ, n_observations=_N, test_size=0.2
    )

    assert end_train == str(_INDEX[_N - 20 - 1].date())


def test_resolve_end_train_output_when_date_string():
    """
    Test that a date-string test_size (the first test timestamp) resolves
    end_train to the last training timestamp strictly before it.
    """
    test_start = _INDEX[80]
    end_train = resolve_end_train(
        start_date=_START,
        frequency=_FREQ,
        n_observations=_N,
        test_size=str(test_start.date()),
    )

    assert end_train == str(_INDEX[79].date())


def test_resolve_end_train_output_when_timestamp():
    """
    Test that a pandas Timestamp test_size behaves like a date string.
    """
    test_start = _INDEX[80]
    end_train = resolve_end_train(
        start_date=_START,
        frequency=_FREQ,
        n_observations=_N,
        test_size=test_start,
    )

    assert end_train == str(_INDEX[79].date())


# =============================================================================
# Tests: invalid inputs
# =============================================================================
def test_resolve_end_train_ValueError_when_int_out_of_range():
    """
    Test that an integer test_size not strictly smaller than the number of
    observations raises ValueError.
    """
    with pytest.raises(ValueError, match="Integer .test_size."):
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size=1000
        )


def test_resolve_end_train_ValueError_when_float_out_of_range():
    """
    Test that a float test_size outside the open interval (0, 1) raises
    ValueError.
    """
    with pytest.raises(ValueError, match="Float .test_size."):
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size=1.5
        )


def test_resolve_end_train_ValueError_when_date_outside_range():
    """
    Test that a date-string test_size outside the data range raises
    ValueError.
    """
    with pytest.raises(ValueError, match="Timestamp .test_size."):
        resolve_end_train(
            start_date=_START,
            frequency=_FREQ,
            n_observations=_N,
            test_size="2050-01-01",
        )


def test_resolve_end_train_TypeError_when_bool():
    """
    Test that a bool test_size is rejected (bool is a subclass of int).
    """
    with pytest.raises(TypeError, match="test_size"):
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size=True
        )


def test_resolve_end_train_ValueError_when_no_frequency():
    """
    Test that resolution requires a datetime index with a known frequency.
    """
    with pytest.raises(ValueError, match="requires a datetime index"):
        resolve_end_train(
            start_date=_START, frequency=None, n_observations=_N, test_size=20
        )


def test_resolve_end_train_TypeError_when_unsupported_type():
    """
    Test that a `test_size` of an unsupported type (for example a list)
    raises TypeError naming the accepted types.
    """
    with pytest.raises(TypeError, match="must be an int, float, str or Timestamp, got list"):
        resolve_end_train(
            start_date="2023-01-01", frequency="D", n_observations=100, test_size=[10]
        )


def test_resolve_end_train_InvalidInputError_when_text_is_not_a_date():
    """
    Test that a text `test_size` that is not a date raises with the field
    'test_size' instead of the raw error of pandas.
    """
    err_msg = re.escape(
        "`test_size` is text that is not a date: 'abc'. Pass an integer, a "
        "fraction in (0, 1) or the first date of the test set, such as "
        "'2023-03-01'."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size="abc"
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "test_size"


def test_resolve_end_train_InvalidInputError_hint_when_no_frequency():
    """
    Test that the error of a missing datetime index with a known frequency
    carries the field 'test_size' and a hint.
    """
    err_msg = re.escape(
        "`test_size` requires a datetime index with a known frequency. Set the "
        "index frequency (e.g. `data.asfreq(...)`) before forecasting."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        resolve_end_train(
            start_date=_START, frequency=None, n_observations=_N, test_size=20
        )

    assert exc_info.value.field == "test_size"
    assert exc_info.value.hint == (
        "Give the data a datetime index with a regular frequency, or a date "
        "column whose dates follow one."
    )


# =============================================================================
# Tests: sub-daily data and time zones
# =============================================================================
@pytest.mark.parametrize(
    "start, test_size, expected",
    [
        ("2023-06-01 03:00:00", 3, "2023-06-02 00:00:00"),
        ("2023-06-01 03:00:00+02:00", 3, "2023-06-02 00:00:00+02:00"),
        ("2023-06-01 03:00:00", "2023-06-02 00:00:00", "2023-06-01 23:00:00"),
        (
            "2023-06-01 03:00:00+02:00",
            "2023-06-02 00:00:00",
            "2023-06-01 23:00:00+02:00",
        ),
        (
            "2023-06-01 03:00:00+02:00",
            pd.Timestamp("2023-06-02 00:00:00"),
            "2023-06-01 23:00:00+02:00",
        ),
    ],
    ids=["naive", "tz", "naive_text", "tz_text_without_zone", "tz_timestamp"],
)
def test_resolve_end_train_output_when_hourly_data(start, test_size, expected):
    """
    Test that on hourly data `end_train` keeps the time also at midnight (a
    date only made the script train on the whole day), with the time zone of
    tz-aware dates, and that a `test_size` written without a time zone is read
    in the zone of the data (it raised TypeError).
    """
    end_train = resolve_end_train(
        start_date=start, frequency="h", n_observations=25, test_size=test_size
    )

    assert end_train == expected


def test_resolve_end_train_output_when_daily_and_monthly_data_keep_the_date_only():
    """
    Test that daily and monthly data, all at midnight, still give a date-only
    `end_train`.
    """
    daily = resolve_end_train(
        start_date="2023-01-01", frequency="D", n_observations=100, test_size=7
    )
    monthly = resolve_end_train(
        start_date="1991-07-01", frequency="MS", n_observations=204, test_size=12
    )

    assert daily == "2023-04-03"
    assert monthly == "2007-06-01"


@pytest.mark.parametrize(
    "test_size",
    [
        "2024-04-09T00:00:00Z",
        "2024-04-09T00:00:00+00:00",
        "2024-04-09T02:00:00+02:00",
        "2024-04-09",
        pd.Timestamp("2024-04-09", tz="UTC"),
    ],
    ids=["Z", "+00:00", "+02:00", "without_zone", "tz_timestamp"],
)
def test_resolve_end_train_output_when_time_zone_of_the_profile(test_size):
    """
    Test that, with the time zone of the profile (its `start_date` has
    none), a date with a time zone is placed on the dates in their zone and
    one without is read as a local time of the data, as `create_cv` places
    an `initial_train_size` (G04: a date with a time zone raised TypeError).
    `end_train` is a local time, without the zone.
    """
    end_train = resolve_end_train(
        start_date     = "2024-03-20",
        frequency      = "h",
        n_observations = 24 * 30,
        test_size      = test_size,
        time_zone      = "UTC",
    )

    assert end_train == "2024-04-08 23:00:00"


def test_resolve_end_train_output_when_time_zone_with_daylight_saving_change():
    """
    Test that, in a zone with a daylight saving change, the position of a
    date is the one it has in the data: the local times skip 02:00 on
    2023-03-26 in Madrid, so a test set of the last 2 hours (05:00 and
    06:00) ends training at 04:00 (the regular grid without the zone gave
    03:00, an hour early).
    """
    by_size = resolve_end_train(
        start_date     = "2023-03-26",
        frequency      = "h",
        n_observations = 6,
        test_size      = 2,
        time_zone      = "Europe/Madrid",
    )
    by_date = resolve_end_train(
        start_date     = "2023-03-26",
        frequency      = "h",
        n_observations = 6,
        test_size      = "2023-03-26 05:00:00",
        time_zone      = "Europe/Madrid",
    )

    assert by_size == "2023-03-26 04:00:00"
    assert by_date == "2023-03-26 04:00:00"


@pytest.mark.parametrize(
    "time_zone, reason",
    [
        (None, "the dates of the data have none"),
        (
            "Not/AZone",
            "the dates of the data cannot be rebuilt in their time zone "
            "(Not/AZone)",
        ),
    ],
    ids=["no_zone", "unusable_zone"],
)
def test_resolve_end_train_InvalidInputError_when_date_with_time_zone_and_data_without(
    time_zone, reason
):
    """
    Test that a date with a time zone on dates without one is
    `InvalidInputError` on `test_size` saying to drop the zone, instead of
    a TypeError from comparing them (G04).
    """
    err_msg = re.escape(
        f"`test_size` ('2024-04-09T00:00:00Z') has a time zone, and {reason}. "
        f"Pass the first date of the test set without the time zone, such as "
        f"'2024-04-09'."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        resolve_end_train(
            start_date     = "2024-03-20",
            frequency      = "h",
            n_observations = 24 * 30,
            test_size      = "2024-04-09T00:00:00Z",
            time_zone      = time_zone,
        )

    assert exc_info.value.field == "test_size"
