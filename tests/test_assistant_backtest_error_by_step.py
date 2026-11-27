# Unit test backtest (error by step) ForecastingAssistant

import numpy as np
import pandas as pd
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant

from tests.fixtures_assistant import df_multi_wide, df_single

assistant = ForecastingAssistant()


def _error_by_step_of(predictions: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """
    Mean absolute error of the point prediction by `by` (step, or level and
    step), computed outside the script from the predictions of the backtest.
    """
    error = (predictions["y_true"] - predictions["pred"]).abs()

    return (
        error.groupby([predictions[column] for column in by])
        .mean()
        .reset_index(name="mean_absolute_error")
    )


def test_backtest_error_by_step_single_series_equals_error_of_predictions():
    """
    Test that the `error_by_step` of a backtest of a single series is the
    mean absolute error of its predictions by step of the horizon: a `step`
    and a `mean_absolute_error` column, one row per step, equal to the error
    computed from `predictions`, and stated in the explanation.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    result = assistant.backtest(
        data          = df_single,
        target        = "sales",
        date_column   = "date",
        cv            = cv,
        show_progress = False,
    )

    expected = pd.DataFrame({
        "step": [1, 2, 3, 4, 5],
        "mean_absolute_error": [
            0.24063859098886317,
            0.29272778762385104,
            0.3551946253915664,
            0.42993808246442217,
            0.5075265193104576,
        ],
    })
    pd.testing.assert_frame_equal(
        result.error_by_step, _error_by_step_of(result.predictions, ["step"])
    )
    pd.testing.assert_frame_equal(result.error_by_step, expected)
    assert "error_by_step = (" in result.code
    assert (
        "Mean absolute error by step of the horizon (error_by_step): step 1: "
        "0.2406, step 2: 0.2927, step 3: 0.3552, step 4: 0.4299, step 5: 0.5075."
    ) in result.explanation


def test_backtest_error_by_step_several_series_equals_error_of_predictions():
    """
    Test that the `error_by_step` of a backtest of several series has a row
    per series and step (`level`, `step` and `mean_absolute_error` columns),
    equal to the error computed from `predictions`, and that the explanation
    names the first and the last step of each series.
    """
    cv = TimeSeriesFold(steps=3, initial_train_size=40, verbose=False)

    result = assistant.backtest(
        data          = df_multi_wide,
        target        = ["series_a", "series_b"],
        date_column   = "date",
        cv            = cv,
        show_progress = False,
    )

    by_step = result.error_by_step
    pd.testing.assert_frame_equal(
        by_step, _error_by_step_of(result.predictions, ["level", "step"])
    )
    assert list(by_step.columns) == ["level", "step", "mean_absolute_error"]
    assert list(by_step["level"]) == ["series_a"] * 3 + ["series_b"] * 3
    assert list(by_step["step"]) == [1, 2, 3, 1, 2, 3]
    np.testing.assert_array_almost_equal(
        by_step["mean_absolute_error"].to_numpy(),
        np.array([
            0.8463489685211971, 1.0053867737520814, 1.193579760481207,
            0.8463489685211961, 1.0053867737520839, 1.1935797604812095,
        ]),
    )
    assert (
        "Mean absolute error by step of the horizon (error_by_step) of each "
        "series, at steps 1 and 3: series_a: 0.8463 and 1.1936; series_b: "
        "0.8463 and 1.1936."
    ) in result.explanation
