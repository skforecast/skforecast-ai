# Unit test dropped_plan_decisions

from skforecast_ai._utils import dropped_plan_decisions
from skforecast_ai.schemas import ForecastPlan

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
    assert dropped_plan_decisions(PLAN, PLAN, set(), []) is None


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

    assert dropped_plan_decisions(PLAN, STATS, set(), []) == expected


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

    assert dropped_plan_decisions(PLAN, refined, set(), []) is None
