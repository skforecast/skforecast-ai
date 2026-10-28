# Unit test match_strategy_plan

from skforecast_ai.execution.comparison import match_strategy_plan

from tests.fixtures_compare import (
    assistant,
    plan_multivariate,
    plan_sales,
    plan_sales_refined,
    profile_sales,
)


def _build_plan(config):
    """Plan of a candidate of `profile_sales`, as `compare()` builds it."""
    return assistant.plan(profile=profile_sales, steps=5, **config)


def _plans(**configs):
    """Plans of the candidates of `profile_sales`, by name."""
    return {name: _build_plan(config) for name, config in configs.items()}


def test_match_strategy_plan_names_the_candidate_with_the_same_decisions():
    """
    Test that the candidate that makes the decisions of the refined plan
    (RandomForestRegressor with lags 1 to 3) is its row, without a note,
    whatever the other candidates.
    """
    plans = _plans(
        ridge={"forecaster": "ForecasterRecursive"},
        forest={"estimator": "RandomForestRegressor", "lags": [1, 2, 3]},
    )

    name, note = match_strategy_plan(
        strategy_plan = plan_sales_refined,
        plans         = plans,
        profile       = profile_sales,
        build_plan    = _build_plan,
    )

    assert (name, note) == ("forest", None)


def test_match_strategy_plan_note_when_no_candidate_makes_its_decisions():
    """
    Test that, when no candidate makes the decisions of the plan (the same
    estimator with other lags is not it), the note says that it was not
    compared and how to compare it (V24).
    """
    plans = _plans(
        ridge={"forecaster": "ForecasterRecursive"},
        forest={"estimator": "RandomForestRegressor", "lags": [1, 2]},
    )

    name, note = match_strategy_plan(
        strategy_plan = plan_sales_refined,
        plans         = plans,
        profile       = profile_sales,
        build_plan    = _build_plan,
    )

    assert name is None
    assert note == (
        "The plan the strategy was created for (ForecasterRecursive + "
        "RandomForestRegressor) makes other decisions than every candidate, "
        "so it was not compared: `candidates` runs only the configurations "
        "given. Add it to `candidates` with its decisions, or leave "
        "`candidates` out to run it in the row 'Strategy plan' next to the "
        "configurations the profile recommends."
    )


def test_match_strategy_plan_note_when_plan_is_of_another_family():
    """
    Test that a ForecasterDirectMultiVariate plan, whose metrics cannot be
    ranked with single-series candidates, gets the note of another family.
    """
    name, note = match_strategy_plan(
        strategy_plan = plan_multivariate,
        plans         = _plans(ridge={"forecaster": "ForecasterRecursive"}),
        profile       = profile_sales,
        build_plan    = _build_plan,
    )

    assert name is None
    assert note.startswith(
        "The plan the strategy was created for (ForecasterDirectMultiVariate"
    )
    assert note.endswith(
        "was not compared: `candidates` runs only the configurations given, "
        "and its metrics are not comparable with theirs (a multivariate "
        "forecaster is scored on the single series it predicts, a "
        "multi-series forecaster on the average across all series). Backtest "
        "it, or compare it with `candidates` of its family."
    )


def test_match_strategy_plan_note_when_its_plan_cannot_be_built_again():
    """
    Test that a plan that `build_plan` cannot build again matches no
    candidate, and the note says it was not compared.
    """

    def failing(config):
        raise ValueError("cannot build")

    name, note = match_strategy_plan(
        strategy_plan = plan_sales,
        plans         = _plans(ridge={"forecaster": "ForecasterRecursive"}),
        profile       = profile_sales,
        build_plan    = failing,
    )

    assert name is None
    assert "so it was not compared" in note


def test_match_strategy_plan_None_when_no_plan_was_built():
    """
    Test that nothing is said when no candidate could be built: nothing was
    compared at all, which `AllCandidatesFailedError` says.
    """
    assert match_strategy_plan(
        strategy_plan = plan_sales_refined,
        plans         = {},
        profile       = profile_sales,
        build_plan    = _build_plan,
    ) == (None, None)
