# Unit test resolve_default_candidates execution/comparison

from skforecast_ai.execution import comparison as comparison_module
from skforecast_ai.execution.comparison import resolve_default_candidates

from tests.fixtures_assistant import patch_find_spec
from tests.fixtures_compare import (
    assistant,
    plan_promo_no_exog,
    profile_h2o,
    profile_items,
    profile_promo,
)


def _build_plan(config):
    """Plan of a candidate of `profile_h2o`, as `compare()` builds it."""
    return assistant.plan(profile=profile_h2o, steps=12, **config)


def _resolve(skip_folds):
    """Default candidates of `profile_h2o` for a strategy with `skip_folds`."""
    return resolve_default_candidates(
        profile       = profile_h2o,
        strategy_plan = None,
        build_plan    = _build_plan,
        n_fits        = 1,
        steps         = 12,
        n_folds       = 6,
        skip_folds    = skip_folds,
    )


def test_resolve_default_candidates_leaves_out_stats_when_strategy_skips_folds(
    monkeypatch,
):
    """
    Test that ForecasterStats is not a candidate, and the note says why, when
    the strategy skips folds, while the other candidates of the profile stay.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: True
    )

    resolved = _resolve([1])

    forecasters = {config["forecaster"] for _, config in resolved.candidates}
    assert forecasters == {
        "ForecasterRecursive", "ForecasterDirect", "ForecasterFoundation"
    }
    assert resolved.skip_folds_note == (
        "ForecasterStats left out: the strategy has `skip_folds=[1]`, which "
        "skforecast does not allow for it (it refits ForecasterStats in every "
        "fold)."
    )


def test_resolve_default_candidates_keeps_stats_when_strategy_runs_every_fold(
    monkeypatch,
):
    """
    Test that ForecasterStats stays among the candidates, without a note,
    when the strategy does not skip folds.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: True
    )

    resolved = _resolve(None)

    forecasters = {config["forecaster"] for _, config in resolved.candidates}
    assert "ForecasterStats" in forecasters
    assert resolved.skip_folds_note is None


def test_resolve_default_candidates_leaves_out_an_estimator_not_installed(
    monkeypatch,
):
    """
    Test that, with several series and XGBoost not installed, the candidate
    `ForecasterRecursiveMultiSeries+XGBRegressor` is left out (so it counts
    in no cost) and the note says which package to install, after the note
    of the foundation model without its backend; the profile still lists
    the estimator.
    """
    patch_find_spec(monkeypatch, missing=["xgboost"])
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )

    resolved = resolve_default_candidates(
        profile       = profile_items,
        strategy_plan = None,
        build_plan    = lambda config: assistant.plan(
                            profile=profile_items, steps=7, **config
                        ),
        n_fits        = 1,
        steps         = 7,
        n_folds       = 4,
    )

    assert resolved.candidates == [
        (
            "ForecasterRecursiveMultiSeries+LGBMRegressor",
            {
                "forecaster": "ForecasterRecursiveMultiSeries",
                "estimator": "LGBMRegressor",
            },
        ),
        (
            "ForecasterRecursiveMultiSeries+Ridge",
            {"forecaster": "ForecasterRecursiveMultiSeries", "estimator": "Ridge"},
        ),
    ]
    assert resolved.backend_note == (
        "ForecasterFoundation left out: its default model "
        "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
        "which is not installed (pip install skforecast-ai[foundation]). "
        "ForecasterRecursiveMultiSeries+XGBRegressor left out: XGBRegressor "
        "needs the 'xgboost' package, which is not installed (pip install "
        "xgboost)."
    )
    assert profile_items.estimator_candidates == [
        "LGBMRegressor", "XGBRegressor", "Ridge"
    ]


def test_resolve_default_candidates_keeps_an_estimator_installed(monkeypatch):
    """
    Test that, with XGBoost taken as installed, its candidate stays and the
    note names only the foundation model without its backend.
    """
    patch_find_spec(monkeypatch, installed=["xgboost"])
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )

    resolved = resolve_default_candidates(
        profile       = profile_items,
        strategy_plan = None,
        build_plan    = lambda config: assistant.plan(
                            profile=profile_items, steps=7, **config
                        ),
        n_fits        = 1,
        steps         = 7,
        n_folds       = 4,
    )

    assert [name for name, _ in resolved.candidates] == [
        "ForecasterRecursiveMultiSeries+LGBMRegressor",
        "ForecasterRecursiveMultiSeries+XGBRegressor",
        "ForecasterRecursiveMultiSeries+Ridge",
    ]
    assert resolved.backend_note == (
        "ForecasterFoundation left out: its default model "
        "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
        "which is not installed (pip install skforecast-ai[foundation])."
    )


def _resolve_promo(strategy_plan):
    """Default candidates of `profile_promo` for the plan of a strategy."""

    def build_plan(config):
        return assistant.plan(profile=profile_promo, steps=7, **config)

    return resolve_default_candidates(
        profile       = profile_promo,
        strategy_plan = strategy_plan,
        build_plan    = build_plan,
        n_fits        = 1,
        steps         = 7,
        n_folds       = 5,
    )


def test_resolve_default_candidates_inherit_use_exog_false_of_the_user(
    monkeypatch,
):
    """
    Test that, when the user left the exogenous variables out of the plan
    of the strategy (`use_exog=False`), every candidate of the profile
    leaves them out too, and the recommended forecaster is then the row of
    that plan, with no row added for it.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )

    resolved = _resolve_promo(plan_promo_no_exog)

    assert resolved.candidates == [
        (
            "ForecasterRecursive",
            {"forecaster": "ForecasterRecursive", "use_exog": False},
        ),
        ("ForecasterDirect", {"forecaster": "ForecasterDirect", "use_exog": False}),
        ("ForecasterStats", {"forecaster": "ForecasterStats", "use_exog": False}),
    ]
    assert resolved.strategy_name == "ForecasterRecursive"


def test_resolve_default_candidates_keep_use_exog_when_the_rules_chose_it(
    monkeypatch,
):
    """
    Test that the candidates do not carry `use_exog` when the plan of the
    strategy uses the exogenous variables because the rules chose to: each
    candidate decides as its rules say.
    """
    monkeypatch.setattr(
        comparison_module, "foundation_backend_installed", lambda info: False
    )
    plan = assistant.plan(profile=profile_promo, steps=7)

    resolved = _resolve_promo(plan)

    assert [config for _, config in resolved.candidates] == [
        {"forecaster": "ForecasterRecursive"},
        {"forecaster": "ForecasterDirect"},
        {"forecaster": "ForecasterStats"},
    ]
