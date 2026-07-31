# Fixtures for LLM context tests

import numpy as np
import pandas as pd

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import (
    BacktestResult,
    CandidateFailure,
    ComparisonResult,
    ForecastResult,
    SingleRunResult,
)

from .fixtures_assistant import df_multi_long, df_no_exog, df_single

assistant = ForecastingAssistant()


# ---------------------------------------------------------------------------
# Profiles and plans
#
# Derived from the assistant rather than hardcoded on purpose. The golden
# files are meant to capture the whole deterministic payload the LLM sees,
# so a change in the profiler or planner wording must show up as a diff.
# ---------------------------------------------------------------------------
profile_single = assistant.profile(
    data=df_no_exog, target="sales", date_column="date"
)
profile_exog = assistant.profile(
    data=df_single, target="sales", date_column="date"
)
profile_multi = assistant.profile(
    data             = df_multi_long,
    target           = "value",
    date_column      = "date",
    series_id_column = "series_id",
)

plan_single = assistant.plan(profile_single, steps=5)
plan_interval = assistant.plan(profile_exog, steps=5, interval=[0.1, 0.9])
plan_multi = assistant.plan(profile_multi, steps=3)


# ---------------------------------------------------------------------------
# Prediction frames
#
# `1111.1111` is an interior value of the `pred` column: it is neither the
# minimum, the maximum, nor the mean, so it can only reach the context
# through a row-level rendering. The privacy tests search for it.
# ---------------------------------------------------------------------------
ROW_LEVEL_MARKER = "1111.1111"

_forecast_index = pd.date_range("2023-04-11", periods=5, freq="D")

predictions_single = pd.DataFrame(
    {"pred": [1000.0, 1111.1111, 1250.0, 1375.0, 2000.0]},
    index=_forecast_index,
)

predictions_interval = pd.DataFrame(
    {
        "pred":        [1000.0, 1111.1111, 1250.0, 1375.0, 2000.0],
        "lower_bound": [900.0, 980.0, 1100.0, 1200.0, 1800.0],
        "upper_bound": [1100.0, 1240.0, 1400.0, 1550.0, 2200.0],
    },
    index=_forecast_index,
)

predictions_multi = pd.DataFrame(
    {
        "level": ["store_a", "store_a", "store_a",
                  "store_b", "store_b", "store_b"],
        "pred":  [1000.0, 1111.1111, 1250.0, 1500.0, 1750.0, 2000.0],
    },
    index=pd.DatetimeIndex(
        ["2023-04-11", "2023-04-12", "2023-04-13",
         "2023-04-11", "2023-04-12", "2023-04-13"]
    ),
)

# 40 rows, above `MAX_CONTEXT_DATAFRAME_ROWS`, so the golden captures the
# truncation notice as well as the head, tail, and per-column summary.
predictions_backtest = pd.DataFrame(
    {"pred": np.arange(40, dtype=float) * 2.5 + 1000.0},
    index=pd.date_range("2023-03-02", periods=40, freq="D"),
)

predictions_backtest_multi = pd.DataFrame(
    {
        "level": ["store_a"] * 20 + ["store_b"] * 20,
        "pred":  np.arange(40, dtype=float) * 2.5 + 1000.0,
    },
    index=pd.date_range("2023-03-22", periods=20, freq="D").repeat(2),
)


# ---------------------------------------------------------------------------
# Metrics, cross-validation, and deterministic summaries
# ---------------------------------------------------------------------------
metrics_single = pd.DataFrame(
    {"series": ["sales"], "MAE": [2.5], "MSE": [9.25], "MASE": [0.8]}
)

metrics_multi = pd.DataFrame(
    {
        "series": ["store_a", "store_b"],
        "MAE":    [2.5, 3.5],
        "MSE":    [9.25, 16.5],
        "MASE":   [0.8, 1.2],
    }
)

cv_config = {
    "steps": 5,
    "initial_train_size": 70,
    "refit": False,
    "fixed_train_size": True,
    "gap": 0,
    "n_folds": 6,
}

explanation_backtest = (
    "Backtested with 6 folds of 5 steps each, starting from an initial "
    "training window of 70 observations, without refitting."
)

code_single = "# forecast script\nforecaster.fit(y=y)\n"
code_backtest = "# backtest script\nbacktesting_forecaster(forecaster, y, cv)\n"


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------
def make_single_run_result() -> SingleRunResult:
    """
    Build the shared single-run base class directly.

    Instantiated on its own so the contract tests cover the
    `_build_llm_context` implementation every single run inherits, not
    only the two subclasses that exist today.

    Returns
    -------
    result : SingleRunResult
        Single run carrying a profile, plan, code, predictions, and
        metrics.
    """

    return SingleRunResult(
        profile     = profile_single,
        plan        = plan_single,
        code        = code_single,
        predictions = predictions_single,
        metrics     = metrics_single,
    )


def make_forecast_result(
    *,
    profile      = profile_single,
    plan         = plan_single,
    predictions  = predictions_single,
    metrics      = metrics_single,
) -> ForecastResult:
    """
    Build a `ForecastResult` without executing a forecasting pipeline.

    Parameters
    ----------
    profile : ForecastingProfile, default `profile_single`
        Profile carried by the result.
    plan : ForecastPlan, default `plan_single`
        Plan carried by the result.
    predictions : pandas DataFrame, default `predictions_single`
        Forecasted values carried by the result.
    metrics : pandas DataFrame, default `metrics_single`
        Evaluation metrics carried by the result. Pass None to reproduce
        prediction mode, where there is no ground truth to score against.

    Returns
    -------
    result : ForecastResult
        Result of a single forecasting run.
    """

    return ForecastResult(
        profile     = profile,
        plan        = plan,
        code        = code_single,
        predictions = predictions,
        metrics     = metrics,
    )


def make_backtest_result(
    *,
    profile      = profile_single,
    plan         = plan_single,
    predictions  = predictions_backtest,
    metrics      = metrics_single,
) -> BacktestResult:
    """
    Build a `BacktestResult` without running a backtest.

    Parameters
    ----------
    profile : ForecastingProfile, default `profile_single`
        Profile carried by the result.
    plan : ForecastPlan, default `plan_single`
        Plan carried by the result.
    predictions : pandas DataFrame, default `predictions_backtest`
        Backtest predictions carried by the result.
    metrics : pandas DataFrame, default `metrics_single`
        Backtest metrics carried by the result.

    Returns
    -------
    result : BacktestResult
        Result of a single backtesting run.
    """

    return BacktestResult(
        profile     = profile,
        plan        = plan,
        code        = code_backtest,
        predictions = predictions,
        metrics     = metrics,
        cv_config   = cv_config,
        explanation = explanation_backtest,
    )


def make_comparison_result(*, n_candidates: int = 2, with_failure: bool = False):
    """
    Build a `ComparisonResult` without backtesting any candidate.

    Every candidate shares the same plan object, so the cost of the
    fixture stays flat as `n_candidates` grows and the leaderboard cap
    can be exercised cheaply.

    Parameters
    ----------
    n_candidates : int, default 2
        Number of candidates that ran successfully.
    with_failure : bool, default False
        Whether to append one failed candidate to `failures` and to the
        leaderboard.

    Returns
    -------
    result : ComparisonResult
        Comparison ranked ascending by MAE.
    """

    candidates = {}
    rows = []
    for i in range(n_candidates):
        name = f"candidate_{i + 1:02d}"
        mae = 1.5 + i
        candidates[name] = BacktestResult(
            profile     = profile_single,
            plan        = plan_single,
            code        = f"# {name} code",
            predictions = pd.DataFrame({"pred": [1.0, 2.0, 3.0, 4.0, 5.0]}),
            metrics     = pd.DataFrame({"MAE": [mae]}),
            cv_config   = cv_config,
            explanation = f"Backtest of {name}.",
        )
        rows.append({
            "rank":       i + 1,
            "name":       name,
            "forecaster": "ForecasterRecursive",
            "estimator":  "Ridge",
            "MAE":        mae,
        })

    failures = {}
    if with_failure:
        failures["broken"] = CandidateFailure(
            error_type     = "ImportError",
            message        = "No module named 'lightgbm'",
            traceback      = "Traceback (most recent call last):\n  SECRET_FRAME",
            generated_code = "# broken code",
        )
        for row in rows:
            row["error"] = None
        rows.append({
            "rank":       n_candidates + 1,
            "name":       "broken",
            "forecaster": "ForecasterRecursive",
            "estimator":  "LGBMRegressor",
            "MAE":        float("nan"),
            "error":      "ImportError: No module named 'lightgbm'",
        })

    return ComparisonResult(
        profile        = profile_single,
        cv_config      = cv_config,
        results        = pd.DataFrame(rows),
        candidates     = candidates,
        failures       = failures,
        ranking_metric = "MAE",
        explanation    = (
            f"Compared {n_candidates} configurations, ranked ascending by MAE."
        ),
    )


# ---------------------------------------------------------------------------
# Golden scenarios
#
# One entry per rendered context that is pinned to a file under
# `tests/tests_llm/golden/`. Regenerate with
# `python tools/update_golden_llm_contexts.py` after an intentional change.
# ---------------------------------------------------------------------------
GOLDEN_SCENARIOS = {
    "forecast_single_series_no_intervals": lambda: make_forecast_result(),
    "forecast_single_series_with_intervals": lambda: make_forecast_result(
        profile     = profile_exog,
        plan        = plan_interval,
        predictions = predictions_interval,
    ),
    "forecast_prediction_mode_no_metrics": lambda: make_forecast_result(
        metrics=None
    ),
    "forecast_multi_series": lambda: make_forecast_result(
        profile     = profile_multi,
        plan        = plan_multi,
        predictions = predictions_multi,
        metrics     = metrics_multi,
    ),
    "backtest_single_series": lambda: make_backtest_result(),
    "backtest_multi_series": lambda: make_backtest_result(
        profile     = profile_multi,
        plan        = plan_multi,
        predictions = predictions_backtest_multi,
        metrics     = metrics_multi,
    ),
    "comparison_all_succeeded": lambda: make_comparison_result(),
    "comparison_with_failures": lambda: make_comparison_result(
        with_failure=True
    ),
}
