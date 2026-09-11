# Unit test run_agent_sync llm/runtime

import pytest

from skforecast_ai.llm.runtime import run_agent_sync


def testrun_agent_sync_output_and_forwards_args():
    """
    Test that run_agent_sync awaits agent.run, forwards args/kwargs, and
    returns the awaited value.
    """
    received = {}

    class _FakeAgent:
        async def run(self, *args, **kwargs):
            received["args"] = args
            received["kwargs"] = kwargs
            return "result"

    result = run_agent_sync(_FakeAgent(), "a", "b", deps="d", model_settings="s")

    assert result == "result"
    assert received["args"] == ("a", "b")
    assert received["kwargs"] == {"deps": "d", "model_settings": "s"}


def testrun_agent_sync_runs_on_shared_background_loop():
    """
    Test that agent.run executes on the shared background loop (a daemon
    thread), not the caller's thread, and that the same loop is reused
    across calls.
    """
    import threading

    seen = {}

    class _FakeAgent:
        async def run(self, *args, **kwargs):
            loop = __import__("asyncio").get_running_loop()
            seen.setdefault("loops", []).append(id(loop))
            seen.setdefault("threads", []).append(
                threading.current_thread().ident
            )
            return "ok"

    agent = _FakeAgent()
    run_agent_sync(agent, "first")
    run_agent_sync(agent, "second")

    # Executed off the caller (main) thread
    assert seen["threads"][0] != threading.current_thread().ident
    # Same background loop reused across calls
    assert seen["loops"][0] == seen["loops"][1]


def testrun_agent_sync_propagates_exceptions():
    """
    Test that an exception raised inside agent.run propagates to the
    synchronous caller.
    """

    class _FakeAgent:
        async def run(self, *args, **kwargs):
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_agent_sync(_FakeAgent(), "msg")
