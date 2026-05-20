"""Shared internal utilities for skforecast_ai."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pandas as pd

from .profiling.data_profile import _try_parse_first_date_column

_CODE_BLOCK_RE = re.compile(r"^```[^\n]*\n[\s\S]*?^```", re.MULTILINE)
_CODE_BLOCK_REPLACEMENT = "(See `result.code` for the validated implementation.)"


def _strip_code_blocks(text: str) -> str:
    """Replace fenced code blocks with a pointer to result.code."""
    return _CODE_BLOCK_RE.sub(_CODE_BLOCK_REPLACEMENT, text)


def _coerce_to_dataframe(
    data: pd.DataFrame | str | Path,
) -> pd.DataFrame:
    """
    Load a CSV path into a DataFrame, or return the DataFrame unchanged.

    The CSV is loaded without `parse_dates` (deprecated in pandas
    2.2+). Date columns are detected and parsed by
    `_try_parse_first_date_column` instead, leaving every column
    intact so callers can reference a `date_column` by name.

    Parameters
    ----------
    data : pandas DataFrame, str, Path
        Input dataset or path to a CSV file.

    Returns
    -------
    df : pandas DataFrame
        Loaded DataFrame.
    """

    if isinstance(data, (str, Path)):
        df = pd.read_csv(data)
        return _try_parse_first_date_column(df)

    return data


def _patch_event_loop() -> None:
    """
    Apply `nest_asyncio` when an event loop is already running.

    Enables `run_sync()` to work inside Jupyter notebooks and other
    environments that already have an active asyncio event loop. The
    patch is applied at most once per process.

    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # No running loop — nothing to patch

    if not getattr(loop, "_nest_patched", False):
        try:
            import nest_asyncio
        except ImportError:
            raise ImportError(
                "nest_asyncio is required to use `ask()` inside Jupyter "
                "notebooks or other environments with a running event loop. "
                "Install it with: pip install nest_asyncio"
            ) from None

        nest_asyncio.apply()
