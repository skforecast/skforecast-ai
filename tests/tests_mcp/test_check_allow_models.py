# Unit test check_allow_models

import re
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp._foundation import check_allow_models


def test_check_allow_models_keeps_prefixes_of_adapters_without_repetitions():
    """
    Test that prefixes that start with the model ID prefix of an adapter of
    skforecast (the prefix itself or a whole model ID) are kept, in order and
    without repetitions.
    """
    prefixes = check_allow_models(
        ["google/timesfm-3.0", "taharnbl/TS-ICL", "google/timesfm-3.0"]
    )

    assert prefixes == ("google/timesfm-3.0", "taharnbl/TS-ICL")
    assert check_allow_models(["Salesforce/moirai-2.0-R-small"]) == (
        "Salesforce/moirai-2.0-R-small",
    )
    assert check_allow_models([]) == ()


@pytest.mark.parametrize(
    "prefix",
    ["google/", "google/timesfm", "", "openai/gpt"],
    ids=["owner only", "shorter than the adapter", "empty", "unknown"],
)
def test_check_allow_models_InvalidInputError_when_not_an_adapter_prefix(prefix):
    """
    Test that a prefix shorter than the prefix of an adapter, which would
    allow more than one family of models, or of no adapter is rejected.
    """
    err_msg = re.escape(
        f"`--allow-model {prefix}` does not start with the model ID prefix of a "
        f"foundation model of skforecast."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as info:
        check_allow_models([prefix])

    assert info.value.field == "allow_model"
