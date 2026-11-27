# Unit test _build_backtest_explanation execution/backtesting_runner

import pandas as pd
import pytest

from skforecast_ai.execution.backtesting_runner import _build_backtest_explanation

# Fixtures
from .fixtures_interval_coverage import (
    interval,
    predictions_single_200,
    metrics_single_06,
    predictions_multi_2,
    metrics_multi_2,
)


# Tests: _build_backtest_explanation: metric formatting


def test_build_backtest_explanation_includes_cv_and_metrics():
    """
    Test that _build_backtest_explanation combines the CV explanation with
    a metric summary when metrics are non-empty.
    """
    cv_explanation = "TimeSeriesFold with 10 steps, refit=False."
    metrics = pd.DataFrame({"mean_absolute_error": [1.2345], "mean_squared_error": [2.3456]})

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=metrics
    )

    assert cv_explanation in result
    assert "Results" in result
    assert "mean_absolute_error" in result
    assert "1.2345" in result


def test_build_backtest_explanation_empty_metrics_returns_cv_only():
    """
    Test that _build_backtest_explanation returns only the CV explanation
    when metrics is an empty DataFrame.
    """
    cv_explanation = "TimeSeriesFold with 10 steps, refit=False."
    metrics = pd.DataFrame()

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=metrics
    )

    assert result == cv_explanation


def test_build_backtest_explanation_none_metrics_returns_cv_only():
    """
    Test that _build_backtest_explanation returns only the CV explanation
    when metrics is None.
    """
    cv_explanation = "TimeSeriesFold with 10 steps, refit=False."

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=None
    )

    assert result == cv_explanation


def test_build_backtest_explanation_skips_level_columns():
    """
    Test that _build_backtest_explanation excludes 'levels' and 'level'
    columns from the metric summary string.
    """
    cv_explanation = "CV explanation."
    metrics = pd.DataFrame({
        "levels": ["series_a"],
        "mean_absolute_error": [0.5678],
    })

    result = _build_backtest_explanation(
        cv_explanation=cv_explanation, metrics=metrics
    )

    assert "levels" not in result.split("Results")[1]
    assert "mean_absolute_error" in result
    assert "0.5678" in result


def test_build_backtest_explanation_uses_average_row_when_multi_series():
    """
    Test that a multi-series metrics frame is summarised with its
    `average` row, not with the mean of every row: skforecast appends
    `average`, `weighted_average` and `pooling` rows, and averaging them
    together with the per-series rows produces a number that matches no
    row of the table.
    """
    metrics = pd.DataFrame({
        "levels": ["a", "b", "average", "weighted_average", "pooling"],
        "mean_absolute_error": [1.0, 3.0, 2.0, 2.0, 2.1],
    })

    result = _build_backtest_explanation(cv_explanation="CV.", metrics=metrics)

    assert result == "CV. Results (average across series): mean_absolute_error: 2.0000."


def test_build_backtest_explanation_states_n_evaluated_apart_from_the_metrics():
    """
    Test that `n_evaluated` (skforecast 0.27), a count of points and not a
    metric, is left out of the results and stated in a sentence of its own,
    for a single series (where pandas reads the row as floats) and for
    several, where the `average` row holds the sum across the series.
    """
    single = pd.DataFrame({
        "mean_absolute_error": [1.5], "n_evaluated": [40],
    })
    multi = pd.DataFrame({
        "levels": ["a", "b", "average", "weighted_average", "pooling"],
        "mean_absolute_error": [1.0, 3.0, 2.0, 2.0, 2.1],
        "n_evaluated": [20, 18, 38, 38, 38],
    })

    result_single = _build_backtest_explanation(cv_explanation="CV.", metrics=single)
    result_multi = _build_backtest_explanation(cv_explanation="CV.", metrics=multi)

    assert result_single == (
        "CV. Results: mean_absolute_error: 1.5000. They are measured on 40 "
        "predictions with an observed value (n_evaluated)."
    )
    assert result_multi == (
        "CV. Results (average across series): mean_absolute_error: 2.0000. "
        "They are measured on 38 predictions with an observed value across "
        "the series (n_evaluated)."
    )


def test_build_backtest_explanation_counts_test_dates_without_value():
    """
    Test that a single series whose predictions have test dates without an
    observed value (`y_true` missing, left out of the metrics by skforecast
    0.27) gets a sentence that counts them, a date predicted by two
    overlapping folds once and a single date in the singular; several
    series (a `level` column), whose backtest drops them per series, and
    predictions without missing `y_true` get none.
    """
    metrics = pd.DataFrame({"mean_absolute_error": [1.5], "n_evaluated": [3]})
    dates = pd.to_datetime(
        ["2020-01-01", "2020-01-02", "2020-01-02", "2020-01-03", "2020-01-04",
         "2020-01-05"]
    )
    predictions = pd.DataFrame(
        {
            "fold": [0, 0, 1, 1, 1, 1],
            "y_true": [1.0, None, None, 2.0, None, 3.0],
            "pred": [1.1, 1.2, 1.2, 2.1, 2.2, 3.1],
        },
        index=dates,
    )
    one_missing = predictions.assign(y_true=[1.0, 2.0, 2.0, None, 2.5, 3.0])
    several = predictions.assign(level="a")

    result = _build_backtest_explanation(
        cv_explanation="CV.", metrics=metrics, predictions=predictions
    )
    result_one = _build_backtest_explanation(
        cv_explanation="CV.", metrics=metrics, predictions=one_missing
    )
    result_several = _build_backtest_explanation(
        cv_explanation="CV.", metrics=metrics, predictions=several
    )
    result_complete = _build_backtest_explanation(
        cv_explanation="CV.",
        metrics=metrics,
        predictions=predictions.assign(y_true=1.0),
    )

    measured = (
        "CV. Results: mean_absolute_error: 1.5000. They are measured on 3 "
        "predictions with an observed value (n_evaluated)."
    )
    assert result == (
        f"{measured} The metrics leave out 2 test dates without an observed "
        f"value of the target."
    )
    assert result_one == (
        f"{measured} The metrics leave out 1 test date without an observed "
        f"value of the target."
    )
    assert result_several == measured
    assert result_complete == measured


# Tests: _build_backtest_explanation: prediction interval coverage


def test_build_backtest_explanation_single_series_with_interval():
    """
    Test that with a prediction interval the `coverage` and `interval_width`
    metrics are not listed in the "Results" part and a sentence of their own
    is appended to the explanation.
    """
    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics_single_06,
        predictions    = predictions_single_200,
        interval       = interval,
    )

    expected = (
        "CV. Results: mean_absolute_error: 1.5000. Prediction interval "
        "[0.1, 0.9] (nominal coverage 80 %): 60 % of the 200 actual values "
        "fell inside it (coverage: 0.6000), with a mean width of 4.0000 in "
        "the units of the target (interval_width)."
    )
    assert result == expected


def test_build_backtest_explanation_multi_series_with_interval():
    """
    Test that a multi-series backtest with a prediction interval keeps the
    average row in the "Results" part, without the interval metrics, and
    appends the sentence by series.
    """
    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics_multi_2,
        predictions    = predictions_multi_2,
        interval       = interval,
    )

    expected = (
        "CV. Results (average across series): mean_absolute_error: 1.5000. "
        "Prediction interval [0.1, 0.9] (nominal coverage 80 %), share of "
        "the actual values inside it (coverage) and mean width in the units "
        "of each series (interval_width), by series: 'a' 80 % of 100 "
        "predictions, width 4.0000; 'b' 50 % of 100 predictions, width "
        "3.0000; average across series 65 %, width 3.5000."
    )
    assert result == expected


# Tests: _build_backtest_explanation: error by step of the horizon

error_by_step_two = pd.DataFrame(
    {"step": [1, 2], "mean_absolute_error": [1.0, 2.0]}
)
by_step_sentence = (
    "Mean absolute error by step of the horizon (error_by_step): step 1: "
    "1.0000, step 2: 2.0000."
)


def test_build_backtest_explanation_adds_error_by_step_after_n_evaluated():
    """
    Test that the sentence of the error by step follows the one of
    `n_evaluated` when the predictions are not given (nothing to say about
    dates without value).
    """
    metrics = pd.DataFrame({"mean_absolute_error": [1.5], "n_evaluated": [40]})

    result = _build_backtest_explanation(
        cv_explanation="CV.", metrics=metrics, error_by_step=error_by_step_two
    )

    assert result == (
        "CV. Results: mean_absolute_error: 1.5000. They are measured on 40 "
        "predictions with an observed value (n_evaluated). "
        f"{by_step_sentence}"
    )


def test_build_backtest_explanation_error_by_step_follows_dates_without_value():
    """
    Test that the sentence of the error by step comes after the one that
    counts the test dates without an observed value, and the sentence of
    `target_missing` is not added when there are such dates.
    """
    metrics = pd.DataFrame({"mean_absolute_error": [1.5], "n_evaluated": [1]})
    predictions = pd.DataFrame(
        {"fold": [0, 0], "y_true": [1.0, None], "pred": [1.1, 1.2]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )

    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics,
        predictions    = predictions,
        error_by_step  = error_by_step_two,
        target_missing = True,
    )

    assert result == (
        "CV. Results: mean_absolute_error: 1.5000. They are measured on 1 "
        "predictions with an observed value (n_evaluated). The metrics leave "
        "out 1 test date without an observed value of the target. "
        f"{by_step_sentence}"
    )


def test_build_backtest_explanation_error_by_step_precedes_the_interval_coverage():
    """
    Test that the sentence of the error by step comes before the sentence of
    the coverage of the prediction interval, which stays the last one.
    """
    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics_single_06,
        predictions    = predictions_single_200,
        interval       = interval,
        error_by_step  = error_by_step_two,
    )

    assert result == (
        "CV. Results: mean_absolute_error: 1.5000. "
        f"{by_step_sentence} Prediction interval "
        "[0.1, 0.9] (nominal coverage 80 %): 60 % of the 200 actual values "
        "fell inside it (coverage: 0.6000), with a mean width of 4.0000 in "
        "the units of the target (interval_width)."
    )


@pytest.mark.parametrize("metrics", [None, pd.DataFrame()], ids=["None", "empty"])
def test_build_backtest_explanation_error_by_step_ignored_without_metrics(metrics):
    """
    Test that without metrics the explanation is the CV one only: the error
    by step is part of the results summary.
    """
    result = _build_backtest_explanation(
        cv_explanation="CV.", metrics=metrics, error_by_step=error_by_step_two
    )

    assert result == "CV."


# Tests: _build_backtest_explanation: target without missing dates

_metrics_target = pd.DataFrame({"mean_absolute_error": [1.5], "n_evaluated": [3]})
_dates_target = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
_predictions_target = pd.DataFrame(
    {"fold": [0, 0, 0], "y_true": [1.0, 2.0, 3.0], "pred": [1.1, 2.1, 3.1]},
    index=_dates_target,
)
_measured_target = (
    "CV. Results: mean_absolute_error: 1.5000. They are measured on 3 "
    "predictions with an observed value (n_evaluated)."
)


@pytest.mark.parametrize(
    "predictions, target_missing, expected",
    [
        (
            _predictions_target,
            True,
            f"{_measured_target} Every test date has an observed value of the "
            f"target: the metrics leave none out.",
        ),
        (
            _predictions_target.assign(y_true=[1.0, None, 3.0]),
            True,
            f"{_measured_target} The metrics leave out 1 test date without an "
            f"observed value of the target.",
        ),
        (_predictions_target.assign(level="a"), True, _measured_target),
        (_predictions_target, False, _measured_target),
        (None, True, _measured_target),
        (_predictions_target.drop(columns="y_true"), True, _measured_target),
    ],
    ids=[
        "every y_true observed",
        "a date without y_true",
        "level column",
        "target_missing False",
        "no predictions",
        "no y_true column",
    ],
)
def test_build_backtest_explanation_target_missing_says_no_test_date_left_out(
    predictions, target_missing, expected
):
    """
    Test that, with `target_missing`, a single series whose test dates all
    have an observed value says that the metrics leave none out; that a date
    without value gets the count sentence instead; and that nothing is added
    with a `level` column, without `target_missing`, or when the predictions
    cannot say (missing or without `y_true`).
    """
    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = _metrics_target,
        predictions    = predictions,
        target_missing = target_missing,
    )

    assert result == expected


def test_build_backtest_explanation_target_missing_sentence_precedes_error_by_step():
    """
    Test that the sentence that no test date is left out comes before the
    sentence of the error by step.
    """
    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = _metrics_target,
        predictions    = _predictions_target,
        error_by_step  = error_by_step_two,
        target_missing = True,
    )

    assert result == (
        f"{_measured_target} Every test date has an observed value of the "
        f"target: the metrics leave none out. {by_step_sentence}"
    )


# Tests: _build_backtest_explanation: error by step of a single prediction

withheld_sentence = (
    "The mean absolute error by step of the horizon (error_by_step) is not "
    "stated here: a step measured on a single prediction would give its "
    "observed value."
)


def test_build_backtest_explanation_withholds_error_by_step_of_one_fold():
    """
    Test that the errors by step are not stated when each step is measured
    on a single prediction (one fold): the sentence says where the table is
    instead, since the error next to the prediction gives the observed value.
    """
    metrics = pd.DataFrame({"mean_absolute_error": [1.5], "n_evaluated": [2]})
    predictions = pd.DataFrame(
        {
            "fold": [0, 0],
            "step": [1, 2],
            "y_true": [1.0, 2.0],
            "pred": [2.0, 4.0],
        },
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )

    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics,
        predictions    = predictions,
        error_by_step  = error_by_step_two,
    )

    assert result == (
        "CV. Results: mean_absolute_error: 1.5000. They are measured on 2 "
        f"predictions with an observed value (n_evaluated). {withheld_sentence}"
    )


def test_build_backtest_explanation_states_error_by_step_of_two_folds():
    """
    Test that the errors by step are stated when every step is measured on
    two predictions with an observed value; a step whose only prediction
    has no observed value does not count.
    """
    metrics = pd.DataFrame({"mean_absolute_error": [1.5], "n_evaluated": [4]})
    predictions = pd.DataFrame(
        {
            "fold": [0, 0, 1, 1, 2],
            "step": [1, 2, 1, 2, 3],
            "y_true": [1.0, 2.0, 3.0, 4.0, None],
            "pred": [2.0, 4.0, 4.0, 6.0, 5.0],
        },
        index=pd.date_range("2020-01-01", periods=5, freq="D"),
    )

    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics,
        predictions    = predictions,
        error_by_step  = error_by_step_two,
    )

    assert result.endswith(by_step_sentence)
    assert withheld_sentence not in result


def test_build_backtest_explanation_withholds_error_by_step_of_one_series():
    """
    Test that with several series the errors by step are not stated when a
    single series has a step measured on one prediction.
    """
    metrics = pd.DataFrame({
        "levels": ["a", "b", "average"],
        "mean_absolute_error": [1.0, 2.0, 1.5],
    })
    predictions = pd.DataFrame(
        {
            "level": ["a", "a", "b", "b", "b"],
            "fold": [0, 1, 0, 1, 1],
            "step": [1, 1, 1, 1, 2],
            "y_true": [1.0, 2.0, 3.0, 4.0, 5.0],
            "pred": [2.0, 3.0, 4.0, 5.0, 7.0],
        },
        index=pd.date_range("2020-01-01", periods=5, freq="D"),
    )
    error_by_step = pd.DataFrame({
        "level": ["a", "b", "b"],
        "step": [1, 1, 2],
        "mean_absolute_error": [1.0, 1.0, 2.0],
    })

    result = _build_backtest_explanation(
        cv_explanation = "CV.",
        metrics        = metrics,
        predictions    = predictions,
        error_by_step  = error_by_step,
    )

    assert result == (
        "CV. Results (average across series): mean_absolute_error: 1.5000. "
        f"{withheld_sentence}"
    )
