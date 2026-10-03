# Unit test tool create_cv

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp.models import ToolNotice

from .fixtures_mcp import call, content_of, error_of, h2o_server, profile_and_plan

CV_ARGUMENTS = [
    "initial_train_size",
    "fold_stride",
    "refit",
    "fixed_train_size",
    "gap",
    "skip_folds",
    "allow_incomplete_fold",
]


def _planned(tmp_path, **plan_arguments):
    """
    Return a server, the path of the h2o file and the ids of its profile and
    of a plan with `plan_arguments`.
    """
    server, path = h2o_server(tmp_path)

    return server, path, *profile_and_plan(server, path, **plan_arguments)


@pytest.mark.parametrize(
    "plan_arguments, cv_arguments, cost",
    [
        ({"steps": 12}, {}, {"n_folds": 6, "n_fits": 1, "estimator_fits": 1}),
        (
            {"steps": 12},
            {"initial_train_size": 120, "refit": True},
            {"n_folds": 7, "n_fits": 7, "estimator_fits": 7},
        ),
        (
            {"steps": 12},
            {"initial_train_size": "2005-06-01", "refit": 2, "fixed_train_size": True},
            {"n_folds": 3, "n_fits": 2, "estimator_fits": 2},
        ),
        (
            {"steps": 6, "forecaster": "ForecasterDirect"},
            {"refit": True},
            {"n_folds": 11, "n_fits": 11, "estimator_fits": 66},
        ),
        (
            {"steps": 12, "forecaster": "ForecasterStats"},
            {},
            {"n_folds": 6, "n_fits": 6, "estimator_fits": 6},
        ),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_create_cv_output_matches_python_api(
    tmp_path, plan_arguments, cv_arguments, cost
):
    """
    Test that `create_cv` registers the strategy the Python API builds for
    the plan, states its cost (a direct forecaster fits one estimator per
    step, ForecasterStats is refitted in every fold), links it to its profile
    and plan and lists the arguments of `create_cv`; `get_code` returns the
    code of its `TimeSeriesFold`.
    """
    server, path, profile_id, plan_id = _planned(tmp_path, **plan_arguments)

    result = content_of(call(server, "create_cv", {"plan_id": plan_id, **cv_arguments}))
    code = content_of(call(server, "get_code", {"object_id": result["id"]}))

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    plan = assistant.plan(profile=profile, **plan_arguments)
    cv = assistant.create_cv(profile=profile, plan=plan, **cv_arguments)

    assert result["kind"] == "cv"
    assert result["links"] == {"profile_id": profile_id, "plan_id": plan_id}
    assert result["summary"] == cv.describe()
    assert result["cost"] == cost
    assert result["changeable"] == CV_ARGUMENTS
    long = ["LongTrainingWarning"] if cost["estimator_fits"] > 50 else []
    assert [notice["category"] for notice in result["notices"]] == long
    assert code["code"] == cv.code


def test_tool_create_cv_long_training_notice_before_the_backtest(tmp_path):
    """
    Test that a strategy whose backtest fits the estimator more than 50
    times carries, when it is built, the `LongTrainingWarning` that the
    backtest emits later (source 'runtime'), with the same text, while it
    can still change.
    """
    server, path, _, plan_id = _planned(
        tmp_path, steps=6, forecaster="ForecasterDirect"
    )

    result = content_of(call(server, "create_cv", {"plan_id": plan_id, "refit": True}))
    backtest = content_of(call(server, "backtest", {"cv_id": result["id"]}))

    long_notices = [
        notice for notice in backtest["notices"]
        if notice["category"] == "LongTrainingWarning"
    ]
    assert result["notices"] == long_notices
    assert result["notices"][0]["source"] == "runtime"
    assert result["notices"][0]["message"].startswith(
        "ForecasterDirect will be fit 66 times"
    )


def test_tool_create_cv_notices_of_the_runtime(tmp_path):
    """
    Test that the warning about an explicit `refit=False` that does not run
    with ForecasterStats is a notice with source 'runtime'.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12, forecaster="ForecasterStats")

    result = content_of(call(server, "create_cv", {"plan_id": plan_id, "refit": False}))

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(
            source="runtime",
            category="IgnoredArgumentWarning",
            message=(
                "`refit=False` do not apply to ForecasterStats: skforecast refits "
                "it in every fold, so its backtest runs with `refit=True` and "
                "`fixed_train_size=True`. Pass those values to avoid this warning."
            ),
            count=1,
        )
    ]


@pytest.mark.parametrize(
    "arguments, field",
    [
        ({"initial_train_size": "120"}, "initial_train_size"),
        ({"initial_train_size": " 1e2 "}, "initial_train_size"),
        ({"initial_train_size": 1.5}, "initial_train_size"),
        ({"refit": "yes"}, "refit"),
        ({"refit": -1}, "refit"),
        ({"gap": -1}, "gap"),
        ({"fold_stride": 0}, "fold_stride"),
        ({"skip_folds": 0}, "skip_folds"),
        ({"initial_train_size": 0}, "initial_train_size"),
        ({"folds": 3}, "folds"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_create_cv_invalid_argument(tmp_path, arguments, field):
    """
    Test that a number written as text (which the core would read as a
    date), a wrong type, a value out of the bounds of `TimeSeriesFold` and an
    unknown argument are `invalid_argument`.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, **arguments}), "create_cv"
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == field


@pytest.mark.parametrize(
    "arguments",
    [
        {"initial_train_size": 500},
        {"initial_train_size": "2030-01-01"},
        {"gap": 190},
    ],
    ids=["train size beyond the data", "date after the data", "gap too large"],
)
def test_tool_create_cv_invalid_argument_when_skforecast_rejects_the_strategy(
    tmp_path, arguments
):
    """
    Test that a strategy that skforecast rejects (a first training set
    beyond the data, a gap that leaves no fold) reaches the agent as
    `invalid_argument` with the reason, not as an `internal_error` that only
    names the type: the tool reads no rows of the data, and the agent needs
    the reason to correct its arguments. Nothing is registered.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, **arguments}), "create_cv"
    )

    assert error["code"] == "invalid_argument"
    assert error["message"].startswith(
        "The cross-validation strategy cannot be built: "
    )
    assert error["hint"] == (
        "Change the arguments of `create_cv` (or `steps` of the plan with "
        "`refine_plan`) so that at least two folds fit in the data."
    )
    kinds = [o["kind"] for o in content_of(call(server, "list_objects", {}))["objects"]]
    assert kinds == ["plan", "profile"]


def test_tool_create_cv_invalid_argument_message_when_train_size_beyond_data(tmp_path):
    """
    Test the message of a first training set longer than the data: the one
    of skforecast, on one line.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, "initial_train_size": 500}),
        "create_cv",
    )

    assert error["message"] == (
        "The cross-validation strategy cannot be built: The time series must "
        "have more than `initial_train_size + gap` observations to create at "
        "least one fold. Time series length: 204 Required > 500 "
        "initial_train_size: 500 gap: 0"
    )
