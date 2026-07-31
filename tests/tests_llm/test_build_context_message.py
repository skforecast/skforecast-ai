# Unit test build_context_message skforecast_ai.llm.context

import numpy as np
import pandas as pd

from skforecast_ai.llm.context import (
    build_context_message,
    _serialize_dataframe,
    _summarize_dataframe,
)


# ---------------------------------------------------------------------------
# _serialize_dataframe: truncation logic
# ---------------------------------------------------------------------------

def test_serialize_dataframe_small():
    """
    Test that a small DataFrame (<= 30 rows) is serialized in full and
    reports its true row count.
    """
    df = pd.DataFrame({"pred": [1.0, 2.0, 3.0]})
    result = _serialize_dataframe(df)
    assert "Total rows: 3 (all shown below)." in result
    assert "1.0" in result
    assert "2.0" in result
    assert "3.0" in result
    assert "omitted" not in result


def test_serialize_dataframe_large_truncated():
    """
    Test that a large DataFrame (> 30 rows) is truncated with head/tail.
    """
    df = pd.DataFrame({"pred": np.arange(50, dtype=float)})
    result = _serialize_dataframe(df)
    assert "rows omitted" in result
    assert "0.0" in result  # head
    assert "49.0" in result  # tail
    assert "Per-column summary" in result


def test_serialize_dataframe_truncated_states_row_count_and_forbids_trends():
    """
    Test that the truncated output reports the true row count and warns
    against inferring trends from the head/tail sample, so a first-row to
    last-row comparison is not reported as a progression across the
    horizon.
    """
    df = pd.DataFrame({"pred": np.arange(50, dtype=float)})
    result = _serialize_dataframe(df)

    assert "Total rows: 50." in result
    assert "the 40 interior rows were not provided" in result
    assert "Do not describe trends, growth, or progression" in result
    assert "do not compare an early row against a late row" in result


def test_serialize_dataframe_truncated_summary_is_per_column():
    """
    Test that the truncated summary reports statistics per column instead of
    blending point predictions and interval bounds into a single value.
    """
    df = pd.DataFrame(
        {
            "pred": np.arange(40, dtype=float),
            "lower_bound": np.arange(40, dtype=float) - 5,
            "upper_bound": np.arange(40, dtype=float) + 5,
        }
    )
    result = _serialize_dataframe(df)

    # Each column reports its own statistics.
    assert "pred: min=0.0, max=39.0, mean=19.5" in result
    assert "lower_bound: min=-5.0, max=34.0, mean=14.5" in result
    assert "upper_bound: min=5.0, max=44.0, mean=24.5" in result
    # The blended cross-column line must not be produced.
    assert "Summary: min=" not in result


def test_serialize_dataframe_summary_reports_exact_values():
    """
    Test that the per-column summary reports exact minima and maxima.

    The prompt states that everything inside `<forecast_context>` is
    authoritative and forbids the model from computing new numbers, so a
    rounded figure labelled `max` is a fabricated value originating in our
    own deterministic code. With a four-significant-digit format the true
    maximum of 1097.5 was reported as 1098.
    """
    df = pd.DataFrame({"pred": np.arange(40, dtype=float) * 2.5 + 1000.0})
    result = _serialize_dataframe(df)

    assert "pred: min=1000.0, max=1097.5, mean=1048.75" in result


def test_serialize_dataframe_exactly_30_rows():
    """
    Test that exactly 30 rows are shown in full (boundary case).
    """
    df = pd.DataFrame({"pred": np.arange(30, dtype=float)})
    result = _serialize_dataframe(df)
    assert "omitted" not in result


def test_serialize_dataframe_31_rows_truncated():
    """
    Test that 31 rows triggers truncation.
    """
    df = pd.DataFrame({"pred": np.arange(31, dtype=float)})
    result = _serialize_dataframe(df)
    assert "rows omitted" in result


# ---------------------------------------------------------------------------
# build_context_message: with forecast results
# ---------------------------------------------------------------------------

def test_build_context_message_with_predictions_and_metrics():
    """
    Test that predictions and metrics are included in the context message
    when send_data=True.
    """
    predictions = pd.DataFrame({"pred": [10.0, 11.0, 12.0]})
    metrics = pd.DataFrame({"series": ["target"], "MAE": [1.5]})

    result = build_context_message(
        predictions=predictions, metrics=metrics, send_data=True
    )

    assert "<evaluation_metrics>" in result
    assert "MAE" in result
    assert "1.5" in result
    assert "<predictions>" in result
    assert "10.0" in result


def test_build_context_message_with_intervals():
    """
    Test that prediction interval columns included in predictions are
    rendered when send_data=True.
    """
    predictions = pd.DataFrame({
        "pred": [10.0, 11.0],
        "lower_bound": [8.0, 9.0],
        "upper_bound": [12.0, 13.0],
    })
    metrics = pd.DataFrame({"series": ["target"], "MAE": [1.0]})

    result = build_context_message(
        predictions=predictions,
        metrics=metrics,
        send_data=True,
    )

    assert "<predictions>" in result
    assert "lower_bound" in result
    assert "8.0" in result
    assert "12.0" in result


def test_build_context_message_plan_includes_interval_method_and_metric():
    """
    Test that the plan section reports the prediction interval with its
    coverage, the interval method, and the primary metric, so the LLM does
    not have to guess them.
    """
    from skforecast_ai.schemas import ForecastPlan

    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        estimator="LGBMRegressor",
        steps=36,
        interval=[0.1, 0.9],
        interval_method="bootstrapping",
        metric="mean_absolute_error",
        explanation="Recursive plan.",
    )

    result = build_context_message(plan=plan)

    assert "<forecast_plan>" in result
    assert "Prediction interval: [0.1, 0.9] (80% coverage)" in result
    assert "Interval method: bootstrapping" in result
    assert "Primary metric: mean_absolute_error" in result


def test_build_context_message_plan_omits_interval_when_none():
    """
    Test that no prediction interval line is rendered when the plan has no
    interval configured.
    """
    from skforecast_ai.schemas import ForecastPlan

    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        estimator="LGBMRegressor",
        steps=36,
        interval=None,
        explanation="Recursive plan.",
    )

    result = build_context_message(plan=plan)

    assert "Prediction interval" not in result
    assert "Interval method" not in result


def test_build_context_message_predictions_without_metrics_notes_prediction_mode():
    """
    Test that a note is added when predictions exist but metrics are None
    (prediction mode), and that no evaluation-metrics section is rendered.
    """
    predictions = pd.DataFrame({"pred": [10.0, 11.0, 12.0]})

    result = build_context_message(
        predictions=predictions, metrics=None, send_data=True
    )

    assert "<evaluation_metrics>" in result
    assert "No evaluation metrics were computed" in result
    assert "<predictions>" in result


def test_build_context_message_empty_when_no_args():
    """
    Test that an empty string is returned when no arguments are provided.
    """
    result = build_context_message()
    assert result == ""


def test_build_context_message_results_only_no_profile():
    """
    Test that results can be shown without a profile or plan.
    """
    predictions = pd.DataFrame({"pred": [5.0, 6.0]})
    metrics = pd.DataFrame({"series": ["target"], "MAE": [0.5]})

    result = build_context_message(predictions=predictions, metrics=metrics)

    assert "<evaluation_metrics>" in result
    assert "<predictions>" in result
    assert "<dataset>" not in result
    assert "<forecast_plan>" not in result


# ---------------------------------------------------------------------------
# send_data flag: privacy enforcement
# ---------------------------------------------------------------------------

def test_build_context_message_send_data_false_excludes_raw_rows():
    """
    Test that raw prediction values (including interval columns) are
    excluded when send_data=False (default). Only aggregate stats should
    appear, not tabular row-level data.
    """
    predictions = pd.DataFrame({
        "pred": [10.5, 11.2, 12.8],
        "lower_bound": [8.0, 9.0, 10.0],
        "upper_bound": [13.0, 14.0, 15.0],
    })
    metrics = pd.DataFrame({"series": ["target"], "MAE": [1.5]})

    result = build_context_message(
        predictions=predictions,
        metrics=metrics,
        send_data=False,
    )

    # Metrics are always included (aggregate)
    assert "MAE" in result
    assert "1.5" in result
    # Predictions section uses summary format
    assert "<predictions>" in result
    assert "Shape: 3 rows x 3 columns" in result
    # Row-level tabular format should not appear
    assert "0  10.5" not in result
    assert "1  11.2" not in result
    assert "2  12.8" not in result


def test_build_context_message_send_data_true_includes_raw_rows():
    """
    Test that raw prediction values are included when send_data=True.
    """
    predictions = pd.DataFrame({"pred": [10.5, 11.2, 12.8]})
    metrics = pd.DataFrame({"series": ["target"], "MAE": [1.5]})

    result = build_context_message(
        predictions=predictions,
        metrics=metrics,
        send_data=True,
    )

    assert "10.5" in result
    assert "11.2" in result
    assert "12.8" in result


def test_build_context_message_metrics_always_included_regardless_of_flag():
    """
    Test that metrics (aggregate values) are always included whether
    send_data is True or False.
    """
    metrics = pd.DataFrame({"series": ["target"], "MAE": [2.3], "RMSE": [3.1]})

    result_false = build_context_message(metrics=metrics, send_data=False)
    result_true = build_context_message(metrics=metrics, send_data=True)

    assert "MAE" in result_false
    assert "2.3" in result_false
    assert "MAE" in result_true
    assert "2.3" in result_true


# ---------------------------------------------------------------------------
# _summarize_dataframe
# ---------------------------------------------------------------------------

def test_summarize_dataframe_shows_stats_not_values():
    """
    Test that _summarize_dataframe produces aggregate stats without
    exposing individual row values.
    """
    df = pd.DataFrame({"pred": [10.0, 20.0, 30.0]})
    result = _summarize_dataframe(df)

    assert "Shape: 3 rows x 1 columns" in result
    assert "pred:" in result
    assert "min=10" in result
    assert "max=30" in result
    # Individual row values in table format should not appear
    assert "0  10" not in result
    assert "1  20" not in result


def test_summarize_dataframe_includes_index_range():
    """
    Test that _summarize_dataframe includes the index range.
    """
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    df = pd.DataFrame({"pred": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=idx)
    result = _summarize_dataframe(df)

    assert "Index range:" in result
    assert "2020-01-01" in result
    assert "2020-01-05" in result


# ---------------------------------------------------------------------------
# cv_config section
# ---------------------------------------------------------------------------

def test_build_context_message_cv_config_section():
    """
    Test that build_context_message renders a cross-validation section
    when cv_config is provided.
    """
    cv_config = {
        "steps": 12,
        "initial_train_size": 100,
        "refit": False,
        "fixed_train_size": True,
        "n_folds": 8,
    }
    result = build_context_message(cv_config=cv_config)

    assert "<cross_validation>" in result
    assert "- steps: 12" in result
    assert "- initial_train_size: 100" in result
    assert "- refit: False" in result
    assert "- fixed_train_size: True" in result
    assert "- n_folds: 8" in result


def test_build_context_message_no_cv_config_no_section():
    """
    Test that build_context_message does NOT render the cross-validation
    section when cv_config is None.
    """
    result = build_context_message()
    assert "cross_validation" not in result


# ---------------------------------------------------------------------------
# deterministic_summary section
# ---------------------------------------------------------------------------

def test_build_context_message_renders_deterministic_summary():
    """
    Test that a supplied deterministic explanation is rendered in its own
    section, so the LLM does not have to re-derive facts (such as the
    fold count) that were already computed.
    """
    result = build_context_message(
        explanation="No refit, 36-step horizon, 82 folds."
    )

    assert "<deterministic_summary>" in result
    assert "No refit, 36-step horizon, 82 folds." in result


def test_build_context_message_no_deterministic_summary_no_section():
    """
    Test that no deterministic summary section is rendered when no
    explanation is supplied.
    """
    result = build_context_message(metrics=pd.DataFrame({"MAE": [1.0]}))
    assert "deterministic_summary" not in result


# ---------------------------------------------------------------------------
# Tagged context block
# ---------------------------------------------------------------------------

def test_build_context_message_wraps_sections_in_forecast_context():
    """
    Test that every rendered section sits inside a single balanced
    <forecast_context> block, so the deterministic payload cannot be
    confused with the skills or with the answer the LLM produces.
    """
    predictions = pd.DataFrame({"pred": [1.0, 2.0]})
    metrics = pd.DataFrame({"series": ["target"], "MAE": [1.0]})

    result = build_context_message(
        predictions = predictions,
        metrics     = metrics,
        cv_config   = {"steps": 2},
        explanation = "Summary.",
        send_data   = True,
    )

    assert result.startswith("<forecast_context>")
    assert result.endswith("</forecast_context>")
    assert result.count("<forecast_context>") == 1
    assert result.count("</forecast_context>") == 1

    for tag in ["cross_validation", "deterministic_summary",
                "evaluation_metrics", "predictions"]:
        assert result.count(f"<{tag}>") == 1
        assert result.count(f"</{tag}>") == 1


def test_build_context_message_no_markdown_headings():
    """
    Test that the context block emits no markdown headings. Headings would
    collide with the skills and with the expected answer format.
    """
    predictions = pd.DataFrame({"pred": [1.0, 2.0]})
    metrics = pd.DataFrame({"series": ["target"], "MAE": [1.0]})

    result = build_context_message(
        predictions=predictions, metrics=metrics, send_data=True
    )

    assert "##" not in result
