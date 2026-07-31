# Unit test ForecastingAssistant docstrings

import re

import pytest

from skforecast_ai.assistant import ForecastingAssistant
from skforecast_ai.schemas import (
    AskResult,
    BacktestResult,
    CodeGenerationResult,
    ComparisonResult,
    ForecastResult,
)

# Methods whose `Returns` section documents the attributes of the result
# wrapper it returns, as `- <attribute>: <description>` bullets.
RESULT_WRAPPER_METHODS = [
    ("forecast_code", CodeGenerationResult),
    ("forecast", ForecastResult),
    ("backtest_code", CodeGenerationResult),
    ("backtest", BacktestResult),
    ("compare", ComparisonResult),
    ("ask", AskResult),
]


def extract_section(docstring: str, section: str) -> list[str]:
    """
    Extract the body lines of a NumPy-style docstring section.

    Parameters
    ----------
    docstring : str
        Docstring to parse.
    section : str
        Name of the section, for example `'Returns'`.

    Returns
    -------
    lines : list of str
        Lines between the section underline and the next section header.
    """

    lines = docstring.splitlines()
    start = None
    for i, line in enumerate(lines[:-1]):
        if line.strip() == section and set(lines[i + 1].strip()) == {"-"}:
            start = i + 2
            break
    if start is None:
        return []

    end = len(lines)
    for i in range(start, len(lines) - 1):
        if lines[i].strip() and set(lines[i + 1].strip()) == {"-"}:
            end = i
            break

    return lines[start:end]


def extract_returns_bullets(docstring: str) -> list[str]:
    """
    Extract the `- <name>:` bullet names from the `Returns` section.

    Parameters
    ----------
    docstring : str
        Docstring to parse.

    Returns
    -------
    names : list of str
        Names listed as bullets, in order of appearance.
    """

    return [
        match.group(1)
        for line in extract_section(docstring, "Returns")
        if (match := re.match(r"\s*-\s+(\w+):", line))
    ]


def extract_attribute_names(docstring: str) -> list[str]:
    """
    Extract the attribute names from the `Attributes` section.

    Parameters
    ----------
    docstring : str
        Docstring to parse.

    Returns
    -------
    names : list of str
        Names documented in the section, in order of appearance.
    """

    return [
        match.group(1)
        for line in extract_section(docstring, "Attributes")
        if (match := re.match(r"\s*(\w+) : ", line))
    ]


@pytest.mark.parametrize(
    "method_name, result_model",
    RESULT_WRAPPER_METHODS,
    ids=[name for name, _ in RESULT_WRAPPER_METHODS],
)
def test_returns_bullets_match_result_model_attributes(method_name, result_model):
    """
    Test that the attributes listed in the `Returns` section of a
    result-wrapper method match the `Attributes` section of the returned
    model, and that the model documents only fields or properties that
    actually exist.
    """

    documented = extract_returns_bullets(
        getattr(ForecastingAssistant, method_name).__doc__
    )
    expected = extract_attribute_names(result_model.__doc__)
    # Derived attributes are exposed as read-only properties rather than
    # fields, so they are legitimate entries of the `Attributes` section.
    properties = {
        name
        for klass in result_model.__mro__
        for name, value in vars(klass).items()
        if isinstance(value, property)
    }
    fields = set(result_model.model_fields) | properties

    assert expected, (
        f"`{result_model.__name__}` documents no attributes in its "
        f"`Attributes` section."
    )
    assert set(expected) - fields == set(), (
        f"`{result_model.__name__}` documents attributes that are not model "
        f"fields or properties: {sorted(set(expected) - fields)}."
    )
    assert set(documented) - set(expected) == set(), (
        f"`ForecastingAssistant.{method_name}` documents attributes that "
        f"`{result_model.__name__}` does not: "
        f"{sorted(set(documented) - set(expected))}."
    )
    assert set(expected) - set(documented) == set(), (
        f"`ForecastingAssistant.{method_name}` does not document these "
        f"`{result_model.__name__}` attributes: "
        f"{sorted(set(expected) - set(documented))}."
    )
