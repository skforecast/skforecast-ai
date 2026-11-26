# Unit test _current_alias

import pytest

from skforecast_ai.recommendation.autoregressive import _current_alias


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("H", "h"),
        ("3H", "3h"),
        ("T", "min"),
        ("15T", "15min"),
        ("S", "s"),
        ("30S", "30s"),
        ("L", "ms"),
        ("U", "us"),
        ("M", "ME"),
        ("Q-DEC", "QE-DEC"),
        ("A-DEC", "YE-DEC"),
        ("AS", "YS"),
    ],
    ids=lambda value: f"{value}",
)
def test_current_alias_output_when_legacy_alias(frequency, expected):
    """
    Test that an alias pandas 2.1 infers is read under its current name,
    with its multiplier and its anchor: pandas 3 no longer reads them.
    """
    assert _current_alias(frequency) == expected


@pytest.mark.parametrize(
    "frequency",
    ["h", "15min", "D", "MS", "ME", "W-SUN", "QS-OCT", "ms", "unknown", ""],
    ids=lambda frequency: f"{frequency}",
)
def test_current_alias_output_is_frequency_when_current_alias(frequency):
    """
    Test that a frequency that is not written with a legacy alias is
    returned as it is.
    """
    assert _current_alias(frequency) == frequency
