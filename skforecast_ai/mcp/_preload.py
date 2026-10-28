################################################################################
#                              MCP server preload                              #
#                                                                              #
# Imports the core in a background thread while the server answers its client #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import importlib
import logging
import threading
from collections.abc import Iterable

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

# What the tools compute once per process, warmed after the imports so that
# the first call does not pay for it: the installed distributions that the
# `requirements` of `get_code` read (`packages_distributions` scans every
# installed package, seconds when cold and tens of them while a run holds
# the GIL). Each is `module:function`, called without arguments.
WARMED_CALLS = (
    "skforecast_ai.mcp.server:_distributions",
)


class PreloadError(Exception):
    """
    Raised by `Preload.wait` when the import failed; its cause is the error
    of the import, which the tools report as an unexpected error (its type
    and an id, with the message and the traceback in the log).
    """


class Preload:
    """
    Import of a list of modules in a background thread, started once, that
    the tools wait for.

    The modules are imported once per process, so one instance serves every
    server of the process (`PRELOAD`), which `run_server` starts as it
    starts serving. `start` runs the import in a daemon
    thread, so a client that closes the server during the import does not
    keep the process alive; `wait` starts it if nothing did and blocks until
    it ends. An import that fails is kept, logged once and raised by every
    `wait`, so the first tool reports it and the next ones do not import
    again.

    Once the import ended, and after `wait` returns, the same thread calls
    the functions of `warm`, so the tools never wait for them: a call that
    needs one before it ran computes it itself. A failure there is only
    logged.

    Parameters
    ----------
    modules : iterable of str
        Absolute names of the modules, imported in this order.
    warm : iterable of str, default ()
        Functions to call once the import ended, as `module:function`.

    Attributes
    ----------
    modules : tuple of str
        Names of the modules.
    warm : tuple of str
        Functions called after the import.
    """

    def __init__(self, modules: Iterable[str], warm: Iterable[str] = ()) -> None:
        self.modules = tuple(modules)
        self.warm = tuple(warm)
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
        if self._error is None:
            self._warm()

    def _warm(self) -> None:
        """
        Call the functions of `warm`, logging a failure: the tool that needs
        one calls it again and reports its own error.
        """

        for target in self.warm:
            module, _, name = target.partition(":")
            try:
                getattr(importlib.import_module(module), name)()
            except Exception as exc:  # noqa: BLE001 - only logged
                logger.warning("The server could not warm %s: %s", target, exc)

    @property
    def started(self) -> bool:
        """
        Whether the import was started, by `start` or by `wait`.
        """

        return self._thread is not None

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
        PreloadError
            When an import failed. The original exception is its cause.
        """

        self.start()
        self._done.wait()
        if self._error is not None:
            raise PreloadError(
                "The server could not import skforecast-ai and its dependencies."
            ) from self._error


PRELOAD = Preload(PRELOADED_MODULES, warm=WARMED_CALLS)
