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
    MissingBackendWarning,
)
from skforecast_ai.mcp import _runtime, create_server

from ..fixtures_datasets import df_items_sales_long

from .fixtures_mcp import (
    COMPARE_CANDIDATES,
    call,
    content_of,
    cv_of,
    df_h2o_csv,
    error_of,
    h2o_server,
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
    and states the cost summed over the candidates that ran.
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
    assert text_of(result["files"]["leaderboard"]) == expected.results.to_csv()
    assert text_of(result["files"]["best_predictions"]) == best.predictions.to_csv()
    assert text_of(result["files"]["best_metrics"]) == best.metrics.to_csv()
    # Ridge 1, the direct forecaster one per step (12) and the baseline 0;
    # the candidate that failed trained nothing, and no foundation model ran.
    assert result["cost"] == {
        "n_folds": 6, "n_fits": 1, "estimator_fits": 13, "inference_windows": 0
    }
    assert result["notices"] == []
    assert best_plan["kind"] == "plan"
    assert best_plan["links"] == {
        "profile_id": profile_id,
        "comparison_id": result["id"],
    }
    assert best_plan["summary"] == script.describe()


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
    assert text_of(result["files"]["leaderboard"]) == expected.results.to_csv()


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
    explicit `interval` still wins.
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

    assert text_of(result["files"]["leaderboard"]) == expected.results.to_csv()
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
