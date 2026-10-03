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
from skforecast.foundation import get_model_info

from skforecast_ai.mcp import create_server
from skforecast_ai.mcp._foundation import permissive_adapters, restricted_adapters

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
        error = error_of(
            call(server, "profile", {"data_path": url, "target": "x"}), "profile"
        )
    finally:
        http.shutdown()
        http.server_close()

    assert error["code"] == "url_not_allowed"
    assert not marker.exists()


@pytest.mark.parametrize(
    "make_path, code",
    [
        (
            lambda tmp: str(tmp / "data" / ".." / "outside" / "secret.csv"),
            "path_not_allowed",
        ),
        (lambda tmp: str(tmp / "outside" / "secret.csv"), "path_not_allowed"),
        (lambda tmp: str(tmp / "data" / "link.csv"), "path_not_allowed"),
        (lambda tmp: "outside/secret.csv", "invalid_path"),
    ],
    ids=["dot-dot", "absolute outside", "symlink outside", "relative"],
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
        call(server, "profile", {"data_path": make_path(tmp_path), "target": "x"}),
        "profile",
    )

    assert error["code"] == code
    assert error["field"] == "data_path"
    assert content_of(call(server, "list_objects", {}))["objects"] == []


@pytest.mark.parametrize(
    "arguments, field",
    [
        ({"forecaster": "ForecasterRecursive" + INJECTION}, "forecaster"),
        ({"estimator": "Ridge" + INJECTION}, "estimator"),
        (
            {
                "estimator": "Ridge",
                "estimator_kwargs": {"alpha=1" + INJECTION + "#": 1},
            },
            "estimator_kwargs",
        ),
        (
            {"window_features": [{"stats": ["mean" + INJECTION], "window_size": 3}]},
            "window_features",
        ),
        ({"lags": INJECTION}, "lags"),
        ({"interval": [INJECTION, 0.9]}, "interval[0]"),
    ],
    ids=["forecaster", "estimator", "kwargs key", "window stat", "lags", "interval"],
)
def test_security_plan_arguments_never_reach_code(tmp_path, arguments, field):
    """
    Test that a payload in an argument of `plan` is `invalid_argument` and is
    never written into a script.
    """
    server, path, marker = _server(tmp_path)
    profile_id = content_of(
        call(server, "profile", {"data_path": path, "target": "x"})
    )["id"]

    error = error_of(
        call(server, "plan", {"profile_id": profile_id, "steps": 12, **arguments}),
        "plan",
    )

    assert error["code"] == "invalid_argument"
    assert error["field"].startswith(field)
    assert not marker.exists()


@pytest.mark.parametrize(
    "overrides, field",
    [
        (
            {
                "preprocessing_steps": [
                    {"action": "x", "reason": "x", "code_snippet": INJECTION}
                ]
            },
            "overrides.preprocessing_steps",
        ),
        ({"forecaster_kwargs": {"lags": INJECTION}}, "overrides.forecaster_kwargs"),
        ({"estimator": INJECTION}, "overrides.estimator"),
    ],
    ids=["preprocessing", "forecaster kwargs", "estimator"],
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
        call(
            server,
            "create_cv",
            {"plan_id": plan_id, "initial_train_size": "2005" + INJECTION},
        ),
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
    frame = df_h2o_csv.rename(
        columns={"fecha": "date" + INJECTION, "x": "y" + INJECTION}
    )
    path = write_csv(data, "h2o" + INJECTION + ".csv", frame)
    server = create_server(allow_dir=data, output_dir=tmp_path / "out")

    async def steps(client):
        profile = content_of(
            await client.call_tool(
                "profile",
                {
                    "data_path": path,
                    "target": "y" + INJECTION,
                    "date_column": "date" + INJECTION,
                },
            )
        )
        plan = content_of(
            await client.call_tool(
                "plan",
                {
                    "profile_id": profile["id"],
                    "steps": 12,
                    "forecaster": "ForecasterRecursive",
                    "estimator": "Ridge",
                    "estimator_kwargs": {"solver": "auto" + INJECTION},
                },
            )
        )
        return content_of(
            await client.call_tool("get_code", {"object_id": plan["id"]})
        )["code"]

    code = run_session(server, steps)
    script = tmp_path / "script.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert repr(path) in code
    assert repr("auto" + INJECTION) in code
    assert "InvalidParameterError" in proc.stderr
    assert not (tmp_path / "pwned").exists()
    assert not Path("pwned").exists()


@pytest.mark.parametrize(
    "make_path, code",
    [
        (
            lambda tmp: str(tmp / "data" / ".." / "outside" / "future.csv"),
            "path_not_allowed",
        ),
        (lambda tmp: str(tmp / "data" / "future_link.csv"), "path_not_allowed"),
        (lambda tmp: "future.csv", "invalid_path"),
        (lambda tmp: "https://example.org/future.csv", "url_not_allowed"),
    ],
    ids=["dot-dot", "symlink outside", "relative", "url"],
)
def test_security_exog_files_outside_allowed_dir_are_never_read(
    tmp_path, make_path, code
):
    """
    Test that `exog_path` follows the same rules as `data_path`: a file
    outside the allowed directory, a relative path or a URL is rejected and
    no forecast is registered.
    """
    server, path, _ = _server(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    write_csv(outside, "future.csv", df_h2o_csv.iloc[:12])
    os.symlink(outside / "future.csv", tmp_path / "data" / "future_link.csv")
    _, plan_id = profile_and_plan(server, path)

    error = error_of(
        call(
            server, "forecast", {"plan_id": plan_id, "exog_path": make_path(tmp_path)}
        ),
        "forecast",
    )
    kinds = [o["kind"] for o in content_of(call(server, "list_objects", {}))["objects"]]

    assert error["code"] == code
    assert error["field"] == "exog_path"
    assert "forecast" not in kinds


def test_security_executed_scripts_keep_hostile_values_quoted(tmp_path):
    """
    Test that the tools that run scripts (forecast, backtest, compare) run
    them with hostile column names, file name and estimator argument values
    quoted: the marker is never created, and the estimator rejects the value
    as a parameter it does not know.
    """
    data = tmp_path / "data"
    data.mkdir()
    frame = df_h2o_csv.rename(
        columns={"fecha": "date" + INJECTION, "x": "y" + INJECTION}
    )
    path = write_csv(data, "h2o" + INJECTION + ".csv", frame)
    server = create_server(allow_dir=data, output_dir=tmp_path / "out")
    kwargs = {"solver": "auto" + INJECTION}

    async def steps(client):
        profile = content_of(
            await client.call_tool(
                "profile",
                {
                    "data_path": path,
                    "target": "y" + INJECTION,
                    "date_column": "date" + INJECTION,
                },
            )
        )
        clean = content_of(
            await client.call_tool(
                "plan",
                {
                    "profile_id": profile["id"],
                    "steps": 12,
                    "forecaster": "ForecasterRecursive",
                    "estimator": "Ridge",
                },
            )
        )
        hostile = content_of(
            await client.call_tool(
                "plan",
                {
                    "profile_id": profile["id"],
                    "steps": 12,
                    "forecaster": "ForecasterRecursive",
                    "estimator": "Ridge",
                    "estimator_kwargs": kwargs,
                },
            )
        )
        cv = content_of(await client.call_tool("create_cv", {"plan_id": clean["id"]}))
        return [
            await client.call_tool("forecast", {"plan_id": clean["id"]}),
            await client.call_tool(
                "forecast", {"plan_id": hostile["id"], "test_size": 12}
            ),
            await client.call_tool(
                "backtest", {"cv_id": cv["id"], "plan_id": hostile["id"]}
            ),
            await client.call_tool(
                "compare",
                {
                    "cv_id": cv["id"],
                    "candidates": [
                        {
                            "name": "hostile" + INJECTION,
                            "config": {
                                "estimator": "Ridge",
                                "estimator_kwargs": kwargs,
                            },
                        },
                        {"name": "clean", "config": {"estimator": "Ridge"}},
                    ],
                },
            ),
        ]

    forecast, hostile_forecast, hostile_backtest, comparison = run_session(
        server, steps
    )

    assert not forecast.is_error
    assert error_of(hostile_forecast, "forecast")["code"] == "execution_failed"
    assert error_of(hostile_backtest, "backtest")["code"] == "execution_failed"
    assert not comparison.is_error
    assert not (tmp_path / "pwned").exists()
    assert not Path("pwned").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        {"estimator_kwargs": {"device_map": "cpu"}},
        {"estimator": "priorlabs/tabpfn-ts", "estimator_kwargs": {"mode": "client"}},
    ],
    ids=["chronos device", "tabpfn client mode"],
)
def test_security_foundation_kwargs_outside_the_allowlist_in_plan(tmp_path, arguments):
    """
    Test that keyword arguments of a foundation model outside the allowlist
    of the server (which could send the data to a remote service or
    download files) are `invalid_argument` in `plan`, while an allowed one
    builds the plan.
    """
    server, path, _ = _server(tmp_path)
    profile_id, _ = profile_and_plan(server, path)
    base = {"profile_id": profile_id, "steps": 12, "forecaster": "ForecasterFoundation"}

    error = error_of(call(server, "plan", {**base, **arguments}), "plan")
    allowed = call(server, "plan", {**base, "estimator_kwargs": {"context_length": 64}})

    assert error["code"] == "invalid_argument"
    assert error["field"] == "estimator_kwargs"
    assert error["hint"] == "Use the Python API of skforecast-ai to pass them."
    assert content_of(allowed)["kind"] == "plan"


def test_security_foundation_kwargs_outside_the_allowlist_in_refine_and_compare(
    tmp_path,
):
    """
    Test that the allowlist also applies to `refine_plan` and to the
    candidates of `compare`, before anything runs.
    """
    server, path, _ = _server(tmp_path)
    _, plan_id = profile_and_plan(server, path, forecaster="ForecasterFoundation")
    cv_id = content_of(call(server, "create_cv", {"plan_id": plan_id}))["id"]

    refined = error_of(
        call(
            server,
            "refine_plan",
            {
                "plan_id": plan_id,
                "overrides": {"estimator_kwargs": {"mode": "client"}},
            },
        ),
        "refine_plan",
    )
    compared = error_of(
        call(
            server,
            "compare",
            {
                "cv_id": cv_id,
                "candidates": [
                    {
                        "name": "remote",
                        "config": {
                            "forecaster": "ForecasterFoundation",
                            "estimator_kwargs": {"mode": "client"},
                        },
                    },
                ],
            },
        ),
        "compare",
    )

    assert (refined["code"], refined["field"]) == (
        "invalid_argument",
        "overrides.estimator_kwargs",
    )
    assert (compared["code"], compared["field"]) == (
        "invalid_argument",
        "candidates[0].config.estimator_kwargs",
    )


RESTRICTED_MODELS = [info.default_model_id for info in restricted_adapters()]


def test_security_restricted_models_are_the_documented_ones():
    """
    Test that the foundation models the server rejects by default, derived
    from the information skforecast registers, are TimesFM 3.0, Moirai,
    TabPFN, t0 and TS-ICL, and that Chronos-2, TimesFM 2.5, TabICL and Nori
    run without `--allow-model`.
    """
    assert RESTRICTED_MODELS == [
        "google/timesfm-3.0-pytorch",
        "Salesforce/moirai-2.0-R-small",
        "priorlabs/tabpfn-ts",
        "theforecastingcompany/t0-alpha",
        "taharnbl/TS-ICL",
    ]
    assert [info.default_model_id for info in permissive_adapters()] == [
        "autogluon/chronos-2-small",
        "google/timesfm-2.5-200m-pytorch",
        "soda-inria/tabicl",
        "Synthefy/Nori",
    ]


@pytest.mark.parametrize("model_id", RESTRICTED_MODELS)
def test_security_restricted_model_in_plan_is_model_not_allowed(tmp_path, model_id):
    """
    Test that `plan` with a foundation model that has a license restriction
    or gated weights is `model_not_allowed`, naming the model and the
    `--allow-model` option in its hint, and registers no plan.
    """
    server, path, _ = _server(tmp_path)
    profile_id, _ = profile_and_plan(server, path)

    error = error_of(
        call(
            server,
            "plan",
            {
                "profile_id": profile_id,
                "steps": 12,
                "forecaster": "ForecasterFoundation",
                "estimator": model_id,
            },
        ),
        "plan",
    )
    plans = content_of(call(server, "list_objects", {"kind": "plan"}))["objects"]
    info = get_model_info(model_id)

    assert (error["code"], error["field"]) == ("model_not_allowed", "estimator")
    assert error["details"]["model_id"] == model_id
    assert error["details"]["license"] == info.license_restriction
    assert error["details"]["requires_hf_auth"] == info.requires_hf_auth
    assert f"--allow-model {info.model_id_prefixes[0]}" in error["hint"]
    assert len(plans) == 1


@pytest.mark.parametrize("model_id", RESTRICTED_MODELS)
def test_security_restricted_model_in_refine_plan_is_model_not_allowed(
    tmp_path, model_id
):
    """
    Test that `refine_plan` to a foundation model with a license restriction
    or gated weights is `model_not_allowed` on `overrides.estimator`.
    """
    server, path, _ = _server(tmp_path)
    _, plan_id = profile_and_plan(server, path, forecaster="ForecasterFoundation")

    error = error_of(
        call(
            server,
            "refine_plan",
            {"plan_id": plan_id, "overrides": {"estimator": model_id}},
        ),
        "refine_plan",
    )

    assert (error["code"], error["field"]) == (
        "model_not_allowed",
        "overrides.estimator",
    )
    assert error["details"]["model_id"] == model_id


@pytest.mark.parametrize("model_id", RESTRICTED_MODELS)
def test_security_restricted_model_in_compare_is_model_not_allowed(tmp_path, model_id):
    """
    Test that a candidate of `compare` with a foundation model that has a
    license restriction or gated weights makes the call `model_not_allowed`
    before any candidate runs, and registers nothing.
    """
    server, path, _ = _server(tmp_path)
    _, plan_id = profile_and_plan(server, path)
    cv_id = content_of(call(server, "create_cv", {"plan_id": plan_id}))["id"]

    error = error_of(
        call(
            server,
            "compare",
            {
                "cv_id": cv_id,
                "candidates": [
                    {"name": "ridge", "config": {"estimator": "Ridge"}},
                    {
                        "name": "restricted",
                        "config": {
                            "forecaster": "ForecasterFoundation",
                            "estimator": model_id,
                        },
                    },
                ],
            },
        ),
        "compare",
    )
    comparisons = content_of(call(server, "list_objects", {"kind": "comparison"}))

    assert (error["code"], error["field"]) == (
        "model_not_allowed",
        "candidates[1].config.estimator",
    )
    assert comparisons["objects"] == []


@pytest.mark.parametrize("model_id", RESTRICTED_MODELS)
def test_security_allow_model_runs_a_restricted_model(tmp_path, monkeypatch, model_id):
    """
    Test that `--allow-model` with the prefix of a restricted model lets
    `plan`, `refine_plan` and the candidates of `compare` use it (the
    candidate fails without its backend, ranked last, as in Python), and
    that a prefix of another model does not.
    """
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    data = tmp_path / "data"
    data.mkdir()
    path = write_csv(data, "h2o.csv", df_h2o_csv)
    prefix = get_model_info(model_id).model_id_prefixes[0]
    other = next(m for m in RESTRICTED_MODELS if m != model_id)
    server = create_server(
        allow_dir    = data,
        output_dir   = tmp_path / "out",
        allow_models = [prefix],
    )
    profile_id, plan_id = profile_and_plan(server, path)
    base = {"profile_id": profile_id, "steps": 12, "forecaster": "ForecasterFoundation"}
    cv_id = content_of(call(server, "create_cv", {"plan_id": plan_id}))["id"]

    planned = call(server, "plan", {**base, "estimator": model_id})
    refined = call(
        server,
        "refine_plan",
        {"plan_id": content_of(planned)["id"], "overrides": {"interval": None}},
    )
    other_error = error_of(call(server, "plan", {**base, "estimator": other}), "plan")
    compared = call(
        server,
        "compare",
        {
            "cv_id": cv_id,
            "candidates": [
                {"name": "ridge", "config": {"estimator": "Ridge"}},
                {
                    "name": "allowed",
                    "config": {
                        "forecaster": "ForecasterFoundation",
                        "estimator": model_id,
                    },
                },
            ],
        },
    )

    assert content_of(planned)["kind"] == "plan"
    assert content_of(refined)["kind"] == "plan"
    assert other_error["code"] == "model_not_allowed"
    assert content_of(compared)["kind"] == "comparison"
