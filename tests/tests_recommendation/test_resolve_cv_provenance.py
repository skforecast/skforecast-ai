# Unit test resolve_cv_provenance skforecast_ai.recommendation.backtesting

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.recommendation.backtesting import resolve_cv_provenance

from tests.fixtures_assistant import df_single

assistant = ForecastingAssistant()
profile = assistant.profile(data=df_single, target="sales", date_column="date")
plan = assistant.plan(profile, steps=5)
cv_result = assistant.create_cv(profile, plan, refit=False)

_INITIAL = (
    "Initial training size by default: 70% of the 100 observations (70), up "
    "to 2023-03-11."
)
_CREATED_FOR_ANOTHER = (
    "The strategy was created for another plan (ForecasterRecursive + Ridge)."
)


def _resolve(running_plan, overridden, llm_configured=False):
    """Resolve the provenance of the strategy of `cv_result`."""
    return resolve_cv_provenance(
        created_profile = profile,
        created_plan    = plan,
        cv              = cv_result.cv,
        cv_config       = cv_result.cv_config,
        plan            = running_plan,
        overridden      = overridden,
        llm_configured  = llm_configured,
    )


def test_resolve_cv_provenance_output_when_same_plan():
    """
    Test that for the plan the strategy was created for there is no
    "created for" sentence and what the user passed is said as requested.
    """
    result = _resolve(plan, ["refit"])

    assert result == ([], f"{_INITIAL} `refit` as requested.")


@pytest.mark.parametrize(
    "update",
    [{"metric": "mean_squared_error"}, {"interval": [0.1, 0.9]}],
    ids=["metric", "interval"],
)
def test_resolve_cv_provenance_output_when_plan_differs_only_in_metric_or_interval(
    update,
):
    """
    Test that a plan that only changes the metric or the interval is the
    same plan for the strategy: the default does not depend on them, so no
    "created for another plan" sentence is added.
    """
    other = plan.model_copy(update=update)

    result = _resolve(other, ["refit"])

    assert result == ([], f"{_INITIAL} `refit` as requested.")


def test_resolve_cv_provenance_output_when_plan_has_another_forecaster():
    """
    Test that a plan with another forecaster gets the "created for another
    plan (X + Y)." sentence, and that the effect of the names is decided for
    the forecaster that runs: `refit=False` has no effect on ForecasterStats.
    """
    stats_plan = assistant.plan(profile, steps=5, forecaster="ForecasterStats")

    result = _resolve(stats_plan, ["refit"])
    result_llm = _resolve(stats_plan, [], llm_configured=True)

    assert result == (
        ["refit"],
        f"{_CREATED_FOR_ANOTHER} {_INITIAL} `refit` was passed but has no "
        "effect on this forecaster.",
    )
    assert result_llm == ([], _CREATED_FOR_ANOTHER)


def test_resolve_cv_provenance_output_when_plan_has_another_number_of_steps():
    """
    Test that the steps also make a plan another one: the default
    initial_train_size depends on them. With the same forecaster and
    estimator, the text says it is another configuration of them.
    """
    other = plan.model_copy(update={"steps": 10})

    without_effect, text = _resolve(other, ["refit"])

    assert without_effect == []
    assert text.startswith(
        "The strategy was created for another plan (ForecasterRecursive + "
        "Ridge with another configuration)."
    )


def test_resolve_cv_provenance_output_when_data_have_other_observations():
    """
    Test that a strategy that runs on data of another length than the ones
    it was created on says so: its default was computed on those.
    """
    _, text = resolve_cv_provenance(
        created_profile = profile,
        created_plan    = plan,
        cv              = cv_result.cv,
        cv_config       = cv_result.cv_config,
        plan            = plan,
        overridden      = [],
        llm_configured  = False,
        n_observations  = 130,
    )
    _, text_same = resolve_cv_provenance(
        created_profile = profile,
        created_plan    = plan,
        cv              = cv_result.cv,
        cv_config       = cv_result.cv_config,
        plan            = plan,
        overridden      = [],
        llm_configured  = False,
        n_observations  = 100,
    )

    assert text.startswith(
        f"{_INITIAL} It was computed when the strategy was created, on 100 "
        f"observations; the data it runs on have 130."
    )
    assert "It was computed when" not in text_same


def test_resolve_cv_provenance_output_when_plan_is_none():
    """
    Test that for a comparison (plan None) the text says the strategy was
    "created for the plan (X + Y)." and nothing is without effect.
    """
    result = _resolve(None, ["refit"])
    result_llm = _resolve(None, [], llm_configured=True)

    assert result == (
        [],
        "The strategy was created for the plan (ForecasterRecursive + Ridge). "
        f"{_INITIAL} `refit` as requested.",
    )
    assert result_llm == (
        [], "The strategy was created for the plan (ForecasterRecursive + Ridge)."
    )
