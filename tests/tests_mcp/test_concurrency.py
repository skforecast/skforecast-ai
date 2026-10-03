# Unit test concurrent tool calls

import sys
import threading
import time
import anyio

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server

from .fixtures_mcp import (
    DATA_WARNING,
    content_of,
    cv_of,
    df_data_warning,
    df_h2o_csv,
    h2o_server,
    run_session,
    write_csv,
)


def test_concurrent_calls_never_overlap_and_keep_their_own_notices(
    tmp_path, monkeypatch
):
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


def test_concurrent_executions_never_overlap_and_keep_their_own_notices(
    tmp_path, monkeypatch
):
    """
    Test that concurrent backtests and forecasts run their scripts one at a
    time, that only the backtest that trains many estimators reports
    `LongTrainingWarning`, and that `sys.stdout` (which the scripts
    redirect) is the original one afterwards.
    """
    server, path = h2o_server(tmp_path)
    _, _, long_cv = cv_of(
        server,
        path,
        steps=12,
        forecaster="ForecasterDirect",
        cv_arguments={"refit": True},
    )
    _, plan_id, short_cv = cv_of(server, path)
    stdout = sys.stdout
    running = []
    overlaps = []
    lock = threading.Lock()

    def tracked(method):
        def wrapper(self, *args, **kwargs):
            with lock:
                running.append(1)
                if len(running) > 1:
                    overlaps.append(len(running))
            try:
                return method(self, *args, **kwargs)
            finally:
                with lock:
                    running.pop()

        return wrapper

    monkeypatch.setattr(
        ForecastingAssistant, "backtest", tracked(ForecastingAssistant.backtest)
    )
    monkeypatch.setattr(
        ForecastingAssistant, "forecast", tracked(ForecastingAssistant.forecast)
    )
    calls = [
        ("backtest", {"cv_id": long_cv}),
        ("backtest", {"cv_id": short_cv}),
        ("forecast", {"plan_id": plan_id}),
        ("backtest", {"cv_id": long_cv}),
        ("forecast", {"plan_id": plan_id, "test_size": 12}),
        ("backtest", {"cv_id": short_cv}),
    ]

    async def steps(client):
        results = {}

        async def one(i, name, arguments):
            results[i] = content_of(await client.call_tool(name, arguments))

        async with anyio.create_task_group() as group:
            for i, (name, arguments) in enumerate(calls):
                group.start_soon(one, i, name, arguments)
        return results

    results = run_session(server, steps)

    assert overlaps == []
    assert sys.stdout is stdout
    for i, (name, arguments) in enumerate(calls):
        categories = [notice["category"] for notice in results[i]["notices"]]
        expected = ["LongTrainingWarning"] if arguments.get("cv_id") == long_cv else []
        assert categories == expected, (i, categories)
