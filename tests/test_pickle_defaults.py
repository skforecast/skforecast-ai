# Unit test PickleDefaultsMixin

import pickle

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant

from tests.fixtures_datasets import df_h2o

assistant = ForecastingAssistant()
profile = assistant.profile(data=df_h2o, target="x")
plan = assistant.plan(profile, steps=12, estimator="Ridge")
cv_result = assistant.create_cv(profile, plan)
backtest_result = assistant.backtest(
    data=df_h2o, cv=cv_result, profile=profile, plan=plan, show_progress=False
)


def _saved_without(obj, names):
    """
    Return `obj` as pickle restores an object saved by a version that did
    not have the fields `names`: its state without them.
    """
    state = obj.__getstate__()
    state["__dict__"] = {
        key: value for key, value in state["__dict__"].items() if key not in names
    }
    restored = type(obj).__new__(type(obj))
    restored.__setstate__(state)

    return pickle.loads(pickle.dumps(restored))


@pytest.mark.parametrize(
    "obj, names, expected",
    [
        (
            cv_result,
            ["overridden_fields", "fields_without_effect", "llm_configured",
             "defaults_explanation"],
            [[], [], False, ""],
        ),
        (
            backtest_result,
            ["cv_overridden_fields", "cv_fields_without_effect",
             "cv_llm_configured", "cv_defaults_explanation"],
            [None, [], False, ""],
        ),
        (plan, ["overridden_fields", "exog_columns"], [[], None]),
        (profile.data_profile, ["time_zone", "unused_columns"], [None, []]),
    ],
    ids=["CVResult", "BacktestResult", "ForecastPlan", "DataProfile"],
)
def test_pickle_defaults_output_fields_added_after_the_object_was_saved(
    obj, names, expected
):
    """
    Test that an object pickled without fields added later comes back with
    their defaults, and that its display and description work.
    """
    restored = _saved_without(obj, names)

    assert [getattr(restored, name) for name in names] == expected
    if hasattr(restored, "describe"):
        assert isinstance(restored.describe(), str)


def test_pickle_defaults_backtest_with_a_strategy_saved_by_an_earlier_version():
    """
    Test that backtest() and compare() run with a `CVResult` pickled without
    the fields that say where its values come from, and report them as not
    chosen by the user: both raised `AttributeError`, backtest() after
    running.
    """
    restored = _saved_without(
        cv_result,
        ["overridden_fields", "fields_without_effect", "llm_configured",
         "defaults_explanation"],
    )

    result = assistant.backtest(
        data=df_h2o, cv=restored, profile=profile, plan=plan, show_progress=False
    )
    comparison = assistant.compare(
        data          = df_h2o,
        cv            = restored,
        profile       = profile,
        candidates    = [("ridge", {"estimator": "Ridge"})],
        baseline      = False,
        show_progress = False,
    )

    assert isinstance(restored.cv, TimeSeriesFold)
    assert result.cv_overridden_fields == []
    assert result.metrics.equals(backtest_result.metrics)
    assert comparison.cv_overridden_fields == []
