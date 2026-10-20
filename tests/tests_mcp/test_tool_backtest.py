# Unit test tool backtest

import time

import pandas as pd

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import _runtime, create_server
from skforecast_ai.mcp.models import ToolNotice

from ..fixtures_assistant import df_crossing_zero, df_multi_long_numeric_ids
from ..fixtures_datasets import df_items_sales_long
from .fixtures_mcp import (
    DATA_VALUES_HINT,
    call,
    content_of,
    csv_of,
    cv_of,
    df_data_warning,
    df_h2o_backtest_gaps_csv,
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
    sent), cost, links and script. Its metrics include MASE, so a notice
    gives the reference it is scaled by, which the summary does not.
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
    assert text_of(result["files"]["predictions"]) == csv_of(expected.predictions)
    assert text_of(result["files"]["metrics"]) == csv_of(expected.metrics)
    assert code == expected.code
    assert [(n["source"], n["category"]) for n in result["notices"]] == [
        ("runtime", "MetricReferenceNotice"), ("runtime", "MetricUnitNotice")
    ]
    assert result["notices"][0]["message"].startswith(
        "`mean_absolute_scaled_error` divides the error by that of the "
        "one-step naive forecast (repeat the previous value) on the training "
        "data"
    )


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

    assert [n["category"] for n in result["notices"]] == ["MetricReferenceNotice"]


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


def test_tool_backtest_summary_names_the_arguments_passed_to_the_strategy(tmp_path):
    """
    Test that `backtest` hands the whole strategy to the assistant: the
    summary of a strategy created with `refit=True` says the user chose it
    and ends with the explanation of the defaults, as in the Python API,
    and the summary of a strategy without arguments explains the defaults.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path, cv_arguments={"refit": True})
    _, _, default_cv_id = cv_of(server, path)

    chosen = content_of(call(server, "backtest", {"cv_id": cv_id}))
    default = content_of(call(server, "backtest", {"cv_id": default_cv_id}))

    assert "- Chosen by the user instead of the rules: refit\n" in chosen["summary"]
    assert (
        " Initial training size by default: 70% of the 204 observations "
        "(142), up to 2003-04-01. `refit` as requested.\n"
        "</deterministic_summary>"
    ) in chosen["summary"]
    assert "Chosen by the user instead of the rules" not in default["summary"]
    assert (
        "Trained once by default: refitting in every fold would multiply the "
        "training cost by the 6 folds."
    ) in default["summary"]


def test_tool_backtest_invalid_argument_when_lag_reads_missing_month(tmp_path):
    """
    Test that a CSV with missing months, one of them read by a lag to predict
    a test fold, gets a notice from `create_cv` (source 'runtime') and a
    `backtest` that is `invalid_argument` on `data_path` (the argument that
    holds the data; not `execution_failed`), whose message names the date,
    while `forecast` of the plan works.
    """
    path = write_csv(tmp_path, "gaps.csv", df_h2o_backtest_gaps_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id, cv_id = cv_of(
        server, path, cv_arguments={"initial_train_size": 84, "refit": False}
    )

    cv = content_of(
        call(server, "create_cv", {"plan_id": plan_id, "initial_train_size": 84})
    )
    error = error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")
    forecast = call(server, "forecast", {"plan_id": plan_id})

    assert [
        ToolNotice(**n) for n in cv["notices"] if n["category"] == "UserWarning"
    ] == [
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
        )
    ]
    # The notice of the server that leaves those values to the user comes
    # with the warning, one call before the error that carries the hint.
    assert [n["category"] for n in cv["notices"]][:1] == ["MissingValuesNotice"]
    assert (error["code"], error["field"]) == ("invalid_argument", "data_path")
    assert error["message"] == (
        "The forecaster reads missing values of the target to predict 1 of "
        "the 3 test folds ('x': 1 value(s), such as '2004-10-01'). "
        "ForecasterRecursive with Ridge cannot use them, so its predictions "
        "would be missing. "
        "Either they are filled in, or the plan uses an estimator that "
        "accepts missing values (such as 'RandomForestRegressor')."
    )
    assert error["hint"] == DATA_VALUES_HINT
    assert not forecast.is_error


def test_tool_backtest_output_when_series_ids_are_numbers(tmp_path):
    """
    Test that `backtest` runs on long-format data whose series ids are
    numbers ('001', '1', '10') as the Python API does, with the series named
    as in the file. Before, it failed as `execution_failed` with `KeyError: 1`
    inside skforecast (skforecast issue #1357).
    """
    path = write_csv(tmp_path, "stores.csv", df_multi_long_numeric_ids)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, _, cv_id = cv_of(
        server,
        path,
        target="value",
        steps=7,
        profile_arguments={"series_id_column": "series_id"},
    )

    result = content_of(call(server, "backtest", {"cv_id": cv_id}))
    code = content_of(call(server, "get_code", {"object_id": result["id"]}))["code"]

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="value", series_id_column="series_id")
    plan = assistant.plan(profile=profile, steps=7)
    cv = assistant.create_cv(profile=profile, plan=plan)
    expected = assistant.backtest(
        data=path, cv=cv, profile=profile, plan=plan, show_progress=False
    )
    predictions = pd.read_csv(
        result["files"]["predictions"], index_col=0, dtype={"level": str}
    )

    assert result["summary"] == expected.describe()
    assert text_of(result["files"]["predictions"]) == csv_of(expected.predictions)
    assert text_of(result["files"]["metrics"]) == csv_of(expected.metrics)
    assert sorted(predictions["level"].unique()) == ["001", "1", "10"]
    assert f"pd.read_csv({path!r}, dtype={{'series_id': str}})" in code
    assert code == expected.code


def test_tool_backtest_insufficient_data_when_a_series_is_never_forecast(tmp_path):
    """
    Test that a long-format CSV with a series of 20 days ('item_2', its last
    ones), fewer than the 21 its plan reads, is named from the profile to the
    backtest: the profile notice names it, and `backtest` is
    `insufficient_data` on `data_path` naming it, before running, as
    `forecast` of the plan is. Before, skforecast forecast it in no fold and
    left it out of the predictions and of the average across series without
    a warning (skforecast issue #1406).
    """
    data = df_items_sales_long.drop(
        index=df_items_sales_long.index[df_items_sales_long["series"] == "item_2"][:-20]
    )
    path = write_csv(tmp_path, "items.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def steps(client):
        profile = content_of(await client.call_tool(
            "profile",
            {"data_path": path, "target": "value", "series_id_column": "series"},
        ))
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 7})
        )
        cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
        backtest = await client.call_tool("backtest", {"cv_id": cv["id"]})
        forecast = await client.call_tool("forecast", {"plan_id": plan["id"]})
        return profile, backtest, forecast

    profile, backtest, forecast = run_session(server, steps)
    error = error_of(backtest, "backtest")

    assert [n["message"] for n in profile["notices"]] == [
        "Short series: only 20 observations in series 'item_2'. Results may be "
        "unreliable with fewer than 50 observations."
    ]
    assert (error["code"], error["field"]) == ("insufficient_data", "data_path")
    assert error["message"] == (
        "Some series cannot be forecast in any fold of the backtest ('item_2': "
        "20 observations, from their first to their last value). "
        "ForecasterRecursiveMultiSeries forecasts a series in a fold only when "
        "the training window of the fold has more than the 21 observations of "
        "it that it reads to build its predictors, and the series has the 21 "
        "dates before the fold; skforecast leaves the other series out without "
        "a warning, so they would get no predictions and no metrics, and the "
        "average across series would leave them out. `forecast()` of this plan "
        "rejects them too. Remove those series, or use shorter lags and window "
        "features."
    )
    assert error["hint"] == (
        "Remove those series, or use shorter lags and window features."
    )
    assert error_of(forecast, "forecast")["code"] == "insufficient_data"


def test_tool_backtest_notice_of_undefined_mape_when_target_crosses_zero(tmp_path):
    """
    Test that MAPE requested on a target that crosses zero gets, in the
    response of `backtest`, the notice that it has no meaning instead of its
    unit, which needs the profile of the data.
    """
    path = write_csv(tmp_path, "profit.csv", df_crossing_zero)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, _, cv_id = cv_of(
        server, path, target="profit", steps=6,
        metric="mean_absolute_percentage_error",
    )

    result = content_of(call(server, "backtest", {"cv_id": cv_id}))
    assert [n["category"] for n in result["notices"]] == ["MetricUndefinedNotice"]
    assert result["notices"][-1]["message"].startswith(
        "`mean_absolute_percentage_error` has no meaning on this data"
    )


def test_tool_backtest_confirm_cost_of_an_expensive_run(tmp_path):
    """
    Test that a backtest above 50 estimator fits (a ForecasterDirect of 6
    steps refitted in each of 14 folds: 84) is refused before running
    without `confirm_cost`, with its cost, the cheaper strategies and the
    number to repeat, that `create_cv` gives that number and its
    `CostNotice` names it, that another number is refused saying the
    strategy or the plan changed, that `true` is not a number, and that the
    number runs it.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(
        server,
        path,
        steps=6,
        forecaster="ForecasterDirect",
        cv_arguments={"initial_train_size": 120, "refit": True},
    )
    cv = content_of(call(server, "describe_object", {"object_id": cv_id}))

    missing = error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")
    another = error_of(
        call(server, "backtest", {"cv_id": cv_id, "confirm_cost": 83}), "backtest"
    )
    true = error_of(
        call(server, "backtest", {"cv_id": cv_id, "confirm_cost": True}), "backtest"
    )
    result = content_of(
        call(server, "backtest", {"cv_id": cv_id, "confirm_cost": 84})
    )

    assert cv["cost"]["estimator_fits"] == 84
    assert "passing `confirm_cost: 84` to `backtest`" in cv["notices"][0]["message"]
    assert missing == {
        "code": "invalid_argument",
        "message": (
            "Expensive run not confirmed, so nothing ran. This backtest is above "
            "the threshold of an expensive run (50 estimator fits or 2000 "
            "inference windows). ForecasterDirect will be fit 84 times (14 "
            "trainings x 6 estimators)."
        ),
        "field": "confirm_cost",
        "hint": (
            "Stop here and do not run it: tell the user these numbers and the "
            "cheaper strategies (an integer `refit` (retrain every n folds), "
            "fewer folds (a later `initial_train_size`, a larger `fold_stride` "
            "or `skip_folds`) or `refit=false` (train once)), and ask them. Only "
            "if they choose to run it as it is, call `backtest` again with the "
            "same arguments and `confirm_cost: 84`. Asking to retrain the model, "
            "or to evaluate it as in production, is not that choice."
        ),
        "details": {
            "confirm_cost": 84,
            "cost": {
                "n_folds": 14, "n_fits": 14, "estimator_fits": 84,
                "inference_windows": 0,
            },
        },
    }
    assert another["message"] == (
        f"{missing['message']} `confirm_cost` is 83, not 84: the strategy or the "
        f"plan changed since that number was given."
    )
    assert true["field"] == "confirm_cost"
    assert true["details"] is None
    assert result["cost"] == {
        "n_folds": 14, "n_fits": 14, "estimator_fits": 84, "inference_windows": 0
    }
    assert [n["category"] for n in result["notices"]] == [
        "MetricReferenceNotice", "MetricUnitNotice",
    ]


def test_tool_backtest_confirm_cost_of_another_plan_on_the_strategy(tmp_path):
    """
    Test that the number to confirm is the cost of the plan that runs: a
    strategy built for a ForecasterRecursive plan (14 fits, below the
    threshold) needs no confirmation for it, while `plan_id` of a
    ForecasterDirect plan on it (84 fits) is refused until that number is
    given.
    """
    server, path = h2o_server(tmp_path)
    profile_id, _, cv_id = cv_of(
        server,
        path,
        steps=6,
        cv_arguments={"initial_train_size": 120, "refit": True},
    )
    direct = content_of(
        call(
            server, "plan",
            {"profile_id": profile_id, "steps": 6, "forecaster": "ForecasterDirect"},
        )
    )

    own = content_of(call(server, "backtest", {"cv_id": cv_id}))
    refused = error_of(
        call(server, "backtest", {"cv_id": cv_id, "plan_id": direct["id"]}),
        "backtest",
    )
    confirmed = content_of(
        call(
            server, "backtest",
            {"cv_id": cv_id, "plan_id": direct["id"], "confirm_cost": 84},
        )
    )

    assert own["cost"]["estimator_fits"] == 14
    assert refused["details"]["confirm_cost"] == 84
    assert confirmed["cost"]["estimator_fits"] == 84


def test_tool_backtest_below_the_threshold_ignores_confirm_cost(tmp_path):
    """
    Test that a backtest at or below 50 estimator fits needs no
    `confirm_cost` and ignores one that is not its cost: the same response
    without it and with 999.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)

    without = content_of(call(server, "backtest", {"cv_id": cv_id}))
    ignored = content_of(
        call(server, "backtest", {"cv_id": cv_id, "confirm_cost": 999})
    )

    assert without["cost"] == ignored["cost"]
    assert without["cost"]["estimator_fits"] <= 50
    assert text_of(without["files"]["metrics"]) == text_of(ignored["files"]["metrics"])
