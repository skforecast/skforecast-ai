################################################################################
#                       Recommendations: preprocesing                          #
#                                                                              #
# Transformer, NaN handling, exog usage, kwargs, and preprocessing step rules  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Any
from .._constants import (
    AUTOREG_FORECASTERS,
    DIRECT_FORECASTERS,
    CATEGORICAL_FORECASTERS,
    DROPNA_FORECASTERS,
    REQUIRES_DATETIME_FREQ,
    TREE_BASED_ESTIMATORS,
    NAN_TOLERANT_ESTIMATORS,
)
from ..schemas import DataProfile, PreprocessingStep


def select_transformer_series(
    estimator: str | None,
    task_type: str,
) -> str | None:
    """
    Choose the target series transformer based on estimator type.

    Linear models benefit from scaling the target series to have zero
    mean and unit variance. Tree-based models are invariant to
    monotonic transformations and do not require scaling.

    The returned value maps to `transformer_y` for single-series
    forecasters and `transformer_series` for multi-series forecasters.

    Parameters
    ----------
    estimator : str, None
        Name of the scikit-learn compatible estimator.
    task_type : str
        Forecasting task category.

    Returns
    -------
    transformer_series : str, None
        `'StandardScaler'` when scaling is recommended, `None` otherwise.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`,
    `skforecast_ai/skills/forecasting-single-series/SKILL.md`.
    """
    if task_type in ("statistical", "foundation"):
        return None
    if estimator is None:
        return None
    if estimator in TREE_BASED_ESTIMATORS:
        return None
    return "StandardScaler"


def select_transformer_exog(
    estimator: str | None,
    task_type: str,
    exog_columns: list[str],
    categorical_exog: list[str],
) -> str | None:
    """
    Choose the exogenous variable transformer based on estimator type.

    Linear models benefit from scaling numeric exogenous variables.
    Tree-based models do not require scaling. Categorical columns are
    handled separately by `categorical_features='auto'`.

    Parameters
    ----------
    estimator : str, None
        Name of the scikit-learn compatible estimator.
    task_type : str
        Forecasting task category.
    exog_columns : list of str
        Names of all exogenous columns.
    categorical_exog : list of str
        Names of categorical exogenous columns.

    Returns
    -------
    transformer_exog : str, None
        `'StandardScaler'` when scaling is recommended for numeric exog
        columns, `None` otherwise.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    When `'StandardScaler'` is returned, it means the numeric exogenous
    columns should be scaled. The code generator is responsible for
    building the appropriate `ColumnTransformer` that leaves categorical
    columns untouched.
    """
    if task_type in ("statistical", "foundation"):
        return None
    if estimator is None:
        return None
    if not exog_columns:
        return None
    # Only numeric exog columns need scaling
    numeric_exog = [c for c in exog_columns if c not in categorical_exog]
    if not numeric_exog:
        return None
    if estimator in TREE_BASED_ESTIMATORS:
        return None
    return "StandardScaler"


def select_dropna_from_series(
    estimator: str | None,
    missing_target: dict[str, int],
    missing_exog: dict[str, int],
    task_type: str,
) -> bool | None:
    """
    Determine whether to drop NaN rows from training matrices.

    Parameters
    ----------
    estimator : str, None
        Name of the scikit-learn compatible estimator.
    missing_target : dict
        Mapping of target/series name to NaN count.
    missing_exog : dict
        Mapping of exogenous column name to count of missing values.
    task_type : str
        Forecasting task category.

    Returns
    -------
    dropna_from_series : bool, None
        `None` for forecasters without the parameter. `True` when NaN
        rows must be dropped. `False` when the estimator handles NaN
        natively or no missing values exist.

    Notes
    -----
    Source: `skforecast_ai/skills/troubleshooting-common-errors/SKILL.md`,
    `skforecast_ai/resources/llms-base.txt` (NaN handling section).
    """

    if task_type in ("statistical", "foundation"):
        return None
    has_missing = bool(missing_target) or bool(missing_exog)
    if not has_missing:
        return False
    if estimator in NAN_TOLERANT_ESTIMATORS:
        return False
    return True


def check_exog_usage(exog_columns: list[str]) -> bool:
    """
    Determine whether exogenous variables should be included.

    Parameters
    ----------
    exog_columns : list of str
        Names of detected exogenous columns.

    Returns
    -------
    use_exog : bool
        `True` if at least one exogenous column is available.
    """
    return len(exog_columns) > 0


def build_forecaster_kwargs(
    forecaster: str,
    task_type: str,
    steps: int,
    lags: list[int] | None,
    window_features: list | None = None,
    calendar_features: dict | None = None,
    transformer_series: str | None = None,
    transformer_exog: str | None = None,
    dropna_from_series: bool | None = None,
) -> dict[str, Any]:
    """
    Build the keyword arguments dict for instantiating a forecaster.

    The returned dict can be unpacked directly into the forecaster
    constructor (minus `estimator`, which requires import/instantiation
    logic handled separately).

    Parameters
    ----------
    forecaster : str
        Name of the skforecast forecaster class.
    task_type : str
        Forecasting task category.
    steps : int
        Forecast horizon.
    lags : list of int, None
        Lag indices. None for statistical/foundation forecasters.
    window_features : list, default None
        Window feature objects (e.g. `RollingFeatures` instances). None
        when not applicable.
    calendar_features : dict, default None
        Calendar feature configuration with keys `'features'` (list of
        feature names) and `'encoding'` (encoding name or None). None
        when no calendar features are recommended or the forecaster does
        not support the `calendar_features` parameter.
    transformer_series : str, default None
        Name of the scaler class for the target series (e.g.
        `'StandardScaler'`). None when no scaling is needed. Stored as
        `transformer_y` for single-series or `transformer_series` for
        multi-series forecasters in the returned dict.
    transformer_exog : str, default None
        Name of the scaler class for numeric exogenous variables (e.g.
        `'StandardScaler'`). None when no scaling is needed.
    dropna_from_series : bool, default None
        NaN handling flag. None for statistical/foundation forecasters.

    Returns
    -------
    kwargs : dict
        Keyword arguments for the forecaster constructor.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md`.
    """
    if task_type in ("statistical", "foundation"):
        return {}

    kwargs: dict[str, Any] = {}

    if forecaster in AUTOREG_FORECASTERS:
        kwargs["lags"] = lags
        kwargs["window_features"] = window_features
        kwargs["calendar_features"] = calendar_features

    if forecaster in DIRECT_FORECASTERS:
        kwargs["steps"] = steps

    if forecaster == "ForecasterRecursiveMultiSeries":
        kwargs["encoding"] = "ordinal"

    if transformer_series is not None:
        if forecaster in (
            "ForecasterRecursiveMultiSeries",
            "ForecasterDirectMultiVariate",
        ):
            kwargs["transformer_series"] = transformer_series
        else:
            kwargs["transformer_y"] = transformer_series

    if transformer_exog is not None:
        kwargs["transformer_exog"] = transformer_exog

    if forecaster in CATEGORICAL_FORECASTERS:
        kwargs["categorical_features"] = "auto"

    if forecaster in DROPNA_FORECASTERS and dropna_from_series is not None:
        kwargs["dropna_from_series"] = dropna_from_series

    return kwargs


def derive_preprocessing_steps(
    profile: DataProfile,
    forecaster: str,
) -> list[PreprocessingStep]:
    """
    Determine required preprocessing steps for a given profile and forecaster.

    Each step maps an incompatibility between the data (as described by
    the profile) and the requirements of the selected skforecast
    forecaster.

    Standard data-loading operations (to_datetime, set_index, asfreq,
    sort_index/sort_values) are handled deterministically by the code
    generation templates and are NOT included here.

    Parameters
    ----------
    profile : DataProfile
        Universal data profile from Stage 1.
    forecaster : str
        Name of the skforecast forecaster class.

    Returns
    -------
    steps : list of PreprocessingStep
        Ordered preprocessing steps. Blocking steps must be applied for
        the forecaster to work; non-blocking steps are recommended.
    """
    steps: list[PreprocessingStep] = []

    # --- Duplicate timestamps ---
    if profile.has_duplicate_timestamps:
        steps.append(PreprocessingStep(
            action="drop_duplicates",
            reason="Duplicate timestamps cause errors in skforecast.",
            code_snippet=(
                "data = data[~data.index.duplicated(keep='first')]"
            ),
            blocking=True,
        ))

    # --- No datetime index and no date column (unresolvable) ---
    if forecaster in REQUIRES_DATETIME_FREQ:
        if profile.index_type != "datetime" and profile.date_column is None:
            steps.append(PreprocessingStep(
                action="provide_datetime_index",
                reason=(
                    "Provide a DatetimeIndex or date column for "
                    "time-based features."
                ),
                code_snippet=(
                    "# Set a DatetimeIndex:\n"
                    "# data.index = pd.date_range(start=..., "
                    "periods=len(data), freq=...)"
                ),
                blocking=True,
            ))

        if profile.has_gaps and profile.frequency is not None:
            steps.append(PreprocessingStep(
                action="handle_gaps",
                reason=(
                    "The series has missing timestamps. After asfreq(), "
                    "gaps become NaN rows."
                ),
                code_snippet=(
                    "# After asfreq(), missing timestamps become NaN.\n"
                    "# Handle with dropna_from_series=True or imputation."
                ),
                blocking=False,
            ))

    # --- Target dtype ---
    if profile.target_dtype != "numeric" and forecaster != "ForecasterRecursiveClassifier":
        # A categorical target is valid for the classifier forecaster, which
        # encodes labels internally, so no blocking encode step is needed.
        steps.append(PreprocessingStep(
            action="encode_target",
            reason=(
                "The target column is not numeric. Regression forecasters "
                "require a numeric target."
            ),
            code_snippet=(
                "# Convert target to numeric"
            ),
            blocking=True,
        ))

    # --- Missing values ---
    if profile.missing_target or profile.missing_exog:
        steps.append(PreprocessingStep(
            action="handle_missing_values",
            reason=(
                "Impute or handle missing values before training. Use "
                "dropna_from_series=True or a NaN-tolerant estimator."
            ),
            code_snippet=(
                "# Option 1: Use dropna_from_series=True\n"
                "# Option 2: Use a NaN-tolerant estimator (LightGBM, "
                "CatBoost, HistGradientBoosting)\n"
                "# Option 3: Impute missing values manually"
            ),
            blocking=False,
        ))

    # --- Categorical exogenous variables ---
    if profile.categorical_exog:
        steps.append(PreprocessingStep(
            action="handle_categorical_exog",
            reason=(
                f"Categorical exogenous variables detected: "
                f"{profile.categorical_exog}. These are handled "
                f"automatically by skforecast (categorical_features='auto')."
            ),
            code_snippet=(
                "# skforecast handles categorical variables automatically\n"
                "# with categorical_features='auto' (default)."
            ),
            blocking=False,
        ))

    return steps
