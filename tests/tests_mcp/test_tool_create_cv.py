# Unit test tool create_cv

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server
from skforecast_ai.mcp import server as server_module
from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.schemas import CV_OVERRIDE_NAMES

from .fixtures_mcp import (
    call,
    content_of,
    df_h2o_backtest_gaps_csv,
    error_of,
    h2o_server,
    profile_and_plan,
    write_csv,
)

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
    "plan_arguments, cv_arguments, cost, compare_fits",
    [
        ({"steps": 12}, {}, {"n_folds": 6, "n_fits": 1, "estimator_fits": 1}, 19),
        (
            {"steps": 12},
            {"initial_train_size": 120, "refit": True},
            {"n_folds": 7, "n_fits": 7, "estimator_fits": 7},
            98,
        ),
        (
            {"steps": 12},
            {"initial_train_size": "2005-06-01", "refit": 2, "fixed_train_size": True},
            {"n_folds": 3, "n_fits": 2, "estimator_fits": 2},
            29,
        ),
        (
            {"steps": 6, "forecaster": "ForecasterDirect"},
            {"refit": True},
            {"n_folds": 11, "n_fits": 11, "estimator_fits": 66},
            88,
        ),
        (
            {"steps": 12, "forecaster": "ForecasterStats"},
            {},
            {"n_folds": 6, "n_fits": 6, "estimator_fits": 6},
            19,
        ),
        (
            {"steps": 12, "forecaster": "ForecasterFoundation"},
            {},
            {"n_folds": 6, "n_fits": 0, "estimator_fits": 0, "inference_windows": 6},
            19,
        ),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_create_cv_output_matches_python_api(
    tmp_path, monkeypatch, plan_arguments, cv_arguments, cost, compare_fits
):
    """
    Test that `create_cv` registers the strategy the Python API builds for
    the plan, states its cost (a direct forecaster fits one estimator per
    step, ForecasterStats is refitted in every fold), links it to its profile
    and plan and lists the arguments of `create_cv`; `get_code` returns the
    code of its `TimeSeriesFold`. The cost also gives the estimator fits of
    a `compare` without candidates with that strategy (the candidates of the
    profile, each with the fits of the shared strategy), with a notice when
    they exceed both 50 and the fits of the plan. A foundation model costs
    its inference windows (one per series and fold); without its backend,
    `compare` leaves it out, so it adds no windows to the comparison.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
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
    assert result["cost"] == {
        "inference_windows": 0,
        **cost,
        "compare_estimator_fits": compare_fits,
        "compare_inference_windows": 0,
    }
    assert result["changeable"] == CV_ARGUMENTS
    expected = ["LongTrainingWarning"] if cost["estimator_fits"] > 50 else []
    if compare_fits > max(50, cost["estimator_fits"]):
        expected.append("CompareCostNotice")
    assert sorted(notice["category"] for notice in result["notices"]) == sorted(
        expected
    )
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
    built = [n for n in result["notices"] if n["category"] == "LongTrainingWarning"]
    assert built == long_notices
    assert built[0]["source"] == "runtime"
    assert built[0]["message"].startswith("ForecasterDirect will be fit 66 times")


def test_tool_create_cv_notice_of_the_cost_of_a_default_compare(tmp_path):
    """
    Test that a strategy that is cheap for its plan but expensive for a
    `compare` without candidates says so when it is built: with `refit=True`
    the plan fits 7 estimators, while the comparison also runs
    ForecasterDirect, one estimator per step and fold.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    result = content_of(
        call(
            server, "create_cv",
            {"plan_id": plan_id, "initial_train_size": 120, "refit": True},
        )
    )

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(
            source   = "runtime",
            category = "CompareCostNotice",
            message  = (
                "`compare` without `candidates` on this strategy fits about 98 "
                "estimators (ForecasterRecursive: 7, ForecasterDirect: 84, "
                "ForecasterFoundation: 0, ForecasterStats: 7), more than the 7 "
                "of this plan. Pass `candidates` to choose what runs, or use "
                "`refit=false` or fewer folds."
            ),
            count    = 1,
        )
    ]


def test_tool_create_cv_missing_values_notice_with_the_warning_of_the_library(
    tmp_path,
):
    """
    Test that a strategy for a plan whose estimator cannot predict from a
    missing value, on a file with missing months, carries the
    `MissingValuesNotice` of the server (source 'data') first, then the
    `CompareCostNotice` of the same call, and last the warning of the
    library about those values, once each.
    """
    path = write_csv(tmp_path, "gaps.csv", df_h2o_backtest_gaps_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path)

    result = content_of(
        call(
            server, "create_cv",
            {"plan_id": plan_id, "initial_train_size": 60, "refit": True},
        )
    )

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(
            source   = "data",
            category = "MissingValuesNotice",
            message  = (
                "The missing values of the target are data of the user: do "
                "not fill in, drop or write any of them yourself, in their "
                "file or in a copy of it, unless they asked for exactly that. "
                "Ask before you do. Without touching the data, an estimator "
                "that accepts missing values (such as 'LGBMRegressor', with "
                "`refine_plan` and a new `create_cv`) lets `backtest` run on "
                "every fold: if you switch to it, say in your answer that you "
                "changed the estimator and why. If you forecast without a "
                "backtest, say in your answer that the forecast has no "
                "measure of error and why."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "runtime",
            category = "CompareCostNotice",
            message  = (
                "`compare` without `candidates` on this strategy fits about 70 "
                "estimators (ForecasterRecursive: 5, ForecasterDirect: 60, "
                "ForecasterFoundation: 0, ForecasterStats: 5), more than the 5 "
                "of this plan. Pass `candidates` to choose what runs, or use "
                "`refit=false` or fewer folds."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "runtime",
            category = "UserWarning",
            message  = (
                "The target has missing values or missing timestamps "
                "(asfreq() restores them as missing values), and "
                "ForecasterRecursive with Ridge cannot predict from a "
                "missing value: `backtest()` of this plan raises when a test "
                "fold is predicted from one, naming its dates. "
                "`dropna_from_series` only drops them from the training "
                "data. Impute the target, or choose an estimator that "
                "accepts missing values (for example 'LGBMRegressor') to "
                "backtest every fold."
            ),
            count    = 1,
        ),
    ]


def test_tool_create_cv_no_missing_values_notice_when_estimator_accepts_them(
    tmp_path,
):
    """
    Test that the same file with missing months gives no notice, neither
    of the server nor of the library, when the estimator of the plan
    accepts missing values.
    """
    path = write_csv(tmp_path, "gaps.csv", df_h2o_backtest_gaps_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, estimator="LGBMRegressor")

    result = content_of(
        call(server, "create_cv", {"plan_id": plan_id, "initial_train_size": 84})
    )

    assert result["notices"] == []


def test_tool_create_cv_cost_and_notices_of_inference_windows(tmp_path, monkeypatch):
    """
    Test that a `compare` without candidates counts the inference windows
    of its foundation candidate when its backend is installed (one per
    series and fold), and that above the threshold (lowered to 3 here, 2000
    by default) a strategy says so when it is built: a `CompareCostNotice`
    for the plan of another forecaster, and for a foundation plan the
    `LongTrainingWarning` its backtest will emit.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: True,
    )
    monkeypatch.setattr("skforecast_ai.mcp.server.LONG_INFERENCE_WINDOWS", 3)
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 3)
    server, path, profile_id, plan_id = _planned(tmp_path, steps=12)
    foundation = content_of(
        call(
            server, "plan",
            {"profile_id": profile_id, "steps": 12, "forecaster": "ForecasterFoundation"},
        )
    )

    result = content_of(call(server, "create_cv", {"plan_id": plan_id}))
    result_foundation = content_of(
        call(server, "create_cv", {"plan_id": foundation["id"]})
    )

    assert result["cost"]["inference_windows"] == 0
    assert result["cost"]["compare_inference_windows"] == 6
    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(
            source   = "runtime",
            category = "CompareCostNotice",
            message  = (
                "`compare` without `candidates` on this strategy runs "
                "ForecasterFoundation on up to 6 inference windows (1 series x 6 "
                "folds), which can take minutes on a CPU. Pass `candidates` to "
                "choose what runs, or use fewer folds."
            ),
            count    = 1,
        )
    ]
    assert result_foundation["cost"]["inference_windows"] == 6
    assert result_foundation["cost"]["compare_inference_windows"] == 6
    assert [
        (n["category"], n["source"], n["message"].split("\n")[0])
        for n in result_foundation["notices"]
    ] == [
        (
            "LongTrainingWarning",
            "runtime",
            "ForecasterFoundation will forecast up to 6 inference windows (1 series x "
            "6 folds), more than 3. This can take minutes on a CPU. If not "
            "feasible, use a cross-validation strategy with fewer folds (a "
            "later `initial_train_size` or a larger `fold_stride`) or forecast "
            "fewer series.",
        )
    ]


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


def test_tool_create_cv_notice_when_direct_forecaster_with_gap(tmp_path):
    """
    Test that a strategy with a gap for a ForecasterDirect plan is created,
    with a notice (source 'runtime') that its backtest raises, and that
    `backtest` of it is `invalid_argument` on `cv`.
    """
    server, _, _, plan_id = _planned(
        tmp_path, steps=6, forecaster="ForecasterDirect"
    )

    result = content_of(call(server, "create_cv", {"plan_id": plan_id, "gap": 2}))
    error = error_of(call(server, "backtest", {"cv_id": result["id"]}), "backtest")

    assert [
        ToolNotice(**n) for n in result["notices"] if n["category"] == "UserWarning"
    ] == [
        ToolNotice(
            source   = "runtime",
            category = "UserWarning",
            message  = (
                "ForecasterDirect is trained to predict 6 steps, and with "
                "`gap=2` each fold needs steps + gap = 8 steps ahead, so "
                "skforecast would fail: `backtest()` and `backtest_code()` of "
                "this plan with this strategy raise. The strategy can still "
                "serve the candidates of `compare()` that are not direct; use "
                "a strategy without gap to backtest this plan."
            ),
            count    = 1,
        )
    ]
    assert (error["code"], error["field"]) == ("invalid_argument", "cv_id")


def test_tool_create_cv_notice_when_first_window_shorter_than_forecaster(tmp_path):
    """
    Test that the default strategy of `steps=100` on h2o (204 observations),
    whose first training window of 4 observations is shorter than the 36
    the plan reads, is created with a notice (source 'runtime') that its
    backtest raises, and that `backtest` of it is `insufficient_data`.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=100)

    result = content_of(call(server, "create_cv", {"plan_id": plan_id}))
    error = error_of(call(server, "backtest", {"cv_id": result["id"]}), "backtest")

    assert [
        n["message"] for n in result["notices"] if n["category"] == "UserWarning"
    ] == [
        "The first training window of the strategy has 4 observations, and "
        "ForecasterRecursive needs at least 37 (more than its window size, "
        "36), so skforecast would fail: `backtest()` of this plan with this "
        "strategy raises. The strategy can still serve the candidates of "
        "`compare()` with a smaller window; use a later `initial_train_size`, "
        "or a shorter horizon, to backtest this plan."
    ]
    assert error["code"] == "insufficient_data"


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
    "arguments, field",
    [
        ({"initial_train_size": 500}, "initial_train_size"),
        ({"initial_train_size": "2030-01-01"}, "initial_train_size"),
        ({"gap": 190}, "initial_train_size"),
    ],
    ids=["train size beyond the data", "date after the data", "gap too large"],
)
def test_tool_create_cv_invalid_argument_when_skforecast_rejects_the_strategy(
    tmp_path, arguments, field
):
    """
    Test that a strategy that skforecast rejects (a first training set
    beyond the data, a gap that leaves no fold) reaches the agent as
    `invalid_argument` with the reason and the argument its message names
    first (the core wraps the error of skforecast), not as an
    `internal_error` that only names the type: the tool reads no rows of
    the data, and the agent needs the reason to correct its arguments.
    Nothing is registered.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, **arguments}), "create_cv"
    )

    assert error["code"] == "invalid_argument"
    assert error["message"].startswith(
        "The cross-validation strategy cannot be built: "
    )
    assert error["field"] == field
    assert error["hint"] == (
        "Change the arguments of the strategy (`initial_train_size`, "
        "`fold_stride`, `gap`, `skip_folds`) or the `steps` of the plan so "
        "that at least two folds fit in the data."
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


def test_tool_create_cv_inference_windows_with_several_series_and_at_the_threshold(
    tmp_path, monkeypatch
):
    """
    Test that the inference windows of a `compare` without candidates count
    every series (2 series over the 6 folds of the strategy are 12), and
    that the `CompareCostNotice` is given above the threshold, not at it.
    """
    from skforecast_ai.mcp import create_server

    from ..fixtures_assistant import df_multi_wide
    from .fixtures_mcp import write_csv

    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: True,
    )
    path = write_csv(tmp_path, "wide.csv", df_multi_wide)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(
        server, path, target=["series_a", "series_b"], steps=5
    )

    monkeypatch.setattr("skforecast_ai.mcp.server.LONG_INFERENCE_WINDOWS", 12)
    at_threshold = content_of(call(server, "create_cv", {"plan_id": plan_id}))
    monkeypatch.setattr("skforecast_ai.mcp.server.LONG_INFERENCE_WINDOWS", 11)
    above = content_of(call(server, "create_cv", {"plan_id": plan_id}))

    assert at_threshold["cost"]["n_folds"] == 6
    assert at_threshold["cost"]["compare_inference_windows"] == 12
    assert [n["category"] for n in at_threshold["notices"]] == []
    assert [n["category"] for n in above["notices"]] == ["CompareCostNotice"]
    assert "on up to 12 inference windows (2 series x 6 folds)" in (
        above["notices"][0]["message"]
    )


def test_tool_create_cv_arguments_are_the_names_a_strategy_records():
    """
    Test that the arguments of `create_cv` that the server lists as
    changeable are the names a strategy records when the user passes them
    (`CV_OVERRIDE_NAMES`), in the same order.
    """
    assert server_module.CV_ARGUMENTS == CV_OVERRIDE_NAMES
    assert list(server_module.CV_ARGUMENTS) == CV_ARGUMENTS


def test_tool_create_cv_summary_names_the_arguments_passed(tmp_path):
    """
    Test that the summary of a strategy created with `refit=True` says the
    user chose it and ends with the explanation of the defaults, and that
    without arguments it only explains the defaults.
    """
    server, _, _, plan_id = _planned(tmp_path)

    chosen = content_of(call(server, "create_cv", {"plan_id": plan_id, "refit": True}))
    default = content_of(call(server, "create_cv", {"plan_id": plan_id}))

    assert "- Chosen by the user instead of the rules: refit\n" in chosen["summary"]
    assert chosen["summary"].endswith(
        "Initial training size by default: 70% of the 204 observations "
        "(142), up to 2003-04-01. `refit` as requested.\n"
        "</deterministic_summary>\n</forecast_context>"
    )
    assert "Chosen by the user instead of the rules" not in default["summary"]
    assert "Trained once by default" in default["summary"]


def test_tool_create_cv_insufficient_data_with_hint_when_one_fold(tmp_path):
    """
    Test that a strategy that leaves a single fold (the first training set
    ends one horizon before the end of h2o) is `insufficient_data` with a
    hint that says what gives more folds and names `forecast` with
    `test_size` for one window: without it agents tried sizes blindly.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path, steps=24)

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, "initial_train_size": 180}),
        "create_cv",
    )

    assert error["code"] == "insufficient_data"
    assert error["message"].startswith(
        "The resolved CV configuration produces only 1 fold(s). At least 2 "
        "are required."
    )
    assert error["hint"] == (
        "To evaluate a single window, the last `steps` observations, use "
        "`forecast` with `test_size` instead: one hold-out, not a backtest. A "
        "backtest needs at least 2 folds: a smaller `initial_train_size` (or "
        "leave it out for the default), a smaller `fold_stride` or a plan with "
        "fewer `steps`."
    )
