"""Context message building and DataFrame serialization for LLM prompts."""

from __future__ import annotations

from typing import Any, Literal

from .._utils import _display_n_observations
from ..schemas import ForecastingProfile, ForecastPlan

_MAX_ROWS_FULL = 30


def _serialize_dataframe(df: Any) -> str:
    """Serialize a DataFrame for LLM context, truncating if too large."""
    if len(df) <= _MAX_ROWS_FULL:
        return df.to_string()

    head = df.head(5).to_string()
    tail = df.tail(5).to_string(header=False)
    numeric_cols = df.select_dtypes(include="number")
    stats = ""
    if not numeric_cols.empty:
        # Report per-column statistics rather than a single blended value.
        # Collapsing point predictions and interval bounds (e.g. `pred`,
        # `lower_bound`, `upper_bound`) into one min/max/mean would let the
        # reader mistake an interval edge for a forecast value.
        lines = ["", "Per-column summary (all rows):"]
        for col in numeric_cols.columns:
            col_data = numeric_cols[col]
            lines.append(
                f"  {col}: min={col_data.min():.4g}, "
                f"max={col_data.max():.4g}, mean={col_data.mean():.4g}"
            )
        stats = "\n" + "\n".join(lines)
    return f"{head}\n... ({len(df) - 10} rows omitted) ...\n{tail}{stats}"


def _summarize_dataframe(df: Any) -> str:
    """Produce a privacy-safe summary without row-level values."""
    parts = [f"Shape: {df.shape[0]} rows x {df.shape[1]} columns"]
    parts.append(f"Columns: {list(df.columns)}")
    numeric_cols = df.select_dtypes(include="number")
    if not numeric_cols.empty:
        for col in numeric_cols.columns:
            parts.append(
                f"  {col}: min={numeric_cols[col].min():.4g}, "
                f"max={numeric_cols[col].max():.4g}, "
                f"mean={numeric_cols[col].mean():.4g}, "
                f"std={numeric_cols[col].std():.4g}"
            )
    if hasattr(df.index, "min") and len(df) > 0:
        parts.append(f"Index range: {df.index.min()} to {df.index.max()}")
    return "\n".join(parts)


def build_context_message(
    profile: ForecastingProfile | None = None,
    plan: ForecastPlan | None = None,
    predictions: Any = None,
    metrics: Any = None,
    cv_config: dict | None = None,
    verbosity: Literal["compact", "standard", "full"] = "standard",
    send_data: bool = False,
) -> str:
    """
    Serialize a profile and/or plan into a context block for the LLM.

    Produces a plain-text summary suitable for inclusion in the user
    message so the LLM can explain or discuss the deterministic outputs
    without needing tool access.

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
        provided, a "Backtesting Configuration" section is rendered.
    verbosity : {'compact', 'standard', 'full'}, default 'standard'
        Controls how much detail is included:

        - `'compact'`: Only critical facts (n_obs, n_series, freq,
          target, task_type).
        - `'standard'`: Above plus exog, missing values,
          preprocessing steps, explanation.
        - `'full'`: Above plus all warnings and series-length detail.
    send_data : bool, default False
        Whether raw data values may be included. When False, only
        aggregate statistics are shown for predictions. Metrics
        (already aggregated) are always included.

    Returns
    -------
    context : str
        Plain-text context block. Empty string if all arguments are
        None.
    """
    has_content = (
        profile is not None
        or plan is not None
        or predictions is not None
        or metrics is not None
        or cv_config is not None
    )
    if not has_content:
        return ""

    parts: list[str] = []

    if profile is not None:
        dp = profile.data_profile
        parts.append("## Dataset")
        parts.append(f"- Observations: {_display_n_observations(dp)}")
        parts.append(f"- Series: {dp.n_series}")
        parts.append(f"- Frequency: {dp.frequency or 'unknown'}")
        parts.append(f"- Target: {dp.target}")

        if verbosity in ("standard", "full"):
            exog = ", ".join(dp.exog_columns) if dp.exog_columns else "none"
            parts.append(f"- Exogenous columns: {exog}")
            if dp.missing_target:
                parts.append(f"- Missing in target: {dp.missing_target}")
            if dp.missing_exog:
                parts.append(f"- Missing in exog: {dp.missing_exog}")

        if verbosity == "full" and dp.warnings:
            parts.append(f"- Warnings: {'; '.join(dp.warnings)}")

        parts.append("")
        parts.append("## Profile Decision")
        parts.append(profile.explanation)

    if plan is not None:
        parts.append("")
        parts.append("## Forecast Plan")
        parts.append(f"- Steps: {plan.steps}")
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
        if verbosity in ("standard", "full") and plan.preprocessing_steps:
            for step in plan.preprocessing_steps:
                prefix = "[required]" if step.blocking else "[recommended]"
                parts.append(f"  - {prefix} {step.reason}")
        parts.append(f"- {plan.explanation}")
        parts.append("")
        parts.append(
            "Note: A validated Python script implementing this plan is "
            "generated separately. Do not generate code yourself."
        )

    if cv_config is not None:
        parts.append("")
        parts.append("## Backtesting Configuration")
        for key, value in cv_config.items():
            parts.append(f"- {key}: {value}")

    if metrics is not None or predictions is not None:
        parts.append("")
        parts.append("## Forecast Results")

        if metrics is not None:
            parts.append("")
            parts.append("### Evaluation Metrics")
            parts.append(metrics.to_string(index=False))
        elif predictions is not None:
            # Prediction mode: predictions exist but there is no held-out
            # ground truth, so no metrics were computed. State this explicitly
            # so the explanation does not frame the metric choice as a
            # completed evaluation.
            parts.append("")
            parts.append(
                "Note: no evaluation metrics were computed (prediction mode, "
                "no ground truth to score against)."
            )

        if predictions is not None:
            parts.append("")
            parts.append("### Predictions")
            if send_data:
                parts.append(_serialize_dataframe(predictions))
            else:
                parts.append(_summarize_dataframe(predictions))

    return "\n".join(parts)
