# Unit test add_strategy_candidate

import pytest

from skforecast_ai.execution.comparison import (
    STRATEGY_PLAN_NAME,
    add_strategy_candidate,
    resolve_compare_candidates,
    strategy_candidate_config,
)

from tests.fixtures_compare import (
    assistant,
    plan_multivariate,
    plan_sales,
    plan_sales_direct,
    plan_sales_edited,
    plan_sales_refined,
    profile_multi,
    profile_sales,
)

_CANDIDATES = [
    ("ForecasterRecursive", {"forecaster": "ForecasterRecursive"}),
    ("ForecasterDirect", {"forecaster": "ForecasterDirect"}),
]


def _build_plan(config):
    """Plan of a candidate of `profile_sales`, as `compare()` builds it."""
    return assistant.plan(profile=profile_sales, steps=5, **config)


def test_add_strategy_candidate_appends_the_plan_when_it_is_none_of_the_candidates():
    """
    Test that a refined plan is appended last as 'Strategy plan' with the
    configuration of `strategy_candidate_config()`, without a note, and that
    the candidates passed are not changed.
    """
    candidates = list(_CANDIDATES)

    result, name, note = add_strategy_candidate(
        candidates    = candidates,
        strategy_plan = plan_sales_refined,
        profile       = profile_sales,
        build_plan    = _build_plan,
    )

    assert result == [
        *_CANDIDATES,
        (
            "Strategy plan",
            {
                "forecaster": "ForecasterRecursive",
                "estimator": "RandomForestRegressor",
                "lags": [1, 2, 3],
                "window_features": [
                    {"stats": ["mean", "std"], "window_size": 3},
                    {"stats": ["mean"], "window_size": 7},
                    {"stats": ["mean"], "window_size": 21},
                ],
            },
        ),
    ]
    assert result[-1][1] == strategy_candidate_config(plan_sales_refined)
    assert name == STRATEGY_PLAN_NAME == "Strategy plan"
    assert note is None
    assert candidates == _CANDIDATES


@pytest.mark.parametrize(
    "plan, expected_name",
    [
        (plan_sales, "ForecasterRecursive"),
        (plan_sales_direct, "ForecasterDirect"),
        (
            assistant.refine_plan(
                profile=profile_sales, plan=plan_sales, estimator="Ridge"
            ),
            "ForecasterRecursive",
        ),
    ],
    ids=["recursive", "direct", "refined to the same estimator"],
)
def test_add_strategy_candidate_returns_the_candidate_that_makes_the_same_decisions(
    plan, expected_name
):
    """
    Test that a plan that makes the same decisions as one of the candidates
    appends nothing and returns the name of that candidate, also when the
    plan was refined with the value the rules had chosen (the marks of who
    decided are not compared).
    """
    result, name, note = add_strategy_candidate(
        candidates    = list(_CANDIDATES),
        strategy_plan = plan,
        profile       = profile_sales,
        build_plan    = _build_plan,
    )

    assert result == _CANDIDATES
    assert name == expected_name
    assert note is None


def test_add_strategy_candidate_appends_the_plan_when_the_candidate_cannot_be_built():
    """
    Test that a candidate whose plan cannot be built is skipped when looking
    for the one that makes the same decisions, so the plan is appended as
    'Strategy plan'.
    """
    def build_plan(config):
        if config == {"forecaster": "ForecasterRecursive"}:
            raise ValueError("cannot be built")
        return _build_plan(config)

    result, name, note = add_strategy_candidate(
        candidates    = list(_CANDIDATES),
        strategy_plan = plan_sales,
        profile       = profile_sales,
        build_plan    = build_plan,
    )

    assert [candidate_name for candidate_name, _ in result] == [
        "ForecasterRecursive", "ForecasterDirect", "Strategy plan"
    ]
    assert result[-1][1] == strategy_candidate_config(plan_sales)
    assert name == "Strategy plan"
    assert note is None


def test_add_strategy_candidate_appends_the_plan_without_dedup_when_build_plan_raises():
    """
    Test that when `build_plan` raises for the configuration of the plan,
    the plan is appended as 'Strategy plan' without comparing it with the
    candidates and without a note: the candidate fails when it runs, with
    its own reason.
    """
    def build_plan(config):
        raise ValueError("cannot be built")

    result, name, note = add_strategy_candidate(
        candidates    = list(_CANDIDATES),
        strategy_plan = plan_sales,
        profile       = profile_sales,
        build_plan    = build_plan,
    )

    assert result == [
        *_CANDIDATES, ("Strategy plan", strategy_candidate_config(plan_sales))
    ]
    assert name == "Strategy plan"
    assert note is None


def test_add_strategy_candidate_note_when_plan_was_edited_by_hand():
    """
    Test that a value of the plan that `plan()` does not rebuild (a
    differentiation edited by hand) is reported in the note, which names the
    fields, while the plan is still appended as 'Strategy plan'.
    """
    result, name, note = add_strategy_candidate(
        candidates    = list(_CANDIDATES),
        strategy_plan = plan_sales_edited,
        profile       = profile_sales,
        build_plan    = _build_plan,
    )

    assert result == [
        *_CANDIDATES, ("Strategy plan", strategy_candidate_config(plan_sales_edited))
    ]
    assert name == "Strategy plan"
    assert note == (
        "The row 'Strategy plan' runs the plan the strategy was created for "
        "as `plan()` rebuilds it, which changes these values of that plan: "
        "[\"forecaster_kwargs['differentiation']\"]. Pass the plan to "
        "`backtest()` to measure it as it is."
    )


def test_add_strategy_candidate_note_ignores_interval_and_metric_of_the_plan():
    """
    Test that a plan with an interval and a metric the comparison replaces
    by its own is not reported as edited: those two are the comparison's for
    every row.
    """
    plan = assistant.refine_plan(
        profile  = profile_sales,
        plan     = plan_sales,
        interval = [0.1, 0.9],
        metric   = "mean_squared_error",
    )

    result, name, note = add_strategy_candidate(
        candidates    = list(_CANDIDATES),
        strategy_plan = plan,
        profile       = profile_sales,
        build_plan    = _build_plan,
    )

    assert result == _CANDIDATES
    assert name == "ForecasterRecursive"
    assert note is None


def test_add_strategy_candidate_leaves_out_the_plan_of_another_family():
    """
    Test that a multivariate plan, when the data have two series and the
    candidates are multi-series, is not appended: the name is None and the
    note says the metrics are not comparable.
    """
    candidates = resolve_compare_candidates(None, profile_multi)

    result, name, note = add_strategy_candidate(
        candidates    = candidates,
        strategy_plan = plan_multivariate,
        profile       = profile_multi,
        build_plan    = lambda config: pytest.fail("the plan must not be rebuilt"),
    )

    assert result == candidates
    assert name is None
    assert note == (
        "The plan the strategy was created for (ForecasterDirectMultiVariate) "
        "is not in the comparison: its metrics are not comparable with those "
        "of the candidates the profile recommends (a multivariate forecaster "
        "is scored on the single series it predicts, a multi-series "
        "forecaster on the average across all series). Backtest it, or "
        "compare it with `candidates` of its family."
    )
