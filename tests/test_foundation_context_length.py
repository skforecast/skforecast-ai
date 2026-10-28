# Unit test foundation_context_length

import re

import pytest

from skforecast_ai._foundation import foundation_context_length
from skforecast_ai.exceptions import InvalidInputError


def test_foundation_context_length_output_when_default_of_the_adapter():
    """
    Test that, without `context_length` in `estimator_kwargs`, it is the
    default of the skforecast adapter of the model (8192 for Chronos-2
    small), which the generated script writes.
    """
    assert foundation_context_length("autogluon/chronos-2-small", None) == 8192
    assert foundation_context_length("autogluon/chronos-2-small", {}) == 8192


def test_foundation_context_length_output_when_given_in_estimator_kwargs():
    """
    Test that `context_length` of `estimator_kwargs` takes precedence.
    """
    assert foundation_context_length(
        "autogluon/chronos-2-small", {"context_length": 512}
    ) == 512


def test_foundation_context_length_InvalidInputError_when_model_is_unknown():
    """
    Test that a model that no skforecast adapter serves raises the error of
    `resolve_foundation_model`.
    """
    err_msg = re.escape(
        "'nobody/none' is not a foundation model supported by skforecast."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        foundation_context_length("nobody/none", None)
