"""Shared internal utilities for skforecast_ai."""

from __future__ import annotations

import asyncio
import re
import threading
import warnings
from pathlib import Path

import pandas as pd

from skforecast.exceptions import IgnoredArgumentWarning

from .profiling.data_profile import _try_parse_first_date_column
from .schemas import DataProfile, ForecastPlan

_CODE_BLOCK_RE = re.compile(r"^```[^\n]*\n[\s\S]*?^```", re.MULTILINE)
_CODE_BLOCK_REPLACEMENT = "(See `result.code` for the validated implementation.)"


def _series_span_length(data_profile: DataProfile) -> int:
    """
    Length of the union datetime index spanning all series.

    Computes the number of periods between the earliest start and the
    latest end across every series at the profiled frequency. Falls back
    to the longest individual series when datetime bounds or frequency
    are unavailable.

    Parameters
    ----------
    data_profile : DataProfile
        Universal data profile from Stage 1.

    Returns
    -------
    span : int
        Number of observations in the union index.
    """
    infos = list(data_profile.series_lengths.values())
    starts = [info.start for info in infos if info.start is not None]
    ends = [info.end for info in infos if info.end is not None]
    if not starts or not ends or data_profile.frequency is None:
        return max(info.length for info in infos)

    start = min(pd.Timestamp(s) for s in starts)
    end = max(pd.Timestamp(e) for e in ends)
    try:
        return len(pd.date_range(start=start, end=end, freq=data_profile.frequency))
    except (ValueError, TypeError):
        return max(info.length for info in infos)


def _display_n_observations(data_profile: DataProfile) -> int:
    """
    Task-agnostic observation count for display and summaries.

    Returns the single series length for single-series data and the
    union span for multi-series data.

    Parameters
    ----------
    data_profile : DataProfile
        Universal data profile from Stage 1.

    Returns
    -------
    n_observations : int
        Representative observation count for display.
    """
    infos = list(data_profile.series_lengths.values())
    if len(infos) == 1:
        return infos[0].length
    return _series_span_length(data_profile)


def _validate_task_input(data_profile: DataProfile, task_type: str) -> None:
    """
    Validate that the input shape is compatible with the task type.

    Single-series tasks (`single_series`, `statistical`, `foundation`)
    accept exactly one series. The `multivariate` task requires all
    series to share the same length.

    Parameters
    ----------
    data_profile : DataProfile
        Universal data profile from Stage 1.
    task_type : str
        Forecasting task type implied by the selected forecaster.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        When the input shape is incompatible with the task type.
    """
    series_lengths = data_profile.series_lengths
    n_series = len(series_lengths)

    if task_type in ("single_series", "statistical", "foundation") and n_series > 1:
        raise ValueError(
            f"Task type '{task_type}' supports a single series only, but the "
            f"input contains {n_series} series ({list(series_lengths)}). "
            f"Use a multi-series forecaster (e.g. "
            f"'ForecasterRecursiveMultiSeries') or provide a single series."
        )

    if task_type == "multivariate":
        lengths = {info.length for info in series_lengths.values()}
        if len(lengths) > 1:
            detail = {
                name: info.length for name, info in series_lengths.items()
            }
            raise ValueError(
                f"Task type 'multivariate' (ForecasterDirectMultiVariate) "
                f"requires all series to have the same length, but got "
                f"{detail}. Align the series to a common index or use "
                f"'ForecasterRecursiveMultiSeries'."
            )


def _strip_code_blocks(text: str) -> str:
    """Replace fenced code blocks with a pointer to result.code."""
    return _CODE_BLOCK_RE.sub(_CODE_BLOCK_REPLACEMENT, text)


def _warn_if_plan_overrides_ignored(
    plan: ForecastPlan | None,
    forecaster: str | None,
    estimator: str | None,
    estimator_kwargs: dict | None,
    interval: list[float] | None,
) -> None:
    """
    Warn when plan-shaping arguments are ignored due to a supplied plan.

    When a pre-built `plan` is passed to `forecast()` or `forecast_code()`,
    the planning stage is skipped, so any argument that only feeds that
    stage is silently dropped. This emits an `IgnoredArgumentWarning`
    instead, pointing the caller to `refine_plan()`.

    Parameters
    ----------
    plan : ForecastPlan, None
        Pre-built plan supplied by the caller. When None, nothing is
        warned because the planning stage runs normally.
    forecaster : str, None
        Forecaster override that would be ignored.
    estimator : str, None
        Estimator override that would be ignored.
    estimator_kwargs : dict, None
        Estimator keyword arguments that would be ignored.
    interval : list of float, None
        Prediction interval override that would be ignored.

    Returns
    -------
    None
    """
    if plan is None:
        return
    ignored = [
        name
        for name, value in (
            ("forecaster", forecaster),
            ("estimator", estimator),
            ("estimator_kwargs", estimator_kwargs),
            ("interval", interval),
        )
        if value is not None
    ]
    if ignored:
        warnings.warn(
            f"A pre-built `plan` was provided, so the following argument(s) "
            f"are ignored: {ignored}. To change these, refine the plan with "
            f"`refine_plan()` before calling.",
            IgnoredArgumentWarning,
        )


def _resolve_data_and_target(
    data: pd.Series | pd.DataFrame | str | Path,
    target: str | list[str] | None,
) -> tuple[pd.DataFrame, str | list[str]]:
    """
    Coerce the input to a DataFrame and resolve the target column name.

    Centralizes the rules for accepting a `pandas Series` as input. When
    `data` is a Series, the target is derived from the Series name; for
    every other input type a `target` must be provided explicitly. CSV
    paths and URLs are loaded with `pandas.read_csv` (without `parse_dates`,
    deprecated in pandas 2.2+); date columns are detected and parsed by
    `_try_parse_first_date_column` instead, leaving every column intact so
    callers can reference a `date_column` by name.

    Parameters
    ----------
    data : pandas Series, pandas DataFrame, str, Path
        Input dataset, a single series, or a path/URL to a CSV file.
    target : str, list, None
        Name of the column(s) to forecast. Optional only when `data` is a
        Series (the name is used instead).

    Returns
    -------
    data : pandas DataFrame
        Coerced DataFrame.
    target : str, list
        Resolved target column name(s).

    Raises
    ------
    ValueError
        When `data` is a Series and `target` is provided but does not
        match the Series name, or when `data` is not a Series and
        `target` is None.
    FileNotFoundError
        When `data` is a path or URL that cannot be read.
    """
    if isinstance(data, pd.Series):
        name = data.name
        if target is not None and target != name:
            raise ValueError(
                f"When `data` is a pandas Series and `target` is provided, "
                f"`target` must match the Series name. Got target={target!r} "
                f"and series.name={name!r}. Omit `target` to use the Series "
                f"name, or rename the Series."
            )
        if name is None:
            warnings.warn(
                "The input Series has no name; using 'y' as the target name.",
                UserWarning,
                stacklevel=2,
            )
            resolved_target = "y"
        else:
            resolved_target = name
        return data.to_frame(name=resolved_target), resolved_target

    if target is None:
        raise ValueError(
            "`target` is required when `data` is not a pandas Series."
        )

    if isinstance(data, (str, Path)):
        data_str = str(data)
        if data_str.startswith(("http://", "https://")):
            try:
                df = pd.read_csv(data_str)
            except Exception as e:
                raise FileNotFoundError(
                    f"Could not read CSV from URL: '{data_str}'. {e}"
                ) from e
            return _try_parse_first_date_column(df), target
        path = Path(data_str)
        if not path.is_file():
            raise FileNotFoundError(
                f"CSV file not found: '{path}'. Please provide a valid file path."
            )
        df = pd.read_csv(path)
        return _try_parse_first_date_column(df), target

    return data, target


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
