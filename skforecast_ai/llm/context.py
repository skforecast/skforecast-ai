################################################################################
#                               llm: Context                                   #
#                                                                              #
# Context message building and DataFrame serialization for LLM prompts.        #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import re
from typing import Any
from .._constants import (
    CONTEXT_HEAD_TAIL_ROWS,
    MAX_CONTEXT_DATAFRAME_ROWS,
    MAX_LEADERBOARD_ROWS,
)
from ..schemas import ComparisonResult, ForecastingProfile, ForecastPlan


# Per-series lines in the dataset and profile sections are capped so a
# wide multi-series dataset cannot crowd the prompt.
MAX_STATS_SERIES = 5
MAX_PACF_LAGS = 15


def _fmt(value: float) -> str:
    """Format a statistic with four significant digits."""
    return f"{value:.4g}"


def _limited(items, limit: int):
    """Yield at most `limit` items."""
    for position, item in enumerate(items):
        if position >= limit:
            return
        yield item


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
        # item_2") has no answer. Break `pred` down by level, capped like
        # the per-series target statistics of the dataset section.
        if "level" in df.columns and "pred" in numeric_cols.columns:
            levels = list(dict.fromkeys(df["level"]))
            if len(levels) > 1:
                shown = levels[:MAX_STATS_SERIES]
                suffix = (
                    "" if len(levels) <= MAX_STATS_SERIES
                    else f" (first {MAX_STATS_SERIES} of {len(levels)} levels)"
                )
                lines.append(f"Per-level summary of pred (all rows){suffix}:")
                for level in shown:
                    level_pred = df.loc[df["level"] == level, "pred"]
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
    numeric_cols = df.select_dtypes(include="number")
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


def render_dataset_section(profile: ForecastingProfile | None) -> str:
    """
    Render the `<dataset>` section describing the profiled data.

    Parameters
    ----------
    profile : ForecastingProfile, None
        Profile to describe. None renders nothing.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `profile` is None.
    """

    if profile is None:
        return ""

    dp = profile.data_profile
    exog = ", ".join(dp.exog_columns) if dp.exog_columns else "none"
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

    parts += [
        f"- Target: {dp.target}",
        f"- Exogenous columns: {exog}",
    ]
    if dp.categorical_exog:
        parts.append(
            f"- Categorical exogenous columns: {', '.join(dp.categorical_exog)}"
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

    # Missing values are stated even when there are none: "not mentioned"
    # and "none" are different answers to the user.
    if dp.missing_target:
        parts.append(f"- Missing in target: {dp.missing_target}")
    if dp.missing_exog:
        parts.append(f"- Missing in exog: {dp.missing_exog}")
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
    for warning in dp.warnings:
        parts.append(f"- Data warning: {warning}")

    return _tag("dataset", "\n".join(parts))


def render_profile_decision_section(profile: ForecastingProfile | None) -> str:
    """
    Render the `<profile_decision>` section.

    Carries the deterministic rationale for the modeling decisions the
    profiler made, so the LLM restates it rather than inventing one.

    Parameters
    ----------
    profile : ForecastingProfile, None
        Profile whose explanation is rendered. None renders nothing.

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


def render_plan_section(plan: ForecastPlan | None) -> str:
    """
    Render the `<forecast_plan>` section.

    Parameters
    ----------
    plan : ForecastPlan, None
        Plan to describe. None renders nothing.

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
            parts.append(f"- Lags: {plan.forecaster_kwargs['lags']}")
        if "window_features" in plan.forecaster_kwargs:
            parts.append(
                f"- Window features: {plan.forecaster_kwargs['window_features']}"
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
    parts.append("")
    parts.append(
        "Note: A validated Python script implementing this plan is "
        "generated separately. Do not generate code yourself."
    )

    return _tag("forecast_plan", "\n".join(parts))


def render_script_section(plan: ForecastPlan | None, code: str | None) -> str:
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

    Returns
    -------
    section : str
        Tagged section, or an empty string when there is no script.
    """

    if plan is None or code is None:
        return ""

    if plan.end_train is not None:
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
        "The script is available to the user as `result.code`; describe it "
        "from this summary and the plan, do not reproduce it.",
    ]

    return _tag("script", "\n".join(parts))


def render_cv_section(cv_config: dict | None, note: str | None = None) -> str:
    """
    Render the `<cross_validation>` section.

    Parameters
    ----------
    cv_config : dict, None
        Resolved `TimeSeriesFold` parameters plus the resulting
        `n_folds`. None renders nothing.
    note : str, default None
        Line prepended to the parameter list, used by a comparison to
        state that the same strategy was applied to every candidate.

    Returns
    -------
    section : str
        Tagged section, or an empty string when `cv_config` is None.
    """

    if cv_config is None:
        return ""

    parts = [note] if note else []
    parts += [f"- {key}: {value}" for key, value in cv_config.items()]

    return _tag("cross_validation", "\n".join(parts))


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


def render_metrics_section(metrics: Any, has_predictions: bool = False) -> str:
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

    Returns
    -------
    section : str
        Tagged section, or an empty string when there is nothing to say.
    """

    if metrics is not None:
        return _tag("evaluation_metrics", metrics.to_string(index=False))

    if has_predictions:
        return _tag(
            "evaluation_metrics",
            "No evaluation metrics were computed (prediction mode, no "
            "ground truth to score against).",
        )

    return ""


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


def render_comparison_overview_section(result: ComparisonResult) -> str:
    """
    Render the `<comparison_overview>` section.

    Parameters
    ----------
    result : ComparisonResult
        Completed comparison to describe.

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
        (
            f"The ranking is a deterministic ascending sort of the "
            f"{result.ranking_metric} column (lower is better). Do not "
            f"re-rank the candidates or recompute the table, and do not "
            f"suggest reasons for the ranking beyond the metric values: the "
            f"leaderboard reports what happened, not why."
        ),
    ]

    return _tag("comparison_overview", "\n".join(parts))


def render_leaderboard_section(
    results: Any, max_rows: int = MAX_LEADERBOARD_ROWS
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
        body = (
            f"Candidates listed: {n_rows}. Only the top {max_rows} rows are "
            f"shown; the remaining {omitted} ranked below them and were not "
            f"provided. Do not name, count, or score a candidate that does "
            f"not appear below.\n\n"
            f"{results.head(max_rows).to_string()}\n"
            f"... ({omitted} lower-ranked candidates omitted) ..."
        )

    return _tag("leaderboard", body)


def render_failures_section(failures: dict | None) -> str:
    """
    Render the `<failed_candidates>` section of a comparison.

    One line per failure. Full tracebacks are omitted: they are verbose
    and can expose local filesystem paths.

    Parameters
    ----------
    failures : dict, None
        Mapping of candidate name to `CandidateFailure`. Empty or None
        renders nothing.

    Returns
    -------
    section : str
        Tagged section, or an empty string when there are no failures.
    """

    if not failures:
        return ""

    parts = [
        f"- {name}: {failure.summary()}" for name, failure in failures.items()
    ]

    return _tag("failed_candidates", "\n".join(parts))


def render_winning_candidate_section(
    best_name: str, plan: ForecastPlan | None
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
        render_plan_section(plan),
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
        provided, a `<cross_validation>` section is rendered.
    explanation : str, default None
        Deterministic human-readable summary produced alongside the run.
        When provided, a `<deterministic_summary>` section is rendered.
        Passing it keeps the LLM from re-deriving facts (such as the fold
        count) that were already computed correctly.
    send_data : bool, default False
        Whether raw data values may be included. When False, only
        aggregate statistics are shown for predictions. Metrics
        (already aggregated) are always included.

    Returns
    -------
    context : str
        Tagged context block. Empty string if all arguments are None.
    """

    return join_sections([
        render_dataset_section(profile),
        render_profile_decision_section(profile),
        render_plan_section(plan),
        render_cv_section(cv_config),
        render_deterministic_summary_section(explanation),
        render_metrics_section(metrics, has_predictions=predictions is not None),
        render_predictions_section(predictions, send_data=send_data),
    ])


def build_comparison_context(result: ComparisonResult) -> str:
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

    Returns
    -------
    context : str
        Plain-text context block.
    """

    return join_sections([
        # The profile is shared by construction, so it is stated once here
        # instead of being repeated inside every candidate's own block.
        render_dataset_section(result.profile),
        render_profile_decision_section(result.profile),
        render_comparison_overview_section(result),
        render_leaderboard_section(result.results),
        render_failures_section(result.failures),
        render_cv_section(
            result.cv_config,
            note="Applied identically to every candidate.",
        ),
        render_deterministic_summary_section(result.explanation),
        render_winning_candidate_section(
            result.best_name, result.best_candidate.plan
        ),
    ])

