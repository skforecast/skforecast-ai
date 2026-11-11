# Unit test Preload.wait

import logging
import re
import sys
import threading
import pytest

from skforecast_ai.mcp._preload import Preload, PreloadError


def _probe_module(tmp_path, monkeypatch, request, body: str = "") -> tuple[str, object]:
    """
    Write a module into `tmp_path`, importable while the test runs, that
    appends a line to `imports.log` each time it is imported and then runs
    `body`; return its name and the path of the log.
    """
    name = f"skforecast_ai_preload_probe_{tmp_path.name.replace('-', '_')}"
    log = tmp_path / "imports.log"
    (tmp_path / f"{name}.py").write_text(
        "import pathlib\n"
        f"with pathlib.Path({str(log)!r}).open('a') as file:\n"
        "    file.write('imported\\n')\n" + body
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    request.addfinalizer(lambda: sys.modules.pop(name, None))

    return name, log


def test_preload_wait_imports_the_modules(tmp_path, monkeypatch, request):
    """
    Test that `wait` starts the import when nothing started it, returns once
    every module is imported and marks the preload as done.
    """
    name, log = _probe_module(tmp_path, monkeypatch, request)
    preload = Preload(["json", name])

    assert (preload.started, preload.done) == (False, False)

    preload.wait()

    assert (preload.started, preload.done) == (True, True)
    assert name in sys.modules
    assert log.read_text() == "imported\n"


def test_preload_wait_imports_once_for_callers_in_several_threads(
    tmp_path, monkeypatch, request
):
    """
    Test that a background import and five threads that wait for it at the
    same time import the module once, and that all of them return after it
    ends: a tool that arrives during the import waits instead of loading the
    modules a second time.
    """
    name, log = _probe_module(
        tmp_path, monkeypatch, request, "import time\ntime.sleep(0.3)\n"
    )
    preload = Preload([name])
    finished = []

    def waiter():
        preload.wait()
        finished.append(name in sys.modules)

    preload.start()
    threads = [threading.Thread(target=waiter) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    preload.start()
    preload.wait()

    assert finished == [True] * 5
    assert log.read_text() == "imported\n"


def test_preload_wait_PreloadError_when_an_import_fails(caplog):
    """
    Test that a failed import is raised by every `wait` as a `PreloadError`
    whose cause is the import error, and is logged once with its traceback,
    without importing again.
    """
    preload = Preload(["skforecast_ai_module_that_does_not_exist"])
    err_msg = re.escape(
        "The server could not import skforecast-ai and its dependencies."
    )

    with caplog.at_level(logging.ERROR, logger="skforecast_ai.mcp"):
        with pytest.raises(PreloadError, match=err_msg) as first:
            preload.wait()
        with pytest.raises(PreloadError, match=err_msg) as second:
            preload.wait()

    assert isinstance(first.value.__cause__, ModuleNotFoundError)
    assert second.value.__cause__ is first.value.__cause__
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is not None


def test_preload_wait_returns_before_the_warmed_calls(tmp_path, monkeypatch, request):
    """
    Test that the functions of `warm` run in the preload thread once the
    import ended, after `wait` returned (a tool never waits for them), and
    that one that fails is only logged and does not stop the next one.
    """
    name, _ = _probe_module(
        tmp_path,
        monkeypatch,
        request,
        "import threading\n"
        "release = threading.Event()\n"
        "calls = []\n"
        "def slow():\n"
        "    release.wait(timeout=30)\n"
        "    calls.append(threading.current_thread().name)\n"
        "def broken():\n"
        "    raise RuntimeError('warm failed')\n"
        "def fast():\n"
        "    calls.append('fast')\n",
    )
    preload = Preload([name], warm=[f"{name}:slow", f"{name}:broken", f"{name}:fast"])

    preload.wait()
    module = sys.modules[name]
    called_before = list(module.calls)
    module.release.set()
    preload._thread.join(timeout=30)

    assert called_before == []
    assert module.calls == ["skforecast-ai-preload", "fast"]


def test_preload_wait_of_the_server_then_warms_the_installed_distributions():
    """
    Test that the preload of the server warms the installed distributions
    that the `requirements` of `get_code` read (G05).
    """
    from skforecast_ai.mcp._preload import PRELOAD

    assert PRELOAD.warm == ("skforecast_ai.mcp.server:_distributions",)
