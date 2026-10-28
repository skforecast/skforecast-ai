# Unit test run_backtest execution/backtesting_runner

import re

import numpy as np
import pandas as pd
import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant
from skforecast_ai._utils import _cv_in_time_zone
from skforecast_ai.execution.backtesting_runner import run_backtest
from skforecast_ai.schemas import ForecastPlan, RenderedScript

from .fixtures_execution import (
    cv_explanation_single,
    cv_multi,
    cv_short,
    cv_single,
    df_multi,
    df_short,
    df_single,
    plan_baseline,
    plan_multi,
    plan_short,
    plan_single,
    plan_statistical,
    profile_multi,
    profile_short,
    profile_single,
    profile_single_no_exog,
)


# Tests: run_backtest: error handling


def test_run_backtest_ValueError_when_unsupported_task_type():
    """
    Test that run_backtest raises ValueError when the plan has an
    unsupported task_type not present in the dispatch table.
    """
    plan_bad = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        estimator="Ridge",
        steps=5,
        frequency="D",
        explanation="Bad task type.",
    )
    # Monkey-patch task_type to an unsupported value
    object.__setattr__(plan_bad, "task_type", "unsupported_type")

    with pytest.raises(ValueError, match="Unsupported task_type"):
        run_backtest(
            data=df_single,
            profile=profile_single,
            plan=plan_bad,
            cv=cv_single,
            cv_explanation=cv_explanation_single,
        )


def test_run_backtest_ValueError_when_estimator_not_supported():
    """
    Test that run_backtest raises ValueError, before writing the name into
    the script, for a plan whose estimator skipped validation (model_copy
    does not run the ForecastPlan validator).
    """
    plan_bad = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        estimator="Ridge",
        steps=5,
        frequency="D",
        explanation="Bad estimator for backtesting.",
    ).model_copy(update={"estimator": "NonExistentEstimator"})

    err_msg = re.escape("'NonExistentEstimator' is not a supported estimator.")
    with pytest.raises(ValueError, match=err_msg):
        run_backtest(
            data=df_single,
            profile=profile_single,
            plan=plan_bad,
            cv=cv_single,
            cv_explanation=cv_explanation_single,
        )


# Tests: run_backtest: single series


def test_run_backtest_single_series_returns_dict_with_expected_keys():
    """
    Test that run_backtest returns a dict with keys 'metrics',
    'predictions', 'rendered_code', 'explanation' and 'left_out_of_folds'
    (None for a single series).
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    assert isinstance(result, dict)
    expected_keys = {
        "metrics", "predictions", "rendered_code", "explanation",
        "left_out_of_folds",
    }
    assert set(result.keys()) == expected_keys
    assert result["left_out_of_folds"] is None


def test_run_backtest_single_series_metrics_is_dataframe():
    """
    Test that run_backtest returns a metrics DataFrame with numeric values
    for a single-series task.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    metrics = result["metrics"]
    assert isinstance(metrics, pd.DataFrame)
    assert not metrics.empty
    # All non-level columns should have numeric values
    for col in metrics.columns:
        if col not in ("levels", "level"):
            assert metrics[col].dtype.kind == "f"


def test_run_backtest_single_series_predictions_is_dataframe():
    """
    Test that run_backtest returns a non-empty predictions DataFrame for
    a single-series task.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    predictions = result["predictions"]
    assert isinstance(predictions, pd.DataFrame)
    assert not predictions.empty


def test_run_backtest_single_series_rendered_code_is_RenderedScript():
    """
    Test that run_backtest returns a RenderedScript instance in the
    'rendered_code' key.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    assert isinstance(result["rendered_code"], RenderedScript)
    assert "backtesting_forecaster(" in result["rendered_code"].core
    assert "read_csv" in result["rendered_code"].full_script
    assert "read_csv" not in result["rendered_code"].executable


def test_run_backtest_single_series_explanation_contains_metrics():
    """
    Test that the explanation string includes metric summary values from
    the backtesting results.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
    )

    explanation = result["explanation"]
    assert isinstance(explanation, str)
    assert "Results" in explanation
    assert cv_explanation_single in explanation


def test_run_backtest_single_series_show_progress_false():
    """
    Test that run_backtest executes without error when show_progress is
    set to False.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single,
        plan=plan_single,
        cv=cv_single,
        cv_explanation=cv_explanation_single,
        show_progress=False,
    )

    assert isinstance(result["metrics"], pd.DataFrame)
    assert not result["metrics"].empty


# Tests: run_backtest: multi series


def test_run_backtest_multi_series_returns_predictions():
    """
    Test that run_backtest works end-to-end for a multi-series task and
    returns a predictions DataFrame.
    """
    result = run_backtest(
        data=df_multi,
        profile=profile_multi,
        plan=plan_multi,
        cv=cv_multi,
        cv_explanation="Multi-series CV with 5 steps.",
    )

    assert isinstance(result["predictions"], pd.DataFrame)
    assert not result["predictions"].empty


def test_run_backtest_multi_series_metrics_per_level():
    """
    Test that multi-series backtesting returns metrics with one row per
    series level.
    """
    result = run_backtest(
        data=df_multi,
        profile=profile_multi,
        plan=plan_multi,
        cv=cv_multi,
        cv_explanation="Multi-series CV with 5 steps.",
    )

    metrics = result["metrics"]
    assert isinstance(metrics, pd.DataFrame)
    assert len(metrics) >= profile_multi.n_series


# Tests: run_backtest: statistical


@pytest.mark.slow
def test_run_backtest_statistical_returns_predictions():
    """
    Test that run_backtest works for statistical forecasters (ForecasterStats
    with Arima) and returns a predictions DataFrame.
    """
    result = run_backtest(
        data=df_single,
        profile=profile_single_no_exog,
        plan=plan_statistical,
        cv=cv_single,
        cv_explanation="Statistical backtesting with ARIMA.",
    )

    assert isinstance(result["predictions"], pd.DataFrame)
    assert not result["predictions"].empty
    assert isinstance(result["metrics"], pd.DataFrame)


# Tests: run_backtest: edge cases


def test_run_backtest_short_series_runs_without_error():
    """
    Test that run_backtest handles a short time series (30 observations)
    without raising an error.
    """
    result = run_backtest(
        data=df_short,
        profile=profile_short,
        plan=plan_short,
        cv=cv_short,
        cv_explanation="Short series CV with 5 steps.",
    )

    assert isinstance(result["metrics"], pd.DataFrame)
    assert "mean_absolute_error" in result["metrics"].columns
    assert np.isfinite(result["metrics"]["mean_absolute_error"].iloc[0])
    assert "pred" in result["predictions"].columns
    assert len(result["predictions"]) == len(df_short) - cv_short.initial_train_size


def test_run_backtest_baseline_returns_metrics_and_conformal_intervals():
    """
    Test that run_backtest runs the ForecasterEquivalentDate baseline with
    conformal intervals and returns one metrics row plus the predictions.
    With an interval, skforecast 0.27 adds `coverage` and `interval_width`
    after the requested metrics.
    """
    result = run_backtest(
        data           = df_single,
        profile        = profile_single,
        plan           = plan_baseline,
        cv             = cv_single,
        cv_explanation = cv_explanation_single,
        show_progress  = False,
    )

    assert list(result["metrics"].columns) == [
        "mean_absolute_error",
        "root_mean_squared_error",
        "mean_absolute_scaled_error",
        "coverage",
        "interval_width",
    ]
    assert len(result["metrics"]) == 1
    assert {"pred", "lower_bound", "upper_bound"} <= set(result["predictions"].columns)
    assert "interval_method   = 'conformal'" in result["rendered_code"].core


def test_run_backtest_show_progress_false_keeps_column_named_like_the_keyword():
    """
    Test that `show_progress=False` only rewrites the keyword line of the
    backtesting call: an exogenous column named `'show_progress = True'`,
    written in the script as a string literal, is still found.
    """
    assistant = ForecastingAssistant()
    data = df_single.rename(columns={"promo": "show_progress = True"})
    profile = assistant.profile(data=data, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60)

    result = run_backtest(
        data           = data,
        profile        = profile.data_profile,
        plan           = plan,
        cv             = cv,
        cv_explanation = "",
        show_progress  = False,
    )

    assert "'show_progress = True'" in result["rendered_code"].full_script
    assert len(result["predictions"]) == 140


# Tests: run_backtest: series left out of some folds


def _items_starting_late(n_values: int) -> pd.DataFrame:
    """Return the long items_sales data with only the last `n_values` of item_2."""
    from tests.fixtures_datasets import df_items_sales_long

    rows = df_items_sales_long.index[df_items_sales_long["series"] == "item_2"]
    return df_items_sales_long.drop(index=rows[:-n_values])


@pytest.mark.parametrize(
    "refit, expected", [(True, "left_out"), (False, None)], ids=["refit", "complete"]
)
def test_run_backtest_explanation_names_series_left_out_of_some_folds(refit, expected):
    """
    Test that the explanation of a ForecasterRecursiveMultiSeries backtest
    names a series that some test fold where it has values did not
    forecast: item_2 has its last 60 values, and with refit the first fold
    trains on 20 of them, no more than the window of the plan (21), so its
    metrics use 7 of its 8 folds. skforecast left it out without a warning.
    With all the values of item_2 (and no refit), every fold forecasts every
    series and nothing is said.
    """
    assistant = ForecastingAssistant()
    data = _items_starting_late(60 if refit else 120)
    profile = assistant.profile(
        data, target="value", date_column="date", series_id_column="series"
    )
    plan = assistant.plan(profile, steps=5, estimator="Ridge")
    cv = TimeSeriesFold(
        steps=5, initial_train_size=80, refit=refit, verbose=False
    )

    result = run_backtest(
        data           = data,
        profile        = profile.data_profile,
        plan           = plan,
        cv             = _cv_in_time_zone(cv, data, profile.data_profile),
        cv_explanation = "CV.",
        show_progress  = False,
    )

    if expected is None:
        assert result["left_out_of_folds"] is None
        assert "Some series were not forecast" not in result["explanation"]
    else:
        text = (
            "Some series were not forecast in every test fold where they have "
            "values to evaluate ('item_2': in 7 of its 8 folds with values), "
            "so their metrics, and the average across series, leave the other "
            "folds out. ForecasterRecursiveMultiSeries leaves a series out of a "
            "fold when the training window of the fold has too few of its "
            "observations, or when it cannot predict it from the values before "
            "the fold."
        )
        assert result["left_out_of_folds"] == text
        assert result["explanation"].endswith(f" {text}")
        assert set(
            result["predictions"].loc[result["predictions"]["level"] == "item_2", "fold"]
        ) == {1, 2, 3, 4, 5, 6, 7}
