# Unit test resolve_default_candidates execution/comparison

from skforecast_ai.execution import comparison as comparison_module
from skforecast_ai.execution.comparison import resolve_default_candidates

from tests.fixtures_compare import assistant, profile_h2o


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
