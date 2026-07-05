# Unit test _utils

from pathlib import Path

import pytest
import pandas as pd

from skforecast_ai._utils import (
    _strip_code_blocks,
    _resolve_data_and_target,
    _run_agent_sync,
    _series_span_length,
    _display_n_observations,
    _validate_task_input,
    _validate_window_features,
)
from skforecast_ai.schemas import DataProfile


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
# _run_agent_sync
# =============================================================================
def test_run_agent_sync_output_and_forwards_args():
    """
    Test that _run_agent_sync awaits agent.run, forwards args/kwargs, and
    returns the awaited value.
    """
    received = {}

    class _FakeAgent:
        async def run(self, *args, **kwargs):
            received["args"] = args
            received["kwargs"] = kwargs
            return "result"

    result = _run_agent_sync(_FakeAgent(), "a", "b", deps="d", model_settings="s")

    assert result == "result"
    assert received["args"] == ("a", "b")
    assert received["kwargs"] == {"deps": "d", "model_settings": "s"}


def test_run_agent_sync_runs_on_shared_background_loop():
    """
    Test that agent.run executes on the shared background loop (a daemon
    thread), not the caller's thread, and that the same loop is reused
    across calls.
    """
    import threading

    seen = {}

    class _FakeAgent:
        async def run(self, *args, **kwargs):
            loop = __import__("asyncio").get_running_loop()
            seen.setdefault("loops", []).append(id(loop))
            seen.setdefault("threads", []).append(
                threading.current_thread().ident
            )
            return "ok"

    agent = _FakeAgent()
    _run_agent_sync(agent, "first")
    _run_agent_sync(agent, "second")

    # Executed off the caller (main) thread
    assert seen["threads"][0] != threading.current_thread().ident
    # Same background loop reused across calls
    assert seen["loops"][0] == seen["loops"][1]


def test_run_agent_sync_propagates_exceptions():
    """
    Test that an exception raised inside agent.run propagates to the
    synchronous caller.
    """

    class _FakeAgent:
        async def run(self, *args, **kwargs):
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        _run_agent_sync(_FakeAgent(), "msg")


# =============================================================================
# Task-aware observation-count helpers
# =============================================================================
def _make_profile(series_lengths, frequency="D", n_series=None):
    """Build a minimal DataProfile for observation-count helper tests."""
    return DataProfile(
        n_series=n_series if n_series is not None else len(series_lengths),
        series_lengths=series_lengths,
        target="value",
        index_type="datetime",
        frequency=frequency,
    )


def test_series_span_length_output_when_dates_available():
    """
    Test _series_span_length spans from the earliest start to the latest
    end across all series at the profiled frequency.
    """
    profile = _make_profile({
        "A": {"start": "2023-01-01", "end": "2023-04-10", "length": 100},
        "B": {"start": "2023-02-01", "end": "2023-03-01", "length": 29},
    })
    # 2023-01-01 .. 2023-04-10 inclusive at daily frequency
    assert _series_span_length(profile) == 100


def test_series_span_length_output_when_no_frequency_falls_back_to_max():
    """
    Test _series_span_length falls back to the longest series length when
    no frequency is available.
    """
    profile = _make_profile(
        {"A": {"length": 100}, "B": {"length": 60}}, frequency=None
    )
    assert _series_span_length(profile) == 100


def test_display_n_observations_output_when_single_series_uses_length():
    """
    Test _display_n_observations returns the single series length.
    """
    profile = _make_profile(
        {"value": {"start": "2023-01-01", "end": "2023-04-10", "length": 100}}
    )
    assert _display_n_observations(profile) == 100


def test_display_n_observations_output_when_multi_series_uses_span():
    """
    Test _display_n_observations returns the union span for multi-series.
    """
    profile = _make_profile({
        "A": {"start": "2023-01-01", "end": "2023-04-10", "length": 100},
        "B": {"start": "2023-02-01", "end": "2023-03-01", "length": 29},
    })
    assert _display_n_observations(profile) == 100


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
