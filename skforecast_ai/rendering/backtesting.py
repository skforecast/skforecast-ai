################################################################################
#                       Rendering for backtesting                              #
#                                                                              #
# Script rendering for backtesting workflows                                   #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

import numbers
from typing import Any
import pandas as pd
from ..recommendation.backtesting import cv_as_executed
from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ._helpers import (
    _emit_aligned_kwargs,
    _emit_feature_setup,
    _emit_imports_baseline,
    _emit_imports_foundation,
    _emit_imports_multi_series,
    _emit_imports_single_series,
    _emit_imports_statistical,
    _emit_loading_and_index,
    _emit_pivot_to_wide,
    _emit_preprocessing_steps,
    _emit_reshape_exog_long_to_dict,
    _emit_reshape_series_long_to_dict,
    _emit_series_dict,
    _format_bool,
    _format_int,
    _get_interval_method_literal,
    _get_numeric_exog,
    _get_target_str,
)
from .baseline import _emit_forecaster_creation_baseline
from .foundation import (
    _SERIES_DICT_COMMENT,
    _emit_excluded_categorical_note,
    _emit_forecaster_creation_foundation,
    _get_foundation_exog,
)
from .multi_series import _emit_forecaster_creation_multi
from .single_series import _emit_forecaster_creation_single
from .statistical import (
    _emit_exog_features_statistical,
    _emit_forecaster_creation_statistical,
)


def _format_initial_train_size(initial_train_size: Any) -> str:
    """
    Render the `initial_train_size` of a `TimeSeriesFold` as a code literal.

    An integer (numpy integers included) is written as a plain number and a
    date string with `repr()`. A pandas Timestamp is rebuilt in the script
    from the `repr()` of its string form, with a time zone kept as its UTC
    offset, for example `pd.Timestamp('2020-03-31 00:00:00')`: `str()` alone
    gives a line that does not compile, and the `repr()` of a Timestamp
    writes the name of its time zone between quotes without escaping it, so
    a name with a quote would close the string. Any other value is written
    with `repr()`.

    Parameters
    ----------
    initial_train_size : int, str, pandas Timestamp, None
        Value stored in the `TimeSeriesFold`.

    Returns
    -------
    literal : str
        Code literal for the `initial_train_size` argument.
    """

    if isinstance(initial_train_size, numbers.Integral) and not isinstance(
        initial_train_size, bool
    ):
        return str(int(initial_train_size))
    if isinstance(initial_train_size, pd.Timestamp):
        return f"pd.Timestamp({str(initial_train_size)!r})"
    return repr(initial_train_size)


def _emit_cv_configuration(
    lines: list[str],
    cv: Any,
) -> None:
    """Append TimeSeriesFold construction code."""

    # `TimeSeriesFold` validates its arguments when it is created, not when
    # an attribute is assigned later, so each value is checked again here.
    lines.append("# Time series cross-validation configuration")
    cv_kwargs: list[tuple[str, str]] = []
    cv_kwargs.append(("steps", _format_int(cv.steps, "steps")))
    cv_kwargs.append(
        ("initial_train_size", _format_initial_train_size(cv.initial_train_size))
    )
    if cv.fold_stride is not None and cv.fold_stride != cv.steps:
        cv_kwargs.append(("fold_stride", _format_int(cv.fold_stride, "fold_stride")))
    if isinstance(cv.refit, bool):
        cv_kwargs.append(("refit", repr(cv.refit)))
    else:
        cv_kwargs.append(("refit", _format_int(cv.refit, "refit")))
    if cv.refit:
        cv_kwargs.append(
            ("fixed_train_size", _format_bool(cv.fixed_train_size, "fixed_train_size"))
        )
    if cv.gap != 0:
        cv_kwargs.append(("gap", _format_int(cv.gap, "gap")))
    if cv.skip_folds is not None:
        if isinstance(cv.skip_folds, list):
            skip_folds = [_format_int(fold, "skip_folds") for fold in cv.skip_folds]
            cv_kwargs.append(("skip_folds", f"[{', '.join(skip_folds)}]"))
        else:
            cv_kwargs.append(("skip_folds", _format_int(cv.skip_folds, "skip_folds")))
    if cv.allow_incomplete_fold is False:
        cv_kwargs.append(("allow_incomplete_fold", "False"))
    if cv.differentiation is not None:
        cv_kwargs.append(
            ("differentiation", _format_int(cv.differentiation, "differentiation"))
        )

    _emit_aligned_kwargs(lines, "cv = TimeSeriesFold(", cv_kwargs)
    lines.append("")


def _emit_backtesting_call(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """Append backtesting_forecaster call for a single series.

    Shared by the ML forecasters and the baseline. The exogenous variables
    are passed only when the plan uses them, and `interval_method` only
    when it is not skforecast's default (`'bootstrapping'`), as for the
    conformal intervals of the baseline.
    """

    target = _get_target_str(profile)
    exog_columns = profile.exog_columns

    lines.append("# Run backtesting")
    if plan.use_exog and exog_columns:
        lines.append(f"exog_features = {repr(exog_columns)}")
        lines.append("")

    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("y", f"data[{repr(target)}]"))
    if plan.use_exog and exog_columns:
        bt_kwargs.append(("exog", "data[exog_features]"))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if plan.interval is not None:
        bt_kwargs.append(("interval", repr(plan.interval)))
        if plan.interval_method not in (None, "bootstrapping"):
            bt_kwargs.append(
                ("interval_method", _get_interval_method_literal(plan.interval_method))
            )
    bt_kwargs.append(("n_jobs", "'auto'"))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines, "metrics, predictions = backtesting_forecaster(", bt_kwargs
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


def _emit_backtesting_call_multiseries(
    lines: list[str],
    plan: ForecastPlan,
    *,
    series_expr: str,
    exog_expr: str | None,
) -> None:
    """Append backtesting_forecaster_multiseries call."""

    lines.append("# Run backtesting")
    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("series", series_expr))
    if exog_expr is not None:
        bt_kwargs.append(("exog", exog_expr))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if plan.interval is not None:
        bt_kwargs.append(("interval", repr(plan.interval)))
    bt_kwargs.append(("n_jobs", "'auto'"))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines,
        "metrics, predictions = backtesting_forecaster_multiseries(",
        bt_kwargs,
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


def render_backtesting_single_series(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterRecursive or ForecasterDirect."""

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_single_series(
        import_lines,
        plan,
        profile,
        include_backtesting=True,
    )

    # --- Load data and index setup ---
    _emit_loading_and_index(loading_lines, core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Window features, calendar features and exog transformer ---
    _emit_feature_setup(
        core_lines,
        plan,
        profile,
        use_exog=bool(plan.use_exog and profile.exog_columns),
    )

    # --- Create forecaster ---
    _emit_forecaster_creation_single(core_lines, plan, profile)

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call(core_lines, plan, profile)

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


def render_backtesting_multi_series(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterRecursiveMultiSeries."""

    is_wide = profile.data_format == "wide"
    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_multi_series(
        import_lines,
        plan,
        profile,
        include_backtesting=True,
    )

    # --- Load data and index setup ---
    _emit_loading_and_index(
        loading_lines, core_lines, profile, long_format=not is_wide
    )

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Reshape to series expression ---
    if is_wide:
        if isinstance(profile.target, list):
            series_expr = f"data[{repr(profile.target)}]"
        else:
            series_expr = f"data[[{repr(profile.target)}]]"
    else:
        _emit_reshape_series_long_to_dict(
            core_lines,
            profile,
            comment=(
                "# Reshape to dict format"
                " (required for backtesting multi-series)"
            ),
        )
        core_lines.append("")
        series_expr = "series_dict"

    # --- Exog setup ---
    exog_expr: str | None = None
    if use_exog:
        if is_wide:
            core_lines.append(f"exog_features = {repr(exog_columns)}")
            core_lines.append("")
            exog_expr = "data[exog_features]"
        else:
            _emit_reshape_exog_long_to_dict(
                core_lines, profile, var="exog_dict", data_expr="data"
            )
            core_lines.append("")
            exog_expr = "exog_dict"

    # --- Window features, calendar features and exog transformer ---
    _emit_feature_setup(core_lines, plan, profile, use_exog=use_exog)

    # --- Create forecaster ---
    _emit_forecaster_creation_multi(
        core_lines,
        plan,
        profile,
        forecaster_class="ForecasterRecursiveMultiSeries",
        use_exog=use_exog,
    )

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call_multiseries(
        core_lines, plan, series_expr=series_expr, exog_expr=exog_expr
    )

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


def render_backtesting_multivariate(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterDirectMultiVariate."""

    is_wide = profile.data_format == "wide"
    exog_columns = profile.exog_columns
    use_exog = plan.use_exog and bool(exog_columns)

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_multi_series(
        import_lines,
        plan,
        profile,
        include_backtesting=True,
    )

    # --- Load data and index setup ---
    _emit_loading_and_index(
        loading_lines, core_lines, profile, long_format=not is_wide
    )

    # --- Preprocessing / pivot ---
    _emit_preprocessing_steps(core_lines, plan, profile)
    if not is_wide:
        _emit_pivot_to_wide(core_lines, profile)

    # --- Series expression ---
    if is_wide:
        if isinstance(profile.target, list):
            series_expr = f"data[{repr(profile.target)}]"
        else:
            series_expr = f"data[[{repr(profile.target)}]]"
    else:
        series_expr = "series"

    # --- Exog setup ---
    exog_expr: str | None = None
    if use_exog:
        core_lines.append(f"exog_features = {repr(exog_columns)}")
        core_lines.append("")
        exog_expr = "data[exog_features]"

    # --- Window features, calendar features and exog transformer ---
    _emit_feature_setup(core_lines, plan, profile, use_exog=use_exog)

    # --- Create forecaster ---
    _emit_forecaster_creation_multi(
        core_lines,
        plan,
        profile,
        forecaster_class="ForecasterDirectMultiVariate",
        use_exog=use_exog,
    )

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call_multiseries(
        core_lines, plan, series_expr=series_expr, exog_expr=exog_expr
    )

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )



def _get_quantiles_from_plan(plan: ForecastPlan) -> list[float] | None:
    """Derive quantiles list from plan.interval, or None if no intervals."""

    if plan.interval_method is None:
        return None
    if plan.interval is not None:
        quantiles = list(plan.interval)
        if 0.5 not in quantiles:
            quantiles = sorted([quantiles[0], 0.5, quantiles[1]])
        return quantiles
    return [0.1, 0.5, 0.9]


def _emit_backtesting_call_foundation(
    lines: list[str],
    plan: ForecastPlan,
    *,
    series_expr: str,
    exog_expr: str | None,
) -> None:
    """Append backtesting_foundation call."""

    quantiles = _get_quantiles_from_plan(plan)

    lines.append("# Run backtesting")
    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("series", series_expr))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if exog_expr is not None:
        bt_kwargs.append(("exog", exog_expr))
    if quantiles is not None:
        bt_kwargs.append(("quantiles", repr(quantiles)))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines,
        "metrics, predictions = backtesting_foundation(",
        bt_kwargs,
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


def render_backtesting_foundation(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """Render backtesting code for ForecasterFoundation."""

    exog_columns, excluded_categorical = _get_foundation_exog(plan, profile)
    use_exog = bool(exog_columns)

    is_multi_series = profile.n_series > 1
    is_long = profile.data_format == "long"

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_foundation(
        import_lines,
        plan,
        include_backtesting = True,
        profile             = profile,
        use_exog            = use_exog,
    )

    # --- Load data and index setup ---
    _emit_loading_and_index(
        loading_lines, core_lines, profile, long_format=is_long
    )

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Series expression ---
    if is_multi_series:
        _emit_series_dict(core_lines, profile, comment=_SERIES_DICT_COMMENT)
        core_lines.append("")
        series_expr = "series_dict"
    else:
        series_expr = f"data[{repr(_get_target_str(profile))}]"

    # --- Exog setup ---
    exog_expr: str | None = None
    if use_exog:
        _emit_excluded_categorical_note(core_lines, plan, excluded_categorical)
        if is_long:
            _emit_reshape_exog_long_to_dict(
                core_lines, profile, var="exog_dict", data_expr="data",
                columns=exog_columns,
            )
            exog_expr = "exog_dict"
        else:
            core_lines.append(f"exog_features = {repr(exog_columns)}")
            exog_expr = "data[exog_features]"
        core_lines.append("")

    # --- Create forecaster ---
    _emit_forecaster_creation_foundation(core_lines, plan)

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call_foundation(
        core_lines,
        plan,
        series_expr=series_expr,
        exog_expr=exog_expr,
    )

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


def _emit_backtesting_call_statistical(
    lines: list[str],
    plan: ForecastPlan,
    profile: DataProfile,
) -> None:
    """Append backtesting_stats call for ForecasterStats."""

    target = _get_target_str(profile)
    exog_columns = _get_numeric_exog(profile)

    lines.append("# Run backtesting")
    if plan.use_exog and exog_columns:
        _emit_exog_features_statistical(lines, profile)
        lines.append("")

    bt_kwargs: list[tuple[str, str]] = []
    bt_kwargs.append(("forecaster", "forecaster"))
    bt_kwargs.append(("y", f"data[{repr(target)}]"))
    if plan.use_exog and exog_columns:
        bt_kwargs.append(("exog", "data[exog_features]"))
    bt_kwargs.append(("cv", "cv"))
    bt_kwargs.append(("metric", repr(plan.metrics_to_compute)))
    if plan.interval is not None:
        bt_kwargs.append(("interval", repr(plan.interval)))
    bt_kwargs.append(("freeze_params", "True"))
    bt_kwargs.append(("n_jobs", "'auto'"))
    bt_kwargs.append(("verbose", "False"))
    bt_kwargs.append(("show_progress", "True"))
    bt_kwargs.append(("suppress_warnings", "True"))

    _emit_aligned_kwargs(
        lines, "metrics, predictions = backtesting_stats(", bt_kwargs
    )
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")


def render_backtesting_statistical(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """
    Render backtesting code for ForecasterStats (Auto-ARIMA).

    The `TimeSeriesFold` written is the one skforecast runs (see
    `cv_as_executed`): `refit=True`, and `fixed_train_size=True` when `cv`
    does not refit, so the script states what `backtesting_stats` does.

    Parameters
    ----------
    plan : ForecastPlan
        Plan with task type `'statistical'`.
    profile : DataProfile
        Data profile of the series.
    cv : TimeSeriesFold
        Cross-validation splitter. It is not modified.

    Returns
    -------
    script : RenderedScript
        Imports, data loading and core sections of the backtesting script.
    """

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_statistical(import_lines, plan, include_backtesting=True)

    # --- Load data and index setup ---
    _emit_loading_and_index(loading_lines, core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Create forecaster ---
    _emit_forecaster_creation_statistical(core_lines, plan, profile)

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv_as_executed(cv, plan.forecaster))

    # --- Backtesting call ---
    _emit_backtesting_call_statistical(core_lines, plan, profile)

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )


def render_backtesting_baseline(
    plan: ForecastPlan,
    profile: DataProfile,
    cv: Any,
) -> RenderedScript:
    """
    Render backtesting code for `ForecasterEquivalentDate` (baseline).

    Parameters
    ----------
    plan : ForecastPlan
        Plan with task type `'baseline'`. Its `forecaster_kwargs` hold the
        `offset` and `n_offsets` of the forecaster.
    profile : DataProfile
        Data profile of the series.
    cv : TimeSeriesFold
        Cross-validation splitter rendered into the script.

    Returns
    -------
    script : RenderedScript
        Imports, data loading and core sections of the backtesting script.
    """

    import_lines: list[str] = []
    loading_lines: list[str] = []
    core_lines: list[str] = []

    # --- Imports ---
    _emit_imports_baseline(import_lines, plan, include_backtesting=True)

    # --- Load data and index setup ---
    _emit_loading_and_index(loading_lines, core_lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(core_lines, plan, profile)

    # --- Create forecaster ---
    _emit_forecaster_creation_baseline(core_lines, plan)

    # --- CV configuration ---
    _emit_cv_configuration(core_lines, cv)

    # --- Backtesting call ---
    _emit_backtesting_call(core_lines, plan, profile)

    return RenderedScript(
        imports="\n".join(import_lines),
        data_loading="\n".join(loading_lines),
        core="\n".join(core_lines),
    )
