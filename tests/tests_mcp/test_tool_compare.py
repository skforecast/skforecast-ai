# Unit test tool compare

import importlib.util
import re
import threading
import time
import warnings
import anyio
import pytest
from mcp import Client

from skforecast_ai import (
    CandidateFailedWarning,
    ForecastingAssistant,
    IntervalCoverageWarning,
    MissingBackendWarning,
)
from skforecast_ai.mcp import _runtime, create_server

from ..fixtures_assistant import df_crossing_zero, df_multi_long_numeric_ids, df_no_exog
from ..fixtures_datasets import df_items_sales_long

from .fixtures_mcp import (
    COMPARE_CANDIDATES,
    DATA_VALUES_HINT,
    call,
    content_of,
    csv_of,
    cv_of,
    df_h2o_csv,
    error_of,
    h2o_server,
    profile_and_plan,
    run_session,
    text_of,
    write_csv,
)


def _python_comparison(path):
    """
    Return the profile and the comparison of `COMPARE_CANDIDATES` of the Python API.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    cv = assistant.create_cv(
        profile=profile, plan=assistant.plan(profile=profile, steps=12)
    )
    with pytest.warns(UserWarning, match=re.escape("Candidate 'bad' failed")):
        result = assistant.compare(
            data=path,
            cv=cv,
            profile=profile,
            show_progress=False,
            candidates=[(c["name"], dict(c["config"])) for c in COMPARE_CANDIDATES],
        )

    return profile, result


def test_tool_compare_output_matches_python_api(tmp_path):
    """
    Test that `compare` ranks the candidates as the Python API does (same
    summary, leaderboard, best predictions and metrics, the invalid
    candidate as a failure ranked last), registers the plan of the winner
    and states the cost summed over all the candidates, counted before they
    run.
    """
    server, path = h2o_server(tmp_path)
    profile_id, _, cv_id = cv_of(server, path)

    result = content_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES})
    )
    best_plan = content_of(
        call(server, "describe_object", {"object_id": result["links"]["best_plan_id"]})
    )
    profile, expected = _python_comparison(path)
    best = expected.best_candidate
    script = ForecastingAssistant().forecast_code(profile=profile, plan=best.plan)

    assert result["kind"] == "comparison"
    assert result["links"] == {
        "profile_id": profile_id,
        "cv_id": cv_id,
        "best_plan_id": result["links"]["best_plan_id"],
    }
    assert result["summary"] == expected.describe()
    assert text_of(result["files"]["leaderboard"]) == csv_of(expected.results)
    assert text_of(result["files"]["best_predictions"]) == csv_of(best.predictions)
    assert text_of(result["files"]["best_metrics"]) == csv_of(best.metrics)
    # Counted before running, the candidate that failed included: one
    # training each (the baseline too), and estimator fits Ridge 1, the
    # failed candidate 1, the direct forecaster one per step (12) and the
    # baseline 0; no foundation model ran.
    assert result["cost"] == {
        "n_folds": 6, "n_fits": 4, "estimator_fits": 14, "inference_windows": 0
    }
    # The leaderboard has MAPE, whose unit the server states.
    assert [n["category"] for n in result["notices"]] == ["MetricUnitNotice"]
    assert best_plan["kind"] == "plan"
    assert best_plan["links"] == {
        "profile_id": profile_id,
        "comparison_id": result["id"],
    }
    assert best_plan["summary"] == script.describe()


def test_tool_compare_cost_of_candidates_above_the_threshold_only_in_total(
    tmp_path,
):
    """
    Test that `compare` with explicit candidates, each at most 50 estimator
    fits (two ForecasterDirect of 8 trainings x 6 estimators, 48 each) but
    104 together, carries the `LongTrainingWarning` of the total, counted
    before they run, with what each candidate adds, the baseline included;
    and that its `cost` has the totals: trainings 8 per candidate, the
    baseline too, and the folds of the shared strategy.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path, steps=6)
    cv = content_of(
        call(
            server, "create_cv",
            {"plan_id": plan_id, "initial_train_size": 160, "refit": True},
        )
    )
    candidates = [
        {"name": "direct_a", "config": {"forecaster": "ForecasterDirect", "lags": 3}},
        {"name": "direct_b", "config": {"forecaster": "ForecasterDirect", "lags": 6}},
        {"name": "rec", "config": {}},
    ]

    result = content_of(
        call(server, "compare", {"cv_id": cv["id"], "candidates": candidates})
    )

    assert result["cost"] == {
        "n_folds": 8, "n_fits": 32, "estimator_fits": 104, "inference_windows": 0
    }
    assert [n["category"] for n in result["notices"]] == [
        "MetricUnitNotice", "LongTrainingWarning",
    ]
    assert result["notices"][1] == {
        "source": "runtime",
        "category": "LongTrainingWarning",
        "message": (
            "The comparison will fit 104 estimators in all ('direct_a': 48 "
            "(8 trainings x 6 estimators), 'direct_b': 48 (8 trainings x 6 "
            "estimators), 'rec': 8, 'Baseline (seasonal naive)': 0). This can "
            "take substantial amounts of time. If not feasible, compare fewer "
            "candidates or use an integer `refit` (retrain every n folds), "
            "fewer folds (a later `initial_train_size`, a larger `fold_stride` "
            "or `skip_folds`) or `refit=False` (train once)."
        ),
        "count": 1,
    }


def test_tool_compare_code_and_failures_of_the_candidates(tmp_path):
    """
    Test that `get_code` returns the script of the best candidate or of the
    one named, and that `get_failure` returns the traceback of a failed
    candidate; unknown candidates are `invalid_argument`.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    comparison_id = content_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES})
    )["id"]
    _, expected = _python_comparison(path)

    best = content_of(call(server, "get_code", {"object_id": comparison_id}))
    direct = content_of(
        call(server, "get_code", {"object_id": comparison_id, "candidate": "direct"})
    )
    failure = content_of(
        call(server, "get_failure", {"object_id": comparison_id, "candidate": "bad"})
    )
    no_code = error_of(
        call(server, "get_code", {"object_id": comparison_id, "candidate": "bad"}),
        "get_code",
    )
    no_failure = error_of(
        call(server, "get_failure", {"object_id": comparison_id, "candidate": "ridge"}),
        "get_failure",
    )

    assert best["code"] == expected.best_candidate.code
    assert best["candidate"] is None
    assert direct["code"] == expected.candidates["direct"].code
    assert failure["candidate"] == "bad"
    assert failure["text"].startswith(
        "Candidate 'bad' failed: ValueError: 'NoSuchEstimator' is not a "
        "supported estimator."
    )
    assert "Traceback:\n" in failure["text"]
    assert (no_code["code"], no_code["field"]) == ("invalid_argument", "candidate")
    assert no_failure["message"] == (
        f"The comparison {comparison_id!r} has no failed candidate named 'ridge'. "
        f"Failed candidates: ['bad']."
    )


def test_tool_compare_reports_monotonic_progress(tmp_path, monkeypatch):
    """
    Test that `compare` reports progress when each candidate starts and
    ends: `2 * completed + started` over `2 * total`, always growing, the
    baseline included (no heartbeat, which fires after a long silence).
    """
    monkeypatch.setattr(_runtime, "HEARTBEAT_SECONDS", 3600)
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    events = []

    async def steps(client):
        async def record(progress, total, message):
            events.append((progress, total, message))

        return await client.call_tool(
            "compare",
            {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES[:2]},
            progress_callback=record,
        )

    content_of(run_session(server, steps))

    assert events == [
        (1.0, 6.0, "ridge: started"),
        (2.0, 6.0, "ridge: succeeded"),
        (3.0, 6.0, "bad: started"),
        (4.0, 6.0, "bad: failed"),
        (5.0, 6.0, "Baseline (seasonal naive): started"),
        (6.0, 6.0, "Baseline (seasonal naive): succeeded"),
    ]


def test_tool_compare_cancelled_between_candidates(tmp_path, monkeypatch):
    """
    Test that cancelling a comparison while a candidate runs stops it before
    the next candidate, registers nothing, and leaves the server ready for
    the next call. The first candidate waits until the client has cancelled.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    ran = []
    client_cancelled = threading.Event()
    backtest = ForecastingAssistant.backtest

    def recorded_backtest(self, *args, **kwargs):
        ran.append(kwargs["plan"].forecaster)
        if len(ran) == 1:
            client_cancelled.wait(10)
            # Time for the cancellation to reach the handler of the server.
            time.sleep(0.5)
        return backtest(self, *args, **kwargs)

    monkeypatch.setattr(ForecastingAssistant, "backtest", recorded_backtest)

    async def main():
        async with Client(server) as client:
            started = anyio.Event()

            async def record(progress, total, message):
                started.set()

            with anyio.CancelScope() as scope:
                async with anyio.create_task_group() as group:

                    async def cancel_when_started():
                        await started.wait()
                        scope.cancel()
                        client_cancelled.set()

                    group.start_soon(cancel_when_started)
                    await client.call_tool(
                        "compare",
                        {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES},
                        progress_callback=record,
                    )
            objects = content_of(await client.call_tool("list_objects", {}))["objects"]
            after = content_of(await client.call_tool("backtest", {"cv_id": cv_id}))
            return scope.cancelled_caught, objects, after

    cancelled, objects, after = anyio.run(main)

    assert cancelled is True
    # The first candidate, then the backtest called after the cancellation.
    assert ran == ["ForecasterRecursive", "ForecasterRecursive"]
    assert [o["kind"] for o in objects] == ["cv", "plan", "profile"]
    assert after["kind"] == "backtest"


@pytest.mark.parametrize(
    "arguments, field",
    [
        ({"metric": "accuracy"}, "metric"),
        ({"metric": []}, "metric"),
        ({"candidates": [{"name": "a\nb", "config": {}}]}, "candidates[0].name"),
        (
            {"candidates": [{"name": "a", "config": {"steps": 3}}]},
            "candidates[0].config.steps",
        ),
        ({"candidates": [{"name": "a"}, {"name": "a"}]}, "candidates"),
        ({"interval": [0.9, 0.1]}, "interval"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_compare_invalid_argument(tmp_path, arguments, field):
    """
    Test that `compare` rejects a metric outside the regression metrics or
    an empty list of them, a candidate name with a control character, an
    unknown key of a candidate, repeated names and an invalid interval,
    before any candidate runs.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)

    error = error_of(call(server, "compare", {"cv_id": cv_id, **arguments}), "compare")

    assert error["code"] == "invalid_argument"
    assert error["field"] == field


def test_tool_compare_all_candidates_failed_keeps_the_failures(tmp_path):
    """
    Test that a comparison whose candidates all fail is
    `all_candidates_failed`, with the id of a failure that holds the
    traceback of every candidate.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)

    error = error_of(
        call(
            server,
            "compare",
            {
                "cv_id": cv_id,
                "candidates": COMPARE_CANDIDATES[1:2],
                "baseline": False,
            },
        ),
        "compare",
    )
    failure = content_of(
        call(server, "get_failure", {"object_id": error["details"]["failure_id"]})
    )

    assert error["code"] == "all_candidates_failed"
    assert error["message"].startswith("All 1 candidate configuration(s) failed to run")
    assert failure["text"].startswith("Candidate 'bad' failed: ValueError:")


def test_tool_compare_default_candidates_of_the_profile(tmp_path):
    """
    Test that without `candidates` the comparison uses those of the profile,
    as the Python API does (several series: the estimators of
    ForecasterRecursiveMultiSeries, the foundation model being left out when
    its backend is missing).
    """
    if importlib.util.find_spec("chronos") is not None:
        pytest.skip("With its backend installed the default set runs Chronos-2.")
    path = write_csv(tmp_path, "items.csv", df_items_sales_long)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, _, cv_id = cv_of(
        server,
        path,
        target="value",
        steps=7,
        profile_arguments={"series_id_column": "series"},
    )

    result = content_of(call(server, "compare", {"cv_id": cv_id}))

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="value", series_id_column="series")
    cv = assistant.create_cv(
        profile=profile, plan=assistant.plan(profile=profile, steps=7)
    )
    # A candidate whose library is not installed (XGBoost) fails, as it may.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=CandidateFailedWarning)
        with pytest.warns(MissingBackendWarning):
            expected = assistant.compare(
                data=path, cv=cv, profile=profile, show_progress=False
            )

    assert result["summary"] == expected.describe()
    assert text_of(result["files"]["leaderboard"]) == csv_of(expected.results)


def test_tool_compare_announces_model_download_of_a_candidate_that_ran(
    tmp_path, monkeypatch
):
    """
    Test that a foundation candidate whose weights are not in the local
    Hugging Face cache and whose script ran (here it fails inside the script
    without its backend, which a download could precede; the backend is
    taken as installed so the check before running lets it run) gets one
    `ModelDownloadNotice` in the comparison, and in a second comparison a
    `ModelLicenseNotice` with its license instead.
    """
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: True
    )
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    server = create_server(
        allow_dir    = tmp_path,
        output_dir   = tmp_path / "out",
        allow_models = ["Salesforce/moirai-2"],
    )
    _, _, cv_id = cv_of(server, path)
    arguments = {
        "cv_id": cv_id,
        "candidates": [
            {"name": "ridge", "config": {"estimator": "Ridge"}},
            {
                "name": "moirai",
                "config": {
                    "forecaster": "ForecasterFoundation",
                    "estimator": "Salesforce/moirai-2.0-R-small",
                },
            },
        ],
    }

    first = content_of(call(server, "compare", arguments))
    second = content_of(call(server, "compare", arguments))

    assert [
        (n["source"], n["category"]) for n in first["notices"]
        if n["category"] == "ModelDownloadNotice"
    ] == [("plan", "ModelDownloadNotice")]
    assert "CC-BY-NC-4.0" in first["notices"][0]["message"]
    assert all(n["category"] != "ModelDownloadNotice" for n in second["notices"])
    assert [
        n["message"] for n in second["notices"]
        if n["category"] == "ModelLicenseNotice"
    ] == [
        "Foundation model 'Salesforce/moirai-2.0-R-small'. License (by the "
        "name of the model, as skforecast registers it): its license is "
        "CC-BY-NC-4.0 (https://huggingface.co/Salesforce/moirai-2.0-R-small), "
        "which restricts commercial use."
    ]


def test_tool_compare_heartbeat_inside_a_long_candidate(tmp_path, monkeypatch):
    """
    Test that while a candidate runs for longer than the heartbeat, the
    comparison sends notifications naming it ("ridge: running (0 s)"),
    above its start event and below its end event, with the total of the
    comparison.
    """
    monkeypatch.setattr(_runtime, "HEARTBEAT_SECONDS", 0.05)
    backtest = ForecastingAssistant.backtest

    def slow_backtest(self, *args, **kwargs):
        if kwargs["plan"].estimator == "Ridge":
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
            "compare",
            {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES[:1]},
            progress_callback=record,
        )

    content_of(run_session(server, steps))

    values = [progress for progress, _, _ in events]
    inside = [event for event in events if 1 < event[0] < 2]
    assert values == sorted(set(values))
    assert len(inside) >= 3
    assert inside[0] == (1.5, 4.0, "ridge: running (0 s)")
    assert (1.0, 4.0, "ridge: started") in events
    assert (2.0, 4.0, "ridge: succeeded") in events


def test_tool_compare_without_interval_uses_the_interval_of_the_plan_of_the_cv(
    tmp_path,
):
    """
    Test that `compare` without `interval` computes the interval of the plan
    the strategy was built for, as the Python API with that interval does,
    so the plan of the winner keeps it and its forecast has bounds; an
    explicit `interval` still wins. The interval covers clearly less than
    80 % on these folds, which the Python API warns about.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path, interval=[0.1, 0.9])
    candidates = COMPARE_CANDIDATES[:1]

    result = content_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": candidates})
    )
    explicit = content_of(
        call(
            server,
            "compare",
            {"cv_id": cv_id, "candidates": candidates, "interval": [0.2, 0.8]},
        )
    )
    forecast = content_of(
        call(server, "forecast", {"plan_id": result["links"]["best_plan_id"]})
    )

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    cv = assistant.create_cv(
        profile=profile,
        plan=assistant.plan(profile=profile, steps=12, interval=[0.1, 0.9]),
    )
    with pytest.warns(IntervalCoverageWarning, match="in these candidates"):
        expected = assistant.compare(
            data=path,
            cv=cv,
            profile=profile,
            show_progress=False,
            candidates=[(c["name"], dict(c["config"])) for c in candidates],
            interval=[0.1, 0.9],
        )

    header = text_of(forecast["files"]["predictions"]).splitlines()[0]
    assert header == ",pred,lower_bound,upper_bound"
    assert expected.best_candidate.plan.interval == [0.1, 0.9]
    assert result["summary"] == expected.describe()
    assert explicit["summary"] != result["summary"]


def test_tool_compare_metric_of_the_call_or_of_the_plan(tmp_path):
    """
    Test that `compare` ranks by its `metric`, and without one by the metric
    chosen for the plan of the strategy, whose plan of the winner keeps it.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    _, chosen_plan_id, chosen_cv_id = cv_of(
        server, path, metric=["mean_squared_error", "mean_absolute_error"]
    )
    candidates = [{"name": "ridge", "config": {"estimator": "Ridge"}}]

    given = content_of(call(server, "compare", {
        "cv_id": cv_id, "candidates": candidates, "baseline": False,
        "metric": "median_absolute_error",
    }))
    of_plan = content_of(call(server, "compare", {
        "cv_id": chosen_cv_id, "candidates": candidates, "baseline": False,
    }))
    best = content_of(call(
        server, "describe_object", {"object_id": of_plan["links"]["best_plan_id"]}
    ))

    assert text_of(given["files"]["leaderboard"]).splitlines()[0].endswith(
        "median_absolute_error"
    )
    assert "- Ranking metric: mean_squared_error" in of_plan["summary"]
    assert "Primary metric: mean_squared_error, as requested" in best["summary"]


def test_tool_compare_candidates_with_the_overrides_of_a_plan(tmp_path):
    """
    Test that the candidates of `compare` take the overrides of a plan
    (`differentiation`, `calendar_features`, `target_transformer`,
    `dropna_from_series`, `use_exog`) and rank as the Python API does.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    candidates = [
        {"name": "plain", "config": {"estimator": "Ridge"}},
        {
            "name": "variant",
            "config": {
                "estimator": "Ridge", "differentiation": 1,
                "calendar_features": ["month"], "target_transformer": "none",
                "dropna_from_series": True, "use_exog": False,
            },
        },
    ]

    result = content_of(call(server, "compare", {
        "cv_id": cv_id, "candidates": candidates, "baseline": False,
    }))

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    expected = assistant.compare(
        data=path,
        cv=assistant.create_cv(
            profile=profile, plan=assistant.plan(profile=profile, steps=12)
        ),
        profile=profile,
        candidates=[(c["name"], dict(c["config"])) for c in candidates],
        show_progress=False,
        baseline=False,
    )

    assert text_of(result["files"]["leaderboard"]) == csv_of(expected.results)
    assert result["summary"] == expected.describe()


def test_tool_compare_summary_names_the_arguments_passed_to_the_strategy(tmp_path):
    """
    Test that `compare` hands the whole strategy to the assistant: the
    summary of a strategy created with `refit=True` says the user chose it,
    in the shared strategy and at the end of the explanation, saying the
    strategy was created for the plan, and that the summary of a strategy
    without arguments explains the defaults.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path, cv_arguments={"refit": True})
    _, _, default_cv_id = cv_of(server, path)

    chosen = content_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES})
    )
    default = content_of(
        call(
            server, "compare",
            {"cv_id": default_cv_id, "candidates": COMPARE_CANDIDATES},
        )
    )

    assert "- Chosen by the user instead of the rules: refit\n" in chosen["summary"]
    assert (
        " The strategy was created for the plan (ForecasterRecursive + Ridge). "
        "Initial training size by default: 70% of the 204 observations (142), "
        "up to 2003-04-01. `refit` as requested.\n</deterministic_summary>"
    ) in chosen["summary"]
    strategy = default["summary"][
        default["summary"].index("<backtesting_strategy>"):
        default["summary"].index("</backtesting_strategy>")
    ]
    assert "Chosen by the user instead of the rules" not in strategy
    assert (
        "The shared strategy trains once by default: refitting in every fold "
        "would multiply the training cost by the 6 folds."
    ) in default["summary"]


def test_tool_compare_invalid_argument_with_hint_when_the_target_has_missing_values(
    tmp_path,
):
    """
    Test that a comparison on data whose last rows have no target value is
    `invalid_argument` on `data_path` with the hint of the server that
    leaves the values to the user: the message says to impute them, which
    an agent does without asking.
    """
    data = df_h2o_csv.copy()
    data.loc[data.index[-3:], "x"] = float("nan")
    path = write_csv(tmp_path, "tail.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, _, cv_id = cv_of(server, path)

    error = error_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES}),
        "compare",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "data_path")
    assert error["message"] == (
        "The target has 3 missing value(s) in test folds 5 and 6 of 6 "
        "(2008-04-01 "
        "00:00:00, 2008-05-01 00:00:00, 2008-06-01 00:00:00), counting the "
        "missing timestamps that asfreq() restores. skforecast cannot compute "
        "the metrics on them, whatever the estimator. Impute the target, or "
        "evaluate on dates without missing values."
    )
    assert error["hint"] == DATA_VALUES_HINT


def _refined_cv_ids(server, path, overrides, profile_arguments=None, **plan_arguments):
    """
    Profile `path`, build a plan, refine it with `overrides` and create the
    strategy of the refined plan in the server; return the id of the
    strategy.
    """
    plan_arguments.setdefault("steps", 12)

    async def steps(client):
        profile = content_of(
            await client.call_tool(
                "profile", {"data_path": path, **(profile_arguments or {})}
            )
        )
        plan = content_of(
            await client.call_tool(
                "plan", {"profile_id": profile["id"], **plan_arguments}
            )
        )
        refined = content_of(
            await client.call_tool(
                "refine_plan", {"plan_id": plan["id"], "overrides": overrides}
            )
        )
        cv = content_of(
            await client.call_tool("create_cv", {"plan_id": refined["id"]})
        )
        return cv["id"]

    return run_session(server, steps)


def test_tool_compare_runs_the_refined_plan_of_the_strategy_as_a_row(
    tmp_path, monkeypatch
):
    """
    Test that `compare` without `candidates` on the strategy of a refined
    plan runs that plan as the row 'Strategy plan', as the Python API does
    (same summary and leaderboard), and that the summary names the row, its
    rank and the configurations that beat the baseline. The foundation
    backend is reported as missing, so the table does not depend on whether
    it is installed.
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
    path = write_csv(tmp_path, "sales.csv", df_no_exog)
    arguments = {"target": "sales", "date_column": "date"}
    overrides = {"estimator": "LGBMRegressor", "lags": [1, 2, 3]}
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    cv_id = _refined_cv_ids(
        server, path, overrides, profile_arguments=arguments, steps=5
    )

    result = content_of(call(server, "compare", {"cv_id": cv_id}))

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, **arguments)
    refined = assistant.refine_plan(
        profile=profile, plan=assistant.plan(profile=profile, steps=5), **overrides
    )
    cv = assistant.create_cv(profile=profile, plan=refined)
    with pytest.warns(MissingBackendWarning):
        expected = assistant.compare(
            data=path, cv=cv, profile=profile, show_progress=False
        )
    leaderboard = text_of(result["files"]["leaderboard"])

    assert expected.strategy_plan_name == "Strategy plan"
    assert result["summary"] == expected.describe()
    assert leaderboard == csv_of(expected.results)
    assert [line.split(",")[2] for line in leaderboard.splitlines()[1:]] == [
        "ForecasterStats",
        "ForecasterDirect",
        "ForecasterRecursive",
        "Baseline (seasonal naive)",
        "Strategy plan",
    ]
    assert (
        "'Strategy plan' runs the plan the strategy was created for "
        "(ForecasterRecursive / LGBMRegressor), ranked 5 of 5 (26.0997); the "
        "rows named after a forecaster run the configurations the profile "
        "recommends, not that plan."
    ) in result["summary"]
    assert (
        "3 of 4 configurations beat the baseline 'Baseline (seasonal naive)' "
        "(7.0000); 'Strategy plan' does not. The best, 'ForecasterStats', "
        "beats it by 100.0%."
    ) in result["summary"]
    assert (
        "The strategy was created for the plan of row 'Strategy plan' "
        "(ForecasterRecursive + LGBMRegressor)."
    ) in result["summary"]
    # Trainings: stats 6 (one per fold), and 1 for each of direct,
    # recursive, the baseline and the plan of the strategy. Estimator fits:
    # direct 5, stats 6, recursive 1, the plan of the strategy 1 and the
    # baseline 0.
    assert result["cost"] == {
        "n_folds": 6, "n_fits": 10, "estimator_fits": 13, "inference_windows": 0
    }


@pytest.mark.slow
def test_tool_compare_refined_plan_of_h2o_is_the_last_row_below_the_baseline(
    tmp_path, monkeypatch
):
    """
    Test the minimal case of the plan refined to LGBMRegressor with lags
    [1, 2, 3, 12] on h2o through the tools: the row 'Strategy plan' scores
    the MAE of its backtest (0.082949), ranks below the baseline, and the
    summary counts the configurations that beat the baseline (2 of 4).
    """
    monkeypatch.setattr(
        "skforecast_ai.execution.comparison.foundation_backend_installed",
        lambda info: False,
    )
    server, path = h2o_server(tmp_path)
    cv_id = _refined_cv_ids(
        server, path, {"estimator": "LGBMRegressor", "lags": [1, 2, 3, 12]},
        profile_arguments={"target": "x"},
    )

    result = content_of(call(server, "compare", {"cv_id": cv_id}))

    rows = [
        line.split(",")
        for line in text_of(result["files"]["leaderboard"]).splitlines()
    ]
    assert [(row[2], row[4]) for row in rows[1:]] == [
        ("ForecasterRecursive", "Ridge"),
        ("ForecasterStats", "Arima"),
        ("Baseline (seasonal naive)", ""),
        ("ForecasterDirect", "Ridge"),
        ("Strategy plan", "LGBMRegressor"),
    ]
    assert round(float(rows[5][5]), 6) == 0.082949
    assert (
        "2 of 4 configurations beat the baseline 'Baseline (seasonal naive)' "
        "(0.0661): 'ForecasterRecursive' and 'ForecasterStats'. The best, "
        "'ForecasterRecursive', beats it by 6.2%."
    ) in result["summary"]


def test_tool_compare_output_when_series_ids_are_numbers(tmp_path):
    """
    Test that `compare` runs its candidates on long-format data whose series
    ids are numbers ('001', '1', '10') as the Python API does, none of them
    failing. Before, every candidate failed with `KeyError: 1` inside
    skforecast (skforecast issue #1357) and the call was
    `all_candidates_failed`.
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
    candidates = [
        {"name": "ridge", "config": {"estimator": "Ridge"}},
        {"name": "lgbm", "config": {"estimator": "LGBMRegressor"}},
    ]

    result = content_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": candidates})
    )

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="value", series_id_column="series_id")
    cv = assistant.create_cv(
        profile=profile, plan=assistant.plan(profile=profile, steps=7)
    )
    expected = assistant.compare(
        data=path,
        cv=cv,
        profile=profile,
        show_progress=False,
        candidates=[(c["name"], dict(c["config"])) for c in candidates],
    )

    assert result["summary"] == expected.describe()
    assert text_of(result["files"]["leaderboard"]) == csv_of(expected.results)
    assert not expected.failures


def test_tool_compare_notice_of_undefined_mape_when_target_crosses_zero(tmp_path):
    """
    Test that MAPE requested on a target that crosses zero gets, in the
    response of `compare`, the notice that it has no meaning instead of its
    unit, which needs the profile of the data. The plan of the explicit
    candidate carries its own warning, as any warning of its plan.
    """
    path = write_csv(tmp_path, "profit.csv", df_crossing_zero)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, _, cv_id = cv_of(server, path, target="profit", steps=6)

    result = content_of(call(server, "compare", {
        "cv_id": cv_id, "baseline": False,
        "candidates": [{"name": "ridge", "config": {"estimator": "Ridge"}}],
        "metric": ["mean_absolute_error", "mean_absolute_percentage_error"],
    }))
    assert [(n["source"], n["category"]) for n in result["notices"]] == [
        ("runtime", "MetricUndefinedNotice"), ("plan", "UserWarning"),
    ]
    assert result["notices"][0]["message"].startswith(
        "`mean_absolute_percentage_error` has no meaning on this data"
    )


def test_tool_compare_output_when_interval_adds_coverage_without_changing_ranking(
    tmp_path,
):
    """
    Test that `compare` with an interval puts the `coverage` and the
    `interval_width` that skforecast measured after the metrics of the
    leaderboard, ranks the candidates as without an interval, and carries an
    `IntervalCoverageNotice` naming the candidates whose interval covers
    clearly less than 80 % (in place of the `IntervalCoverageWarning` of the
    library).
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    candidates = [COMPARE_CANDIDATES[0], COMPARE_CANDIDATES[2]]

    plain = content_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": candidates})
    )
    result = content_of(
        call(
            server,
            "compare",
            {"cv_id": cv_id, "candidates": candidates, "interval": [0.1, 0.9]},
        )
    )
    leaderboard = text_of(result["files"]["leaderboard"]).splitlines()
    plain_leaderboard = text_of(plain["files"]["leaderboard"]).splitlines()

    assert leaderboard[0] == (
        ",rank,name,forecaster,estimator,mean_absolute_error,mean_squared_error,"
        "mean_absolute_scaled_error,mean_absolute_percentage_error,coverage,"
        "interval_width"
    )
    assert [line.split(",")[2] for line in leaderboard[1:]] == [
        line.split(",")[2] for line in plain_leaderboard[1:]
    ]
    assert [n["category"] for n in plain["notices"]] == ["MetricUnitNotice"]
    assert [(n["source"], n["category"]) for n in result["notices"]] == [
        ("runtime", "IntervalCoverageNotice"),
        ("runtime", "MetricUnitNotice"),
    ]
    assert result["notices"][0]["message"] == (
        "The prediction interval [0.1, 0.9] has a nominal coverage of 80 %, but "
        "it covered clearly less (more than 2 binomial standard errors for the "
        "number of predictions, and at least 5 percentage points, below 80 %) "
        "in these candidates: 'ridge' (64.5 % of 62 actual values), 'direct' "
        "(59.7 % of 62 actual values). Do not present their interval as "
        "covering 80 %: report the coverage measured in the backtest (the "
        "`coverage` column of the table, and of the metrics of each candidate "
        "by series). The same holds for a `forecast` of the same plan with "
        "this interval: give the user the coverage measured here (by series "
        "when there are several) and say that the uncertainty is larger than "
        "its bounds show."
    )
    assert (
        "The table also gives, for the prediction interval [0.1, 0.9] (nominal "
        "coverage 80 %), the share of the actual values inside it (coverage) "
        "and its mean width in the units of the target (interval_width); they "
        "do not change the ranking."
    ) in result["summary"]
