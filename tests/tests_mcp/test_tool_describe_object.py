# Unit test tool describe_object

from skforecast_ai.mcp import create_server

from .fixtures_mcp import call, content_of, df_data_warning, error_of, run_session, write_csv


def test_tool_describe_object_returns_the_response_that_created_it(tmp_path):
    """
    Test that `describe_object` returns the response of the tool that created
    the object, notices included.
    """
    path = write_csv(tmp_path, "warning.csv", df_data_warning)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def steps(client):
        created = content_of(await client.call_tool("profile", {"data_path": path, "target": "y"}))
        described = content_of(await client.call_tool("describe_object", {"object_id": created["id"]}))
        return created, described

    created, described = run_session(server, steps)

    assert len(created["notices"]) == 1
    assert described == created


def test_tool_describe_object_unknown_id(tmp_path):
    """
    Test that an id that does not exist is `unknown_id` naming `object_id`.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(call(server, "describe_object", {"object_id": "cv-one"}), "describe_object")

    assert error == {
        "code": "unknown_id",
        "message": "No object has the id 'cv-one'.",
        "field": "object_id",
        "hint": "Call `list_objects` to see the ids registered now.",
        "details": {"id": "cv-one", "removed": False},
    }
