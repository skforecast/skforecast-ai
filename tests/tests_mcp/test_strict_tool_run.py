# Unit test _StrictTool.run

import logging
import re
import sys

from skforecast_ai.mcp import _preload
from skforecast_ai.mcp._preload import Preload

from .fixtures_mcp import call, content_of, error_of, h2o_server


def test_strict_tool_run_waits_for_the_background_import(
    tmp_path, monkeypatch, request
):
    """
    Test that a tool called while the background import runs waits for it
    and then answers: the module the import loads (it takes 0.5 seconds) is
    loaded when the tool returns, and the tool gives its normal result.
    """
    name = f"skforecast_ai_run_probe_{tmp_path.name.replace('-', '_')}"
    (tmp_path / f"{name}.py").write_text("import time\ntime.sleep(0.5)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    request.addfinalizer(lambda: sys.modules.pop(name, None))
    preload = Preload([name])
    monkeypatch.setattr(_preload, "PRELOAD", preload)
    server, _ = h2o_server(tmp_path)

    result = content_of(call(server, "list_objects", {}))

    assert preload.done
    assert name in sys.modules
    assert result == {
        "objects": [], "removed": 0, "max_objects": 256, "max_memory_mb": 1024,
    }


def test_strict_tool_run_reports_a_failed_background_import(
    tmp_path, monkeypatch, caplog
):
    """
    Test that a tool called after the background import failed answers
    with an `internal_error` that names the type of the import error and an
    id, as any unexpected error: the message and the traceback go to the
    log of the server under that id, not to the agent.
    """
    server, _ = h2o_server(tmp_path)
    monkeypatch.setattr(
        _preload, "PRELOAD", Preload(["skforecast_ai_module_that_does_not_exist"])
    )

    with caplog.at_level(logging.ERROR, logger="skforecast_ai.mcp"):
        result = call(server, "list_objects", {})

    error = error_of(result, "list_objects")
    error_id = error["details"]["error_id"]

    assert re.fullmatch(r"error-[0-9a-f]{12}", error_id)
    assert error == {
        "code": "internal_error",
        "message": (
            f"Unexpected ModuleNotFoundError. Its message and traceback are in "
            f"the log of the server (stderr) under the id {error_id}."
        ),
        "field": None,
        "hint": (
            "Report it to the user with the id; do not retry with the same "
            "inputs."
        ),
        "details": {"error_id": error_id, "error_type": "ModuleNotFoundError"},
    }
    assert "skforecast_ai_module_that_does_not_exist" not in str(error)
    assert any(error_id in record.getMessage() for record in caplog.records)
