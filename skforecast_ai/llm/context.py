################################################################################
#                               llm: Context                                   #
#                                                                              #
# Context message building and DataFrame serialization for LLM prompts.        #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Any
from .._constants import (
    CONTEXT_HEAD_TAIL_ROWS,
    MAX_CONTEXT_DATAFRAME_ROWS,
    MAX_LEADERBOARD_ROWS,
)
from .._utils import _display_n_observations
from ..schemas import ComparisonResult, ForecastingProfile, ForecastPlan


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

    numeric_cols = df.select_dtypes(include="number")
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
        f"- Observations: {_display_n_observations(dp)}",
        f"- Series: {dp.n_series}",
        f"- Frequency: {dp.frequency or 'unknown'}",
        f"- Target: {dp.target}",
        f"- Exogenous columns: {exog}",
    ]
    if dp.missing_target:
        parts.append(f"- Missing in target: {dp.missing_target}")
    if dp.missing_exog:
        parts.append(f"- Missing in exog: {dp.missing_exog}")

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

    return _tag("profile_decision", profile.explanation)


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
            prefix = "[required]" if step.blocking else "[recommended]"
            parts.append(f"  - {prefix} {step.reason}")
    parts.append(f"- {plan.explanation}")
    parts.append("")
    parts.append(
        "Note: A validated Python script implementing this plan is "
        "generated separately. Do not generate code yourself."
    )

    return _tag("forecast_plan", "\n".join(parts))


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
            f"re-rank the candidates or recompute the table."
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

