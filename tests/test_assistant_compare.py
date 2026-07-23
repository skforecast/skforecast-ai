# Unit test compare ForecastingAssistant

import ast

import numpy as np
import pandas as pd
import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import (
    BacktestResult,
    ComparisonResult,
    ForecastingAssistant,
)

from tests.fixtures_assistant import df_single, df_no_exog, df_multi_wide

assistant = ForecastingAssistant()


# Two lightweight, backend-free candidate configurations reused across tests.
_LIGHT_FORECASTERS = [
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
    when `forecasters` is None, each labelled by its forecaster name.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    candidates = assistant._resolve_compare_candidates(None, profile)

    names = [name for name, _ in candidates]
    assert names == profile.forecaster_candidates
    for name, config in candidates:
        assert config == {"forecaster": name}


def test_resolve_compare_candidates_ValueError_when_empty_list():
    """
    Test that an empty explicit `forecasters` list raises ValueError.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(ValueError, match="must not be an empty list"):
        assistant._resolve_compare_candidates([], profile)


@pytest.mark.parametrize(
    "forecasters, err_type, err_match",
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
    forecasters, err_type, err_match
):
    """
    Test that malformed `forecasters` entries raise the expected error.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(err_type, match=err_match):
        assistant._resolve_compare_candidates(forecasters, profile)


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
# Tests: error summary (private helper)
# =============================================================================
def test_summarize_error_unwraps_execution_error_to_root_cause():
    """
    Test that `_summarize_error` unwraps a ForecastExecutionError to a
    concise single-line summary of its root cause.
    """
    from skforecast_ai.exceptions import ForecastExecutionError

    root = ImportError("cannot import name 'Ridge'")
    exc = ForecastExecutionError(
        original_error=root,
        generated_code="import Ridge",
        execution_traceback="Traceback ...\n  line 1\n  line 2",
    )

    summary = assistant._summarize_error(exc)

    assert summary == "ImportError: cannot import name 'Ridge'"
    assert "\n" not in summary
    assert "Error executing generated forecasting code" not in summary


def test_summarize_error_plain_exception_first_line_only():
    """
    Test that `_summarize_error` keeps only the first line of a plain
    exception message.
    """
    exc = ValueError("bad value\nextra detail line")

    summary = assistant._summarize_error(exc)

    assert summary == "ValueError: bad value"


def test_summarize_error_truncates_long_messages():
    """
    Test that `_summarize_error` truncates overly long messages with a
    trailing ellipsis.
    """
    exc = ValueError("x" * 500)

    summary = assistant._summarize_error(exc, max_length=50)

    assert len(summary) == 50
    assert summary.endswith("...")


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
            forecasters=_LIGHT_FORECASTERS,
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
        forecasters=_LIGHT_FORECASTERS,
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

    # Detailed results align with successful candidates and are ordered
    assert len(result.detailed_results) == 2
    assert all(isinstance(bt, BacktestResult) for bt in result.detailed_results)

    # Winner is the top-ranked candidate and is reusable
    best = result.best_forecaster
    assert isinstance(best, BacktestResult)
    assert best is result.detailed_results[0]
    assert best.profile is not None
    assert best.plan is not None
    ast.parse(best.code)


def test_compare_output_when_forecasters_none_auto_candidates():
    """
    Test that compare() auto-builds candidates from the profile when
    `forecasters` is None, running each derived forecaster.
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
        forecasters=None,
        profile=profile,
        show_progress=False,
    )

    assert set(result.results["name"]) == {
        "ForecasterRecursive",
        "ForecasterDirect",
    }
    assert len(result.detailed_results) == 2


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
        forecasters=_LIGHT_FORECASTERS,
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
        forecasters=_LIGHT_FORECASTERS,
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
        forecasters=_LIGHT_FORECASTERS,
        interval=[0.1, 0.9],
        show_progress=False,
    )

    for bt in result.detailed_results:
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
        forecasters=[
            ("multiseries", {"forecaster": "ForecasterRecursiveMultiSeries"})
        ],
        show_progress=False,
    )

    assert isinstance(result, ComparisonResult)
    assert list(result.results["rank"]) == [1]
    assert result.best_forecaster is not None
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
    forecasters = [
        ("good", {"forecaster": "ForecasterRecursive"}),
        ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"}),
    ]

    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        forecasters=forecasters,
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

    # Only the successful candidate has a detailed result
    assert len(result.detailed_results) == 1
    assert result.best_forecaster.plan.forecaster == "ForecasterRecursive"
    assert "1 configuration(s) failed" in result.explanation


def test_compare_best_forecaster_none_when_all_candidates_fail():
    """
    Test that best_forecaster is None and the explanation flags the total
    failure when every candidate fails to run.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        forecasters=[
            ("bad", {"forecaster": "ForecasterRecursive", "estimator": "NotAReal"})
        ],
        show_progress=False,
    )

    assert result.best_forecaster is None
    assert result.detailed_results == []
    assert "all candidates failed" in result.explanation


# =============================================================================
# Tests: reuse of the winning configuration
# =============================================================================
def test_compare_best_forecaster_reusable_in_backtest():
    """
    Test that the winning configuration's profile and plan can be fed back
    into backtest() to reproduce a result.
    """
    result = assistant.compare(
        data=df_single,
        cv=_single_cv(),
        target="sales",
        date_column="date",
        forecasters=_LIGHT_FORECASTERS,
        show_progress=False,
    )

    best = result.best_forecaster
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
