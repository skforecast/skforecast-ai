# Unit test start_preload_after_answer

import sys
import time
from types import SimpleNamespace
import anyio
import pytest

from skforecast_ai.mcp import _preload
from skforecast_ai.mcp._preload import Preload, start_preload_after_answer

from .fixtures_mcp import h2o_server, run_session


def _finished(preload: Preload, seconds: float = 30.0) -> bool:
    """
    Whether `preload` ends within `seconds`, without calling its `wait`
    (which would start it).
    """
    deadline = time.monotonic() + seconds
    while not preload.done and time.monotonic() < deadline:
        time.sleep(0.01)

    return preload.done


def _probe(tmp_path, monkeypatch, request) -> str:
    """
    Write an empty module into `tmp_path`, importable while the test runs,
    and return its name.
    """
    name = f"skforecast_ai_answer_probe_{tmp_path.name.replace('-', '_')}"
    (tmp_path / f"{name}.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    request.addfinalizer(lambda: sys.modules.pop(name, None))

    return name


@pytest.mark.parametrize("method", ["initialize", "server/discover", "tools/list"])
def test_start_preload_after_answer_returns_the_answer_and_starts_the_import(
    tmp_path, monkeypatch, request, method
):
    """
    Test that the middleware returns what the rest of the chain answers and
    then starts the background import, whatever the first message is (the
    handshake of either protocol, or a request of a client that sends none).
    """
    name = _probe(tmp_path, monkeypatch, request)
    preload = Preload([name])
    monkeypatch.setattr(_preload, "PRELOAD", preload)
    started_before_answer = []

    async def call_next(ctx):
        started_before_answer.append(preload.done)
        return {"answer": ctx.method}

    result = anyio.run(
        start_preload_after_answer, SimpleNamespace(method=method), call_next
    )

    assert result == {"answer": method}
    assert started_before_answer == [False]
    assert _finished(preload)
    assert name in sys.modules


def test_start_preload_after_answer_runs_when_a_client_lists_the_tools(
    tmp_path, monkeypatch, request
):
    """
    Test that a session that only lists the tools starts the background
    import of the server: the first tool does not have to start it.
    """
    name = _probe(tmp_path, monkeypatch, request)
    preload = Preload([name])
    monkeypatch.setattr(_preload, "PRELOAD", preload)
    server, _ = h2o_server(tmp_path)

    async def steps(client):
        return await client.list_tools()

    tools = run_session(server, steps)

    assert len(tools.tools) == 11
    assert _finished(preload)
    assert name in sys.modules
