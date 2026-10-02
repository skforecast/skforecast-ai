# Unit test compare ForecastingAssistant

import ast
import json
import re
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from skforecast.exceptions import LongTrainingWarning, MissingValuesWarning
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.execution import comparison as comparison_module
from skforecast_ai.execution.comparison import (
    _comparison_family,
    add_baseline_candidate,
    aggregate_metrics,
    build_comparison_explanation,
    build_comparison_table,
    compare_sort_key,
    resolve_compare_candidates,
)

from skforecast_ai import (
    AllCandidatesFailedError,
    BacktestResult,
    CandidateFailedWarning,
    CandidateFailure,
    CompareProgress,
    ComparisonResult,
    DataNotFoundError,
    ForecastingAssistant,
    InvalidInputError,
    InvalidInputTypeError,
    MissingBackendWarning,
)

from tests.fixtures_assistant import (
    df_multi_wide,
    df_no_exog,
    df_single,
    df_with_missing,
)

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

    resolved = resolve_compare_candidates(None, profile)

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
        resolve_compare_candidates([], profile)


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
        resolve_compare_candidates(candidates, profile)


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
        resolve_compare_candidates(candidates, profile)


# =============================================================================
# Tests: metric aggregation (private helper)
# =============================================================================
def test_aggregate_metrics_single_series_uses_single_row():
    """
    Test that `aggregate_metrics` returns the single row's values for a
    single-series metrics frame.
    """
    metrics = pd.DataFrame({"mean_absolute_error": [0.5], "mean_squared_error": [0.25]})

    agg = aggregate_metrics(metrics)

    assert agg == {"mean_absolute_error": 0.5, "mean_squared_error": 0.25}


def test_aggregate_metrics_multi_series_uses_average_row():
    """
    Test that `aggregate_metrics` selects the `'average'` aggregate row
    for a multi-series metrics frame and drops the `'levels'` column.
    """
    metrics = pd.DataFrame(
        {
            "levels": ["series_a", "series_b", "average"],
            "mean_absolute_error": [0.2, 0.4, 0.3],
        }
    )

    agg = aggregate_metrics(metrics)

    assert "levels" not in agg
    assert agg == {"mean_absolute_error": 0.3}


def test_aggregate_metrics_empty_frame_returns_empty_dict():
    """
    Test that `aggregate_metrics` returns an empty dict for None or an
    empty frame.
    """
    assert aggregate_metrics(None) == {}
    assert aggregate_metrics(pd.DataFrame()) == {}


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
        baseline=False,
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
        baseline=False,
    )

    explanation = result.explanation
    best_name = result.results["name"].iloc[0]
    runner_name = result.results["name"].iloc[1]
    best_value = result.results["mean_absolute_error"].iloc[0]
    runner_value = result.results["mean_absolute_error"].iloc[1]
    expected_margin = 100 * (runner_value - best_value) / abs(runner_value)

    assert "Compared 2 configurations, ranked ascending by " in explanation
    assert "mean_absolute_error." in explanation
    assert "averaged across series" not in explanation
    assert "Shared cross-validation strategy: " in explanation
    assert "5-step horizon" in explanation
    assert f"Best: '{best_name}' (" in explanation
    assert f"= {best_value:.4f}" in explanation
    assert (
        f"{expected_margin:.1f}% ahead of '{runner_name}' ({runner_value:.4f})."
        in explanation
    )
    assert "failed to run" not in explanation


def test_compare_explanation_reports_averaged_metric_when_multi_series():
    """
    Test that the compare() explanation flags the ranking metric as
    averaged across series for multi-series tasks, the skforecast
    `average` row it is read from (not the `pooling` row).
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
    assert "averaged across series." in result.explanation
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
        baseline=False,
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
        baseline=False,
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
            baseline=False,
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
        (
            "bad",
            {
                "forecaster": "ForecasterRecursive",
                "estimator": "Ridge",
                "estimator_kwargs": {"alpha": "not-a-number"},
            },
        ),
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
    assert "alpha" in failure.message
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
            baseline=False,
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
                baseline=False,
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


def test_compare_output_when_profile_given_without_target():
    """
    Test that a supplied profile makes `target` and `date_column`
    optional for compare(), taking them from the profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    cv = TimeSeriesFold(steps=5, initial_train_size=60)

    result = assistant.compare(
        data=df_no_exog,
        cv=cv,
        candidates=[("recursive", {"forecaster": "ForecasterRecursive"})],
        profile=profile,
        show_progress=False,
    )

    assert result.profile is profile
    assert result.best_name == "recursive"


def test_compare_output_when_cv_result_given():
    """
    Test that compare() accepts a CVResult and applies its splitter to
    every candidate.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.compare(
        data=df_no_exog,
        cv=cv_result,
        candidates=[("recursive", {"forecaster": "ForecasterRecursive"})],
        profile=profile,
        show_progress=False,
    )

    assert result.cv_config == cv_result.cv_config


def test_compare_ValueError_when_multi_series_and_multivariate_are_mixed():
    """
    Test that a comparison mixing a multi-series candidate (scored on the
    average across series) with a multivariate one (scored on the single
    series it predicts) is rejected, since the ranking column would not
    measure the same thing for both.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    with pytest.raises(ValueError, match="mix forecaster families"):
        assistant.compare(
            data=df_multi_wide,
            cv=cv,
            profile=profile,
            candidates=[
                ("multi", {"forecaster": "ForecasterRecursiveMultiSeries"}),
                ("multivariate", {"forecaster": "ForecasterDirectMultiVariate"}),
            ],
            show_progress=False,
        )


def test_resolve_compare_candidates_auto_when_multi_series():
    """
    Test that the automatic candidates of a multi-series profile compare
    ForecasterRecursiveMultiSeries against ForecasterFoundation, both scored
    on the average across series, and leave out the multivariate
    alternative, which scores one series only.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )
    assert "ForecasterDirectMultiVariate" in profile.forecaster_candidates

    resolved = resolve_compare_candidates(None, profile)

    assert resolved == [
        ("ForecasterRecursiveMultiSeries", {"forecaster": "ForecasterRecursiveMultiSeries"}),
        ("ForecasterFoundation", {"forecaster": "ForecasterFoundation"}),
    ]


def test_resolve_compare_candidates_auto_varies_the_estimator_when_one_forecaster_left():
    """
    Test that when a single forecaster of the recommended family is left,
    the automatic candidates vary its estimator across the profile's
    estimator candidates, so the comparison still has more than one row.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    ).model_copy(update={"forecaster_candidates": [
        "ForecasterRecursiveMultiSeries", "ForecasterDirectMultiVariate"
    ]})

    resolved = resolve_compare_candidates(None, profile)

    assert [name for name, _ in resolved] == [
        f"ForecasterRecursiveMultiSeries+{estimator}"
        for estimator in profile.estimator_candidates
    ]
    assert all(
        config == {"forecaster": "ForecasterRecursiveMultiSeries", "estimator": estimator}
        for (_, config), estimator in zip(resolved, profile.estimator_candidates)
    )


@pytest.mark.parametrize(
    "forecaster, n_series, expected",
    [
        ("ForecasterFoundation", 1, "single-target"),
        ("ForecasterFoundation", 3, "multi-series"),
        ("ForecasterRecursive", 1, "single-target"),
        ("ForecasterRecursiveMultiSeries", 3, "multi-series"),
        ("ForecasterDirectMultiVariate", 3, "multivariate"),
        ("ForecasterUnknown", 1, None),
    ],
    ids=lambda dt: f"forecaster, n_series, expected: {dt}",
)
def test_comparison_family_output(forecaster, n_series, expected):
    """
    Test that the family of ForecasterFoundation follows the number of
    series, while the other forecasters keep a fixed family and an
    unknown forecaster has none.
    """
    assert _comparison_family(forecaster, n_series) == expected


def test_resolve_compare_candidates_accepts_foundation_with_multi_series_forecaster():
    """
    Test that ForecasterFoundation and ForecasterRecursiveMultiSeries can be
    compared on multi-series data, while ForecasterFoundation and the
    multivariate forecaster cannot.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )
    candidates = [
        ("multiseries", {"forecaster": "ForecasterRecursiveMultiSeries"}),
        ("foundation", {"forecaster": "ForecasterFoundation"}),
    ]

    resolved = resolve_compare_candidates(candidates, profile)

    assert resolved == candidates
    with pytest.raises(ValueError, match="Candidates mix forecaster families"):
        resolve_compare_candidates(
            [
                ("foundation", {"forecaster": "ForecasterFoundation"}),
                ("multivariate", {"forecaster": "ForecasterDirectMultiVariate"}),
            ],
            profile,
        )


def test_add_baseline_candidate_skips_baseline_when_foundation_on_multi_series():
    """
    Test that no baseline is added to a ForecasterFoundation candidate on
    multi-series data, where it is scored on the average across series.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )
    candidates = [("foundation", {"forecaster": "ForecasterFoundation"})]

    resolved, baseline_name, note = add_baseline_candidate(candidates, profile)

    assert resolved == candidates
    assert baseline_name is None
    assert note == (
        "No baseline: ForecasterEquivalentDate forecasts a single series, so "
        "it cannot be ranked against multi-series or multivariate candidates."
    )


# =============================================================================
# Tests: foundation backend
# =============================================================================
_MISSING_BACKEND_NOTE = (
    "ForecasterFoundation left out: its default model "
    "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
    "which is not installed (pip install skforecast-ai[foundation])."
)


@pytest.mark.parametrize(
    "installed, expected_excluded, expected_note",
    [
        (True, frozenset(), None),
        (False, frozenset({"ForecasterFoundation"}), _MISSING_BACKEND_NOTE),
    ],
    ids=["installed", "missing"],
)
def test_missing_foundation_backend_output(
    monkeypatch, installed, expected_excluded, expected_note
):
    """
    Test that the foundation forecaster is excluded, with a note naming the
    package to install, only when the backend of its default model is not
    installed.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: installed
    )
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")

    excluded, note = comparison_module.missing_foundation_backend(profile)

    assert excluded == expected_excluded
    assert note == expected_note


def test_missing_foundation_backend_output_when_no_foundation_candidate(monkeypatch):
    """
    Test that nothing is excluded when the profile has no foundation
    candidate, whether or not its backend is installed.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )
    profile = assistant.profile(
        data=df_no_exog, target="sales", date_column="date"
    ).model_copy(update={"forecaster_candidates": ["ForecasterRecursive"]})

    assert comparison_module.missing_foundation_backend(profile) == (frozenset(), None)


def test_resolve_compare_candidates_auto_when_forecaster_excluded():
    """
    Test that an excluded forecaster is left out of the auto candidates, so
    a multi-series profile without its foundation candidate falls back to
    varying the estimator of the multi-series forecaster.
    """
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )

    resolved = resolve_compare_candidates(
        None, profile, exclude=frozenset({"ForecasterFoundation"})
    )

    assert [name for name, _ in resolved] == [
        f"ForecasterRecursiveMultiSeries+{estimator}"
        for estimator in profile.estimator_candidates
    ]


def test_compare_MissingBackendWarning_when_foundation_backend_not_installed(
    monkeypatch,
):
    """
    Test that compare() without candidates leaves ForecasterFoundation out
    when its backend is not installed, warns with MissingBackendWarning and
    records the reason in the explanation, instead of failing the candidate.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    profile.forecaster_candidates = ["ForecasterRecursive", "ForecasterFoundation"]
    profile.estimator_candidates = ["Ridge"]

    with pytest.warns(MissingBackendWarning, match=re.escape(_MISSING_BACKEND_NOTE)):
        result = assistant.compare(
            data          = df_no_exog,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            profile       = profile,
            show_progress = False,
            baseline      = False,
        )

    assert list(result.results["name"]) == ["ForecasterRecursive"]
    assert result.failures == {}
    assert result.explanation.endswith(_MISSING_BACKEND_NOTE)


def test_compare_LongTrainingWarning_when_automatic_candidate_exceeds_fit_budget(
    monkeypatch,
):
    """
    Test that compare() without candidates leaves out an alternative whose
    estimator fits exceed the budget (ForecasterDirect refitted in 6 folds
    fits 5 estimators per training, 30 fits, above a budget patched to 10),
    warns with LongTrainingWarning and records the reason in the
    explanation. The recommended forecaster is kept.
    """
    monkeypatch.setattr(comparison_module, "COMPARE_FIT_BUDGET", 10)
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    profile.forecaster_candidates = ["ForecasterRecursive", "ForecasterDirect"]
    profile.estimator_candidates = ["Ridge"]
    cv = TimeSeriesFold(steps=5, initial_train_size=70, refit=True, verbose=False)

    budget_note = (
        "Left out of the automatic candidates because this cross-validation "
        "strategy exceeds the budget of 10 estimator fits: 'ForecasterDirect': "
        "ForecasterDirect will be fit 30 times (6 trainings x 5 estimators). "
        "Pass them in `candidates` to include them."
    )
    with pytest.warns(LongTrainingWarning, match=re.escape(budget_note)):
        result = assistant.compare(
            data          = df_no_exog,
            cv            = cv,
            target        = "sales",
            date_column   = "date",
            profile       = profile,
            show_progress = False,
            baseline      = False,
        )

    assert list(result.results["name"]) == ["ForecasterRecursive"]
    assert result.failures == {}
    assert result.explanation.endswith(budget_note)


def test_compare_LongTrainingWarning_when_automatic_stats_exceeds_fit_budget(
    monkeypatch,
):
    """
    Test that compare() without candidates counts one fit per fold for an
    automatic ForecasterStats candidate, which skforecast refits in every
    fold: with `refit=False` (1 training) and 6 folds it costs 6 fits, above
    a budget patched to 5, so it is left out with LongTrainingWarning while
    ForecasterRecursive, trained once, is kept.
    """
    monkeypatch.setattr(comparison_module, "COMPARE_FIT_BUDGET", 5)
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    profile.forecaster_candidates = ["ForecasterRecursive", "ForecasterStats"]
    profile.estimator_candidates = ["Ridge"]
    cv = TimeSeriesFold(steps=5, initial_train_size=70, refit=False, verbose=False)

    budget_note = (
        "Left out of the automatic candidates because this cross-validation "
        "strategy exceeds the budget of 5 estimator fits: 'ForecasterStats': "
        "ForecasterStats will be fit 6 times. "
        "Pass them in `candidates` to include them."
    )
    with pytest.warns(LongTrainingWarning, match=re.escape(budget_note)):
        result = assistant.compare(
            data          = df_no_exog,
            cv            = cv,
            target        = "sales",
            date_column   = "date",
            profile       = profile,
            show_progress = False,
            baseline      = False,
        )

    assert list(result.results["name"]) == ["ForecasterRecursive"]
    assert result.cv_config["n_fits"] == 1
    assert result.cv_config["n_folds"] == 6
    assert result.explanation.endswith(budget_note)


def test_compare_LongTrainingWarning_once_when_explicit_candidate_is_costly(
    monkeypatch,
):
    """
    Test that an explicit candidate is never left out for its cost, even
    above the budget, and that compare() warns once before running it
    instead of once more from its backtest.
    """
    monkeypatch.setattr(comparison_module, "COMPARE_FIT_BUDGET", 10)
    cv = TimeSeriesFold(steps=10, initial_train_size=40, refit=True, verbose=False)

    with pytest.warns(LongTrainingWarning) as record:
        result = assistant.compare(
            data          = df_no_exog,
            cv            = cv,
            target        = "sales",
            date_column   = "date",
            candidates    = [
                ("direct", {"forecaster": "ForecasterDirect", "lags": [1, 2, 3]})
            ],
            show_progress = False,
            baseline      = False,
        )

    messages = [
        str(w.message) for w in record if w.category is LongTrainingWarning
    ]
    assert len(messages) == 1
    assert messages[0].startswith(
        "ForecasterDirect will be fit 60 times (6 trainings x 10 estimators)."
    )
    assert list(result.results["name"]) == ["direct"]
    assert result.failures == {}


def test_build_comparison_explanation_notes_foundation_is_not_trained():
    """
    Test that the explanation says the shared window and refit settings do
    not apply to a ForecasterFoundation candidate, which is not trained.
    """
    ranked = [
        _ranked_entry("foundation", "ForecasterFoundation", 1.0),
        _ranked_entry("recursive", "ForecasterRecursive", 2.0),
    ]

    explanation = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = ranked,
        ranking_metric = "mean_absolute_error",
        any_error      = False,
        cv_explanation = "Initial training up to 2023-03-01, fixed window, no refit.",
    )

    assert (
        "Shared cross-validation strategy: Initial training up to 2023-03-01, "
        "fixed window, no refit. ForecasterFoundation is not trained: the "
        "window and refit settings do not apply to it, each fold forecasts "
        "from the observations before it. Best: 'foundation'"
    ) in explanation


@pytest.mark.parametrize(
    "fixed_train_size, window",
    [(True, "fixed"), (False, "expanding")],
    ids=["fixed window", "expanding window"],
)
def test_build_comparison_explanation_notes_stats_is_refitted_in_every_fold(
    fixed_train_size, window
):
    """
    Test that the explanation states that ForecasterStats is refitted in
    every fold, with its window type and number of trainings, before the
    best configuration sentence.
    """
    stats_backtest = SimpleNamespace(
        plan=SimpleNamespace(forecaster="ForecasterStats", estimator=None),
        metrics=None,
        cv_config={"fixed_train_size": fixed_train_size, "n_fits": 6},
    )
    ranked = [
        ("stats", stats_backtest, 1.0),
        _ranked_entry("recursive", "ForecasterRecursive", 2.0),
    ]

    explanation = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = ranked,
        ranking_metric = "mean_absolute_error",
        any_error      = False,
        cv_explanation = "Folds.",
    )

    assert (
        "Shared cross-validation strategy: Folds. ForecasterStats is "
        f"refitted in every fold on a {window} window (6 trainings): "
        "skforecast requires it for ARIMA models. Best: 'stats'"
    ) in explanation


# =============================================================================
# Tests: baseline
# =============================================================================
_CV_EXPLANATION = (
    "Using 70% of data (70 observations) for initial training, trained once "
    "(no refit), 5-step horizon, 6 folds."
)


def test_compare_output_when_baseline_added_by_default():
    """
    Test that compare() adds the seasonal naive baseline as one more ranked
    row by default and states by how much the best configuration beats it.
    On the linear fixture the baseline (offset 7) is off by 7 at every step.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    assert result.baseline_name == "Baseline (seasonal naive)"
    assert list(result.results["name"]) == [
        "recursive_default",
        "direct_ridge",
        "Baseline (seasonal naive)",
    ]
    baseline_row = result.results.iloc[2]
    assert baseline_row["forecaster"] == "ForecasterEquivalentDate"
    assert baseline_row["estimator"] is None
    assert baseline_row["mean_absolute_error"] == 7.0
    assert baseline_row["mean_squared_error"] == 49.0
    assert baseline_row["mean_absolute_scaled_error"] == 7.0

    baseline_plan = result.candidates["Baseline (seasonal naive)"].plan
    assert baseline_plan.forecaster_kwargs == {"offset": 7, "n_offsets": 1}

    assert result.explanation == (
        f"Compared 3 configurations, ranked ascending by mean_absolute_error. "
        f"Shared cross-validation strategy: {_CV_EXPLANATION} Best: "
        f"'recursive_default' (ForecasterRecursive / Ridge) = 0.3652, 22.5% "
        f"ahead of 'direct_ridge' (0.4711). 'recursive_default' beats the "
        f"baseline 'Baseline (seasonal naive)' (7.0000) by 94.8%."
    )


def test_compare_explanation_counts_candidates_behind_baseline():
    """
    Test that the explanation counts the configurations ranked below the
    baseline, which do not beat the naive reference.
    """
    candidates = [
        (
            "strong_ridge",
            {
                "forecaster": "ForecasterRecursive",
                "estimator": "Ridge",
                "estimator_kwargs": {"alpha": 1e6},
            },
        ),
        ("recursive_default", {"forecaster": "ForecasterRecursive"}),
    ]
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=candidates,
        show_progress=False,
    )

    assert list(result.results["name"]) == [
        "recursive_default",
        "Baseline (seasonal naive)",
        "strong_ridge",
    ]
    assert result.explanation.endswith(
        "'recursive_default' beats the baseline 'Baseline (seasonal naive)' "
        "(7.0000) by 94.8%. 1 configuration does not beat it."
    )


def test_compare_explanation_when_no_candidate_beats_baseline():
    """
    Test that the explanation says so when the baseline ranks first, and
    that the baseline is then the reusable best candidate.
    """
    candidates = [
        (
            "strong_ridge",
            {
                "forecaster": "ForecasterRecursive",
                "estimator": "Ridge",
                "estimator_kwargs": {"alpha": 1e6},
            },
        ),
    ]
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=candidates,
        show_progress=False,
    )

    assert result.best_name == "Baseline (seasonal naive)"
    assert result.best_candidate.plan.task_type == "baseline"
    assert result.explanation.endswith(
        "No configuration beats the baseline 'Baseline (seasonal naive)' "
        "(7.0000): the added complexity is not justified on this data."
    )


def test_compare_output_when_baseline_false():
    """
    Test that `baseline=False` leaves the candidates untouched and the
    explanation without any baseline sentence.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
        baseline=False,
    )

    assert result.baseline_name is None
    assert set(result.results["name"]) == {"recursive_default", "direct_ridge"}
    assert "baseline" not in result.explanation


def test_compare_uses_explicit_baseline_candidate_without_duplicating_it():
    """
    Test that a ForecasterEquivalentDate passed in `candidates` is used as
    the baseline and no second baseline row is added.
    """
    candidates = [
        ("naive_weekly", {"forecaster": "ForecasterEquivalentDate"}),
        ("recursive_default", {"forecaster": "ForecasterRecursive"}),
    ]
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=candidates,
        show_progress=False,
    )

    assert result.baseline_name == "naive_weekly"
    assert list(result.results["name"]) == ["recursive_default", "naive_weekly"]
    assert result.explanation.endswith(
        "'recursive_default' beats the baseline 'naive_weekly' (7.0000) by 94.8%."
    )


def test_compare_baseline_uses_conformal_intervals():
    """
    Test that the requested interval reaches the baseline with the conformal
    method while the ML candidates keep bootstrapping.
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

    methods = {name: bt.plan.interval_method for name, bt in result.candidates.items()}
    assert methods == {
        "recursive_default": "bootstrapping",
        "direct_ridge": "bootstrapping",
        "Baseline (seasonal naive)": "conformal",
    }


def test_compare_no_baseline_when_multi_series():
    """
    Test that no baseline is added for multi-series data, which
    ForecasterEquivalentDate cannot forecast, and that the explanation says
    why.
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

    assert result.baseline_name is None
    assert list(result.results["name"]) == ["multiseries"]
    assert result.explanation.endswith(
        "No baseline: ForecasterEquivalentDate forecasts a single series, so "
        "it cannot be ranked against multi-series or multivariate candidates."
    )


def test_compare_ValueError_when_candidate_uses_baseline_name():
    """
    Test that compare() rejects a candidate named like the baseline it
    would add, instead of producing two rows with the same name.
    """
    candidates = [
        ("Baseline (seasonal naive)", {"forecaster": "ForecasterRecursive"}),
    ]

    err_msg = re.escape(
        "The candidate name 'Baseline (seasonal naive)' is reserved for the "
        "baseline. Rename the candidate or pass `baseline=False`."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=candidates,
            show_progress=False,
        )


def test_compare_baseline_name_is_serialized():
    """
    Test that `baseline_name` is part of the JSON dump of the result.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    dumped = json.loads(result.model_dump_json())

    assert dumped["baseline_name"] == "Baseline (seasonal naive)"


def _ranked_entry(name: str, forecaster: str, value: float) -> tuple:
    """Build a `(name, backtest, value)` entry with the attributes the explanation reads."""
    backtest = SimpleNamespace(
        plan=SimpleNamespace(forecaster=forecaster, estimator=None),
        metrics=None,
    )
    return (name, backtest, value)


def test_build_comparison_explanation_when_baseline_failed():
    """
    Test that the explanation says the candidates cannot be checked against
    the baseline when the baseline failed to run.
    """
    explanation = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = [_ranked_entry("model", "ForecasterRecursive", 1.0)],
        ranking_metric = "mean_absolute_error",
        any_error      = True,
        cv_explanation = "Folds.",
        baseline_name  = "Baseline (naive)",
    )

    assert explanation == (
        "Compared 2 configurations, ranked ascending by mean_absolute_error. "
        "Shared cross-validation strategy: Folds. Best: 'model' "
        "(ForecasterRecursive) = 1.0000. The baseline 'Baseline (naive)' "
        "failed to run, so the candidates cannot be checked against it. "
        "1 configuration failed to run and is ranked last."
    )


def test_build_comparison_explanation_when_only_baseline_ran():
    """
    Test that the explanation says so when the baseline is the only
    configuration that ran successfully.
    """
    explanation = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = [
            _ranked_entry("Baseline (naive)", "ForecasterEquivalentDate", 2.0)
        ],
        ranking_metric = "mean_absolute_error",
        any_error      = True,
        cv_explanation = "Folds.",
        baseline_name  = "Baseline (naive)",
    )

    assert "Only the baseline 'Baseline (naive)' ran successfully." in explanation



def test_build_comparison_explanation_when_candidate_ties_baseline():
    """
    Test that a candidate tied with the baseline does not beat it, even when
    it is passed ranked above the baseline.
    """
    explanation = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = [
            _ranked_entry("model", "ForecasterRecursive", 2.0),
            _ranked_entry("Baseline (naive)", "ForecasterEquivalentDate", 2.0),
        ],
        ranking_metric = "mean_absolute_error",
        any_error      = False,
        cv_explanation = "Folds.",
        baseline_name  = "Baseline (naive)",
    )

    assert explanation.endswith(
        "No configuration beats the baseline 'Baseline (naive)' (2.0000): the "
        "added complexity is not justified on this data."
    )


def test_build_comparison_explanation_counts_tied_candidate_as_not_beating():
    """
    Test that only the candidates strictly better than the baseline count as
    beating it: a tied candidate ranked below it is counted with the ones
    that do not.
    """
    explanation = build_comparison_explanation(
        n_candidates   = 3,
        ranked         = [
            _ranked_entry("model_a", "ForecasterRecursive", 1.0),
            _ranked_entry("Baseline (naive)", "ForecasterEquivalentDate", 2.0),
            _ranked_entry("model_b", "ForecasterDirect", 2.0),
        ],
        ranking_metric = "mean_absolute_error",
        any_error      = False,
        cv_explanation = "Folds.",
        baseline_name  = "Baseline (naive)",
    )

    assert explanation.endswith(
        "'model_a' beats the baseline 'Baseline (naive)' (2.0000) by 50.0%. "
        "1 configuration does not beat it."
    )


@pytest.mark.parametrize(
    "baseline_value",
    [np.nan, np.inf],
    ids=lambda value: f"baseline_value: {value}",
)
def test_build_comparison_explanation_when_baseline_value_is_not_finite(
    baseline_value,
):
    """
    Test that no candidate is said to beat a baseline whose ranking value is
    NaN or infinite (for example MAPE on a series with zeros).
    """
    explanation = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = [
            _ranked_entry("model", "ForecasterRecursive", 1.0),
            _ranked_entry(
                "Baseline (naive)", "ForecasterEquivalentDate", baseline_value
            ),
        ],
        ranking_metric = "mean_absolute_percentage_error",
        any_error      = False,
        cv_explanation = "Folds.",
        baseline_name  = "Baseline (naive)",
    )

    assert explanation.endswith(
        "The baseline 'Baseline (naive)' has no finite "
        "mean_absolute_percentage_error, so the candidates cannot be checked "
        "against it."
    )


def test_add_baseline_candidate_ignores_unknown_forecaster():
    """
    Test that a candidate with an unknown forecaster name does not prevent
    the baseline: it has no family and fails on its own when run, so the
    baseline is still added and no multi-series note is given.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    candidates = [
        ("known", {"forecaster": "ForecasterRecursive"}),
        ("typo", {"forecaster": "ForecasterRecursve"}),
    ]

    resolved, baseline_name, note = add_baseline_candidate(candidates, profile)

    assert resolved == [
        *candidates,
        ("Baseline (seasonal naive)", {"forecaster": "ForecasterEquivalentDate"}),
    ]
    assert baseline_name == "Baseline (seasonal naive)"
    assert note is None


def test_add_baseline_candidate_skips_baseline_when_target_has_missing_values():
    """
    Test that no baseline is added when the target has missing values,
    which ForecasterEquivalentDate would repeat as missing predictions, and
    that the note says why.
    """
    with pytest.warns(MissingValuesWarning, match="pairwise deletion"):
        profile = assistant.profile(
            data=df_with_missing, target="sales", date_column="date"
        )
    candidates = [("recursive", {"forecaster": "ForecasterRecursive"})]

    resolved, baseline_name, note = add_baseline_candidate(candidates, profile)

    assert resolved == candidates
    assert baseline_name is None
    assert note == (
        "No baseline: the target has missing values or missing timestamps, "
        "and ForecasterEquivalentDate repeats a missing value as a missing "
        "prediction. Impute the target to compare the candidates against it."
    )


def test_build_comparison_table_ranks_baseline_first_on_tie():
    """
    Test that the baseline ranks above a candidate with the same ranking
    value, although the candidate was evaluated first, so a candidate ranks
    above the baseline only when it beats it.
    """
    def _row(name, forecaster, estimator, mae):
        row = {
            "name": name,
            "forecaster": forecaster,
            "estimator": estimator,
            "MAE": mae,
        }
        return (row, mae)

    rows = [
        _row("model_a", "ForecasterRecursive", "Ridge", 2.0),
        _row("model_b", "ForecasterDirect", "Ridge", 1.0),
        _row("Baseline (naive)", "ForecasterEquivalentDate", None, 2.0),
    ]

    results = build_comparison_table(
        rows           = rows,
        metric_columns = ["MAE"],
        any_error      = False,
        baseline_name  = "Baseline (naive)",
    )

    expected = pd.DataFrame(
        {
            "rank": [1, 2, 3],
            "name": ["model_b", "Baseline (naive)", "model_a"],
            "forecaster": [
                "ForecasterDirect",
                "ForecasterEquivalentDate",
                "ForecasterRecursive",
            ],
            "estimator": ["Ridge", None, "Ridge"],
            "MAE": [1.0, 2.0, 2.0],
        }
    )
    pd.testing.assert_frame_equal(results, expected)


def test_compare_sort_key_ranks_baseline_first_on_tie():
    """
    Test that sorting with `compare_sort_key` puts the baseline before a
    tied candidate and keeps NaN values last, matching the results table.
    """
    ranked = [
        ("model_a", None, 2.0),
        ("model_nan", None, float("nan")),
        ("Baseline (naive)", None, 2.0),
        ("model_b", None, 1.0),
    ]

    ranked_sorted = sorted(
        ranked, key=lambda item: compare_sort_key(item, "Baseline (naive)")
    )

    assert [name for name, _, _ in ranked_sorted] == [
        "model_b",
        "Baseline (naive)",
        "model_a",
        "model_nan",
    ]


def test_compare_ValueError_when_target_missing_in_test_folds():
    """
    Test that compare() stops before running any candidate when a test fold
    contains a missing timestamp, instead of failing every candidate with
    "Input contains NaN".
    """
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    data = pd.DataFrame(
        {"date": dates, "sales": np.arange(100, dtype=float)}
    ).drop(index=[85]).reset_index(drop=True)

    err_msg = re.escape(
        "The target has 1 missing value(s) in the test folds (2023-03-27 00:00:00)"
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.compare(
            data=data,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=_LIGHT_CANDIDATES,
            show_progress=False,
        )


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"metric": "f1_score"}, "Unknown metric 'f1_score'."),
        ({"metric": ["mean_absolute_error", "foo"]}, "Unknown metric 'foo'."),
        (
            {"interval": [5, 95]},
            "`interval` must be `[lower, upper]` with 0 < lower < upper < 1",
        ),
    ],
    ids=["classification score", "unknown metric", "percentile interval"],
)
def test_compare_ValueError_when_metric_or_interval_invalid(kwargs, match):
    """
    Test that compare() rejects an invalid metric or interval before any
    candidate runs, instead of failing every candidate and raising
    AllCandidatesFailedError.
    """
    with pytest.raises(ValueError, match=re.escape(match)):
        assistant.compare(
            data          = df_single,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            candidates    = _LIGHT_CANDIDATES,
            show_progress = False,
            **kwargs,
        )


# =============================================================================
# Tests: error code and field
# =============================================================================
@pytest.mark.parametrize(
    "candidates, error_class, err_msg",
    [
        ([], InvalidInputError, "`candidates` must not be an empty list."),
        (
            [("lgbm", "ForecasterRecursive")], InvalidInputTypeError,
            "Configuration for 'lgbm' must be a dict, got str.",
        ),
        (
            [("a", {"forecaster": "ForecasterRecursive"})] * 2, InvalidInputError,
            "Candidate names must be unique, found duplicates: ['a'].",
        ),
        (
            [("lgbm", {"bogus": 1})], InvalidInputError,
            "Invalid config keys for 'lgbm': ['bogus']. Allowed keys: "
            "['estimator', 'estimator_kwargs', 'forecaster', 'lags', "
            "'window_features'].",
        ),
    ],
    ids=["empty", "config_not_dict", "duplicate_names", "unknown_key"],
)
def test_compare_error_code_and_field_when_candidates_invalid(
    candidates, error_class, err_msg
):
    """
    Test that an invalid `candidates` list raises before any candidate runs,
    with the code 'invalid_argument' and `candidates` as field; a config
    that is not a dict keeps raising a TypeError.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    cv = assistant.create_cv(profile, plan)

    with pytest.raises(error_class, match=re.escape(err_msg)) as exc_info:
        assistant.compare(
            data=df_single, cv=cv, profile=profile, candidates=candidates
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "candidates"


@pytest.mark.parametrize(
    "error, expected_type",
    [
        (InvalidInputError("bad value"), "ValueError"),
        (InvalidInputTypeError("bad value"), "TypeError"),
        (DataNotFoundError("bad value"), "FileNotFoundError"),
    ],
    ids=["InvalidInputError", "InvalidInputTypeError", "DataNotFoundError"],
)
def test_candidate_failure_reports_input_errors_under_builtin_name(
    error, expected_type
):
    """
    Test that an input error of skforecast-ai is recorded under the built-in
    class it derives from, so the summaries of compare() keep the text they
    had before these errors had their own classes.
    """
    failure = CandidateFailure.from_exception(error)

    assert failure.error_type == expected_type
    assert failure.summary() == f"{expected_type}: bad value"


def test_compare_AllCandidatesFailedError_message_names_builtin_classes():
    """
    Test that the message of AllCandidatesFailedError, when the candidates
    are rejected by the input checks, names the built-in classes as before
    (`ValueError`), not the classes of skforecast-ai.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    cv = assistant.create_cv(profile, plan)

    err_msg = re.escape(
        "All 2 candidate configuration(s) failed to run, so there is no "
        "ranking to report.\n\n"
        "  - bad_lags: ValueError: `lags` must be positive integers (>= 1), "
        "got 0.\n"
        "  - bad_estimator: ValueError: 'Nope' is not a supported estimator."
    )
    with pytest.warns(CandidateFailedWarning):
        with pytest.raises(AllCandidatesFailedError, match=err_msg):
            assistant.compare(
                data          = df_single,
                cv            = cv,
                profile       = profile,
                show_progress = False,
                baseline      = False,
                candidates    = [
                    ("bad_lags", {"forecaster": "ForecasterRecursive", "lags": 0}),
                    (
                        "bad_estimator",
                        {"forecaster": "ForecasterRecursive", "estimator": "Nope"},
                    ),
                ],
            )


# =============================================================================
# Tests: progress_callback
# =============================================================================
def test_compare_progress_callback_receives_start_and_end_of_each_candidate():
    """
    Test that `progress_callback` receives a `CompareProgress` when each
    candidate starts and when it ends, in the order the candidates run,
    with the baseline counted in `total`.
    """
    events = []
    assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
        progress_callback=events.append,
    )

    baseline = "Baseline (seasonal naive)"
    expected = [
        CompareProgress(
            candidate="recursive_default", status="started", completed=0, total=3
        ),
        CompareProgress(
            candidate="recursive_default", status="succeeded", completed=1, total=3
        ),
        CompareProgress(
            candidate="direct_ridge", status="started", completed=1, total=3
        ),
        CompareProgress(
            candidate="direct_ridge", status="succeeded", completed=2, total=3
        ),
        CompareProgress(candidate=baseline, status="started", completed=2, total=3),
        CompareProgress(candidate=baseline, status="succeeded", completed=3, total=3),
    ]
    assert events == expected


def test_compare_progress_callback_reports_failed_candidate_with_its_error():
    """
    Test that a failed candidate ends with a `'failed'` event whose `error`
    is the text of the `error` column of the results table.
    """
    candidates = [
        ("good", {"forecaster": "ForecasterRecursive"}),
        ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
    ]
    events = []
    with pytest.warns(CandidateFailedWarning, match="Candidate 'bad' failed"):
        result = assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=candidates,
            show_progress=False,
            baseline=False,
            progress_callback=events.append,
        )

    bad_error = result.results.set_index("name").loc["bad", "error"]
    assert [(e.candidate, e.status, e.error) for e in events] == [
        ("good", "started", None),
        ("good", "succeeded", None),
        ("bad", "started", None),
        ("bad", "failed", bad_error),
    ]


def test_compare_progress_callback_exception_cancels_remaining_candidates():
    """
    Test that an exception raised by `progress_callback` is not recorded as
    a candidate failure: it propagates unchanged and no further candidate
    runs, which is how a caller cancels a comparison.
    """

    class Cancelled(Exception):
        pass

    events = []

    def callback(event):
        events.append(event)
        if event.status == "succeeded":
            raise Cancelled("stop")

    with pytest.raises(Cancelled, match="stop"):
        assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=_LIGHT_CANDIDATES,
            show_progress=False,
            baseline=False,
            progress_callback=callback,
        )

    assert [(e.candidate, e.status) for e in events] == [
        ("recursive_default", "started"),
        ("recursive_default", "succeeded"),
    ]


def test_compare_progress_callback_does_not_change_the_result():
    """
    Test that passing `progress_callback` returns the same table,
    explanation, CV and candidate predictions as a call without it.
    """
    kwargs = dict(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )
    without = assistant.compare(**kwargs)
    with_callback = assistant.compare(**kwargs, progress_callback=lambda e: None)

    pd.testing.assert_frame_equal(with_callback.results, without.results)
    assert with_callback.explanation == without.explanation
    assert with_callback.cv_config == without.cv_config
    assert list(with_callback.candidates) == list(without.candidates)
    for name, bt in without.candidates.items():
        pd.testing.assert_frame_equal(
            with_callback.candidates[name].predictions, bt.predictions
        )
        assert with_callback.candidates[name].code == bt.code


def test_compare_TypeError_when_progress_callback_is_not_callable():
    """
    Test that a `progress_callback` that is not callable raises
    InvalidInputTypeError (a TypeError) naming the field, before any
    candidate runs.
    """
    err_msg = re.escape("`progress_callback` must be callable or None, got str.")
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=_LIGHT_CANDIDATES,
            show_progress=False,
            progress_callback="report",
        )

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "progress_callback"


def test_compare_progress_callback_exception_closes_progress_bar(monkeypatch):
    """
    Test that when `progress_callback` cancels the comparison with
    `show_progress=True`, the progress bar is closed before the exception
    propagates, instead of staying open on a partial count.
    """
    import tqdm.auto

    bars = []

    class RecordingBar(tqdm.auto.tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, disable=True, **kwargs)
            self.close_calls = 0
            bars.append(self)

        def close(self):
            self.close_calls += 1
            super().close()

    monkeypatch.setattr(tqdm.auto, "tqdm", RecordingBar)

    def callback(event):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=_LIGHT_CANDIDATES,
            show_progress=True,
            baseline=False,
            progress_callback=callback,
        )

    assert len(bars) == 1
    assert bars[0].close_calls >= 1


def test_compare_candidate_scripts_load_csv_path_that_ran(tmp_path):
    """
    Test that compare() with a CSV path records it in the shared profile,
    so the script of every candidate, the baseline included, loads it.
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)

    result = assistant.compare(
        data=csv_path,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
    )

    assert result.profile.data_profile.data_path == str(csv_path)
    assert len(result.candidates) == 3
    for bt in result.candidates.values():
        assert f"data = pd.read_csv({str(csv_path)!r})" in bt.code
