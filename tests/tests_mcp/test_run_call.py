# Unit test run_call

import io
import re
import sys
import threading
import time
import warnings
from contextlib import redirect_stdout
import anyio
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp._runtime import PROCESS_LOCK, run_call


def test_run_call_runs_one_call_at_a_time_with_its_own_warnings():
    """
    Test that concurrent calls never overlap, that each call gets only the
    warnings it emitted, and that `sys.stdout` is the original one after
    calls that redirect it.
    """
    active = []
    overlaps = []
    stdout = sys.stdout

    def make_work(i):
        def work(control):
            active.append(i)
            if len(active) > 1:
                overlaps.append(list(active))
            with redirect_stdout(io.StringIO()):
                print("noise")
                time.sleep(0.02)
            warnings.warn(f"warning of call {i}", UserWarning)
            active.remove(i)
            return i
        return work

    async def main():
        outcomes = {}

        async def one(i):
            outcomes[i] = await run_call(make_work(i))

        async with anyio.create_task_group() as group:
            for i in range(6):
                group.start_soon(one, i)
        return outcomes

    outcomes = anyio.run(main)

    assert overlaps == []
    assert sys.stdout is stdout
    for i, outcome in outcomes.items():
        assert outcome.value == i
        assert [str(w.message) for w in outcome.warnings] == [f"warning of call {i}"]


def test_run_call_raises_the_error_of_the_work():
    """
    Test that an exception of the work is raised by `run_call`.
    """
    def work(control):
        raise InvalidInputError("Bad input.", field="steps")

    async def main():
        await run_call(work)

    with pytest.raises(InvalidInputError, match=re.escape("Bad input.")):
        anyio.run(main)


def test_run_call_cancelled_while_waiting_for_the_lock_never_runs_the_work():
    """
    Test that a call cancelled while another one holds the process lock
    does not run its work once the lock is free, that the cancellation
    reaches the caller only after its thread ended, and that the lock is
    free afterwards.
    """
    ran = []
    held = threading.Event()
    release = threading.Event()

    def holder():
        with PROCESS_LOCK:
            held.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    held.wait(5)

    async def free_lock_later():
        await anyio.sleep(0.4)
        release.set()

    async def main():
        async with anyio.create_task_group() as group:
            group.start_soon(free_lock_later)
            with anyio.move_on_after(0.2) as scope:
                await run_call(lambda control: ran.append(1))
        return scope.cancelled_caught

    try:
        cancelled = anyio.run(main)
    finally:
        release.set()
        thread.join()

    assert cancelled is True
    assert ran == []
    assert PROCESS_LOCK.acquire(timeout=1)
    PROCESS_LOCK.release()
