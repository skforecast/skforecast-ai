# Unit test create_data_profile

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling import create_data_profile
from skforecast_ai.schemas import DataProfile

from .fixtures_profiling import (
    df_multi_long,
    df_range_index,
    df_short,
    df_single_daily,
    df_single_hourly_exog,
    df_with_missing,
)


def test_create_data_profile_output_when_single_series_daily():
    """
    Test create_data_profile returns correct profile for a single daily
    series with DatetimeIndex.
    """
    profile = create_data_profile(data=df_single_daily, target="y")

    assert isinstance(profile, DataProfile)
    assert profile.n_observations == 365
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

    assert profile.n_observations == 720
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
    assert profile.n_observations == 100  # min series length (all equal here)
    assert profile.series_lengths == {"A": 100, "B": 100, "C": 100}
    assert profile.data_format == "long"
    assert profile.series_id_column == "series_id"
    assert profile.date_column == "date"
    assert profile.index_type == "datetime"
    assert "exog_1" in profile.exog_columns
    assert "value" not in profile.exog_columns
    assert "date" not in profile.exog_columns
    assert "series_id" not in profile.exog_columns


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

    assert profile.n_observations == 20
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
    assert profile.n_observations == 365
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
    assert profile.n_observations == 365
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
    assert profile.n_observations == 100
    assert profile.series_lengths == {
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
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    values = np.arange(100, dtype=float)
    values[10] = np.nan
    values[20] = np.nan
    df = pd.DataFrame({"y": values}, index=dates)
    df_gapped = df.drop(dates[[50, 60, 70]])
    from skforecast_ai.profiling.data_profile import detect_gaps
    gapped_index = pd.DatetimeIndex(df_gapped.index)
    assert detect_gaps(gapped_index, "D") is True


def test_create_data_profile_output_when_has_gaps_false():
    df = pd.DataFrame(
        {"y": np.arange(100, dtype=float)},
        index=pd.date_range("2023-01-01", periods=100, freq="D"),
    )
    profile = create_data_profile(df, target="y")
    assert profile.has_gaps is False


def test_create_data_profile_output_when_has_duplicate_timestamps():
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    dup_dates = dates.append(dates[:5])
    df = pd.DataFrame(
        {"y": np.arange(55, dtype=float)},
        index=dup_dates,
    )
    profile = create_data_profile(df, target="y")
    assert profile.has_duplicate_timestamps is True


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
    assert profile is not None


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
