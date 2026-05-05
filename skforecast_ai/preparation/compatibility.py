"""Derive preprocessing steps based on (DataProfile, forecaster) pair."""

from __future__ import annotations

from .._constants import MULTI_SERIES_FORECASTERS, REQUIRES_DATETIME_FREQ
from ..schemas import DataProfile, PreprocessingStep


def derive_preprocessing_steps(
    profile: DataProfile,
    forecaster: str,
) -> list[PreprocessingStep]:
    """
    Determine required preprocessing steps for a given profile and forecaster.

    Each step maps an incompatibility between the data (as described by
    the profile) and the requirements of the selected skforecast
    forecaster.

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

    # --- Common to all forecasters ---
    if not profile.index_is_monotonic and profile.index_type == "datetime":
        steps.append(PreprocessingStep(
            action="sort_index",
            reason="skforecast requires a monotonically increasing index.",
            code_snippet="data = data.sort_index()",
            blocking=True,
        ))

    if profile.has_duplicate_timestamps:
        steps.append(PreprocessingStep(
            action="drop_duplicates",
            reason="Duplicate timestamps cause errors in skforecast.",
            code_snippet=(
                "data = data[~data.index.duplicated(keep='first')]"
            ),
            blocking=True,
        ))

    # --- Datetime frequency requirement ---
    if forecaster in REQUIRES_DATETIME_FREQ:
        if profile.index_type != "datetime" and profile.date_column is not None:
            steps.append(PreprocessingStep(
                action="set_datetime_index",
                reason=(
                    "skforecast requires a DatetimeIndex. The date column "
                    "must be parsed and set as index."
                ),
                code_snippet=(
                    "data['{date_column}'] = pd.to_datetime("
                    "data['{date_column}'])\n"
                    "data = data.set_index('{date_column}').sort_index()"
                ),
                blocking=True,
            ))

        if (
            profile.index_type == "datetime"
            and not profile.frequency_is_set
            and profile.frequency is not None
        ):
            steps.append(PreprocessingStep(
                action="asfreq",
                reason=(
                    "skforecast requires the DatetimeIndex to have a "
                    "frequency set via asfreq()."
                ),
                code_snippet="data = data.asfreq('{frequency}')",
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

    # --- Multi-series specific ---
    if forecaster in MULTI_SERIES_FORECASTERS:
        if profile.data_format == "long":
            steps.append(PreprocessingStep(
                action="reshape_long_to_dict",
                reason=(
                    "ForecasterRecursiveMultiSeries does not accept long "
                    "format directly. Convert to dict of Series."
                ),
                code_snippet=(
                    "from skforecast.preprocessing import "
                    "reshape_series_long_to_dict\n"
                    "series_dict = reshape_series_long_to_dict(\n"
                    "    data=data,\n"
                    "    series_id='{series_id_column}',\n"
                    "    index='{date_column}',\n"
                    "    values='{target}',\n"
                    ")"
                ),
                blocking=True,
            ))

    # --- Target dtype ---
    if profile.target_dtype != "numeric" and forecaster not in (
        "ForecasterRecursiveClassifier",
    ):
        steps.append(PreprocessingStep(
            action="encode_target",
            reason=(
                "The target column is not numeric. Regression forecasters "
                "require a numeric target."
            ),
            code_snippet=(
                "# Convert target to numeric or use "
                "ForecasterRecursiveClassifier"
            ),
            blocking=True,
        ))

    return steps
