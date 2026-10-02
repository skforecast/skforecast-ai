# Unit test tool plan

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp.models import ToolNotice

from .fixtures_mcp import call, content_of, error_of, h2o_server

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
