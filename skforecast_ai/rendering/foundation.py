################################################################################
#                       Rendering for foundation                               #
#                                                                              #
# Script rendering for foundation model forecasting                            #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from .._foundation import foundation_exog_columns, resolve_foundation_model
from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_end_train,
    _emit_future_exog_index_setup,
    _emit_future_exog_loading,
    _emit_imports_foundation,
    _emit_loading_and_index,
    _emit_metrics_section_foundation,
    _emit_preprocessing_steps,
    _emit_production_note,
    _emit_reshape_exog_long_to_dict,
    _emit_series_dict,
    _emit_train_test_split_multiseries,
    _get_target_str,
)

_SERIES_DICT_COMMENT = "# Reshape to dict format (one entry per series)"


def _get_foundation_exog(
    plan: ForecastPlan,
    profile: DataProfile,
) -> tuple[list[str], list[str]]:
    """
    Split the exogenous columns into those the foundation model uses and
    the categorical ones it cannot take.

    Parameters
    ----------
    plan : ForecastPlan
        Foundation plan; `plan.estimator` is the model ID.
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    exog_columns : list of str
        Columns passed to the model. Empty when the plan uses no exogenous
        variables or the model does not accept covariates.
    excluded_categorical : list of str
        Categorical columns left out because the model only accepts
        numeric covariates. Empty when nothing is left out.
    """
    if not plan.use_exog or not profile.exog_columns:
        return [], []
    info = resolve_foundation_model(plan.estimator)
    exog_columns = foundation_exog_columns(
        info             = info,
        exog_columns     = profile.exog_columns,
        categorical_exog = profile.categorical_exog,
    )
    excluded_categorical = []
    if info.allow_exog:
        excluded_categorical = [
            col for col in profile.categorical_exog if col not in exog_columns
        ]

    return exog_columns, excluded_categorical


def _emit_excluded_categorical_note(
    lines: list[str],
    plan: ForecastPlan,
    excluded_categorical: list[str],
) -> None:
    """Document in the script the categorical exog the model cannot take."""
    if excluded_categorical:
        lines.append(
            f"# Categorical exog excluded ({', '.join(excluded_categorical)}): "
            f"'{plan.estimator}' only accepts numeric covariates"
        )


def _emit_forecaster_creation_foundation(
    lines: list[str],
    plan: ForecastPlan,
) -> None:
    """
    Append FoundationModel + ForecasterFoundation construction code.

    The model is `plan.estimator`, a Hugging Face model ID. The default
    `context_length` of its skforecast adapter is written explicitly, so
    the script shows the context the model receives; `plan.estimator_kwargs`
    override it and add any other `FoundationModel` argument.
    """

    info = resolve_foundation_model(plan.estimator)
    foundation_kwargs = {
        "model_id": plan.estimator,
        "context_length": info.default_context_length,
        **(plan.estimator_kwargs or {}),
    }
    model_id = plan.estimator

    lines.append(f"# Create foundation model ({str(model_id).split('/')[-1]})")
    model_kwargs_pairs: list[tuple[str, str]] = [
        (k, repr(v)) for k, v in foundation_kwargs.items()
    ]
    _emit_aligned_kwargs(lines, "estimator = FoundationModel(", model_kwargs_pairs)
    lines.append("")

    lines.append("# Create forecaster")
    lines.append("forecaster = ForecasterFoundation(estimator=estimator)")
    lines.append("")


def render_forecast_foundation(
    plan: ForecastPlan,
    profile: DataProfile,
) -> RenderedScript:
    """Render code for ForecasterFoundation with the model of `plan.estimator`."""

    target = _get_target_str(profile)
    exog_columns, excluded_categorical = _get_foundation_exog(plan, profile)
    use_exog = bool(exog_columns)

    # Several series (wide or long) are passed as a dict, one entry per
    # series; long data also has one exogenous frame per series.
    is_multi_series = profile.n_series > 1
    is_long = profile.data_format == "long"

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    evaluate = plan.end_train is not None

    _emit_imports_foundation(
        import_lines,
        plan,
        include_metrics = evaluate,
        profile         = profile,
        use_exog        = use_exog,
    )

    # --- Load data and index setup ---
    _emit_loading_and_index(
        loading_lines, core_lines, profile, long_format=is_long
    )
    if not evaluate and use_exog:
        _emit_future_exog_loading(loading_lines, profile)
        if not is_long:
            _emit_future_exog_index_setup(core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Series / exog extraction ---
    if is_multi_series:
        _emit_series_dict(core_lines, profile, comment=_SERIES_DICT_COMMENT)
        if use_exog:
            core_lines.append("")
    else:
        core_lines.append(f"series = data[{repr(target)}]")
    if use_exog:
        _emit_excluded_categorical_note(core_lines, plan, excluded_categorical)
        if is_long:
            _emit_reshape_exog_long_to_dict(
                core_lines, profile, var="exog_dict", data_expr="data",
                columns=exog_columns,
            )
        else:
            core_lines.append(f"exog = data[{repr(exog_columns)}]")
    core_lines.append("")

    # --- Train/test split (evaluation mode) ---
    if evaluate and is_multi_series:
        _emit_train_test_split_multiseries(
            core_lines, plan, is_wide=not is_long, use_exog=use_exog
        )
    elif evaluate:
        core_lines.append("# Train/test split")
        _emit_end_train(core_lines, plan)
        core_lines.append("series_train = series.loc[:end_train]")
        core_lines.append("series_test  = series.loc[series.index > end_train]")
        if use_exog:
            core_lines.append("exog_train = exog.loc[:end_train]")
            core_lines.append("exog_test  = exog.loc[exog.index > end_train]")
        core_lines.append("")
    elif use_exog and is_long:
        # The future exogenous variables arrive in long format as well.
        core_lines.append("# Reshape future exogenous variables to dict format")
        _emit_reshape_exog_long_to_dict(
            core_lines, profile, var="exog_future_dict", data_expr="exog_future",
            columns=exog_columns,
        )
        core_lines.append("")

    # --- Create forecaster ---
    _emit_forecaster_creation_foundation(core_lines, plan)

    # In evaluation mode the context is the training split; in prediction
    # mode the full series is used as context and the future is forecast.
    series_var = "series_dict" if is_multi_series else "series"
    exog_var = "exog_dict" if is_long else "exog"
    series_fit_var = f"{series_var}_train" if evaluate else series_var
    exog_fit_var = f"{exog_var}_train" if evaluate else exog_var
    if evaluate:
        exog_pred_var = f"{exog_var}_test"
    elif is_long:
        exog_pred_var = "exog_future_dict"
    elif excluded_categorical:
        # The future exog holds every column, the excluded ones included.
        exog_pred_var = f"exog_future[{repr(exog_columns)}]"
    else:
        exog_pred_var = "exog_future"

    # --- Fit ---
    core_lines.append("# Fit (stores context only, no training)")
    if use_exog:
        core_lines.append(
            f"forecaster.fit(series={series_fit_var}, exog={exog_fit_var})"
        )
    else:
        core_lines.append(f"forecaster.fit(series={series_fit_var})")
    core_lines.append("")

    # --- Predict ---
    # `predict_interval` returns `pred`, `lower_bound` and `upper_bound`,
    # the columns every other forecaster returns, with the median as `pred`.
    if plan.interval_method is not None:
        interval = list(plan.interval) if plan.interval is not None else [0.1, 0.9]
        core_lines.append("# Predict intervals (native quantiles)")
        core_lines.append(f"steps = {plan.steps}")
        predict_kwargs: list[tuple[str, str]] = [("steps", "steps")]
        if use_exog:
            predict_kwargs.append(("exog", exog_pred_var))
        predict_kwargs.append(("interval", repr(interval)))
        _emit_aligned_kwargs(
            core_lines, "predictions = forecaster.predict_interval(", predict_kwargs
        )
    else:
        core_lines.append("# Predict")
        core_lines.append(f"steps = {plan.steps}")
        predict_args = ["steps=steps"]
        if use_exog:
            predict_args.append(f"exog={exog_pred_var}")
        core_lines.append(f"predictions = forecaster.predict({', '.join(predict_args)})")
    core_lines.append("print(predictions)")
    core_lines.append("")

    if evaluate:
        _emit_metrics_section_foundation(
            core_lines,
            is_multi_series=is_multi_series,
            test_var=f"{series_var}_test",
            train_var=f"{series_var}_train",
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
