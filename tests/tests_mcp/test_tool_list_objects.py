# Unit test tool list_objects

from skforecast_ai.mcp import create_server

from .fixtures_mcp import call, content_of, df_h2o_csv, error_of, run_session, write_csv


def test_tool_list_objects_output_most_recent_first_and_by_kind(tmp_path):
    """
    Test that the objects are listed most recently used first with their
    links (building a plan uses its profile), that `kind` filters them, and
    that the limits of the server and the number of removed objects are
    reported.
    """
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    server = create_server(
        allow_dir=tmp_path, output_dir=tmp_path / "out", max_objects=3, max_memory_mb=50
    )

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "x"})
        )
        first = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 12})
        )
        second = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 6})
        )
        everything = content_of(await client.call_tool("list_objects", {}))
        plans = content_of(await client.call_tool("list_objects", {"kind": "plan"}))
        third = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 3})
        )
        after = content_of(await client.call_tool("list_objects", {}))
        return (
            profile["id"],
            first["id"],
            second["id"],
            third["id"],
            everything,
            plans,
            after,
        )

    profile_id, first, second, third, everything, plans, after = run_session(
        server, steps
    )
    links = {"profile_id": profile_id}

    assert everything == {
        "objects": [
            {"id": second, "kind": "plan", "links": links},
            {"id": profile_id, "kind": "profile", "links": {}},
            {"id": first, "kind": "plan", "links": links},
        ],
        "max_objects": 3,
        "max_memory_mb": 50,
        "removed": 0,
    }
    assert [o["id"] for o in plans["objects"]] == [second, first]
    assert [o["id"] for o in after["objects"]] == [third, profile_id, second]
    assert after["removed"] == 1


def test_tool_list_objects_invalid_argument_when_kind_unknown(tmp_path):
    """
    Test that a kind that does not exist is `invalid_argument`.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(call(server, "list_objects", {"kind": "model"}), "list_objects")

    assert (error["code"], error["field"]) == ("invalid_argument", "kind")
