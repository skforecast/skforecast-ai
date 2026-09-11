# Unit test _utils

import re
from pathlib import Path

import pytest
import pandas as pd

from skforecast_ai._utils import (
    _apply_interval_to_plan,
    _strip_code_blocks,
    _resolve_data_and_target,
    _resolve_inputs_with_profile,
    _validate_task_input,
    _validate_window_features,
)
from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import DataProfile

from tests.fixtures_assistant import df_single, series_single


# =============================================================================
# _strip_code_blocks
# =============================================================================
@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Some text\n```python\nprint('hello')\n```\nMore text",
            "Some text\n"
            "(See `result.code` for the validated implementation.)\n"
            "More text",
        ),
        (
            "Intro\n```python\ncode1\n```\nMiddle\n```bash\ncode2\n```\nEnd",
            "Intro\n"
            "(See `result.code` for the validated implementation.)\n"
            "Middle\n"
            "(See `result.code` for the validated implementation.)\n"
            "End",
        ),
        (
            "Before\n```\nsome code\n```\nAfter",
            "Before\n"
            "(See `result.code` for the validated implementation.)\n"
            "After",
        ),
    ],
    ids=["single_block", "multiple_blocks", "no_language_specifier"],
)
def test_strip_code_blocks_output_when_code_blocks_present(text, expected):
    """
    Test that fenced code blocks are replaced with the pointer text.
    """
    result = _strip_code_blocks(text)
    assert result == expected


@pytest.mark.parametrize(
    "text",
    [
        "Just plain text without any code blocks.",
        "",
    ],
    ids=["plain_text", "empty_string"],
)
def test_strip_code_blocks_output_when_no_code_blocks(text):
    """
    Test that text without code blocks is returned unchanged.
    """
    result = _strip_code_blocks(text)
    assert result == text


# =============================================================================
# _resolve_data_and_target
# =============================================================================
def test_resolve_data_and_target_output_when_named_series():
    """
    Test that a named Series is framed and its name is used as the target.
    """
    index = pd.date_range("2020-01-01", periods=5, freq="D")
    series = pd.Series([1, 2, 3, 4, 5], index=index, name="sales")

    data, target = _resolve_data_and_target(series, target=None)

    assert isinstance(data, pd.DataFrame)
    assert target == "sales"
    assert list(data.columns) == ["sales"]
    pd.testing.assert_index_equal(data.index, index)


def test_resolve_data_and_target_output_when_named_series_matching_target():
    """
    Test that providing a target matching the Series name is accepted.
    """
    series = pd.Series([1, 2, 3], name="sales")

    data, target = _resolve_data_and_target(series, target="sales")

    assert target == "sales"
    assert list(data.columns) == ["sales"]


def test_resolve_data_and_target_warns_and_uses_y_when_series_unnamed():
    """
    Test that an unnamed Series triggers a warning and uses 'y' as target.
    """
    series = pd.Series([1, 2, 3])

    with pytest.warns(UserWarning, match="using 'y'"):
        data, target = _resolve_data_and_target(series, target=None)

    assert target == "y"
    assert list(data.columns) == ["y"]


def test_resolve_data_and_target_raises_when_target_mismatch_series_name():
    """
    Test that a target not matching the Series name raises ValueError.
    """
    series = pd.Series([1, 2, 3], name="sales")

    with pytest.raises(ValueError, match="must match the Series name"):
        _resolve_data_and_target(series, target="revenue")


def test_resolve_data_and_target_raises_when_dataframe_and_target_none():
    """
    Test that a DataFrame input with target=None raises ValueError.
    """
    df = pd.DataFrame({"sales": [1, 2, 3]})

    with pytest.raises(ValueError, match="`target` is required"):
        _resolve_data_and_target(df, target=None)


def test_resolve_data_and_target_output_when_dataframe_passthrough():
    """
    Test that a DataFrame input is returned unchanged with the given target.
    """
    df = pd.DataFrame({"sales": [1, 2, 3], "promo": [0, 1, 0]})

    data, target = _resolve_data_and_target(df, target="sales")

    assert target == "sales"
    pd.testing.assert_frame_equal(data, df)


@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_resolve_data_and_target_output_when_csv_path(tmp_path, path_type):
    """
    Test that a CSV file path (str or Path) is loaded into a DataFrame.
    """
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "value": [10, 20, 30],
    })
    df.to_csv(csv_path, index=False)

    data, target = _resolve_data_and_target(path_type(csv_path), target="value")

    assert isinstance(data, pd.DataFrame)
    assert target == "value"
    assert "date" in data.columns
    assert "value" in data.columns
    assert len(data) == 3


@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_resolve_data_and_target_raises_when_csv_path_not_found(tmp_path, path_type):
    """
    Test that a clear FileNotFoundError is raised when the CSV path doesn't exist.
    """
    missing_path = tmp_path / "nonexistent.csv"
    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        _resolve_data_and_target(path_type(missing_path), target="value")


def test_resolve_data_and_target_parses_date_column(tmp_path):
    """
    Test that a date column in a CSV is detected and parsed as datetime.
    """
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "value": [10, 20, 30],
    })
    df.to_csv(csv_path, index=False)

    data, _ = _resolve_data_and_target(csv_path, target="value")

    assert pd.api.types.is_datetime64_any_dtype(data["date"])


# =============================================================================
# _resolve_inputs_with_profile
# =============================================================================
profile_single = ForecastingAssistant().profile(
    data=df_single, target="sales", date_column="date"
)


def test_resolve_inputs_with_profile_delegates_when_no_profile():
    """
    Test that without a profile the inputs are resolved as before, so a
    DataFrame still requires an explicit target.
    """
    data, target, date_column, series_id_column = _resolve_inputs_with_profile(
        df_single, "sales", "date", None, profile=None
    )
    assert target == "sales"
    assert date_column == "date"
    assert series_id_column is None
    assert data is df_single

    with pytest.raises(ValueError, match="`target` is required"):
        _resolve_inputs_with_profile(df_single, None, None, None, profile=None)


def test_resolve_inputs_with_profile_fills_missing_values_from_profile():
    """
    Test that target, date_column and series_id_column default to the
    values recorded in the profile when they are not given.
    """
    _, target, date_column, series_id_column = _resolve_inputs_with_profile(
        df_single, None, None, None, profile=profile_single
    )

    assert target == "sales"
    assert date_column == "date"
    assert series_id_column is None


def test_resolve_inputs_with_profile_accepts_matching_values():
    """
    Test that explicit values equal to the recorded ones are accepted.
    """
    _, target, date_column, _ = _resolve_inputs_with_profile(
        df_single, "sales", "date", None, profile=profile_single
    )

    assert target == "sales"
    assert date_column == "date"


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"target": "other"}, "`target` 'other' does not match the target"),
        ({"date_column": "other"}, "`date_column` 'other' does not match"),
        ({"series_id_column": "id"}, "`series_id_column` 'id' does not match"),
    ],
    ids=["target", "date_column", "series_id_column"],
)
def test_resolve_inputs_with_profile_raises_when_value_conflicts(kwargs, match):
    """
    Test that a value different from the one recorded in the profile
    raises ValueError instead of being silently ignored.
    """
    args = {"target": None, "date_column": None, "series_id_column": None}
    args.update(kwargs)

    with pytest.raises(ValueError, match=match):
        _resolve_inputs_with_profile(
            df_single,
            args["target"],
            args["date_column"],
            args["series_id_column"],
            profile=profile_single,
        )


def test_resolve_inputs_with_profile_raises_when_columns_missing_in_data():
    """
    Test that data lacking a column the profile was built from fails
    early with a readable message, rather than inside the executed script.
    """
    with pytest.raises(ValueError, match=re.escape("column(s) ['sales']")):
        _resolve_inputs_with_profile(
            df_single.drop(columns=["sales"]), None, None, None,
            profile=profile_single,
        )


def test_resolve_inputs_with_profile_output_when_series_input():
    """
    Test that a pandas Series takes its target from its name and that a
    name different from the profile's target is rejected.
    """
    profile = ForecastingAssistant().profile(data=series_single)

    _, target, _, _ = _resolve_inputs_with_profile(
        series_single, None, None, None, profile=profile
    )
    assert target == "sales"

    with pytest.raises(ValueError, match="does not match the target"):
        _resolve_inputs_with_profile(
            series_single.rename("other"), None, None, None, profile=profile
        )


# =============================================================================
# Task-aware observation-count helpers
# =============================================================================
def _make_profile(series_lengths, frequency="D", n_series=None):
    """Build a minimal DataProfile for task input validation tests."""
    return DataProfile(
        n_series=n_series if n_series is not None else len(series_lengths),
        series_lengths=series_lengths,
        target="value",
        index_type="datetime",
        frequency=frequency,
    )


@pytest.mark.parametrize(
    "task_type",
    ["single_series", "statistical", "foundation"],
)
def test_validate_task_input_raises_when_single_task_with_multiple_series(
    task_type,
):
    """
    Test _validate_task_input raises ValueError when a single-series task
    receives more than one series.
    """
    profile = _make_profile({"A": {"length": 100}, "B": {"length": 100}})
    with pytest.raises(ValueError, match="supports a single series only"):
        _validate_task_input(profile, task_type)


def test_validate_task_input_raises_when_multivariate_unequal_lengths():
    """
    Test _validate_task_input raises ValueError when a multivariate task
    receives series of different lengths.
    """
    profile = _make_profile({"A": {"length": 100}, "B": {"length": 80}})
    with pytest.raises(ValueError, match="same length"):
        _validate_task_input(profile, "multivariate")


def test_validate_task_input_passes_when_valid():
    """
    Test _validate_task_input accepts compatible inputs (single-series
    task with one series; multivariate with equal lengths).
    """
    single = _make_profile({"value": {"length": 100}}, n_series=1)
    multivariate = _make_profile({"A": {"length": 100}, "B": {"length": 100}})

    assert _validate_task_input(single, "single_series") is None
    assert _validate_task_input(multivariate, "multivariate") is None



# =============================================================================
# _validate_window_features
# =============================================================================
@pytest.mark.parametrize(
    "window_features",
    [
        None,
        [{"stats": ["mean"], "window_size": 7}],
        [{"stats": ["mean", "std"], "window_size": 3}],
        [
            {"stats": ["mean", "std"], "window_size": 3},
            {"stats": ["mean"], "window_size": 24},
            {"stats": ["ratio_min_max", "coef_variation", "ewm"], "window_size": 168},
        ],
    ],
    ids=lambda wf: f"window_features: {wf}",
)
def test_validate_window_features_passes_when_valid(window_features):
    """
    Test that valid window_features configurations (including None and
    multi-stat scalar-window entries) pass validation without raising.
    """
    assert _validate_window_features(window_features) is None


@pytest.mark.parametrize(
    "window_features, match",
    [
        ({"stats": ["mean"], "window_size": 7}, "must be a list of dicts"),
        ([["mean", 7]], "must be a dict"),
        ([{"stats": ["mean"]}], "missing required key"),
        ([{"window_size": 7}], "missing required key"),
        ([{"stats": "mean", "window_size": 7}], "non-empty list"),
        ([{"stats": [], "window_size": 7}], "non-empty list"),
        ([{"stats": ["mean", "variance"], "window_size": 7}], "unsupported"),
        ([{"stats": ["mean"], "window_size": [3, 7]}], "must be a scalar int"),
        ([{"stats": ["mean"], "window_size": 7.0}], "must be a scalar int"),
        ([{"stats": ["mean"], "window_size": True}], "must be a scalar int"),
        ([{"stats": ["mean"], "window_size": 0}], "must be a positive int"),
    ],
)
def test_validate_window_features_raises_when_invalid(window_features, match):
    """
    Test that malformed window_features (wrong container, missing keys,
    unsupported stats, or non-scalar/invalid window_size) raise ValueError.
    """
    with pytest.raises(ValueError, match=match):
        _validate_window_features(window_features)


def test_apply_interval_to_plan_uses_native_method_for_foundation_plan():
    """
    Test that applying an interval to a foundation plan without intervals
    selects the native interval method, extends the explanation, and leaves
    the original plan untouched, while a plan that already predicts the
    same interval is returned as is.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    assert plan.interval is None

    updated = _apply_interval_to_plan(plan, [0.1, 0.9])

    assert updated.interval == [0.1, 0.9]
    assert updated.interval_method == "native"
    assert updated.explanation == f"{plan.explanation} Prediction intervals via native."
    assert plan.interval is None
    assert _apply_interval_to_plan(updated, [0.1, 0.9]) is updated
