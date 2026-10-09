# Unit test check_foundation_backend

import re

import pytest

from skforecast_ai import _foundation as foundation_module
from skforecast_ai._foundation import check_foundation_backend
from skforecast_ai.exceptions import InvalidInputError


def test_check_foundation_backend_InvalidInputError_when_backend_not_installed(
    monkeypatch,
):
    """
    Test that a model whose backend package is not installed raises with the
    code 'missing_dependency', the field 'estimator' and the install command.
    """
    monkeypatch.setattr(
        foundation_module, "foundation_backend_installed", lambda info: False
    )

    err_msg = re.escape(
        "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
        "which is not installed (pip install \"chronos-forecasting\")."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        check_foundation_backend("autogluon/chronos-2-small")

    assert exc_info.value.code == "missing_dependency"
    assert exc_info.value.field == "estimator"
    assert exc_info.value.hint == (
        'Install it where skforecast-ai runs: pip install "chronos-forecasting".'
    )


@pytest.mark.parametrize("model_id", [None, "unknown/model", "Chronos-2"])
def test_check_foundation_backend_output_when_nothing_to_check(
    monkeypatch, model_id
):
    """
    Test that no model ID, or an ID that no adapter serves, does nothing even
    when no backend is installed: the validation of the plan reports it.
    """
    monkeypatch.setattr(
        foundation_module, "foundation_backend_installed", lambda info: False
    )

    assert check_foundation_backend(model_id) is None


def test_check_foundation_backend_output_when_backend_installed(monkeypatch):
    """
    Test that a model whose backend package is installed passes.
    """
    monkeypatch.setattr(
        foundation_module, "foundation_backend_installed", lambda info: True
    )

    assert check_foundation_backend("autogluon/chronos-2-small") is None
