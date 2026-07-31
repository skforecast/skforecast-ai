# Unit test compare ForecastingAssistant

import ast
import json
import re

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import (
    AllCandidatesFailedError,
    BacktestResult,
    CandidateFailedWarning,
    CandidateFailure,
    ComparisonResult,
    ForecastingAssistant,
)

from tests.fixtures_assistant import df_single, df_no_exog, df_multi_wide

assistant = ForecastingAssistant()


# Two lightweight, backend-free candidate configurations reused across tests.
_LIGHT_CANDIDATES = [
    ("recursive_default", {"forecaster": "ForecasterRecursive"}),
    (
        "direct_ridge",
        {
            "forecaster": "ForecasterDirect",
            "estimator": "Ridge",
            "lags": [1, 2, 3],
        },
    ),
]


def _single_cv():
    """Return a small TimeSeriesFold for the single-series fixtures."""
    return TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)


# =============================================================================
# Tests: candidate resolution (private helper)
# =============================================================================
def test_resolve_compare_candidates_auto_from_profile():
    """
    Test that candidates are built from `profile.forecaster_candidates`
    when `candidates` is None, each labelled by its forecaster name.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    resolved = assistant._resolve_compare_candidates(None, profile)

    names = [name for name, _ in resolved]
    assert names == profile.forecaster_candidates
    for name, config in resolved:
        assert config == {"forecaster": name}


def test_resolve_compare_candidates_ValueError_when_empty_list():
    """
    Test that an empty explicit `candidates` list raises ValueError.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(ValueError, match="must not be an empty list"):
        assistant._resolve_compare_candidates([], profile)


def test_resolve_compare_candidates_ValueError_when_duplicate_names():
    """
    Test that repeated candidate names raise ValueError, since the names
    key the `candidates` and `failures` mappings of the result.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    candidates = [
        ("dup", {"forecaster": "ForecasterRecursive"}),
        ("dup", {"forecaster": "ForecasterDirect"}),
        ("unique", {"forecaster": "ForecasterDirect"}),
    ]

    err_msg = re.escape(
        "Candidate names must be unique, found duplicates: ['dup']."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant._resolve_compare_candidates(candidates, profile)


@pytest.mark.parametrize(
    "candidates, err_type, err_match",
    [
        (
            [("bad", {"unknown_key": 1})],
            ValueError,
            "Invalid config keys",
        ),
        (
            [("bad", ["not", "a", "dict"])],
            TypeError,
            "must be a dict",
        ),
        (
            [("only_one",)],
            ValueError,
            "must be a \\(name, config\\) tuple",
        ),
    ],
    ids=lambda v: f"{v}",
)
def test_resolve_compare_candidates_raises_on_invalid_entry(
    candidates, err_type, err_match
):
    """
    Test that malformed `candidates` entries raise the expected error.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(err_type, match=err_match):
        assistant._resolve_compare_candidates(candidates, profile)


# =============================================================================
# Tests: metric aggregation (private helper)
# =============================================================================
def test_aggregate_metrics_single_series_uses_single_row():
    """
    Test that `_aggregate_metrics` returns the single row's values for a
    single-series metrics frame.
    """
    metrics = pd.DataFrame({"mean_absolute_error": [0.5], "mean_squared_error": [0.25]})

    agg = assistant._aggregate_metrics(metrics)

    assert agg == {"mean_absolute_error": 0.5, "mean_squared_error": 0.25}


def test_aggregate_metrics_multi_series_uses_average_row():
    """
    Test that `_aggregate_metrics` selects the `'average'` aggregate row
    for a multi-series metrics frame and drops the `'levels'` column.
    """
    metrics = pd.DataFrame(
        {
            "levels": ["series_a", "series_b", "average"],
            "mean_absolute_error": [0.2, 0.4, 0.3],
        }
    )

    agg = assistant._aggregate_metrics(metrics)

    assert "levels" not in agg
    assert agg == {"mean_absolute_error": 0.3}


def test_aggregate_metrics_empty_frame_returns_empty_dict():
    """
    Test that `_aggregate_metrics` returns an empty dict for None or an
    empty frame.
    """
    assert assistant._aggregate_metrics(None) == {}
    assert assistant._aggregate_metrics(pd.DataFrame()) == {}


# =============================================================================
# Tests: candidate failure snapshot
# =============================================================================
def test_candidate_failure_unwraps_execution_error_to_root_cause():
    """
    Test that `CandidateFailure.from_exception` unwraps a
    ForecastExecutionError to its root cause and keeps the generated code
    and the pre-formatted execution traceback.
    """
    from skforecast_ai.exceptions import ForecastExecutionError

    root = ImportError("cannot import name 'Ridge'")
    exc = ForecastExecutionError(
        original_error=root,
        generated_code="import Ridge",
        execution_traceback="Traceback ...\n  line 1\n  line 2",
    )

    failure = CandidateFailure.from_exception(exc)

    assert failure.error_type == "ImportError"
    assert failure.message == "cannot import name 'Ridge'"
    assert failure.traceback == "Traceback ...\n  line 1\n  line 2"
    assert failure.generated_code == "import Ridge"
    assert failure.summary() == "ImportError: cannot import name 'Ridge'"


def test_candidate_failure_from_plain_exception_formats_traceback():
    """
    Test that `CandidateFailure.from_exception` formats the traceback of a
    plain exception and leaves `generated_code` as None.
    """
    try:
        raise ValueError("bad value\nextra detail line")
    except ValueError as exc:
        failure = CandidateFailure.from_exception(exc)

    assert failure.error_type == "ValueError"
    assert failure.generated_code is None
    assert "ValueError: bad value" in failure.traceback
    assert "Traceback (most recent call last)" in failure.traceback
    # The summary keeps only the first line of a multi-line message.
    assert failure.summary() == "ValueError: bad value"


def test_candidate_failure_summary_truncates_long_messages():
    """
    Test that `CandidateFailure.summary` truncates overly long messages
    with a trailing ellipsis.
    """
    failure = CandidateFailure(
        error_type="ValueError", message="x" * 500, traceback="tb"
    )

    summary = failure.summary(max_length=50)

    assert len(summary) == 50
    assert summary.endswith("...")


def test_candidate_failure_does_not_retain_exception_frames():
    """
    Test that a `CandidateFailure` holds only plain data, so it cannot
    keep the execution namespace of a failed candidate alive.
    """
    try:
        raise ValueError("boom")
    except ValueError as exc:
        failure = CandidateFailure.from_exception(exc)

    assert all(
        isinstance(value, (str, type(None)))
        for value in failure.model_dump().values()
    )


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_compare_ValueError_when_metric_is_empty_list():
    """
    Test that compare() raises ValueError when `metric` is an empty list.
    """
    with pytest.raises(ValueError, match="`metric` must not be an empty list"):
        assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=_LIGHT_CANDIDATES,
            metric=[],
            show_progress=False,
        )


# =============================================================================
# Tests: basic output
# =============================================================================
def test_compare_output_when_single_series():
    """
    Test that compare() returns a ComparisonResult with a ranked table,
    per-candidate detailed results, and a valid winning configuration.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    # Type and structure
    assert isinstance(result, ComparisonResult)
    assert isinstance(result.results, pd.DataFrame)
    assert isinstance(result.cv_config, dict)
    assert result.ranking_metric == "mean_absolute_error"
    assert isinstance(result.explanation, str) and result.explanation

    # Results table shape and ordering
    assert list(result.results["rank"]) == [1, 2]
    assert set(result.results["name"]) == {"recursive_default", "direct_ridge"}
    expected_cols = [
        "rank",
        "name",
        "forecaster",
        "estimator",
        "mean_absolute_error",
        "mean_squared_error",
        "mean_absolute_scaled_error",
    ]
    assert list(result.results.columns) == expected_cols
    # No "error" column when every candidate succeeds
    assert "error" not in result.results.columns

    # Ranked ascending by the ranking metric
    ranking_values = result.results["mean_absolute_error"].to_numpy()
    assert np.all(np.diff(ranking_values) >= 0)

    # Candidates map every successful name to its BacktestResult, best first
    assert list(result.candidates) == list(result.results["name"])
    assert all(
        isinstance(bt, BacktestResult) for bt in result.candidates.values()
    )

    # Winner is the top-ranked candidate and is reusable
    best = result.best_candidate
    assert isinstance(best, BacktestResult)
    assert result.best_name == result.results["name"].iloc[0]
    assert best is result.candidates[result.best_name]
    assert best.profile is not None
    assert best.plan is not None
    ast.parse(best.code)


def test_compare_explanation_content_when_single_series():
    """
    Test that the compare() explanation reports the candidate count, the
    ranking rule, the shared CV strategy, and the margin over the
    runner-up.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    explanation = result.explanation
    best_name = result.results["name"].iloc[0]
    runner_name = result.results["name"].iloc[1]
    best_value = result.results["mean_absolute_error"].iloc[0]
    runner_value = result.results["mean_absolute_error"].iloc[1]
    expected_margin = 100 * (runner_value - best_value) / abs(runner_value)

    assert "Compared 2 configurations, ranked ascending by " in explanation
    assert "mean_absolute_error." in explanation
    assert "pooled across series" not in explanation
    assert "Shared cross-validation strategy: " in explanation
    assert "5-step horizon" in explanation
    assert f"Best: '{best_name}' (" in explanation
    assert f"= {best_value:.4f}" in explanation
    assert (
        f"{expected_margin:.1f}% ahead of '{runner_name}' ({runner_value:.4f})."
        in explanation
    )
    assert "failed to run" not in explanation


def test_compare_explanation_reports_pooled_metric_when_multi_series():
    """
    Test that the compare() explanation flags the ranking metric as
    pooled across series for multi-series tasks.
    """
    result = assistant.compare(
        data=df_multi_wide,
        cv=TimeSeriesFold(steps=5, initial_train_size=70, verbose=False),
        target=["series_a", "series_b"],
        date_column="date",
        candidates=[
            ("multi_default", {"forecaster": "ForecasterRecursiveMultiSeries"})
        ],
        show_progress=False,
    )

    assert "Compared 1 configuration, ranked ascending by " in result.explanation
    assert "pooled across series." in result.explanation
    assert "ahead of" not in result.explanation


def test_compare_output_when_candidates_none_auto_candidates():
    """
    Test that compare() auto-builds candidates from the profile when
    `candidates` is None, running each derived forecaster.
    """
    profile = assistant.profile(
        data=df_no_exog, target="sales", date_column="date"
    )
    # Restrict to lightweight, backend-free candidates for a deterministic,
    # fast run that does not depend on optional foundation/statistical backends.
    profile.forecaster_candidates = ["ForecasterRecursive", "ForecasterDirect"]

    result = assistant.compare(
        data=df_no_exog,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=None,
        profile=profile,
        show_progress=False,
    )

    assert set(result.results["name"]) == {
        "ForecasterRecursive",
        "ForecasterDirect",
    }
    assert list(result.candidates) == list(result.results["name"])


# =============================================================================
# Tests: metric override
# =============================================================================
def test_compare_output_when_metric_str_override():
    """
    Test that a single `metric` string sets the ranking metric and the
    only metric column in the results table.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        metric="mean_absolute_scaled_error",
        show_progress=False,
    )

    assert result.ranking_metric == "mean_absolute_scaled_error"
    assert list(result.results.columns) == [
        "rank",
        "name",
        "forecaster",
        "estimator",
        "mean_absolute_scaled_error",
    ]


def test_compare_output_when_metric_list_ranks_by_first():
    """
    Test that when `metric` is a list, the first entry ranks the table and
    all requested metrics appear as columns in order.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        metric=["mean_squared_error", "mean_absolute_error"],
        show_progress=False,
    )

    assert result.ranking_metric == "mean_squared_error"
    assert list(result.results.columns) == [
        "rank",
        "name",
        "forecaster",
        "estimator",
        "mean_squared_error",
        "mean_absolute_error",
    ]
    ranking_values = result.results["mean_squared_error"].to_numpy()
    assert np.all(np.diff(ranking_values) >= 0)


# =============================================================================
# Tests: interval and multi-series
# =============================================================================
def test_compare_propagates_interval_to_candidates():
    """
    Test that the `interval` argument flows into each candidate's plan.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        interval=[0.1, 0.9],
        show_progress=False,
    )

    for bt in result.candidates.values():
        assert bt.plan.interval == [0.1, 0.9]
        assert bt.plan.interval_method == "bootstrapping"


def test_compare_output_when_multi_series_wide():
    """
    Test that compare() ranks multi-series candidates using the pooled
    `'average'` metric row without a formatting error.
    """
    result = assistant.compare(
        data=df_multi_wide,
        cv=_single_cv(),
        target=["series_a", "series_b"],
        date_column="date",
        candidates=[
            ("multiseries", {"forecaster": "ForecasterRecursiveMultiSeries"})
        ],
        show_progress=False,
    )

    assert isinstance(result, ComparisonResult)
    assert list(result.results["rank"]) == [1]
    assert result.best_candidate is not None
    # The ranking value comes from the single-scalar aggregate, so it is
    # finite even though the raw metrics frame has multiple level rows.
    ranking_value = result.results[result.ranking_metric].iloc[0]
    assert np.isfinite(ranking_value)


# =============================================================================
# Tests: error handling during ranking
# =============================================================================
def test_compare_records_error_and_sorts_failed_candidate_last():
    """
    Test that a failing candidate records its error, is ranked last, and
    does not abort the comparison of the remaining candidates.
    """
    candidates = [
        ("good", {"forecaster": "ForecasterRecursive"}),
        ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
    ]

    with pytest.warns(CandidateFailedWarning, match="Candidate 'bad' failed"):
        result = assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=candidates,
            show_progress=False,
        )

    # The "error" column is present because one candidate failed
    assert "error" in result.results.columns

    good_row = result.results[result.results["name"] == "good"].iloc[0]
    bad_row = result.results[result.results["name"] == "bad"].iloc[0]
    assert good_row["rank"] == 1
    assert bad_row["rank"] == 2
    assert good_row["error"] is None
    assert isinstance(bad_row["error"], str) and bad_row["error"]
    assert np.isnan(bad_row["mean_absolute_error"])

    # The recorded error is a concise, single-line root-cause summary, not
    # the verbose generated-code execution wrapper.
    assert "\n" not in bad_row["error"]
    assert "Error executing generated forecasting code" not in bad_row["error"]
    assert "NotAReal" in bad_row["error"]
    # The failed row still reflects the requested estimator.
    assert bad_row["estimator"] == "NotAReal"

    # Only the successful candidate is present in `candidates`
    assert list(result.candidates) == ["good"]
    assert result.best_name == "good"
    assert result.best_candidate.plan.forecaster == "ForecasterRecursive"
    assert "1 configuration failed to run and is ranked last." in result.explanation


def test_compare_keeps_failure_snapshot_in_failures():
    """
    Test that a failed candidate is recorded in `failures` as a
    CandidateFailure carrying the root cause, the full traceback and the
    generated code that failed.
    """
    candidates = [
        ("good", {"forecaster": "ForecasterRecursive"}),
        ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
    ]

    with pytest.warns(CandidateFailedWarning):
        result = assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=candidates,
            show_progress=False,
        )

    assert list(result.failures) == ["bad"]
    failure = result.failures["bad"]
    assert isinstance(failure, CandidateFailure)
    assert "NotAReal" in failure.message
    assert "Traceback (most recent call last)" in failure.traceback
    assert failure.generated_code is not None
    # The recorded summary matches the 'error' column of the results table.
    bad_row = result.results[result.results["name"] == "bad"].iloc[0]
    assert bad_row["error"] == failure.summary()


def test_compare_failures_is_serializable():
    """
    Test that `failures` holds plain data, so a ComparisonResult stays
    JSON-serializable and does not pin the execution namespace of a
    failed candidate.
    """
    candidates = [
        ("good", {"forecaster": "ForecasterRecursive"}),
        ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
    ]

    with pytest.warns(CandidateFailedWarning):
        result = assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=candidates,
            show_progress=False,
        )

    dumped = {
        name: failure.model_dump(mode="json")
        for name, failure in result.failures.items()
    }

    assert json.loads(json.dumps(dumped))["bad"]["error_type"]


def test_compare_failures_empty_when_all_candidates_succeed():
    """
    Test that `failures` is an empty dict and no `'error'` column is added
    when every candidate runs successfully.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    assert result.failures == {}
    assert "error" not in result.results.columns


def test_compare_candidates_and_failures_partition_names():
    """
    Test that `candidates` and `failures` partition the candidate names:
    every requested name appears in exactly one of the two mappings.
    """
    candidates = [
        ("good", {"forecaster": "ForecasterRecursive"}),
        ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
    ]

    with pytest.warns(CandidateFailedWarning):
        result = assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=candidates,
            show_progress=False,
        )

    assert set(result.candidates) == {"good"}
    assert set(result.failures) == {"bad"}
    assert set(result.candidates) & set(result.failures) == set()
    assert set(result.candidates) | set(result.failures) == {"good", "bad"}
    assert set(result.results["name"]) == {"good", "bad"}


def test_ComparisonResult_ValidationError_when_candidates_empty():
    """
    Test that a ComparisonResult cannot be built with an empty
    `candidates` mapping, so `best_name` and `best_candidate` are always
    resolvable.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    fields = {
        "profile": result.profile,
        "cv_config": result.cv_config,
        "results": result.results,
        "candidates": {},
        "failures": result.failures,
        "ranking_metric": result.ranking_metric,
        "explanation": result.explanation,
    }

    with pytest.raises(ValidationError, match="candidates"):
        ComparisonResult(**fields)


def test_compare_AllCandidatesFailedError_when_all_candidates_fail():
    """
    Test that compare() raises AllCandidatesFailedError, carrying every
    candidate failure, when no candidate runs successfully.
    """
    candidates = [
        ("bad_1", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
        ("bad_2", {"forecaster": "ForecasterDirect", "estimator": "AlsoNotReal"}),
    ]

    with pytest.warns(CandidateFailedWarning):
        with pytest.raises(
            AllCandidatesFailedError,
            match="All 2 candidate configuration\\(s\\) failed to run",
        ) as excinfo:
            assistant.compare(
                data=df_single,
                cv=_single_cv(),
                target="sales",
                date_column="date",
                candidates=candidates,
                show_progress=False,
            )

    failures = excinfo.value.failures
    assert list(failures) == ["bad_1", "bad_2"]
    assert all(isinstance(f, CandidateFailure) for f in failures.values())
    assert "bad_1" in str(excinfo.value)
    assert "NotAReal" in str(excinfo.value)


# =============================================================================
# Tests: reuse of the winning configuration
# =============================================================================
def test_compare_best_candidate_reusable_in_backtest():
    """
    Test that the winning configuration's profile and plan can be fed back
    into backtest() to reproduce a result.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    best = result.best_candidate
    reused = assistant.backtest(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        profile=best.profile,
        plan=best.plan,
        show_progress=False,
    )

    assert isinstance(reused, BacktestResult)
    assert reused.plan.forecaster == best.plan.forecaster
