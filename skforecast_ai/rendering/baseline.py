################################################################################
#                       Rendering for baseline forecasting                     #
#                                                                              #
# Script rendering for the ForecasterEquivalentDate baseline                   #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from ..schemas import ForecastPlan, DataProfile, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_end_train,
    _emit_imports_baseline,
    _emit_loading_and_index,
    _emit_metrics_section,
    _emit_preprocessing_steps,
    _emit_production_note,
    _emit_split_dates,
    _format_int,
    _get_interval_method_literal,
    _get_interval_repr,
    _get_target_str,
)


def _emit_forecaster_creation_baseline(
    lines: list[str],
    plan: ForecastPlan,
) -> None:
    """Append ForecasterEquivalentDate construction code."""

    offset = plan.forecaster_kwargs.get("offset", 1)
    n_offsets = plan.forecaster_kwargs.get("n_offsets", 1)
    label = "naive" if offset == 1 else "seasonal naive"

    lines.append(f"# Create forecaster (baseline, {label})")
    _emit_aligned_kwargs(
        lines,
        "forecaster = ForecasterEquivalentDate(",
        [("offset", repr(offset)), ("n_offsets", repr(n_offsets))],
    )
    lines.append("")


def render_forecast_baseline(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """
    Render forecasting code for `ForecasterEquivalentDate` (baseline).

    In evaluation mode (`plan.end_train` set) the script fits on the
    training split, predicts the test split and computes the metrics. In
    prediction mode it fits on the whole series and forecasts the future.
    No exogenous variables are loaded: the baseline only repeats past
    values of the target.

    Parameters
    ----------
    plan : ForecastPlan
        Plan with task type `'baseline'`. Its `forecaster_kwargs` hold the
        `offset` and `n_offsets` of the forecaster.
    profile : DataProfile
        Data profile of the series.

    Returns
    -------
    script : RenderedScript
        Imports, data loading and core sections of the forecasting script.
    """

    target = _get_target_str(profile)

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    evaluate = plan.end_train is not None
    _emit_imports_baseline(import_lines, plan, include_metrics=evaluate)

    # --- Load data and index setup ---
    # The baseline uses no exogenous variables, so no future exog is loaded.
    _emit_loading_and_index(loading_lines, core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Train/test split (evaluation mode) ---
    if evaluate:
        core_lines.append("# Train/test split")
        _emit_end_train(core_lines, plan)
        core_lines.append("data_train = data.loc[:end_train]")
        core_lines.append("data_test  = data.loc[data.index > end_train]")
        core_lines.append("")
        _emit_split_dates(core_lines)

    # --- Create forecaster ---
    _emit_forecaster_creation_baseline(core_lines, plan)

    train_var = "data_train" if evaluate else "data"

    # --- Fit & Predict ---
    if plan.interval_method is not None:
        interval_repr = _get_interval_repr(plan)
        core_lines.append("# Fit")
        _emit_aligned_kwargs(
            core_lines,
            "forecaster.fit(",
            [
                ("y", f"{train_var}[{repr(target)}]"),
                ("store_in_sample_residuals", "True"),
            ],
        )
        core_lines.append("")

        core_lines.append("# Predict intervals (conformal)")
        core_lines.append(f"steps = {_format_int(plan.steps, 'steps')}")
        _emit_aligned_kwargs(
            core_lines,
            "predictions = forecaster.predict_interval(",
            [
                ("steps", "steps"),
                ("method", _get_interval_method_literal(plan.interval_method)),
                ("interval", interval_repr),
            ],
        )
    else:
        core_lines.append("# Fit")
        core_lines.append(f"forecaster.fit(y={train_var}[{repr(target)}])")
        core_lines.append("")
        core_lines.append("# Predict")
        core_lines.append(f"steps = {_format_int(plan.steps, 'steps')}")
        core_lines.append("predictions = forecaster.predict(steps=steps)")
    core_lines.append("print(predictions)")
    core_lines.append("")

    # --- Metrics & production note (evaluation mode only) ---
    if evaluate:
        pred_expr = "predictions['pred']" if plan.interval_method else "predictions"
        _emit_metrics_section(
            core_lines,
            actual_expr=f"data_test[{repr(target)}].iloc[:steps]",
            pred_expr=pred_expr,
            train_expr=f"data_train[{repr(target)}]",
            metrics_to_compute=plan.metrics_to_compute,
        )
        core_lines.append("")
        _emit_production_note(core_lines, use_exog=False)
        core_lines.append("")

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )
