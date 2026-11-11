# Fixtures for the tests of the plan a strategy was created for in compare()

from skforecast_ai import ForecastingAssistant

from .fixtures_assistant import df_multi_wide, df_no_exog, df_single
from .fixtures_datasets import df_h2o, df_items_sales_long

assistant = ForecastingAssistant()

# --- Minimal case of `compare` on a refined plan (fixed in 0.4.2): h2o
# --- (monthly), the plan recommended by the profile and the plan refined
# --- with another estimator and other lags, which is the one the strategy
# --- is created for.
profile_h2o = assistant.profile(data=df_h2o, target="x")
plan_h2o = assistant.plan(profile=profile_h2o, steps=12)
plan_h2o_refined = assistant.refine_plan(
    profile   = profile_h2o,
    plan      = plan_h2o,
    estimator = "LGBMRegressor",
    lags      = [1, 2, 3, 12],
)
cv_h2o_refined = assistant.create_cv(profile=profile_h2o, plan=plan_h2o_refined)

# --- Light single series (100 daily observations): two forecasters and one
# --- estimator, so a comparison has two automatic rows and runs fast.
profile_sales = assistant.profile(
    data=df_no_exog, target="sales", date_column="date"
).model_copy(update={
    "forecaster_candidates": ["ForecasterRecursive", "ForecasterDirect"],
    "estimator_candidates": ["Ridge"],
})
plan_sales = assistant.plan(profile=profile_sales, steps=5)
plan_sales_direct = assistant.plan(
    profile=profile_sales, steps=5, forecaster="ForecasterDirect"
)
# Another lags for the direct forecaster: none of the automatic rows.
plan_sales_direct_lags = assistant.plan(
    profile=profile_sales, steps=5, forecaster="ForecasterDirect", lags=[1, 2, 3]
)
plan_sales_refined = assistant.refine_plan(
    profile   = profile_sales,
    plan      = plan_sales,
    estimator = "RandomForestRegressor",
    lags      = [1, 2, 3],
)
# Every decision `refine_plan()` carries over, chosen by the user.
plan_sales_all_overrides = assistant.refine_plan(
    profile            = profile_sales,
    plan               = plan_sales,
    estimator          = "Ridge",
    estimator_kwargs   = {"alpha": 2.0},
    lags               = [1, 2],
    differentiation    = 1,
    calendar_features  = ["day_of_week"],
    target_transformer = "StandardScaler",
    use_exog           = False,
)
plan_sales_window_features = assistant.refine_plan(
    profile         = profile_sales,
    plan            = plan_sales,
    window_features = [{"stats": ["mean"], "window_size": 3}],
)
# The profile as it is recommends ForecasterStats among its candidates.
plan_sales_stats = assistant.plan(
    profile=assistant.profile(data=df_no_exog, target="sales", date_column="date"),
    steps=5,
    forecaster="ForecasterStats",
)
# Edited by hand after `plan()`: a differentiation the user did not choose
# through `refine_plan()`, which `plan()` does not rebuild.
plan_sales_edited = plan_sales.model_copy(update={
    "forecaster_kwargs": {**plan_sales.forecaster_kwargs, "differentiation": 1}
})
cv_sales = assistant.create_cv(profile=profile_sales, plan=plan_sales)
cv_sales_direct = assistant.create_cv(profile=profile_sales, plan=plan_sales_direct)
cv_sales_refined = assistant.create_cv(profile=profile_sales, plan=plan_sales_refined)
cv_sales_direct_default_refit = assistant.create_cv(
    profile=profile_sales, plan=plan_sales_direct, refit=True
)
cv_sales_direct_refit = assistant.create_cv(
    profile=profile_sales, plan=plan_sales_direct_lags, refit=True
)

# --- Exogenous column `promo`: a plan that leaves it out by choice of the
# --- user (finding of the 0.5.0 agent check: the automatic candidates of
# --- `compare` used it, so the winner needed its future values).
profile_promo = assistant.profile(data=df_single, target="sales", date_column="date")
plan_promo_no_exog = assistant.plan(profile=profile_promo, steps=7, use_exog=False)
cv_promo_no_exog = assistant.create_cv(profile=profile_promo, plan=plan_promo_no_exog)

# --- One forecaster left: the automatic candidates vary the estimator
# --- ('ForecasterRecursive+Ridge' and 'ForecasterRecursive+RandomForestRegressor').
profile_sales_one_forecaster = profile_sales.model_copy(update={
    "forecaster_candidates": ["ForecasterRecursive"],
    "estimator_candidates": ["Ridge", "RandomForestRegressor"],
})
plan_sales_forest = assistant.plan(
    profile=profile_sales_one_forecaster, steps=5, estimator="RandomForestRegressor"
)
cv_sales_forest = assistant.create_cv(
    profile=profile_sales_one_forecaster, plan=plan_sales_forest
)

# --- Two series: a multivariate plan is of another family than the
# --- candidates of the profile (multi-series).
profile_multi = assistant.profile(
    data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
).model_copy(update={"estimator_candidates": ["Ridge"]})
plan_multivariate = assistant.plan(
    profile=profile_multi, steps=5, forecaster="ForecasterDirectMultiVariate"
)
cv_multivariate = assistant.create_cv(profile=profile_multi, plan=plan_multivariate)

# --- Three series of 120 days (360 observations): the estimator candidates
# --- of ForecasterRecursiveMultiSeries include XGBRegressor, which no extra
# --- of skforecast-ai installs (V01).
profile_items = assistant.profile(
    data=df_items_sales_long, target="value", series_id_column="series"
)
