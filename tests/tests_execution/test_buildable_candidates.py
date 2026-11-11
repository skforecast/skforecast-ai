# Unit test buildable_candidates execution/comparison

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.execution.comparison import buildable_candidates

_CANDIDATES = [
    ("recursive", {"forecaster": "ForecasterRecursive"}),
    ("broken", {"forecaster": "ForecasterRecursive", "lags": 0}),
    ("direct", {"forecaster": "ForecasterDirect"}),
    ("stats", {"forecaster": "ForecasterStats"}),
]


def _build_plan(config):
    """Fake plan builder that fails for a config with `lags` equal to 0."""
    if config.get("lags") == 0:
        raise ValueError("lags must be positive")

    return object()


def test_buildable_candidates_output_when_one_plan_cannot_be_built():
    """
    Test that the candidate whose `build_plan` raises is left out and the
    others are kept, in the input order, as the same `(name, config)`
    pairs.
    """
    result = buildable_candidates(
        candidate_configs = _CANDIDATES,
        build_plan        = _build_plan,
    )

    assert result == [_CANDIDATES[0], _CANDIDATES[2], _CANDIDATES[3]]


def test_buildable_candidates_calls_build_plan_once_per_candidate_in_order():
    """
    Test that `build_plan` is called with the config of every candidate,
    once and in the input order, and that the input list is not modified.
    """
    calls = []

    def build_plan(config):
        calls.append(config)
        return _build_plan(config)

    candidates = list(_CANDIDATES)
    buildable_candidates(candidate_configs=candidates, build_plan=build_plan)

    assert calls == [config for _, config in _CANDIDATES]
    assert candidates == _CANDIDATES


@pytest.mark.parametrize(
    "error",
    [ValueError("a"), InvalidInputError("b"), KeyError("c"), RuntimeError("d")],
    ids=lambda error: type(error).__name__,
)
def test_buildable_candidates_leaves_out_candidate_whatever_the_error(error):
    """
    Test that a candidate is left out whatever the error its plan raises,
    since `compare()` fails on any of them and runs nothing for it.
    """
    def build_plan(config):
        if config.get("lags") == 0:
            raise error
        return object()

    result = buildable_candidates(
        candidate_configs = _CANDIDATES,
        build_plan        = build_plan,
    )

    assert [name for name, _ in result] == ["recursive", "direct", "stats"]


@pytest.mark.parametrize(
    "candidate_configs, expected",
    [
        (_CANDIDATES[1:2], []),
        ([], []),
        (_CANDIDATES[:1], _CANDIDATES[:1]),
    ],
    ids=["none_buildable", "no_candidates", "all_buildable"],
)
def test_buildable_candidates_output_when_none_or_all_are_buildable(
    candidate_configs, expected
):
    """
    Test that the result is empty when no plan can be built or there are no
    candidates, and the same candidates when every plan can be built.
    """
    result = buildable_candidates(
        candidate_configs = candidate_configs,
        build_plan        = _build_plan,
    )

    assert result == expected
