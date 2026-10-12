# Unit test tool get_code

from importlib.metadata import version

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server, server as server_module

from ..fixtures_csv_dialect import df_dialect, write_dialect
from .fixtures_mcp import call, content_of, error_of, h2o_server, profile_and_plan


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
