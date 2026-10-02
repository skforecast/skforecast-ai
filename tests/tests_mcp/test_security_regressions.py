# Unit test security regressions of the MCP server
#
# Every payload would create the file `pwned` if it reached Python code or a
# network request; each test checks the error and that the file is absent.

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import pytest

from skforecast_ai.mcp import create_server

from .fixtures_mcp import (
    MARKER_CODE,
    call,
    content_of,
    df_h2o_csv,
    error_of,
    profile_and_plan,
    run_session,
    write_csv,
)

# Payload that closes a string literal and runs code, relative to the
# working directory so it fits in a file name.
INJECTION = "'); " + MARKER_CODE.format(marker="pwned") + "; ('"


def _server(tmp_path):
    """
    Return a server allowed to read `tmp_path / 'data'`, the h2o file in it
    and the marker path.
    """
    data = tmp_path / "data"
    data.mkdir()
    path = write_csv(data, "h2o.csv", df_h2o_csv)
    server = create_server(allow_dir=data, output_dir=tmp_path / "out")

    return server, path, tmp_path / "pwned"


def test_security_url_is_never_requested(tmp_path):
    """
    Test that a URL as `data_path` is `url_not_allowed` and never requested:
    a local server that would create the marker on any request sees none.
    """
    server, _, marker = _server(tmp_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            marker.touch()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"date,x\n2020-01-01,1\n")

        def log_message(self, *args):
            pass

    http = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{http.server_address[1]}/data.csv"
        error = error_of(call(server, "profile", {"data_path": url, "target": "x"}), "profile")
    finally:
        http.shutdown()
        http.server_close()

    assert error["code"] == "url_not_allowed"
    assert not marker.exists()


@pytest.mark.parametrize(
    "make_path, code",
    [
        (lambda tmp: str(tmp / "data" / ".." / "outside" / "secret.csv"), "path_not_allowed"),
        (lambda tmp: str(tmp / "outside" / "secret.csv"), "path_not_allowed"),
        (lambda tmp: str(tmp / "data" / "link.csv"), "path_not_allowed"),
        (lambda tmp: "outside/secret.csv", "invalid_path"),
    ],
    ids=["dot-dot", "absolute outside", "symlink outside", "relative"]
)
def test_security_files_outside_allowed_dir_are_never_read(tmp_path, make_path, code):
    """
    Test that a CSV file outside the allowed directory, reached with '..', an
    absolute path, a symbolic link or a relative path, is rejected and
    nothing is registered.
    """
    server, _, _ = _server(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    write_csv(outside, "secret.csv", df_h2o_csv)
    os.symlink(outside / "secret.csv", tmp_path / "data" / "link.csv")

    error = error_of(
        call(server, "profile", {"data_path": make_path(tmp_path), "target": "x"}), "profile"
    )

    assert error["code"] == code
    assert error["field"] == "data_path"
    assert content_of(call(server, "list_objects", {}))["objects"] == []


@pytest.mark.parametrize(
    "arguments, field",
    [
        ({"forecaster": "ForecasterRecursive" + INJECTION}, "forecaster"),
        ({"estimator": "Ridge" + INJECTION}, "estimator"),
        ({"estimator": "Ridge", "estimator_kwargs": {"alpha=1" + INJECTION + "#": 1}},
         "estimator_kwargs"),
        ({"window_features": [{"stats": ["mean" + INJECTION], "window_size": 3}]},
         "window_features"),
        ({"lags": INJECTION}, "lags"),
        ({"interval": [INJECTION, 0.9]}, "interval[0]"),
    ],
    ids=["forecaster", "estimator", "kwargs key", "window stat", "lags", "interval"]
)
def test_security_plan_arguments_never_reach_code(tmp_path, arguments, field):
    """
    Test that a payload in an argument of `plan` is `invalid_argument` and is
    never written into a script.
    """
    server, path, marker = _server(tmp_path)
    profile_id = content_of(call(server, "profile", {"data_path": path, "target": "x"}))["id"]

    error = error_of(
        call(server, "plan", {"profile_id": profile_id, "steps": 12, **arguments}), "plan"
    )

    assert error["code"] == "invalid_argument"
    assert error["field"].startswith(field)
    assert not marker.exists()


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"preprocessing_steps": [{"action": "x", "reason": "x", "code_snippet": INJECTION}]},
         "overrides.preprocessing_steps"),
        ({"forecaster_kwargs": {"lags": INJECTION}}, "overrides.forecaster_kwargs"),
        ({"estimator": INJECTION}, "overrides.estimator"),
    ],
    ids=["preprocessing", "forecaster kwargs", "estimator"]
)
def test_security_refine_plan_overrides_never_reach_code(tmp_path, overrides, field):
    """
    Test that `refine_plan` rejects fields of a plan that are not overrides
    (a plan is never accepted as JSON) and payloads in the overrides.
    """
    server, path, marker = _server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    error = error_of(
        call(server, "refine_plan", {"plan_id": plan_id, "overrides": overrides}),
        "refine_plan",
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == field
    assert not marker.exists()


def test_security_ids_are_never_parsed_as_objects(tmp_path):
    """
    Test that a plan passed as JSON in place of an id is `unknown_id`.
    """
    server, path, marker = _server(tmp_path)
    profile_and_plan(server, path)
    hostile_plan = (
        '{"task_type": "single_series", "forecaster": "ForecasterRecursive", '
        '"preprocessing_steps": [{"code_snippet": "' + INJECTION + '"}]}'
    )

    error = error_of(call(server, "create_cv", {"plan_id": hostile_plan}), "create_cv")

    assert error["code"] == "unknown_id"
    assert not marker.exists()


def test_security_initial_train_size_payload(tmp_path):
    """
    Test that a payload as the date of `initial_train_size` is rejected by
    the core as a date it cannot read.
    """
    server, path, marker = _server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, "initial_train_size": "2005" + INJECTION}),
        "create_cv",
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == "initial_train_size"
    assert not marker.exists()


def test_security_hostile_names_and_values_are_quoted_in_the_script(tmp_path):
    """
    Test that a file name, column names and an estimator argument value that
    close a string literal (valid for the core, which quotes them) are
    written quoted into the script of `get_code`, which runs as a file
    without creating the marker.
    """
    data = tmp_path / "data"
    data.mkdir()
    frame = df_h2o_csv.rename(columns={"fecha": "date" + INJECTION, "x": "y" + INJECTION})
    path = write_csv(data, "h2o" + INJECTION + ".csv", frame)
    server = create_server(allow_dir=data, output_dir=tmp_path / "out")

    async def steps(client):
        profile = content_of(await client.call_tool("profile", {
            "data_path": path, "target": "y" + INJECTION, "date_column": "date" + INJECTION,
        }))
        plan = content_of(await client.call_tool("plan", {
            "profile_id": profile["id"], "steps": 12, "forecaster": "ForecasterRecursive",
            "estimator": "Ridge", "estimator_kwargs": {"solver": "auto" + INJECTION},
        }))
        return content_of(await client.call_tool("get_code", {"object_id": plan["id"]}))["code"]

    code = run_session(server, steps)
    script = tmp_path / "script.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True,
        timeout=300,
    )

    assert repr(path) in code
    assert repr("auto" + INJECTION) in code
    assert "InvalidParameterError" in proc.stderr
    assert not (tmp_path / "pwned").exists()
    assert not Path("pwned").exists()
