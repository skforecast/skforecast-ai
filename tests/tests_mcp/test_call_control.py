# Unit test CallControl

import re
import threading
import pytest

from skforecast_ai.mcp._runtime import CallCancelled, CallControl


def test_CallControl_progress_reports_and_stops_when_cancelled():
    """
    Test that progress is sent through `report`, that a cancelled call stops
    at the next report, and that without `report` nothing is sent.
    """
    sent = []
    cancelled = threading.Event()
    control = CallControl(cancelled=cancelled, report=lambda *args: sent.append(args))

    control.progress(1, 4, "a: started")
    cancelled.set()
    with pytest.raises(CallCancelled):
        control.progress(2, 4, "a: succeeded")

    assert sent == [(1, 4, "a: started")]
    assert CallControl(cancelled=threading.Event()).progress(1, 2, "x") is None


def test_CallControl_progress_failed_report():
    """
    Test that a report that fails because the call was cancelled meanwhile
    stops the call, and that any other failure is raised as it is, not taken
    for a cancellation.
    """
    cancelled = threading.Event()

    def failing_after_cancel(*args):
        cancelled.set()
        raise RuntimeError("closed")

    def broken(*args):
        raise RuntimeError("bug")

    with pytest.raises(CallCancelled):
        CallControl(cancelled=cancelled, report=failing_after_cancel).progress(
            1, 2, "x"
        )
    with pytest.raises(RuntimeError, match=re.escape("bug")):
        CallControl(cancelled=threading.Event(), report=broken).progress(1, 2, "x")


def test_CallControl_wrote_records_paths():
    """
    Test that `wrote` records paths given alone or in dicts by role, and
    skips None.
    """
    control = CallControl(cancelled=threading.Event())

    control.wrote({"predictions": "/out/a.csv"}, None, "/out/b.py", {})

    assert control.written == ["/out/a.csv", "/out/b.py"]
