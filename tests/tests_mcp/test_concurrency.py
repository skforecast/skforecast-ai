# Unit test concurrent tool calls

import sys
import threading
import time
import warnings
import anyio

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import _preload, create_server
from skforecast_ai.mcp import server as server_module
from skforecast_ai.mcp._preload import Preload

from .fixtures_mcp import (
    DATA_MISSING_EXOG_WARNING,
    DATA_WARNING,
    call,
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
        assert messages == (
            [DATA_MISSING_EXOG_WARNING, DATA_WARNING] if i % 2 else []
        )
    assert len({result["id"] for result in results.values()}) == 8


def test_concurrent_executions_never_overlap_and_keep_their_own_notices(
    tmp_path, monkeypatch
):
    """
    Test that concurrent backtests and forecasts run their scripts one at a
    time, that only the backtests of the strategy that trains many
    estimators (confirmed with `confirm_cost`) report the warning their
    core call emits, and that `sys.stdout` (which the scripts redirect) is
    the original one afterwards.
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
    fits = content_of(
        call(server, "describe_object", {"object_id": long_cv})
    )["cost"]["estimator_fits"]
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
                # A warning of the confirmed backtests only, which must not
                # reach the notices of the other calls.
                if kwargs.get("confirm_cost"):
                    warnings.warn("A confirmed run.", UserWarning)
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
        ("backtest", {"cv_id": long_cv, "confirm_cost": fits}),
        ("backtest", {"cv_id": short_cv}),
        ("forecast", {"plan_id": plan_id}),
        ("backtest", {"cv_id": long_cv, "confirm_cost": fits}),
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
        # Every run with metrics computes MASE, whose reference the server
        # states, and MAPE, whose unit it states; a forecast of the future has
        # none, and an evaluation says first that its dates are already in
        # the data.
        future = name == "forecast" and "test_size" not in arguments
        expected = [] if future else ["MetricReferenceNotice", "MetricUnitNotice"]
        if name == "forecast" and not future:
            expected.insert(0, "HoldoutEvaluationNotice")
        if arguments.get("cv_id") == long_cv:
            expected.append("UserWarning")
        assert categories == expected, (i, categories)


def test_get_code_with_cold_distributions_does_not_hold_a_read_during_a_run(
    tmp_path, monkeypatch, request
):
    """
    Test that the first `get_code` of a session, which reads the installed
    distributions for its `requirements` (here with their cache empty and a
    scan that lasts until the test ends it), does not hold the event loop
    during a run: a `list_objects` sent while the scan and a backtest are
    still going answers before the scan ends (G05). Before, the scan ran in
    the event loop and every call waited for it.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id, cv_id = cv_of(server, path)
    # A preload that already ended and warms nothing: the test empties the
    # cache of the distributions itself.
    preload = Preload([])
    preload.wait()
    monkeypatch.setattr(_preload, "PRELOAD", preload)
    server_module._distributions.cache_clear()
    request.addfinalizer(server_module._distributions.cache_clear)
    release = threading.Event()
    running = threading.Event()
    scanning = threading.Event()
    scanned = []
    backtest = ForecastingAssistant.backtest
    packages_distributions = server_module.metadata.packages_distributions

    def long_backtest(self, *args, **kwargs):
        running.set()
        release.wait(timeout=5)
        return backtest(self, *args, **kwargs)

    def cold_packages_distributions():
        scanning.set()
        release.wait(timeout=5)
        scanned.append(time.monotonic())
        return packages_distributions()

    monkeypatch.setattr(ForecastingAssistant, "backtest", long_backtest)
    monkeypatch.setattr(
        server_module.metadata, "packages_distributions", cold_packages_distributions
    )

    async def steps(client):
        results = {}

        async def one(name, arguments):
            results[name] = content_of(await client.call_tool(name, arguments))

        async with anyio.create_task_group() as group:
            group.start_soon(one, "backtest", {"cv_id": cv_id})
            await anyio.to_thread.run_sync(running.wait, 5)
            group.start_soon(one, "get_code", {"object_id": plan_id})
            await anyio.to_thread.run_sync(scanning.wait, 5)
            listed = content_of(await client.call_tool("list_objects", {}))
            answered = time.monotonic()
            release.set()
        return results, listed, answered

    results, listed, answered = run_session(server, steps)

    assert answered < scanned[0]
    assert {entry["kind"] for entry in listed["objects"]} == {"profile", "plan", "cv"}
    assert [name.split("==")[0] for name in results["get_code"]["requirements"]] == [
        "pandas", "scikit-learn", "skforecast"
    ]
    assert results["backtest"]["kind"] == "backtest"
