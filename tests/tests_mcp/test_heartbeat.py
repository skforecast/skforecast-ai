# Unit test _heartbeat (through run_call)

import time
import anyio

from skforecast_ai.mcp import _runtime
from skforecast_ai.mcp._runtime import run_call


def _run(work, label, monkeypatch, seconds=0.05):
    """
    Run `work` with `run_call` and a heartbeat every `seconds`; return the
    value and the notifications sent.
    """
    monkeypatch.setattr(_runtime, "HEARTBEAT_SECONDS", seconds)
    sent = []

    async def report(progress, total, message):
        sent.append((progress, total, message))

    async def main():
        return await run_call(work, report=report, label=label)

    outcome = anyio.run(main)

    return outcome.value, sent


def test_heartbeat_while_the_worker_thread_is_busy(monkeypatch):
    """
    Test that a call without events of its own sends a notification every
    heartbeat while its thread runs: growing values below 1 (the first
    event a work could send), no total, and a message naming the label and
    the seconds it has run.
    """
    def work(control):
        time.sleep(0.6)
        return "done"

    value, sent = _run(work, "ForecasterStats", monkeypatch)

    assert value == "done"
    assert len(sent) >= 3
    values = [progress for progress, _, _ in sent]
    assert values == sorted(set(values))
    assert all(0 < progress < 1 for progress in values)
    assert values[:3] == [1 / 2, 2 / 3, 3 / 4]
    assert {total for _, total, _ in sent} == {None}
    assert sent[0][2] == "ForecasterStats: running (0 s)"


def test_heartbeat_between_events_stays_below_the_next_event(monkeypatch):
    """
    Test that heartbeats after an event of the work grow from its value
    without reaching the next one, keep its total, and name the candidate
    that runs; after the end of a candidate they name the call again.
    """
    def work(control):
        control.progress(1, 4, "slow: started", running="slow")
        time.sleep(0.4)
        control.progress(2, 4, "slow: succeeded")
        time.sleep(0.3)
        control.progress(3, 4, "next: started", running="next")
        return None

    _, sent = _run(work, "compare", monkeypatch)

    values = [progress for progress, _, _ in sent]
    assert values == sorted(set(values))
    real = [entry for entry in sent if entry[0] == int(entry[0])]
    assert real == [
        (1, 4, "slow: started"),
        (2, 4, "slow: succeeded"),
        (3, 4, "next: started"),
    ]
    between = [entry for entry in sent if 1 < entry[0] < 2]
    after_end = [entry for entry in sent if 2 < entry[0] < 3]
    assert between and after_end
    assert {total for _, total, _ in between + after_end} == {4}
    assert all(message.startswith("slow: running (") for _, _, message in between)
    assert all(
        message.startswith("compare: running (") for _, _, message in after_end
    )


def test_heartbeat_not_sent_without_report_or_for_quick_calls(monkeypatch):
    """
    Test that no heartbeat is sent for a call shorter than the interval,
    and that a call without `report` runs as before.
    """
    _, sent = _run(lambda control: 1, "plan", monkeypatch, seconds=5)

    async def main():
        return await run_call(lambda control: 2)

    assert sent == []
    assert anyio.run(main).value == 2


def test_heartbeat_failure_to_send_does_not_stop_the_call(monkeypatch):
    """
    Test that a heartbeat that cannot be sent (the client is gone) leaves
    the call running to its end.
    """
    monkeypatch.setattr(_runtime, "HEARTBEAT_SECONDS", 0.05)

    async def report(progress, total, message):
        raise RuntimeError("closed")

    def work(control):
        time.sleep(0.3)
        return "done"

    async def main():
        return await run_call(work, report=report, label="backtest")

    assert anyio.run(main).value == "done"


def test_heartbeat_not_sent_above_the_total(monkeypatch):
    """
    Test that after the last event of a work (progress equal to the total),
    while the work writes its files, no heartbeat is sent, so the client
    never reads more than 100 %.
    """
    def work(control):
        control.progress(2, 2, "only: succeeded")
        time.sleep(0.4)
        return None

    _, sent = _run(work, "compare", monkeypatch)

    assert sent == [(2, 2, "only: succeeded")]
