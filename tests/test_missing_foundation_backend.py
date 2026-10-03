# Unit test missing_foundation_backend

import pytest

from skforecast_ai import _foundation as foundation_module
from skforecast_ai._foundation import missing_foundation_backend


def test_missing_foundation_backend_output_when_backend_not_installed(monkeypatch):
    """
    Test that the package to install is returned when the backend of the
    model is not installed.
    """
    monkeypatch.setattr(
        foundation_module, "foundation_backend_installed", lambda info: False
    )

    assert missing_foundation_backend("autogluon/chronos-2-small") == (
        "chronos-forecasting"
    )


def test_missing_foundation_backend_output_when_backend_installed(monkeypatch):
    """
    Test that None is returned when the backend of the model is installed.
    """
    monkeypatch.setattr(
        foundation_module, "foundation_backend_installed", lambda info: True
    )

    assert missing_foundation_backend("autogluon/chronos-2-small") is None


@pytest.mark.parametrize("model_id", [None, "unknown/model", "Chronos-2"])
def test_missing_foundation_backend_output_when_model_not_known(
    monkeypatch, model_id
):
    """
    Test that no model ID, or an ID that no adapter serves, gives None even
    when no backend is installed: the validation of the plan reports it.
    """
    monkeypatch.setattr(
        foundation_module, "foundation_backend_installed", lambda info: False
    )

    assert missing_foundation_backend(model_id) is None
