# Unit test build_context_message skforecast_ai.llm.context

import numpy as np
import pandas as pd
import pytest

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
    Test that a small DataFrame (<= 30 rows) is serialized in full.
    """
    df = pd.DataFrame({"pred": [1.0, 2.0, 3.0]})
    result = _serialize_dataframe(df)
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
    assert "Summary" in result


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

    assert "## Forecast Results" in result
    assert "### Evaluation Metrics" in result
    assert "MAE" in result
    assert "1.5" in result
    assert "### Predictions" in result
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
        verbosity="standard",
        send_data=True,
    )

    assert "### Predictions" in result
    assert "lower_bound" in result
    assert "8.0" in result
    assert "12.0" in result


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

    assert "## Forecast Results" in result
    assert "## Dataset" not in result
    assert "## Forecast Plan" not in result


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
    assert "### Predictions" in result
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
    Test that build_context_message renders a 'Backtesting Configuration'
    section when cv_config is provided.
    """
    cv_config = {
        "steps": 12,
        "initial_train_size": 100,
        "refit": False,
        "fixed_train_size": True,
    }
    result = build_context_message(cv_config=cv_config)

    assert "## Backtesting Configuration" in result
    assert "- steps: 12" in result
    assert "- initial_train_size: 100" in result
    assert "- refit: False" in result
    assert "- fixed_train_size: True" in result


def test_build_context_message_no_cv_config_no_section():
    """
    Test that build_context_message does NOT render the backtesting section
    when cv_config is None.
    """
    result = build_context_message()
    assert "Backtesting Configuration" not in result
