# Unit test tool backtest

import time

import pandas as pd

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import _runtime, create_server

from .fixtures_mcp import (
    call,
    content_of,
    cv_of,
    df_data_warning,
    df_h2o_csv,
    error_of,
    h2o_server,
    profile_and_plan,
    run_session,
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
    assert result["cost"] == {
        "n_folds": 6, "n_fits": 6, "estimator_fits": 6, "inference_windows": 0
    }
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
    `get_failure` returns. The error names only the type of what failed (its
    message, of scikit-learn here, may quote a value), and the traceback of
    `get_failure` has no absolute path.
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
    assert error["message"] == (
        "The generated script failed with InvalidParameterError. Its message, "
        "the traceback and the code that ran are in `get_failure`, with the "
        "`failure_id` of `details`."
    )
    assert failure["id"] == error["details"]["failure_id"]
    assert failure["text"].startswith("Error executing generated forecasting code.")
    assert "Traceback:\n" in failure["text"]
    assert "'no-such-solver'" in failure["text"].split("Code that ran:\n")[1]
    traceback_text = failure["text"].split("Traceback:\n")[1].split("Code that ran")[0]
    assert 'File "sklearn/' in traceback_text
    assert 'File "/' not in traceback_text
    assert "site-packages" not in traceback_text


def test_tool_backtest_heartbeat_progress_while_it_runs(tmp_path, monkeypatch):
    """
    Test that a backtest that runs for longer than the heartbeat sends
    growing progress notifications naming its forecaster and the seconds it
    has run, so a client does not end the request, and still returns its
    result.
    """
    monkeypatch.setattr(_runtime, "HEARTBEAT_SECONDS", 0.05)
    backtest = ForecastingAssistant.backtest

    def slow_backtest(self, *args, **kwargs):
        time.sleep(0.4)
        return backtest(self, *args, **kwargs)

    monkeypatch.setattr(ForecastingAssistant, "backtest", slow_backtest)
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    events = []

    async def steps(client):
        async def record(progress, total, message):
            events.append((progress, total, message))

        return await client.call_tool(
            "backtest", {"cv_id": cv_id}, progress_callback=record
        )

    result = content_of(run_session(server, steps))

    assert result["kind"] == "backtest"
    assert len(events) >= 3
    values = [progress for progress, _, _ in events]
    assert values == sorted(set(values))
    assert all(0 < progress < 1 for progress in values)
    assert events[0][1:] == (None, "ForecasterRecursive: running (0 s)")


def test_tool_backtest_missing_dependency_of_a_foundation_model(
    tmp_path, monkeypatch
):
    """
    Test that backtesting a ForecasterFoundation plan whose backend is not
    installed is `missing_dependency` before any script runs (it was
    `execution_failed` after the script failed), with one install advice;
    `forecast` checks the same.
    """
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )
    server, path = h2o_server(tmp_path)
    _, plan_id, cv_id = cv_of(server, path, forecaster="ForecasterFoundation")

    error = error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")
    forecast = error_of(call(server, "forecast", {"plan_id": plan_id}), "forecast")

    assert error == {
        "code": "missing_dependency",
        "message": (
            "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
            "which is not installed where the server runs. Nothing was run."
        ),
        "field": "plan_id",
        "hint": (
            'Ask the user to install it where the server runs and to restart the '
            'server: `pip install "chronos-forecasting"` in its Python '
            'environment, or `--with "chronos-forecasting"` added to the uvx '
            'command that starts it.'
        ),
        "details": {
            "model_id": "autogluon/chronos-2-small",
            "package": "chronos-forecasting",
        },
    }
    assert (forecast["code"], forecast["field"]) == ("missing_dependency", "plan_id")


def test_tool_backtest_differentiation_of_the_plan_and_of_the_strategy(tmp_path):
    """
    Test that a plan with `differentiation` backtests on a strategy created
    from it, as the Python API does, and that backtesting it on a strategy
    with another order is an `invalid_argument` naming `cv_id`.
    """
    server, path = h2o_server(tmp_path)
    profile_id, _, cv_id = cv_of(server, path)
    _, _, diff_cv_id = cv_of(server, path, differentiation=1)
    diff_plan = content_of(call(server, "plan", {
        "profile_id": profile_id, "steps": 12, "differentiation": 1,
    }))

    result = content_of(call(server, "backtest", {"cv_id": diff_cv_id}))
    error = error_of(
        call(server, "backtest", {"cv_id": cv_id, "plan_id": diff_plan["id"]}),
        "backtest",
    )

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    plan = assistant.plan(profile=profile, steps=12, differentiation=1)
    expected = assistant.backtest(
        data=path, cv=assistant.create_cv(profile=profile, plan=plan),
        profile=profile, show_progress=False,
    )

    assert result["summary"] == expected.describe()
    assert (error["code"], error["field"]) == ("invalid_argument", "cv_id")


def test_tool_backtest_output_when_csv_dates_in_utc(tmp_path):
    """
    Test that a CSV whose dates are written in UTC is backtested with the
    default strategy of `create_cv`, whose date has no time zone: the
    script gets its number of observations instead of failing on it.
    """
    frame = df_h2o_csv.assign(
        fecha=pd.to_datetime(df_h2o_csv["fecha"]).dt.tz_localize("UTC")
    )
    path = write_csv(tmp_path, "utc.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    profile_id = content_of(
        call(server, "profile", {"data_path": path, "target": "x"})
    )["id"]
    plan_id = content_of(
        call(server, "plan", {"profile_id": profile_id, "steps": 12})
    )["id"]
    cv_id = content_of(call(server, "create_cv", {"plan_id": plan_id}))["id"]

    result = content_of(call(server, "backtest", {"cv_id": cv_id}))
    code = content_of(call(server, "get_code", {"object_id": result["id"]}))

    assert result["kind"] == "backtest"
    assert "    initial_train_size = 142,\n" in code["code"]
