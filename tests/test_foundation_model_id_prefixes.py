# Unit test FOUNDATION_MODEL_ID_PREFIXES

from skforecast.foundation import list_adapters

from skforecast_ai._constants import FOUNDATION_MODEL_ID_PREFIXES


def test_foundation_model_id_prefixes_are_those_of_skforecast():
    """
    Test that the copy of the model ID prefixes of the foundation adapters,
    written out so the MCP server builds the schemas of its tools without
    importing skforecast, holds the prefixes of `list_adapters()` of the
    installed skforecast, in its order. A new adapter of skforecast fails
    here until the constant is updated. The expected value is read from
    skforecast, not hardcoded, because keeping the two equal is what this
    test is for.
    """
    expected = tuple(
        prefix for info in list_adapters() for prefix in info.model_id_prefixes
    )

    assert FOUNDATION_MODEL_ID_PREFIXES == expected
