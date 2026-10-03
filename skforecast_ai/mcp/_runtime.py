################################################################################
#                              MCP server runtime                              #
#                                                                              #
# Runs the core in a worker thread, one call at a time, capturing warnings     #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import logging
import math
import os
import threading
import time
import warnings
from collections.abc import Awaitable, Callable, Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar
import anyio
import anyio.lowlevel
from anyio.lowlevel import RunVar
from ..exceptions import CandidateFailedWarning
from ._errors import ServerError
from .models import ToolNotice

logger = logging.getLogger("skforecast_ai.mcp")

T = TypeVar("T")

# One call of the core at a time in the whole process: the scripts redirect
# `sys.stdout` while they run and `warnings.catch_warnings` replaces global
# state, so two calls at once would leave `sys.stdout` redirected or mix
# their warnings. A threading lock (not an anyio one) is held by the worker
# thread itself, so it is shared by every server and event loop of the
# process and a cancelled call keeps it until its thread really stops.
PROCESS_LOCK = threading.Lock()

_CALL_GATE: RunVar[anyio.Lock] = RunVar("skforecast_ai_mcp_call_gate")

MAX_NOTICES = 20
MAX_NOTICE_CHARS = 1_000

# Seconds between two progress notifications while the worker thread is
# busy with no event of its own: some clients end a request after 60 s
# without one, and an Auto-ARIMA candidate or a backtest of many fits can
# run for longer.
HEARTBEAT_SECONDS = 5.0

# skforecast appends how to silence its warnings, which does not apply to an
# agent.
_SUPPRESS_HINT = "\nYou can suppress this warning"


class CallCancelled(Exception):
    """
    Raised in the worker thread to stop a call whose request was cancelled.

    It is not a `SkforecastAIError`, so the core never records it as the
    failure of a candidate: raised from the `progress_callback` of
    `compare()`, it leaves the comparison before the next candidate.
    """


@dataclass
class CallControl:
    """
    What the work of a call can use from its worker thread.

    Attributes
    ----------
    cancelled : threading.Event
        Set when the request of the call is cancelled.
    report : Callable, None
        Sends a progress notification to the client, `report(progress, total,
        message, running)`. None when the call reports no progress.
    written : list of str
        Files the work wrote, removed when the call is cancelled before it
        returns, since nothing is then registered that names them.
    label : str
        What the call runs, named by the heartbeat notifications.
    activity : tuple, None
        Progress and total of the last notification of the work that was
        sent, what runs since then and when it started
        (`time.monotonic()`), read by the heartbeat notifications. None
        until the worker thread starts.
    """

    cancelled: threading.Event
    report: Callable[[float, float, str, str | None], None] | None = None
    written: list[str] = field(default_factory=list)
    label: str = "call"
    activity: tuple[float, float | None, str, float] | None = None

    def begin(self) -> None:
        """
        Record that the worker thread started the work.

        Returns
        -------
        None
        """

        self.activity = (0.0, None, self.label, time.monotonic())

    def wrote(self, *files: dict[str, str] | str | None) -> None:
        """
        Record files written by the work.

        Parameters
        ----------
        *files : dict, str, None
            Paths, or dicts of paths by role; None is skipped.

        Returns
        -------
        None
        """

        for item in files:
            if isinstance(item, dict):
                self.written.extend(item.values())
            elif item is not None:
                self.written.append(item)

    def check(self) -> None:
        """
        Raise `CallCancelled` when the request was cancelled.

        Returns
        -------
        None
        """

        if self.cancelled.is_set():
            raise CallCancelled()

    def progress(
        self,
        progress: float,
        total: float,
        message: str,
        running: str | None = None,
    ) -> None:
        """
        Report progress to the client, or stop the call when its request was
        cancelled or the client can no longer be reached.

        Called from the worker thread. The notification is sent in the event
        loop with `anyio.from_thread.run`, without taking any lock, so it
        never waits for another call.

        Parameters
        ----------
        progress : float
            Progress so far, an integer step; it grows with every
            notification.
        total : float
            Progress at the end.
        message : str
            What is running.
        running : str, default None
            What runs from now on (a candidate that starts), named by the
            heartbeat notifications until the next event; None for the
            label of the call.

        Returns
        -------
        None
        """

        self.check()
        if self.report is None:
            return
        try:
            self.report(progress, total, message, running)
        except Exception as exc:
            # A notification that cannot be sent because the request was
            # cancelled stops the call; any other failure is an error of its
            # own, reported as such.
            if self.cancelled.is_set():
                raise CallCancelled() from exc
            raise


@dataclass
class CallOutcome(Generic[T]):
    """
    Value returned by the work of a call and the warnings it emitted.

    Attributes
    ----------
    value : object
        Value returned by the work.
    warnings : list
        `warnings.WarningMessage` records, in the order they were emitted.
    """

    value: T
    warnings: list[warnings.WarningMessage] = field(default_factory=list)


def _call_gate() -> anyio.Lock:
    """
    Lock of the current event loop that admits one call at a time to a
    worker thread.

    Calls wait for it without holding a thread, so the threads of anyio stay
    free for the transport (reading stdin, which also brings cancellations).
    It lives in a `RunVar`, so each event loop has its own: a lock created in
    one loop cannot be used in another. `PROCESS_LOCK` still guards the
    process.
    """

    try:
        return _CALL_GATE.get()
    except LookupError:
        gate = anyio.Lock()
        _CALL_GATE.set(gate)
        return gate


@contextmanager
def _record_warnings() -> Iterator[list[warnings.WarningMessage]]:
    """
    Record the warnings emitted by the current thread, every time.

    The filters and the display of warnings are global: a warning of another
    thread (the event loop) while the call runs is shown as it would be
    otherwise, not recorded as a warning of the call.
    """

    records: list[warnings.WarningMessage] = []
    thread = threading.get_ident()
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        show = warnings.showwarning

        def record(message, category, filename, lineno, file=None, line=None):
            if threading.get_ident() == thread:
                records.append(warnings.WarningMessage(
                    message, category, filename, lineno, file, line
                ))
            else:
                show(message, category, filename, lineno, file, line)

        warnings.showwarning = record
        yield records


async def _heartbeat(
    control: CallControl,
    emit: Callable[[float, float | None, str], Awaitable[None]],
) -> None:
    """
    Send a progress notification every `HEARTBEAT_SECONDS` while the worker
    thread runs, so a client does not end a long request without events.

    Each value grows over the previous one without reaching the next event
    of the work: `k` notifications after an event of progress `p` send
    `p + k / (k + 1)`, below `p + 1`. The message names what runs and for
    how long ("ForecasterStats: running (35 s)").
    """

    seen, beats = None, 0
    while True:
        await anyio.sleep(HEARTBEAT_SECONDS)
        activity = control.activity
        if activity is None:
            continue
        base, total, running, since = activity
        if total is not None and base >= total:
            # The work only writes its files after its last event: a value
            # above the total would read as more than 100 %.
            continue
        if (base, since) != seen:
            seen, beats = (base, since), 0
        beats += 1
        elapsed = int(time.monotonic() - since)
        try:
            await emit(
                base + beats / (beats + 1),
                total,
                f"{running}: running ({elapsed} s)",
            )
        except Exception as exc:
            # A heartbeat that cannot be sent changes nothing: the call goes
            # on, and a cancellation reaches it through its own request.
            logger.debug("Progress notification not sent: %s", exc)


async def run_call(
    work: Callable[[CallControl], T],
    report: Callable[[float, float | None, str], Awaitable[None]] | None = None,
    label: str = "call",
) -> CallOutcome[T]:
    """
    Run the work of a tool in a worker thread, under the process lock, with
    its warnings captured.

    A cancelled request sets `CallControl.cancelled`; the work stops at its
    next check (between the candidates of a comparison), and never starts
    when it was waiting for its turn. The worker thread always runs to its
    end before this returns, so the lock is never released while the core
    is still running.

    Parameters
    ----------
    work : Callable
        Function run in the worker thread with a `CallControl`.
    report : Callable, default None
        Async function that sends a progress notification (the
        `report_progress` of the MCP context, a no-op when the client asked
        for no progress), called through `CallControl.progress` and, every
        `HEARTBEAT_SECONDS` while the worker thread runs, by a heartbeat.
        Values never go back: a heartbeat computed before an event of the
        work that is sent after it is dropped.
    label : str, default 'call'
        What the call runs, named by the heartbeat notifications.

    Returns
    -------
    outcome : CallOutcome
        Value of `work` and the warnings it emitted.
    """

    cancelled = threading.Event()
    control = CallControl(cancelled=cancelled, label=label)
    last_sent = -math.inf

    async def emit(progress: float, total: float | None, message: str) -> None:
        # Runs in the event loop, without awaiting between the check and the
        # update, so the values sent always grow.
        nonlocal last_sent
        if progress <= last_sent:
            return
        last_sent = progress
        await report(progress, total, message)

    async def emit_event(
        progress: float, total: float, message: str, running: str | None
    ) -> None:
        # An event of the work becomes the base of the heartbeats only here,
        # in the event loop and with its value already recorded as sent, so
        # no heartbeat built on it can be sent before it.
        control.activity = (
            float(progress), total, running or label, time.monotonic()
        )
        await emit(progress, total, message)

    if report is not None:
        def send(
            progress: float, total: float, message: str, running: str | None
        ) -> None:
            anyio.from_thread.run(emit_event, progress, total, message, running)

        control.report = send
    result: dict[str, Any] = {}
    finished = False

    def target() -> None:
        with PROCESS_LOCK:
            control.begin()
            try:
                control.check()
                with _record_warnings() as records:
                    value = work(control)
                # Cancelled while the work ended: nothing will name its files.
                control.check()
                result["outcome"] = CallOutcome(value=value, warnings=records)
            except CallCancelled:
                result["cancelled"] = True
                for path in control.written:
                    with suppress(OSError):
                        os.remove(path)
            except Exception as exc:
                result["error"] = exc

    async def watch() -> None:
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            if not finished:
                cancelled.set()
            raise

    async with _call_gate():
        async with anyio.create_task_group() as group:
            group.start_soon(watch)
            if report is not None:
                group.start_soon(_heartbeat, control, emit)
            # Not abandoned on cancellation: the thread must end first.
            await anyio.to_thread.run_sync(target)
            finished = True
            group.cancel_scope.cancel()

    if "error" in result:
        raise result["error"]
    if "cancelled" in result or cancelled.is_set():
        # Raises the cancellation of the request, if there is one.
        await anyio.lowlevel.checkpoint()
        raise ServerError(
            "The call was cancelled. Nothing was registered.",
            code = "internal_error",
        )

    return result["outcome"]


def build_notices(
    records: Iterable[warnings.WarningMessage],
    plan_warnings: Iterable[str] = (),
    data_warnings: Iterable[str] = (),
    default_source: str = "runtime",
    server_notices: Iterable[ToolNotice] = (),
) -> tuple[list[ToolNotice], int]:
    """
    Turn the warnings of a call into notices.

    Warnings are deduplicated by category and text. `CandidateFailedWarning`
    is left out (the failures of a comparison are in its result) and
    deprecation warnings go to the log of the server.

    Parameters
    ----------
    records : iterable of warnings.WarningMessage
        Warnings emitted by the call.
    plan_warnings : iterable of str, default ()
        Texts of `plan.warnings` of the plans of the call: a warning with
        one of these texts has source `'plan'`.
    data_warnings : iterable of str, default ()
        Texts of the warnings emitted when the data was profiled: a warning
        with one of these texts has source `'data'`.
    default_source : str, default 'runtime'
        Source of any other warning (`'data'` for the `profile` tool).
    server_notices : iterable of ToolNotice, default ()
        Notices of the server itself (a model that will download its
        weights), placed before the warnings so they are never omitted.

    Returns
    -------
    notices : list of ToolNotice
        The first 20 distinct warnings.
    omitted : int
        Number of distinct warnings left out.
    """

    plan_texts = set(plan_warnings)
    data_texts = set(data_warnings)
    counts: dict[tuple[str, str], int] = {}
    for record in records:
        category = record.category
        if issubclass(category, CandidateFailedWarning):
            continue
        text = notice_text(record)
        if issubclass(category, (DeprecationWarning, PendingDeprecationWarning)):
            logger.info("%s: %s", category.__name__, text)
            continue
        key = (category.__name__, text)
        counts[key] = counts.get(key, 0) + 1

    notices = [
        notice.model_copy(update={"message": _cut_notice(notice.message)})
        for notice in server_notices
    ]
    for (category, text), count in counts.items():
        if text in plan_texts:
            source = "plan"
        elif text in data_texts:
            source = "data"
        else:
            source = default_source
        notices.append(
            ToolNotice(
                source   = source,
                category = category,
                message  = _cut_notice(text),
                count    = count,
            )
        )

    return notices[:MAX_NOTICES], max(0, len(notices) - MAX_NOTICES)


def _cut_notice(message: str) -> str:
    """
    Cut the text of a notice to `MAX_NOTICE_CHARS`, saying how many
    characters were left out.
    """

    if len(message) <= MAX_NOTICE_CHARS:
        return message
    omitted_chars = len(message) - MAX_NOTICE_CHARS

    return f"{message[:MAX_NOTICE_CHARS]} ... ({omitted_chars} more characters)"


def notice_text(record: warnings.WarningMessage) -> str:
    """
    Text of a warning without the suggestion of skforecast on how to
    silence it.

    Parameters
    ----------
    record : warnings.WarningMessage
        Recorded warning.

    Returns
    -------
    text : str
        Text of the warning.
    """

    text = str(record.message)
    position = text.find(_SUPPRESS_HINT)

    return text if position < 0 else text[:position]
