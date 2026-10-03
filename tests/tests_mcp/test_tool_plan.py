# Unit test tool plan

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server
from skforecast_ai.mcp.models import ToolNotice

from .fixtures_mcp import (
    GAPS_WARNING,
    call,
    content_of,
    df_h2o_gaps_csv,
    error_of,
    h2o_server,
    write_csv,
)

LGBM_WARNING = (
    "'not_a_param' is not a named parameter of LGBMRegressor. It is passed to "
    "the library as an extra parameter, which ignores it without an error if it "
    "does not exist."
)


def _profiled(tmp_path):
    """
    Return a server, the path of the h2o file and the id of its profile.
    """
    server, path = h2o_server(tmp_path)
    profile_id = content_of(
        call(server, "profile", {"data_path": path, "target": "x"})
    )["id"]

    return server, path, profile_id


@pytest.mark.parametrize(
    "arguments",
    [
        {"steps": 12},
        {"steps": 12, "interval": [0.1, 0.9], "lags": [1, 2, 12]},
        {
            "steps": 6,
            "forecaster": "ForecasterDirect",
            "estimator": "Ridge",
            "estimator_kwargs": {"alpha": 0.5},
            "window_features": [{"stats": ["mean"], "window_size": 6}],
        },
        {"steps": 12, "forecaster": "ForecasterStats"},
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_plan_output_matches_python_api(tmp_path, arguments):
    """
    Test that `plan` registers the plan the Python API builds, described by
    its forecasting script, links it to its profile and lists the arguments
    of `refine_plan`; `get_code` returns that script.
    """
    server, path, profile_id = _profiled(tmp_path)

    result = content_of(call(server, "plan", {"profile_id": profile_id, **arguments}))
    code = content_of(call(server, "get_code", {"object_id": result["id"]}))

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    plan = assistant.plan(profile=profile, **arguments)
    script = assistant.forecast_code(profile=profile, plan=plan)

    assert result["id"].startswith("plan-2-")
    assert result["kind"] == "plan"
    assert result["links"] == {"profile_id": profile_id}
    assert result["summary"] == script.describe()
    assert result["notices"] == []
    assert result["changeable"] == [
        "estimator",
        "estimator_kwargs",
        "forecaster",
        "interval",
        "lags",
        "steps",
        "window_features",
    ]
    assert result["cost"] is None
    assert code == {
        "id": result["id"],
        "kind": "plan",
        "candidate": None,
        "code": script.code,
        "code_truncated": False,
        "files": {},
    }


def test_tool_plan_notices_of_the_plan(tmp_path):
    """
    Test that a warning the plan carries in `plan.warnings` is a notice with
    source 'plan'.
    """
    server, _, profile_id = _profiled(tmp_path)

    result = content_of(
        call(
            server,
            "plan",
            {
                "profile_id": profile_id,
                "steps": 12,
                "forecaster": "ForecasterRecursive",
                "estimator": "LGBMRegressor",
                "estimator_kwargs": {"not_a_param": 1},
            },
        )
    )

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(source="plan", category="UserWarning", message=LGBM_WARNING, count=1)
    ]


@pytest.mark.parametrize(
    "arguments, code, field",
    [
        ({"steps": "12"}, "invalid_argument", "steps"),
        ({"steps": 12.0}, "invalid_argument", "steps"),
        ({"steps": True}, "invalid_argument", "steps"),
        ({"steps": 0}, "invalid_argument", "steps"),
        ({"steps": 12, "metric": "mean_absolute_error"}, "invalid_argument", "metric"),
        ({"steps": 12, "lags": ["1"]}, "invalid_argument", "lags"),
        (
            {"steps": 12, "forecaster": "ForecasterStats", "lags": 3},
            "invalid_argument",
            "lags",
        ),
        ({"steps": 12, "estimator": "os.system"}, "invalid_argument", "estimator"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_plan_invalid_argument(tmp_path, arguments, code, field):
    """
    Test that the arguments are checked strictly (no text for a number, no
    float or bool for an integer, no unknown argument) and that the errors of
    the core keep their field.
    """
    server, _, profile_id = _profiled(tmp_path)

    error = error_of(
        call(server, "plan", {"profile_id": profile_id, **arguments}), "plan"
    )

    assert error["code"] == code
    assert error["field"] == field


def test_tool_plan_unknown_or_wrong_id(tmp_path):
    """
    Test that an id that does not exist is `unknown_id` and the id of a plan
    passed as a profile is `invalid_argument`, both naming `profile_id`.
    """
    server, _, profile_id = _profiled(tmp_path)
    plan_id = content_of(call(server, "plan", {"profile_id": profile_id, "steps": 12}))[
        "id"
    ]

    unknown = error_of(
        call(server, "plan", {"profile_id": "profile-99-000000", "steps": 12}), "plan"
    )
    wrong = error_of(call(server, "plan", {"profile_id": plan_id, "steps": 12}), "plan")

    assert (unknown["code"], unknown["field"]) == ("unknown_id", "profile_id")
    assert (wrong["code"], wrong["field"]) == ("invalid_argument", "profile_id")
    assert wrong["message"] == (
        f"{plan_id!r} is the id of a plan, and `profile_id` takes the id of a "
        f"profile (returned by profile)."
    )


def test_tool_plan_announces_model_download_once(tmp_path, monkeypatch):
    """
    Test that the first plan with a foundation model whose weights are not
    in the local Hugging Face cache carries a `ModelDownloadNotice` (source
    'plan') with its license, that a second plan with the same model does
    not, and that a model already in the cache is never announced.
    """
    cache = tmp_path / "hf"
    (cache / "models--Synthefy--Nori" / "snapshots" / "abc").mkdir(parents=True)
    (cache / "models--Synthefy--Nori" / "snapshots" / "abc" / "f").write_text("")
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    server, _, profile_id = _profiled(tmp_path)
    base = {"profile_id": profile_id, "steps": 12, "forecaster": "ForecasterFoundation"}

    first = content_of(call(server, "plan", base))
    second = content_of(call(server, "plan", {**base, "interval": [0.1, 0.9]}))
    cached = content_of(call(server, "plan", {**base, "estimator": "Synthefy/Nori"}))

    assert first["notices"] == [
        ToolNotice(
            source   = "plan",
            category = "ModelDownloadNotice",
            message  = (
                "The weights of 'autogluon/chronos-2-small' were not found in "
                "the local Hugging Face cache: the first run may download "
                "them from the Hugging Face Hub. License: its license is "
                "Apache-2.0 (https://huggingface.co/autogluon/chronos-2-small)."
            ),
            count    = 1,
        ).model_dump()
    ]
    assert second["notices"] == []
    assert cached["notices"] == []


@pytest.mark.parametrize("steps", [205, 500, 10**9], ids=lambda s: f"steps={s}")
def test_tool_plan_invalid_argument_when_steps_longer_than_the_series(
    tmp_path, steps
):
    """
    Test that a horizon longer than the longest series of the profile (h2o
    has 204 observations) is `invalid_argument` on `steps` when the plan is
    built, instead of failing when it runs, and that 204 is accepted.
    """
    server, _, profile_id = _profiled(tmp_path)

    error = error_of(
        call(server, "plan", {"profile_id": profile_id, "steps": steps}), "plan"
    )
    longest = call(server, "plan", {"profile_id": profile_id, "steps": 204})

    assert (error["code"], error["field"]) == ("invalid_argument", "steps")
    assert error["message"] == (
        f"`steps` is {steps}, more than the 204 observations of the longest "
        f"series of the data. The horizon must not exceed the history."
    )
    assert error["details"] == {"steps": steps, "longest_series": 204}
    assert content_of(longest)["kind"] == "plan"


def test_tool_plan_notices_of_the_plan_and_of_its_data(tmp_path):
    """
    Test that a plan carries, as notices, the warnings of the data it was
    built from (source 'data') besides its own (source 'plan'), so the agent
    sees a data problem where it decides the plan.
    """
    path = write_csv(tmp_path, "gaps.csv", df_h2o_gaps_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    profile_id = content_of(
        call(server, "profile", {"data_path": path, "target": "x"})
    )["id"]

    result = content_of(
        call(
            server,
            "plan",
            {
                "profile_id": profile_id,
                "steps": 12,
                "estimator_kwargs": {"not_a_param": 1},
                "estimator": "LGBMRegressor",
            },
        )
    )

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(source="data", category="DataProfileWarning",
                   message=GAPS_WARNING, count=1),
        ToolNotice(source="plan", category="UserWarning",
                   message=LGBM_WARNING, count=1),
    ]
