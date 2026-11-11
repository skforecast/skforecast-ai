# Unit test create_data_profile

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import IgnoredArgumentWarning

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling import create_data_profile
from skforecast_ai.profiling.csv_dialect import cp1252_note
from skforecast_ai.profiling.data_profile import DAYFIRST_FRAME_HINT, DAYFIRST_HINT
from skforecast_ai.schemas import DataProfile, SeriesLengthInfo

from ..fixtures_assistant import (
    df_multi_long_integer_ids,
    df_multi_long_numeric_ids,
    df_no_sundays_long,
)
from ..fixtures_csv_dialect import write_cp1252
from ..fixtures_datasets import df_h2o, df_items_sales_long, df_items_sales_wide
from .fixtures_profiling import (
    df_dates_compact,
    df_dates_day_first,
    df_dates_iso,
    df_dates_month_first,
    df_dates_monthly_ambiguous,
    df_dates_monthly_us,
    df_dates_three_ambiguous,
    df_dirty_exog,
    df_german_from_15th,
    df_german_from_1st,
    df_german_monthly,
    df_long_duplicate_values_series_b,
    df_long_identical_duplicates_series_b,
    df_multi_long,
    df_multiindex_identical_duplicates_series_b,
    df_range_index,
    df_short,
    df_single_daily,
    df_single_duplicate_values,
    df_single_hourly_exog,
    df_single_identical_duplicates,
    df_wide_duplicate_values,
    df_wide_identical_duplicates,
    df_with_missing,
    write_german_excel,
)


def test_create_data_profile_output_when_single_series_daily():
    """
    Test create_data_profile returns correct profile for a single daily
    series with DatetimeIndex.
    """
    profile = create_data_profile(data=df_single_daily, target="y")

    assert isinstance(profile, DataProfile)
    assert profile.series_lengths["y"].length == 365
    assert profile.n_series == 1
    assert profile.index_type == "datetime"
    assert profile.frequency == "D"
    assert profile.target == "y"
    assert profile.date_column is None
    assert profile.series_id_column is None
    assert profile.exog_columns == []


def test_create_data_profile_output_when_single_series_hourly_with_exog():
    """
    Test create_data_profile detects exogenous columns, categorical exog,
    and hourly seasonality for an hourly series with exog variables.
    """
    profile = create_data_profile(data=df_single_hourly_exog, target="sales")

    assert profile.series_lengths["sales"].length == 720
    assert profile.frequency == "h"
    assert profile.index_type == "datetime"
    assert set(profile.exog_columns) == {"temperature", "promo_budget", "holiday"}
    assert "holiday" in profile.categorical_exog


def test_create_data_profile_output_when_multi_series_long_format():
    """
    Test create_data_profile correctly identifies multiple series in long
    format when series_id_column is provided.
    """
    profile = create_data_profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )

    assert profile.n_series == 3
    assert {k: v.length for k, v in profile.series_lengths.items()} == {
        "A": 100, "B": 100, "C": 100
    }
    assert profile.data_format == "long"
    assert profile.series_id_column == "series_id"
    assert profile.date_column == "date"
    assert profile.index_type == "datetime"
    assert "exog_1" in profile.exog_columns
    assert "value" not in profile.exog_columns
    assert "date" not in profile.exog_columns
    assert "series_id" not in profile.exog_columns


def test_create_data_profile_output_when_date_column_matches_index_name():
    """
    Test create_data_profile resolves date_column to the index when it
    matches the DatetimeIndex name (e.g. after set_index(date_column)).
    """
    df = df_single_daily.copy()
    df.index.name = "fecha"

    profile = create_data_profile(data=df, target="y", date_column="fecha")

    assert profile.index_type == "datetime"
    assert profile.date_column is None
    assert profile.frequency == "D"
    assert profile.start_date is not None


def test_create_data_profile_ValueError_when_date_column_not_found():
    """
    Test create_data_profile raises a ValueError when date_column matches
    neither a column nor the index name.
    """
    df = df_single_daily.copy()
    df.index.name = "fecha"

    err_msg = re.escape("date_column='wrong' was not found in the data.")
    with pytest.raises(ValueError, match=err_msg):
        create_data_profile(data=df, target="y", date_column="wrong")


def test_create_data_profile_ValueError_when_date_column_not_datetime():
    """
    Test create_data_profile raises a ValueError when date_column points to
    a column that does not hold dates, instead of profiling it as an
    exogenous variable.
    """
    df = df_single_daily.reset_index(drop=True)
    df["label"] = ["a"] * len(df)

    err_msg = re.escape(
        "date_column='label' does not hold dates: values such as ['a'] could "
        "not be parsed as timestamps."
    )
    with pytest.raises(ValueError, match=err_msg):
        create_data_profile(data=df, target="y", date_column="label")


def test_create_data_profile_output_when_date_column_is_string_dtype():
    """
    Test create_data_profile resolves date_column when it is a string or
    object column that parses to datetime.
    """
    df = df_single_daily.reset_index()
    df.rename(columns={"index": "fecha"}, inplace=True)
    df["fecha"] = df["fecha"].astype(str)

    profile = create_data_profile(data=df, target="y", date_column="fecha")

    assert profile.index_type == "datetime"
    assert profile.date_column == "fecha"
    assert profile.frequency == "D"
    assert profile.start_date is not None


def test_create_data_profile_output_when_missing_values_detected():
    """
    Test create_data_profile correctly reports per-column missing value
    counts.
    """
    profile = create_data_profile(data=df_with_missing, target="target")

    assert profile.missing_target == {"target": 3}
    assert profile.missing_exog == {"exog": 2}


def test_create_data_profile_output_when_no_datetime_index():
    """
    Test create_data_profile sets index_type to 'range' and emits a warning
    when no datetime index or column is found.
    """
    profile = create_data_profile(data=df_range_index, target="value")

    assert profile.index_type == "range"
    assert profile.frequency is None
    assert any("No datetime index" in w for w in profile.warnings)


def test_create_data_profile_output_when_short_series():
    """
    Test create_data_profile emits a warning when the series has fewer than
    50 observations.
    """
    profile = create_data_profile(data=df_short, target="y")

    assert profile.series_lengths["y"].length == 20
    assert any("Short series" in w for w in profile.warnings)


def test_create_data_profile_output_when_categorical_exog():
    """
    Test create_data_profile detects categorical exogenous variables based
    on dtype (object, category, bool).
    """
    profile = create_data_profile(data=df_single_hourly_exog, target="sales")

    assert "holiday" in profile.categorical_exog
    assert "temperature" not in profile.categorical_exog
    assert "promo_budget" not in profile.categorical_exog


def test_create_data_profile_output_when_csv_path_input(tmp_path):
    """
    Test create_data_profile works with a CSV file path as input, producing
    the same result as passing the DataFrame directly.
    """
    csv_file = tmp_path / "data.csv"
    df_single_daily.to_csv(csv_file)

    profile = create_data_profile(data=csv_file, target="y")

    assert isinstance(profile, DataProfile)
    assert profile.series_lengths["y"].length == 365
    assert profile.target == "y"
    assert profile.index_type == "datetime"


def test_create_data_profile_output_when_csv_path_input_string_dtype(tmp_path):
    """
    Test create_data_profile works with a CSV file path as input when the
    resulting loaded DataFrame has a modern string dtype for the date column.
    """
    csv_file = tmp_path / "data.csv"
    
    # Export without index
    df = df_single_daily.reset_index()
    df.rename(columns={"index": "date"}, inplace=True)
    df.to_csv(csv_file, index=False)

    # We mock pd.read_csv to return a DataFrame where the date column is explicitly 'string' dtype.
    # This simulates pandas>=2.0 read_csv with dtype_backend="pyarrow" or similar string inference.
    original_read_csv = pd.read_csv
    
    def mocked_read_csv(*args, **kwargs):
        df_loaded = original_read_csv(*args, **kwargs)
        df_loaded["date"] = df_loaded["date"].astype("string")
        return df_loaded
        
    import skforecast_ai.profiling.data_profile as dp
    dp.pd.read_csv = mocked_read_csv
    try:
        profile = create_data_profile(data=csv_file, target="y")
    finally:
        dp.pd.read_csv = original_read_csv

    assert isinstance(profile, DataProfile)
    assert profile.series_lengths["y"].length == 365
    assert profile.target == "y"
    assert profile.index_type == "datetime"
    assert profile.date_column == "date"


# ---------------------------------------------------------------------------
# Data format detection
# ---------------------------------------------------------------------------
def test_create_data_profile_raises_when_target_not_in_columns():
    df = pd.DataFrame({"y": np.arange(50, dtype=float)})
    with pytest.raises(ValueError, match="Target column"):
        create_data_profile(df, target="nonexistent")


def test_create_data_profile_output_when_data_format_long():
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "date": np.tile(dates, 2),
        "series_id": np.repeat(["A", "B"], 50),
        "value": np.arange(100, dtype=float),
    })
    profile = create_data_profile(
        df, target="value", date_column="date", series_id_column="series_id"
    )
    assert profile.data_format == "long"


def test_create_data_profile_output_when_data_format_single():
    df = pd.DataFrame(
        {"y": np.arange(100, dtype=float)},
        index=pd.date_range("2023-01-01", periods=100, freq="D"),
    )
    profile = create_data_profile(df, target="y")
    assert profile.data_format == "single"


def test_create_data_profile_output_when_data_format_wide():
    df = pd.DataFrame(
        {
            "series_a": np.arange(100, dtype=float),
            "series_b": np.arange(100, 200, dtype=float),
            "series_c": np.arange(200, 300, dtype=float),
        },
        index=pd.date_range("2023-01-01", periods=100, freq="D"),
    )
    profile = create_data_profile(
        df, target=["series_a", "series_b", "series_c"]
    )
    assert profile.data_format == "wide"
    assert profile.n_series == 3
    assert {k: v.length for k, v in profile.series_lengths.items()} == {
        "series_a": 100, "series_b": 100, "series_c": 100
    }


def test_create_data_profile_output_when_data_format_single_with_exog():
    df = pd.DataFrame(
        {
            "y": np.arange(100, dtype=float),
            "temp": np.random.default_rng(0).standard_normal(100),
            "humidity": np.random.default_rng(1).standard_normal(100),
            "holiday": ["no"] * 90 + ["yes"] * 10,
        },
        index=pd.date_range("2023-01-01", periods=100, freq="D"),
    )
    # Has non-numeric column → should be "single", not "wide"
    profile = create_data_profile(df, target="y")
    assert profile.data_format == "single"


# ---------------------------------------------------------------------------
# Target dtype
# ---------------------------------------------------------------------------
def test_create_data_profile_output_when_target_dtype_numeric():
    df = pd.DataFrame(
        {"sales": np.arange(50, dtype=float)},
        index=pd.date_range("2023-01-01", periods=50, freq="D"),
    )
    profile = create_data_profile(df, target="sales")
    assert profile.target_dtype == "numeric"


def test_create_data_profile_output_when_target_dtype_categorical():
    df = pd.DataFrame(
        {"category": pd.Categorical(["low", "mid", "high"] * 20)},
        index=pd.date_range("2023-01-01", periods=60, freq="D"),
    )
    profile = create_data_profile(df, target="category")
    assert profile.target_dtype == "categorical"


# ---------------------------------------------------------------------------
# Gaps, duplicates, monotonicity, frequency
# ---------------------------------------------------------------------------
def test_create_data_profile_output_when_has_gaps_true():
    """
    Test that create_data_profile infers the frequency of a series with
    missing timestamps, flags the gaps and warns with their count, instead
    of leaving the frequency unknown.
    """
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({"y": np.arange(100, dtype=float)}, index=dates)
    df_gapped = df.drop(dates[[50, 60, 70]])

    profile = create_data_profile(df_gapped, target="y")

    assert profile.frequency == "D"
    assert profile.has_gaps is True
    assert profile.closed_weekdays == []
    assert profile.warnings == [
        "Missing timestamps: 3 timestamps of frequency 'D' are missing from "
        "the date range. asfreq() inserts them as rows with missing values."
    ]


def test_create_data_profile_output_when_daily_data_closed_on_sundays():
    """
    Test that create_data_profile infers daily data without Sundays (a shop
    closed on them), whose gaps leave no ten days in a row, as daily with
    gaps: the Sundays are counted as missing timestamps, and the warning
    says that they all fall on Sundays, that a forecast predicts Sundays
    too, and that a business closed on them can fill them with 0, after
    asking the user. The profile keeps those days (`closed_weekdays`), which
    `create_cv` names. In long format, each shop is read on its own range.
    """
    dates = pd.date_range("2023-01-02", periods=364, freq="D")
    dates = dates[dates.dayofweek != 6]
    df = pd.DataFrame({"y": np.arange(len(dates), dtype=float)}, index=dates)

    profile = create_data_profile(df, target="y")
    profile_long = create_data_profile(
        df_no_sundays_long,
        target           = "sales",
        date_column      = "date",
        series_id_column = "shop",
    )

    assert profile.frequency == "D"
    assert profile.has_gaps is True
    assert profile.closed_weekdays == [6]
    assert profile_long.closed_weekdays == [6]
    assert profile.warnings == [
        "Missing timestamps: 51 timestamps of frequency 'D' are missing from "
        "the date range, all of them on Sundays, when the data never has a "
        "date. asfreq() inserts them as rows with missing values, and a "
        "forecast predicts Sundays too. If the business is closed on Sundays, "
        "they can be filled with 0 in the data, after asking the user."
    ]
    assert profile_long.frequency == "D"
    assert profile_long.warnings == [
        "Missing timestamps: 102 timestamps of frequency 'D' are missing from "
        "the date range, all of them on Sundays, when the series that miss "
        "them never have a date. asfreq() inserts them as rows with missing "
        "values, and a forecast predicts Sundays too. If the business is "
        "closed on Sundays, they can be filled with 0 in the data, after "
        "asking the user."
    ]


def test_create_data_profile_output_when_has_gaps_false():
    df = pd.DataFrame(
        {"y": np.arange(100, dtype=float)},
        index=pd.date_range("2023-01-01", periods=100, freq="D"),
    )
    profile = create_data_profile(df, target="y")
    assert profile.has_gaps is False
    assert profile.closed_weekdays == []


@pytest.mark.parametrize(
    "data, kwargs, err_msg",
    [
        (
            df_single_duplicate_values,
            {"target": "y"},
            "Found 5 timestamps with more than one row and different values, "
            "for example '2023-01-01'. A single series needs one row per "
            "timestamp, and keeping only one of them would silently discard "
            "data. Aggregate or remove the repeated rows before profiling, or "
            "pass `series_id_column` if a column identifies different series.",
        ),
        (
            df_multi_long,
            {"target": "value", "date_column": "date"},
            "Found 100 timestamps with more than one row and different values, "
            "for example '2023-01-01'. A single series needs one row per "
            "timestamp, and keeping only one of them would silently discard "
            "data. If the rows belong to different series, pass "
            "`series_id_column` (candidate columns: ['series_id']) to profile "
            "the data in long format. Otherwise, aggregate or remove the "
            "repeated rows before profiling.",
        ),
        (
            df_wide_duplicate_values,
            {"target": ["a", "b"]},
            "Found 5 timestamps with more than one row and different values, "
            "for example '2023-01-01'. Wide format needs one row per "
            "timestamp, with one column per series, and keeping only one of "
            "them would silently discard data. Aggregate or remove the "
            "repeated rows before profiling.",
        ),
        (
            df_long_duplicate_values_series_b,
            {
                "target": "value",
                "date_column": "date",
                "series_id_column": "series_id",
            },
            "Found 1 date with more than one row and different values within "
            "the same series, for example '2023-01-11' in series 'B' (affected "
            "series: ['B']). Each series needs one row per date, and keeping "
            "only one of them would silently discard data. Aggregate or "
            "remove the repeated rows of each series before profiling.",
        ),
    ],
    ids=[
        "single",
        "long data without series_id_column",
        "wide",
        "long, duplicate in the second series",
    ],
)
def test_create_data_profile_ValueError_when_duplicate_timestamps_have_different_values(
    data, kwargs, err_msg
):
    """
    Test that create_data_profile raises a ValueError when a timestamp has
    several rows with different values in the same series, instead of
    keeping the first row. Long-format data profiled without
    `series_id_column` gets the identifier column suggested (the float exog
    `exog_1` is not a candidate), and long-format data is checked in every
    series, not only the first one.
    """
    with pytest.raises(ValueError, match=re.escape(err_msg)):
        create_data_profile(data, **kwargs)


@pytest.mark.parametrize(
    "data, kwargs, expected_lengths, expected_warnings",
    [
        (
            df_single_identical_duplicates,
            {"target": "y"},
            {"y": 50},
            [
                "Duplicate timestamps: identical rows repeat 5 timestamps. The "
                "generated code keeps the first row of each.",
                "Missing values in exogenous columns: 'exog': 1. An estimator "
                "that does not accept missing values fails when it reads them.",
            ],
        ),
        (
            df_wide_identical_duplicates,
            {"target": ["a", "b"]},
            {"a": 50, "b": 50},
            [
                "Duplicate timestamps: identical rows repeat 5 timestamps. The "
                "generated code keeps the first row of each."
            ],
        ),
        (
            df_long_identical_duplicates_series_b,
            {
                "target": "value",
                "date_column": "date",
                "series_id_column": "series_id",
            },
            {"A": 100, "B": 100, "C": 100},
            [
                "Duplicate timestamps: identical rows repeat 1 timestamp. The "
                "generated code keeps the first row of each."
            ],
        ),
        (
            df_multiindex_identical_duplicates_series_b,
            {"target": "value"},
            {"A": 100, "B": 100, "C": 100},
            [
                "Duplicate timestamps: identical rows repeat 1 timestamp. The "
                "generated code keeps the first row of each."
            ],
        ),
    ],
    ids=["single", "wide", "long", "long with MultiIndex"],
)
def test_create_data_profile_output_when_duplicate_timestamps_are_identical(
    data, kwargs, expected_lengths, expected_warnings
):
    """
    Test that create_data_profile accepts timestamps repeated in identical
    rows (two missing values count as identical): it flags them, warns
    with their count, and describes the deduplicated data, so the series
    lengths and the frequency do not count the repeated rows. The single
    series keeps the missing value of its exogenous column, which is named.
    """
    profile = create_data_profile(data, **kwargs)

    assert profile.has_duplicate_timestamps is True
    assert profile.warnings == expected_warnings
    assert profile.frequency == "D"
    assert {
        name: info.length for name, info in profile.series_lengths.items()
    } == expected_lengths


def test_create_data_profile_output_when_index_not_monotonic():
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    df = pd.DataFrame(
        {"y": np.arange(50, dtype=float)},
        index=dates[::-1],
    )
    profile = create_data_profile(df, target="y")
    assert profile.index_is_monotonic is False


def test_create_data_profile_output_when_frequency_is_set():
    df = pd.DataFrame(
        {"y": np.arange(50, dtype=float)},
        index=pd.date_range("2023-01-01", periods=50, freq="D"),
    )
    profile = create_data_profile(df, target="y")
    assert profile.frequency_is_set is True


def test_create_data_profile_output_when_frequency_not_set():
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    dates_no_freq = pd.DatetimeIndex(dates.values)
    df = pd.DataFrame(
        {"y": np.arange(50, dtype=float)},
        index=dates_no_freq,
    )
    profile = create_data_profile(df, target="y")
    assert profile.frequency_is_set is False


# ---------------------------------------------------------------------------
# Constant target, missing values
# ---------------------------------------------------------------------------
def test_create_data_profile_ValueError_when_target_is_constant():
    """
    Test create_data_profile raises ValueError when the target column has
    zero variance.
    """
    df = pd.DataFrame(
        {"y": np.full(50, 5.0)},
        index=pd.date_range("2023-01-01", periods=50, freq="D"),
    )
    msg = re.escape("Target column 'y' is constant (zero variance).")
    with pytest.raises(ValueError, match=msg):
        create_data_profile(df, target="y")


def test_create_data_profile_output_when_target_not_constant():
    df = pd.DataFrame(
        {"y": np.arange(50, dtype=float)},
        index=pd.date_range("2023-01-01", periods=50, freq="D"),
    )
    profile = create_data_profile(df, target="y")

    assert profile.target == "y"
    assert profile.n_series == 1
    assert profile.frequency == "D"
    assert profile.target_stats["y"]["min"] == 0.0
    assert profile.target_stats["y"]["max"] == 49.0


def test_create_data_profile_missing_values_excludes_date_and_series_id():
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "series_id": ["A"] * 50,
        "value": np.arange(50, dtype=float),
    })
    df.loc[0, "date"] = pd.NaT
    profile = create_data_profile(
        df, target="value", date_column="date", series_id_column="series_id"
    )
    assert "date" not in profile.missing_exog
    assert "series_id" not in profile.missing_exog


# ---------------------------------------------------------------------------
# series_lengths: per-series ranges, MultiIndex, and unequal lengths
# ---------------------------------------------------------------------------
def test_create_data_profile_series_lengths_ranges_when_single_series():
    """
    Test series_lengths records the start, end, and length of a single
    series keyed by the target name.
    """
    df = pd.DataFrame(
        {"y": np.arange(365, dtype=float)},
        index=pd.date_range("2023-01-01", periods=365, freq="D"),
    )
    profile = create_data_profile(df, target="y")

    info = profile.series_lengths["y"]
    assert info.length == 365
    assert info.start == "2023-01-01"
    assert info.end == "2023-12-31"


def test_create_data_profile_output_when_multiindex_multi_series():
    """
    Test create_data_profile flattens a (series_id, datetime) MultiIndex
    into long format and reports per-series ranges.
    """
    dates_a = pd.date_range("2023-01-01", periods=100, freq="D")
    dates_b = pd.date_range("2023-01-01", periods=60, freq="D")
    index = pd.MultiIndex.from_tuples(
        [("A", d) for d in dates_a] + [("B", d) for d in dates_b],
        names=["series_id", "date"],
    )
    df = pd.DataFrame({"value": np.arange(160, dtype=float)}, index=index)

    profile = create_data_profile(df, target="value")

    assert profile.data_format == "long"
    assert profile.n_series == 2
    assert profile.series_id_column == "series_id"
    assert profile.date_column == "date"
    assert profile.series_lengths["A"].length == 100
    assert profile.series_lengths["B"].length == 60
    assert profile.series_lengths["A"].end == "2023-04-10"
    assert profile.series_lengths["B"].end == "2023-03-01"


@pytest.mark.parametrize(
    "names",
    [[None, None], ["series_id", None], [None, "date"]],
    ids=lambda names: f"names: {names}",
)
def test_create_data_profile_InvalidInputError_when_multiindex_level_unnamed(names):
    """
    Test create_data_profile rejects a MultiIndex with a level without a
    name instead of naming it: the generated script reads the levels by name
    from the frame saved with `to_csv()`, which writes an empty header for
    them.
    """
    data = df_multi_long.set_index(["series_id", "date"]).rename_axis(names)
    err_msg = re.escape(
        f"`data` is indexed by a MultiIndex with levels without a name "
        f"(names {names})."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        create_data_profile(data, target="value")

    assert exc_info.value.field == "data"


def test_create_data_profile_output_when_long_series_different_lengths():
    """
    Test create_data_profile records different per-series lengths and
    ranges for a long-format dataset with unequal series.
    """
    dates_a = pd.date_range("2023-01-01", periods=120, freq="D")
    dates_b = pd.date_range("2023-02-01", periods=80, freq="D")
    df = pd.DataFrame({
        "date": list(dates_a) + list(dates_b),
        "series_id": ["A"] * 120 + ["B"] * 80,
        "value": np.arange(200, dtype=float),
    })

    profile = create_data_profile(
        df, target="value", date_column="date", series_id_column="series_id"
    )

    assert profile.n_series == 2
    assert profile.series_lengths["A"].length == 120
    assert profile.series_lengths["B"].length == 80
    assert profile.series_lengths["A"].start == "2023-01-01"
    assert profile.series_lengths["B"].start == "2023-02-01"


def test_create_data_profile_start_date_keeps_time_when_not_midnight():
    """
    Test that the recorded start date carries the time component when the
    series does not start at midnight, so position-to-date conversions
    stay aligned with the actual timestamps.
    """
    df = pd.DataFrame(
        {"y": np.arange(48, dtype=float)},
        index=pd.date_range("2023-01-01 06:00:00", periods=48, freq="h"),
    )

    profile = create_data_profile(df, target="y")

    assert profile.start_date == "2023-01-01 06:00:00"


# =============================================================================
# Tests: rows not in date order
# =============================================================================
_SORTED_NOTE = (
    "Rows not in date order: they were sorted by date before profiling, as "
    "the generated code sorts them."
)


@pytest.mark.parametrize(
    "order, source",
    [
        ("descending", "index"),
        ("shuffled", "index"),
        ("descending", "date_column"),
        ("shuffled", "date_column"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_create_data_profile_sorts_rows_when_not_in_date_order(order, source):
    """
    Test that rows out of date order (h2o in descending or shuffled order)
    are profiled as the sorted data, with a note, `index_is_monotonic`
    False and no frequency set on the index. Before, descending dates gave
    the frequency '-1MS', a span of 0 and the last date as start date, and
    shuffled rows a wrong start date.
    """
    data = df_h2o.iloc[::-1] if order == "descending" else df_h2o.sample(
        frac=1, random_state=1
    )
    kwargs = {}
    if source == "date_column":
        data = data.reset_index()
        kwargs = {"date_column": "fecha"}

    profile = create_data_profile(data=data, target="x", **kwargs)

    assert profile.frequency == "MS"
    assert profile.start_date == "1991-07-01"
    assert profile.span_index_length == 204
    assert profile.n_total_observations == 204
    assert profile.series_lengths["x"].start == "1991-07-01"
    assert profile.series_lengths["x"].end == "2008-06-01"
    assert profile.series_lengths["x"].length == 204
    assert profile.has_gaps is False
    assert profile.has_duplicate_timestamps is False
    assert profile.index_is_monotonic is False
    assert profile.frequency_is_set is False
    assert profile.warnings == [_SORTED_NOTE]


def test_create_data_profile_sorts_rows_when_long_format_not_in_date_order():
    """
    Test that long-format rows out of date order within a series are sorted
    per series, with a note, and profiled as the sorted data.
    """
    shuffled = df_multi_long.sample(frac=1, random_state=0)

    profile = create_data_profile(
        data             = shuffled,
        target           = "value",
        date_column      = "date",
        series_id_column = "series_id",
    )

    assert profile.frequency == "D"
    assert profile.start_date == "2023-01-01"
    assert profile.span_index_length == 100
    assert {
        name: (info.start, info.end, info.length)
        for name, info in profile.series_lengths.items()
    } == {
        "A": ("2023-01-01", "2023-04-10", 100),
        "B": ("2023-01-01", "2023-04-10", 100),
        "C": ("2023-01-01", "2023-04-10", 100),
    }
    assert profile.has_gaps is False
    assert profile.index_is_monotonic is False
    assert profile.warnings == [
        "Rows not in date order within each series: they were sorted by date "
        "before profiling, as the generated code sorts them."
    ]


@pytest.mark.parametrize(
    "data, kwargs",
    [
        (df_h2o, {"target": "x"}),
        (
            df_multi_long.sort_values(["date", "series_id"]),
            {"target": "value", "date_column": "date", "series_id_column": "series_id"},
        ),
        (
            df_multi_long,
            {"target": "value", "date_column": "date", "series_id_column": "series_id"},
        ),
    ],
    ids=["single", "long_by_date", "long_by_series"],
)
def test_create_data_profile_no_sort_note_when_rows_in_date_order(data, kwargs):
    """
    Test that data in date order (long format by date or by series, which
    are both in date order within each series) gets no note and keeps
    `index_is_monotonic` True.
    """
    profile = create_data_profile(data=data, **kwargs)

    assert profile.index_is_monotonic is True
    assert profile.warnings == []


def test_create_data_profile_reads_text_dates_day_first_in_order():
    """
    Test that day-first text dates in an in-memory column are read with the
    format of the first date, as the generated script reads them: in date
    order, daily, without notes. Read one by one, '01/02/2012' was the
    second of January, so the frequency could not be inferred.
    """
    data = df_items_sales_long[df_items_sales_long["series"] == "item_1"]
    data = data.drop(columns="series").iloc[12:]
    data = data.assign(date=data["date"].dt.strftime("%d/%m/%Y"))

    profile = create_data_profile(data=data, target="value", date_column="date")

    assert profile.frequency == "D"
    assert profile.index_is_monotonic is True
    assert profile.start_date == "2012-01-13"
    assert profile.series_lengths["value"].end == "2012-04-29"
    assert profile.warnings == []


def test_create_data_profile_sorts_rows_when_text_dates_day_first_descending():
    """
    Test that day-first text dates in descending order (an in-memory column,
    latest first: '29/04/2012') are sorted with the dates parsed from the
    whole column, as the generated script reads them, instead of being
    parsed again from the new first row, '01/01/2012', which is read
    month-first and makes '13/01/2012' fail.
    """
    data = df_items_sales_long[df_items_sales_long["series"] == "item_1"]
    data = data.drop(columns="series").assign(
        date=data["date"].dt.strftime("%d/%m/%Y")
    )

    profile = create_data_profile(
        data=data.iloc[::-1], target="value", date_column="date"
    )

    assert profile.frequency == "D"
    assert profile.start_date == "2012-01-01"
    assert profile.series_lengths["value"].end == "2012-04-29"
    assert profile.warnings == [_SORTED_NOTE]


def test_create_data_profile_passes_date_column_to_csv_loader(tmp_path):
    """
    Test that, from a CSV path, `date_column` reaches the loader: a column of
    dates with empty cells before it ('contract_end') is left as an
    exogenous variable without a warning, and the named column is the date
    column.
    """
    data = df_h2o.reset_index().rename(columns={"fecha": "date"})
    data.insert(0, "contract_end", data["date"])
    data.loc[list(range(10)), "contract_end"] = None
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path, index=False)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        profile = create_data_profile(
                      data        = str(csv_path),
                      target      = "x",
                      date_column = "date",
                  )

    assert profile.date_column == "date"
    assert profile.frequency == "MS"
    assert profile.exog_columns == ["contract_end"]


# =============================================================================
# Tests: frequency of each series in long format
# =============================================================================
_LONG_KWARGS = {"target": "value", "date_column": "date", "series_id_column": "series"}


def _weekly(data: pd.DataFrame, series: str) -> pd.DataFrame:
    """Keep only the Sundays of one series of `df_items_sales_long`."""
    return data[(data["series"] != series) | (data["date"].dt.dayofweek == 6)]


@pytest.mark.parametrize(
    "data, err_msg",
    [
        (
            _weekly(df_items_sales_long, "item_3"),
            "The series do not share one frequency: 'D' (series 'item_1'), "
            "'W-SUN' (series 'item_3'). Every series of long-format data must "
            "have the same frequency; forecast the series of each frequency "
            "separately.",
        ),
        (
            _weekly(df_items_sales_long, "item_1"),
            "The series do not share one frequency: 'D' (series 'item_2'), "
            "'W-SUN' (series 'item_1'). Every series of long-format data must "
            "have the same frequency; forecast the series of each frequency "
            "separately.",
        ),
    ],
    ids=["weekly_last", "weekly_first"],
)
def test_create_data_profile_InvalidInputError_when_long_series_frequencies_differ(
    data, err_msg
):
    """
    Test that long-format series of different frequencies (one weekly series
    among daily ones in items_sales) raise, with the same frequencies named
    whatever the order of the series. Before, the frequency of the first
    series was used for all: a weekly series after daily ones was filled
    with missing values, and daily series after a weekly one were resampled
    to weekly, with only the warning of skforecast that a series is
    incomplete.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        create_data_profile(data=data, **_LONG_KWARGS)

    assert exc_info.value.field == "data"


def test_create_data_profile_InvalidInputError_when_long_timestamp_off_grid():
    """
    Test that a timestamp of a long-format series that is off the grid of
    the frequency of the other series raises, instead of being dropped by
    the generated script, which said nothing about it.
    """
    data = df_items_sales_long.copy()
    data.loc[130, "date"] = pd.Timestamp("2012-01-11 12:00")

    err_msg = re.escape(
        "Series 'item_2' has timestamps off the 'D' grid, for example "
        "2012-01-11 12:00:00. Every series of long-format data must have the "
        "same frequency on the same grid: correct or drop those timestamps, or "
        "forecast those series separately."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        create_data_profile(data=data, **_LONG_KWARGS)


def test_create_data_profile_InvalidInputError_when_long_weekly_series_has_gap():
    """
    Test that a weekly series with a missing week among daily ones, which is
    not regular on its own, raises as one of another frequency (every step
    a multiple of 7 days), instead of being read as a daily series with
    gaps.
    """
    weekly = df_items_sales_long[
        (df_items_sales_long["series"] == "item_3")
        & (df_items_sales_long["date"].dt.dayofweek == 6)
    ].drop(index=[261])
    data = pd.concat(
        [df_items_sales_long[df_items_sales_long["series"] != "item_3"], weekly]
    )

    err_msg = re.escape(
        "The series do not share one frequency: 'D' (series 'item_1'), "
        "'W-SUN' (series 'item_3')."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        create_data_profile(data=data, **_LONG_KWARGS)


def test_create_data_profile_InvalidInputError_when_long_aware_weekly_series():
    """
    Test that time zone aware long-format dates are checked too: a weekly
    series among daily ones raises, where the first series alone set the
    frequency.
    """
    data = df_items_sales_long.assign(
        date=df_items_sales_long["date"].dt.tz_localize("Europe/Madrid")
    )
    weekly = data[(data["series"] == "item_3") & (data["date"].dt.dayofweek == 6)]
    data = pd.concat([data[data["series"] != "item_3"], weekly])

    err_msg = re.escape(
        "The series do not share one frequency: 'D' (series 'item_1'), "
        "'W-SUN' (series 'item_3')."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        create_data_profile(data=data, **_LONG_KWARGS)


def test_create_data_profile_counts_missing_timestamps_of_every_long_series():
    """
    Test that the missing timestamps of every long-format series are
    counted, not only those of the first series: 20 dates removed from
    item_2 were reported as no gaps.
    """
    data = df_items_sales_long.drop(index=range(130, 150))

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency == "D"
    assert profile.has_gaps is True
    assert profile.warnings == [
        "Missing timestamps: 20 timestamps of frequency 'D' are missing from "
        "the date range. asfreq() inserts them as rows with missing values."
    ]


@pytest.mark.parametrize(
    "rows",
    [range(0, 118), range(240, 358)],
    ids=["first_series_short", "last_series_short"],
)
def test_create_data_profile_output_when_long_series_too_short_to_infer(rows):
    """
    Test that a long-format series whose frequency cannot be inferred on its
    own (two dates left) takes the frequency of the other series when its
    dates are on their grid, first or last. Before, a first series too short
    to infer gave no frequency at all.
    """
    data = df_items_sales_long.drop(index=rows)

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency == "D"


def test_create_data_profile_note_when_long_series_ends_early():
    """
    Test that a long-format series that ends before the last date of the
    data gets a note: a forecast of the future leaves it out without any
    warning (item_3 ending 30 days before the others).
    """
    data = df_items_sales_long.drop(index=range(330, 360))

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.series_lengths["item_3"].end == "2012-03-30"
    assert profile.warnings == [
        "Series ending early: 1 series ends before the last date with a value "
        "(2012-04-29): 'item_3' (2012-03-30). ForecasterRecursiveMultiSeries does "
        "not predict them, and ForecasterFoundation predicts each one after its "
        "own last row, rows without a value included."
    ]


def test_create_data_profile_note_when_long_series_ends_with_missing_values():
    """
    Test that a series whose last 30 rows have no value (skforecast drops
    them, so the series is not predicted) gets the note on series ending
    early, at the date of its last value.
    """
    data = df_items_sales_long.copy()
    data.loc[330:359, "value"] = np.nan

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.warnings[0] == (
        "Series ending early: 1 series ends before the last date with a value "
        "(2012-04-29): 'item_3' (2012-03-30). ForecasterRecursiveMultiSeries does "
        "not predict them, and ForecasterFoundation predicts each one after its "
        "own last row, rows without a value included."
    )


@pytest.mark.parametrize("dates_in", ["index", "column"])
def test_create_data_profile_note_when_wide_series_ends_early(dates_in):
    """
    Test that a wide-format series (column) whose last values are missing
    gets the note on series ending early, as in long format: a forecast of
    the future left it out without any warning (item_3 empty on the last 2
    dates, with the dates in the index or in a column).
    """
    data = df_items_sales_wide.copy()
    data.iloc[-2:, 2] = np.nan
    kwargs = {"target": ["item_1", "item_2", "item_3"]}
    if dates_in == "column":
        data = data.reset_index()
        kwargs["date_column"] = "date"

    profile = create_data_profile(data=data, **kwargs)

    assert profile.warnings == [
        "Series ending early: 1 series ends before the last date with a value "
        "(2012-04-29): 'item_3' (2012-04-27). ForecasterRecursiveMultiSeries does "
        "not predict them, and the other forecasters read their last values as "
        "missing values, which not every estimator or foundation model can use."
    ]


def test_create_data_profile_no_note_when_wide_series_end_together():
    """
    Test that wide-format series that all end on the same date, also with
    missing values at the end of every one, get no note on series ending
    early.
    """
    data = df_items_sales_wide.copy()
    data.iloc[-2:, :] = np.nan

    profile = create_data_profile(data=data, target=["item_1", "item_2", "item_3"])

    assert profile.warnings == []


@pytest.mark.parametrize("dates_in", ["index", "column"])
def test_create_data_profile_output_when_wide_series_start_late(dates_in):
    """
    Test that each wide-format series (column) spans the rows from its first
    to its last value, as a long-format series spans its own rows: item_2
    starts 30 days late and item_3 ends 2 days early. The span of the data
    and its first date stay those of the frame, which skforecast splits.
    """
    data = df_items_sales_wide.copy()
    data.iloc[:30, 1] = np.nan
    data.iloc[-2:, 2] = np.nan
    kwargs = {"target": ["item_1", "item_2", "item_3"]}
    if dates_in == "column":
        data = data.reset_index()
        kwargs["date_column"] = "date"

    profile = create_data_profile(data=data, **kwargs)

    assert profile.series_lengths == {
        "item_1": SeriesLengthInfo(
            start="2012-01-01", end="2012-04-29", length=120
        ),
        "item_2": SeriesLengthInfo(
            start="2012-01-31", end="2012-04-29", length=90
        ),
        "item_3": SeriesLengthInfo(
            start="2012-01-01", end="2012-04-27", length=118
        ),
    }
    assert profile.span_index_length == 120
    assert profile.span_start_date == "2012-01-01"
    assert profile.n_total_observations == 328


def test_create_data_profile_span_of_frame_when_every_wide_series_starts_late():
    """
    Test that the span of wide-format data is that of its frame when every
    series starts after its first row: skforecast splits the dates of the
    frame, whatever the first value of each series.
    """
    data = df_items_sales_wide.copy()
    data.iloc[:10, :] = np.nan

    profile = create_data_profile(data=data, target=["item_1", "item_2", "item_3"])

    assert {name: info.start for name, info in profile.series_lengths.items()} == {
        "item_1": "2012-01-11", "item_2": "2012-01-11", "item_3": "2012-01-11"
    }
    assert profile.span_index_length == 120
    assert profile.start_date == "2012-01-01"


def test_create_data_profile_note_names_short_wide_series():
    """
    Test that the note on short series names the wide-format series with
    fewer than 50 observations, from their first to their last value
    (item_2 with its last 20 values), instead of the bare count. The rate
    of missing values is still counted on the rows of the frame.
    """
    data = df_items_sales_wide.copy()
    data.iloc[:-20, 1] = np.nan

    profile = create_data_profile(data=data, target=["item_1", "item_2", "item_3"])

    assert profile.warnings == [
        "Short series: only 20 observations in series 'item_2'. Results may be "
        "unreliable with fewer than 50 observations.",
        "High missing value rate (83.3%). Consider imputation before "
        "forecasting.",
    ]


def test_create_data_profile_output_when_long_series_share_frequency():
    """
    Test that long-format series that share one frequency and end on the
    same date keep their profile (items_sales, 120 days).
    """
    profile = create_data_profile(data=df_items_sales_long, **_LONG_KWARGS)

    assert profile.frequency == "D"
    assert profile.has_gaps is False
    assert profile.start_date == "2012-01-01"
    assert profile.span_index_length == 120
    assert profile.warnings == []


def test_create_data_profile_output_when_first_long_row_has_no_series_id():
    """
    Test that a first row without a series id is left out, as the generated
    script leaves it out: the frequency and the start date come from the
    series. Before, the first series was the empty one, so the frequency
    and the start date were None.
    """
    first = pd.DataFrame(
        {"date": [pd.Timestamp("2012-01-05")], "series": [None], "value": [1.0]}
    )
    data = pd.concat([first, df_items_sales_long], ignore_index=True)

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency == "D"
    assert profile.start_date == "2012-01-01"
    assert profile.has_gaps is False


@pytest.mark.parametrize("unit", ["ns", "us", "s"], ids=lambda dt: f"unit: {dt}")
def test_create_data_profile_output_when_long_dates_in_other_units(unit):
    """
    Test that long-format dates stored in microseconds or seconds give the
    same daily frequency as in nanoseconds.
    """
    data = df_items_sales_long.assign(
        date=df_items_sales_long["date"].astype(f"datetime64[{unit}]")
    )

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency == "D"
    assert profile.has_gaps is False


def test_create_data_profile_output_when_long_dates_time_zone_aware():
    """
    Test that time zone aware long-format daily dates across a daylight
    saving time change (days of 23 hours) are read in local time: a daily
    frequency without gaps.
    """
    data = df_items_sales_long.assign(
        date=df_items_sales_long["date"].dt.tz_localize("Europe/Madrid")
    )

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency == "D"
    assert profile.has_gaps is False


def test_create_data_profile_output_when_long_hourly_dates_time_zone_aware():
    """
    Test that time zone aware long-format hourly dates across the change to
    summer time are read in UTC, where the hour skipped by the clocks is not
    missing, and that the two hours missing from the second series are
    counted.
    """
    dates = pd.date_range(
        "2023-03-24", "2023-03-28 23:00", freq="h", tz="Europe/Madrid"
    )
    data = pd.concat([
        pd.DataFrame({"series": "a", "date": dates, "value": np.arange(119.0)}),
        pd.DataFrame({
            "series": "b", "date": dates.delete([30, 31]), "value": np.arange(117.0)
        }),
    ])

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency == "h"
    assert profile.has_gaps is True
    assert profile.warnings == [
        "Missing timestamps: 2 timestamps of frequency 'h' are missing from the "
        "date range. asfreq() inserts them as rows with missing values."
    ]


def test_create_data_profile_output_when_long_dates_all_missing():
    """
    Test that long-format data without any row with both a date and a series
    id has no frequency, without an error.
    """
    data = df_items_sales_long.assign(date=pd.NaT)

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency is None


def test_create_data_profile_note_when_long_dates_beyond_nanoseconds():
    """
    Test that long-format dates after the year 2262, kept in seconds, are
    profiled from the first series, as before, with a note that the other
    series were not checked.
    """
    dates = np.array(
        [f"{year}-01-01" for year in range(2300, 2340)], dtype="datetime64[s]"
    )
    data = pd.DataFrame({
        "series": np.repeat(["a", "b"], 40),
        "date": np.concatenate([dates, dates]),
        "value": np.arange(80.0),
    })

    profile = create_data_profile(data=data, **_LONG_KWARGS)

    assert profile.frequency == "YS-JAN"
    assert profile.warnings == [
        "Short series: only 40 observations in 2 series ('a': 40, 'b': 40). "
        "Results may be unreliable with fewer than 50 observations.",
        "Long-format dates outside the years 1677 to 2262: the frequency and "
        "the missing timestamps were read from the first series only, so the "
        "other series were not checked."
    ]


# =============================================================================
# Tests: early input checks
# =============================================================================
@pytest.mark.parametrize(
    "series_id_column, date_column, err_msg",
    [
        (
            "missing",
            "date",
            "series_id_column='missing' was not found in the data. Available "
            "columns: ['date', 'series_id', 'value', 'exog_1'].",
        ),
        (
            "value",
            "date",
            "series_id_column='value' is also the target: pass the column "
            "that identifies the series, other than the values to forecast.",
        ),
        (
            "date",
            "date",
            "series_id_column='date' is also the date column: pass the column "
            "that identifies the series, other than the dates.",
        ),
    ],
    ids=["not a column", "the target", "the date column"],
)
def test_create_data_profile_InvalidInputError_when_series_id_column_invalid(
    series_id_column, date_column, err_msg
):
    """
    Test that a `series_id_column` that is not a column, or is the target or
    the date column, raises with the field 'series_id_column'.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        create_data_profile(
            data             = df_multi_long,
            target           = "value",
            date_column      = date_column,
            series_id_column = series_id_column,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "series_id_column"


def test_create_data_profile_InvalidInputError_when_target_is_empty_list():
    """
    Test that an empty list of targets raises with the field 'target'.
    """
    err_msg = re.escape(
        "`target` is an empty list: pass the name of the column to forecast, "
        "or a list with the column of each series."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        create_data_profile(data=df_single_daily, target=[])

    assert exc_info.value.field == "target"


@pytest.mark.parametrize(
    "data, target, series_id_column",
    [
        (df_items_sales_wide, ["item_1", "item_2"], "item_3"),
        (df_items_sales_long, ["value"], "series"),
    ],
    ids=["wide", "long"],
)
def test_create_data_profile_InvalidInputError_when_target_list_with_series_id_column(
    data, target, series_id_column
):
    """
    Test that a list of targets with a `series_id_column` raises with the
    field 'series_id_column', on wide data (where the id column was dropped)
    and on long data (where the repeated timestamps blamed the data), and
    that a list of one column is not read as its name.
    """
    err_msg = re.escape(
        f"`target` is a list of columns ({target}) and series_id_column="
        f"{series_id_column!r} was also given: a list of columns is wide "
        f"format (one column per series) and `series_id_column` is long "
        f"format (the series stacked in rows, told apart by that column). "
        f"For long format, pass `target` as the name of the column of "
        f"values, not as a list; for wide format, leave out "
        f"`series_id_column`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        create_data_profile(
            data             = data,
            target           = target,
            series_id_column = series_id_column,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "series_id_column"


@pytest.mark.parametrize(
    "series",
    [["item_1"], ["item_1", "item_2"]],
    ids=["one series", "two series"],
)
def test_create_data_profile_InvalidInputError_when_target_list_and_multiindex(
    series,
):
    """
    Test that a list of targets with a `(series_id, date)` MultiIndex raises
    with the field 'target', since a MultiIndex is long format: with two
    series instead of the error about repeated timestamps that blamed the
    data, with one instead of profiling it as wide data, and in both cases
    without naming the `series_id_column` that the first level fills and the
    caller did not pass.
    """
    data = df_items_sales_long[df_items_sales_long["series"].isin(series)]
    data = data.set_index(["series", "date"])
    err_msg = re.escape(
        "`target` is a list of columns (['value']), but `data` is indexed by "
        "a MultiIndex (levels ['series', 'date']), which is long format: the "
        "series are stacked in rows, told apart by the first level. Pass "
        "`target` as the name of the column of values, not as a list."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        create_data_profile(data=data, target=["value"])

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "target"


def test_create_data_profile_output_when_target_text_and_multiindex():
    """
    Test that the name of the column of values with a `(series_id, date)`
    MultiIndex still profiles long data, with the first level as the
    `series_id_column`.
    """
    data = df_items_sales_long.set_index(["series", "date"])

    profile = create_data_profile(data=data, target="value")

    assert profile.data_format == "long"
    assert profile.target == "value"
    assert profile.series_id_column == "series"
    assert profile.n_series == 3


def test_create_data_profile_InvalidInputError_when_target_list_repeats_column():
    """
    Test that a list of targets naming a column more than once raises with
    the field 'target' and names the repeated column, instead of profiling
    one column as two series.
    """
    err_msg = re.escape(
        "`target` names a column more than once: ['item_1']. A list of "
        "targets holds one column per series: name each one once."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        create_data_profile(
            data   = df_items_sales_wide,
            target = ["item_1", "item_2", "item_1"],
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "target"


def test_create_data_profile_output_when_target_list_is_valid():
    """
    Test that a list of targets naming each column once, without
    `series_id_column`, profiles as wide data with the columns in the order
    given.
    """
    profile = create_data_profile(
        data   = df_items_sales_wide,
        target = ["item_3", "item_1"],
    )

    assert profile.data_format == "wide"
    assert profile.target == ["item_3", "item_1"]
    assert profile.series_id_column is None
    assert profile.n_series == 2
    assert list(profile.series_lengths) == ["item_3", "item_1"]


def test_create_data_profile_InvalidInputError_when_target_has_no_values():
    """
    Test that a target column with every value missing raises with the code
    'insufficient_data' and the field 'target'.
    """
    data = df_single_daily.assign(y=np.nan)

    err_msg = re.escape("Target column 'y' has no values: every row is missing.")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        create_data_profile(data=data, target="y")

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "target"


def test_create_data_profile_output_when_target_is_numeric_strings():
    """
    Test that a target of text, such as numeric strings, is described and
    not rejected: only `ForecastingAssistant.profile()` checks that the
    target holds numbers.
    """
    data = df_single_daily.assign(y=df_single_daily["y"].astype(str))

    profile = create_data_profile(data=data, target="y")

    assert profile.target == "y"
    assert profile.series_lengths["y"].length == 365


@pytest.mark.parametrize(
    (
        "exog_columns, expected_exog, expected_categorical, expected_missing, "
        "expected_unused"
    ),
    [
        (None, ["temperature", "promo_budget", "holiday"], ["holiday"], {}, []),
        (["holiday"], ["holiday"], ["holiday"], {}, ["temperature", "promo_budget"]),
        ([], [], [], {}, ["temperature", "promo_budget", "holiday"]),
    ],
    ids=["None", "subset", "none"],
)
def test_create_data_profile_output_when_exog_columns(
    exog_columns, expected_exog, expected_categorical, expected_missing,
    expected_unused,
):
    """
    Test that `exog_columns` keeps the exogenous columns named, describes
    only those (categorical and missing values) and lists the others in
    `unused_columns`.
    """
    profile = create_data_profile(
                  data         = df_single_hourly_exog,
                  target       = "sales",
                  exog_columns = exog_columns,
              )

    assert profile.exog_columns == expected_exog
    assert profile.categorical_exog == expected_categorical
    assert profile.missing_exog == expected_missing
    assert profile.unused_columns == expected_unused


def test_create_data_profile_output_when_exog_columns_leave_out_missing_values():
    """
    Test that the missing values of a column left out by `exog_columns` are
    not counted in `missing_exog`.
    """
    data = df_with_missing.assign(other=1.0)

    profile = create_data_profile(
                  data         = data,
                  target       = "target",
                  exog_columns = ["other"],
              )
    default = create_data_profile(data=data, target="target")

    assert default.missing_exog == {"exog": 2}
    assert profile.missing_exog == {}
    assert profile.unused_columns == ["exog"]


def test_create_data_profile_output_when_exog_columns_are_dirty():
    """
    Test that numbers written as text in exogenous columns ('12%', '-') are
    profiled as categorical, unchanged, with a warning per column, that true
    categories get none, and that a single missing value of a numeric
    exogenous column is named with its count.
    """
    profile = create_data_profile(data=df_dirty_exog, target="y")

    assert profile.categorical_exog == [
        "pct", "dash", "mixed", "store", "code", "few"
    ]
    assert profile.missing_exog == {"x_na": 2}
    assert profile.warnings == [
        "Short series: only 30 observations. Results may be unreliable with "
        "fewer than 50 observations.",
        "Missing values in exogenous columns: 'x_na': 2. An estimator that "
        "does not accept missing values fails when it reads them.",
        "Numbers written as text in exogenous column 'pct': all of its values "
        "are numbers, once a final '%' and spaces are removed, or markers of "
        "missing values (it holds numbers with a final '%'), so it is used as a categorical "
        "variable with 30 levels. If it is a numeric variable, write its "
        "values as plain numbers in the data, without '%' and with empty "
        "cells instead of '-' for missing values (ask the user before "
        "changing their file); if it holds categories, nothing needs to "
        "change.",
        "Numbers written as text in exogenous column 'dash': all of its values "
        "are numbers, once a final '%' and spaces are removed, or markers of "
        "missing values (it holds cells of '-'), so it is used as a categorical "
        "variable with 28 levels. If it is a numeric variable, write its "
        "values as plain numbers in the data, without '%' and with empty "
        "cells instead of '-' for missing values (ask the user before "
        "changing their file); if it holds categories, nothing needs to "
        "change.",
        "Numbers written as text in exogenous column 'mixed': all of its "
        "values are numbers, once a final '%' and spaces are removed, or "
        "markers of missing values (it holds numbers with a final '%', cells "
        "of '-', blank cells and numbers with spaces), so it is used as a "
        "categorical variable with 30 levels. If it is a numeric variable, "
        "write its values as plain numbers in the data, without '%' and with "
        "empty cells instead of '-' for missing values (ask the user before "
        "changing their file); if it holds categories, nothing needs to "
        "change.",
    ]


def test_create_data_profile_output_when_csv_exog_columns_are_dirty(tmp_path):
    """
    Test that the same warnings are given when the data is read from a CSV
    file, where '-' and '12%' keep the column as text and an empty cell is a
    missing value.
    """
    path = tmp_path / "dirty.csv"
    df_dirty_exog.to_csv(path, index_label="date")

    from_file = create_data_profile(data=path, target="y")
    from_frame = create_data_profile(data=df_dirty_exog, target="y")

    assert from_file.categorical_exog == from_frame.categorical_exog
    assert from_file.missing_exog == from_frame.missing_exog
    assert from_file.warnings == from_frame.warnings


def test_create_data_profile_InvalidInputError_when_exog_columns_not_in_data():
    """
    Test that a column of `exog_columns` that is not in the data raises
    InvalidInputError with the field 'exog_columns'.
    """
    err_msg = re.escape(
        "`exog_columns` names columns that are not in the data: ['price']. "
        "Columns of the data: ['sales', 'temperature', 'promo_budget', "
        "'holiday']."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        create_data_profile(
            data         = df_single_hourly_exog,
            target       = "sales",
            exog_columns = ["price"],
        )

    assert exc_info.value.field == "exog_columns"


@pytest.mark.parametrize(
    "freq, tz",
    [("D", None), ("h", "Europe/Madrid"), ("W-MON", None), ("MS", None), ("15min", None)],
    ids=["daily", "hourly with time zone", "weekly", "monthly", "15 minutes"],
)
def test_create_data_profile_emits_no_warning_for_long_data_with_gaps(freq, tz):
    """
    Test that profiling long format data with missing dates emits no warning
    of its own: with numpy 2.5, `pd.Timedelta(days=1)` and the like emit a
    DeprecationWarning (the generic timedelta unit) that a user running with
    warnings as errors would get from `profile()`.
    """
    index = pd.date_range("2022-01-03", periods=120, freq=freq, tz=tz)
    data = pd.concat([
        pd.DataFrame({
            "date": index, "series": name, "value": np.arange(120) % 7 + 0.5
        })
        for name in ("a", "b")
    ]).reset_index(drop=True).drop([5, 6])

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        profile = create_data_profile(
            data, target="value", date_column="date", series_id_column="series"
        )

    assert profile.frequency == freq
    assert profile.n_series == 2


# =============================================================================
# Tests: series ids and series names as text
# =============================================================================
_TEXT_COLUMNS_HINT = (
    "Rename the columns of the DataFrame to text, for example with "
    "`data.columns = data.columns.astype(str)`, and pass their names as text "
    "in `target`."
)
_MISSING_TARGET_HINT = (
    "If the user named this column, tell them it is not in the data and ask "
    "which one to forecast before using another."
)
_LONG_IDS_KWARGS = {
    "target": "value", "date_column": "date", "series_id_column": "series_id",
}

# Two daily series named with numbers, as a DataFrame read by other means
# may hold them.
df_wide_integer_columns = pd.DataFrame(
    {1: np.arange(60, dtype=float), 2: np.arange(60, dtype=float) * 2},
    index=pd.date_range("2023-01-01", periods=60, freq="D"),
)


@pytest.mark.parametrize("date_column", ["date", None], ids=lambda dt: f"date: {dt}")
def test_create_data_profile_series_ids_are_text_when_csv_path_input(
    tmp_path, date_column
):
    """
    Test that the ids of a CSV file ('001', '1' and '10') are read as text, so
    they stay three series with their zeros, in the order of their text, and
    the profile describes them as the generated script reads them.
    """
    csv_file = tmp_path / "ids.csv"
    df_multi_long_numeric_ids.to_csv(csv_file, index=False)

    profile = create_data_profile(
        data             = csv_file,
        target           = "value",
        date_column      = date_column,
        series_id_column = "series_id",
    )

    assert list(profile.series_lengths) == ["001", "1", "10"]
    assert {k: v.length for k, v in profile.series_lengths.items()} == {
        "001": 100, "1": 100, "10": 100
    }
    assert profile.n_series == 3
    assert profile.data_format == "long"
    assert profile.date_column == "date"
    assert profile.frequency == "D"
    assert profile.warnings == []


def test_create_data_profile_series_ids_are_not_the_date_column_when_csv_path_input(
    tmp_path,
):
    """
    Test that a first column of ids that read as years ('2001', '2002') is
    kept as the series ids and is not taken for the date column: the dates are
    in the column 'date'.
    """
    csv_file = tmp_path / "years.csv"
    df_multi_long_numeric_ids.assign(
        series_id=df_multi_long_numeric_ids["series_id"].map(
            {"001": "2001", "1": "2002", "10": "2003"}
        )
    )[["series_id", "date", "value"]].to_csv(csv_file, index=False)

    profile = create_data_profile(
        data=csv_file, target="value", series_id_column="series_id"
    )

    assert list(profile.series_lengths) == ["2001", "2002", "2003"]
    assert profile.date_column == "date"
    assert profile.frequency == "D"
    assert profile.warnings == []


@pytest.mark.parametrize(
    "multiindex", [False, True], ids=lambda dt: f"multiindex: {dt}"
)
def test_create_data_profile_series_ids_are_text_when_integer_ids(multiindex):
    """
    Test that integer ids of a DataFrame (1, 2 and 10), in a column or in the
    first level of a MultiIndex, are turned into text, so the series are named
    '1', '10' and '2' (the order of their text) as the generated script
    names them.
    """
    data = df_multi_long_integer_ids
    kwargs = dict(_LONG_IDS_KWARGS)
    if multiindex:
        data = data.set_index(["series_id", "date"])
        kwargs["date_column"] = None

    profile = create_data_profile(data=data, **kwargs)

    assert list(profile.series_lengths) == ["1", "10", "2"]
    assert {k: v.length for k, v in profile.series_lengths.items()} == {
        "1": 100, "10": 100, "2": 100
    }
    assert profile.n_series == 3
    assert profile.series_id_column == "series_id"
    assert profile.frequency == "D"
    assert profile.warnings == []


def test_create_data_profile_series_ids_do_not_modify_input():
    """
    Test that the DataFrame given keeps its integer ids: they are turned into
    text in a copy.
    """
    data = df_multi_long_integer_ids.copy()

    create_data_profile(data=data, **_LONG_IDS_KWARGS)

    pd.testing.assert_frame_equal(data, df_multi_long_integer_ids)


def test_create_data_profile_series_ids_leave_out_rows_without_id():
    """
    Test that a row without series id is left out, with the ids of the other
    rows turned into text: there is no series named 'nan', and the three
    series keep their 100 rows.
    """
    first = pd.DataFrame(
        {
            "date": [pd.Timestamp("2023-01-05")],
            "series_id": [None],
            "value": [1.0],
        }
    )
    data = pd.concat(
        [first, df_multi_long_integer_ids.astype({"series_id": object})],
        ignore_index=True,
    )

    profile = create_data_profile(data=data, **_LONG_IDS_KWARGS)

    assert list(profile.series_lengths) == ["1", "10", "2"]
    assert {k: v.length for k, v in profile.series_lengths.items()} == {
        "1": 100, "10": 100, "2": 100
    }
    assert profile.n_series == 3
    assert profile.frequency == "D"
    assert profile.start_date == "2023-01-01"
    assert profile.warnings == []


@pytest.mark.parametrize(
    "target, listed",
    [
        ([1, 2], "[1, 2]"),
        ([1], "[1]"),
        ([1, "x"], "[1]"),
        (1, "[1]"),
    ],
    ids=["integers", "one integer", "integer and text", "single integer"],
)
def test_create_data_profile_InvalidInputError_when_target_is_not_named_with_text(
    target, listed
):
    """
    Test that a target given with names that are not text raises an
    InvalidInputError with the field 'target', the names that are not text and
    the hint to rename the columns, because skforecast names the series with
    text.
    """
    err_msg = re.escape(
        f"Target column(s) {listed} are not named with text: the series are "
        f"named after their columns, and their names must be text."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        create_data_profile(data=df_wide_integer_columns, target=target)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "target"
    assert exc_info.value.hint == _TEXT_COLUMNS_HINT


@pytest.mark.parametrize(
    "target, listed, hint",
    [
        (["1", "2"], "['1', '2']", _TEXT_COLUMNS_HINT),
        ("1", "['1']", _TEXT_COLUMNS_HINT),
        (["a"], "['a']", _MISSING_TARGET_HINT),
        (["1", "a"], "['1', 'a']", _MISSING_TARGET_HINT),
    ],
    ids=["text names of the integers", "one text name", "unknown name",
         "text name and unknown name"],
)
def test_create_data_profile_InvalidInputError_when_text_target_not_found_in_integer_columns(
    target, listed, hint
):
    """
    Test that text names for columns named with integers keep the message
    that they are not found and add the hint to rename the columns, while a
    name that matches no column, alone or next to one that does, has the
    hint to tell the user that the column they named is not in the data and
    ask before forecasting another one.
    """
    err_msg = re.escape(
        f"Target column(s) {listed} not found in the DataFrame. Available "
        f"columns: [1, 2]"
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        create_data_profile(data=df_wide_integer_columns, target=target)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "target"
    assert exc_info.value.hint == hint


# ---------------------------------------------------------------------------
# Order of the day and the month of the dates, and other date formats
# ---------------------------------------------------------------------------
_AMBIGUOUS_FOUND = (
    "The dates of column 'date' read both day first and month first: no day "
    "is after the 12th, so '01/02/2020' may be '2020-02-01' or '2020-01-02', "
    "and both readings have a regular frequency ('MS' day first and 'D' month "
    "first), so the order is not guessed"
)
_AMBIGUOUS_CSV_ERROR = (
    _AMBIGUOUS_FOUND + ". Profile the file saying which it is, with `dayfirst`."
)
_AMBIGUOUS_FRAME_ERROR = (
    _AMBIGUOUS_FOUND + ". Profile the data saying which it is, with `dayfirst`."
)


def _regular_order_note(read: str, quoted: str, remedy: str, name="date") -> str:
    """
    Return the note of dates whose order was told from their regularity
    (monthly, 'MS'), read in the order `read`, with the remedy for the
    other order.
    """
    other = "month" if read == "day" else "day"
    return (
        f"The dates of column {name!r} read both day first and month first "
        f"(no day is after the 12th): they were read {read} first, the only "
        f"order in which they have a regular frequency ('MS'), so {quoted}. "
        f"If they are written {other} first, {remedy}."
    )


_SPANISH_FILE_NOTE = _regular_order_note(
    "day",
    "'01/02/2015' is '2015-02-01' and not '2015-01-02'",
    "profile the file again with `dayfirst=False` in `profile()`, "
    "`--monthfirst` in the `profile` command or `dayfirst` false in the "
    "`profile` tool of the MCP server",
)
_US_FILE_NOTE = _regular_order_note(
    "month",
    "'02/01/2015' is '2015-02-01' and not '2015-01-02'",
    "profile the file again with `dayfirst=True` in `profile()`, "
    "`--dayfirst` in the `profile` command or `dayfirst` true in the "
    "`profile` tool of the MCP server",
)
_DAYFIRST_IGNORED = (
    "`dayfirst` does not apply and is ignored: {reason}. It orders the day "
    "and the month of dates written as text, such as '01/02/2020'."
)
_DAYFIRST_CONTRADICTION_HINT = (
    "Leave `dayfirst` out, so the order is told from the dates."
)
_COULD_NOT_INFER_FREQUENCY = (
    "Could not infer frequency from the datetime index: the spacing is "
    "irregular, or there are too few timestamps."
)


def test_create_data_profile_date_format_when_day_first_dates_in_csv(tmp_path):
    """
    Test that a CSV file of daily dates written day first ('01/01/2020', with
    days after the 12th) is read day first, and the profile records the
    format the generated script must read them with: the frequency is daily
    from the 1st of January, not from the 1st of every month.
    """
    csv_file = tmp_path / "daily.csv"
    df_dates_day_first.to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y")

    assert profile.date_column == "date"
    assert profile.date_format == "%d/%m/%Y"
    assert profile.index_type == "datetime"
    assert profile.frequency == "D"
    assert profile.start_date == "2020-01-01"
    assert profile.series_lengths["y"].start == "2020-01-01"
    assert profile.series_lengths["y"].end == "2020-03-30"
    assert profile.series_lengths["y"].length == 90
    assert profile.exog_columns == []
    assert profile.csv_sep == ","
    assert profile.csv_decimal == "."
    assert profile.csv_thousands is None
    assert profile.warnings == []


def test_create_data_profile_date_format_when_month_first_dates_in_csv(tmp_path):
    """
    Test that a CSV file of dates written month first ('01/13/2020', with
    days after the 12th) is read month first, and its format is recorded
    too, so future exogenous values whose dates read in both orders are
    read like the data.
    """
    csv_file = tmp_path / "month_first.csv"
    df_dates_month_first.to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y")

    assert profile.date_column == "date"
    assert profile.date_format == "%m/%d/%Y"
    assert profile.frequency == "D"
    assert profile.start_date == "2020-01-13"
    assert profile.series_lengths["y"].end == "2020-03-12"
    assert profile.warnings == []


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
@pytest.mark.parametrize(
    "data, expected_format, expected_note",
    [
        (df_dates_monthly_ambiguous, "%d/%m/%Y", _SPANISH_FILE_NOTE),
        (df_dates_monthly_us, "%m/%d/%Y", _US_FILE_NOTE),
    ],
    ids=["spanish monthly", "us monthly"],
)
def test_create_data_profile_output_when_csv_dates_read_in_both_orders_and_one_is_regular(
    tmp_path, data, expected_format, expected_note, date_column
):
    """
    Test that a CSV file of five years of monthly dates on the first of each
    month, whose dates all read day first and month first ('01/02/2015' of a
    Spanish file, '02/01/2015' of a US file), is read in the only order in
    which the dates have a regular frequency: monthly ('MS') from January
    2015, day first for the Spanish file and month first for the US one,
    whether the date column is named or found. The format is recorded, and
    a note in `warnings` says that the order was told from the regularity
    and how to give the other one.
    """
    csv_file = tmp_path / "monthly.csv"
    data.to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y", date_column=date_column)

    assert profile.date_column == "date"
    assert profile.date_format == expected_format
    assert profile.frequency == "MS"
    assert profile.start_date == "2015-01-01"
    assert profile.series_lengths["y"].end == "2019-12-01"
    assert profile.series_lengths["y"].length == 60
    assert profile.warnings == [expected_note]


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
def test_create_data_profile_InvalidInputError_when_csv_dates_read_in_both_orders(
    tmp_path, date_column
):
    """
    Test that a CSV file of three monthly dates written day first with no
    day after the 12th ('01/02/2020', the 1st of February or the 2nd of
    January), which have a regular frequency in both orders ('MS' day first,
    'D' month first), raises an InvalidInputError with the code
    'data_unreadable', the field 'data' and the hint that names `dayfirst`:
    the order is never guessed, whether the column of dates is named or
    found.
    """
    csv_file = tmp_path / "three.csv"
    df_dates_three_ambiguous.to_csv(csv_file, index=False)

    with pytest.raises(
        InvalidInputError, match="^" + re.escape(_AMBIGUOUS_CSV_ERROR) + "$"
    ) as exc_info:
        create_data_profile(data=csv_file, target="y", date_column=date_column)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DAYFIRST_HINT


@pytest.mark.parametrize(
    "kwargs, expected_format, expected_frequency",
    [
        ({}, "%d/%m/%y", "D"),
        ({"date_column": "date"}, "%d/%m/%y", "D"),
    ],
    ids=["date column found", "date column given"],
)
def test_create_data_profile_output_when_csv_dates_have_a_year_of_two_digits(
    tmp_path, kwargs, expected_format, expected_frequency
):
    """
    Test that daily dates written day first with a year of two digits
    ('01/01/18', then '13/01/18'), whose format pandas does not guess, are
    read day first and their format recorded, instead of one by one with
    the frequency lost.
    """
    csv_file = tmp_path / "short.csv"
    pd.DataFrame({
        "date": pd.date_range("2018-01-01", periods=40, freq="D")
                .strftime("%d/%m/%y"),
        "y": np.arange(40, dtype=float),
    }).to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y", **kwargs)

    assert profile.date_format == expected_format
    assert profile.frequency == expected_frequency
    assert profile.start_date == "2018-01-01"
    assert profile.series_lengths["y"].end == "2018-02-09"


def test_create_data_profile_output_when_csv_short_year_dates_read_both_ways(
    tmp_path,
):
    """
    Test that two years of monthly dates on the first day with a year of two
    digits ('01/02/18') are read in the order told from their regularity,
    as those with four digits, with the format and the note.
    """
    csv_file = tmp_path / "short.csv"
    pd.DataFrame({
        "date": pd.date_range("2018-01-01", periods=24, freq="MS")
                .strftime("%d/%m/%y"),
        "y": np.arange(24, dtype=float),
    }).to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y")

    assert profile.date_format == "%d/%m/%y"
    assert profile.frequency == "MS"
    assert profile.series_lengths["y"].end == "2019-12-01"
    assert profile.warnings[0] == (
        _regular_order_note(
            "day",
            "'01/02/18' is '2018-02-01' and not '2018-01-02'",
            "profile the file again with `dayfirst=False` in `profile()`, "
            "`--monthfirst` in the `profile` command or `dayfirst` false in "
            "the `profile` tool of the MCP server",
        )
    )


def test_create_data_profile_InvalidInputError_when_csv_short_year_dates_read_both_ways(
    tmp_path,
):
    """
    Test that three monthly dates with a year of two digits ('01/02/18'),
    regular in both orders, raise the error of the order, as those with four
    digits.
    """
    csv_file = tmp_path / "short.csv"
    pd.DataFrame({
        "date": ["01/01/18", "01/02/18", "01/03/18"],
        "y": [1.0, 2.0, 4.0],
    }).to_csv(csv_file, index=False)

    with pytest.raises(
        InvalidInputError, match="^The dates of column 'date' read"
    ) as exc_info:
        create_data_profile(data=csv_file, target="y")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == DAYFIRST_HINT


def test_create_data_profile_output_when_dataframe_dates_are_whole_numbers_as_text():
    """
    Test that dates such as '20200131' written as text (a CSV file read with
    its date column as text) record the format '%Y%m%d', as the same dates
    read as whole numbers do.
    """
    data = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=30, freq="D")
                .strftime("%Y%m%d"),
        "y": np.arange(30, dtype=float),
    })

    profile = create_data_profile(data=data, target="y", date_column="date")

    assert profile.date_format == "%Y%m%d"
    assert profile.frequency == "D"


def test_create_data_profile_output_when_csv_dates_are_the_same_in_both_orders(
    tmp_path,
):
    """
    Test that annual dates on the first of January ('01/01/2000'), which read
    the same day first and month first, are profiled without asking for the
    order and without a format: yearly, from 2000.
    """
    csv_file = tmp_path / "annual.csv"
    pd.DataFrame({
        "date": [f"01/01/{year}" for year in range(2000, 2024)],
        "y": np.arange(24, dtype=float),
    }).to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y")

    assert profile.date_format is None
    assert profile.frequency == "YS-JAN"
    assert profile.start_date == "2000-01-01"


@pytest.mark.parametrize(
    "kwargs, expected_format, expected_frequency, expected_end",
    [
        ({"dayfirst": True}, "%d/%m/%Y", "MS", "2019-12-01"),
        ({"dayfirst": False}, "%m/%d/%Y", None, "2019-01-12"),
        ({"date_format": "%d/%m/%Y"}, "%d/%m/%Y", "MS", "2019-12-01"),
        ({"date_format": "%m/%d/%Y"}, "%m/%d/%Y", None, "2019-01-12"),
    ],
    ids=[
        "dayfirst true",
        "dayfirst false",
        "format day first",
        "format month first",
    ],
)
def test_create_data_profile_output_when_csv_dates_read_in_both_orders_and_order_given(
    tmp_path, kwargs, expected_format, expected_frequency, expected_end
):
    """
    Test that the order of monthly dates that read both ways is the one given
    with `dayfirst` or with the format of a profile of the data, and that
    the profile records the format in either order: read day first they are
    monthly ('MS'); read month first ('01/02/2015' is the 2nd of January)
    they have no frequency.
    """
    csv_file = tmp_path / "monthly.csv"
    df_dates_monthly_ambiguous.to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y", **kwargs)

    assert profile.date_column == "date"
    assert profile.date_format == expected_format
    assert profile.frequency == expected_frequency
    assert profile.start_date == "2015-01-01"
    assert profile.series_lengths["y"].end == expected_end
    assert profile.series_lengths["y"].length == 60
    if expected_frequency is None:
        assert profile.warnings == [_COULD_NOT_INFER_FREQUENCY]
    else:
        assert profile.warnings == []


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
def test_create_data_profile_InvalidInputError_when_dayfirst_against_csv_dates(
    tmp_path, date_column
):
    """
    Test that `dayfirst=True` on a CSV file of dates that only read month
    first ('01/13/2020') raises an InvalidInputError on the field 'dayfirst'
    that quotes the first date that does not fit, with the hint to leave
    `dayfirst` out.
    """
    csv_file = tmp_path / "month_first.csv"
    df_dates_month_first.to_csv(csv_file, index=False)

    err_msg = re.escape(
        "`dayfirst` is True, but the dates of column 'date' do not read day "
        "first: '01/13/2020' only reads month first. Leave `dayfirst` out to "
        "tell the order from the dates."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg) as exc_info:
        create_data_profile(
            data=csv_file, target="y", date_column=date_column, dayfirst=True
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "dayfirst"
    assert exc_info.value.hint == _DAYFIRST_CONTRADICTION_HINT


def test_create_data_profile_InvalidInputError_when_dayfirst_false_against_csv_dates(
    tmp_path,
):
    """
    Test that `dayfirst=False` on a CSV file of dates that only read day first
    ('13/01/2020') raises an InvalidInputError on the field 'dayfirst' that
    quotes the first date that does not fit, with the hint to leave
    `dayfirst` out.
    """
    csv_file = tmp_path / "daily.csv"
    df_dates_day_first.to_csv(csv_file, index=False)

    err_msg = re.escape(
        "`dayfirst` is False, but the dates of column 'date' do not read "
        "month first: '13/01/2020' only reads day first. Leave `dayfirst` out "
        "to tell the order from the dates."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg) as exc_info:
        create_data_profile(
            data=csv_file, target="y", date_column="date", dayfirst=False
        )

    assert exc_info.value.field == "dayfirst"
    assert exc_info.value.hint == _DAYFIRST_CONTRADICTION_HINT


def test_create_data_profile_dayfirst_agreeing_with_csv_dates_changes_nothing(
    tmp_path,
):
    """
    Test that `dayfirst` agreeing with dates that read in only one order gives
    the same profile as without it.
    """
    day_first_file = tmp_path / "daily.csv"
    df_dates_day_first.to_csv(day_first_file, index=False)
    month_first_file = tmp_path / "month_first.csv"
    df_dates_month_first.to_csv(month_first_file, index=False)

    day_first = create_data_profile(data=day_first_file, target="y", dayfirst=True)
    month_first = create_data_profile(
        data=month_first_file, target="y", dayfirst=False
    )

    assert day_first == create_data_profile(data=day_first_file, target="y")
    assert day_first.date_format == "%d/%m/%Y"
    assert month_first == create_data_profile(data=month_first_file, target="y")
    assert month_first.date_format == "%m/%d/%Y"


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
def test_create_data_profile_output_when_csv_dates_are_whole_numbers(
    tmp_path, date_column
):
    """
    Test that a CSV file whose dates are whole numbers of eight digits
    ('20200101') has them read as dates, found or named: the column is the
    date column and not an exogenous variable, the profile records the
    format '%Y%m%d' and the series is daily.
    """
    csv_file = tmp_path / "compact.csv"
    df_dates_compact.to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y", date_column=date_column)

    assert profile.date_column == "date"
    assert profile.date_format == "%Y%m%d"
    assert profile.exog_columns == []
    assert profile.index_type == "datetime"
    assert profile.frequency == "D"
    assert profile.start_date == "2020-01-01"
    assert profile.series_lengths["y"].end == "2020-03-30"
    assert profile.series_lengths["y"].length == 90
    assert profile.warnings == []


@pytest.mark.parametrize(
    "data, expected_start, expected_end",
    [
        (df_german_from_15th, "2020-01-15", "2020-03-14"),
        (df_german_from_1st, "2020-01-01", "2020-02-29"),
    ],
    ids=["first date after the 12th", "first date on the 1st"],
)
@pytest.mark.parametrize(
    "kwargs",
    [{}, {"date_column": "datum"}, {"sep": ";", "decimal": ","}],
    ids=["dialect detected", "date column given", "separator and decimal given"],
)
def test_create_data_profile_output_when_german_spreadsheet_csv(
    tmp_path, data, expected_start, expected_end, kwargs
):
    """
    Test that a ';' CSV file with dates written with points ('15.01.2020')
    and amounts with '.' between thousands ('1.234,56'), as a German
    spreadsheet exports it, is profiled with ';' as separator, ',' as decimal
    mark and '.' as thousands separator, the dates read day first (also when
    the first one is the 1st of January) and recorded as '%d.%m.%Y', and the
    amounts read as numbers.
    """
    csv_file = write_german_excel(tmp_path, data)

    profile = create_data_profile(data=csv_file, target="umsatz", **kwargs)

    assert (profile.csv_sep, profile.csv_decimal, profile.csv_thousands) == (
        ";", ",", ".",
    )
    assert profile.date_column == "datum"
    assert profile.date_format == "%d.%m.%Y"
    assert profile.exog_columns == []
    assert profile.frequency == "D"
    assert profile.start_date == expected_start
    assert profile.series_lengths["umsatz"].end == expected_end
    assert profile.series_lengths["umsatz"].length == 60
    stats = profile.target_stats["umsatz"]
    assert (stats["min"], stats["max"], stats["mean"]) == (1234.56, 7149.31, 4191.935)
    assert np.isclose(stats["std"], 1750.7909819564416)
    assert profile.warnings == []


@pytest.mark.parametrize(
    "dayfirst", [None, True], ids=lambda dt: f"dayfirst: {dt}"
)
def test_create_data_profile_german_spreadsheet_csv_dates_read_in_both_orders(
    tmp_path, dayfirst
):
    """
    Test that a German spreadsheet of monthly dates with points ('01.02.2015')
    is profiled with the dialect of the file and its dates read day first:
    told from their regularity, with the note, or given by `dayfirst`,
    without it.
    """
    csv_file = write_german_excel(tmp_path, df_german_monthly)

    profile = create_data_profile(
        data=csv_file, target="umsatz", dayfirst=dayfirst
    )

    assert (profile.csv_sep, profile.csv_decimal, profile.csv_thousands) == (
        ";", ",", ".",
    )
    assert profile.date_format == "%d.%m.%Y"
    assert profile.frequency == "MS"
    assert profile.start_date == "2015-01-01"
    assert profile.series_lengths["umsatz"].end == "2019-12-01"
    assert profile.warnings == (
        [
            _regular_order_note(
                "day",
                "'01.02.2015' is '2015-02-01' and not '2015-01-02'",
                "profile the file again with `dayfirst=False` in `profile()`, "
                "`--monthfirst` in the `profile` command or `dayfirst` false "
                "in the `profile` tool of the MCP server",
                name="datum",
            )
        ]
        if dayfirst is None else []
    )


def test_create_data_profile_date_format_is_None_when_iso_dates_in_csv(tmp_path):
    """
    Test that a CSV file of ISO 8601 dates is profiled as it always was: no
    format is recorded, because the generated script reads them without one.
    """
    csv_file = tmp_path / "iso.csv"
    df_dates_iso.to_csv(csv_file, index=False)

    profile = create_data_profile(data=csv_file, target="y")

    assert profile.date_column == "date"
    assert profile.date_format is None
    assert profile.index_type == "datetime"
    assert profile.frequency == "D"
    assert profile.start_date == "2020-01-01"
    assert profile.series_lengths["y"].start == "2020-01-01"
    assert profile.series_lengths["y"].end == "2020-03-30"
    assert profile.series_lengths["y"].length == 90
    assert profile.exog_columns == []
    stats = profile.target_stats["y"]
    assert (stats["min"], stats["max"], stats["mean"]) == (10.0, 54.5, 32.25)
    assert np.isclose(stats["std"], 13.062350477613132)
    assert profile.warnings == []


def test_create_data_profile_date_format_when_day_first_dates_in_long_csv(tmp_path):
    """
    Test that a long-format CSV file with dates written day first is read day
    first for every series, and the profile records the format.
    """
    csv_file = tmp_path / "long.csv"
    df_multi_long.assign(date=df_multi_long["date"].dt.strftime("%d/%m/%Y")).to_csv(
        csv_file, index=False
    )

    profile = create_data_profile(
        data=csv_file, target="value", series_id_column="series_id"
    )

    assert profile.data_format == "long"
    assert profile.n_series == 3
    assert profile.date_column == "date"
    assert profile.date_format == "%d/%m/%Y"
    assert profile.frequency == "D"
    assert profile.start_date == "2023-01-01"
    assert {k: v.end for k, v in profile.series_lengths.items()} == {
        "A": "2023-04-10", "B": "2023-04-10", "C": "2023-04-10"
    }
    assert profile.exog_columns == ["exog_1"]
    assert profile.warnings == []


def test_create_data_profile_date_format_when_day_first_text_in_dataframe():
    """
    Test that a DataFrame whose `date_column` holds day-first text is read
    day first, and the profile records the format the generated script must
    read the dates with, without changing the DataFrame given.
    """
    data = df_dates_day_first.copy()

    profile = create_data_profile(data=data, target="y", date_column="date")

    assert profile.date_column == "date"
    assert profile.date_format == "%d/%m/%Y"
    assert profile.frequency == "D"
    assert profile.start_date == "2020-01-01"
    assert profile.series_lengths["y"].end == "2020-03-30"
    pd.testing.assert_frame_equal(data, df_dates_day_first)


def test_create_data_profile_date_format_when_month_first_text_in_dataframe():
    """
    Test that a DataFrame whose `date_column` holds month-first text (with
    days after the 12th) is read month first, with the format recorded.
    """
    profile = create_data_profile(
        data=df_dates_month_first, target="y", date_column="date"
    )

    assert profile.date_format == "%m/%d/%Y"
    assert profile.start_date == "2020-01-13"
    assert profile.frequency == "D"


def test_create_data_profile_date_format_when_whole_numbers_in_dataframe():
    """
    Test that a DataFrame whose `date_column` holds whole numbers of eight
    digits has them read as dates, and the profile records '%Y%m%d'.
    """
    profile = create_data_profile(data=df_dates_compact, target="y", date_column="date")

    assert profile.date_column == "date"
    assert profile.date_format == "%Y%m%d"
    assert profile.frequency == "D"
    assert profile.start_date == "2020-01-01"
    assert profile.exog_columns == []


def test_create_data_profile_InvalidInputError_when_dataframe_dates_read_in_both_orders():
    """
    Test that a DataFrame with three monthly text dates that read day first
    and month first, regular in both orders, raises an InvalidInputError
    with the code 'data_unreadable', the field 'data' and the hint that
    names `dayfirst` of `profile()`: the order is never guessed.
    """
    err_msg = re.escape(_AMBIGUOUS_FRAME_ERROR)
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        create_data_profile(
            data=df_dates_three_ambiguous, target="y", date_column="date"
        )

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DAYFIRST_FRAME_HINT


@pytest.mark.parametrize(
    "dayfirst, expected_format, expected_frequency, expected_end",
    [
        (True, "%d/%m/%Y", "MS", "2020-03-01"),
        (False, "%m/%d/%Y", "D", "2020-01-03"),
    ],
    ids=["dayfirst true", "dayfirst false"],
)
def test_create_data_profile_output_when_dayfirst_decides_dataframe_dates(
    dayfirst, expected_format, expected_frequency, expected_end
):
    """
    Test that `dayfirst` gives the order of the text dates of a DataFrame
    that read both ways, as for a CSV file: three dates regular in both
    orders are monthly day first and daily month first, and the profile
    records the format, without a note.
    """
    profile = create_data_profile(
        data        = df_dates_three_ambiguous,
        target      = "y",
        date_column = "date",
        dayfirst    = dayfirst,
    )

    assert profile.date_format == expected_format
    assert profile.frequency == expected_frequency
    assert profile.series_lengths["y"].end == expected_end
    assert all("read both day first" not in note for note in profile.warnings)


def test_create_data_profile_output_when_dataframe_dates_read_in_both_orders_and_one_is_regular():
    """
    Test that the monthly text dates of a DataFrame that read both ways are
    read in the only order in which they have a regular frequency, day
    first, with the note that gives `dayfirst` of `profile()` for the other
    order.
    """
    profile = create_data_profile(
        data=df_dates_monthly_ambiguous, target="y", date_column="date"
    )

    assert profile.date_format == "%d/%m/%Y"
    assert profile.frequency == "MS"
    assert profile.warnings == [
        _regular_order_note(
            "day",
            "'01/02/2015' is '2015-02-01' and not '2015-01-02'",
            "profile the data again with `dayfirst=False`",
        )
    ]


@pytest.mark.parametrize(
    "data, date_column, reason",
    [
        (
            df_dates_day_first.assign(
                date=pd.to_datetime(df_dates_day_first["date"], format="%d/%m/%Y")
            ),
            "date",
            "the dates of column 'date' are not text, so the order of their "
            "day and month is already set",
        ),
        (
            df_dates_day_first.assign(
                date=pd.to_datetime(df_dates_day_first["date"], format="%d/%m/%Y")
            ).set_index("date"),
            None,
            "the dates of the index are not text, so the order of their day "
            "and month is already set",
        ),
        (
            df_dates_day_first,
            None,
            "the data has no dates written as text (a text column of dates is "
            "read when `date_column` names it)",
        ),
    ],
    ids=["datetime column", "datetime index", "text dates not named"],
)
def test_create_data_profile_IgnoredArgumentWarning_when_dayfirst_and_dataframe_dates_not_text(
    data, date_column, reason
):
    """
    Test that `dayfirst` with a DataFrame whose dates are not text (a
    datetime column or index), or that has no date column, emits an
    IgnoredArgumentWarning saying that it does not apply, and the profile
    is the one without it.
    """
    warn_msg = re.escape(_DAYFIRST_IGNORED.format(reason=reason))
    with pytest.warns(IgnoredArgumentWarning, match="^" + warn_msg):
        profile = create_data_profile(
            data=data, target="y", date_column=date_column, dayfirst=True
        )

    assert profile == create_data_profile(
        data=data, target="y", date_column=date_column
    )


@pytest.mark.parametrize(
    "date_format, expected_frequency",
    [("%d/%m/%Y", "MS"), ("%m/%d/%Y", None)],
    ids=lambda dt: f"{dt}",
)
def test_create_data_profile_output_when_date_format_decides_dataframe_dates(
    date_format, expected_frequency
):
    """
    Test that monthly text dates of a DataFrame that read both ways are read
    in the order of the `date_format` given (the format of a profile of the
    data), which the profile records.
    """
    profile = create_data_profile(
        data        = df_dates_monthly_ambiguous,
        target      = "y",
        date_column = "date",
        date_format = date_format,
    )

    assert profile.date_format == date_format
    assert profile.frequency == expected_frequency
    assert profile.start_date == "2015-01-01"


def test_create_data_profile_date_format_recorded_when_dataframe_dates_are_parsed():
    """
    Test that the `date_format` given with a DataFrame whose dates were
    already parsed (read from a CSV file) is the one recorded, and that it is
    not when the dates are the index, where the script needs no format.
    """
    data = df_dates_day_first.assign(
        date=pd.to_datetime(df_dates_day_first["date"], format="%d/%m/%Y")
    )

    column = create_data_profile(
        data=data, target="y", date_column="date", date_format="%d/%m/%Y"
    )
    index = create_data_profile(
        data=data.set_index("date"), target="y", date_format="%d/%m/%Y"
    )

    assert column.date_format == "%d/%m/%Y"
    assert column.frequency == "D"
    assert index.date_format is None
    assert index.frequency == "D"


def test_create_data_profile_date_format_is_None_when_dates_in_the_index():
    """
    Test that a DataFrame indexed by dates records no format.
    """
    profile = create_data_profile(data=df_single_daily, target="y")

    assert profile.date_format is None


@pytest.mark.parametrize("name", ["excel.csv", "excel.csv.gz"], ids=["plain", "gzip"])
def test_create_data_profile_output_when_csv_is_cp1252(tmp_path, name):
    """
    Test that the CSV that Excel saves on Windows in Spanish (cp1252, ';',
    ',' as decimal mark, 'año' in the header, accents in the categories) is
    profiled with its names and categories read right, its encoding
    recorded next to its dialect and a note first among the warnings that
    says the encoding cannot be checked; also compressed with gzip.
    """
    csv_file = write_cp1252(tmp_path, name=name)

    profile = create_data_profile(data=csv_file, target="año")

    assert (profile.csv_sep, profile.csv_decimal, profile.csv_encoding) == (
        ";", ",", "cp1252",
    )
    assert profile.date_column == "fecha"
    assert profile.date_format == "%d/%m/%Y"
    assert profile.exog_columns == ["zona"]
    assert profile.categorical_exog == ["zona"]
    assert profile.series_lengths["año"].length == 60
    assert profile.warnings == [cp1252_note()]


@pytest.mark.parametrize(
    "encoding, expected_warnings",
    [(None, []), ("utf-8", []), ("cp1252", [cp1252_note()])],
    ids=lambda dt: f"{dt}",
)
def test_create_data_profile_output_when_encoding_of_dataframe_read(
    encoding, expected_warnings
):
    """
    Test that the encoding of the CSV file a DataFrame was read from is
    recorded ('utf-8' when it is not given), with the note on cp1252.
    """
    profile = create_data_profile(
                  data     = df_single_daily,
                  target   = "y",
                  encoding = encoding,
              )

    assert profile.csv_encoding == (encoding or "utf-8")
    assert profile.warnings == expected_warnings
