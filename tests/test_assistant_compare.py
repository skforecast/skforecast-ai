# Unit test compare ForecastingAssistant

import ast
import json
import re
import warnings
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from skforecast.exceptions import (
    IgnoredArgumentWarning,
    LongTrainingWarning,
    MissingValuesWarning,
)
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
    CostNotConfirmedError,
    DataNotFoundError,
    ForecastingAssistant,
    IntervalCoverageWarning,
    InvalidInputError,
    InvalidInputTypeError,
    MissingBackendWarning,
    PlanEditsDiscardedWarning,
)

from tests.fixtures_csv_dialect import df_dialect, write_dialect
from tests.fixtures_compare import (
    cv_h2o_refined,
    cv_multivariate,
    cv_sales,
    cv_sales_direct,
    cv_sales_direct_default_refit,
    cv_sales_direct_refit,
    cv_sales_forest,
    cv_sales_refined,
    plan_h2o_refined,
    plan_sales_edited,
    profile_h2o,
    profile_multi,
    profile_sales,
    profile_sales_one_forecaster,
)
from tests.fixtures_datasets import (
    df_h2o,
    df_h2o_daily,
    df_items_sales_long,
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


def test_compare_ValueError_when_metric_is_repeated():
    """
    Test that compare() rejects a metric listed twice before any candidate
    runs (the backtest failed with a TypeError of pandas).
    """
    err_msg = re.escape(
        "`metric` repeats ['mean_squared_error']: list each metric once."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            candidates=_LIGHT_CANDIDATES,
            metric=["mean_squared_error", "mean_squared_error"],
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


def test_compare_explanation_says_tied_when_best_and_runner_up_have_same_value():
    """
    Test that the compare() explanation says the best candidate is tied
    with the runner-up when both have the same value of the ranking
    metric, instead of quoting a margin of 0.0%.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=[
            ("first", {"forecaster": "ForecasterRecursive"}),
            ("second", {"forecaster": "ForecasterRecursive"}),
        ],
        show_progress=False,
        baseline=False,
    )

    value = result.results["mean_absolute_error"].iloc[0]

    assert result.results["mean_absolute_error"].iloc[1] == value
    assert (
        f"Best: 'first' (ForecasterRecursive / Ridge) = {value:.4f}, "
        f"tied with 'second' ({value:.4f})."
        in result.explanation
    )
    assert "ahead of" not in result.explanation


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
    # The metric is a decision of each candidate plan, so refine_plan()
    # keeps it in the plan of the winner.
    assert result.best_candidate.plan.metrics_to_compute == [
        "mean_squared_error", "mean_absolute_error"
    ]
    assert "metric" in result.best_candidate.plan.overridden_fields


def test_compare_output_when_metric_is_rmse():
    """
    Test that `root_mean_squared_error` ranks the table and is the square
    root of the MSE of every candidate.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        metric=["root_mean_squared_error", "mean_squared_error"],
        show_progress=False,
    )

    assert result.ranking_metric == "root_mean_squared_error"
    assert list(result.results.columns) == [
        "rank",
        "name",
        "forecaster",
        "estimator",
        "root_mean_squared_error",
        "mean_squared_error",
    ]
    ranking_values = result.results["root_mean_squared_error"].to_numpy()
    assert np.all(np.diff(ranking_values) >= 0)
    np.testing.assert_allclose(
        ranking_values, np.sqrt(result.results["mean_squared_error"].to_numpy())
    )


# =============================================================================
# Tests: interval and multi-series
# =============================================================================
def test_compare_propagates_interval_to_candidates():
    """
    Test that the `interval` argument flows into each candidate's plan.
    """
    with pytest.warns(IntervalCoverageWarning, match="in these candidates"):
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


@pytest.mark.parametrize("with_profile", [True, False], ids=["profile", "no_profile"])
def test_compare_output_when_long_format_multiindex(with_profile):
    """
    Test that compare() ranks the candidates of long-format data indexed by
    a (series, date) MultiIndex as those of the same data with the levels as
    columns, which is how their scripts read the frame saved with
    `to_csv()`. Before, every candidate failed in the executed script
    (KeyError: 'date') and compare() raised AllCandidatesFailedError.
    """
    candidates = [
        (
            "multiseries_ridge",
            {"forecaster": "ForecasterRecursiveMultiSeries", "estimator": "Ridge"},
        )
    ]
    cv = TimeSeriesFold(steps=5, initial_train_size=80, verbose=False)
    expected = assistant.compare(
        data             = df_items_sales_long,
        target           = "value",
        date_column      = "date",
        series_id_column = "series",
        cv               = cv,
        candidates       = candidates,
        show_progress    = False,
    )
    data = df_items_sales_long.set_index(["series", "date"])
    if with_profile:
        kwargs = {"profile": assistant.profile(data=data, target="value")}
    else:
        kwargs = {"target": "value"}

    result = assistant.compare(
        data=data, cv=cv, candidates=candidates, show_progress=False, **kwargs
    )

    pd.testing.assert_frame_equal(result.results, expected.results)
    assert (
        result.candidates["multiseries_ridge"].code
        == expected.candidates["multiseries_ridge"].code
    )


@pytest.mark.parametrize("with_profile", [True, False], ids=["profile", "no_profile"])
def test_compare_InvalidInputError_when_multiindex_level_unnamed(with_profile):
    """
    Test that compare() rejects long-format data indexed by a MultiIndex with
    a level without a name, also with a profile of the same data with named
    levels, before any candidate runs: their scripts read the levels by name
    from the frame saved with `to_csv()`, which writes an empty header for
    them.
    """
    data = df_items_sales_long.set_index(["series", "date"])
    kwargs = {"target": "value"}
    if with_profile:
        kwargs = {"profile": assistant.profile(data=data, target="value")}
    cv = TimeSeriesFold(steps=5, initial_train_size=80, verbose=False)
    err_msg = re.escape(
        "`data` is indexed by a MultiIndex with levels without a name "
        "(names [None, 'date'])."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.compare(
            data          = data.rename_axis([None, "date"]),
            cv            = cv,
            show_progress = False,
            **kwargs,
        )

    assert exc_info.value.field == "data"


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


def test_compare_CostNotConfirmedError_when_explicit_candidate_is_costly(
    monkeypatch,
):
    """
    Test that an explicit candidate is never left out for its cost, even
    above the budget: compare() raises CostNotConfirmedError before running
    it, and runs it, without a LongTrainingWarning from its backtest, once
    `confirm_cost` is the figure of the cost.
    """
    monkeypatch.setattr(comparison_module, "COMPARE_FIT_BUDGET", 10)
    cv = TimeSeriesFold(steps=10, initial_train_size=40, refit=True, verbose=False)
    kwargs = dict(
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

    err_msg = re.escape(
        "The comparison will fit 60 estimators in all ('direct': 60 "
        "(6 trainings x 10 estimators))."
    )
    with pytest.raises(CostNotConfirmedError, match=err_msg) as exc_info:
        assistant.compare(**kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter("error", category=LongTrainingWarning)
        result = assistant.compare(**kwargs, confirm_cost=60)

    assert exc_info.value.figure == 60
    assert list(result.results["name"]) == ["direct"]
    assert result.failures == {}


def test_compare_CostNotConfirmedError_when_candidates_add_up_above_threshold():
    """
    Test that explicit candidates that fit fewer than 50 estimators each
    (36, 36 and 6) but 78 together make compare() raise
    CostNotConfirmedError before running, with the total, what each
    candidate adds and the changes that lower it, and that the error and
    `result.cost` of the run confirmed with that figure have the same
    values.
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=64, refit=True, verbose=False)
    kwargs = dict(
        data          = df_no_exog,
        cv            = cv,
        target        = "sales",
        date_column   = "date",
        candidates    = [
            ("direct_a", {"forecaster": "ForecasterDirect", "lags": [1, 2, 3]}),
            (
                "direct_b",
                {"forecaster": "ForecasterDirect", "lags": [1, 2],
                 "estimator": "Ridge"},
            ),
            ("recursive", {"forecaster": "ForecasterRecursive"}),
        ],
        show_progress = False,
        baseline      = False,
    )

    err_msg = re.escape(
        "This comparison is above the threshold of an expensive run (50 "
        "estimator fits or 2000 inference windows), so it needs a confirmation "
        "and nothing ran. The comparison will fit 78 estimators in all "
        "('direct_a': 36 (6 trainings x 6 estimators), 'direct_b': 36 (6 "
        "trainings x 6 estimators), 'recursive': 6). It can take substantial "
        "amounts of time. If not feasible, compare fewer candidates or use an "
        "integer `refit` (retrain every n folds), fewer folds (a later "
        "`initial_train_size`, a larger `fold_stride` or `skip_folds`) or "
        "`refit=False` (train once)."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        assistant.compare(**kwargs)
    result = assistant.compare(**kwargs, confirm_cost=78)

    error = exc_info.value
    assert error.figure == 78
    assert error.cost == {
        "n_folds": 6, "n_fits": 18, "estimator_fits": 78, "inference_windows": 0
    }
    assert error.comparison_cost == result.cost
    assert result.failures == {}
    assert result.cost.model_dump() == {
        "n_folds": 6,
        "candidates": {
            "direct_a": {
                "forecaster": "ForecasterDirect", "n_fits": 6,
                "estimator_fits": 36, "inference_windows": 0,
            },
            "direct_b": {
                "forecaster": "ForecasterDirect", "n_fits": 6,
                "estimator_fits": 36, "inference_windows": 0,
            },
            "recursive": {
                "forecaster": "ForecasterRecursive", "n_fits": 6,
                "estimator_fits": 6, "inference_windows": 0,
            },
        },
        "n_fits": 18,
        "estimator_fits": 78,
        "inference_windows": 0,
    }


@pytest.mark.parametrize("confirm_cost", [False, 77], ids=["false", "another"])
def test_compare_CostNotConfirmedError_when_confirm_cost_is_not_the_figure(
    confirm_cost,
):
    """
    Test that compare() above the threshold does not run with
    `confirm_cost=False` nor with a figure other than that of its cost (77
    for 78 estimator fits), and that the second error says the strategy or
    the candidates changed.
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=64, refit=True, verbose=False)
    events = []

    with pytest.raises(CostNotConfirmedError) as exc_info:
        assistant.compare(
            data              = df_no_exog,
            cv                = cv,
            target            = "sales",
            date_column       = "date",
            candidates        = [
                ("direct_a", {"forecaster": "ForecasterDirect", "lags": 3}),
                ("direct_b", {"forecaster": "ForecasterDirect", "lags": 2}),
                ("recursive", {"forecaster": "ForecasterRecursive"}),
            ],
            show_progress     = False,
            baseline          = False,
            progress_callback = events.append,
            confirm_cost      = confirm_cost,
        )

    mismatch = (
        "`confirm_cost=77` does not confirm it: the figure of this cost is 78, "
        "so the strategy or the candidates changed since that number was given."
    )
    assert exc_info.value.figure == 78
    assert str(exc_info.value).endswith(mismatch) == (confirm_cost == 77)
    assert events == []


def test_compare_ignores_confirm_cost_below_threshold():
    """
    Test that compare() whose candidates together fit 50 estimators or fewer
    runs whatever `confirm_cost` says, also a figure that is not its cost.
    """
    result = assistant.compare(
        data          = df_single,
        cv            = _single_cv(),
        target        = "sales",
        date_column   = "date",
        candidates    = _LIGHT_CANDIDATES,
        show_progress = False,
        confirm_cost  = 3,
    )

    assert result.cost.estimator_fits == 6
    assert result.failures == {}


@pytest.mark.parametrize(
    "confirm_cost, error",
    [("yes", InvalidInputTypeError), (-5, InvalidInputError)],
    ids=["text", "negative"],
)
def test_compare_InvalidInputError_when_confirm_cost_is_not_valid(
    confirm_cost, error
):
    """
    Test that compare() rejects a `confirm_cost` that is neither a bool nor
    an integer of at least 0 before anything runs, also below the
    threshold.
    """
    with pytest.raises(error, match=re.escape("`confirm_cost` must be")) as exc_info:
        assistant.compare(
            data          = df_single,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            candidates    = _LIGHT_CANDIDATES,
            show_progress = False,
            confirm_cost  = confirm_cost,
        )

    assert exc_info.value.field == "confirm_cost"


def test_compare_builds_every_plan_before_counting_and_running():
    """
    Test that compare() builds the plan of every candidate before it counts
    the cost: a candidate whose plan cannot be built fails then, with its
    CandidateFailedWarning before the cost is checked, is not counted, and
    nothing runs (no progress event) when the others are above the
    threshold, as the error says.
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=64, refit=True, verbose=False)
    events = []

    with pytest.warns(
        CandidateFailedWarning, match=re.escape("Candidate 'bad' failed")
    ):
        with pytest.raises(CostNotConfirmedError) as exc_info:
            assistant.compare(
                data              = df_no_exog,
                cv                = cv,
                target            = "sales",
                date_column       = "date",
                candidates        = [
                    ("direct_a", {"forecaster": "ForecasterDirect", "lags": 3}),
                    ("bad", {"estimator": "NoSuchEstimator"}),
                    ("direct_b", {"forecaster": "ForecasterDirect", "lags": 2}),
                ],
                show_progress     = False,
                baseline          = False,
                progress_callback = events.append,
            )

    assert exc_info.value.figure == 72
    assert list(exc_info.value.comparison_cost.candidates) == [
        "direct_a", "direct_b"
    ]
    assert str(exc_info.value.description).endswith(
        "'bad' is not counted: its plan cannot be built, so it runs nothing."
    )
    assert events == []


def test_compare_candidate_with_invalid_plan_fails_before_any_candidate_runs():
    """
    Test that the CandidateFailedWarning of a candidate whose plan cannot be
    built comes before the first candidate runs, that its two progress
    events still come at its turn, in the order of the candidates, that it
    is not in `cost` and that `failures` keeps the order of the candidates
    when another one fails later, while running (a direct forecaster with a
    gap).
    """
    candidates = [
        ("direct", {"forecaster": "ForecasterDirect", "estimator": "Ridge"}),
        ("recursive", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
        ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
    ]
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=2, verbose=False)
    events = []

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        def record(event):
            failed = [
                str(w.message).split(":")[0] for w in caught
                if issubclass(w.category, CandidateFailedWarning)
            ]
            events.append((event.candidate, event.status, failed))

        result = assistant.compare(
            data              = df_single,
            cv                = cv,
            target            = "sales",
            date_column       = "date",
            candidates        = candidates,
            show_progress     = False,
            baseline          = False,
            progress_callback = record,
        )

    bad = "Candidate 'bad' failed and is ranked last"
    direct = "Candidate 'direct' failed and is ranked last"
    assert events == [
        ("direct", "started", [bad]),
        ("direct", "failed", [bad, direct]),
        ("recursive", "started", [bad, direct]),
        ("recursive", "succeeded", [bad, direct]),
        ("bad", "started", [bad, direct]),
        ("bad", "failed", [bad, direct]),
    ]
    assert list(result.cost.candidates) == ["direct", "recursive"]
    assert list(result.failures) == ["direct", "bad"]
    assert result.failures["bad"].generated_code is None
    assert list(result.results["name"]) == ["recursive", "direct", "bad"]


def test_compare_cost_counts_the_baseline_and_matches_what_ran():
    """
    Test that `result.cost` counts the baseline with 0 estimator fits, that
    the totals are the sum of the candidates, and that the trainings counted
    before running equal the `n_fits` of the `cv_config` of each candidate
    that ran: one per fold for ForecasterStats (6), one for the others
    (`refit=False`), including a candidate with its own differentiation.
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=64, refit=False, verbose=False)

    result = assistant.compare(
        data          = df_no_exog,
        cv            = cv,
        target        = "sales",
        date_column   = "date",
        candidates    = [
            ("stats", {"forecaster": "ForecasterStats"}),
            (
                "diff",
                {"forecaster": "ForecasterDirect", "differentiation": 1,
                 "lags": [1, 2]},
            ),
            ("recursive", {"forecaster": "ForecasterRecursive"}),
        ],
        show_progress = False,
    )

    assert result.failures == {}
    assert result.cost.model_dump() == {
        "n_folds": 6,
        "candidates": {
            "stats": {
                "forecaster": "ForecasterStats", "n_fits": 6,
                "estimator_fits": 6, "inference_windows": 0,
            },
            "diff": {
                "forecaster": "ForecasterDirect", "n_fits": 1,
                "estimator_fits": 6, "inference_windows": 0,
            },
            "recursive": {
                "forecaster": "ForecasterRecursive", "n_fits": 1,
                "estimator_fits": 1, "inference_windows": 0,
            },
            "Baseline (seasonal naive)": {
                "forecaster": "ForecasterEquivalentDate", "n_fits": 1,
                "estimator_fits": 0, "inference_windows": 0,
            },
        },
        "n_fits": 9,
        "estimator_fits": 13,
        "inference_windows": 0,
    }
    assert result.candidates["diff"].cv_config["differentiation"] == 1
    assert set(result.cost.candidates) == set(result.candidates)
    for name, candidate in result.candidates.items():
        assert result.cost.candidates[name].n_fits == candidate.cv_config["n_fits"]


def test_compare_cost_leaves_out_the_baseline_when_baseline_is_false():
    """
    Test that `result.cost` has only the candidates given when
    `baseline=False`.
    """
    result = assistant.compare(
        data          = df_single,
        cv            = _single_cv(),
        target        = "sales",
        date_column   = "date",
        candidates    = _LIGHT_CANDIDATES,
        show_progress = False,
        baseline      = False,
    )

    assert list(result.cost.candidates) == ["recursive_default", "direct_ridge"]
    assert result.cost.n_folds == 6
    assert result.cost.n_fits == 2
    assert result.cost.estimator_fits == 6


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
        f"ahead of 'direct_ridge' (0.4711). Both configurations beat the "
        f"baseline 'Baseline (seasonal naive)' (7.0000). The best, "
        f"'recursive_default', beats it by 94.8%."
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
        "1 of 2 configurations beats the baseline 'Baseline (seasonal naive)' "
        "(7.0000): 'recursive_default', by 94.8%."
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
    with pytest.warns(IntervalCoverageWarning, match="in these candidates"):
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
        "1 of 2 configurations beats the baseline 'Baseline (naive)' (2.0000): "
        "'model_a', by 50.0%."
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
    with pytest.warns(MissingValuesWarning, match="Only the pairs where both values are finite"):
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
        "The target has 1 missing value(s) in test fold 4 of 6 (2023-03-27 "
        "00:00:00)"
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
            "['calendar_features', 'differentiation', 'dropna_from_series', "
            "'estimator', 'estimator_kwargs', 'forecaster', 'lags', "
            "'target_transformer', 'use_exog', 'window_features'].",
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


# =============================================================================
# Tests: early input checks
# =============================================================================
@pytest.mark.parametrize(
    "cv, type_name",
    [({"steps": 5}, "dict"), (None, "NoneType"), (5, "int")],
    ids=["dict", "None", "int"],
)
def test_compare_InvalidInputTypeError_when_cv_wrong_type(cv, type_name):
    """
    Test that compare() raises InvalidInputTypeError (a TypeError) with the
    field 'cv' when it is not a TimeSeriesFold or a CVResult.
    """
    err_msg = re.escape(
        f"`cv` must be a skforecast TimeSeriesFold or the CVResult of "
        f"create_cv(), got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        assistant.compare(
            data          = df_single,
            cv            = cv,
            target        = "sales",
            date_column   = "date",
            candidates    = _LIGHT_CANDIDATES,
            show_progress = False,
        )

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "cv"


def test_compare_output_when_interval_asymmetric_and_baseline_requested():
    """
    Test that compare() with an asymmetric interval leaves the baseline out,
    since ForecasterEquivalentDate predicts symmetric intervals only, and
    says so in the explanation, without any candidate failing.
    """
    with pytest.warns(IntervalCoverageWarning, match="in these candidates"):
        result = assistant.compare(
            data          = df_single,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            candidates    = [("ridge", {"forecaster": "ForecasterRecursive"})],
            interval      = [0.1, 0.8],
            show_progress = False,
        )

    assert result.baseline_name is None
    assert list(result.results["name"]) == ["ridge"]
    assert result.failures == {}
    assert result.explanation.endswith(
        "No baseline: ForecasterEquivalentDate predicts symmetric intervals "
        "only (lower + upper = 1), and the interval is [0.1, 0.8]. Pass a "
        "symmetric interval, such as [0.1, 0.9], to compare the candidates "
        "against it."
    )


def test_compare_output_when_interval_symmetric_adds_baseline():
    """
    Test that compare() with a symmetric interval still adds the baseline.
    """
    with pytest.warns(IntervalCoverageWarning, match="in these candidates"):
        result = assistant.compare(
            data          = df_single,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            candidates    = [("ridge", {"forecaster": "ForecasterRecursive"})],
            interval      = [0.1, 0.9],
            show_progress = False,
        )

    assert result.baseline_name == "Baseline (seasonal naive)"
    assert list(result.results["name"]) == ["ridge", "Baseline (seasonal naive)"]


@pytest.mark.parametrize(
    "interval, expected_baseline",
    [
        (None, "Baseline (seasonal naive)"),
        ([0.1, 0.9], "Baseline (seasonal naive)"),
        ([0.05, 0.95], "Baseline (seasonal naive)"),
        ([0.1, 0.8], None),
        ([0.2, 0.7], None),
    ],
    ids=lambda value: f"interval: {value}",
)
def test_add_baseline_candidate_output_when_interval(interval, expected_baseline):
    """
    Test that the baseline is added unless the interval is asymmetric
    (lower + upper different from 1), which its conformal intervals cannot
    predict.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    candidates = [("recursive", {"forecaster": "ForecasterRecursive"})]

    resolved, baseline_name, note = add_baseline_candidate(
        candidates, profile, interval
    )

    assert baseline_name == expected_baseline
    if expected_baseline is None:
        assert resolved == candidates
        assert note == (
            f"No baseline: ForecasterEquivalentDate predicts symmetric "
            f"intervals only (lower + upper = 1), and the interval is "
            f"{interval}. Pass a symmetric interval, such as [0.1, 0.9], to "
            f"compare the candidates against it."
        )
    else:
        assert resolved == [
            *candidates,
            (
                "Baseline (seasonal naive)",
                {"forecaster": "ForecasterEquivalentDate"},
            ),
        ]
        assert note is None


def test_compare_CandidateFailedWarning_when_foundation_backend_not_installed(
    monkeypatch,
):
    """
    Test that an explicit ForecasterFoundation candidate whose backend is not
    installed fails with the install message (CandidateFailedWarning) and is
    ranked last, while the other candidates are ranked.
    """
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )
    candidates = [
        ("ridge", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
        ("foundation", {"forecaster": "ForecasterFoundation"}),
    ]

    warn_msg = re.escape(
        "Candidate 'foundation' failed and is ranked last: ValueError: "
        "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
        "which is not installed (pip install \"chronos-forecasting\")."
    )
    with pytest.warns(CandidateFailedWarning, match=warn_msg):
        result = assistant.compare(
            data          = df_single,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            candidates    = candidates,
            show_progress = False,
            baseline      = False,
        )

    assert list(result.results["name"]) == ["ridge", "foundation"]
    assert list(result.candidates) == ["ridge"]
    assert list(result.failures) == ["foundation"]
    assert result.best_name == "ridge"


def test_compare_CostNotConfirmedError_when_foundation_candidate_inference_windows_exceed_threshold(
    monkeypatch,
):
    """
    Test that compare() raises CostNotConfirmedError before running when a
    ForecasterFoundation candidate forecasts more inference windows (series
    times folds of the shared strategy) than the threshold (lowered to 3
    here), with the windows as the figure, since the other candidates fit
    their estimator once.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 3)
    candidates = [
        ("ridge", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
        ("foundation", {"forecaster": "ForecasterFoundation"}),
    ]

    err_msg = re.escape(
        "This comparison is above the threshold of an expensive run (50 "
        "estimator fits or 3 inference windows), so it needs a confirmation "
        "and nothing ran. ForecasterFoundation will forecast up to 6 inference "
        "windows (1 series x 6 folds). It can take substantial amounts of "
        "time. If not feasible, compare fewer candidates or use fewer folds (a "
        "later `initial_train_size`, a larger `fold_stride` or `skip_folds`) "
        "or fewer series."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        assistant.compare(
            data          = df_single,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            candidates    = candidates,
            show_progress = False,
            baseline      = False,
        )

    assert exc_info.value.figure == 6


def test_compare_CostNotConfirmedError_adds_up_the_foundation_candidates(
    monkeypatch,
):
    """
    Test that the inference windows of several ForecasterFoundation
    candidates add up into one figure that states the total: two candidates
    of 6 windows (1 series x 6 folds) exceed a threshold of 10 that neither
    exceeds alone.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 10)
    candidates = [
        ("ridge", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
        ("small", {"forecaster": "ForecasterFoundation"}),
        (
            "large",
            {"forecaster": "ForecasterFoundation", "estimator": "amazon/chronos-2"},
        ),
    ]

    err_msg = re.escape(
        "ForecasterFoundation will forecast up to 12 inference windows (1 series "
        "x 6 folds x 2 candidates)."
    )
    with pytest.raises(CostNotConfirmedError, match=err_msg) as exc_info:
        assistant.compare(
            data          = df_single,
            cv            = _single_cv(),
            target        = "sales",
            date_column   = "date",
            candidates    = candidates,
            show_progress = False,
            baseline      = False,
        )

    assert exc_info.value.figure == 12
    assert exc_info.value.cost["inference_windows"] == 12


def test_compare_CandidateFailedWarning_when_direct_candidate_and_cv_with_gap():
    """
    Test that compare() with a cv that has a gap fails a ForecasterDirect
    candidate (it cannot predict steps + gap steps) with a
    CandidateFailedWarning, and still ranks the recursive candidate.
    """
    candidates = [
        ("recursive", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
        ("direct", {"forecaster": "ForecasterDirect", "estimator": "Ridge"}),
    ]
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=2, verbose=False)

    # The warning truncates the error message of the candidate.
    warn_msg = re.escape(
        "Candidate 'direct' failed and is ranked last: ValueError: "
        "ForecasterDirect is trained to predict 5 steps, and with `gap=2` "
        "each fold needs steps + gap = 7 steps ahead"
    )
    with pytest.warns(CandidateFailedWarning, match=warn_msg):
        result = assistant.compare(
            data          = df_single,
            cv            = cv,
            target        = "sales",
            date_column   = "date",
            candidates    = candidates,
            show_progress = False,
            baseline      = False,
        )

    assert list(result.results["name"]) == ["recursive", "direct"]
    assert list(result.candidates) == ["recursive"]
    assert list(result.failures) == ["direct"]
    assert result.best_name == "recursive"


# =============================================================================
# Tests: coherence of the CVResult and the profile
# =============================================================================
def test_compare_InvalidInputError_when_cv_result_of_another_structure():
    """
    Test that compare() raises InvalidInputError with the field 'cv' when
    the CVResult was created for data of another structure (single series
    of monthly data used with wide multi-series daily data).
    """
    h2o_profile = assistant.profile(data=df_h2o, target="x")
    cv_result = assistant.create_cv(h2o_profile, assistant.plan(h2o_profile, steps=5))

    err_msg = re.escape(
        "The CVResult was created for data of another structure "
        "(data_format: 'single' != 'wide'; "
        "target: 'x' != ['series_a', 'series_b']; "
        "date_column: None != 'date'; "
        "frequency: 'MS' != 'D'). Create the strategy from the profile of "
        "these data with `create_cv()`, or pass its TimeSeriesFold "
        "(`cv.cv`)."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.compare(
            data=df_multi_wide,
            cv=cv_result,
            target=["series_a", "series_b"],
            date_column="date",
            candidates=_LIGHT_CANDIDATES,
            show_progress=False,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "cv"


def test_compare_output_when_cv_result_of_same_structure():
    """
    Test that compare() accepts a CVResult created for the same data with
    fewer observations (same structure) and ranks the candidates.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    cv_result = assistant.create_cv(profile, assistant.plan(profile, steps=5))

    result = assistant.compare(
        data=df_single.iloc[:90],
        cv=cv_result,
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        show_progress=False,
        baseline=False,
    )

    assert set(result.results["name"]) == {"recursive_default", "direct_ridge"}


# =============================================================================
# Tests: data against a saved profile
# =============================================================================
_REFRESH_CANDIDATES = [("recursive", {"forecaster": "ForecasterRecursive"})]


def test_compare_output_when_data_equal_to_profile():
    """
    Test that compare() with data equal to the saved profile keeps the
    profile unchanged, without a note.
    """
    profile = assistant.profile(data=df_h2o, target="x")
    cv = TimeSeriesFold(steps=3, initial_train_size=100, verbose=False)

    result = assistant.compare(
        data=df_h2o,
        cv=cv,
        candidates=_REFRESH_CANDIDATES,
        profile=profile,
        show_progress=False,
        baseline=False,
    )

    assert result.profile.data_profile == profile.data_profile
    assert result.profile.data_profile.warnings == []


def test_compare_output_when_data_have_more_rows_than_profile():
    """
    Test that compare() with data that extend the saved profile (192 rows in
    the profile, 204 in the data) ranks the candidates on the new data and
    returns the new profile with the note.
    """
    profile = assistant.profile(data=df_h2o.iloc[:192], target="x")
    cv = TimeSeriesFold(steps=3, initial_train_size=100, verbose=False)

    result = assistant.compare(
        data=df_h2o,
        cv=cv,
        candidates=_REFRESH_CANDIDATES,
        profile=profile,
        show_progress=False,
        baseline=False,
    )

    assert result.best_name == "recursive"
    assert result.profile.data_profile.n_total_observations == 204
    assert result.profile.data_profile.warnings == [
        "The data differ in their values from the profile passed (changed: "
        "series_lengths, span_index_length, n_total_observations, "
        "target_stats): the profile was computed again from these data."
    ]


@pytest.mark.parametrize(
    "data, differences",
    [
        (df_h2o_daily, "(frequency: 'MS' != 'D')"),
    ],
    ids=["frequency"],
)
def test_compare_InvalidInputError_when_data_have_other_structure_than_profile(
    data, differences
):
    """
    Test that compare() raises InvalidInputError with the field 'profile'
    when the data have another frequency than the saved
    profile.
    """
    profile = assistant.profile(data=df_h2o, target="x")
    cv = TimeSeriesFold(steps=3, initial_train_size=50, verbose=False)

    err_msg = re.escape(
        f"The data do not have the structure of the profile passed {differences}: "
        f"profile these data and build the plan from that profile."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.compare(
            data=data,
            cv=cv,
            candidates=_REFRESH_CANDIDATES,
            profile=profile,
            show_progress=False,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "profile"


def test_compare_candidate_use_exog():
    """
    Test that a candidate config takes `use_exog`, so the same forecaster
    can be compared with and without the exogenous variables.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=[
            ("with", {"forecaster": "ForecasterRecursive"}),
            ("without", {"forecaster": "ForecasterRecursive", "use_exog": False}),
        ],
        show_progress=False,
        baseline=False,
    )

    assert result.candidates["with"].plan.use_exog is True
    assert result.candidates["without"].plan.use_exog is False
    assert result.candidates["without"].plan.overridden_fields == [
        "forecaster", "use_exog"
    ]


def test_compare_overridden_fields_of_automatic_candidates_and_baseline(monkeypatch):
    """
    Test that the plans of the automatic candidates and of the baseline,
    whose forecaster and estimator the rules chose, name no decision of the
    user but the metric passed to compare(), and that describe() does not
    say the user chose the forecaster. The foundation backend is reported
    as missing, so the result does not depend on whether it is installed.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )
    with pytest.warns(MissingBackendWarning, match=re.escape(_MISSING_BACKEND_NOTE)):
        automatic = assistant.compare(
            data=df_single,
            cv=_single_cv(),
            target="sales",
            date_column="date",
            show_progress=False,
        )
    with_metric = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=_LIGHT_CANDIDATES,
        metric="mean_squared_error",
        show_progress=False,
    )

    assert {
        tuple(candidate.plan.overridden_fields)
        for candidate in automatic.candidates.values()
    } == {()}
    assert "Chosen by the user" not in automatic.describe()
    baseline_plan = with_metric.candidates[with_metric.baseline_name].plan
    assert baseline_plan.overridden_fields == ["metric"]
    explicit = [
        candidate.plan.overridden_fields
        for name, candidate in with_metric.candidates.items()
        if name != with_metric.baseline_name
    ]
    assert all("forecaster" in fields for fields in explicit)


def test_compare_candidate_differentiation_runs_on_a_copy_of_the_strategy():
    """
    Test that a candidate with its own differentiation order runs on a copy
    of the shared strategy with that order (the strategy is not changed),
    and that the explanation says so.
    """
    cv = _single_cv()
    result = assistant.compare(
        data=df_single,
        cv=cv,
        target="sales",
        date_column="date",
        candidates=[
            ("plain", {"forecaster": "ForecasterRecursive"}),
            ("diff", {"forecaster": "ForecasterRecursive", "differentiation": 1}),
        ],
        show_progress=False,
        baseline=False,
    )

    assert cv.differentiation is None
    assert result.candidates["diff"].cv_config["differentiation"] == 1
    assert result.candidates["plain"].cv_config["differentiation"] is None
    assert result.explanation.endswith(
        "These candidates ran on a copy of the strategy with their own "
        "differentiation order (the strategy has None): {'diff': 1}."
    )


def test_compare_explanation_without_differentiation_note_when_only_baseline_differs():
    """
    Test that when every candidate uses the order of the strategy, the
    baseline (which runs on a copy of the strategy without order) is not
    named in a note about candidates with their own differentiation order.
    """
    cv = TimeSeriesFold(
        steps=5, initial_train_size=70, differentiation=1, verbose=False
    )
    result = assistant.compare(
        data=df_single,
        cv=cv,
        target="sales",
        date_column="date",
        candidates=[
            (
                "recursive_diff",
                {"forecaster": "ForecasterRecursive", "differentiation": 1},
            ),
            (
                "direct_diff",
                {
                    "forecaster": "ForecasterDirect",
                    "estimator": "Ridge",
                    "lags": [1, 2, 3],
                    "differentiation": 1,
                },
            ),
        ],
        show_progress=False,
        baseline=True,
    )

    assert result.baseline_name == "Baseline (seasonal naive)"
    assert "Baseline (seasonal naive)" in list(result.results["name"])
    assert result.candidates["Baseline (seasonal naive)"].cv_config[
        "differentiation"
    ] is None
    assert result.candidates["recursive_diff"].cv_config["differentiation"] == 1
    assert "own differentiation order" not in result.explanation
    assert "copy of the strategy" not in result.explanation


def test_compare_candidate_feature_overrides():
    """
    Test that a candidate config takes `calendar_features`,
    `target_transformer` and `dropna_from_series`, so variants of one
    forecaster can be compared.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        candidates=[
            ("scaled", {"estimator": "Ridge"}),
            (
                "plain",
                {
                    "estimator": "Ridge", "target_transformer": "none",
                    "calendar_features": [], "dropna_from_series": True,
                },
            ),
        ],
        show_progress=False,
        baseline=False,
    )
    plain = result.candidates["plain"].plan

    assert result.candidates["scaled"].plan.forecaster_kwargs["transformer_y"] == (
        "StandardScaler"
    )
    assert "transformer_y" not in plain.forecaster_kwargs
    assert plain.forecaster_kwargs["calendar_features"] is None
    assert plain.forecaster_kwargs["dropna_from_series"] is True


# =============================================================================
# Tests: provenance of the strategy
# =============================================================================
_COMPARISON_INITIAL_TRAIN_SIZE_DEFAULT = (
    "The strategy was created for the plan (ForecasterRecursive + Ridge). "
    "Initial training size by default: 70% of the 100 observations (70), up "
    "to 2023-03-11."
)
_COMPARISON_TRAINED_ONCE_DEFAULT = (
    "The shared strategy trains once by default: refitting in every fold would multiply the "
    "training cost by the 6 folds."
)


def _compare_with(cv, profile):
    """Compare the light candidates with `cv`, without a baseline."""
    return assistant.compare(
        data=df_single, cv=cv, target="sales", date_column="date",
        profile=profile, candidates=_LIGHT_CANDIDATES, show_progress=False,
        baseline=False,
    )


def test_compare_cv_provenance_when_cv_result_with_defaults():
    """
    Test that compare() with the CVResult of create_cv() without arguments
    records that nothing was passed and, as a comparison has no plan of its
    own, says the strategy was created for the plan of the CVResult.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    cv_result = assistant.create_cv(profile, assistant.plan(profile, steps=5))

    result = _compare_with(cv_result, profile)

    assert result.cv_overridden_fields == []
    assert result.cv_fields_without_effect == []
    assert result.cv_llm_configured is False
    assert result.cv_defaults_explanation == (
        f"{_COMPARISON_INITIAL_TRAIN_SIZE_DEFAULT} "
        f"{_COMPARISON_TRAINED_ONCE_DEFAULT}"
    )


def test_compare_cv_provenance_when_cv_result_with_arguments():
    """
    Test that compare() carries the names the user passed to create_cv()
    and says they were requested.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    cv_result = assistant.create_cv(
        profile, assistant.plan(profile, steps=5), refit=True,
        allow_incomplete_fold=False,
    )

    result = _compare_with(cv_result, profile)

    assert result.cv_overridden_fields == ["refit", "allow_incomplete_fold"]
    assert result.cv_fields_without_effect == []
    assert result.cv_defaults_explanation == (
        f"{_COMPARISON_INITIAL_TRAIN_SIZE_DEFAULT} `refit` and "
        "`allow_incomplete_fold` as requested."
    )


def test_compare_cv_provenance_when_fixed_train_size_passed():
    """
    Test that in a comparison a passed `fixed_train_size` is listed as
    chosen by the user and never as without effect: whether it matters
    depends on each candidate, so the shared strategy reports nothing as
    ineffective.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    with pytest.warns(IgnoredArgumentWarning):
        cv_result = assistant.create_cv(profile, plan, fixed_train_size=True)

    result = _compare_with(cv_result, profile)

    assert result.cv_overridden_fields == ["fixed_train_size"]
    assert result.cv_fields_without_effect == []
    assert result.cv_defaults_explanation == (
        f"{_COMPARISON_INITIAL_TRAIN_SIZE_DEFAULT} "
        f"{_COMPARISON_TRAINED_ONCE_DEFAULT} `fixed_train_size` as requested."
    )


def test_compare_cv_provenance_when_candidates_include_forecaster_stats():
    """
    Test that a comparison with a ForecasterStats candidate (refitted in
    every fold whatever the strategy says) reports nothing as without
    effect and never says "Trained once by default" or "no effect on this
    forecaster": the text speaks of the shared strategy, with defaults and
    with `refit=False, fixed_train_size=True` passed.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    candidates = [
        ("recursive", {"forecaster": "ForecasterRecursive"}),
        ("stats", {"forecaster": "ForecasterStats"}),
    ]
    default_cv = assistant.create_cv(profile, plan)
    with pytest.warns(IgnoredArgumentWarning):
        passed_cv = assistant.create_cv(
            profile, plan, refit=False, fixed_train_size=True
        )

    results = [
        assistant.compare(
            data=df_single, cv=cv, target="sales", date_column="date",
            profile=profile, candidates=candidates, show_progress=False,
            baseline=False,
        )
        for cv in (default_cv, passed_cv)
    ]

    assert [r.cv_fields_without_effect for r in results] == [[], []]
    assert results[0].cv_overridden_fields == []
    assert results[1].cv_overridden_fields == ["refit", "fixed_train_size"]
    assert results[0].cv_defaults_explanation == (
        f"{_COMPARISON_INITIAL_TRAIN_SIZE_DEFAULT} "
        f"{_COMPARISON_TRAINED_ONCE_DEFAULT}"
    )
    assert results[1].cv_defaults_explanation == (
        f"{_COMPARISON_INITIAL_TRAIN_SIZE_DEFAULT} `refit` and "
        "`fixed_train_size` as requested."
    )
    for result in results:
        assert "Trained once by default" not in result.cv_defaults_explanation
        assert "no effect on this forecaster" not in result.cv_defaults_explanation


def test_compare_cv_provenance_when_cv_result_llm_configured():
    """
    Test that compare() carries `llm_configured` of the CVResult and, as
    the LLM set the parameters, explains no default.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    cv_result = assistant.create_cv(
        profile, assistant.plan(profile, steps=5), refit=True
    ).model_copy(update={"llm_configured": True})

    result = _compare_with(cv_result, profile)

    assert result.cv_llm_configured is True
    assert result.cv_defaults_explanation == (
        "The strategy was created for the plan (ForecasterRecursive + "
        "Ridge). `refit` as requested."
    )


def test_compare_cv_provenance_when_cv_is_a_time_series_fold():
    """
    Test that compare() with a bare TimeSeriesFold leaves the provenance
    unknown (`cv_overridden_fields` None, not an empty list) and without
    text, and that `cv_config` and `explanation` are the same as with the
    CVResult of the same strategy.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    cv_result = assistant.create_cv(
        profile, assistant.plan(profile, steps=5), refit=True
    )

    from_fold = _compare_with(cv_result.cv, profile)
    from_result = _compare_with(cv_result, profile)

    assert from_fold.cv_overridden_fields is None
    assert from_fold.cv_fields_without_effect == []
    assert from_fold.cv_llm_configured is False
    assert from_fold.cv_defaults_explanation == ""
    assert from_fold.cv_config == from_result.cv_config
    assert from_fold.explanation == from_result.explanation
    assert from_result.cv_defaults_explanation not in from_result.explanation


# =============================================================================
# Tests: the plan the strategy was created for
# =============================================================================
_STRATEGY_TAIL = (
    "Initial training size by default: 70% of the 100 observations (70), up to "
    "2023-03-11. The shared strategy trains once by default: refitting in every "
    "fold would multiply the training cost by the 6 folds."
)


@pytest.mark.slow
def test_compare_strategy_plan_row_when_plan_was_refined(monkeypatch):
    """
    Test the minimal case of the refined plan on h2o: `compare()` without
    `candidates` on the strategy created for the plan refined to
    LGBMRegressor and lags [1, 2, 3, 12] runs that plan as the row
    'Strategy plan', with the metric `backtest()` gives it, and the summary
    names the row, its rank and the configurations that beat the baseline.
    The foundation backend is reported as missing, so the table does not
    depend on whether it is installed.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )
    with pytest.warns(MissingBackendWarning, match=re.escape(_MISSING_BACKEND_NOTE)):
        result = assistant.compare(
            data          = df_h2o,
            cv            = cv_h2o_refined,
            profile       = profile_h2o,
            show_progress = False,
        )
    backtest = assistant.backtest(
        data    = df_h2o,
        cv      = cv_h2o_refined,
        profile = profile_h2o,
        plan    = plan_h2o_refined,
    )

    assert list(result.results["name"]) == [
        "ForecasterRecursive",
        "ForecasterStats",
        "Baseline (seasonal naive)",
        "ForecasterDirect",
        "Strategy plan",
    ]
    assert list(result.results["estimator"]) == [
        "Ridge", "Arima", None, "Ridge", "LGBMRegressor"
    ]
    # The Arima fit of ForecasterStats ends where its optimizer stops, which
    # moves in the fifth decimal from one CI runner to another (0.063813 and
    # 0.063819); the other rows are exact to six decimals.
    maes = result.results["mean_absolute_error"].to_numpy()
    np.testing.assert_array_almost_equal(
        maes[[0, 2, 3, 4]],
        np.array([0.061982, 0.066072, 0.076281, 0.082949]),
        decimal=6,
    )
    assert np.isclose(maes[1], 0.063817, atol=1e-5)
    assert result.strategy_plan_name == "Strategy plan"
    strategy_row = result.candidates["Strategy plan"]
    assert np.isclose(
        strategy_row.metrics["mean_absolute_error"].iloc[0], 0.082949, atol=1e-6
    )
    assert np.isclose(
        strategy_row.metrics["mean_absolute_error"].iloc[0],
        backtest.metrics["mean_absolute_error"].iloc[0],
    )
    assert strategy_row.plan.forecaster == "ForecasterRecursive"
    assert strategy_row.plan.estimator == "LGBMRegressor"
    assert strategy_row.plan.forecaster_kwargs["lags"] == [1, 2, 3, 12]
    assert strategy_row.plan.overridden_fields == ["estimator", "lags"]
    assert strategy_row.plan.overridden_fields == plan_h2o_refined.overridden_fields
    # The row of the forecaster is the plan the profile recommends.
    assert result.candidates["ForecasterRecursive"].plan.estimator == "Ridge"
    assert result.candidates["ForecasterRecursive"].plan.overridden_fields == []
    assert result.explanation == (
        "Compared 5 configurations, ranked ascending by mean_absolute_error. "
        "'Strategy plan' runs the plan the strategy was created for "
        "(ForecasterRecursive / LGBMRegressor), ranked 5 of 5 (0.0829); the "
        "rows named after a forecaster run the configurations the profile "
        "recommends, not that plan. Shared cross-validation strategy: Initial "
        "training up to 2003-04-01, trained once (no refit), 12-step horizon, "
        "6 folds. ForecasterStats is refitted in every fold on a fixed window "
        "(6 trainings): skforecast requires it for ARIMA models. Best: "
        "'ForecasterRecursive' (ForecasterRecursive / Ridge) = 0.0620, 2.9% "
        "ahead of 'ForecasterStats' (0.0638). 2 of 4 configurations beat the "
        "baseline 'Baseline (seasonal naive)' (0.0661): 'ForecasterRecursive' "
        "and 'ForecasterStats'. The best, 'ForecasterRecursive', beats it by "
        "6.2%. " + _MISSING_BACKEND_NOTE
    )
    assert result.cv_defaults_explanation == (
        "The strategy was created for the plan of row 'Strategy plan' "
        "(ForecasterRecursive + LGBMRegressor). Initial training size by "
        "default: 70% of the 204 observations (142), up to 2003-04-01. The "
        "shared strategy trains once by default: refitting in every fold would "
        "multiply the training cost by the 6 folds."
    )


@pytest.mark.parametrize(
    "profile, cv, names, expected_name, plan_label",
    [
        (
            profile_sales,
            cv_sales,
            ["ForecasterDirect", "ForecasterRecursive"],
            "ForecasterRecursive",
            "ForecasterRecursive + Ridge",
        ),
        (
            profile_sales,
            cv_sales_direct,
            ["ForecasterDirect", "ForecasterRecursive"],
            "ForecasterDirect",
            "ForecasterDirect + Ridge",
        ),
        (
            profile_sales_one_forecaster,
            cv_sales_forest,
            [
                "ForecasterRecursive+Ridge",
                "ForecasterRecursive+RandomForestRegressor",
            ],
            "ForecasterRecursive+RandomForestRegressor",
            "ForecasterRecursive + RandomForestRegressor",
        ),
    ],
    ids=["recursive", "direct", "estimator variant"],
)
def test_compare_strategy_plan_is_a_candidate_when_plan_is_the_recommended_one(
    profile, cv, names, expected_name, plan_label
):
    """
    Test that when the plan the strategy was created for makes the same
    decisions as one of the automatic candidates (a forecaster, or a
    forecaster with an estimator when only one forecaster is left), no row
    is added: `strategy_plan_name` is the name of that candidate, the text of
    the strategy names its row and the summary has no sentence about a
    'Strategy plan'.
    """
    result = assistant.compare(
        data          = df_no_exog,
        cv            = cv,
        profile       = profile,
        target        = "sales",
        date_column   = "date",
        show_progress = False,
        baseline      = False,
    )

    assert list(result.results["name"]) == names
    assert result.strategy_plan_name == expected_name
    assert "Strategy plan" not in result.explanation
    assert "runs the plan the strategy was created for" not in result.explanation
    assert result.cv_defaults_explanation == (
        f"The strategy was created for the plan of row '{expected_name}' "
        f"({plan_label}). {_STRATEGY_TAIL}"
    )


def test_compare_strategy_plan_row_without_overridden_metric_unless_passed():
    """
    Test that the row 'Strategy plan' keeps the decisions the user made in
    that plan (`estimator`, `lags`) and gets `metric` only when `compare()`
    received one, while the other rows name no decision of the user but that
    metric.
    """
    default = assistant.compare(
        data          = df_no_exog,
        cv            = cv_sales_refined,
        profile       = profile_sales,
        target        = "sales",
        date_column   = "date",
        show_progress = False,
    )
    with_metric = assistant.compare(
        data          = df_no_exog,
        cv            = cv_sales_refined,
        profile       = profile_sales,
        target        = "sales",
        date_column   = "date",
        metric        = "mean_squared_error",
        show_progress = False,
    )

    assert {
        name: candidate.plan.overridden_fields
        for name, candidate in default.candidates.items()
    } == {
        "ForecasterDirect": [],
        "ForecasterRecursive": [],
        "Baseline (seasonal naive)": [],
        "Strategy plan": ["estimator", "lags"],
    }
    assert {
        name: candidate.plan.overridden_fields
        for name, candidate in with_metric.candidates.items()
    } == {
        "ForecasterDirect": ["metric"],
        "ForecasterRecursive": ["metric"],
        "Baseline (seasonal naive)": ["metric"],
        "Strategy plan": ["estimator", "lags", "metric"],
    }
    assert with_metric.ranking_metric == "mean_squared_error"


def test_compare_strategy_plan_row_is_in_the_explanation_when_it_ran_last():
    """
    Test that the summary of a comparison with the row 'Strategy plan' says
    that it is the plan the strategy was created for, where it ranks and
    that the rows named after a forecaster are the recommended
    configurations, and that the baseline sentence names the row that does
    not beat the baseline.
    """
    result = assistant.compare(
        data          = df_no_exog,
        cv            = cv_sales_refined,
        profile       = profile_sales,
        target        = "sales",
        date_column   = "date",
        show_progress = False,
    )

    assert list(result.results["name"]) == [
        "ForecasterDirect",
        "ForecasterRecursive",
        "Baseline (seasonal naive)",
        "Strategy plan",
    ]
    assert result.strategy_plan_name == "Strategy plan"
    assert result.explanation == (
        "Compared 4 configurations, ranked ascending by mean_absolute_error. "
        "'Strategy plan' runs the plan the strategy was created for "
        "(ForecasterRecursive / RandomForestRegressor), ranked 4 of 4 "
        "(16.2383); the rows named after a forecaster run the configurations "
        "the profile recommends, not that plan. Shared cross-validation "
        "strategy: Initial training up to 2023-03-11, trained once (no "
        "refit), 5-step horizon, 6 folds. Best: 'ForecasterDirect' "
        "(ForecasterDirect / Ridge) = 0.3163, 13.4% ahead of "
        "'ForecasterRecursive' (0.3652). 2 of 3 configurations beat the "
        "baseline 'Baseline (seasonal naive)' (7.0000); 'Strategy plan' does "
        "not. The best, 'ForecasterDirect', beats it by 95.5%."
    )


def test_compare_candidates_explicit_ignore_the_plan_of_the_strategy():
    """
    Test that with explicit `candidates` and the CVResult of a refined plan
    the rows are the candidates and the baseline, no row is added for the
    plan of the strategy (`strategy_plan_name` is None) and the text of the
    strategy keeps the sentence "created for the plan".
    """
    result = assistant.compare(
        data          = df_no_exog,
        cv            = cv_sales_refined,
        profile       = profile_sales,
        target        = "sales",
        date_column   = "date",
        candidates    = [
            ("ridge", {"forecaster": "ForecasterRecursive"}),
            ("direct", {"forecaster": "ForecasterDirect", "lags": [1, 2, 3]}),
        ],
        show_progress = False,
    )

    assert list(result.results["name"]) == [
        "ridge", "direct", "Baseline (seasonal naive)"
    ]
    assert result.strategy_plan_name is None
    assert "Strategy plan" not in result.explanation
    assert "runs the plan the strategy was created for" not in result.explanation
    assert result.cv_defaults_explanation == (
        "The strategy was created for the plan (ForecasterRecursive + "
        f"RandomForestRegressor). {_STRATEGY_TAIL}"
    )


def test_compare_strategy_plan_name_is_none_when_cv_is_a_time_series_fold():
    """
    Test that a bare `TimeSeriesFold` carries no plan, so the comparison
    runs the candidates of the profile and `strategy_plan_name` is None.
    """
    result = assistant.compare(
        data          = df_no_exog,
        cv            = cv_sales_refined.cv,
        profile       = profile_sales,
        target        = "sales",
        date_column   = "date",
        show_progress = False,
        baseline      = False,
    )

    assert list(result.results["name"]) == ["ForecasterDirect", "ForecasterRecursive"]
    assert result.strategy_plan_name is None
    assert result.cv_defaults_explanation == ""


def test_compare_strategy_plan_left_out_with_UserWarning_when_other_family(
    monkeypatch,
):
    """
    Test that a multivariate plan of the strategy, when the data have
    several series (the candidates are multi-series), is left out of the
    comparison with a UserWarning, and that the summary says so and does not
    name a row for it.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )
    note = (
        "The plan the strategy was created for (ForecasterDirectMultiVariate) "
        "is not in the comparison: its metrics are not comparable with those "
        "of the candidates the profile recommends (a multivariate forecaster "
        "is scored on the single series it predicts, a multi-series "
        "forecaster on the average across all series). Backtest it, or "
        "compare it with `candidates` of its family."
    )

    with pytest.warns(MissingBackendWarning, match=re.escape(_MISSING_BACKEND_NOTE)):
        with pytest.warns(UserWarning, match=re.escape(note)):
            result = assistant.compare(
                data          = df_multi_wide,
                cv            = cv_multivariate,
                profile       = profile_multi,
                target        = ["series_a", "series_b"],
                date_column   = "date",
                show_progress = False,
            )

    assert result.strategy_plan_name is None
    assert "Strategy plan" not in list(result.results["name"])
    assert note in result.explanation
    assert "runs the plan the strategy was created for" not in result.explanation
    assert result.cv_defaults_explanation.startswith(
        "The strategy was created for the plan (ForecasterDirectMultiVariate "
        "+ Ridge)."
    )


def test_compare_strategy_plan_runs_when_it_exceeds_the_budget(monkeypatch):
    """
    Test that the plan of the strategy always runs, as its backtest would:
    with a budget of 10 estimator fits, a ForecasterDirect plan with other
    lags that refits in 6 folds (30 fits) is the row 'Strategy plan', while
    the automatic 'ForecasterDirect' is left out and is the only one the
    warning and the explanation name.
    """
    monkeypatch.setattr(comparison_module, "COMPARE_FIT_BUDGET", 10)
    budget_note = (
        "Left out of the automatic candidates because this cross-validation "
        "strategy exceeds the budget of 10 estimator fits: 'ForecasterDirect': "
        "ForecasterDirect will be fit 30 times (6 trainings x 5 estimators). "
        "Pass them in `candidates` to include them."
    )

    with pytest.warns(LongTrainingWarning, match=re.escape(budget_note)):
        result = assistant.compare(
            data          = df_no_exog,
            cv            = cv_sales_direct_refit,
            profile       = profile_sales,
            target        = "sales",
            date_column   = "date",
            show_progress = False,
            baseline      = False,
        )

    assert list(result.results["name"]) == ["ForecasterRecursive", "Strategy plan"]
    assert result.failures == {}
    assert result.strategy_plan_name == "Strategy plan"
    assert result.candidates["Strategy plan"].plan.forecaster == "ForecasterDirect"
    assert result.explanation.endswith(budget_note)
    assert result.explanation.count("'Strategy plan'") == 2


def test_compare_automatic_candidate_of_the_strategy_plan_is_kept_over_the_budget(
    monkeypatch,
):
    """
    Test that the automatic candidate that is the plan of the strategy is
    never left out for its cost: a ForecasterDirect plan refitted in 6 folds
    (30 fits, above a budget patched to 10) runs as 'ForecasterDirect', no
    LongTrainingWarning is raised and the explanation has no budget note.
    """
    monkeypatch.setattr(comparison_module, "COMPARE_FIT_BUDGET", 10)
    result = assistant.compare(
        data          = df_no_exog,
        cv            = cv_sales_direct_default_refit,
        profile       = profile_sales,
        target        = "sales",
        date_column   = "date",
        show_progress = False,
        baseline      = False,
    )

    assert list(result.results["name"]) == ["ForecasterDirect", "ForecasterRecursive"]
    assert result.strategy_plan_name == "ForecasterDirect"
    assert "Left out of the automatic candidates" not in result.explanation


# =============================================================================
# Tests: the baseline sentence of the explanation
# =============================================================================
def _explanation_with_baseline(values: dict[str, float], baseline_value: float) -> str:
    """Explanation of a comparison whose baseline scored `baseline_value`."""
    entries = [
        _ranked_entry(name, "ForecasterRecursive", value)
        for name, value in values.items()
    ]
    entries.append(
        _ranked_entry("Baseline (naive)", "ForecasterEquivalentDate", baseline_value)
    )
    entries.sort(key=lambda entry: entry[2])

    return build_comparison_explanation(
        n_candidates   = len(entries),
        ranked         = entries,
        ranking_metric = "mean_absolute_error",
        any_error      = False,
        cv_explanation = "Folds.",
        baseline_name  = "Baseline (naive)",
    )


@pytest.mark.parametrize(
    "values, sentence",
    [
        (
            {"a": 3.0},
            "No configuration beats the baseline 'Baseline (naive)' (2.0000): "
            "the added complexity is not justified on this data.",
        ),
        (
            {"a": 3.0, "b": 4.0},
            "No configuration beats the baseline 'Baseline (naive)' (2.0000): "
            "the added complexity is not justified on this data.",
        ),
        (
            {"a": 1.0},
            "'a' beats the baseline 'Baseline (naive)' (2.0000) by 50.0%.",
        ),
        (
            {"a": 1.0, "b": 3.0, "c": 4.0},
            "1 of 3 configurations beats the baseline 'Baseline (naive)' "
            "(2.0000): 'a', by 50.0%.",
        ),
        (
            {"a": 0.5, "b": 1.0, "c": 3.0, "d": 4.0, "e": 5.0},
            "2 of 5 configurations beat the baseline 'Baseline (naive)' "
            "(2.0000): 'a' and 'b'. The best, 'a', beats it by 75.0%.",
        ),
        (
            {"a": 0.5, "b": 1.0, "c": 1.5, "d": 3.0, "e": 4.0, "f": 5.0, "g": 6.0},
            "3 of 7 configurations beat the baseline 'Baseline (naive)' "
            "(2.0000): 'a', 'b' and 'c'. The best, 'a', beats it by 75.0%.",
        ),
        (
            {"a": 0.5, "b": 1.0, "c": 1.5, "d": 3.0, "e": 4.0},
            "3 of 5 configurations beat the baseline 'Baseline (naive)' "
            "(2.0000); 'd' and 'e' do not. The best, 'a', beats it by 75.0%.",
        ),
        (
            {"a": 0.5, "b": 1.0, "c": 3.0},
            "2 of 3 configurations beat the baseline 'Baseline (naive)' "
            "(2.0000); 'c' does not. The best, 'a', beats it by 75.0%.",
        ),
        (
            {"a": 0.5, "b": 1.0, "c": 1.5, "d": 3.0, "e": 4.0, "f": 5.0, "g": 6.0,
             "h": 0.6, "i": 0.7, "j": 0.8},
            "6 of 10 configurations beat the baseline 'Baseline (naive)' "
            "(2.0000); 'd', 'e', 'f' and 'g' do not. The best, 'a', beats it "
            "by 75.0%.",
        ),
        (
            {"a": 1.0, "b": 1.5},
            "Both configurations beat the baseline 'Baseline (naive)' "
            "(2.0000). The best, 'a', beats it by 50.0%.",
        ),
        (
            {"a": 1.0, "b": 1.5, "c": 1.8},
            "All 3 configurations beat the baseline 'Baseline (naive)' "
            "(2.0000). The best, 'a', beats it by 50.0%.",
        ),
    ],
    ids=[
        "none of one", "none of two", "single model", "one of three",
        "two of five", "three of seven", "three of five", "two of three",
        "six of ten", "both", "all three",
    ],
)
def test_build_comparison_explanation_states_how_many_configurations_beat_baseline(
    values, sentence
):
    """
    Test that the baseline sentence says how many configurations beat the
    baseline and names the shorter list: those that beat it (up to half of
    them) or those that do not (more than half), with the best one and its
    margin when more than one beats it; 'Both' and 'All n' when every one
    does and the plain sentence for a single model.
    """
    explanation = _explanation_with_baseline(values, baseline_value=2.0)

    assert explanation.endswith(sentence)


def test_build_comparison_explanation_names_the_row_of_the_strategy_plan():
    """
    Test that the explanation says which row runs the plan the strategy was
    created for, with its forecaster and estimator, its rank among the
    candidates and its value, before the shared strategy, and that the note
    of a plan with edits that `plan()` does not rebuild is appended after
    the baseline sentence.
    """
    strategy_entry = _ranked_entry("Strategy plan", "ForecasterRecursive", 3.0)
    strategy_entry[1].plan.estimator = "LGBMRegressor"
    explanation = build_comparison_explanation(
        n_candidates   = 3,
        ranked         = [
            _ranked_entry("model", "ForecasterRecursive", 1.0),
            _ranked_entry("Baseline (naive)", "ForecasterEquivalentDate", 2.0),
            strategy_entry,
        ],
        ranking_metric = "mean_absolute_error",
        any_error      = False,
        cv_explanation = "Folds.",
        baseline_name  = "Baseline (naive)",
        strategy_row   = "Strategy plan",
        strategy_note  = "Edited values.",
    )

    assert explanation == (
        "Compared 3 configurations, ranked ascending by mean_absolute_error. "
        "'Strategy plan' runs the plan the strategy was created for "
        "(ForecasterRecursive / LGBMRegressor), ranked 3 of 3 (3.0000); the "
        "rows named after a forecaster run the configurations the profile "
        "recommends, not that plan. Shared cross-validation strategy: Folds. "
        "Best: 'model' (ForecasterRecursive) = 1.0000. 1 of 2 configurations "
        "beats the baseline 'Baseline (naive)' (2.0000): 'model', by 50.0%. "
        "Edited values."
    )


def test_build_comparison_explanation_when_strategy_plan_failed():
    """
    Test that the explanation says the row of the plan the strategy was
    created for failed to run when it is not among the ranked results, and
    that a forecaster without estimator is named alone when it ran.
    """
    failed = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = [_ranked_entry("model", "ForecasterRecursive", 1.0)],
        ranking_metric = "mean_absolute_error",
        any_error      = True,
        cv_explanation = "Folds.",
        strategy_row   = "Strategy plan",
    )
    ran = build_comparison_explanation(
        n_candidates   = 2,
        ranked         = [
            _ranked_entry("model", "ForecasterRecursive", 1.0),
            _ranked_entry("Strategy plan", "ForecasterDirect", 2.0),
        ],
        ranking_metric = "mean_absolute_error",
        any_error      = False,
        cv_explanation = "Folds.",
        strategy_row   = "Strategy plan",
    )

    assert failed == (
        "Compared 2 configurations, ranked ascending by mean_absolute_error. "
        "'Strategy plan' runs the plan the strategy was created for and "
        "failed to run; the rows named after a forecaster run the "
        "configurations the profile recommends, not that plan. Shared "
        "cross-validation strategy: Folds. Best: 'model' "
        "(ForecasterRecursive) = 1.0000. 1 configuration failed to run and "
        "is ranked last."
    )
    assert ran.startswith(
        "Compared 2 configurations, ranked ascending by mean_absolute_error. "
        "'Strategy plan' runs the plan the strategy was created for "
        "(ForecasterDirect), ranked 2 of 2 (2.0000); the rows named after a "
        "forecaster run the configurations the profile recommends, not that "
        "plan. Shared cross-validation strategy: Folds."
    )


def test_compare_PlanEditsDiscardedWarning_when_strategy_plan_was_edited_by_hand():
    """
    Test that compare() without candidates warns with
    PlanEditsDiscardedWarning when the plan of the strategy holds a value
    edited by hand that `plan()` does not rebuild: its row still runs, as
    the plan rebuilt without that value, and the summary carries the note.
    """
    cv = cv_sales.model_copy(update={"plan": plan_sales_edited})
    note = (
        "The row 'Strategy plan' runs the plan the strategy was created for "
        "as `plan()` rebuilds it, which changes these values of that plan: "
        "[\"forecaster_kwargs['differentiation']\"]. Pass the plan to "
        "`backtest()` to measure it as it is."
    )

    with pytest.warns(PlanEditsDiscardedWarning, match=re.escape(note)):
        result = assistant.compare(
            data          = df_no_exog,
            cv            = cv,
            profile       = profile_sales,
            target        = "sales",
            date_column   = "date",
            show_progress = False,
        )

    assert result.strategy_plan_name == "Strategy plan"
    strategy_plan = result.candidates["Strategy plan"].plan
    assert "differentiation" not in strategy_plan.forecaster_kwargs
    assert note in result.explanation


def test_compare_candidate_scripts_read_csv_with_the_dialect_of_the_file(tmp_path):
    """
    Test that compare() on a CSV with ';' and a decimal comma records the
    dialect in the shared profile, so the script of every candidate reads the
    file with `sep=';', decimal=','`.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    cv = TimeSeriesFold(steps=5, initial_train_size=40, verbose=False)

    result = assistant.compare(
        data          = path,
        cv            = cv,
        target        = "y",
        candidates    = [("ridge", {"estimator": "Ridge"})],
        show_progress = False,
    )

    assert result.profile.data_profile.csv_sep == ";"
    assert result.profile.data_profile.csv_decimal == ","
    assert len(result.candidates) == 2
    for backtest in result.candidates.values():
        assert f"data = pd.read_csv({path!r}, sep=';', decimal=',')\n" in backtest.code


def test_compare_candidate_scripts_keep_the_dialect_when_saved_profile_is_stale(
    tmp_path,
):
    """
    Test that compare() on a ';' file with a saved profile built when the file
    had fewer rows still gives candidate scripts that read it with
    `sep=';', decimal=','`.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    old_path = tmp_path / "old.csv"
    df_dialect.iloc[:50].to_csv(old_path, sep=";", decimal=",", index=False)
    profile = assistant.profile(data=old_path, target="y")
    cv = TimeSeriesFold(steps=5, initial_train_size=40, verbose=False)

    result = assistant.compare(
        data          = path,
        cv            = cv,
        profile       = profile,
        candidates    = [("ridge", {"estimator": "Ridge"})],
        baseline      = False,
        show_progress = False,
    )

    assert result.profile.data_profile.data_path == path
    assert result.profile.data_profile.csv_sep == ";"
    for backtest in result.candidates.values():
        assert f"data = pd.read_csv({path!r}, sep=';', decimal=',')\n" in backtest.code


def test_compare_output_when_interval_adds_coverage_columns_without_changing_ranking():
    """
    Test that compare() with an interval puts the `coverage` and the
    `interval_width` that skforecast measured after the metrics of the
    table, from the metrics of each candidate, ranks the candidates as
    without an interval, and warns once, naming the candidates whose
    interval covers clearly less than 80 % (h2o, 6 folds of 12 months).
    """
    cv = TimeSeriesFold(steps=12, initial_train_size=142)
    candidates = [
        ("ridge", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
        ("direct", {"forecaster": "ForecasterDirect", "lags": 3}),
    ]
    plain = assistant.compare(
        data=df_h2o, cv=cv, target="x", candidates=candidates,
        baseline=False, show_progress=False,
    )
    warn_msg = re.escape(
        "The prediction interval [0.1, 0.9] has a nominal coverage of 80 %, "
        "but it covered clearly less (more than 2 binomial standard errors for "
        "the number of predictions, and at least 5 percentage points, below "
        "80 %) in these candidates: 'ridge' (64.5 % of 62 actual values), "
        "'direct' (59.7 % of 62 actual values). Do not present their interval "
        "as covering 80 %: report the coverage measured in the backtest (the "
        "`coverage` column of the table, and of the metrics of each candidate "
        "by series)."
    )
    with pytest.warns(IntervalCoverageWarning, match=f"^{warn_msg}$") as records:
        result = assistant.compare(
            data=df_h2o, cv=cv, target="x", candidates=candidates,
            interval=[0.1, 0.9], baseline=False, show_progress=False,
        )

    assert len(records) == 1
    assert list(result.results.columns) == [
        "rank", "name", "forecaster", "estimator", "mean_absolute_error",
        "mean_squared_error", "mean_absolute_scaled_error",
        "mean_absolute_percentage_error", "coverage", "interval_width",
    ]
    assert list(result.results["name"]) == list(plain.results["name"])
    for _, row in result.results.iterrows():
        metrics = result.candidates[row["name"]].metrics
        assert row["coverage"] == metrics.loc[0, "coverage"]
        assert row["interval_width"] == metrics.loc[0, "interval_width"]
    np.testing.assert_allclose(
        result.results[["coverage"]].to_numpy(),
        [[0.6451612903225806], [0.5967741935483871]],
    )
