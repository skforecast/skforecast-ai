# Unit test _utils

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import numpy as np
import pandas as pd

from skforecast_ai._utils import (
    _strip_code_blocks,
    _coerce_to_dataframe,
    _run_agent_sync,
)


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
# _coerce_to_dataframe
# =============================================================================
def test_coerce_to_dataframe_output_when_dataframe_input():
    """
    Test that passing a DataFrame returns it unchanged.
    """
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    result = _coerce_to_dataframe(df)
    pd.testing.assert_frame_equal(result, df)


@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_coerce_to_dataframe_output_when_csv_path(tmp_path, path_type):
    """
    Test that a CSV file path (str or Path) is loaded into a DataFrame.
    """
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "value": [10, 20, 30],
    })
    df.to_csv(csv_path, index=False)

    result = _coerce_to_dataframe(path_type(csv_path))
    assert isinstance(result, pd.DataFrame)
    assert "date" in result.columns
    assert "value" in result.columns
    assert len(result) == 3


@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_coerce_to_dataframe_raises_when_csv_path_not_found(tmp_path, path_type):
    """
    Test that a clear FileNotFoundError is raised when the CSV path doesn't exist.
    """
    missing_path = tmp_path / "nonexistent.csv"
    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        _coerce_to_dataframe(path_type(missing_path))


def test_coerce_to_dataframe_parses_date_column(tmp_path):
    """
    Test that a date column in a CSV is detected and parsed as datetime.
    """
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "value": [10, 20, 30],
    })
    df.to_csv(csv_path, index=False)

    result = _coerce_to_dataframe(csv_path)
    assert pd.api.types.is_datetime64_any_dtype(result["date"])


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
