# Integration test of the MCP server over stdio

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import sys
import time
import anyio
import pytest
from mcp import Client, StdioServerParameters

from skforecast_ai import ForecastingAssistant
from skforecast_ai._constants import DEFAULT_FOUNDATION_MODEL_ID
from skforecast_ai._foundation import (
    foundation_backend_installed,
    resolve_foundation_model,
)

from .fixtures_mcp import content_of, df_h2o_csv, error_of, write_csv


@pytest.mark.slow
def test_stdio_server_runs_the_planning_workflow(tmp_path):
    """
    Test that `skforecast-ai mcp` serves the tools over stdio in a process of
    its own: profile, plan and create_cv give the results of the Python API,
    an error arrives as the JSON of the error, and the output directory is
    created.
    """
    data = tmp_path / "data"
    data.mkdir()
    path = write_csv(data, "h2o.csv", df_h2o_csv)
    output_dir = tmp_path / "out"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from skforecast_ai.cli import app; app()",
            "mcp",
            "--allow-dir",
            str(data),
            "--output-dir",
            str(output_dir),
        ],
        env=dict(os.environ),
        cwd=str(tmp_path),
    )

    async def main():
        async with Client(parameters) as client:
            profile = content_of(
                await client.call_tool("profile", {"data_path": path, "target": "x"})
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 12}
                )
            )
            cv = content_of(
                await client.call_tool("create_cv", {"plan_id": plan["id"]})
            )
            code = content_of(
                await client.call_tool("get_code", {"object_id": plan["id"]})
            )
            error = await client.call_tool("plan", {"profile_id": "x", "steps": 12})
            return profile, plan, cv, code, error

    profile, plan, cv, code, error = anyio.run(main)

    assistant = ForecastingAssistant()
    expected_profile = assistant.profile(path, target="x")
    expected_plan = assistant.plan(profile=expected_profile, steps=12)
    expected_cv = assistant.create_cv(profile=expected_profile, plan=expected_plan)
    script = assistant.forecast_code(profile=expected_profile, plan=expected_plan)

    assert profile["summary"] == expected_profile.describe()
    assert plan["summary"] == script.describe()
    assert cv["summary"] == expected_cv.describe()
    # A `compare` without candidates runs the foundation model, one window
    # per fold of the single series, only when its backend is installed.
    backend = foundation_backend_installed(
        resolve_foundation_model(DEFAULT_FOUNDATION_MODEL_ID)
    )
    assert cv["cost"] == {
        "n_folds": 6, "n_fits": 1, "estimator_fits": 1, "inference_windows": 0,
        "compare_estimator_fits": 19, "compare_inference_windows": 6 if backend else 0,
    }
    assert code["code"] == script.code
    assert error_of(error, "plan")["code"] == "unknown_id"
    assert output_dir.is_dir()


@pytest.mark.slow
def test_stdio_server_runs_executes_reports_progress_and_cancels(tmp_path):
    """
    Test over stdio that a backtest writes its files, that `compare` sends
    growing progress notifications, and that a comparison cancelled by the
    client after its first event registers nothing while the server keeps
    answering.
    """
    data = tmp_path / "data"
    data.mkdir()
    path = write_csv(data, "h2o.csv", df_h2o_csv)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from skforecast_ai.cli import app; app()",
            "mcp",
            "--allow-dir",
            str(data),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        env=dict(os.environ),
        cwd=str(tmp_path),
    )
    candidates = [
        {"name": f"lags_{lags}", "config": {"estimator": "Ridge", "lags": lags}}
        for lags in range(1, 13)
    ]

    async def main():
        async with Client(parameters) as client:
            profile = content_of(
                await client.call_tool("profile", {"data_path": path, "target": "x"})
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 12}
                )
            )
            cv = content_of(
                await client.call_tool(
                    "create_cv", {"plan_id": plan["id"], "refit": True}
                )
            )
            backtest = content_of(
                await client.call_tool("backtest", {"cv_id": cv["id"]})
            )
            events = []

            async def record(progress, total, message):
                # The events of the candidates; a heartbeat (a value between
                # two of them) only comes after a long silence.
                if progress == int(progress):
                    events.append((progress, total))

            comparison = content_of(
                await client.call_tool(
                    "compare",
                    {"cv_id": cv["id"], "candidates": candidates[:2]},
                    progress_callback=record,
                )
            )
            first = anyio.Event()

            async def first_event(progress, total, message):
                first.set()

            with anyio.CancelScope() as scope:
                async with anyio.create_task_group() as group:

                    async def cancel():
                        await first.wait()
                        scope.cancel()

                    group.start_soon(cancel)
                    await client.call_tool(
                        "compare",
                        {"cv_id": cv["id"], "candidates": candidates},
                        progress_callback=first_event,
                    )
            objects = content_of(await client.call_tool("list_objects", {}))["objects"]
            return backtest, comparison, events, scope.cancelled_caught, objects

    backtest, comparison, events, cancelled, objects = anyio.run(main)

    assert sorted(backtest["files"]) == ["metrics", "predictions"]
    assert comparison["kind"] == "comparison"
    assert events == [
        (1.0, 6.0),
        (2.0, 6.0),
        (3.0, 6.0),
        (4.0, 6.0),
        (5.0, 6.0),
        (6.0, 6.0),
    ]
    assert cancelled is True
    assert [o["kind"] for o in objects].count("comparison") == 1


# Starts the server with a heartbeat every 0.2 s and a backtest that takes
# 1.5 s longer, to see the heartbeat cross the process boundary.
_SLOW_SERVER = """
import sys, time
from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import _runtime
from skforecast_ai.cli import app
_runtime.HEARTBEAT_SECONDS = 0.2
backtest = ForecastingAssistant.backtest
def slow(self, *args, **kwargs):
    time.sleep(1.5)
    return backtest(self, *args, **kwargs)
ForecastingAssistant.backtest = slow
app()
"""


@pytest.mark.slow
def test_stdio_server_heartbeat_during_a_long_backtest(tmp_path):
    """
    Test over stdio that a backtest longer than the heartbeat sends growing
    progress notifications to the client while it runs, naming its
    forecaster and the seconds it has run, and then returns its result.
    """
    data = tmp_path / "data"
    data.mkdir()
    path = write_csv(data, "h2o.csv", df_h2o_csv)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            _SLOW_SERVER,
            "mcp",
            "--allow-dir",
            str(data),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        env=dict(os.environ),
        cwd=str(tmp_path),
    )

    async def main():
        async with Client(parameters) as client:
            profile = content_of(
                await client.call_tool("profile", {"data_path": path, "target": "x"})
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 12}
                )
            )
            cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
            events = []

            async def record(progress, total, message):
                events.append((progress, total, message))

            backtest = content_of(
                await client.call_tool(
                    "backtest", {"cv_id": cv["id"]}, progress_callback=record
                )
            )
            return backtest, events

    backtest, events = anyio.run(main)

    values = [progress for progress, _, _ in events]
    assert backtest["kind"] == "backtest"
    assert len(events) >= 3
    assert values == sorted(set(values))
    assert all(0 < progress < 1 for progress in values)
    assert all(
        message.startswith("ForecasterRecursive: running (") for _, _, message in events
    )


def _jsonrpc_server(tmp_path):
    """
    Start the slow server of `_SLOW_SERVER` as a process with pipes, run the
    handshake and a profile, a plan and a strategy, and return the process,
    a function that sends a message and the id of the strategy.
    """
    data = tmp_path / "data"
    data.mkdir()
    path = write_csv(data, "h2o.csv", df_h2o_csv)
    # A server that does not exit writes where each of its threads waits,
    # before the test gives up on it.
    script = (
        "import faulthandler\n"
        "faulthandler.dump_traceback_later(45, exit=False)\n" + _SLOW_SERVER
    )
    process = subprocess.Popen(
        [
            sys.executable, "-c", script, "mcp",
            "--allow-dir", str(data), "--output-dir", str(tmp_path / "out"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(tmp_path),
    )

    def send(message):
        process.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())
        process.stdin.flush()

    def readline():
        # Bounded: a server that hangs is killed, which ends the read.
        with ThreadPoolExecutor(max_workers=1) as pool:
            line = pool.submit(process.stdout.readline)
            try:
                return line.result(timeout=60)
            except TimeoutError:
                process.kill()
                raise

    def call(number, name, arguments):
        send({
            "id": number,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        return json.loads(readline())["result"]["structuredContent"]

    send({
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    })
    try:
        readline()
        send({"method": "notifications/initialized"})
        profile = call(2, "profile", {"data_path": path, "target": "x"})
        plan = call(3, "plan", {"profile_id": profile["id"], "steps": 12})
        cv = call(4, "create_cv", {"plan_id": plan["id"]})
    except BaseException:
        process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
        raise

    return process, send, cv["id"]


@pytest.mark.slow
def test_stdio_server_exits_cleanly_when_the_client_disconnects_during_a_call(
    tmp_path,
):
    """
    Test that when the client closes its pipes while a backtest runs, the
    server ends the call and exits with code 0, logging two plain lines (the
    start, with both directories on one line, and the disconnection) and no
    traceback of the broken pipe.
    """
    process, send, cv_id = _jsonrpc_server(tmp_path)
    try:
        send({
            "id": 5,
            "method": "tools/call",
            "params": {"name": "backtest", "arguments": {"cv_id": cv_id}},
        })
        time.sleep(0.5)
        process.stdout.close()
        process.stdin.close()
        # The standard error is read while waiting: a server that writes
        # more than its pipe holds (4 KB on Windows, less than a traceback)
        # would wait for a reader and never exit.
        with ThreadPoolExecutor(max_workers=1) as pool:
            reading = pool.submit(process.stderr.read)
            try:
                code = process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                pytest.fail(
                    "The server did not exit after the client disconnected. "
                    "Its standard error:\n"
                    + reading.result().decode(errors="replace")
                )
            stderr = reading.result().decode()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

    lines = stderr.splitlines()
    assert code == 0
    assert "Traceback" not in stderr
    assert len(lines) == 2
    assert lines[0].endswith(
        f"skforecast-ai MCP server: reads CSV files in {tmp_path / 'data'}, "
        f"writes files to {tmp_path / 'out'}."
    )
    assert lines[1].endswith("The client disconnected; the server stops.")
