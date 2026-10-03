# Unit test tool backtest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server

from .fixtures_mcp import (
    call,
    content_of,
    cv_of,
    df_data_warning,
    error_of,
    h2o_server,
    profile_and_plan,
    text_of,
    write_csv,
)


def test_tool_backtest_output_matches_python_api(tmp_path):
    """
    Test that `backtest` runs the plan of the strategy as the Python API
    does: same summary, predictions and metrics (written to CSV files, not
    sent), cost, links and script.
    """
    server, path = h2o_server(tmp_path)
    profile_id, plan_id, cv_id = cv_of(server, path, cv_arguments={"refit": True})

    result = content_of(call(server, "backtest", {"cv_id": cv_id}))
    code = content_of(call(server, "get_code", {"object_id": result["id"]}))["code"]

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    plan = assistant.plan(profile=profile, steps=12)
    cv = assistant.create_cv(profile=profile, plan=plan, refit=True)
    expected = assistant.backtest(
        data=path, cv=cv, profile=profile, plan=plan, show_progress=False
    )

    assert result["kind"] == "backtest"
    assert result["links"] == {
        "profile_id": profile_id,
        "plan_id": plan_id,
        "cv_id": cv_id,
    }
    assert result["summary"] == expected.describe()
    assert result["cost"] == {"n_folds": 6, "n_fits": 6, "estimator_fits": 6}
    assert result["values_included"] is False
    assert sorted(result["files"]) == ["metrics", "predictions"]
    assert text_of(result["files"]["predictions"]) == expected.predictions.to_csv()
    assert text_of(result["files"]["metrics"]) == expected.metrics.to_csv()
    assert code == expected.code


def test_tool_backtest_another_plan_of_the_same_profile(tmp_path):
    """
    Test that `plan_id` backtests another plan of the same profile on the
    folds of the strategy, as the Python API does, and that a plan of
    another profile is `inconsistent_ids`.
    """
    server, path = h2o_server(tmp_path)
    profile_id, _, cv_id = cv_of(server, path)
    other = content_of(
        call(server, "plan", {"profile_id": profile_id, "steps": 12, "lags": 3})
    )
    _, foreign_plan_id = profile_and_plan(server, path)

    result = content_of(
        call(server, "backtest", {"cv_id": cv_id, "plan_id": other["id"]})
    )
    error = error_of(
        call(server, "backtest", {"cv_id": cv_id, "plan_id": foreign_plan_id}),
        "backtest",
    )

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    cv = assistant.create_cv(
        profile=profile, plan=assistant.plan(profile=profile, steps=12)
    )
    expected = assistant.backtest(
        data=path,
        cv=cv,
        profile=profile,
        show_progress=False,
        plan=assistant.plan(profile=profile, steps=12, lags=3),
    )

    assert result["links"] == {
        "profile_id": profile_id,
        "plan_id": other["id"],
        "cv_id": cv_id,
    }
    assert result["summary"] == expected.describe()
    assert error["code"] == "inconsistent_ids"
    assert error["field"] == "plan_id"
    assert error["details"] == {"plan_id": foreign_plan_id, "cv_id": cv_id}


def test_tool_backtest_does_not_repeat_the_warnings_of_the_profile(tmp_path):
    """
    Test that the warning about the date column emitted when the data was
    profiled is not repeated by the backtest, which reads the data with the
    date column of the profile.
    """
    path = write_csv(tmp_path, "warning.csv", df_data_warning)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, _, cv_id = cv_of(
        server, path, target="y", steps=7, forecaster="ForecasterEquivalentDate"
    )

    result = content_of(call(server, "backtest", {"cv_id": cv_id}))

    assert result["notices"] == []


def test_tool_backtest_data_changed_since_profiled(tmp_path):
    """
    Test that a file that changed since it was profiled is `data_changed`
    before anything runs, and that nothing is registered.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    with open(path, "a") as handle:
        handle.write("2008-07-01,0.5\n")

    error = error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")
    kinds = [o["kind"] for o in content_of(call(server, "list_objects", {}))["objects"]]

    assert error["code"] == "data_changed"
    assert error["field"] == "data_path"
    assert error["message"] == (
        f"The file {path!r} changed since it was profiled, so its profile and "
        f"the objects built from it no longer describe it. Nothing was run."
    )
    assert "backtest" not in kinds


def test_tool_backtest_execution_failed_keeps_the_failure(tmp_path):
    """
    Test that a script that fails while it runs is `execution_failed`, with
    the id of its failure in the details, whose traceback and code
    `get_failure` returns.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(
        server,
        path,
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        estimator_kwargs={"solver": "no-such-solver"},
    )

    error = error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")
    failure = content_of(
        call(server, "get_failure", {"object_id": error["details"]["failure_id"]})
    )

    assert error["code"] == "execution_failed"
    assert error["message"].startswith("Error executing generated forecasting code.")
    assert failure["id"] == error["details"]["failure_id"]
    assert failure["text"].startswith("Error executing generated forecasting code.")
    assert "Traceback:\n" in failure["text"]
    assert "'no-such-solver'" in failure["text"].split("Code that ran:\n")[1]
