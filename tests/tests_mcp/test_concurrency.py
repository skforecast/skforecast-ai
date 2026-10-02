# Unit test concurrent tool calls

import sys
import threading
import time
import anyio

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server

from .fixtures_mcp import DATA_WARNING, content_of, df_data_warning, df_h2o_csv, run_session, write_csv


def test_concurrent_calls_never_overlap_and_keep_their_own_notices(tmp_path, monkeypatch):
    """
    Test that concurrent calls run the core one at a time, that each response
    carries only the warnings of its own call, and that `sys.stdout` is the
    original one afterwards.
    """
    h2o = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    warned = write_csv(tmp_path, "warning.csv", df_data_warning)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    stdout = sys.stdout
    running = []
    overlaps = []
    lock = threading.Lock()
    profile = ForecastingAssistant.profile

    def slow_profile(self, *args, **kwargs):
        with lock:
            running.append(1)
            if len(running) > 1:
                overlaps.append(len(running))
        try:
            time.sleep(0.05)
            return profile(self, *args, **kwargs)
        finally:
            with lock:
                running.pop()

    monkeypatch.setattr(ForecastingAssistant, "profile", slow_profile)

    async def steps(client):
        results = {}

        async def one(i):
            path, target = (warned, "y") if i % 2 else (h2o, "x")
            results[i] = content_of(
                await client.call_tool("profile", {"data_path": path, "target": target})
            )

        async with anyio.create_task_group() as group:
            for i in range(8):
                group.start_soon(one, i)
        return results

    results = run_session(server, steps)

    assert overlaps == []
    assert sys.stdout is stdout
    for i, result in results.items():
        messages = [notice["message"] for notice in result["notices"]]
        assert messages == ([DATA_WARNING] if i % 2 else [])
    assert len({result["id"] for result in results.values()}) == 8
