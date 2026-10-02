################################################################################
#                               llm: Context                                   #
#                                                                              #
# Context message building and DataFrame serialization for LLM prompts.        #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import ast
import re
from typing import Any
import pandas as pd
from .._constants import (
    CONTEXT_HEAD_TAIL_ROWS,
    MAX_CONTEXT_DATAFRAME_ROWS,
    MAX_DESCRIBE_ITEMS,
    MAX_LEADERBOARD_ROWS,
)
from ..schemas import ComparisonResult, ForecastingProfile, ForecastPlan


# Per-series lines in the dataset and profile sections are capped so a
# wide multi-series dataset cannot crowd the prompt.
MAX_STATS_SERIES = 5
MAX_PACF_LAGS = 15

# Limits that only `describe()` applies (`for_describe=True`), so its text
# stays short with hundreds of series: at most `MAX_DESCRIBE_ITEMS` items
# of any list, and the first `MAX_STATS_SERIES` series of the metrics plus
# the aggregated rows. Each cut says how many items there were. The
# context of `ask()` keeps its own limits.
_AGGREGATED_METRIC_ROWS = ("average", "weighted_average", "pooling")

# Sentences addressed to the LLM of `ask()`: they tell it how to use the
# context, they state nothing about the result. `describe()` leaves them
# out (`for_describe=True`); with `for_describe=False` every renderer
# writes them exactly where it always did.
PLAN_CODE_NOTE = (
    "Note: A validated Python script implementing this plan is "
    "generated separately. Do not generate code yourself."
)
SCRIPT_NOTE = (
    "The script is available to the user as `result.code`; describe it "
    "from this summary and the plan, do not reproduce it."
)
RANKING_NOTE = (
    "Do not re-rank the candidates or recompute the table, and do not "
    "suggest reasons for the ranking beyond the metric values: the "
    "leaderboard reports what happened, not why."
)
LEADERBOARD_NOTE = (
    "Do not name, count, or score a candidate that does not appear below."
)


def _fmt(value: float) -> str:
    """Format a statistic with four significant digits."""
    return f"{value:.4g}"


def _limited(items, limit: int):
    """Yield at most `limit` items."""
    for position, item in enumerate(items):
        if position >= limit:
            return
        yield item


def _first_items(items: list, for_describe: bool) -> tuple[list, str]:
    """
    Keep the first `MAX_DESCRIBE_ITEMS` items of a list for `describe()`.

    Parameters
    ----------
    items : list
        Items to show.
    for_describe : bool
        Whether the list is rendered for `describe()`. When False, every
        item is kept.

    Returns
    -------
    shown : list
        Items to show.
    suffix : str
        `' (first N of M)'` when the list was cut, an empty string
        otherwise.
    """

    if not for_describe or len(items) <= MAX_DESCRIBE_ITEMS:
        return list(items), ""

    return (
        list(items[:MAX_DESCRIBE_ITEMS]),
        f" (first {MAX_DESCRIBE_ITEMS} of {len(items)})",
    )


def _tag(name: str, body: str) -> str:
    """
    Wrap a rendered section body in an XML-style tag.

    Markdown headings are ambiguous inside the prompt: the loaded skills,
    the context block, and the answer the LLM is asked to produce all use
    `##`. Tagging each section instead makes the boundary between injected
    deterministic output and everything else unambiguous.

    Parameters
    ----------
    name : str
        Tag name.
    body : str
        Already rendered section body.

    Returns
    -------
    section : str
        Body wrapped in an opening and closing tag.
    """

    return f"<{name}>\n{body}\n</{name}>"


def join_sections(sections: list[str | None]) -> str:
    """
    Compose rendered sections into a single `<forecast_context>` block.

    This is the composition entry point for result types. A result builds
    the list of sections it wants and joins them, so adding a new result
    type never changes the signature of an existing renderer or forces
    unrelated callers to pass arguments they ignore.

    Parameters
    ----------
    sections : list of str or None
        Rendered sections in the order they should appear. Entries that
        are None or empty are dropped, so a renderer that had nothing to
        say can be listed unconditionally.

    Returns
    -------
    context : str
        Wrapped context block, or an empty string when every section is
        empty.

    Examples
    --------
    >>> join_sections([                                    # doctest: +SKIP
    ...     render_dataset_section(profile),
    ...     render_plan_section(plan),
    ... ])

    """

    rendered = [section for section in sections if section]
    if not rendered:
        return ""

    return (
        "<forecast_context>\n"
        + "\n".join(rendered)
        + "\n</forecast_context>"
    )


def _serialize_dataframe(
    df: Any, max_rows: int = MAX_CONTEXT_DATAFRAME_ROWS
) -> str:
    """
    Serialize a DataFrame for LLM context, truncating if too large.

    Parameters
    ----------
    df : pandas DataFrame
        Frame to serialize.
    max_rows : int, default `MAX_CONTEXT_DATAFRAME_ROWS`
        Frames with at most this many rows are rendered in full. Larger
        frames are reduced to their head and tail plus a per-column
        summary.

    Returns
    -------
    serialized : str
        Rendered frame.
    """

    n_rows = len(df)
    if n_rows <= max_rows:
        return f"Total rows: {n_rows} (all shown below).\n{df.to_string()}"

    head = df.head(CONTEXT_HEAD_TAIL_ROWS).to_string()
    tail = df.tail(CONTEXT_HEAD_TAIL_ROWS).to_string(header=False)
    omitted = n_rows - 2 * CONTEXT_HEAD_TAIL_ROWS

    # State the row count and the limits of the sample explicitly. Without
    # this, an early row and a late row get compared as if they were
    # adjacent, and the resulting sampling artifact is reported as a trend
    # across the horizon.
    notice = (
        f"Total rows: {n_rows}. Only the first {CONTEXT_HEAD_TAIL_ROWS} and "
        f"last {CONTEXT_HEAD_TAIL_ROWS} rows are shown; the {omitted} interior "
        f"rows were not provided. Do not describe trends, growth, or "
        f"progression across the horizon from these rows, and do not compare "
        f"an early row against a late row as if they were adjacent. Use the "
        f"per-column summary below for any statement about the full set of "
        f"rows."
    )

    # `fold` is an identifier, not a measurement: the mean fold index is
    # noise that would be quoted back as if it described the predictions.
    numeric_cols = df.select_dtypes(include="number").drop(
        columns="fold", errors="ignore"
    )
    stats = ""
    if not numeric_cols.empty:
        # Report per-column statistics rather than a single blended value.
        # Collapsing point predictions and interval bounds (e.g. `pred`,
        # `lower_bound`, `upper_bound`) into one min/max/mean would let the
        # reader mistake an interval edge for a forecast value.
        #
        # No format spec: these values are quoted back as facts, and a
        # rounded figure presented as `max` is exactly the fabricated number
        # the prompt forbids. Verbosity is the cheaper failure.
        lines = ["", "Per-column summary (all rows):"]
        for col in numeric_cols.columns:
            col_data = numeric_cols[col]
            lines.append(
                f"  {col}: min={col_data.min()}, "
                f"max={col_data.max()}, mean={col_data.mean()}"
            )
        # A multi-series frame pools every series into the summary above,
        # so a question about one series ("what is the average forecast for
        # item_2") has no answer. Break the point forecast down by level,
        # capped like the per-series target statistics of the dataset
        # section. Foundation models predicting quantiles have no `pred`
        # column: their point forecast is the median, `q_0.5`.
        point_col = next(
            (col for col in ("pred", "q_0.5") if col in numeric_cols.columns),
            None,
        )
        if "level" in df.columns and point_col is not None:
            levels = list(dict.fromkeys(df["level"]))
            if len(levels) > 1:
                shown = levels[:MAX_STATS_SERIES]
                suffix = (
                    "" if len(levels) <= MAX_STATS_SERIES
                    else f" (first {MAX_STATS_SERIES} of {len(levels)} levels)"
                )
                lines.append(
                    f"Per-level summary of {point_col} (all rows){suffix}:"
                )
                for level in shown:
                    level_pred = df.loc[df["level"] == level, point_col]
                    lines.append(
                        f"  {level}: min={level_pred.min()}, "
                        f"max={level_pred.max()}, mean={level_pred.mean()}"
                    )
        stats = "\n" + "\n".join(lines)

    return (
        f"{notice}\n\n{head}\n... ({omitted} rows omitted) ...\n{tail}{stats}"
    )


def _summarize_dataframe(df: Any) -> str:
    """Produce a privacy-safe summary without row-level values."""
    parts = [f"Shape: {df.shape[0]} rows x {df.shape[1]} columns"]
    parts.append(f"Columns: {list(df.columns)}")
    # `fold` is an identifier, not a measurement (as in
    # `_serialize_dataframe`): its statistics would be quoted back as if
    # they described the predictions, so only the number of folds is given.
    if "fold" in df.columns:
        parts.append(f"Folds: {df['fold'].nunique()}")
    numeric_cols = df.select_dtypes(include="number").drop(
        columns="fold", errors="ignore"
    )
    if not numeric_cols.empty:
        # No format spec, for the same reason as `_serialize_dataframe`:
        # when row-level values are withheld these statistics are all the
        # LLM has, so they must be exact rather than tidy.
        for col in numeric_cols.columns:
            parts.append(
                f"  {col}: min={numeric_cols[col].min()}, "
                f"max={numeric_cols[col].max()}, "
                f"mean={numeric_cols[col].mean()}, "
                f"std={numeric_cols[col].std()}"
            )
    if hasattr(df.index, "min") and len(df) > 0:
        parts.append(f"Index range: {df.index.min()} to {df.index.max()}")
    return "\n".join(parts)


def render_dataset_section(
    profile: ForecastingProfile | None,
    for_describe: bool = False,
) -> str:
    """
    Render the `<dataset>` section describing the profiled data.

    Parameters
    ----------
    profile : ForecastingProfile, None
        Profile to describe. None renders nothing.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which keeps the
        first `MAX_DESCRIBE_ITEMS` items of each list (target columns,
        exogenous columns, series with missing values, warnings) and says
        how many there are.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `profile` is None.
    """

    if profile is None:
        return ""

    dp = profile.data_profile
    exog_columns, exog_suffix = _first_items(dp.exog_columns, for_describe)
    exog = ", ".join(exog_columns) + exog_suffix if exog_columns else "none"
    parts = [
        f"- Observations: {dp.n_observations_display}",
        f"- Series: {dp.n_series}",
        f"- Frequency: {dp.frequency or 'unknown'}",
    ]
    if dp.n_series > 1:
        # The profile explanation sizes the estimator on the pooled count;
        # state it here so the two numbers are not read as a contradiction.
        parts.insert(
            1, f"- Observations pooled across series: {dp.n_total_observations}"
        )

    # Date range of the union index, so questions about the period covered
    # (and metrics that depend on it) can be answered without the data.
    starts = [info.start for info in dp.series_lengths.values() if info.start]
    ends = [info.end for info in dp.series_lengths.values() if info.end]
    if starts and ends:
        parts.append(f"- Date range: {min(starts)} to {max(ends)}")

    target = dp.target
    if isinstance(target, list):
        shown, suffix = _first_items(target, for_describe)
        target = f"{shown}{suffix}" if suffix else target
    parts += [
        f"- Target: {target}",
        f"- Exogenous columns: {exog}",
    ]
    if dp.categorical_exog:
        categorical, suffix = _first_items(dp.categorical_exog, for_describe)
        parts.append(
            f"- Categorical exogenous columns: {', '.join(categorical)}{suffix}"
        )

    # Scale of the target. Needed to judge MAPE (unreliable near zero) and
    # to put MAE and MSE in perspective, both rules the role prompt sets.
    for series, stats in _limited(dp.target_stats.items(), MAX_STATS_SERIES):
        if not stats:
            continue
        label = "Target statistics" if len(dp.target_stats) == 1 else f"Target statistics ({series})"
        parts.append(
            f"- {label}: min {_fmt(stats['min'])}, max {_fmt(stats['max'])}, "
            f"mean {_fmt(stats['mean'])}, std {_fmt(stats['std'])}"
        )
    if for_describe and len(dp.target_stats) > MAX_STATS_SERIES:
        parts.append(
            f"- Target statistics shown (first {MAX_STATS_SERIES} of "
            f"{len(dp.target_stats)} series)"
        )

    # Missing values are stated even when there are none: "not mentioned"
    # and "none" are different answers to the user.
    if dp.missing_target:
        parts.append(
            f"- Missing in target: "
            f"{_missing_counts(dp.missing_target, 'series', for_describe)}"
        )
    if dp.missing_exog:
        parts.append(
            f"- Missing in exog: "
            f"{_missing_counts(dp.missing_exog, 'columns', for_describe)}"
        )
    if not dp.missing_target and not dp.missing_exog:
        parts.append("- Missing values: none")

    irregularities = []
    if dp.has_gaps:
        irregularities.append("gaps in the index")
    if dp.has_duplicate_timestamps:
        irregularities.append("duplicate timestamps")
    if not dp.index_is_monotonic:
        irregularities.append("index not sorted")
    parts.append(
        f"- Index irregularities: {', '.join(irregularities) if irregularities else 'none detected'}"
    )
    warnings_shown, suffix = _first_items(dp.warnings, for_describe)
    for warning in warnings_shown:
        parts.append(f"- Data warning: {warning}")
    if suffix:
        parts.append(f"- Data warnings shown{suffix}")

    return _tag("dataset", "\n".join(parts))


def _missing_counts(counts: dict, noun: str, for_describe: bool) -> str:
    """
    Render the missing values per series or per column.

    Parameters
    ----------
    counts : dict
        Number of missing values per series or column.
    noun : str
        What the keys are (`'series'` or `'columns'`), used in the note
        of a cut.
    for_describe : bool
        Whether the counts are rendered for `describe()`, which keeps the
        first `MAX_DESCRIBE_ITEMS` of them and states the totals. When
        False, the dict is rendered as it is.

    Returns
    -------
    text : str
        Rendered counts.
    """

    if not for_describe or len(counts) <= MAX_DESCRIBE_ITEMS:
        return f"{counts}"

    shown = dict(list(counts.items())[:MAX_DESCRIBE_ITEMS])

    return (
        f"{shown} (first {MAX_DESCRIBE_ITEMS} of {len(counts)} {noun}, "
        f"{sum(counts.values())} missing values in all)"
    )


def render_profile_decision_section(
    profile: ForecastingProfile | None,
    for_describe: bool = False,
) -> str:
    """
    Render the `<profile_decision>` section.

    Carries the deterministic rationale for the modeling decisions the
    profiler made, so the LLM restates it rather than inventing one.

    Parameters
    ----------
    profile : ForecastingProfile, None
        Profile whose explanation is rendered. None renders nothing.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which says for
        how many series the significant lags are shown when there are more
        than `MAX_STATS_SERIES`.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `profile` is None.
    """

    if profile is None:
        return ""

    parts = [profile.explanation]

    # The temporal structure the profiler found. It is what the plan's
    # lags and features are derived from, so a question about the profile
    # alone (before any plan exists) can still be answered.
    for pacf in _limited(profile.series_pacf, MAX_STATS_SERIES):
        if not pacf.lags:
            continue
        lags = ", ".join(str(lag) for lag in pacf.lags[:MAX_PACF_LAGS])
        suffix = "" if len(pacf.lags) <= MAX_PACF_LAGS else f" (first {MAX_PACF_LAGS} of {len(pacf.lags)})"
        label = "Significant lags" if len(profile.series_pacf) == 1 else f"Significant lags for {pacf.series_id}"
        parts.append(f"- {label} (partial autocorrelation, strongest first): {lags}{suffix}")
    if for_describe and len(profile.series_pacf) > MAX_STATS_SERIES:
        parts.append(
            f"- Significant lags shown (first {MAX_STATS_SERIES} of "
            f"{len(profile.series_pacf)} series; a series without "
            f"significant lags has no line)"
        )
    if profile.window_features:
        rendered = ", ".join(
            f"{stat}(window={wf['window_size']})"
            for wf in profile.window_features
            for stat in wf["stats"]
        )
        parts.append(f"- Suggested window features: {rendered}")
    if profile.calendar_features:
        parts.append(
            f"- Suggested calendar features: {', '.join(profile.calendar_features)}"
        )

    return _tag("profile_decision", "\n".join(parts))


def render_plan_section(
    plan: ForecastPlan | None,
    for_describe: bool = False,
) -> str:
    """
    Render the `<forecast_plan>` section.

    Parameters
    ----------
    plan : ForecastPlan, None
        Plan to describe. None renders nothing.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which leaves out
        `PLAN_CODE_NOTE`, addressed to the LLM of `ask()`, and keeps the
        first `MAX_DESCRIBE_ITEMS` lags and window features.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `plan` is None.
    """

    if plan is None:
        return ""

    parts = [f"- Steps: {plan.steps}"]
    if plan.estimator:
        parts.append(f"- Estimator: {plan.estimator}")
    if plan.forecaster_kwargs:
        if "lags" in plan.forecaster_kwargs:
            lags = plan.forecaster_kwargs["lags"]
            if isinstance(lags, list):
                shown, suffix = _first_items(lags, for_describe)
                lags = f"{shown}{suffix}" if suffix else lags
            parts.append(f"- Lags: {lags}")
        if "window_features" in plan.forecaster_kwargs:
            window_features = plan.forecaster_kwargs["window_features"]
            if isinstance(window_features, list):
                shown, suffix = _first_items(window_features, for_describe)
                window_features = f"{shown}{suffix}" if suffix else window_features
            parts.append(f"- Window features: {window_features}")
        if "offset" in plan.forecaster_kwargs:
            parts.append(
                f"- Baseline offset: {plan.forecaster_kwargs['offset']} steps "
                f"(n_offsets={plan.forecaster_kwargs.get('n_offsets', 1)})"
            )
    if plan.interval is not None:
        coverage = (plan.interval[1] - plan.interval[0]) * 100
        parts.append(
            f"- Prediction interval: {plan.interval} "
            f"({coverage:.4g}% coverage)"
        )
        if plan.interval_method is not None:
            parts.append(f"- Interval method: {plan.interval_method}")
    if plan.metric:
        parts.append(f"- Primary metric: {plan.metric}")
    if plan.preprocessing_steps:
        for step in plan.preprocessing_steps:
            prefix = (
                "[in generated code]" if step.blocking else "[informational]"
            )
            parts.append(f"  - {prefix} {step.reason}")
    parts.append(f"- {plan.explanation}")
    if not for_describe:
        parts.append("")
        parts.append(PLAN_CODE_NOTE)

    return _tag("forecast_plan", "\n".join(parts))


def backtest_cv_from_code(code: str) -> Any:
    """
    Read the `TimeSeriesFold` that a backtesting script builds, without
    running the script.

    Only the literal arguments of the `cv = TimeSeriesFold(...)` call are
    read (numbers, booleans, strings, lists, None and the
    `pd.Timestamp('...')` that the renderer writes for a date), so the
    description of a script cannot drift from its code.

    Parameters
    ----------
    code : str
        Generated script.

    Returns
    -------
    cv : TimeSeriesFold, None
        The splitter the script builds, or None when the script builds none
        or its arguments are not literals.
    """

    from skforecast.model_selection import TimeSeriesFold

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    for node in tree.body:
        if not (
            isinstance(node, ast.Assign)
            and [getattr(t, "id", None) for t in node.targets] == ["cv"]
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) == "TimeSeriesFold"
            and not node.value.args
        ):
            continue
        kwargs = {}
        for keyword in node.value.keywords:
            value = keyword.value
            if (
                isinstance(value, ast.Call)
                and ast.unparse(value.func) == "pd.Timestamp"
                and len(value.args) == 1
                and not value.keywords
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                kwargs[keyword.arg] = pd.Timestamp(value.args[0].value)
                continue
            try:
                kwargs[keyword.arg] = ast.literal_eval(value)
            except (ValueError, TypeError, SyntaxError):
                return None
        try:
            return TimeSeriesFold(**kwargs)
        except Exception:
            return None

    return None


def render_script_section(
    plan: ForecastPlan | None,
    code: str | None,
    for_describe: bool = False,
    cv_config: dict | None = None,
) -> str:
    """
    Render the `<script>` section describing a generated script.

    The script itself is never sent (the user already holds it, and the
    role prompt forbids code in the answer). What the model needs to
    explain it is its contract: the mode it runs in, the files it reads,
    the variables it defines and the packages it imports, all read from
    the code string so they cannot drift from it.

    Parameters
    ----------
    plan : ForecastPlan, None
        Plan the script was rendered from. None renders nothing.
    code : str, None
        Generated script. None renders nothing.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which leaves out
        `SCRIPT_NOTE`, addressed to the LLM of `ask()`.
    cv_config : dict, default None
        Cross-validation strategy of a backtesting script (as returned by
        `resolve_cv_config`), read from the script with
        `backtest_cv_from_code`. With it, or with a script that calls a
        backtesting function, the mode is backtesting.

    Returns
    -------
    section : str
        Tagged section, or an empty string when there is no script.
    """

    if plan is None or code is None:
        return ""

    is_backtest = re.search(
        r"^metrics, predictions = backtesting_\w+\(", code, re.M
    )
    if is_backtest or cv_config is not None:
        if cv_config is None:
            mode = (
                "backtesting: predicts every fold of a cross-validation "
                "strategy and scores it against the held-out observations "
                "(its folds could not be counted from the script)"
            )
        else:
            n_folds = cv_config["n_folds"]
            n_fits = cv_config["n_fits"]
            trained = (
                "without training the model (foundation model)"
                if plan.task_type == "foundation"
                else f"training the forecaster {n_fits} time"
                     f"{'s' if n_fits != 1 else ''}"
            )
            mode = (
                f"backtesting: predicts {n_folds} fold"
                f"{'s' if n_folds != 1 else ''} of {cv_config['steps']} steps, "
                f"{trained}, and scores the predictions of every fold against "
                f"the held-out observations"
            )
        outputs = (
            "metrics (one column per metric, one row per series when there "
            "are several), and predictions of every fold with a `fold` column"
        )
    elif plan.end_train is not None:
        mode = (
            f"evaluation: trains up to {plan.end_train}, predicts the "
            f"following {plan.steps} steps and scores them against the "
            f"held-out observations"
        )
        outputs = "predictions, plus the evaluation metrics printed at the end"
    else:
        mode = (
            f"prediction: trains on all the data and forecasts the next "
            f"{plan.steps} steps"
        )
        outputs = "predictions (no metrics: there is no ground truth yet)"

    files = re.findall(r"read_csv\((['\"])(.*?)\1", code)
    packages = sorted({
        match.group(1)
        for match in re.finditer(r"^(?:import|from)\s+([A-Za-z_][\w]*)", code, re.M)
    })

    parts = [
        f"- Mode: {mode}",
        f"- Files read: {', '.join(path for _, path in files) if files else 'none'}",
        f"- Variables defined: {outputs}",
        f"- Packages imported: {', '.join(packages) if packages else 'none'}",
        f"- Length: {len(code.splitlines())} lines",
    ]
    if not for_describe:
        parts.append(SCRIPT_NOTE)

    return _tag("script", "\n".join(parts))


# `TimeSeriesFold` parameters that only describe how a model is trained. A
# foundation model is not trained (`backtesting_foundation` overrides both),
# so they are left out of its context rather than quoted back as facts.
_TRAINING_CV_PARAMS = ("refit", "fixed_train_size")


def render_cv_section(
    cv_config: dict | None,
    note: str | None = None,
    trains: bool = True,
) -> str:
    """
    Render the `<backtesting_strategy>` section (time series cross-validation).

    Parameters
    ----------
    cv_config : dict, None
        Resolved `TimeSeriesFold` parameters plus the resulting
        `n_folds`. None renders nothing.
    note : str, default None
        Line prepended to the parameter list, used by a comparison to
        state that the same strategy was applied to every candidate.
    trains : bool, default True
        Whether the forecaster is trained. When False (a foundation
        model), `refit` and `fixed_train_size` are left out: they do not
        apply to it.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `cv_config` is None.
    """

    if cv_config is None:
        return ""

    parts = [note] if note else []
    parts += [
        f"- {key}: {value}" for key, value in cv_config.items()
        if trains or key not in _TRAINING_CV_PARAMS
    ]

    return _tag("backtesting_strategy", "\n".join(parts))


def render_deterministic_summary_section(explanation: str | None) -> str:
    """
    Render the `<deterministic_summary>` section.

    The summary already states facts such as the fold count. Sending it
    keeps the LLM from re-deriving them from a truncated table.

    Parameters
    ----------
    explanation : str, None
        Deterministic human-readable summary produced alongside the run.
        None renders nothing.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `explanation` is None.
    """

    if explanation is None:
        return ""

    return _tag("deterministic_summary", explanation)


def render_metrics_section(
    metrics: Any,
    has_predictions: bool = False,
    for_describe: bool = False,
) -> str:
    """
    Render the `<evaluation_metrics>` section.

    Parameters
    ----------
    metrics : pandas DataFrame, None
        Evaluation metrics produced by the run.
    has_predictions : bool, default False
        Whether the run produced predictions. When True and `metrics` is
        None, the section states that no metrics were computed. Without
        it, the absence of the section would leave the LLM free to frame
        the plan's metric choice as a completed evaluation.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which keeps the
        rows of the first `MAX_STATS_SERIES` series plus the aggregated
        rows (`average`, `weighted_average`, `pooling`) and says how many
        series there are.

    Returns
    -------
    section : str
        Tagged section, or an empty string when there is nothing to say.
    """

    if metrics is not None:
        if for_describe:
            body = _first_series_metrics(metrics)
        else:
            body = metrics.to_string(index=False)
        return _tag("evaluation_metrics", body)

    if has_predictions:
        return _tag(
            "evaluation_metrics",
            "No evaluation metrics were computed (prediction mode, no "
            "ground truth to score against).",
        )

    return ""


def _first_series_metrics(metrics: Any) -> str:
    """
    Render the metrics of the first series plus the aggregated rows.

    Parameters
    ----------
    metrics : pandas DataFrame
        Metrics with one row per series in a `levels` (backtest) or
        `series` (forecast) column, and the aggregated rows of skforecast.

    Returns
    -------
    text : str
        The table, cut to the rows of the first `MAX_STATS_SERIES` series
        plus the aggregated rows when there are more series, with a line
        that says so. Any other table is rendered whole.
    """

    level_column = next(
        (col for col in ("levels", "series") if col in metrics.columns), None
    )
    if level_column is None:
        return metrics.to_string(index=False)

    is_aggregated = metrics[level_column].isin(_AGGREGATED_METRIC_ROWS)
    series = list(dict.fromkeys(metrics.loc[~is_aggregated, level_column]))
    if len(series) <= MAX_STATS_SERIES:
        return metrics.to_string(index=False)

    keep = is_aggregated | metrics[level_column].isin(series[:MAX_STATS_SERIES])
    aggregated = ", plus the aggregated rows" if is_aggregated.any() else ""

    return (
        f"Rows shown (first {MAX_STATS_SERIES} of {len(series)} series"
        f"{aggregated}).\n"
        f"{metrics.loc[keep].to_string(index=False)}"
    )


def render_predictions_section(predictions: Any, send_data: bool = False) -> str:
    """
    Render the `<predictions>` section.

    Parameters
    ----------
    predictions : pandas DataFrame, None
        Forecasted values. None renders nothing.
    send_data : bool, default False
        Whether row-level values may be included. When False, only
        aggregate statistics are rendered.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `predictions` is None.
    """

    if predictions is None:
        return ""

    body = (
        _serialize_dataframe(predictions)
        if send_data
        else _summarize_dataframe(predictions)
    )

    return _tag("predictions", body)


def render_comparison_overview_section(
    result: ComparisonResult,
    for_describe: bool = False,
) -> str:
    """
    Render the `<comparison_overview>` section.

    Parameters
    ----------
    result : ComparisonResult
        Completed comparison to describe.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which leaves out
        `RANKING_NOTE`, addressed to the LLM of `ask()`.

    Returns
    -------
    section : str
        Tagged section.
    """

    n_candidates = len(result.candidates) + len(result.failures)
    parts = [
        f"- Candidates evaluated: {n_candidates}",
        f"- Ranking metric: {result.ranking_metric}",
        f"- Winner: {result.best_name}",
    ]
    if result.baseline_name is not None:
        parts.append(
            f"- Baseline: {result.baseline_name} (ForecasterEquivalentDate, "
            f"repeats past values). A candidate beats this naive reference "
            f"only when it ranks above it (strictly lower "
            f"{result.ranking_metric}; the baseline wins ties). This row is "
            f"not the reference of MASE or RMSSE: those scale every row, this "
            f"one included, against the one-step naive forecast on the "
            f"training data, so the baseline row can also score below 1."
        )
    ranking = (
        f"The ranking is a deterministic ascending sort of the "
        f"{result.ranking_metric} column (lower is better)."
    )
    if not for_describe:
        ranking += f" {RANKING_NOTE}"
    parts.append(ranking)

    return _tag("comparison_overview", "\n".join(parts))


def _shared_cv_note(result: ComparisonResult) -> str:
    """
    State how the shared cross-validation strategy applies to the
    candidates of a comparison.

    skforecast refits `ForecasterStats` in every fold whatever `refit`
    says, so when one ran with a strategy that does not refit (or does so
    on another window), the strategy is not applied identically to it and
    the note says what ran for it, as the comparison explanation does.

    Parameters
    ----------
    result : ComparisonResult
        Completed comparison.

    Returns
    -------
    note : str
        Line prepended to the strategy.
    """

    shared = result.cv_config
    for candidate in result.candidates.values():
        if candidate.plan.forecaster != "ForecasterStats":
            continue
        stats = candidate.cv_config
        if all(
            stats.get(key) == shared.get(key)
            for key in ("refit", "fixed_train_size", "n_fits")
        ):
            break
        window = "fixed" if stats["fixed_train_size"] else "expanding"
        return (
            f"Applied to every candidate, except ForecasterStats: skforecast "
            f"refits it in every fold, on a {window} window "
            f"({stats['n_fits']} trainings)."
        )

    return "Applied identically to every candidate."


def render_leaderboard_section(
    results: Any,
    max_rows: int = MAX_LEADERBOARD_ROWS,
    for_describe: bool = False,
) -> str:
    """
    Render the `<leaderboard>` section of a comparison.

    Deliberately not routed through `_serialize_dataframe`. That helper
    keeps a head and a tail and appends a per-column min/max/mean, which
    is meaningless on a leaderboard: the table is already sorted by the
    ranking metric, so summarising the `rank` column reports the shape of
    a counter rather than of the results. The rows are kept from the top
    instead, and the omitted count is stated.

    Parameters
    ----------
    results : pandas DataFrame
        Ranked comparison table, sorted best first.
    max_rows : int, default `MAX_LEADERBOARD_ROWS`
        Top rows kept in full.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which leaves out
        `LEADERBOARD_NOTE`, addressed to the LLM of `ask()`.

    Returns
    -------
    section : str
        Tagged section.
    """

    n_rows = len(results)
    if n_rows <= max_rows:
        body = f"Candidates listed: {n_rows} (all shown below).\n{results.to_string()}"
    else:
        omitted = n_rows - max_rows
        note = "" if for_describe else f" {LEADERBOARD_NOTE}"
        body = (
            f"Candidates listed: {n_rows}. Rows shown (first {max_rows} of "
            f"{n_rows}): the {omitted} lower-ranked "
            f"{'rows are' if omitted != 1 else 'row is'} omitted.{note}\n\n"
            f"{results.head(max_rows).to_string()}"
        )

    return _tag("leaderboard", body)


def render_failures_section(
    failures: dict | None,
    for_describe: bool = False,
) -> str:
    """
    Render the `<failed_candidates>` section of a comparison.

    One line per failure. Full tracebacks are omitted: they are verbose
    and can expose local filesystem paths.

    Parameters
    ----------
    failures : dict, None
        Mapping of candidate name to `CandidateFailure`. Empty or None
        renders nothing.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, which keeps the
        first `MAX_DESCRIBE_ITEMS` failures and says how many there are.

    Returns
    -------
    section : str
        Tagged section, or an empty string when there are no failures.
    """

    if not failures:
        return ""

    shown, suffix = _first_items(list(failures.items()), for_describe)
    parts = [f"- {name}: {failure.summary()}" for name, failure in shown]
    if suffix:
        parts.append(f"- Failures shown{suffix}")

    return _tag("failed_candidates", "\n".join(parts))


def render_winning_candidate_section(
    best_name: str,
    plan: ForecastPlan | None,
    for_describe: bool = False,
) -> str:
    """
    Render the `<winning_candidate>` section of a comparison.

    The winner's plan is nested inside this tag so the LLM cannot mistake
    it for the configuration shared by every candidate.

    Parameters
    ----------
    best_name : str
        Name of the top-ranked candidate.
    plan : ForecastPlan, None
        The winner's plan.
    for_describe : bool, default False
        Whether the section is rendered for `describe()`, passed on to
        `render_plan_section`.

    Returns
    -------
    section : str
        Tagged section.
    """

    parts = [
        f"Name: {best_name}",
        (
            "Only the winning configuration is detailed below. The other "
            "candidates are represented by their leaderboard rows."
        ),
        render_plan_section(plan, for_describe=for_describe),
    ]

    return _tag("winning_candidate", "\n".join(p for p in parts if p))


def build_context_message(
    profile: ForecastingProfile | None = None,
    plan: ForecastPlan | None = None,
    predictions: Any = None,
    metrics: Any = None,
    cv_config: dict | None = None,
    explanation: str | None = None,
    send_data: bool = False,
    for_describe: bool = False,
) -> str:
    """
    Serialize a single forecasting run into a context block for the LLM.

    Convenience composition of the section renderers in this module,
    covering everything a single run produces. A result type that needs a
    different set of sections should call the renderers it wants and pass
    them to `join_sections` rather than extend this signature.

    The block is delimited with XML-style tags rather than markdown
    headings. The loaded skills, this context, and the answer the LLM is
    asked to produce would otherwise all use `##`, leaving the model to
    guess which content is authoritative.

    Parameters
    ----------
    profile : ForecastingProfile, default None
        High-level profile of the forecasting problem.
    plan : ForecastPlan, default None
        Detailed forecasting plan.
    predictions : pandas DataFrame, default None
        Forecasted values from a completed forecast run. When prediction
        intervals are requested, the interval columns are included here.
    metrics : pandas DataFrame, default None
        Evaluation metrics from a completed forecast run.
    cv_config : dict, default None
        Cross-validation configuration from a backtest run. When
        provided, a `<backtesting_strategy>` section is rendered.
    explanation : str, default None
        Deterministic human-readable summary produced alongside the run.
        When provided, a `<deterministic_summary>` section is rendered.
        Passing it keeps the LLM from re-deriving facts (such as the fold
        count) that were already computed correctly.
    send_data : bool, default False
        Whether raw data values may be included. When False, only
        aggregate statistics are shown for predictions. Metrics
        (already aggregated) are always included.
    for_describe : bool, default False
        Whether the block is rendered for `describe()`, which leaves out
        the sentences addressed to the LLM of `ask()`.

    Returns
    -------
    context : str
        Tagged context block. Empty string if all arguments are None.
    """

    return join_sections([
        render_dataset_section(profile, for_describe=for_describe),
        render_profile_decision_section(profile, for_describe=for_describe),
        render_plan_section(plan, for_describe=for_describe),
        render_cv_section(
            cv_config,
            trains=plan is None or plan.task_type != "foundation",
        ),
        render_deterministic_summary_section(explanation),
        render_metrics_section(
            metrics,
            has_predictions = predictions is not None,
            for_describe    = for_describe,
        ),
        render_predictions_section(predictions, send_data=send_data),
    ])


def build_comparison_context(
    result: ComparisonResult,
    for_describe: bool = False,
) -> str:
    """
    Serialize a forecaster comparison into a context block for the LLM.

    Emits the shared dataset profile, the ranked leaderboard, the shared
    cross-validation strategy, one line per failed candidate, and the
    winning candidate's plan, each in its own tagged section.

    The payload is deliberately compact. Each of the shared sections is
    stated once rather than repeated per candidate, and the non-winning
    candidates' plans, code, metrics, and predictions are omitted: the
    leaderboard already carries the per-candidate numbers a ranking
    question needs. The context therefore stays roughly constant as the
    number of candidates grows. Full tracebacks are omitted too, since
    they are verbose and can expose local filesystem paths.

    The leaderboard itself is capped at `MAX_LEADERBOARD_ROWS`, keeping
    the top rows, so a comparison of many candidates cannot crowd out the
    rest of the prompt.

    There is no `send_data` toggle here, unlike `build_context_message`.
    That flag gates row-level predictions, and a comparison renders none:
    the leaderboard holds aggregated metrics only.

    Parameters
    ----------
    result : ComparisonResult
        Completed comparison to describe.
    for_describe : bool, default False
        Whether the block is rendered for `describe()`, which leaves out
        the sentences addressed to the LLM of `ask()`.

    Returns
    -------
    context : str
        Plain-text context block.
    """

    return join_sections([
        # The profile is shared by construction, so it is stated once here
        # instead of being repeated inside every candidate's own block.
        render_dataset_section(result.profile, for_describe=for_describe),
        render_profile_decision_section(result.profile, for_describe=for_describe),
        render_comparison_overview_section(result, for_describe=for_describe),
        render_leaderboard_section(result.results, for_describe=for_describe),
        render_failures_section(result.failures, for_describe=for_describe),
        render_cv_section(
            result.cv_config,
            note=_shared_cv_note(result),
        ),
        render_deterministic_summary_section(result.explanation),
        render_winning_candidate_section(
            result.best_name,
            result.best_candidate.plan,
            for_describe = for_describe,
        ),
    ])

