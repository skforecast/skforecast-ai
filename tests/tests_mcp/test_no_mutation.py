# Unit test that no tool changes the registered objects

from skforecast_ai.mcp.server import _build_server, _build_state

from .fixtures_mcp import content_of, df_h2o_csv, run_session, write_csv


def _snapshot(store):
    """
    Return the JSON of every registered object and of its envelope, by id.
    """
    return {
        entry.id: (
            entry.obj.model_dump_json(),
            entry.envelope.model_dump_json(),
            entry.code,
        )
        for entry in store.entries()
    }


def test_tools_do_not_modify_registered_objects(tmp_path):
    """
    Test that no tool changes an object registered before it ran, whatever
    it is passed (the core receives copies).
    """
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    state = _build_state(tmp_path, tmp_path / "out", 256, 1024)
    server = _build_server(state)
    changed = []

    async def steps(client):
        async def checked(name, arguments):
            before = _snapshot(state.store)
            result = content_of(await client.call_tool(name, arguments))
            after = _snapshot(state.store)
            changed.extend(
                (name, object_id)
                for object_id, value in before.items()
                if after[object_id] != value
            )
            return result

        profile = await checked("profile", {"data_path": path, "target": "x"})
        plan = await checked(
            "plan",
            {
                "profile_id": profile["id"],
                "steps": 12,
                "interval": [0.1, 0.9],
                "estimator_kwargs": {"alpha": 2.0},
            },
        )
        refined = await checked(
            "refine_plan",
            {
                "plan_id": plan["id"],
                "overrides": {"lags": 3, "interval": None, "estimator_kwargs": None},
            },
        )
        await checked(
            "refine_plan",
            {
                "plan_id": plan["id"],
                "overrides": {"forecaster": "ForecasterStats"},
            },
        )
        cv = await checked("create_cv", {"plan_id": plan["id"], "refit": True})
        await checked(
            "create_cv", {"plan_id": refined["id"], "initial_train_size": "2005-06-01"}
        )
        await checked("backtest", {"cv_id": cv["id"]})
        await checked("backtest", {"cv_id": cv["id"], "plan_id": refined["id"]})
        comparison = await checked(
            "compare",
            {
                "cv_id": cv["id"],
                "interval": [0.1, 0.9],
                "candidates": [
                    {"name": "ridge", "config": {"estimator": "Ridge"}},
                    {"name": "lags", "config": {"estimator": "Ridge", "lags": 3}},
                ],
            },
        )
        await checked("forecast", {"plan_id": plan["id"]})
        await checked(
            "forecast",
            {"plan_id": comparison["links"]["best_plan_id"], "test_size": 12},
        )
        await checked("get_code", {"object_id": plan["id"]})
        await checked(
            "get_code",
            {"object_id": comparison["id"], "candidate": "Baseline (seasonal naive)"},
        )
        await checked("describe_object", {"object_id": profile["id"]})
        await checked("list_objects", {})

    run_session(server, steps)

    assert len(state.store.entries()) == 12
    assert changed == []
