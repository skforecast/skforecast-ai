# Unit test derive_preprocessing_steps recommendation/preprocessing

from skforecast_ai.recommendation import derive_preprocessing_steps
from skforecast_ai.schemas import DataProfile, PreprocessingStep


def test_derive_steps_returns_empty_when_no_issues():
    profile = DataProfile(
        series_lengths={"y": 365},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        data_format="single",
        frequency_is_set=True,
        index_is_monotonic=True,
        has_duplicate_timestamps=False,
        has_gaps=False,
        target_dtype="numeric",
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    assert steps == []


def test_derive_steps_no_sort_index_step():
    """sort_index is now handled by the template, not preprocessing steps."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        index_is_monotonic=False,
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "sort_index" not in actions


def test_derive_steps_includes_drop_duplicates_when_duplicates():
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        has_duplicate_timestamps=True,
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "drop_duplicates" in actions


def test_derive_steps_no_asfreq_step():
    """asfreq is now handled by the template, not preprocessing steps."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        frequency_is_set=False,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "asfreq" not in actions


def test_derive_steps_no_set_datetime_index_step():
    """set_datetime_index is now handled by the template."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="other",
        target="y",
        date_column="date",
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "set_datetime_index" not in actions


def test_derive_steps_provides_datetime_index_when_no_date_column():
    """provide_datetime_index is kept for unresolvable case."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="other",
        target="y",
        date_column=None,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "provide_datetime_index" in actions


def test_derive_steps_no_reshape_for_multi_series_long():
    """reshape_long_to_dict is now handled by the template."""
    profile = DataProfile(
        series_lengths={"value": 300},
        n_series=3,
        index_type="datetime",
        frequency="D",
        target="value",
        date_column="date",
        series_id_column="series_id",
        data_format="long",
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(
        profile, "ForecasterRecursiveMultiSeries"
    )
    actions = [s.action for s in steps]
    assert "reshape_long_to_dict" not in actions


def test_derive_steps_no_reshape_for_multi_series_wide():
    profile = DataProfile(
        series_lengths={"value": 300},
        n_series=3,
        index_type="datetime",
        frequency="D",
        target="value",
        data_format="wide",
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(
        profile, "ForecasterRecursiveMultiSeries"
    )
    actions = [s.action for s in steps]
    assert "reshape_long_to_dict" not in actions


def test_derive_steps_includes_encode_target_when_non_numeric():
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        target_dtype="categorical",
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "encode_target" in actions


def test_derive_steps_includes_handle_missing_values_when_missing_target():
    """handle_missing_values step is added when the target has NaNs."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        missing_target={"y": 3},
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "handle_missing_values" in actions


def test_derive_steps_includes_handle_categorical_exog_when_categorical():
    """handle_categorical_exog step is added when categorical exog present."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["holiday"],
        categorical_exog=["holiday"],
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "handle_categorical_exog" in actions


def test_derive_steps_handle_gaps_is_non_blocking():
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        has_gaps=True,
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    gap_steps = [s for s in steps if s.action == "handle_gaps"]
    assert len(gap_steps) == 1
    assert gap_steps[0].blocking is False


def test_derive_steps_all_steps_are_preprocessing_step_instances():
    profile = DataProfile(
        series_lengths={"value": 100},
        n_series=3,
        index_type="datetime",
        frequency="D",
        target="value",
        date_column="date",
        series_id_column="series_id",
        data_format="long",
        frequency_is_set=False,
        has_gaps=True,
        index_is_monotonic=False,
    )
    steps = derive_preprocessing_steps(
        profile, "ForecasterRecursiveMultiSeries"
    )
    assert all(isinstance(s, PreprocessingStep) for s in steps)
    assert len(steps) >= 1  # handle_gaps (non-blocking)
