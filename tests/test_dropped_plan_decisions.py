# Unit test dropped_plan_decisions

from skforecast_ai._utils import dropped_plan_decisions
from skforecast_ai.schemas import DataProfile, ForecastPlan

from tests.fixtures_future_exog import (
    plans_daily_by_forecaster,
    profile_daily,
    profile_daily_promo,
)

# Data without exogenous columns, and with a categorical one alone (profile_daily
# holds a numeric and a categorical one, profile_daily_promo a numeric one).
PROFILE_NO_EXOG = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 100},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
)
PROFILE_CATEGORICAL = PROFILE_NO_EXOG.model_copy(update={
    "exog_columns": ["weekday"],
    "categorical_exog": ["weekday"],
})

PLAN = ForecastPlan(
    task_type         = "single_series",
    forecaster        = "ForecasterRecursive",
    forecaster_kwargs = {
        "lags": [1, 2],
        "differentiation": 1,
        "calendar_features": {"features": ["month"], "encoding": "cyclical"},
        "transformer_y": "StandardScaler",
        "dropna_from_series": False,
    },
    estimator         = "Ridge",
    estimator_kwargs  = {"alpha": 2.0},
    steps             = 5,
    frequency         = "D",
    overridden_fields = ["estimator_kwargs", "differentiation"],
    explanation       = "Plan.",
)
STATS = ForecastPlan(
    task_type   = "statistical",
    forecaster  = "ForecasterStats",
    estimator   = "Arima",
    steps       = 5,
    frequency   = "D",
    explanation = "Plan.",
)


def test_dropped_plan_decisions_None_when_refined_plan_holds_the_values():
    """
    Test that nothing is named when the refined plan holds the same
    decisions.
    """
    assert dropped_plan_decisions(PLAN, PLAN, set(), [], PROFILE_NO_EXOG) is None


def test_dropped_plan_decisions_names_decisions_the_forecaster_does_not_take():
    """
    Test that, for a forecaster without lags, the decisions of the user and
    the decisions about the data made by the rules are named with who chose
    them, while the lags and the estimator of the rules and a value without
    effect (`dropna_from_series=False`) are not.
    """
    expected = (
        "refine_plan() left out the values of the plan that ForecasterStats "
        "does not take: differentiation=1 (chosen by the user), "
        "calendar_features=['month'] (chosen by the rules), "
        "target_transformer='StandardScaler' (chosen by the rules). "
        "refine_plan() left out the estimator_kwargs of the plan, "
        "{'alpha': 2.0} (chosen by the user), written for Ridge: Arima starts "
        "from its defaults; pass `estimator_kwargs` to set its own."
    )

    assert dropped_plan_decisions(PLAN, STATS, set(), [], PROFILE_NO_EXOG) == expected


def test_dropped_plan_decisions_skips_explicit_keys_and_edits_by_hand():
    """
    Test that a key overridden in the call and a field already named as an
    edit by hand (`forecaster_kwargs['transformer_y']`) are not named.
    """
    expected = (
        "refine_plan() left out the values of the plan that ForecasterStats "
        "does not take: differentiation=1 (chosen by the user), "
        "calendar_features=['month'] (chosen by the rules)."
    )

    dropped = dropped_plan_decisions(
        PLAN,
        STATS,
        {"estimator_kwargs"},
        ["forecaster_kwargs['transformer_y']"],
        PROFILE_NO_EXOG,
    )

    assert dropped == expected


def test_dropped_plan_decisions_rule_decisions_not_named_for_autoregressive():
    """
    Test that a decision of the rules that an autoregressive forecaster
    decides again with another value is not named: it is decided again,
    not left out.
    """
    refined = PLAN.model_copy(update={
        "forecaster": "ForecasterDirect",
        "forecaster_kwargs": {
            **PLAN.forecaster_kwargs,
            "calendar_features": None,
            "transformer_y": None,
        },
    })

    assert dropped_plan_decisions(PLAN, refined, set(), [], PROFILE_NO_EXOG) is None


# A Ridge plan whose rules set `transformer_exog` and `categorical_features`
# because it reads exogenous columns.
PLAN_EXOG = ForecastPlan(
    task_type         = "single_series",
    forecaster        = "ForecasterRecursive",
    forecaster_kwargs = {
        "lags": [1, 2],
        "transformer_exog": "StandardScaler",
        "categorical_features": "auto",
    },
    estimator         = "Ridge",
    use_exog          = True,
    steps             = 5,
    frequency         = "D",
    explanation       = "Plan.",
)
STATS_PLAN = plans_daily_by_forecaster["stats"]
_TEXT_STATS = (
    "refine_plan() left out the values of the plan that ForecasterStats does "
    "not take: "
)


def test_dropped_plan_decisions_names_lags_refined_by_the_llm():
    """
    Test that `lags` in `llm_refined_fields` that the refined plan drops are
    named as refined by the LLM, while the lags of the rules are not named.
    """
    refined_by_llm = PLAN.model_copy(update={"llm_refined_fields": ["lags"]})
    expected = (
        _TEXT_STATS
        + "lags=[1, 2] (refined by the LLM), differentiation=1 (chosen by the "
        "user), calendar_features=['month'] (chosen by the rules), "
        "target_transformer='StandardScaler' (chosen by the rules). "
        "refine_plan() left out the estimator_kwargs of the plan, "
        "{'alpha': 2.0} (chosen by the user), written for Ridge: Arima starts "
        "from its defaults; pass `estimator_kwargs` to set its own."
    )

    dropped = dropped_plan_decisions(
        refined_by_llm, STATS, set(), [], PROFILE_NO_EXOG
    )

    assert dropped == expected


def test_dropped_plan_decisions_names_window_features_refined_by_the_llm():
    """
    Test that `window_features` in `llm_refined_fields` that the refined plan
    drops are named as refined by the LLM.
    """
    plan = PLAN_EXOG.model_copy(update={
        "forecaster_kwargs": {
            "window_features": [{"stats": ["mean"], "window_size": 3}],
        },
        "llm_refined_fields": ["window_features"],
    })
    expected = (
        _TEXT_STATS + "window_features=[{'stats': ['mean'], 'window_size': 3}]"
        " (refined by the LLM)."
    )

    dropped = dropped_plan_decisions(plan, STATS, set(), [], PROFILE_NO_EXOG)

    assert dropped == expected


def test_dropped_plan_decisions_lags_in_overridden_fields_are_chosen_by_the_user():
    """
    Test that lags both overridden and refined by the LLM are named as chosen
    by the user.
    """
    plan = PLAN.model_copy(update={
        "overridden_fields": ["lags"],
        "llm_refined_fields": ["lags"],
    })

    dropped = dropped_plan_decisions(plan, STATS, set(), [], PROFILE_NO_EXOG)

    assert "lags=[1, 2] (chosen by the user)" in dropped
    assert "(refined by the LLM)" not in dropped


def test_dropped_plan_decisions_lags_refined_by_the_llm_not_named_when_kept():
    """
    Test that lags refined by the LLM are not named when the refined plan
    holds them.
    """
    plan = PLAN_EXOG.model_copy(update={"llm_refined_fields": ["lags"]})
    refined = plan.model_copy(update={"forecaster": "ForecasterDirect"})

    assert dropped_plan_decisions(plan, refined, set(), [], PROFILE_NO_EXOG) is None


def test_dropped_plan_decisions_names_exog_settings_when_forecaster_does_not_use_them():
    """
    Test that `transformer_exog` and `categorical_features` set by the rules
    are named at the end of the list for ForecasterStats when the plan read a
    numeric and a categorical exogenous column.
    """
    expected = (
        _TEXT_STATS + "transformer_exog='StandardScaler' (chosen by the rules), "
        "categorical_features='auto' (chosen by the rules)."
    )

    dropped = dropped_plan_decisions(
        PLAN_EXOG, STATS_PLAN, set(), [], profile_daily
    )

    assert dropped == expected


def test_dropped_plan_decisions_names_exog_settings_when_baseline():
    """
    Test that a baseline, which reads no exogenous variables, is named for
    both settings.
    """
    baseline = plans_daily_by_forecaster["baseline"]
    expected = (
        "refine_plan() left out the values of the plan that "
        "ForecasterEquivalentDate does not take: "
        "transformer_exog='StandardScaler' (chosen by the rules), "
        "categorical_features='auto' (chosen by the rules)."
    )

    dropped = dropped_plan_decisions(
        PLAN_EXOG, baseline, set(), [], profile_daily
    )

    assert dropped == expected


def test_dropped_plan_decisions_names_only_transformer_exog_when_numeric_exog_only():
    """
    Test that only `transformer_exog` is named when the plan read numeric
    exogenous columns and no categorical one.
    """
    expected = _TEXT_STATS + "transformer_exog='StandardScaler' (chosen by the rules)."

    dropped = dropped_plan_decisions(
        PLAN_EXOG, STATS_PLAN, set(), [], profile_daily_promo
    )

    assert dropped == expected


def test_dropped_plan_decisions_names_only_categorical_features_when_categorical_exog_only():
    """
    Test that only `categorical_features` is named when the plan read a
    categorical exogenous column and no numeric one.
    """
    expected = _TEXT_STATS + "categorical_features='auto' (chosen by the rules)."

    dropped = dropped_plan_decisions(
        PLAN_EXOG, STATS_PLAN, set(), [], PROFILE_CATEGORICAL
    )

    assert dropped == expected


def test_dropped_plan_decisions_exog_settings_for_foundation_model_without_categorical():
    """
    Test that a foundation model that only takes numeric covariates
    ('soda-inria/tabicl') drops both settings.
    """
    expected = (
        "refine_plan() left out the values of the plan that "
        "ForecasterFoundation does not take: "
        "transformer_exog='StandardScaler' (chosen by the rules), "
        "categorical_features='auto' (chosen by the rules)."
    )

    dropped = dropped_plan_decisions(
        PLAN_EXOG,
        plans_daily_by_forecaster["foundation_numeric"],
        set(),
        [],
        profile_daily,
    )

    assert dropped == expected


def test_dropped_plan_decisions_exog_settings_for_foundation_model_with_categorical():
    """
    Test that a foundation model that reads categorical covariates
    ('autogluon/chronos-2-small') does not drop `categorical_features`, only
    `transformer_exog`.
    """
    expected = (
        "refine_plan() left out the values of the plan that "
        "ForecasterFoundation does not take: "
        "transformer_exog='StandardScaler' (chosen by the rules)."
    )

    dropped = dropped_plan_decisions(
        PLAN_EXOG,
        plans_daily_by_forecaster["foundation"],
        set(),
        [],
        profile_daily,
    )

    assert dropped == expected


def test_dropped_plan_decisions_exog_settings_not_named_when_use_exog_is_explicit():
    """
    Test that the settings are not named when `use_exog` was overridden in
    the call.
    """
    dropped = dropped_plan_decisions(
        PLAN_EXOG, STATS_PLAN, {"use_exog"}, [], profile_daily
    )

    assert dropped is None


def test_dropped_plan_decisions_exog_settings_not_named_when_edited_by_hand():
    """
    Test that a setting named as an edit by hand is not named again, while
    the other one is.
    """
    expected = _TEXT_STATS + "categorical_features='auto' (chosen by the rules)."

    dropped = dropped_plan_decisions(
        PLAN_EXOG,
        STATS_PLAN,
        set(),
        ["forecaster_kwargs['transformer_exog']"],
        profile_daily,
    )

    assert dropped == expected


def test_dropped_plan_decisions_exog_settings_not_named_when_refined_is_autoregressive():
    """
    Test that the settings are not named when the refined forecaster is
    autoregressive: the rules decide them again.
    """
    refined = plans_daily_by_forecaster["direct"]

    assert dropped_plan_decisions(PLAN_EXOG, refined, set(), [], profile_daily) is None


def test_dropped_plan_decisions_exog_settings_not_named_when_plan_had_no_exog():
    """
    Test that the settings are not named when the data has no exogenous
    columns, nor when the plan did not use them.
    """
    plan_no_exog = PLAN_EXOG.model_copy(update={"use_exog": False})

    assert dropped_plan_decisions(
        PLAN_EXOG, STATS_PLAN, set(), [], PROFILE_NO_EXOG
    ) is None
    assert dropped_plan_decisions(
        plan_no_exog, STATS_PLAN, set(), [], profile_daily
    ) is None
