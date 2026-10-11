################################################################################
#                              MCP server preload                              #
#                                                                              #
# Imports the core in a background thread once the client is connected        #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import importlib
import logging
import threading
from collections.abc import Iterable
from typing import Any
from ._errors import ServerError

logger = logging.getLogger("skforecast_ai.mcp")

# What the tools import: the core loads pandas, scikit-learn, scipy and
# skforecast, most of the start of the server (more than 5 seconds with the
# bytecode not compiled yet, as in the first start after an installation).
# The server answers `initialize` and `tools/list` without them.
PRELOADED_MODULES = (
    "skforecast_ai.assistant",
    "skforecast_ai.execution.comparison",
    "skforecast_ai.recommendation",
    "skforecast_ai.schemas",
    "skforecast_ai._last_window",
    "skforecast_ai._utils",
    "skforecast.foundation",
)


class Preload:
    """
    Import of a list of modules in a background thread, started once, that
    the tools wait for.

    The modules are imported once per process, so one instance serves every
    server of the process (`PRELOAD`), started by
    `start_preload_after_answer`. `start` runs the import in a daemon
    thread, so a client that closes the server during the import does not
    keep the process alive; `wait` starts it if nothing did and blocks until
    it ends. An import that fails is kept, logged once and raised by every
    `wait`, so the first tool reports it and the next ones do not import
    again.

    Parameters
    ----------
    modules : iterable of str
        Absolute names of the modules, imported in this order.

    Attributes
    ----------
    modules : tuple of str
        Names of the modules.
    """

    def __init__(self, modules: Iterable[str]) -> None:
        self.modules = tuple(modules)
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def start(self) -> None:
        """
        Start the import in a background thread, unless it was started.

        Returns
        -------
        None
        """

        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target = self._run,
                name   = "skforecast-ai-preload",
                daemon = True,
            )
            self._thread.start()

    def _run(self) -> None:
        """
        Import the modules and record the first error.
        """

        try:
            for module in self.modules:
                importlib.import_module(module)
        except BaseException as exc:  # noqa: BLE001 - reported by `wait`
            self._error = exc
            logger.error(
                "The server could not import its dependencies: %s: %s",
                type(exc).__name__,
                exc,
                exc_info = exc,
            )
        finally:
            self._done.set()

    @property
    def done(self) -> bool:
        """
        Whether the import ended, with or without an error.
        """

        return self._done.is_set()

    def wait(self) -> None:
        """
        Start the import if needed and block until it ends.

        Returns
        -------
        None

        Raises
        ------
        ServerError
            With the code `'internal_error'`, when an import failed. The
            original exception is its cause.
        """

        self.start()
        self._done.wait()
        if self._error is not None:
            exc = self._error
            raise ServerError(
                f"The server could not import skforecast-ai and its "
                f"dependencies: {type(exc).__name__}: {exc}",
                code = "internal_error",
                hint = (
                    "Report it to the user: the installation of skforecast-ai "
                    "is broken and every tool fails the same way until it is "
                    "repaired. The traceback is in the log of the server "
                    "(stderr)."
                ),
            ) from exc


PRELOAD = Preload(PRELOADED_MODULES)


async def start_preload_after_answer(ctx: Any, call_next: Any) -> Any:
    """
    Middleware of the server that starts `PRELOAD` once the server has
    handled the first message of its client, so the answer to the handshake
    is ready before the import starts competing with it.

    The first message is `initialize` with the protocol of 2025 and
    `server/discover` with the one of 2026-07-28, which sends no
    `notifications/initialized` (Claude Code 2.1.296 does so). A client that
    sends neither starts it with its first request; `PRELOAD.start` does
    nothing after the first time.

    Parameters
    ----------
    ctx : ServerRequestContext
        Context of the incoming message.
    call_next : Callable
        Rest of the chain of the SDK.

    Returns
    -------
    result : object
        What the chain returns.
    """

    result = await call_next(ctx)
    # Read here, not bound at import, so a test can replace it.
    PRELOAD.start()

    return result
