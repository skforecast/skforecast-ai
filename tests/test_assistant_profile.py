# Unit test profile ForecastingAssistant

from pathlib import Path

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import DataProfile, ForecastingProfile

from tests.fixtures_assistant import (
    df_single,
    df_no_exog,
    df_short,
    df_multi_long,
    df_multi_wide,
    df_with_missing,
    df_constant_target,
)


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_profile_ValueError_when_target_column_not_found():
    """
    Test that profile() raises ValueError when the target column does not
    exist in the DataFrame.
    """
    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="not found"):
        assistant.profile(
            data=df_single, target="nonexistent", date_column="date"
        )


def test_profile_ValueError_when_constant_target():
    """
    Test that profile() raises ValueError when the target column has zero
    variance (constant series).
    """
    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="constant"):
        assistant.profile(
            data=df_constant_target, target="sales", date_column="date"
        )


# =============================================================================
# Tests: basic output
# =============================================================================
def test_profile_output_when_single_series():
    """
    Test that profile() returns a ForecastingProfile with correct DataProfile
    for a single-series DataFrame.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_single, target="sales", date_column="date"
    )

    assert isinstance(profile, ForecastingProfile)
    assert isinstance(profile.data_profile, DataProfile)
    assert profile.data_profile.target == "sales"
    assert profile.data_profile.series_lengths["sales"].length == 100
    assert profile.data_profile.n_series == 1
    assert profile.data_profile.index_type == "datetime"
    assert "promo" in profile.data_profile.exog_columns
    assert profile.forecaster_candidates
    assert profile.forecaster == profile.forecaster_candidates[0]


def test_profile_output_when_no_exog():
    """
    Test that profile() returns a ForecastingProfile with empty exog_columns
    when no exogenous variables are present.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_no_exog, target="sales", date_column="date"
    )

    assert profile.data_profile.exog_columns == []
    assert profile.data_profile.n_series == 1


# =============================================================================
# Tests: feature-rich / multi-series
# =============================================================================
def test_profile_output_when_multi_series_long_format():
    """
    Test that profile() correctly identifies a long-format multi-series
    dataset with series_id_column.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )

    assert profile.data_profile.n_series == 2
    assert profile.data_profile.data_format == "long"
    assert profile.forecaster == "ForecasterRecursiveMultiSeries"


def test_profile_output_when_multi_series_wide_format():
    """
    Test that profile() correctly identifies a wide-format multi-series
    dataset with multiple target columns.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide,
        target=["series_a", "series_b"],
        date_column="date",
    )

    assert profile.data_profile.n_series == 2
    assert profile.data_profile.data_format == "wide"
    assert profile.forecaster == "ForecasterRecursiveMultiSeries"


def test_profile_output_when_data_has_missing_values():
    """
    Test that profile() succeeds when data has NaN values and populates
    the missing_target field in DataProfile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_with_missing, target="sales", date_column="date"
    )

    assert isinstance(profile, ForecastingProfile)
    assert profile.data_profile.missing_target != {}


def test_profile_output_when_short_series():
    """
    Test that profile() handles a short time series (25 observations)
    without errors.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_short, target="sales", date_column="date"
    )

    assert isinstance(profile, ForecastingProfile)
    assert profile.data_profile.series_lengths["sales"].length == 25


# =============================================================================
# Tests: input type variants
# =============================================================================
@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_profile_output_when_csv_path(tmp_path, path_type):
    """
    Test that profile() accepts CSV file paths as str or Path objects.
    """
    csv_path = tmp_path / "data.csv"
    df_single.to_csv(csv_path, index=False)

    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=path_type(csv_path), target="sales", date_column="date"
    )

    assert isinstance(profile, ForecastingProfile)
    assert profile.data_profile.target == "sales"
    assert profile.data_profile.series_lengths["sales"].length == 100
