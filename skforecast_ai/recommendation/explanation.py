################################################################################
#                              Explanation builders                            #
#                                                                              #
# Human-readable explanation builders for forecasting decisions                #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################


from __future__ import annotations
from typing import TYPE_CHECKING
from ..schemas import DataProfile

if TYPE_CHECKING:
    from skforecast.foundation import FoundationModelInfo


def build_plan_explanation(
    forecaster: str,
    estimator: str | None,
    lags: list[int] | None,
    window_features: list[dict] | None,
    interval_method: str | None,
    dropna_from_series: bool | None,
    use_exog: bool,
    metric_explanation: str | None = None,
    calendar_features: dict | None = None,
    task_type: str | None = None,
    skipped_calendar_features: list[str] | None = None,
) -> str:
    """
    Compose a sentence-by-sentence summary of the plan configuration.

    Covers lags, window features, interval method, NaN handling, exogenous
    variables, and metric. Does not explain forecaster/estimator selection;
    that belongs in the profile explanation.

    Parameters
    ----------
    forecaster : str
        Selected forecaster class name.
    estimator : str, None
        Selected estimator name.
    lags : list of int, None
        Selected lag indices.
    window_features : list of dict, None
        Window feature configurations.
    interval_method : str, None
        Selected prediction interval method.
    dropna_from_series : bool, None
        NaN handling strategy. None when there is none to explain (no
        missing values, or a forecaster without the option).
    use_exog : bool
        Whether exogenous variables are included.
    metric_explanation : str, default None
        Metric explanation sentence.
    calendar_features : dict, default None
        Calendar feature configuration with keys `'features'` and
        `'encoding'`. None when no calendar features are used.
    task_type : str, default None
        Forecasting task category. Used to state why `'foundation'`,
        `'statistical'` and `'baseline'` plans carry no lag or window
        features.
    skipped_calendar_features : list of str, default None
        Calendar features left out because the columns they would create
        already exist among the exogenous variables. None or empty when
        nothing was skipped.

    Returns
    -------
    explanation : str
        Multi-sentence explanation of the plan configuration.
    """
    parts = []

    parts.append(f"Plan: {forecaster}")
    if estimator is not None:
        parts[-1] += f" + {estimator}"
    parts[-1] += "."

    if lags is not None:
        parts.append(f"Lags: {lags}.")
    elif task_type == "foundation":
        parts.append(
            "No lag or window features: the foundation model forecasts "
            "directly from the raw context window."
        )
    elif task_type == "statistical":
        parts.append(
            "No lag or window features: the statistical model estimates its "
            "own autoregressive and seasonal structure."
        )
    elif task_type == "baseline":
        parts.append(
            "No lag or window features: the baseline repeats past values "
            "and learns nothing from the data."
        )

    if window_features is not None:
        descriptions: list[str] = []
        if isinstance(window_features, list):
            for wf in window_features:
                ws = wf.get("window_size")
                for stat in wf.get("stats", []):
                    descriptions.append(f"{stat}(window={ws})")
        if descriptions:
            parts.append(f"Window features: {descriptions}.")

    if calendar_features is not None:
        feature_names = calendar_features.get("features")
        if feature_names:
            encoding = calendar_features.get("encoding")
            encoding_str = encoding if encoding is not None else "raw ordinal"
            parts.append(
                f"Calendar features: {feature_names} ({encoding_str} encoding)."
            )

    if skipped_calendar_features:
        parts.append(
            f"Calendar features {skipped_calendar_features} skipped: the "
            f"exogenous variables already have columns with the names they "
            f"would create, and those columns are used instead."
        )

    if interval_method is not None:
        parts.append(f"Prediction intervals via {interval_method}.")

    if dropna_from_series is True:
        parts.append("NaN rows will be dropped before fitting.")
    elif dropna_from_series is False:
        parts.append("NaN rows kept (NaN-tolerant estimator).")

    if use_exog:
        parts.append("Exogenous variables included.")

    if metric_explanation is not None:
        parts.append(f"{metric_explanation}")

    return " ".join(parts)


def build_foundation_explanation(
    foundation_model: FoundationModelInfo,
    exog_columns: list[str],
    context_length: int,
    n_observations: int,
    n_series: int,
) -> str:
    """
    Explain what the chosen foundation model implies for the plan.

    A foundation model reads only the last `context_length` observations
    of each series, which the plan does not show otherwise. skforecast
    reports the license only when the weights are loaded, and ignores
    unsupported covariates with a warning at fit time. Stating all of them
    in the plan lets the user see them before running anything.

    Parameters
    ----------
    foundation_model : FoundationModelInfo
        Capabilities and requirements of the foundation model.
    exog_columns : list of str
        Exogenous columns of the data.
    context_length : int
        Maximum number of past observations the model reads per series.
    n_observations : int
        Length of the longest series.
    n_series : int
        Number of series.

    Returns
    -------
    explanation : str
        Sentences about the context the model reads, unused exogenous
        variables, licenses that restrict commercial use, gated weights and
        providers that require an account.
    """
    model_id = foundation_model.model_id
    parts: list[str] = []

    of_series = "of each series" if n_series > 1 else "of the series"
    longest = "the longest series has" if n_series > 1 else "the series has"
    if n_observations > context_length:
        parts.append(
            f"The model reads the last {context_length} observations "
            f"{of_series} as context; {longest} {n_observations}, so older "
            f"observations are not used."
        )
    else:
        parts.append(
            f"The model reads up to {context_length} observations "
            f"{of_series} as context, so the whole history is used "
            f"({longest} {n_observations})."
        )
    if exog_columns and not foundation_model.allow_exog:
        parts.append(
            f"Exogenous variables {exog_columns} are not used: "
            f"'{model_id}' does not support covariates."
        )
    if foundation_model.commercial_use_restricted:
        parts.append(
            f"The weights of '{model_id}' are released under "
            f"{foundation_model.license}, which restricts "
            f"commercial use ({foundation_model.license_url})."
        )
    if foundation_model.requires_hf_auth:
        parts.append(
            f"The weights of '{model_id}' are gated on the Hugging Face Hub: "
            f"log in with an account that has accepted the model license "
            f"before running the script."
        )
    if foundation_model.requires_provider_auth:
        parts.append(
            f"The provider of '{model_id}' requires its own account and "
            f"accepting its license, outside the Hugging Face Hub, before "
            f"running the script."
        )

    return " ".join(parts)


def _build_profile_explanation(
    task_type: str,
    forecaster: str,
    forecaster_candidates: list[str],
    estimator: str | None,
    estimator_candidates: list[str],
    data_profile: DataProfile,
) -> str:
    """
    Compose a human-readable sentence explaining why a specific forecaster and
    estimator were selected, listing the available alternatives.

    Parameters
    ----------
    task_type : str
        Selected task type.
    forecaster : str
        Selected forecaster class name.
    forecaster_candidates : list of str
        Compatible forecaster alternatives.
    estimator : str, None
        Selected estimator name.
    estimator_candidates : list of str
        Compatible estimator alternatives.
    data_profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    explanation : str
        Multi-sentence explanation of the coarse decisions.
    """
    parts: list[str] = []

    if task_type == "multi_series":
        parts.append(
            f"The dataset contains {data_profile.n_series} series, so a "
            f"multi-series forecaster ({forecaster}) is recommended."
        )
    elif task_type == "multivariate":
        parts.append(
            f"A multivariate forecaster ({forecaster}) is recommended for "
            "predicting the target using multiple correlated series as features."
        )
    elif task_type == "foundation":
        parts.append(
            f"A foundation model ({forecaster}) was selected per user "
            "preference."
        )
    elif task_type == "statistical":
        parts.append(
            f"A statistical model ({forecaster}) was selected per user "
            "preference."
        )
    else:
        parts.append(
            f"A single-series ML forecaster ({forecaster}) is recommended."
        )

    # Data context anchoring the recommendation.
    context_bits: list[str] = []
    n_obs = data_profile.n_total_observations
    if n_obs and data_profile.n_series > 1:
        context_bits.append(
            f"{n_obs} observations pooled across {data_profile.n_series} series"
        )
    elif n_obs:
        context_bits.append(f"{n_obs} observations")
    if data_profile.frequency is not None:
        context_bits.append(f"'{data_profile.frequency}' frequency")
    elif data_profile.index_type != "datetime":
        context_bits.append(f"a {data_profile.index_type} index")
    if context_bits:
        parts.append(f"Data: {', '.join(context_bits)}.")

    alt_forecasters = [c for c in forecaster_candidates if c != forecaster]
    if alt_forecasters:
        parts.append(f"Alternative forecasters: {alt_forecasters}.")

    if estimator is not None:
        parts.append(f"Estimator: {estimator}.")
        # Estimator choice is driven by dataset size for ML tasks.
        if task_type not in ("statistical", "foundation") and n_obs:
            if estimator == "Ridge":
                parts.append(
                    f"A linear model is preferred because the dataset is small "
                    f"({n_obs} observations < 250); gradient boosting is offered "
                    f"as an alternative once more data is available."
                )
            else:
                parts.append(
                    f"A gradient boosting model is preferred for a dataset of "
                    f"this size ({n_obs} observations)."
                )
        alt_estimators = [c for c in estimator_candidates if c != estimator]
        if alt_estimators:
            parts.append(f"Alternative estimators: {alt_estimators}.")

    if data_profile.exog_columns:
        n_exog = len(data_profile.exog_columns)
        n_cat = len(data_profile.categorical_exog)
        exog_note = f"{n_exog} exogenous variable" + ("s" if n_exog != 1 else "")
        if n_cat:
            exog_note += f" ({n_cat} categorical)"
        parts.append(f"{exog_note} available as predictors.")

    return " ".join(parts)
