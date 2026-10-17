# Unit test infer_frequency

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import infer_frequency
from skforecast_ai.recommendation.autoregressive import estimate_seasonality

# A year of days from a Monday, the fixed holidays of a Spanish calendar in
# it, and the days of a shop closed on Sundays.
_YEAR = pd.date_range("2023-01-02", periods=364, freq="D")
_HOLIDAYS = pd.DatetimeIndex(
    [
        "2023-01-06", "2023-04-07", "2023-05-01", "2023-08-15", "2023-10-12",
        "2023-11-01", "2023-12-06", "2023-12-08", "2023-12-25",
    ]
)
_NO_SUNDAYS = _YEAR[_YEAR.dayofweek != 6]
_BUSINESS_YEAR = pd.bdate_range("2023-01-02", periods=260)
# The daily file of the MCP audit (b_07): 40 of 150 days missing at random.
_DAYS_150 = pd.date_range("2020-01-01", periods=150, freq="D")
_RANDOM_GAPS = _DAYS_150[
    np.sort(np.random.default_rng(3).choice(150, size=110, replace=False))
]
# Hours of a month: from 8:00 to 23:00, and office hours (9:00 to 17:00 on
# business days).
_HOURS = pd.date_range("2023-01-02", periods=720, freq="h")
_OPEN_FROM_EIGHT = _HOURS[_HOURS.hour >= 8]
_OFFICE_HOURS = _HOURS[
    (_HOURS.dayofweek < 5) & (_HOURS.hour >= 9) & (_HOURS.hour <= 17)
]
_MONTHS = pd.date_range("2015-01-01", periods=60, freq="MS")
# Every other day, with three days in a row every ten days: 60 % of the
# daily grid, but most dates two days apart.
_EVERY_OTHER_DAY = _YEAR[np.isin(np.arange(364) % 10, [0, 1, 2, 4, 6, 8])]


@pytest.mark.parametrize(
    "freq, expected",
    [
        ("h", "h"),
        ("D", "D"),
        ("B", "B"),
        ("W", "W-SUN"),
        ("MS", "MS"),
        ("ME", "ME"),
        ("QS", "QS-OCT"),
    ],
    ids=lambda x: f"{x}",
)
def test_infer_frequency_output_when_regular_series(freq, expected):
    """
    Test infer_frequency returns the correct frequency string for a
    regularly-spaced DatetimeIndex.
    """
    index = pd.date_range("2023-01-01", periods=100, freq=freq)
    result = infer_frequency(index)
    assert result == expected


def test_infer_frequency_output_when_irregular_series():
    """
    Test infer_frequency returns None when the DatetimeIndex has irregular
    spacing.
    """
    index = pd.DatetimeIndex(["2023-01-01", "2023-01-03", "2023-01-08", "2023-01-20"])
    result = infer_frequency(index)
    assert result is None


@pytest.mark.parametrize(
    "freq, drop, expected",
    [
        ("h", [5, 6, 30], "h"),
        ("D", [50, 51, 80], "D"),
        ("B", [10, 40], "B"),
        ("W", [10, 11], "W-SUN"),
        ("MS", [20, 45], "MS"),
        ("15min", [3, 70, 71, 72], "15min"),
    ],
    ids=lambda x: f"{x}",
)
def test_infer_frequency_output_when_regular_series_with_gaps(freq, drop, expected):
    """
    Test infer_frequency infers the frequency of a regular DatetimeIndex
    with missing timestamps, which `pd.infer_freq` alone cannot, without
    confusing business days with calendar days.
    """
    index = pd.date_range("2023-01-02", periods=100, freq=freq)
    index = index.delete(drop)
    result = infer_frequency(index)
    assert result == expected


@pytest.mark.parametrize(
    "index, expected",
    [
        (_BUSINESS_YEAR.difference(_HOLIDAYS), "B"),
        (_OPEN_FROM_EIGHT, "h"),
        (_MONTHS[_MONTHS.month != 8], "MS"),
    ],
    ids=["business days without holidays", "hourly closed at night", "no august"],
)
def test_infer_frequency_output_when_gap_free_stretches_give_frequency(
    index, expected
):
    """
    Test infer_frequency infers, as before, the frequency of regular gaps
    that leave stretches of ten timestamps without one: business days
    without the fixed holidays are 'B', hours from 8:00 to 23:00 'h', and
    months without August 'MS'.
    """
    result = infer_frequency(index)
    assert result == expected


@pytest.mark.parametrize(
    "index, expected",
    [
        (_NO_SUNDAYS, "D"),
        (_NO_SUNDAYS.difference(_HOLIDAYS), "D"),
        (_YEAR[_YEAR.dayofweek != 2], "D"),
        (_RANDOM_GAPS, "D"),
        (
            _YEAR[np.sort(np.random.default_rng(0).choice(364, 200, replace=False))],
            "D",
        ),
        (_YEAR[_YEAR.dayofweek < 4], "B"),
        (
            _BUSINESS_YEAR[
                np.sort(np.random.default_rng(0).choice(260, 143, replace=False))
            ],
            "B",
        ),
        (_MONTHS[:18].delete([4, 9, 14]), "MS"),
    ],
    ids=[
        "closed on sundays", "closed on sundays and fixed holidays",
        "closed on wednesdays", "27 % of days missing at random",
        "45 % of days missing at random", "monday to thursday",
        "45 % of business days missing at random", "months with gaps",
    ],
)
def test_infer_frequency_output_when_gaps_leave_no_gap_free_stretch(
    index, expected
):
    """
    Test infer_frequency infers the frequency of an index whose gaps, regular
    or frequent, leave no ten timestamps in a row, when every timestamp lies
    on its grid and at least half of it is observed: a shop closed on
    Sundays (and on fixed holidays) or on Wednesdays, and days missing at
    random (the file of the MCP audit, 27 %, and 45 %) are daily with gaps.
    Business days stay 'B', the coarsest frequency that fits, also from
    Monday to Thursday, where no three dates in a row give 'B' to pandas;
    months with gaps stay 'MS'.
    """
    result = infer_frequency(index)
    assert result == expected


@pytest.mark.parametrize(
    "index",
    [
        _YEAR[np.sort(np.random.default_rng(0).choice(364, 145, replace=False))],
        _OFFICE_HOURS,
        _BUSINESS_YEAR.insert(112, pd.Timestamp("2023-06-10")),
        _NO_SUNDAYS.insert(40, pd.Timestamp("2023-02-14 12:00")),
        _YEAR[_YEAR.dayofweek.isin([0, 2, 4, 5])],
        _EVERY_OTHER_DAY,
        _NO_SUNDAYS.append(
            pd.DatetimeIndex(["2023-06-01 00:00:01", "2023-06-01 00:00:02"])
        ).sort_values(),
    ],
    ids=[
        "60 % of days missing at random", "office hours",
        "saturday among business days", "noon among days without sundays",
        "most steps of two days", "every other day and three in a row",
        "two timestamps a second apart",
    ],
)
def test_infer_frequency_output_when_gaps_are_not_a_frequency_with_gaps(index):
    """
    Test infer_frequency returns None for regular or frequent gaps that are
    not a frequency with missing timestamps: days missing at random over 60 %
    of the year and office hours (9:00 to 17:00 on business days) fill less
    than half of their grid; a Saturday among business days is a timestamp
    off the grid of 'B', which the stretches of ten give, not daily data
    with gaps; a timestamp at noon among days without Sundays is off the
    daily grid, and not '12h' with gaps; a shop open on Monday, Wednesday,
    Friday and Saturday, and dates every other day with three in a row
    every ten days (60 % of the daily grid), have most of their days two
    apart, not one period of the daily grid. Two timestamps a second after
    midnight among days without Sundays are not '1s' with gaps either.
    """
    result = infer_frequency(index)
    assert result is None


@pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"], ids=lambda unit: unit)
def test_infer_frequency_output_when_gaps_leave_no_gap_free_stretch_in_any_unit(
    unit,
):
    """
    Test infer_frequency infers the frequency of regular gaps that leave no
    ten timestamps in a row whatever the unit of the index (pandas 3 parses
    text dates to microseconds, Parquet files hold seconds): days without
    Sundays are 'D', also time zone aware, and days from Monday to Thursday
    'B'.
    """
    no_sundays = _NO_SUNDAYS.as_unit(unit)
    monday_to_thursday = _YEAR[_YEAR.dayofweek < 4].as_unit(unit)

    assert infer_frequency(no_sundays) == "D"
    assert infer_frequency(no_sundays.tz_localize("Europe/Madrid")) == "D"
    assert infer_frequency(monday_to_thursday) == "B"


def test_infer_frequency_output_when_regular_gaps_is_false():
    """
    Test infer_frequency with `regular_gaps=False` infers a frequency only on
    gap-free stretches, as before this argument: days without Sundays have
    none, and business days without the fixed holidays are still 'B'.
    """
    assert infer_frequency(_NO_SUNDAYS, regular_gaps=False) is None
    assert infer_frequency(
        _BUSINESS_YEAR.difference(_HOLIDAYS), regular_gaps=False
    ) == "B"


def test_infer_frequency_output_when_most_of_the_grid_is_missing():
    """
    Test infer_frequency returns None when the regular stretches suggest a
    frequency but less than half of its grid is observed: the spacing is
    irregular rather than regular with gaps.
    """
    index = pd.date_range("2023-01-01", periods=10, freq="D").append(
        pd.date_range("2023-03-01", periods=10, freq="D")
    )
    result = infer_frequency(index)
    assert result is None


def test_infer_frequency_output_when_too_few_observations():
    """
    Test infer_frequency returns None when the index has fewer than 3
    observations.
    """
    index = pd.date_range("2023-01-01", periods=2, freq="D")
    result = infer_frequency(index)
    assert result is None


@pytest.mark.parametrize(
    "freq, expected_seasonalities",
    [
        # --- Base aliases (pandas 2.x lowercase) ---
        ("s",   [3_600, 86_400]),
        ("min", [60, 1_440]),
        ("h",   [24, 168]),
        ("D",   [7, 365]),
        # --- Legacy uppercase aliases ---
        ("T",   [60, 1_440]),
        ("H",   [24, 168]),
        # --- Business day (non-fixed, heuristic table) ---
        ("B",   [5, 252]),
        # --- Weekly (non-fixed, heuristic table) ---
        ("W",     [52]),
        ("W-SUN", [52]),
        # --- Monthly / quarterly / yearly (variable-length) ---
        ("MS",     [12]),
        ("ME",     [12]),
        ("QS",     [4]),
        ("QE",     [4]),
        ("QS-OCT", [4]),
        ("QE-DEC", [4]),
        ("A-DEC",  [1]),
        ("YE-DEC", [1]),
        # --- Multiplied sub-daily (previously wrong or missing) ---
        ("15min", [4, 96]),    # 15-min: 4/hour, 96/day
        ("15T",   [4, 96]),    # same via legacy alias
        ("30min", [2, 48]),    # 30-min: 2/hour, 48/day
        ("30s",   [120, 2_880]),  # 30-sec: 120/hour, 2880/day
        ("2h",    [12, 84]),   # 2-hour: 12/day, 84/week
        ("2H",    [12, 84]),   # same via legacy alias
        ("6h",    [4, 28]),    # 6-hour: 4/day, 28/week
        # --- Multiplied variable offsets (multiplier divides the table) ---
        ("2W",  [26]),   # biweekly: 26/year
        ("2MS", [6]),    # bi-monthly: 6/year
        ("2ME", [6]),    # same via period-end alias
        ("2QS", [2]),    # semi-annual: 2/year
        # --- Edge cases ---
        (None,      []),
        ("UNKNOWN", []),
    ],
    ids=lambda x: f"{x}",
)
def test_estimate_seasonality_output(freq, expected_seasonalities):
    """
    Test estimate_seasonality returns correct seasonal periods for base
    aliases, anchored offsets, legacy uppercase aliases, multiplied
    variants, and an empty list for unknown or None inputs.
    """
    result = estimate_seasonality(freq)
    assert result == expected_seasonalities
