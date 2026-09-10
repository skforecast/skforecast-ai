################################################################################
#                                 llm: runtime                                 #
#                                                                              #
# Shared background event loop for running pydantic-ai agents from sync code   #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import asyncio
import threading

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


def run_agent_sync(agent, *args, **kwargs):
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
