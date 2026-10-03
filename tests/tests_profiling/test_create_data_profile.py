# Unit test create_data_profile

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling import create_data_profile
from skforecast_ai.schemas import DataProfile

from ..fixtures_datasets import df_h2o, df_items_sales_long, df_items_sales_wide
from .fixtures_profiling import (
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
    assert profile.warnings == [
        "Missing timestamps: 3 timestamps of frequency 'D' are missing from "
        "the date range. asfreq() inserts them as rows with missing values."
    ]


def test_create_data_profile_output_when_has_gaps_false():
    df = pd.DataFrame(
        {"y": np.arange(100, dtype=float)},
        index=pd.date_range("2023-01-01", periods=100, freq="D"),
    )
    profile = create_data_profile(df, target="y")
    assert profile.has_gaps is False


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
    "data, kwargs, expected_lengths, expected_warning",
    [
        (
            df_single_identical_duplicates,
            {"target": "y"},
            {"y": 50},
            "Duplicate timestamps: identical rows repeat 5 timestamps. The "
            "generated code keeps the first row of each.",
        ),
        (
            df_wide_identical_duplicates,
            {"target": ["a", "b"]},
            {"a": 50, "b": 50},
            "Duplicate timestamps: identical rows repeat 5 timestamps. The "
            "generated code keeps the first row of each.",
        ),
        (
            df_long_identical_duplicates_series_b,
            {
                "target": "value",
                "date_column": "date",
                "series_id_column": "series_id",
            },
            {"A": 100, "B": 100, "C": 100},
            "Duplicate timestamps: identical rows repeat 1 timestamp. The "
            "generated code keeps the first row of each.",
        ),
        (
            df_multiindex_identical_duplicates_series_b,
            {"target": "value"},
            {"A": 100, "B": 100, "C": 100},
            "Duplicate timestamps: identical rows repeat 1 timestamp. The "
            "generated code keeps the first row of each.",
        ),
    ],
    ids=["single", "wide", "long", "long with MultiIndex"],
)
def test_create_data_profile_output_when_duplicate_timestamps_are_identical(
    data, kwargs, expected_lengths, expected_warning
):
    """
    Test that create_data_profile accepts timestamps repeated in identical
    rows (two missing values count as identical): it flags them, warns
    with their count, and describes the deduplicated data, so the series
    lengths and the frequency do not count the repeated rows.
    """
    profile = create_data_profile(data, **kwargs)

    assert profile.has_duplicate_timestamps is True
    assert profile.warnings == [expected_warning]
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
    not regular on its own and too short to infer with gaps, raises as one
    of another frequency (every step a multiple of 7 days), instead of being
    read as a daily series with gaps.
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
        "Short series: only 40 observations. Results may be unreliable with "
        "fewer than 50 observations.",
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
