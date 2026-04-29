# Unit test create_data_profile

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
    assert 7 in profile.inferred_seasonalities


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
    assert 24 in profile.inferred_seasonalities


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

    assert profile.missing_values == {"target": 3, "exog": 2}


def test_create_data_profile_output_when_no_datetime_index():
    """
    Test create_data_profile sets index_type to 'range' and emits a warning
    when no datetime index or column is found.
    """
    profile = create_data_profile(data=df_range_index, target="value")

    assert profile.index_type == "range"
    assert profile.frequency is None
    assert profile.inferred_seasonalities == []
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
