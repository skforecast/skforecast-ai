# Unit test tool get_code

import subprocess
import sys
import textwrap
from importlib.metadata import version

import numpy as np
import pandas as pd

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server, server as server_module

from ..fixtures_csv_dialect import (
    df_dialect,
    df_dialect_excel,
    df_dialect_excel_exog,
    write_dialect,
    write_excel_es,
)
from .fixtures_mcp import (
    call,
    content_of,
    cv_of,
    error_of,
    h2o_server,
    profile_and_plan,
    run_session,
)


def test_tool_get_code_invalid_argument_when_object_has_no_code(tmp_path):
    """
    Test that the id of a profile, which has no code, is `invalid_argument`.
    """
    server, path = h2o_server(tmp_path)
    profile_id, _ = profile_and_plan(server, path)

    error = error_of(call(server, "get_code", {"object_id": profile_id}), "get_code")

    assert error == {
        "code": "invalid_argument",
        "message": (
            f"{profile_id!r} is a profile, which has no code: pass the id of a "
            f"plan, a cross-validation strategy, a backtest, a forecast or a "
            f"comparison."
        ),
        "field": "object_id",
        "hint": None,
        "details": None,
    }


def test_tool_get_code_cut_with_full_code_in_a_file(tmp_path, monkeypatch):
    """
    Test that code longer than the limit of `get_code` is cut, and written in
    full to a file of the output directory once, when the object is created.
    """
    monkeypatch.setattr(server_module, "MAX_CODE_CHARS", 50)
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)
    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    full = assistant.forecast_code(
        profile=profile, plan=assistant.plan(profile=profile, steps=12)
    ).code

    result = content_of(call(server, "get_code", {"object_id": plan_id}))
    again = content_of(call(server, "get_code", {"object_id": plan_id}))
    code_path = tmp_path / "out" / f"{plan_id}-code.py"

    assert result == {
        "id": plan_id,
        "kind": "plan",
        "candidate": None,
        "code": full[:50],
        "code_truncated": True,
        "requirements": [
            f"{package}=={version(package)}"
            for package in ("pandas", "scikit-learn", "skforecast")
        ],
        "files": {"code": str(code_path)},
    }
    assert again == result
    assert code_path.read_text(encoding="utf-8") == full


def test_tool_get_code_requirements_of_a_foundation_plan(tmp_path):
    """
    Test that the script of a plan with a foundation model lists the backend
    of the model among its requirements, after the packages it imports.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path, forecaster="ForecasterFoundation")

    result = content_of(call(server, "get_code", {"object_id": plan_id}))

    assert [name.split("==")[0] for name in result["requirements"]] == [
        "pandas",
        "skforecast",
        "chronos-forecasting",
    ]
    assert result["requirements"][:2] == [
        f"pandas=={version('pandas')}",
        f"skforecast=={version('skforecast')}",
    ]


def test_tool_get_code_requirements_of_a_strategy_of_a_foundation_plan(tmp_path):
    """
    Test that the script of a cross-validation strategy created for a plan
    with a foundation model, which builds the folds and loads no model,
    lists only skforecast: not the backend of the model, which the script of
    the plan lists (G05).
    """
    server, path = h2o_server(tmp_path)
    _, plan_id, cv_id = cv_of(server, path, forecaster="ForecasterFoundation")

    strategy = content_of(call(server, "get_code", {"object_id": cv_id}))
    plan = content_of(call(server, "get_code", {"object_id": plan_id}))

    assert strategy["requirements"] == [f"skforecast=={version('skforecast')}"]
    assert plan["requirements"][-1].split("==")[0] == "chronos-forecasting"


def test_tool_get_code_reads_the_file_with_its_dialect(tmp_path):
    """
    Test that the code of a plan built from a ';' file with a decimal comma
    reads it with `sep=';', decimal=','`, and that the code of a comma file
    names neither.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    comma_path = str(tmp_path / "us.csv")
    df_dialect.to_csv(comma_path, index=False)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="y", steps=3)
    _, comma_plan_id = profile_and_plan(server, comma_path, target="y", steps=3)

    result = content_of(call(server, "get_code", {"object_id": plan_id}))
    comma = content_of(call(server, "get_code", {"object_id": comma_plan_id}))

    assert not result["code_truncated"]
    assert f"data = pd.read_csv({path!r}, sep=';', decimal=',')\n" in result["code"]
    assert f"data = pd.read_csv({comma_path!r})\n" in comma["code"]
    assert "sep=" not in comma["code"]


def test_tool_get_code_end_to_end_when_forecast_with_exog_path_from_excel_es(
    tmp_path,
):
    """
    Test the session of data and future values saved by the Excel in
    Spanish (cp1252, ';', ',' as decimal mark, '.' between thousands, dates
    day first, rows made only of separators at the end of the future
    values): `profile`, `plan`, `forecast` with `exog_path` and `get_code`.
    The script reads the file of `exog_path` by its path, with its whole
    dialect, and not `exog_future.csv`; run as it is in another directory,
    it gives the predictions of `forecast`.
    """
    path = write_excel_es(tmp_path, df_dialect_excel, "ventas.csv")
    exog_path = write_excel_es(
        tmp_path, df_dialect_excel_exog, "futuro.csv", blank_rows=2
    )
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "año"})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 10})
        )
        forecast = content_of(
            await client.call_tool(
                "forecast", {"plan_id": plan["id"], "exog_path": exog_path}
            )
        )
        code = content_of(
            await client.call_tool("get_code", {"object_id": forecast["id"]})
        )
        return forecast, code

    forecast, code = run_session(server, steps)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    script = run_dir / "script.py"
    script.write_text(code["code"])
    wrapper = run_dir / "run.py"
    wrapper.write_text(textwrap.dedent(f"""
        import runpy
        import pandas as pd
        namespace = runpy.run_path({str(script)!r})
        pd.DataFrame(namespace["predictions"]).to_csv("predictions.csv")
    """))
    proc = subprocess.run(
        [sys.executable, str(wrapper)],
        cwd=run_dir, capture_output=True, text=True, timeout=600,
    )

    assert not code["code_truncated"]
    assert (
        f"exog_future = pd.read_csv({exog_path!r}, sep=';', decimal=',', "
        f"thousands='.', encoding='cp1252', dtype={{'fecha': str}})\n"
        "exog_future = exog_future.dropna(how='all')\n" in code["code"]
    )
    assert "exog_future.csv" not in code["code"]
    assert proc.returncode == 0, proc.stderr[-3000:]
    standalone = pd.read_csv(run_dir / "predictions.csv", index_col=0)
    expected = pd.read_csv(forecast["files"]["predictions"], index_col=0)
    assert list(standalone.index) == list(expected.index)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), expected["pred"].to_numpy(), rtol=1e-6
    )
