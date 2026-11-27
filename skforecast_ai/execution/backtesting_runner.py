################################################################################
#                          Backtesting Runner                                  #
#                                                                              #
# Programmatic execution of backtesting workflows using skforecast APIs        #
# Render the backtesting code as a string and code via exec()                  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import re
from typing import Any, Callable
import numpy as np
import pandas as pd
from skforecast.model_selection import TimeSeriesFold

from ..rendering.backtesting import (
    render_backtesting_baseline,
    render_backtesting_foundation,
    render_backtesting_multi_series,
    render_backtesting_multivariate,
    render_backtesting_single_series,
    render_backtesting_statistical,
)
from .._constants import N_EVALUATED_COLUMN, OBSERVED_COLUMN
from ..profiling.data_profile import compact_dates_as_text
from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ..exceptions import InvalidInputError
from .comparison import aggregate_metrics
from .interval_coverage import INTERVAL_METRICS, describe_interval_coverage
from ._exec import exec_rendered

# Column of the mean absolute error in `error_by_step`, the table of the
# error by step of the horizon that the script computes.
ERROR_BY_STEP_COLUMN = "mean_absolute_error"

# Steps of the horizon, and series, that the summary names from
# `error_by_step`; the rest are in the table.
MAX_SUMMARY_STEPS = 12
MAX_SUMMARY_SERIES = 5

_RENDER_DISPATCH: dict[
    str, Callable[[ForecastPlan, DataProfile, Any], RenderedScript]
] = {
    "single_series": render_backtesting_single_series,
    "multi_series": render_backtesting_multi_series,
    "multivariate": render_backtesting_multivariate,
    "statistical": render_backtesting_statistical,
    "foundation": render_backtesting_foundation,
    "baseline": render_backtesting_baseline,
}


def run_backtest(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    cv: Any,
    cv_explanation: str,
    show_progress: bool = True,
) -> dict[str, Any]:
    """
    Execute a backtesting workflow by running the generated code.

    The code executed is identical to what `render_backtesting_script`
    produces (minus the CSV loading preamble). This guarantees that the
    `BacktestResult.code` field always reflects exactly what was run.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset with DatetimeIndex, target, and optional exog.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Validated forecast plan.
    cv : TimeSeriesFold
        Cross-validation fold splitter.
    cv_explanation : str
        Human-readable CV explanation (from `create_cv`).
    show_progress : bool, default True
        Whether to display a progress bar during backtesting.

    Returns
    -------
    result : dict
        Dictionary with keys `'metrics'`, `'predictions'`, `'error_by_step'`
        (the mean absolute error by step of the horizon, and by series with
        several, that the script computes), `'rendered_code'`,
        `'explanation'` and `'left_out_of_folds'`: the text about the series
        that the backtest did not forecast in some test fold where they have
        a value (see `series_left_out_of_folds`), also at the end of the
        explanation, or None.
    """

    # Render backtesting code
    rendered = render_backtesting_script(profile, plan, cv)

    # Execute the rendered code with `data` pre-loaded in the namespace:
    # dates of whole numbers (20200131) as text, as the script turns them
    # after reading the CSV file.
    namespace = _exec_rendered_code(
        rendered, compact_dates_as_text(data, profile.date_column), show_progress
    )

    # Extract results from namespace
    metrics = namespace.get("metrics")
    predictions = namespace.get("predictions")
    error_by_step = namespace.get("error_by_step")

    # Imported here: `_last_window` imports the execution package.
    from .._last_window import describe_left_out_of_folds, series_left_out_of_folds

    # The series a fold left out are read from the predictions, which
    # carry the level and the fold of each one: skforecast does not warn
    # about them when the script runs with `suppress_warnings=True`.
    left_out = describe_left_out_of_folds(
        left_out = series_left_out_of_folds(
                       data        = data,
                       profile     = profile,
                       plan        = plan,
                       cv          = cv,
                       predictions = predictions,
                   ),
        plan     = plan,
    )

    # Build explanation
    explanation = _build_backtest_explanation(
        cv_explanation = cv_explanation,
        metrics        = metrics,
        predictions    = predictions,
        interval       = plan.interval,
        error_by_step  = error_by_step,
        target_missing = (
            profile.n_series == 1
            and (bool(profile.missing_target) or profile.has_gaps)
        ),
    )
    if left_out is not None:
        explanation = f"{explanation} {left_out}"

    return {
        "metrics": metrics,
        "predictions": predictions,
        "error_by_step": error_by_step,
        "rendered_code": rendered,
        "explanation": explanation,
        "left_out_of_folds": left_out,
    }


def render_backtesting_script(
    profile: DataProfile,
    plan: ForecastPlan,
    cv: TimeSeriesFold,
) -> RenderedScript:
    """
    Render structured backtesting code from a plan, profile, and CV.

    Parameters
    ----------
    profile : DataProfile
        Profile of the input dataset.
    plan : ForecastPlan
        Validated forecast plan.
    cv : TimeSeriesFold
        Cross-validation fold splitter.

    Returns
    -------
    rendered : RenderedScript
        Structured code split into imports, data_loading, and core
        sections.
    """
    render_fn = _RENDER_DISPATCH.get(plan.task_type)
    if render_fn is None:
        supported = list(_RENDER_DISPATCH.keys())
        raise InvalidInputError(
            f"Unsupported task_type '{plan.task_type}'. "
            f"Supported types: {supported}",
            field = "task_type",
        )
    return render_fn(plan, profile, cv)


def _exec_rendered_code(
    rendered: RenderedScript,
    data: pd.DataFrame,
    show_progress: bool = True,
) -> dict[str, Any]:
    """
    Execute the rendered backtesting code with data injected into the
    namespace.

    Parameters
    ----------
    rendered : RenderedScript
        Structured rendered code.
    data : pandas DataFrame
        Input dataset to inject as the `data` variable.
    show_progress : bool, default True
        Whether to display a progress bar during backtesting.

    Returns
    -------
    namespace : dict
        Executed namespace containing all variables produced by the
        code.
    """
    code_to_exec = rendered.executable

    # The rendered script always shows `show_progress = True`, so the value
    # is patched only in the code that runs, never in the code returned to
    # the user. The pattern is anchored to the keyword line of the
    # backtesting call: a column name written as a string literal in the
    # script (`'show_progress = True'`) is never rewritten.
    if not show_progress:
        code_to_exec = re.sub(
            r"^(\s+show_progress\s*=\s*)True,$",
            r"\g<1>False,",
            code_to_exec,
            flags=re.MULTILINE,
        )

    return exec_rendered(code_to_exec, {"data": data.copy()}, "<backtesting>")


def _dates_without_value(predictions: pd.DataFrame | None) -> int:
    """
    Count the test dates of a backtest of a single series whose target has
    no observed value (`y_true` missing), which skforecast leaves out of the
    metrics. A date that overlapping folds predict twice counts once, as in
    `n_evaluated`. Zero for several series (a `level` column), whose
    backtest drops them per series, and for predictions without `y_true`.
    """
    if (
        predictions is None
        or OBSERVED_COLUMN not in predictions.columns
        or "level" in predictions.columns
    ):
        return 0

    return int(predictions.index[predictions[OBSERVED_COLUMN].isna()].nunique())


def _dates_without_value_known(predictions: pd.DataFrame | None) -> bool:
    """
    Whether `_dates_without_value` can count the test dates without an
    observed value: predictions of a single series with `y_true`.
    """
    return (
        predictions is not None
        and OBSERVED_COLUMN in predictions.columns
        and "level" not in predictions.columns
    )


def _shown_steps(steps: list[int]) -> list[int]:
    """
    Steps of the horizon named in the summary: all of them up to
    `MAX_SUMMARY_STEPS`, otherwise that many spread evenly from the first
    to the last.
    """
    if len(steps) <= MAX_SUMMARY_STEPS:
        return steps

    positions = np.linspace(0, len(steps) - 1, MAX_SUMMARY_STEPS).round()
    return [steps[int(position)] for position in positions]


def _describe_error_by_step(error_by_step: pd.DataFrame | None) -> str | None:
    """
    Describe the mean absolute error by step of the horizon that the script
    computes (`error_by_step`), so a reader sees how the error changes with
    the horizon. With one series, the error of each step (of up to
    `MAX_SUMMARY_STEPS` steps); with several, that of the first and the
    last step of the first `MAX_SUMMARY_SERIES` series, since the errors
    of different series are in different units. None when the table is
    missing or every error in it is missing.
    """
    if error_by_step is None or ERROR_BY_STEP_COLUMN not in error_by_step.columns:
        return None
    frame = error_by_step.dropna(subset=[ERROR_BY_STEP_COLUMN])
    if frame.empty:
        return None

    if "level" not in frame.columns or frame["level"].nunique() == 1:
        frame = frame.sort_values("step")
        steps = [int(step) for step in frame["step"]]
        errors = dict(zip(steps, frame[ERROR_BY_STEP_COLUMN]))
        shown = _shown_steps(steps)
        listed = ", ".join(f"step {step}: {errors[step]:.4f}" for step in shown)
        count = "" if len(shown) == len(steps) else (
            f" ({len(shown)} of {len(steps)} steps shown)"
        )
        return (
            f"Mean absolute error by step of the horizon (error_by_step)"
            f"{count}: {listed}."
        )

    series = list(dict.fromkeys(frame["level"]))
    ends = {}
    for level in series[:MAX_SUMMARY_SERIES]:
        rows = frame[frame["level"] == level].sort_values("step")
        ends[level] = (rows.iloc[0], rows.iloc[-1])
    which = (
        "each series" if len(series) <= MAX_SUMMARY_SERIES
        else f"the first {MAX_SUMMARY_SERIES} of {len(series)} series"
    )
    steps = {
        (int(first["step"]), int(last["step"])) for first, last in ends.values()
    }
    if len(steps) == 1:
        # The steps are named once when every series has the same ones,
        # which keeps the sentence short with many series.
        first_step, last_step = steps.pop()
        listed = "; ".join(
            f"{level}: {first[ERROR_BY_STEP_COLUMN]:.4f}"
            + (
                "" if first_step == last_step
                else f" and {last[ERROR_BY_STEP_COLUMN]:.4f}"
            )
            for level, (first, last) in ends.items()
        )
        at = (
            f"at step {first_step}" if first_step == last_step
            else f"at steps {first_step} and {last_step}"
        )
        return (
            f"Mean absolute error by step of the horizon (error_by_step) of "
            f"{which}, {at}: {listed}."
        )

    listed = "; ".join(
        f"{level}: {first[ERROR_BY_STEP_COLUMN]:.4f} at step {int(first['step'])}"
        + (
            "" if first["step"] == last["step"]
            else f" and {last[ERROR_BY_STEP_COLUMN]:.4f} at step "
                 f"{int(last['step'])}"
        )
        for level, (first, last) in ends.items()
    )
    return (
        f"Mean absolute error by step of the horizon (error_by_step), at the "
        f"first and the last step of {which}: {listed}."
    )


def _build_backtest_explanation(
    cv_explanation: str,
    metrics: pd.DataFrame,
    predictions: pd.DataFrame | None = None,
    interval: list[float] | None = None,
    error_by_step: pd.DataFrame | None = None,
    target_missing: bool = False,
) -> str:
    """
    Build the full backtesting explanation.

    Concatenates the CV explanation with a post-execution summary. With a
    prediction interval, the coverage and the width that skforecast
    measured (`coverage` and `interval_width` of the metrics) are not
    listed with the other metrics: a sentence of their own states them by
    series next to the nominal coverage of the interval. Neither is the
    number of points evaluated (`n_evaluated`), which is not a metric: a
    sentence after the results states it, and with a single series another
    one counts the test dates without an observed value, which skforecast
    leaves out of the metrics (or says that there is none, when the target
    has missing values elsewhere). Then the mean absolute error by step of
    the horizon that the script computes (see `_describe_error_by_step`).

    Parameters
    ----------
    cv_explanation : str
        Explanation from `create_cv`.
    metrics : pandas DataFrame
        Backtesting metrics result.
    predictions : pandas DataFrame, default None
        Backtesting predictions, which give the number of predictions the
        coverage of each series is measured on.
    interval : list of float, default None
        Prediction interval of the plan.
    error_by_step : pandas DataFrame, default None
        Mean absolute error by step of the horizon computed by the script.
    target_missing : bool, default False
        Whether the target of a single series has missing values or
        missing timestamps, so the summary also says when no test date is
        left out of the metrics.

    Returns
    -------
    explanation : str
        Combined CV + results explanation.
    """

    # One scalar per metric. For multi-series backtests skforecast appends
    # aggregate rows (`average`, `weighted_average`, `pooling`); averaging
    # the whole column would blend them with the per-series rows into a
    # number that matches no row, so the `average` row is used instead.
    aggregated = aggregate_metrics(metrics)
    summary_parts = [
        f"{name}: {value:.4f}"
        for name, value in aggregated.items()
        if isinstance(value, float)
        and name not in (*INTERVAL_METRICS, N_EVALUATED_COLUMN)
    ]

    explanation = cv_explanation
    if summary_parts:
        metrics_str = ", ".join(summary_parts)
        multi_series = metrics is not None and "levels" in metrics.columns
        label = "Results (average across series)" if multi_series else "Results"
        explanation = f"{cv_explanation} {label}: {metrics_str}."
        # The count of points is stated apart from the metrics, so it is
        # never read as an error figure. In the `average` row of several
        # series skforecast sums it, it does not average it.
        n_evaluated = aggregated.get(N_EVALUATED_COLUMN)
        if n_evaluated is not None and not pd.isna(n_evaluated):
            across = " across the series" if multi_series else ""
            explanation = (
                f"{explanation} They are measured on {int(n_evaluated)} "
                f"predictions with an observed value{across} (n_evaluated)."
            )
        without_value = _dates_without_value(predictions)
        if without_value:
            dates = "test date" if without_value == 1 else "test dates"
            explanation = (
                f"{explanation} The metrics leave out {without_value} {dates} "
                f"without an observed value of the target."
            )
        elif target_missing and _dates_without_value_known(predictions):
            # The plan and `create_cv()` say what happens to a test date
            # without a value; this says that no test date had one.
            explanation = (
                f"{explanation} Every test date has an observed value of the "
                f"target: the metrics leave none out."
            )
        by_step = _describe_error_by_step(error_by_step)
        if by_step is not None:
            explanation = f"{explanation} {by_step}"
    coverage = describe_interval_coverage(metrics, predictions, interval)
    if coverage is not None:
        explanation = f"{explanation} {coverage}"

    return explanation
