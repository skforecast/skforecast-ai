# Unit test ModelPolicy.check

import dataclasses
import pytest
from skforecast.foundation import get_model_info

from skforecast_ai.mcp._errors import ServerError
from skforecast_ai.mcp import _foundation
from skforecast_ai.mcp._foundation import ModelPolicy


@pytest.mark.parametrize(
    "model_id",
    [
        None,
        "autogluon/chronos-2-small",
        "amazon/chronos-2-base",
        "google/timesfm-2.5-200m-pytorch",
        "soda-inria/tabicl",
        "Synthefy/Nori",
        "theforecastingcompany/t0-alpha",
        "nobody/unknown-model",
    ],
)
def test_model_policy_check_accepts_permissive_and_unknown_models(model_id):
    """
    Test that models whose license does not restrict commercial use, without
    gated weights or a provider account, pass without `--allow-model`, and
    that a model skforecast does not serve is left to the core, which
    rejects it.
    """
    assert ModelPolicy().check(model_id, "estimator") is None


def test_model_policy_check_ServerError_when_restricted_model_not_allowed():
    """
    Test that a restricted model is `model_not_allowed` with its license
    and, in the hint, the license of the default model (an agent told only
    its name stated a license from memory, or offered other models), and
    passes once its prefix (or a longer one) is allowed, but not with
    the prefix of another model.
    """
    with pytest.raises(ServerError) as info:
        ModelPolicy().check("google/timesfm-3.0-pytorch", "estimator")

    error = info.value
    assert error.code == "model_not_allowed"
    assert error.field == "estimator"
    assert str(error).startswith(
        "The server does not run 'google/timesfm-3.0-pytorch': its license is "
        "timesfm-non-commercial-license-v1.0 "
        "(https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE), "
        "which restricts commercial use. Foundation models whose license "
        "restricts commercial use, whose weights are gated or whose provider "
        "requires an account only run when the server is started with "
        "`--allow-model`."
    )
    assert error.hint == (
        "Tell the user about the license and, if they accept it, ask them to "
        "restart the server with `--allow-model google/timesfm-3.0`. "
        "The only alternative to offer is the default model, "
        "'autogluon/chronos-2-small' (license Apache-2.0, as skforecast "
        "registers it): leave `estimator` out for it. Name no other model and "
        "no other license: nothing here tells you which ones the server runs."
    )
    assert error.details == {
        "model_id": "google/timesfm-3.0-pytorch",
        "allow_model": "google/timesfm-3.0",
        "license": "timesfm-non-commercial-license-v1.0",
        "license_url": (
            "https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE"
        ),
        "commercial_use_restricted": True,
        "requires_hf_auth": False,
        "requires_provider_auth": False,
    }
    assert ModelPolicy(("google/timesfm-3.0",)).check(
        "google/timesfm-3.0-pytorch", "estimator"
    ) is None
    assert ModelPolicy(("google/timesfm-3.0-pytorch",)).check(
        "google/timesfm-3.0-pytorch", "estimator"
    ) is None
    with pytest.raises(ServerError):
        ModelPolicy(("Salesforce/moirai-2",)).check(
            "google/timesfm-3.0-pytorch", "estimator"
        )


def test_model_policy_check_ServerError_names_the_provider_account():
    """
    Test that TabPFN, whose provider requires an account, says so.
    """
    with pytest.raises(ServerError, match="its provider requires its own account"):
        ModelPolicy().check("priorlabs/tabpfn-ts", "estimator")


def test_model_policy_check_ServerError_names_gated_weights(monkeypatch):
    """
    Test that a model with gated weights says so. No adapter of skforecast
    0.26 is gated, so the information of t0 is marked as gated.
    """
    info = dataclasses.replace(
        get_model_info("theforecastingcompany/t0-alpha"), requires_hf_auth=True
    )
    monkeypatch.setattr(_foundation, "resolve_foundation_model", lambda _: info)

    with pytest.raises(ServerError, match="gated on the Hugging Face Hub"):
        ModelPolicy().check("theforecastingcompany/t0-alpha", "estimator")


def test_model_policy_check_ServerError_when_skforecast_gives_no_information(
    monkeypatch,
):
    """
    Test that a model whose information lacks the license fields is blocked
    by default and says that skforecast gives no license information.
    """
    @dataclasses.dataclass(frozen=True)
    class OldInfo:
        model_id: str = "autogluon/chronos-2-small"
        adapter: str = "ChronosAdapter"
        model_id_prefixes: tuple = ("autogluon/chronos-2",)
        requires_hf_auth: bool = False

    monkeypatch.setattr(_foundation, "resolve_foundation_model", lambda _: OldInfo())

    with pytest.raises(ServerError) as info:
        ModelPolicy().check("autogluon/chronos-2-small", "estimator")

    assert str(info.value).startswith(
        "The server does not run 'autogluon/chronos-2-small': skforecast gives "
        "no license information for it, so the server cannot tell which uses "
        "its license permits; skforecast does not say whether its provider "
        "requires an account."
    )
    assert info.value.details["license"] is None
