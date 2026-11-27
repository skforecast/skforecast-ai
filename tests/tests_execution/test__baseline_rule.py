# Unit test _baseline_rule execution/comparison

from types import SimpleNamespace

import pytest

from skforecast_ai.execution.comparison import _baseline_rule


def _ranked_entry(name: str, forecaster_kwargs: dict, value: float = 1.0) -> tuple:
    """Build a `(name, backtest, value)` entry with the plan the rule reads."""
    backtest = SimpleNamespace(
        plan=SimpleNamespace(
            forecaster="ForecasterEquivalentDate",
            estimator=None,
            forecaster_kwargs=forecaster_kwargs,
        ),
        metrics=None,
    )
    return (name, backtest, value)


@pytest.mark.parametrize(
    "forecaster_kwargs, expected",
    [
        (
            {"offset": 1, "n_offsets": 1},
            "The baseline repeats the last observed value.",
        ),
        (
            {"offset": 1},
            "The baseline repeats the last observed value.",
        ),
        (
            {},
            "The baseline repeats the last observed value.",
        ),
        (
            {"offset": 24, "n_offsets": 1},
            "The baseline repeats the value observed 24 steps earlier.",
        ),
        (
            {"offset": 7, "n_offsets": 3},
            "The baseline averages the values observed 7, 14 and 21 "
            "steps earlier.",
        ),
        (
            {"offset": 12, "n_offsets": 2},
            "The baseline averages the values observed 12 and 24 "
            "steps earlier.",
        ),
        (
            {"offset": 1, "n_offsets": 3},
            "The baseline averages the values observed 1, 2 and 3 "
            "steps earlier.",
        ),
    ],
    ids=[
        "naive",
        "naive without n_offsets",
        "naive without kwargs",
        "seasonal naive",
        "n_offsets 3",
        "n_offsets 2",
        "offset 1 with n_offsets 3",
    ],
)
def test_baseline_rule_output_from_offset_and_n_offsets(forecaster_kwargs, expected):
    """
    Test that `_baseline_rule` says what the baseline predicts from the
    `offset` and `n_offsets` of its plan (both default to 1 when missing).
    """
    ranked = [
        _ranked_entry("model", {"lags": 3}, 0.5),
        _ranked_entry("Baseline", forecaster_kwargs, 1.0),
    ]

    result = _baseline_rule(ranked, "Baseline")

    assert result == expected


def test_baseline_rule_names_the_baseline_that_ran_among_the_ranked():
    """
    Test that `_baseline_rule` reads the plan of the entry named
    `baseline_name`, not that of another candidate, and does not name it.
    """
    ranked = [
        _ranked_entry("other", {"offset": 5}, 0.5),
        _ranked_entry("Baseline (seasonal naive)", {"offset": 24}, 1.0),
    ]

    result = _baseline_rule(ranked, "Baseline (seasonal naive)")

    assert result == (
        "The baseline repeats the value observed "
        "24 steps earlier."
    )


def test_baseline_rule_returns_None_when_baseline_missing_from_ranked():
    """
    Test that `_baseline_rule` returns None when the baseline is not among the
    ranked candidates (it failed to run).
    """
    ranked = [_ranked_entry("model", {"offset": 24}, 0.5)]

    assert _baseline_rule(ranked, "Baseline (naive)") is None


@pytest.mark.parametrize(
    "forecaster_kwargs",
    [
        {"offset": "24"},
        {"offset": 1.5},
        {"offset": 7, "n_offsets": "3"},
        {"offset": None},
    ],
    ids=["offset text", "offset float", "n_offsets text", "offset None"],
)
def test_baseline_rule_returns_None_when_offset_is_not_an_int(forecaster_kwargs):
    """
    Test that `_baseline_rule` returns None when `offset` or `n_offsets` is
    not a whole number of steps (for example a pandas offset or a text).
    """
    ranked = [_ranked_entry("Baseline", forecaster_kwargs)]

    assert _baseline_rule(ranked, "Baseline") is None
