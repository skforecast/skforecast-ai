# Unit test tool create_cv

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server
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
    "plan_arguments, cv_arguments, cost, compare_fits, compare_windows",
    [
        ({"steps": 12}, {}, {"n_folds": 6, "n_fits": 1, "estimator_fits": 1}, 19, 0),
        (
            {"steps": 12},
            {"initial_train_size": 120, "refit": True},
            {"n_folds": 7, "n_fits": 7, "estimator_fits": 7},
            98,
            0,
        ),
        (
            {"steps": 12},
            {"initial_train_size": "2005-06-01", "refit": 2, "fixed_train_size": True},
            {"n_folds": 3, "n_fits": 2, "estimator_fits": 2},
            29,
            0,
        ),
        (
            {"steps": 6, "forecaster": "ForecasterDirect"},
            {"refit": True},
            {"n_folds": 11, "n_fits": 11, "estimator_fits": 66},
            88,
            0,
        ),
        (
            {"steps": 12, "forecaster": "ForecasterStats"},
            {},
            {"n_folds": 6, "n_fits": 6, "estimator_fits": 6},
            19,
            0,
        ),
        (
            {"steps": 12, "forecaster": "ForecasterFoundation"},
            {},
            {"n_folds": 6, "n_fits": 0, "estimator_fits": 0, "inference_windows": 6},
            19,
            6,
        ),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_create_cv_output_matches_python_api(
    tmp_path, monkeypatch, plan_arguments, cv_arguments, cost, compare_fits,
    compare_windows,
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
    `compare` leaves the candidate of the profile out, so it adds no
    windows, unless the strategy was created for a foundation plan, which
    runs as the row of that plan.
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
        "compare_inference_windows": compare_windows,
    }
    assert result["changeable"] == CV_ARGUMENTS
    expected = ["LongTrainingWarning"] if cost["estimator_fits"] > 50 else []
    if compare_fits > max(50, cost["estimator_fits"]):
        expected.append("CompareCostNotice")
    if max(compare_fits, cost["estimator_fits"]) > 50:
        expected.append("CostNotice")
    assert sorted(notice["category"] for notice in result["notices"]) == sorted(
        expected
    )
    assert code["code"] == cv.code


def test_tool_create_cv_cost_is_the_figure_that_confirms_the_backtest(tmp_path):
    """
    Test that a strategy whose backtest fits the estimator more than 50
    times carries, when it is built, the `LongTrainingWarning` with its cost
    (source 'runtime') while it can still change, and that its
    `estimator_fits` is the number `backtest` needs in `confirm_cost`: the
    backtest is refused without it, and runs with it, without the warning.
    """
    server, path, _, plan_id = _planned(
        tmp_path, steps=6, forecaster="ForecasterDirect"
    )

    result = content_of(call(server, "create_cv", {"plan_id": plan_id, "refit": True}))
    refused = error_of(
        call(server, "backtest", {"cv_id": result["id"]}), "backtest"
    )
    backtest = content_of(
        call(
            server, "backtest",
            {"cv_id": result["id"], "confirm_cost": result["cost"]["estimator_fits"]},
        )
    )

    built = [n for n in result["notices"] if n["category"] == "LongTrainingWarning"]
    assert built[0]["source"] == "runtime"
    assert built[0]["message"].startswith("ForecasterDirect will be fit 66 times")
    assert refused["details"]["confirm_cost"] == 66
    assert backtest["cost"]["estimator_fits"] == 66
    assert "LongTrainingWarning" not in [n["category"] for n in backtest["notices"]]


def test_tool_create_cv_cost_notice_when_backtest_above_the_threshold(tmp_path):
    """
    Test that a strategy whose backtest fits the estimator more than 50
    times carries a `CostNotice` of the server (source 'runtime') with the
    rule of an expensive run: stop, tell the number of fits and the cheaper
    strategies, and run only if the user chooses it. It comes before the
    `LongTrainingWarning` of the library, which is not changed.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=6, forecaster="ForecasterDirect")

    result = content_of(call(server, "create_cv", {"plan_id": plan_id, "refit": True}))

    assert result["cost"]["estimator_fits"] == 66
    assert result["cost"]["compare_estimator_fits"] == 88
    assert [n["category"] for n in result["notices"]] == [
        "CostNotice", "CompareCostNotice", "LongTrainingWarning",
    ]
    assert ToolNotice(**result["notices"][0]) == ToolNotice(
        source   = "runtime",
        category = "CostNotice",
        message  = (
            "Expensive run: with this strategy, `backtest` fits 66 estimators; "
            "`compare` without `candidates` fits 88 estimators (an expensive "
            "run is one above 50 estimator fits or 2000 inference windows). Stop "
            "here and do not run it: tell the user those numbers "
            "and the cheaper strategies (for `backtest`, an integer `refit` "
            "(retrain every n folds), fewer folds (a later `initial_train_size`, "
            "a larger `fold_stride` or `skip_folds`) or `refit=false` (train "
            "once); for `compare`, a list of `candidates`, an integer `refit` "
            "(retrain every n folds), fewer folds (a later `initial_train_size` "
            "or a larger `fold_stride`) or `refit=false` (train once)), and run "
            "the expensive one only if they choose it, passing `confirm_cost: "
            "66` to `backtest` or `confirm_cost: 88` to `compare` without "
            "`candidates`: without that number the run is refused. Asking to "
            "retrain the model, or to evaluate it as in production, is not "
            "that choice."
        ),
        count    = 1,
    )


def test_tool_create_cv_no_cost_notice_at_the_threshold(tmp_path, monkeypatch):
    """
    Test that the `CostNotice` is given above the thresholds, not at them:
    with the default strategy of the h2o plan a `compare` without candidates
    fits 19 estimators, so there is a notice with the threshold at 18 and
    none with it at 19.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    for module in ("skforecast_ai.mcp.server", "skforecast_ai._utils"):
        monkeypatch.setattr(f"{module}.LONG_TRAINING_FITS", 19)
    at_threshold = content_of(call(server, "create_cv", {"plan_id": plan_id}))
    for module in ("skforecast_ai.mcp.server", "skforecast_ai._utils"):
        monkeypatch.setattr(f"{module}.LONG_TRAINING_FITS", 18)
    above = content_of(call(server, "create_cv", {"plan_id": plan_id}))

    assert at_threshold["cost"]["compare_estimator_fits"] == 19
    assert [n["category"] for n in at_threshold["notices"]] == []
    assert [n["category"] for n in above["notices"]] == [
        "CostNotice", "CompareCostNotice",
    ]
    assert above["notices"][0]["message"].startswith(
        "Expensive run: with this strategy, `compare` without `candidates` fits "
        "19 estimators (an expensive run is one above 18 estimator fits"
    )
    assert above["notices"][0]["message"].endswith(
        "passing `confirm_cost: 19` to `compare` without `candidates`: without "
        "that number the run is refused. Asking to retrain the model, or to "
        "evaluate it as in production, is not that choice. `backtest` of this "
        "plan is below the thresholds and can run."
    )


def test_tool_create_cv_notice_of_the_cost_of_a_default_compare(
    tmp_path, monkeypatch
):
    """
    Test that a strategy that is cheap for its plan but expensive for a
    `compare` without candidates says so when it is built: with `refit=True`
    the plan fits 7 estimators, while the comparison also runs
    ForecasterDirect, one estimator per step and fold. The notice lists
    the candidates `compare` runs: without its backend, not the foundation
    model.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
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
            category = "CostNotice",
            message  = (
                "Expensive run: with this strategy, `compare` without `candidates` "
                "fits 98 estimators (an expensive run is one above 50 "
                "estimator fits or 2000 inference windows). "
                "Stop here and do not run it: tell the user those numbers and "
                "the cheaper strategies (for `compare`, a list of `candidates`, "
                "an integer `refit` (retrain every n folds), fewer folds (a "
                "later `initial_train_size` or a larger `fold_stride`) or "
                "`refit=false` (train once)), and run the expensive one only "
                "if they choose it, passing `confirm_cost: 98` to `compare` "
                "without `candidates`: without that number the run is refused. "
                "Asking to retrain the model, or to evaluate it as in "
                "production, is not that choice. `backtest` of this plan is "
                "below the thresholds and can run."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "runtime",
            category = "CompareCostNotice",
            message  = (
                "`compare` without `candidates` on this strategy fits 98 "
                "estimators (ForecasterRecursive: 7, ForecasterDirect: 84, "
                "ForecasterStats: 7, Baseline (seasonal naive): 0), more than "
                "the 7 of this plan. Pass `candidates` to choose what runs, or "
                "use an integer `refit` (retrain every n folds), fewer folds (a "
                "later `initial_train_size` or a larger `fold_stride`) or "
                "`refit=false` (train once)."
            ),
            count    = 1,
        )
    ]


def test_tool_create_cv_cost_notice_of_a_stats_plan_names_only_fewer_folds(
    tmp_path, monkeypatch
):
    """
    Test that the `CostNotice` of a ForecasterStats plan, which skforecast
    refits in every fold whatever `refit` says, offers for its backtest only
    fewer folds (without `skip_folds`, which it rejects), never `refit`,
    with `refit` false or true; for a `compare` without candidates it names
    `refit` only when the strategy refits, since only then does `refit`
    lower the cost of the other candidates.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
    server, _, _, plan_id = _planned(tmp_path, steps=1, forecaster="ForecasterStats")
    arguments = {"plan_id": plan_id, "initial_train_size": 150, "fold_stride": 1}

    once = content_of(call(server, "create_cv", arguments))
    refits = content_of(call(server, "create_cv", {**arguments, "refit": True}))

    assert once["cost"]["estimator_fits"] == refits["cost"]["estimator_fits"] == 54
    assert once["cost"]["compare_estimator_fits"] == 56
    assert refits["cost"]["compare_estimator_fits"] == 162
    assert once["notices"][0] == {
        "source": "runtime",
        "category": "CostNotice",
        "message": (
            "Expensive run: with this strategy, `backtest` fits 54 estimators; "
            "`compare` without `candidates` fits 56 estimators (an "
            "expensive run is one above 50 estimator fits or 2000 inference "
            "windows). Stop here and do not run it: tell the user those "
            "numbers and the cheaper strategies (for `backtest`, fewer folds "
            "(a later `initial_train_size` or a larger `fold_stride`); for "
            "`compare`, a list of `candidates` or fewer folds (a later "
            "`initial_train_size` or a larger `fold_stride`)), and run the "
            "expensive one only if they choose it, passing `confirm_cost: 54` "
            "to `backtest` or `confirm_cost: 56` to `compare` without "
            "`candidates`: without that number the run is refused. Asking to "
            "retrain the model, or to evaluate it as in production, is not "
            "that choice."
        ),
        "count": 1,
    }
    assert once["notices"][1]["message"] == (
        "`compare` without `candidates` on this strategy fits 56 "
        "estimators (ForecasterRecursive: 1, ForecasterDirect: 1, "
        "ForecasterStats: 54, Baseline (seasonal naive): 0), more than the 54 "
        "of this plan. Pass `candidates` to choose what runs, or use fewer "
        "folds (a later `initial_train_size` or a larger `fold_stride`)."
    )
    assert refits["notices"][0]["message"] == (
        "Expensive run: with this strategy, `backtest` fits 54 estimators; "
        "`compare` without `candidates` fits 162 estimators (an "
        "expensive run is one above 50 estimator fits or 2000 inference "
        "windows). Stop here and do not run it: tell the user those numbers "
        "and the cheaper strategies (for `backtest`, fewer folds (a later "
        "`initial_train_size` or a larger `fold_stride`); for `compare`, a "
        "list of `candidates`, an integer `refit` (retrain every n folds), "
        "fewer folds (a later `initial_train_size` or a larger `fold_stride`) "
        "or `refit=false` (train once)), and run the expensive one only if "
        "they choose it, passing `confirm_cost: 54` to `backtest` or "
        "`confirm_cost: 162` to `compare` without `candidates`: without that "
        "number the run is refused. Asking to retrain the model, or to "
        "evaluate it as in production, is not that choice."
    )


def test_tool_create_cv_missing_values_notice_with_the_warning_of_the_library(
    tmp_path, monkeypatch
):
    """
    Test that a strategy for a plan whose estimator cannot predict from a
    missing value, on a file with missing months, carries the
    `MissingValuesNotice` of the server (source 'data') after the
    `CostNotice`, then the `CompareCostNotice` of the same call, and last
    the warning of the library about those values, once each.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
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
            source   = "runtime",
            category = "CostNotice",
            message  = (
                "Expensive run: with this strategy, `compare` without `candidates` "
                "fits 70 estimators (an expensive run is one above 50 "
                "estimator fits or 2000 inference windows). "
                "Stop here and do not run it: tell the user those numbers and "
                "the cheaper strategies (for `compare`, a list of `candidates`, "
                "an integer `refit` (retrain every n folds), fewer folds (a "
                "later `initial_train_size` or a larger `fold_stride`) or "
                "`refit=false` (train once)), and run the expensive one only "
                "if they choose it, passing `confirm_cost: 70` to `compare` "
                "without `candidates`: without that number the run is refused. "
                "Asking to retrain the model, or to evaluate it as in "
                "production, is not that choice. `backtest` of this plan is "
                "below the thresholds and can run."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "data",
            category = "MissingValuesNotice",
            message  = (
                "The missing values of the target are data of the user: do not fill "
                "in, drop or write any of them yourself, in their file or in a copy "
                "of it, unless they asked for exactly that. Ask before you do. "
                "`backtest` checks every test fold before running anything and names "
                "the dates that make it fail: run it before changing the plan or "
                "asking the user about the values. Without touching the data, "
                "switching with `refine_plan` and a new `create_cv` to an estimator "
                "that accepts missing values (such as 'RandomForestRegressor') "
                "avoids the error of a fold predicted from a missing value, not of a "
                "fold that holds one: if you switch to it, say in your answer that "
                "you changed the estimator and why. If you forecast without a "
                "backtest, say in your answer that the forecast has no measure of "
                "error and why."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "runtime",
            category = "CompareCostNotice",
            message  = (
                "`compare` without `candidates` on this strategy fits 70 "
                "estimators (ForecasterRecursive: 5, ForecasterDirect: 60, "
                "ForecasterStats: 5), more than "
                "the 5 of this plan. Pass `candidates` to choose what runs, or "
                "use an integer `refit` (retrain every n folds), fewer folds (a "
                "later `initial_train_size` or a larger `fold_stride`) or "
                "`refit=false` (train once)."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "runtime",
            category = "UserWarning",
            message  = (
                "The target has missing timestamps (asfreq() restores them as "
                "missing values), and `backtest()` checks every test fold before "
                "running: it raises, naming the dates, when a test fold holds one, "
                "whatever the estimator, since no metric is computed on it; and when "
                "a test fold is predicted from one, since ForecasterRecursive with "
                "Ridge cannot predict from a missing value. `dropna_from_series` "
                "only drops the training rows that read one, and a training window "
                "left without rows raises too. An estimator that accepts missing "
                "values (such as 'RandomForestRegressor') avoids the error of a fold "
                "predicted from a missing value, not of a fold that holds one. "
                "Impute the target to backtest every fold."
            ),
            count    = 1,
        ),
    ]


def test_tool_create_cv_missing_values_notice_without_estimator_when_estimator_accepts_them(
    tmp_path,
):
    """
    Test that the same file with missing months, with an estimator that
    accepts missing values, still gives the notice of the server and the
    warning of the library: a missing value inside a test fold fails with
    any estimator. Neither offers another estimator (V16: the notice of
    0.4 promised that LGBMRegressor let every fold run).
    """
    path = write_csv(tmp_path, "gaps.csv", df_h2o_backtest_gaps_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, estimator="LGBMRegressor")

    result = content_of(
        call(server, "create_cv", {"plan_id": plan_id, "initial_train_size": 84})
    )

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(
            source   = "data",
            category = "MissingValuesNotice",
            message  = (
                "The missing values of the target are data of the user: do "
                "not fill in, drop or write any of them yourself, in their "
                "file or in a copy of it, unless they asked for exactly that. "
                "Ask before you do. `backtest` checks every test fold before "
                "running anything and names the dates that make it fail: run "
                "it before changing the plan or asking the user about the "
                "values. If you forecast without a backtest, say in your "
                "answer that the forecast has no measure of error and why."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "runtime",
            category = "UserWarning",
            message  = (
                "The target has missing timestamps (asfreq() restores them as "
                "missing values), and `backtest()` checks every test fold before "
                "running: it raises, naming the dates, when a test fold holds one, "
                "whatever the estimator, since no metric is computed on it. Impute "
                "the target to backtest every fold."
            ),
            count    = 1,
        ),
    ]


def test_tool_create_cv_cost_and_notices_of_inference_windows(tmp_path, monkeypatch):
    """
    Test that a `compare` without candidates counts the inference windows
    of its foundation candidate when its backend is installed (one per
    series and fold), and that above the threshold (lowered to 3 here, 2000
    by default) a strategy says so when it is built: a `CostNotice` and a
    `CompareCostNotice` for the plan of another forecaster, and for a
    foundation plan the `CostNotice` and the `LongTrainingWarning` its
    backtest will emit.
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
            category = "CostNotice",
            message  = (
                "Expensive run: with this strategy, `compare` without `candidates` "
                "runs up to 6 inference windows (an expensive run is one above "
                "50 estimator fits or 3 inference windows). "
                "Stop here and do not run it: tell the user those numbers and "
                "the cheaper strategies (for `compare`, a list of `candidates`, "
                "fewer folds (a later `initial_train_size` or a larger "
                "`fold_stride`) or fewer series), and run the expensive one "
                "only if they choose it, passing `confirm_cost: 6` to `compare` "
                "without `candidates`: without that number the run is refused. "
                "Asking to retrain the model, or to evaluate it as in "
                "production, is not that choice. `backtest` of this plan is "
                "below the thresholds and can run."
            ),
            count    = 1,
        ),
        ToolNotice(
            source   = "runtime",
            category = "CompareCostNotice",
            message  = (
                "`compare` without `candidates` on this strategy runs "
                "ForecasterFoundation on up to 6 inference windows (1 series x 6 "
                "folds), which can take minutes on a CPU. Pass `candidates` to "
                "choose what runs, or use fewer folds (a later "
                "`initial_train_size` or a larger `fold_stride`) or fewer "
                "series."
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
            "CostNotice",
            "runtime",
            "Expensive run: with this strategy, `backtest` runs up to 6 inference "
            "windows; `compare` without `candidates` runs up to 6 inference "
            "windows (an expensive run is one above 50 estimator fits or 3 "
            "inference windows). Stop here and do not run it: tell the user "
            "those numbers and the cheaper strategies (for `backtest`, fewer "
            "folds (a later `initial_train_size`, a larger `fold_stride` or "
            "`skip_folds`) or fewer series; for `compare`, a list of "
            "`candidates`, fewer folds (a later `initial_train_size` or a "
            "larger `fold_stride`) or fewer series), and run the expensive one "
            "only if they choose it, passing `confirm_cost: 6` to `backtest` "
            "or `confirm_cost: 6` to `compare` without `candidates`: without "
            "that number the run is refused. Asking to retrain the model, or "
            "to evaluate it as in production, is not that choice.",
        ),
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
    that the `CostNotice` and the `CompareCostNotice` are given above the
    threshold, not at it.
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
    assert [n["category"] for n in above["notices"]] == [
        "CostNotice", "CompareCostNotice",
    ]
    assert "on up to 12 inference windows (2 series x 6 folds)" in (
        above["notices"][1]["message"]
    )


def test_tool_create_cv_arguments_are_the_names_a_strategy_records(tmp_path):
    """
    Test that the arguments of `create_cv` that the server lists as
    changeable are the names a strategy records when the user passes them
    (`CV_OVERRIDE_NAMES`), in the same order.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    result = content_of(call(server, "create_cv", {"plan_id": plan_id}))

    assert result["changeable"] == list(CV_OVERRIDE_NAMES)
    assert list(CV_OVERRIDE_NAMES) == CV_ARGUMENTS


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


def test_tool_create_cv_counts_the_strategy_plan_in_the_cost_of_a_default_compare(
    tmp_path, monkeypatch
):
    """
    Test that for the strategy of a refined plan the cost of a `compare`
    without `candidates` includes the row 'Strategy plan' that `compare`
    adds (Ridge 1, ForecasterDirect 12, ForecasterStats 6, the plan 1 and
    the baseline 0), without the foundation model whose backend is missing,
    and that the `CompareCostNotice` lists the fits by the name of the row
    and names only fewer folds: the strategy trains once, so `refit` lowers
    nothing, and `skip_folds` would make ForecasterStats fail.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
    monkeypatch.setattr("skforecast_ai.mcp.server.LONG_TRAINING_FITS", 19)
    server, _, _, plan_id = _planned(tmp_path, steps=12)
    refined_id = content_of(
        call(
            server,
            "refine_plan",
            {
                "plan_id": plan_id,
                "overrides": {"estimator": "LGBMRegressor", "lags": [1, 2, 3, 12]},
            },
        )
    )["id"]

    result = content_of(call(server, "create_cv", {"plan_id": refined_id}))

    assert result["cost"]["estimator_fits"] == 1
    assert result["cost"]["compare_estimator_fits"] == 20
    assert result["cost"]["compare_inference_windows"] == 0
    assert [ToolNotice(**n) for n in result["notices"]][-1] == ToolNotice(
        source   = "runtime",
        category = "CompareCostNotice",
        message  = (
            "`compare` without `candidates` on this strategy fits 20 "
            "estimators (ForecasterRecursive: 1, ForecasterDirect: 12, "
            "ForecasterStats: 6, Strategy plan: 1, Baseline (seasonal naive): "
            "0), more than the 1 of this plan. Pass `candidates` to choose what "
            "runs, or use fewer folds (a later `initial_train_size` or a larger "
            "`fold_stride`)."
        ),
        count    = 1,
    )


def test_tool_create_cv_counts_the_strategy_plan_over_the_budget_of_compare(
    tmp_path, monkeypatch
):
    """
    Test that the plan of the strategy counts in the cost of a default
    `compare` even when it is above the budget of `compare()`, which leaves
    out the automatic ForecasterDirect (7 trainings x 12 estimators = 84
    fits, above a budget patched to 50) but not the plan of the strategy
    (a direct forecaster with other lags).
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
    monkeypatch.setattr("skforecast_ai.execution.comparison.COMPARE_FIT_BUDGET", 50)
    server, _, _, plan_id = _planned(
        tmp_path, steps=12, forecaster="ForecasterDirect", lags=3
    )

    result = content_of(
        call(
            server, "create_cv",
            {"plan_id": plan_id, "initial_train_size": 120, "refit": True},
        )
    )

    assert result["cost"]["estimator_fits"] == 84
    assert result["cost"]["compare_estimator_fits"] == 98
    notice = [n for n in result["notices"] if n["category"] == "CompareCostNotice"][0]
    assert notice["message"] == (
        "`compare` without `candidates` on this strategy fits 98 "
        "estimators (ForecasterRecursive: 7, ForecasterStats: 7, Strategy "
        "plan: 84, Baseline (seasonal naive): 0), more than the 84 of this "
        "plan. Pass `candidates` to choose what runs, or use an integer "
        "`refit` (retrain every n folds), fewer folds (a later "
        "`initial_train_size` or a larger `fold_stride`) or `refit=false` "
        "(train once)."
    )


def test_tool_create_cv_notice_of_few_residuals_of_a_series_that_starts_later(
    tmp_path,
):
    """
    Test that a strategy for a multi-series plan with an interval, on long
    data whose series 'b' starts 20 months later, is created with a notice
    (source 'runtime') that names 'b', the only series whose first training
    window leaves fewer than 100 rows for its residuals, counted on its own
    observations.
    """
    from ..fixtures_datasets import df_h2o_long

    path = write_csv(
        tmp_path, "staggered.csv", df_h2o_long.drop(index=df_h2o_long.index[204:224])
    )
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    profile = content_of(
        call(
            server,
            "profile",
            {
                "data_path": path,
                "target": "x",
                "series_id_column": "series",
                "date_column": "date",
            },
        )
    )
    plan = content_of(
        call(
            server,
            "plan",
            {"profile_id": profile["id"], "steps": 1, "interval": [0.025, 0.975]},
        )
    )

    result = content_of(
        call(
            server,
            "create_cv",
            {"plan_id": plan["id"], "initial_train_size": 140, "fold_stride": 1},
        )
    )

    assert [
        ToolNotice(**n) for n in result["notices"] if n["category"] == "UserWarning"
    ] == [
        ToolNotice(
            source   = "runtime",
            category = "UserWarning",
            message  = (
                "The first training window of the strategy leaves fewer than "
                "100 rows to train on in 1 of the 2 series ('b': 84 row(s) of "
                "120 observations), for a window size of 36. skforecast "
                "estimates the prediction intervals of each series from the "
                "residuals of its own rows, spread over up to 10 bins, and "
                "below 10 residuals per bin (100 rows) the intervals tend to "
                "be too narrow; with a single residual in a bin the lower bound "
                "equals the upper one. Read the intervals of those series with "
                "caution, or use a later `initial_train_size`, or fewer lags or "
                "smaller window features."
            ),
            count    = 1,
        )
    ]


@pytest.mark.parametrize(
    "fixed_train_size, refit, shown",
    [
        (True, None, "null"),
        (False, None, "null"),
        (True, False, "false"),
        (False, False, "false"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_create_cv_invalid_argument_when_fixed_train_size_without_refit(
    tmp_path, fixed_train_size, refit, shown
):
    """
    Test that a `fixed_train_size` (true or false) with `refit` null or false
    for a plan that is not ForecasterStats is `invalid_argument` on
    `fixed_train_size`, with a message that names the `refit` it got and a
    hint that says how to refit or to leave it out, and that nothing is
    registered.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    error = error_of(
        call(
            server, "create_cv",
            {"plan_id": plan_id, "fixed_train_size": fixed_train_size, "refit": refit},
        ),
        "create_cv",
    )

    kinds = [o["kind"] for o in content_of(call(server, "list_objects", {}))["objects"]]
    assert (error["code"], error["field"]) == ("invalid_argument", "fixed_train_size")
    assert error["message"] == (
        f"`fixed_train_size` has no effect with `refit` {shown}: "
        f"ForecasterRecursive is not refitted between folds, so there is no "
        f"training window to keep or grow."
    )
    assert error["hint"] == (
        "Pass `refit: true` (or an integer) to refit it, with a fixed (true) or "
        "growing (false) window, or leave `fixed_train_size` out."
    )
    assert kinds == ["plan", "profile"]


@pytest.mark.parametrize(
    "plan_arguments, cv_arguments",
    [
        ({"steps": 12}, {"fixed_train_size": True, "refit": True}),
        ({"steps": 12}, {"fixed_train_size": False, "refit": True}),
        ({"steps": 12}, {"fixed_train_size": True, "refit": 2}),
        ({"steps": 12}, {"fixed_train_size": False, "refit": 2}),
        ({"steps": 12}, {"refit": False}),
        ({"steps": 12, "forecaster": "ForecasterStats"}, {"fixed_train_size": True}),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_create_cv_fixed_train_size_accepted_when_refit_or_stats(
    tmp_path, plan_arguments, cv_arguments
):
    """
    Test that `fixed_train_size` is accepted when the strategy refits (`refit`
    true or an integer, with a fixed or a growing window) and for a
    ForecasterStats plan with `refit` null, which skforecast refits in every
    fold, and that a strategy without `fixed_train_size` is not affected by
    `refit` false.
    """
    server, _, _, plan_id = _planned(tmp_path, **plan_arguments)

    result = content_of(
        call(server, "create_cv", {"plan_id": plan_id, **cv_arguments})
    )

    assert result["kind"] == "cv"
    assert result["links"]["plan_id"] == plan_id


@pytest.mark.parametrize(
    "skip_folds, shown",
    [(2, "2"), ([], "[]"), ([1, 3], "[1, 3]")],
    ids=lambda dt: f"{dt}",
)
def test_tool_create_cv_invalid_argument_when_skip_folds_of_a_stats_plan(
    tmp_path, skip_folds, shown
):
    """
    Test that any `skip_folds` (an integer, an empty list or a list of folds)
    for a ForecasterStats plan, which skforecast refits in every fold and
    rejects it for, is `invalid_argument` on `skip_folds`, with a hint that
    names the ways to run fewer folds, and that nothing is registered.
    """
    server, _, _, plan_id = _planned(tmp_path, steps=12, forecaster="ForecasterStats")

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, "skip_folds": skip_folds}),
        "create_cv",
    )

    kinds = [o["kind"] for o in content_of(call(server, "list_objects", {}))["objects"]]
    assert (error["code"], error["field"]) == ("invalid_argument", "skip_folds")
    assert error["message"] == (
        f"`skip_folds={shown}` is not allowed for ForecasterStats: skforecast "
        f"refits it in every fold and rejects any `skip_folds`, an empty list "
        f"included. Leave `skip_folds` out to backtest this plan."
    )
    assert error["hint"] == (
        "For fewer folds, use a later `initial_train_size` or a larger "
        "`fold_stride`."
    )
    assert kinds == ["plan", "profile"]


def test_tool_create_cv_compare_cost_leaves_stats_out_when_skip_folds(
    tmp_path, monkeypatch
):
    """
    Test that the cost of a `compare` without candidates on a strategy with
    `skip_folds` of a recursive plan does not count ForecasterStats, which
    the profile of h2o lists as a candidate and skforecast would reject: the
    default strategy (6 folds) fits Ridge 1, ForecasterDirect 12 and
    ForecasterStats 6 estimators, and with `skip_folds=2` (folds 0, 2 and 4)
    only the first two.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
    server, _, _, plan_id = _planned(tmp_path, steps=12)

    without = content_of(call(server, "create_cv", {"plan_id": plan_id}))
    skipping = content_of(call(server, "create_cv", {"plan_id": plan_id, "skip_folds": 2}))

    assert without["cost"]["compare_estimator_fits"] == 19
    assert skipping["cost"]["n_folds"] == 3
    assert skipping["cost"]["compare_estimator_fits"] == 13
