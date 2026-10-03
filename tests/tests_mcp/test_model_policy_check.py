# Unit test ModelPolicy.check

import pytest

from skforecast_ai.mcp._errors import ServerError
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
        "nobody/unknown-model",
    ],
)
def test_model_policy_check_accepts_permissive_and_unknown_models(model_id):
    """
    Test that models without a license restriction or gated weights pass
    without `--allow-model`, and that a model skforecast does not serve is
    left to the core, which rejects it.
    """
    assert ModelPolicy().check(model_id, "estimator") is None


def test_model_policy_check_ServerError_when_restricted_model_not_allowed():
    """
    Test that a restricted model is `model_not_allowed` with its license,
    and passes once its prefix (or a longer one) is allowed, but not with
    the prefix of another model.
    """
    with pytest.raises(ServerError) as info:
        ModelPolicy().check("google/timesfm-3.0-pytorch", "estimator")

    error = info.value
    assert error.code == "model_not_allowed"
    assert error.field == "estimator"
    assert str(error).startswith(
        "The server does not run 'google/timesfm-3.0-pytorch': its license is "
        "TimesFM Non-Commercial License v1.0 "
        "(https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE)."
    )
    assert error.hint.startswith(
        "Tell the user about the license and, if they accept it, ask them to "
        "restart the server with `--allow-model google/timesfm-3.0`."
    )
    assert error.details["allow_model"] == "google/timesfm-3.0"
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


def test_model_policy_check_ServerError_names_gated_weights():
    """
    Test that a model with gated weights says so.
    """
    with pytest.raises(ServerError, match="gated on the Hugging Face Hub"):
        ModelPolicy().check("theforecastingcompany/t0-alpha", "estimator")
