# Unit test join_remedies

import pytest

from skforecast_ai._utils import join_remedies


@pytest.mark.parametrize(
    "remedies, expected",
    [
        ([], ""),
        (["a"], "a"),
        (["a", "b"], "a or b"),
        (["a", "b", "c"], "a, b or c"),
        (["a", "b", "c", "d"], "a, b, c or d"),
    ],
    ids=lambda value: f"{value}",
)
def test_join_remedies_output(remedies, expected):
    """
    Test that join_remedies returns an empty text for no phrase, the phrase
    itself for one, and the phrases separated by commas with the last one
    after "or" for more.
    """
    result = join_remedies(remedies)

    assert result == expected
