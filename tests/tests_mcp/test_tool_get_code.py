# Unit test tool get_code

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import server as server_module

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
            f"plan or a cross-validation strategy."
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
        "id": plan_id, "kind": "plan", "code": full[:50], "code_truncated": True,
        "files": {"code": str(code_path)},
    }
    assert again == result
    assert code_path.read_text(encoding="utf-8") == full
