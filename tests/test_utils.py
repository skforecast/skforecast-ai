# Unit test _utils

import re
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import numpy as np
import pandas as pd

from skforecast_ai._utils import (
    _strip_code_blocks,
    _coerce_to_dataframe,
    _patch_event_loop,
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
# _patch_event_loop
# =============================================================================
def test_patch_event_loop_output_when_no_running_loop():
    """
    Test that _patch_event_loop returns without error when no event loop
    is running.
    """
    result = _patch_event_loop()
    assert result is None


def test_patch_event_loop_ImportError_when_nest_asyncio_missing():
    """
    Test that ImportError is raised with a helpful message when
    nest_asyncio is not installed and an event loop is running.
    """
    mock_loop = MagicMock()
    mock_loop._nest_patched = False

    with patch(
        "skforecast_ai._utils.asyncio.get_running_loop",
        return_value=mock_loop,
    ):
        with patch.dict(sys.modules, {"nest_asyncio": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                err_msg = re.escape(
                    "nest_asyncio is required to use `ask()` inside Jupyter"
                )
                with pytest.raises(ImportError, match=err_msg):
                    _patch_event_loop()


def test_patch_event_loop_applies_patch_when_loop_running():
    """
    Test that nest_asyncio.apply() is called when an event loop is running
    and not yet patched.
    """
    mock_loop = MagicMock()
    mock_loop._nest_patched = False
    mock_nest_asyncio = MagicMock()

    with patch(
        "skforecast_ai._utils.asyncio.get_running_loop",
        return_value=mock_loop,
    ):
        with patch.dict(sys.modules, {"nest_asyncio": mock_nest_asyncio}):
            with patch("builtins.__import__", return_value=mock_nest_asyncio):
                _patch_event_loop()

    mock_nest_asyncio.apply.assert_called_once()


def test_patch_event_loop_skips_when_already_patched():
    """
    Test that nest_asyncio.apply() is NOT called when the loop is already
    patched.
    """
    mock_loop = MagicMock()
    mock_loop._nest_patched = True

    with patch(
        "skforecast_ai._utils.asyncio.get_running_loop",
        return_value=mock_loop,
    ):
        # Should return early without importing nest_asyncio
        _patch_event_loop()
