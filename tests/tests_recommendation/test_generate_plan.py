"""Unit tests for the recommendation pipeline (profile + plan)."""

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.analysis import create_analysis_context
from skforecast_ai.recommendation import (
    _build_profile_explanation,
    build_data_requirements,
    build_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    select_backtesting,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_interval_method,
    select_autoregressive,
    select_metric,
    select_task_type_from_forecaster,
    select_transformer_exog,
    select_transformer_series,
)
from skforecast_ai.preparation import derive_preprocessing_steps
from skforecast_ai.schemas import (
    DataProfile,
    ForecasterProfile,
    ForecastPlan,
)

from .fixtures_recommendation import (
    profile_categorical_exog,
    profile_multi_long,
    profile_no_datetime,
    profile_short,
    profile_single_daily,
    profile_single_hourly_exog,
    profile_with_missing,
)


SINGLE_SERIES_CANDIDATES = [
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterFoundation",
    "ForecasterStats",
]

ML_ESTIMATOR_CANDIDATES_SMALL = ["Ridge", "RandomForestRegressor", "LGBMRegressor"]
ML_ESTIMATOR_CANDIDATES_LARGE = [
    "LGBMRegressor", "XGBRegressor", "CatBoostRegressor", "Ridge",
]

MULTI_SERIES_CANDIDATES = [
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
]


def _build_profile(data_profile):
    """Build a ForecasterProfile from a DataProfile using rule functions."""
    fc, fc_candidates = select_forecaster_and_candidates(data_profile)

    task_type = select_task_type_from_forecaster(fc)
    context = create_analysis_context(None, data_profile, fc)

    # Inject synthetic target_series when real data is not available
    if context.target_series is None:
        rng = np.random.default_rng(123)
        n = data_profile.n_observations
        y = np.zeros(n)
        for i in range(1, n):
            y[i] = 0.6 * y[i - 1] + rng.normal(0, 1)
        context.target_series = pd.Series(y, name="target")

    est, est_candidates = select_estimator_and_candidates(
        task_type=task_type, n_observations=context.effective_n_observations
    )

    explanation = _build_profile_explanation(
        task_type=task_type,
        forecaster=fc,
        forecaster_candidates=fc_candidates,
        estimator=est,
        estimator_candidates=est_candidates,
        data_profile=data_profile,
    )

    return ForecasterProfile(
        data_profile          = data_profile,
        task_type             = task_type,
        forecaster            = fc,
        forecaster_candidates = fc_candidates,
        estimator             = est,
        estimator_candidates  = est_candidates,
        analysis_context      = context,
        explanation           = explanation,
    )


def _plan(profile, steps, forecaster=None, estimator=None):
    """Chain profile + plan generation (with optional overrides) for tests."""
    fp = _build_profile(profile)

    # Apply overrides (mirrors generate_plan logic)
    fc = fp.forecaster
    if forecaster is not None:
        if forecaster not in fp.forecaster_candidates:
            raise ValueError(
                f"Forecaster '{forecaster}' is not compatible with this profile. "
                f"Available candidates: {fp.forecaster_candidates}."
            )
        fc = forecaster

    task_type = select_task_type_from_forecaster(fc)

    est = fp.estimator
    if task_type in ("statistical", "foundation"):
        est = None
    if estimator is not None:
        if estimator not in fp.estimator_candidates:
            raise ValueError(
                f"Estimator '{estimator}' is not compatible with this profile. "
                f"Available candidates: {fp.estimator_candidates}."
            )
        est = estimator

    data_profile = fp.data_profile
    context      = fp.analysis_context

    if task_type in ("statistical", "foundation"):
        lags = None
        window_features = None
    else:
        lags, window_features = select_autoregressive(
            n_observations = context.effective_n_observations,
            frequency      = data_profile.frequency,
            target_series  = context.target_series,
        )

    metric               = select_metric(task_type)
    backtesting_strategy = select_backtesting(context.effective_n_observations, steps)
    interval_method      = select_interval_method(fc, context.effective_n_observations)
    dropna_from_series   = select_dropna_from_series(
        est, data_profile.missing_target, data_profile.missing_exog, task_type
    )
    use_exog             = check_exog_usage(data_profile.exog_columns)
    data_requirements    = build_data_requirements(data_profile)
    preprocessing_steps  = derive_preprocessing_steps(data_profile, fc)

    transformer_series = select_transformer_series(est, task_type)
    transformer_exog = select_transformer_exog(
        est, task_type, data_profile.exog_columns, data_profile.categorical_exog,
    )

    forecaster_kwargs = build_forecaster_kwargs(
        forecaster         = fc,
        task_type          = task_type,
        lags               = lags,
        steps              = steps,
        window_features    = window_features,
        dropna_from_series = dropna_from_series,
        transformer_series = transformer_series,
        transformer_exog   = transformer_exog,
    )

    warnings_list = []
    if steps > data_profile.n_observations:
        warnings_list.append(
            f"Forecast horizon ({steps}) exceeds available observations "
            f"({data_profile.n_observations})."
        )

    explanation = build_explanation(
        task_type, fc, est, lags, interval_method, data_profile
    )

    plan = ForecastPlan(
        task_type            = task_type,
        forecaster           = fc,
        estimator            = est,
        steps                = steps,
        frequency            = data_profile.frequency,
        forecaster_kwargs    = forecaster_kwargs,
        metric               = metric,
        backtesting_strategy = backtesting_strategy,
        interval_method      = interval_method,
        use_exog             = use_exog,
        preprocessing_steps  = preprocessing_steps,
        data_requirements    = data_requirements,
        warnings             = warnings_list,
        explanation          = explanation,
    )

    return fp, plan


# ---------------------------------------------------------------------------
# build_forecaster_profile
# ---------------------------------------------------------------------------
def test_build_forecaster_profile_output_when_single_series_defaults():
    """
    Test _build_profile picks ForecasterRecursive + LGBMRegressor for a
    365-observation single series and exposes the candidate lists.
    """
    fp = _build_profile(
        data_profile=profile_single_daily,
    )

    assert isinstance(fp, ForecasterProfile)
    assert fp.task_type == "single_series"
    assert fp.forecaster == "ForecasterRecursive"
    assert fp.forecaster_candidates == SINGLE_SERIES_CANDIDATES
    assert fp.estimator == "LGBMRegressor"
    assert fp.estimator_candidates == ML_ESTIMATOR_CANDIDATES_LARGE
    assert fp.data_profile is profile_single_daily
    assert fp.explanation


def test_build_forecaster_profile_output_when_multi_series():
    """
    Test build_forecaster_profile selects ForecasterRecursiveMultiSeries when
    the dataset contains multiple series.
    """
    fp = _build_profile(data_profile=profile_multi_long)

    assert fp.task_type == "multi_series"
    assert fp.forecaster == "ForecasterRecursiveMultiSeries"
    assert fp.forecaster_candidates == MULTI_SERIES_CANDIDATES


def test_build_forecaster_profile_output_when_large_series_picks_lgbm():
    """
    Test build_forecaster_profile prefers LGBMRegressor for series with
    >= 500 observations.
    """
    fp = _build_profile(
        data_profile=profile_single_hourly_exog,
    )

    assert fp.estimator == "LGBMRegressor"
    assert fp.estimator_candidates == ML_ESTIMATOR_CANDIDATES_LARGE


def test_build_forecaster_profile_output_when_foundation_selected():
    """
    Test generate_plan honors an explicit foundation forecaster override
    and clears the estimator.
    """
    _, plan = _plan(profile_single_daily, steps=30, forecaster="ForecasterFoundation")

    assert plan.task_type == "foundation"
    assert plan.forecaster == "ForecasterFoundation"
    assert plan.estimator is None


def test_build_forecaster_profile_output_when_estimator_overridden():
    """
    Test generate_plan accepts an explicit estimator from the candidate
    list as an override.
    """
    _, plan = _plan(profile_single_daily, steps=30, estimator="LGBMRegressor")

    assert plan.estimator == "LGBMRegressor"


def test_build_forecaster_profile_ValueError_when_forecaster_not_candidate():
    """
    Test generate_plan raises ValueError when the requested forecaster is
    not compatible with the profiled problem.
    """
    err_msg = re.escape(
        "Forecaster 'ForecasterRnn' is not compatible with this profile. "
        f"Available candidates: {SINGLE_SERIES_CANDIDATES}."
    )
    with pytest.raises(ValueError, match=err_msg):
        _plan(
            profile_single_daily,
            steps=10,
            forecaster="ForecasterRnn",
        )


def test_build_forecaster_profile_ValueError_when_estimator_not_candidate():
    """
    Test generate_plan raises ValueError when the requested estimator is
    not in the candidate list.
    """
    err_msg = re.escape(
        f"Estimator 'SVR' is not compatible with this profile. "
        f"Available candidates: {ML_ESTIMATOR_CANDIDATES_LARGE}."
    )
    with pytest.raises(ValueError, match=err_msg):
        _plan(
            profile_single_daily,
            steps=10,
            estimator="SVR",
        )


# ---------------------------------------------------------------------------
# generate_plan
# ---------------------------------------------------------------------------
def test_generate_plan_output_when_single_series_defaults():
    """
    Test generate_plan returns a ForecastPlan with the expected defaults
    for a single daily series.
    """
    _, plan = _plan(profile_single_daily, steps=30)

    assert isinstance(plan, ForecastPlan)
    assert plan.task_type == "single_series"
    assert plan.forecaster == "ForecasterRecursive"
    assert plan.estimator == "LGBMRegressor"
    assert plan.metric == "mean_absolute_error"
    assert plan.frequency == "D"
    assert plan.steps == 30
    assert plan.forecaster_kwargs.get("lags") is not None
    assert 7 in plan.forecaster_kwargs["lags"]
    assert plan.use_exog is False
    assert plan.backtesting_strategy == "TimeSeriesFold"


def test_generate_plan_output_when_single_series_with_exog():
    """
    Test generate_plan detects exogenous variables and recommends
    LGBMRegressor for an hourly series with >500 observations.
    """
    _, plan = _plan(profile_single_hourly_exog, steps=24)

    assert plan.use_exog is True
    assert plan.forecaster_kwargs.get("lags") is not None
    assert plan.forecaster == "ForecasterRecursive"
    assert plan.estimator == "LGBMRegressor"


def test_generate_plan_output_when_multi_series():
    """
    Test generate_plan keeps the multi-series choice and uses conformal
    intervals.
    """
    _, plan = _plan(profile_multi_long, steps=10)

    assert plan.task_type == "multi_series"
    assert plan.forecaster == "ForecasterRecursiveMultiSeries"
    assert plan.interval_method == "conformal"


def test_generate_plan_output_when_short_series():
    """
    Test generate_plan produces a valid plan for a short series.
    """
    _, plan = _plan(profile_short, steps=10)

    assert plan.estimator == "Ridge"
    assert plan.forecaster_kwargs.get("lags") is not None
    assert max(plan.forecaster_kwargs["lags"]) <= profile_short.n_observations // 3


def test_generate_plan_output_when_foundation_forecaster_selected():
    """
    Test generate_plan emits no estimator and no lags for foundation models.
    """
    _, plan = _plan(profile_single_daily, steps=30, forecaster="ForecasterFoundation")

    assert plan.task_type == "foundation"
    assert plan.forecaster == "ForecasterFoundation"
    assert plan.estimator is None
    assert plan.forecaster_kwargs == {}


def test_generate_plan_output_when_direct_forecaster_selected():
    """
    Test generate_plan builds a coherent single-series ML plan for
    ForecasterDirect.
    """
    _, plan = _plan(profile_single_daily, steps=14, forecaster="ForecasterDirect")

    assert plan.task_type == "single_series"
    assert plan.forecaster == "ForecasterDirect"
    assert plan.estimator == "LGBMRegressor"
    assert plan.forecaster_kwargs.get("lags") is not None
    assert plan.interval_method == "bootstrapping"


def test_generate_plan_output_when_steps_larger_than_data():
    """
    Test generate_plan adds a warning when steps exceeds the number of
    observations.
    """
    _, plan = _plan(profile_single_daily, steps=500)

    assert any("exceeds" in w.lower() for w in plan.warnings)


def test_generate_plan_output_when_categorical_exog_noted():
    """
    Test generate_plan includes a data requirement about categorical
    encoding when categorical exogenous variables are present.
    """
    _, plan = _plan(profile_categorical_exog, steps=10)

    assert any("categorical" in req.lower() for req in plan.data_requirements)


def test_generate_plan_explanation_not_empty():
    """
    Test generate_plan always produces a non-empty explanation string.
    """
    _, plan = _plan(profile_single_daily, steps=10)

    assert isinstance(plan.explanation, str)
    assert len(plan.explanation) > 0


def test_generate_plan_deterministic():
    """
    Test the recommendation pipeline is deterministic.
    """
    _, plan_1 = _plan(profile_single_daily, steps=30)
    _, plan_2 = _plan(profile_single_daily, steps=30)

    assert plan_1 == plan_2


def test_generate_plan_output_when_statistical_forecaster_selected():
    """
    Test generate_plan emits no estimator and no lags for ForecasterStats.
    """
    _, plan = _plan(profile_single_daily, steps=30, forecaster="ForecasterStats")

    assert plan.task_type == "statistical"
    assert plan.forecaster == "ForecasterStats"
    assert plan.estimator is None
    assert plan.interval_method is None
    assert plan.forecaster_kwargs == {}


def test_generate_plan_output_when_missing_values_detected():
    """
    Test generate_plan includes a data requirement about imputing missing
    values when the profile reports them.
    """
    _, plan = _plan(profile_with_missing, steps=10)

    assert any("impute" in req.lower() for req in plan.data_requirements)


def test_generate_plan_output_when_no_datetime_index():
    """
    Test generate_plan includes a data requirement about providing a
    DatetimeIndex when the profile has a range index.
    """
    _, plan = _plan(profile_no_datetime, steps=10)

    assert any("datetimeindex" in req.lower() for req in plan.data_requirements)


def test_generate_plan_dropna_true_when_missing_values_and_ridge():
    """
    Test generate_plan sets dropna_from_series=True when there are missing
    values and the estimator (Ridge) does not tolerate NaN natively.
    """
    profile = DataProfile(
        n_series       = 1,
        n_observations = 200,
        target         = "y",
        missing_target = {"y": 3},
        index_type     = "datetime",
        frequency      = "D",
    )
    _, plan = _plan(profile, steps=10)

    assert plan.estimator == "Ridge"
    assert plan.forecaster_kwargs.get("dropna_from_series") is True


def test_generate_plan_dropna_false_when_missing_values_and_lgbm():
    """
    Test generate_plan sets dropna_from_series=False when there are missing
    values but the estimator (LGBMRegressor) handles NaN natively.
    """
    profile_large_missing = DataProfile(
        n_series       = 1,
        n_observations = 600,
        target         = "y",
        missing_target = {"y": 5},
        index_type     = "datetime",
        frequency      = "D",
    )
    _, plan = _plan(profile_large_missing, steps=10)

    assert plan.estimator == "LGBMRegressor"
    assert plan.forecaster_kwargs.get("dropna_from_series") is False


def test_generate_plan_dropna_false_when_no_missing_values():
    """
    Test generate_plan sets dropna_from_series=False when no missing values
    exist, regardless of estimator.
    """
    _, plan = _plan(profile_single_daily, steps=10)

    assert plan.forecaster_kwargs.get("dropna_from_series") is False


def test_generate_plan_dropna_none_when_statistical():
    """
    Test generate_plan sets forecaster_kwargs to empty dict for statistical
    models (the dropna_from_series parameter does not apply).
    """
    _, plan = _plan(profile_single_daily, steps=10, forecaster="ForecasterStats")

    assert "dropna_from_series" not in plan.forecaster_kwargs
