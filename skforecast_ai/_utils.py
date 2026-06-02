"""Shared internal utilities for skforecast_ai."""

from __future__ import annotations

import asyncio
import re
import threading
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
    Load a CSV path or URL into a DataFrame, or return the DataFrame unchanged.

    The CSV is loaded without `parse_dates` (deprecated in pandas
    2.2+). Date columns are detected and parsed by
    `_try_parse_first_date_column` instead, leaving every column
    intact so callers can reference a `date_column` by name.

    Parameters
    ----------
    data : pandas DataFrame, str, Path
        Input dataset, path to a CSV file, or URL to a remote CSV.

    Returns
    -------
    df : pandas DataFrame
        Loaded DataFrame.
    """

    if isinstance(data, (str, Path)):
        data_str = str(data)
        if data_str.startswith(("http://", "https://")):
            try:
                df = pd.read_csv(data_str)
            except Exception as e:
                raise FileNotFoundError(
                    f"Could not read CSV from URL: '{data_str}'. {e}"
                ) from e
            return _try_parse_first_date_column(df)
        path = Path(data_str)
        if not path.is_file():
            raise FileNotFoundError(
                f"CSV file not found: '{path}'. Please provide a valid file path."
            )
        df = pd.read_csv(path)
        return _try_parse_first_date_column(df)

    return data


_agent_loop: asyncio.AbstractEventLoop | None = None
_agent_loop_lock = threading.Lock()


def _get_agent_loop() -> asyncio.AbstractEventLoop:
    """
    Return a shared background event loop, starting it on first use.

    The loop runs forever in a daemon thread so it persists across calls.
    A single shared loop keeps asyncio objects cached by the agent valid
    between invocations.

    Returns
    -------
    loop : asyncio.AbstractEventLoop
        The running background event loop.

    """

    global _agent_loop

    if _agent_loop is not None and not _agent_loop.is_closed():
        return _agent_loop

    with _agent_loop_lock:
        if _agent_loop is not None and not _agent_loop.is_closed():
            return _agent_loop

        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=loop.run_forever,
            name="skforecast-ai-agent-loop",
            daemon=True,
        )
        thread.start()
        _agent_loop = loop

    return _agent_loop


def _run_agent_sync(agent, *args, **kwargs):
    """
    Run `agent.run()` from synchronous code, safe inside running loops.

    All agent calls are scheduled on a single, long-lived background
    event loop running in a daemon thread. Sharing one loop across calls
    keeps asyncio primitives cached by the agent (locks, events, HTTP
    client connections) valid between invocations.

    This avoids two problems with a sync entry point:

    - Calling `asyncio.run()` (or `agent.run_sync()`) inside an
    environment that already has a running loop (e.g. Jupyter) raises a
    `RuntimeError`.
    - Creating a fresh loop per call binds cached asyncio objects to a
    loop that no longer exists on the next call, raising
    "bound to a different event loop".

    Parameters
    ----------
    agent : object
        Object exposing an awaitable `run(*args, **kwargs)` method
        (typically a pydantic-ai `Agent`).
    *args
        Positional arguments forwarded to `agent.run()`.
    **kwargs
        Keyword arguments forwarded to `agent.run()`.

    Returns
    -------
    result : object
        The value returned by awaiting `agent.run()`.

    """

    loop = _get_agent_loop()
    future = asyncio.run_coroutine_threadsafe(
        agent.run(*args, **kwargs), loop
    )
    return future.result()
