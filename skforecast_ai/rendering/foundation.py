"""Script rendering for foundation model forecasting."""

from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_data_loading,
    _emit_end_train,
    _emit_imports_foundation,
    _emit_index_setup,
    _emit_metrics_section_foundation,
    _emit_preprocessing_steps,
    _emit_production_note,
    _get_target_str,
)


def _emit_forecaster_creation_foundation(
    lines: list[str],
    plan: ForecastPlan,
) -> None:
    """Append FoundationModel + ForecasterFoundation construction code."""

    foundation_defaults = {
        "model_id": "autogluon/chronos-2-small",
        "context_length": 8192,
    }
    foundation_kwargs = {**foundation_defaults, **(plan.estimator_kwargs or {})}
    model_id = foundation_kwargs["model_id"]

    lines.append(f"# Create foundation model ({str(model_id).split('/')[-1]})")
    model_kwargs_pairs: list[tuple[str, str]] = [
        (k, repr(v)) for k, v in foundation_kwargs.items()
    ]
    _emit_aligned_kwargs(lines, "model = FoundationModel(", model_kwargs_pairs)
    lines.append("")

    lines.append("# Create forecaster")
    lines.append("forecaster = ForecasterFoundation(estimator=model)")
    lines.append("")


def render_forecast_foundation(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterFoundation (Chronos-2, TimesFM, Moirai, TabICL)."""

    target = _get_target_str(profile)
    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    # Multi-series: if profile has multiple target columns (wide format)
    is_multi_series = isinstance(profile.target, list) and len(profile.target) > 1

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_foundation(import_lines, plan, include_metrics=True)

    # --- Load data ---
    _emit_data_loading(loading_lines, profile)

    # --- Index setup (runs in both standalone and exec modes) ---
    _emit_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Series / exog extraction ---
    if is_multi_series:
        target_cols_repr = repr(profile.target)
        core_lines.append(f"series = data[{target_cols_repr}]")
    else:
        core_lines.append(f"series = data[{repr(target)}]")
    if use_exog:
        exog_cols_repr = repr(exog_columns)
        core_lines.append(f"exog = data[{exog_cols_repr}]")
    core_lines.append("")

    # --- Train/test split ---
    core_lines.append("# Train/test split")
    _emit_end_train(core_lines, profile)
    core_lines.append("series_train = series.loc[:end_train]")
    core_lines.append("series_test  = series.loc[series.index > end_train]")
    if use_exog:
        core_lines.append("exog_train = exog.loc[:end_train]")
        core_lines.append("exog_test  = exog.loc[exog.index > end_train]")
    core_lines.append("")

    # --- Create forecaster ---
    _emit_forecaster_creation_foundation(core_lines, plan)

    # --- Fit ---
    core_lines.append("# Fit (stores context only — no training)")
    if use_exog:
        core_lines.append("forecaster.fit(series=series_train, exog=exog_train)")
    else:
        core_lines.append("forecaster.fit(series=series_train)")
    core_lines.append("")

    # --- Predict ---
    if plan.interval_method is not None:
        # Derive quantiles from interval if provided
        if plan.interval is not None:
            quantiles = [round(v / 100, 2) for v in plan.interval]
            # Add median if not present
            if 0.5 not in quantiles:
                quantiles = sorted([quantiles[0], 0.5, quantiles[1]])
        else:
            quantiles = [0.1, 0.5, 0.9]
        quantiles_repr = repr(quantiles)
        core_lines.append("# Predict quantiles (native)")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = []
        predict_kwargs.append(("steps", "steps"))
        if use_exog:
            predict_kwargs.append(("exog", "exog_test"))
        if is_multi_series:
            predict_kwargs.append(("levels", repr(profile.target)))
        predict_kwargs.append(("quantiles", quantiles_repr))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_quantiles(", predict_kwargs
        )
    else:
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        predict_args = ["steps=steps"]
        if use_exog:
            predict_args.append("exog=exog_test")
        if is_multi_series:
            predict_args.append(f"levels={repr(profile.target)}")
        core_lines.append(f"predictions = forecaster.predict({', '.join(predict_args)})")
    core_lines.append("print(predictions)")
    core_lines.append("")
    _emit_metrics_section_foundation(
        core_lines,
        is_multi_series=is_multi_series,
        has_intervals=plan.interval_method is not None,
        test_var="series_test",
        train_var="series_train",
        metrics_to_compute=plan.metrics_to_compute,
    )
    core_lines.append("")
    _emit_production_note(core_lines, use_exog=use_exog, is_foundation=True)
    core_lines.append("")

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )
