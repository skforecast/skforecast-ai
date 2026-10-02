# Unit test has_control_characters

import pytest

from skforecast_ai.mcp._inputs import has_control_characters


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Temperature (C)", False),
        ("Año 'quoted' \\ <tag>", False),
        ("a\nb", True),
        ("a\rb", True),
        ("a\tb", True),
        ("a\x00b", True),
        ("a\x1bb", True),
        ("a\u0085b", True),
        ("a b", True),
        ("a b", True),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_has_control_characters_output(text, expected):
    """
    Test that line breaks, separators and other control characters are
    found, and that quotes, backslashes, brackets and accents are not.
    """
    assert has_control_characters(text) is expected
