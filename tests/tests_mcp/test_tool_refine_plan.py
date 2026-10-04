# Unit test tool refine_plan

import pytest

from skforecast_ai import ForecastingAssistant

from .fixtures_mcp import call, content_of, error_of, h2o_server, profile_and_plan


def _planned(tmp_path, **plan_arguments):
    """
    Return a server, the h2o profile and plan of the Python API, and the ids
    of the same profile and plan in the server.
    """
    server, path = h2o_server(tmp_path)
    profile_id, plan_id = profile_and_plan(server, path, **plan_arguments)
    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    plan = assistant.plan(profile=profile, steps=12, **plan_arguments)

    return server, profile, plan, profile_id, plan_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"lags": 3},
        {},
        {"interval": None},
        {"lags": None, "steps": 6},
        {"forecaster": "ForecasterDirect", "estimator": "Ridge"},
        {"estimator_kwargs": None},
        {"metric": ["mean_squared_error"], "use_exog": False},
        {"differentiation": 1},
        {
            "calendar_features": [],
            "target_transformer": "none",
            "dropna_from_series": True,
        },
    ],
    ids=lambda dt: f"overrides: {dt}",
)
def test_tool_refine_plan_output_matches_python_api(tmp_path, overrides):
    """
    Test that `refine_plan` registers the plan the Python API refines with
    the same overrides (an omitted key keeps the value of the plan, a null
    one asks for the default), links it to its profile and to the original
    plan, and keeps the original plan.
    """
    server, profile, plan, profile_id, plan_id = _planned(
        tmp_path, interval=[0.1, 0.9], lags=[1, 2, 12]
    )
    original = content_of(call(server, "describe_object", {"object_id": plan_id}))

    result = content_of(
        call(server, "refine_plan", {"plan_id": plan_id, "overrides": overrides})
    )

    assistant = ForecastingAssistant()
    refined = assistant.refine_plan(profile=profile, plan=plan, **overrides)
    script = assistant.forecast_code(profile=profile, plan=refined)

    assert result["kind"] == "plan"
    assert result["links"] == {"profile_id": profile_id, "parent_plan_id": plan_id}
    assert result["summary"] == script.describe()
    assert (
        content_of(call(server, "get_code", {"object_id": result["id"]}))["code"]
        == script.code
    )
    assert (
        content_of(call(server, "describe_object", {"object_id": plan_id})) == original
    )


def test_tool_refine_plan_keeps_omitted_and_resets_null_keys(tmp_path):
    """
    Test that an omitted `interval` keeps the interval of the plan and an
    `interval` set to null removes it.
    """
    server, _, _, _, plan_id = _planned(tmp_path, interval=[0.1, 0.9])

    kept = content_of(
        call(server, "refine_plan", {"plan_id": plan_id, "overrides": {"lags": 3}})
    )
    removed = content_of(
        call(
            server,
            "refine_plan",
            {
                "plan_id": plan_id,
                "overrides": {"lags": 3, "interval": None},
            },
        )
    )

    assert "Prediction interval: [0.1, 0.9]" in kept["summary"]
    assert "Prediction interval" not in removed["summary"]


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"metric": "accuracy"}, "overrides.metric"),
        ({"metric": ["mean_squared_error", "mean_squared_error"]}, "overrides.metric"),
        ({"preprocessing_steps": []}, "overrides.preprocessing_steps"),
        ({"steps": "6"}, "overrides.steps"),
        ({"lags": [0]}, "overrides.lags"),
        ({"steps": 0}, "overrides.steps"),
        ({"forecaster": None}, "overrides.forecaster"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_refine_plan_invalid_argument(tmp_path, overrides, field):
    """
    Test that unknown keys and wrong types of `overrides` are rejected before
    the core runs (`forecaster` takes no null), and that the errors of the
    core name the key of `overrides`.
    """
    server, _, _, _, plan_id = _planned(tmp_path)

    error = error_of(
        call(server, "refine_plan", {"plan_id": plan_id, "overrides": overrides}),
        "refine_plan",
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == field


def test_tool_refine_plan_overrides_given_as_json_text(tmp_path):
    """
    Test that `overrides` given as JSON text, as some clients send objects,
    is decoded like the object itself.
    """
    server, _, _, _, plan_id = _planned(tmp_path)

    as_text = content_of(
        call(server, "refine_plan", {"plan_id": plan_id, "overrides": '{"lags": 3}'})
    )
    as_object = content_of(
        call(server, "refine_plan", {"plan_id": plan_id, "overrides": {"lags": 3}})
    )

    assert as_text["summary"] == as_object["summary"]


def test_tool_refine_plan_announces_model_download(tmp_path, monkeypatch):
    """
    Test that refining a plan to a foundation model whose weights are not in
    the local Hugging Face cache announces the download once.
    """
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    refined = content_of(
        call(
            server,
            "refine_plan",
            {
                "plan_id": plan_id,
                "overrides": {
                    "forecaster": "ForecasterFoundation",
                    "estimator": "soda-inria/tabicl",
                },
            },
        )
    )
    again = content_of(
        call(
            server,
            "refine_plan",
            {"plan_id": refined["id"], "overrides": {"interval": [0.1, 0.9]}},
        )
    )

    assert [(n["source"], n["category"]) for n in refined["notices"]] == [
        ("plan", "ModelDownloadNotice")
    ]
    assert "'soda-inria/tabicl'" in refined["notices"][0]["message"]
    assert again["notices"] == []


def test_tool_refine_plan_invalid_argument_when_steps_longer_than_the_series(
    tmp_path,
):
    """
    Test that `overrides.steps` longer than the longest series of the
    profile is `invalid_argument` before anything runs.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    error = error_of(
        call(server, "refine_plan", {"plan_id": plan_id, "overrides": {"steps": 500}}),
        "refine_plan",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "overrides.steps")
    assert error["details"] == {"steps": 500, "longest_series": 204}
