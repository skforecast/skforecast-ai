# Unit test recommend_plan recommendation

from skforecast_ai.recommendation import recommend_plan
from skforecast_ai.schemas import ForecastPlan

from .fixtures_recommendation import (
    profile_categorical_exog,
    profile_multi_long,
    profile_no_datetime,
    profile_short,
    profile_single_daily,
    profile_single_hourly_exog,
    profile_with_missing,
)


def test_recommend_plan_output_when_single_series_defaults():
    """
    Test recommend_plan returns ForecasterRecursive with correct defaults
    for a single daily series without exogenous variables.
    """
    plan = recommend_plan(profile=profile_single_daily, steps=30)

    assert isinstance(plan, ForecastPlan)
    assert plan.task_type == "single_series"
    assert plan.forecaster == "ForecasterRecursive"
    assert plan.metric == "mean_absolute_error"
    assert plan.frequency == "D"
    assert plan.steps == 30
    assert plan.lags is not None
    assert 7 in plan.lags
    assert plan.use_exog is False
    assert plan.backtesting_strategy == "TimeSeriesFold"


def test_recommend_plan_output_when_single_series_with_exog():
    """
    Test recommend_plan detects exogenous variables and recommends
    LGBMRegressor for an hourly series with >500 observations.
    """
    plan = recommend_plan(profile=profile_single_hourly_exog, steps=24)

    assert plan.use_exog is True
    assert plan.lags is not None
    assert plan.forecaster == "ForecasterRecursive"
    assert plan.estimator == "LGBMRegressor"


def test_recommend_plan_output_when_multi_series():
    """
    Test recommend_plan selects ForecasterRecursiveMultiSeries when the
    profile contains multiple series.
    """
    plan = recommend_plan(profile=profile_multi_long, steps=10)

    assert plan.task_type == "multi_series"
    assert plan.forecaster == "ForecasterRecursiveMultiSeries"
    assert plan.interval_method == "conformal"


def test_recommend_plan_output_when_short_series():
    """
    Test recommend_plan produces a valid plan for a short series (50 obs).
    """
    plan = recommend_plan(profile=profile_short, steps=10)

    assert isinstance(plan, ForecastPlan)
    assert plan.estimator == "Ridge"
    assert plan.lags is not None
    assert max(plan.lags) <= profile_short.n_observations // 3


def test_recommend_plan_output_when_foundation_preference():
    """
    Test recommend_plan selects ForecasterFoundation when
    prefer_foundation=True, with no estimator.
    """
    plan = recommend_plan(
        profile=profile_single_daily, steps=30, prefer_foundation=True
    )

    assert plan.task_type == "foundation"
    assert plan.forecaster == "ForecasterFoundation"
    assert plan.estimator is None
    assert plan.lags is None


def test_recommend_plan_output_when_steps_larger_than_data():
    """
    Test recommend_plan adds a warning when the steps exceeds the number
    of observations.
    """
    plan = recommend_plan(profile=profile_single_daily, steps=500)

    assert any("exceeds" in w.lower() for w in plan.warnings)


def test_recommend_plan_output_when_categorical_exog_noted():
    """
    Test recommend_plan includes a data requirement about categorical
    encoding when categorical exogenous variables are present.
    """
    plan = recommend_plan(profile=profile_categorical_exog, steps=10)

    assert any("categorical" in req.lower() for req in plan.data_requirements)


def test_recommend_plan_rationale_not_empty():
    """
    Test recommend_plan always produces a non-empty rationale string.
    """
    plan = recommend_plan(profile=profile_single_daily, steps=10)

    assert isinstance(plan.rationale, str)
    assert len(plan.rationale) > 0


def test_recommend_plan_deterministic():
    """
    Test recommend_plan is deterministic: identical inputs produce identical
    outputs.
    """
    plan_1 = recommend_plan(profile=profile_single_daily, steps=30)
    plan_2 = recommend_plan(profile=profile_single_daily, steps=30)

    assert plan_1 == plan_2


def test_recommend_plan_output_when_statistical_preference():
    """
    Test recommend_plan selects ForecasterStats when prefer_statistical=True,
    with no estimator.
    """
    plan = recommend_plan(
        profile=profile_single_daily, steps=30, prefer_statistical=True
    )

    assert plan.task_type == "statistical"
    assert plan.forecaster == "ForecasterStats"
    assert plan.estimator is None
    assert plan.interval_method is None
    assert plan.lags is None


def test_recommend_plan_output_when_missing_values_detected():
    """
    Test recommend_plan includes a data requirement about imputing missing
    values when the profile reports them.
    """
    plan = recommend_plan(profile=profile_with_missing, steps=10)

    assert any("impute" in req.lower() for req in plan.data_requirements)


def test_recommend_plan_output_when_no_datetime_index():
    """
    Test recommend_plan includes a data requirement about providing a
    DatetimeIndex when the profile has a range index.
    """
    plan = recommend_plan(profile=profile_no_datetime, steps=10)

    assert any("datetimeindex" in req.lower() for req in plan.data_requirements)


def test_recommend_plan_dropna_true_when_missing_values_and_ridge():
    """
    Test recommend_plan sets dropna_from_series=True when there are missing
    values and the estimator (Ridge) does not tolerate NaN natively.
    """
    from skforecast_ai.schemas import DataProfile

    profile = DataProfile(
        n_series               = 1,
        n_observations         = 200,
        target                 = "y",
        missing_target         = {"y": 3},
        index_type             = "datetime",
        frequency              = "D",
    )
    plan = recommend_plan(profile=profile, steps=10)

    assert plan.estimator == "Ridge"
    assert plan.dropna_from_series is True


def test_recommend_plan_dropna_false_when_missing_values_and_lgbm():
    """
    Test recommend_plan sets dropna_from_series=False when there are missing
    values but the estimator (LGBMRegressor) handles NaN natively.
    """
    plan = recommend_plan(profile=profile_with_missing, steps=10)

    assert plan.estimator == "Ridge"
    # profile_with_missing has 365 obs → Ridge (<500)
    # Let's use a profile with >500 obs to get LGBMRegressor
    from skforecast_ai.schemas import DataProfile

    profile_large_missing = DataProfile(
        n_series               = 1,
        n_observations         = 600,
        target                 = "y",
        missing_target         = {"y": 5},
        index_type             = "datetime",
        frequency              = "D",
    )
    plan = recommend_plan(profile=profile_large_missing, steps=10)

    assert plan.estimator == "LGBMRegressor"
    assert plan.dropna_from_series is False


def test_recommend_plan_dropna_false_when_no_missing_values():
    """
    Test recommend_plan sets dropna_from_series=False when no missing values
    exist, regardless of estimator.
    """
    plan = recommend_plan(profile=profile_single_daily, steps=10)

    assert plan.dropna_from_series is False


def test_recommend_plan_dropna_none_when_statistical():
    """
    Test recommend_plan sets dropna_from_series=None for statistical models
    (the parameter does not apply).
    """
    plan = recommend_plan(
        profile=profile_single_daily, steps=10, prefer_statistical=True
    )

    assert plan.dropna_from_series is None
