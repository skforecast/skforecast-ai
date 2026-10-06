# Unit test build_cv_defaults_explanation skforecast_ai.recommendation.backtesting

import pytest

from skforecast_ai.recommendation.backtesting import build_cv_defaults_explanation
from skforecast_ai.schemas import ForecastPlan


def _make_plan(task_type: str, forecaster: str, estimator: str | None) -> ForecastPlan:
    """Build a minimal ForecastPlan, without validation."""
    return ForecastPlan.model_construct(
        task_type         = task_type,
        forecaster        = forecaster,
        estimator         = estimator,
        forecaster_kwargs = {},
        steps             = 10,
        explanation       = "test plan",
    )


def _make_default(
    value, position, rule, n_observations, share, minimum, window_size, steps
) -> dict:
    """Build the dict returned by `default_initial_train_size`."""
    return {
        "value": value,
        "position": position,
        "rule": rule,
        "n_observations": n_observations,
        "share": share,
        "minimum": minimum,
        # What a recursive forecaster needs to run: more than its window.
        "needed": None if window_size is None else window_size + 1,
        "window_size": window_size,
        "steps": steps,
    }


plan_recursive = _make_plan("single_series", "ForecasterRecursive", "Ridge")
plan_stats = _make_plan("statistical", "ForecasterStats", "Arima")
plan_foundation = _make_plan(
    "foundation", "ForecasterFoundation", "amazon/chronos-bolt-tiny"
)
plan_baseline = _make_plan("baseline", "ForecasterBaseline", None)

# The share of the observations is used.
default_share = _make_default("2020-03-10", 70, "share", 100, 70, 15, 5, 10)
default_share_int = _make_default(70, 70, "share", 100, 70, 15, 5, 10)
# Raised to the minimum: the window of the forecaster plus the steps.
default_minimum_window = _make_default(
    "2020-03-15", 75, "minimum", 100, 70, 75, 65, 10
)
default_minimum_window_int = _make_default(75, 75, "minimum", 100, 70, 75, 65, 10)
# Raised to the minimum: twice the steps (no window).
default_minimum_twice = _make_default("2020-03-20", 80, "minimum", 60, 42, 80, None, 40)
# A single step.
default_minimum_one_step = _make_default("2020-01-06", 6, "minimum", 8, 5, 6, 5, 1)
# Lowered for two folds, from the share (that is still enough).
default_two_folds_share = _make_default("2020-02-29", 60, "two_folds", 100, 70, 25, 5, 20)
default_two_folds_share_int = _make_default(60, 60, "two_folds", 100, 70, 25, 5, 20)
# Lowered for two folds, from the share, and less than the minimum.
default_two_folds_share_short = _make_default(
    "2020-02-29", 60, "two_folds", 100, 70, 65, 45, 20
)
# Lowered for two folds, from the minimum (raised first).
default_two_folds_minimum_window = _make_default(
    "2020-02-29", 60, "two_folds", 100, 70, 90, 70, 20
)
default_two_folds_minimum_twice = _make_default(
    "2020-01-20", 20, "two_folds", 100, 70, 80, None, 40
)

config_six_folds = {"n_folds": 6}


def _explain(default, plan, overridden=None, without_effect=None, **kwargs):
    """Call build_cv_defaults_explanation with six folds."""
    return build_cv_defaults_explanation(
        default        = default,
        cv_config      = kwargs.pop("cv_config", config_six_folds),
        plan           = plan,
        overridden     = overridden or [],
        without_effect = without_effect or [],
        **kwargs,
    )


@pytest.mark.parametrize(
    "default, expected",
    [
        (
            default_share,
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10.",
        ),
        (
            default_share_int,
            "Initial training size by default: 70% of the 100 observations (70).",
        ),
        (
            default_minimum_window,
            "Initial training size by default: 70% of the 100 observations "
            "(70) is less than what the rule reserves for the forecaster, so "
            "it is raised to 75, its window of 65 plus the 10 steps, up to "
            "2020-03-15.",
        ),
        (
            default_minimum_window_int,
            "Initial training size by default: 70% of the 100 observations "
            "(70) is less than what the rule reserves for the forecaster, so "
            "it is raised to 75, its window of 65 plus the 10 steps.",
        ),
        (
            default_minimum_twice,
            "Initial training size by default: 70% of the 60 observations "
            "(42) is less than what the rule reserves for the forecaster, so "
            "it is raised to 80, twice the 40 steps, up to 2020-03-20.",
        ),
        (
            default_minimum_one_step,
            "Initial training size by default: 70% of the 8 observations "
            "(5) is less than what the rule reserves for the forecaster, so "
            "it is raised to 6, its window of 5 plus the 1 step, up to "
            "2020-01-06.",
        ),
        (
            default_two_folds_share,
            "Initial training size by default: 70% of the 100 observations "
            "(70) is lowered to 60 so that two folds of 20 steps remain, up "
            "to 2020-02-29.",
        ),
        (
            default_two_folds_share_int,
            "Initial training size by default: 70% of the 100 observations "
            "(70) is lowered to 60 so that two folds of 20 steps remain.",
        ),
        (
            default_two_folds_share_short,
            "Initial training size by default: 70% of the 100 observations "
            "(70) is lowered to 60 so that two folds of 20 steps remain, up "
            "to 2020-02-29.",
        ),
        (
            default_two_folds_minimum_window,
            "Initial training size by default: the 90 observations the rule "
            "reserves for the forecaster (its window of 70 plus the 20 "
            "steps) is lowered to 60 so that two folds of 20 steps remain, "
            "up to 2020-02-29. That is less than the 71 observations the "
            "forecaster needs to run.",
        ),
        (
            default_two_folds_minimum_twice,
            "Initial training size by default: the 80 observations the rule "
            "reserves for the forecaster (twice the 40 steps) is lowered to "
            "20 so that two folds of 40 steps remain, up to 2020-01-20.",
        ),
    ],
    ids=[
        "share_date",
        "share_integer",
        "minimum_window_date",
        "minimum_window_integer",
        "minimum_twice_steps",
        "minimum_one_step",
        "two_folds_from_share_date",
        "two_folds_from_share_integer",
        "two_folds_from_share_short_of_minimum",
        "two_folds_from_minimum_window",
        "two_folds_from_minimum_twice_steps",
    ],
)
def test_build_cv_defaults_explanation_output_when_initial_train_size_is_default(
    default, expected
):
    """
    Test the sentence of the default `initial_train_size` for each rule
    (share, minimum, two folds reached from the share or from the minimum),
    with a date or an integer, the window or twice the steps, the singular
    "1 step" and the tail that says the result is less than the forecaster
    needs. A ForecasterStats plan leaves out the sentence about refit.
    """
    result = _explain(default, plan_stats)

    assert result == expected


_INITIAL = (
    "Initial training size by default: 70% of the 100 observations (70), up "
    "to 2020-03-10."
)
_TRAINED_ONCE = (
    " Trained once by default: refitting in every fold would multiply the "
    "training cost by the {folds}."
)


@pytest.mark.parametrize(
    "plan, cv_config, overridden, llm_configured, expected",
    [
        (
            plan_recursive, {"n_folds": 6}, [], False,
            _INITIAL + _TRAINED_ONCE.format(folds="6 folds"),
        ),
        (
            plan_baseline, {"n_folds": 6}, [], False,
            _INITIAL + _TRAINED_ONCE.format(folds="6 folds"),
        ),
        (
            None, {"n_folds": 6}, [], False,
            _INITIAL + " The shared strategy trains once by default: "
            "refitting in every fold would multiply the training cost by the "
            "6 folds.",
        ),
        (
            None, {"n_folds": 1}, [], False,
            _INITIAL + " The shared strategy trains once by default: "
            "refitting in every fold would multiply the training cost by the "
            "1 fold.",
        ),
        (
            plan_recursive, {"n_folds": 1}, [], False,
            _INITIAL + _TRAINED_ONCE.format(folds="1 fold"),
        ),
        (
            plan_recursive, {}, [], False,
            _INITIAL + _TRAINED_ONCE.format(folds="number of folds"),
        ),
        (plan_recursive, {"n_folds": 6}, ["refit"], False, _INITIAL + " `refit` as requested."),
        (plan_recursive, {"n_folds": 6}, [], True, ""),
        (plan_stats, {"n_folds": 6}, [], False, _INITIAL),
        (
            plan_foundation, {"n_folds": 6}, [], False,
            "First fold start by default: 70% of the 100 observations (70), "
            "up to 2020-03-10.",
        ),
    ],
    ids=[
        "recursive",
        "baseline",
        "plan_none",
        "plan_none_one_fold",
        "recursive_one_fold",
        "without_n_folds",
        "refit_passed",
        "llm_configured",
        "stats",
        "foundation",
    ],
)
def test_build_cv_defaults_explanation_output_when_refit_is_default(
    plan, cv_config, overridden, llm_configured, expected
):
    """
    Test that "Trained once by default" is said only when `refit` is a
    default, the forecaster is trained and it is not ForecasterStats (which
    refits whatever the default); it names the folds when they are known.
    """
    result = build_cv_defaults_explanation(
        default        = default_share,
        cv_config      = cv_config,
        plan           = plan,
        overridden     = overridden,
        without_effect = [],
        llm_configured = llm_configured,
    )

    assert result == expected


@pytest.mark.parametrize(
    "default, expected",
    [
        (
            default_share,
            "First fold start by default: 70% of the 100 observations (70), "
            "up to 2020-03-10.",
        ),
        (
            default_minimum_window,
            "First fold start by default: 70% of the 100 observations (70) "
            "is less than what the rule reserves for the forecaster, so it "
            "is raised to 75, its window of 65 plus the 10 steps, up to "
            "2020-03-15.",
        ),
        (
            default_two_folds_minimum_window,
            "First fold start by default: the 90 observations the rule "
            "reserves for the forecaster (its window of 70 plus the 20 "
            "steps) is lowered to 60 so that two folds of 20 steps remain, "
            "up to 2020-02-29. That is less than the 71 observations the "
            "forecaster needs to run.",
        ),
    ],
    ids=["share", "minimum", "two_folds"],
)
def test_build_cv_defaults_explanation_output_when_plan_is_foundation(
    default, expected
):
    """
    Test that a foundation plan, whose model is not trained, says "First
    fold start by default" instead of the training size and has no sentence
    about refit.
    """
    result = _explain(default, plan_foundation)

    assert result == expected


@pytest.mark.parametrize(
    "plan, overridden, without_effect, expected",
    [
        (
            plan_recursive, ["refit"], [],
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10. `refit` as requested.",
        ),
        (
            plan_recursive, ["refit", "gap"], [],
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10. `refit` and `gap` as requested.",
        ),
        (
            plan_recursive, ["refit", "gap", "skip_folds"], [],
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10. `refit`, `gap` and `skip_folds` as "
            "requested.",
        ),
        (
            plan_recursive, ["fixed_train_size"], ["fixed_train_size"],
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10. Trained once by default: refitting in "
            "every fold would multiply the training cost by the 6 folds. "
            "`fixed_train_size` was passed but has no effect on this "
            "forecaster.",
        ),
        (
            plan_foundation, ["refit", "fixed_train_size"],
            ["refit", "fixed_train_size"],
            "First fold start by default: 70% of the 100 observations (70), "
            "up to 2020-03-10. `refit` and `fixed_train_size` were passed but "
            "have no effect on this forecaster.",
        ),
        (
            plan_recursive, ["gap", "fixed_train_size"], ["fixed_train_size"],
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10. Trained once by default: refitting in "
            "every fold would multiply the training cost by the 6 folds. "
            "`gap` as requested. `fixed_train_size` was passed but has no "
            "effect on this forecaster.",
        ),
        (
            plan_stats, ["refit", "fixed_train_size", "gap"],
            ["refit", "fixed_train_size"],
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10. `gap` as requested. `refit` and "
            "`fixed_train_size` were passed but have no effect on this "
            "forecaster.",
        ),
        (
            plan_recursive, ["initial_train_size"], [],
            "Trained once by default: refitting in every fold would multiply "
            "the training cost by the 6 folds. `initial_train_size` as "
            "requested.",
        ),
    ],
    ids=[
        "one_requested",
        "two_requested",
        "three_requested",
        "one_without_effect",
        "two_without_effect",
        "requested_and_without_effect",
        "stats_without_refit_sentence",
        "initial_train_size_passed",
    ],
)
def test_build_cv_defaults_explanation_output_when_parameters_are_passed(
    plan, overridden, without_effect, expected
):
    """
    Test that the names passed are joined as "`a`", "`a` and `b`" or "`a`,
    `b` and `c`", said "as requested" when they run and "was passed but has
    no effect" (plural "were passed but have") when they do not, and that a
    passed `initial_train_size` leaves out its default sentence.
    """
    result = _explain(default_share, plan, overridden, without_effect)

    assert result == expected


@pytest.mark.parametrize(
    "overridden, expected",
    [
        ([], ""),
        (["refit", "gap"], "`refit` and `gap` as requested."),
        (["initial_train_size"], "`initial_train_size` as requested."),
    ],
    ids=["nothing_passed", "names_passed", "initial_train_size_passed"],
)
def test_build_cv_defaults_explanation_output_when_llm_configured(
    overridden, expected
):
    """
    Test that no default is explained when the LLM set the parameters (its
    reasoning does it): the text is empty, or only names what the user
    passed. A foundation plan behaves the same.
    """
    result = _explain(
        default_share, plan_recursive, overridden, llm_configured=True
    )
    result_foundation = _explain(
        default_share, plan_foundation, overridden, llm_configured=True
    )

    assert result == expected
    assert result_foundation == expected


@pytest.mark.parametrize(
    "default, plan, created_for, overridden, llm_configured, expected",
    [
        (
            default_share, plan_recursive, plan_stats, [], False,
            "The strategy was created for another plan (ForecasterStats + "
            "Arima). Initial training size by default: 70% of the 100 "
            "observations (70), up to 2020-03-10. Trained once by default: "
            "refitting in every fold would multiply the training cost by the "
            "6 folds.",
        ),
        (
            default_minimum_window, plan_recursive, plan_stats, [], False,
            "The strategy was created for another plan (ForecasterStats + "
            "Arima). Initial training size by default: 70% of the 100 "
            "observations (70) is less than what the rule reserves for the "
            "forecaster of that plan, so it is raised to 75, its window of "
            "65 plus the 10 steps, up to 2020-03-15. Trained once by "
            "default: refitting in every fold would multiply the training "
            "cost by the 6 folds.",
        ),
        (
            default_two_folds_minimum_window, plan_recursive, plan_stats, [],
            False,
            "The strategy was created for another plan (ForecasterStats + "
            "Arima). Initial training size by default: the 90 observations "
            "the rule reserves for the forecaster of that plan (its window "
            "of 70 plus the 20 steps) is lowered to 60 so that two folds of "
            "20 steps remain, up to 2020-02-29. That is less than the 71 "
            "observations the forecaster of that plan needs to run. Trained "
            "once by default: refitting in every fold would multiply the "
            "training cost by the 6 folds.",
        ),
        (
            default_share, plan_recursive, plan_baseline, [], False,
            "The strategy was created for another plan (ForecasterBaseline). "
            "Initial training size by default: 70% of the 100 observations "
            "(70), up to 2020-03-10. Trained once by default: refitting in "
            "every fold would multiply the training cost by the 6 folds.",
        ),
        (
            default_share, None, plan_recursive, [], False,
            "The strategy was created for the plan (ForecasterRecursive + "
            "Ridge). Initial training size by default: 70% of the 100 "
            "observations (70), up to 2020-03-10. The shared strategy trains "
            "once by default: refitting in every fold would multiply the "
            "training cost by the 6 folds.",
        ),
        (
            default_share, plan_recursive, plan_stats, ["gap"], True,
            "The strategy was created for another plan (ForecasterStats + "
            "Arima). `gap` as requested.",
        ),
        (
            default_share, None, plan_recursive, [], True,
            "The strategy was created for the plan (ForecasterRecursive + "
            "Ridge).",
        ),
    ],
    ids=[
        "another_plan_share",
        "another_plan_minimum",
        "another_plan_two_folds",
        "another_plan_without_estimator",
        "comparison_without_plan",
        "another_plan_llm_configured",
        "comparison_llm_configured",
    ],
)
def test_build_cv_defaults_explanation_output_when_created_for_another_plan(
    default, plan, created_for, overridden, llm_configured, expected
):
    """
    Test that a strategy created for a plan other than the one that runs it
    starts with "created for another plan (...)" (or "created for the plan
    (...)" in a comparison, where plan is None), says "the forecaster of
    that plan" in the rules, and keeps that sentence when the LLM set the
    parameters.
    """
    result = _explain(
        default, plan, overridden,
        llm_configured=llm_configured, created_for=created_for,
    )

    assert result == expected
