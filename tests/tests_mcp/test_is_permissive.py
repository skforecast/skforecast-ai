# Unit test is_permissive

import dataclasses
import pytest
from skforecast.foundation import get_model_info

from skforecast_ai.mcp._foundation import (
    REVIEWED_ADAPTERS,
    is_permissive,
    permissive_adapters,
    restricted_adapters,
)


@pytest.mark.parametrize(
    "model_id, expected",
    [
        ("autogluon/chronos-2-small", True),
        ("google/timesfm-2.5-200m-pytorch", True),
        ("google/timesfm-3.0-pytorch", False),
        ("theforecastingcompany/t0-alpha", False),
    ],
    ids=["chronos-2", "timesfm 2.5", "license restriction", "gated weights"],
)
def test_is_permissive_license_and_gated_weights(model_id, expected):
    """
    Test that a model is permissive only without a license restriction and
    without gated weights.
    """
    assert is_permissive(get_model_info(model_id)) is expected


def test_is_permissive_splits_the_adapters_of_skforecast():
    """
    Test that the adapters split, from the information skforecast
    registers, into Chronos-2, TimesFM 2.5, TabICL and Nori (permissive) and
    TimesFM 3.0, Moirai, TabPFN, t0 and TS-ICL (restricted).
    """
    assert [info.adapter for info in permissive_adapters()] == [
        "ChronosAdapter",
        "TimesFM25Adapter",
        "TabICLAdapter",
        "NoriAdapter",
    ]
    assert [info.adapter for info in restricted_adapters()] == [
        "TimesFM3Adapter",
        "MoiraiAdapter",
        "TabPFNAdapter",
        "T0Adapter",
        "TSICLAdapter",
    ]


def test_is_permissive_false_for_an_adapter_not_reviewed():
    """
    Test that a model of an adapter outside `REVIEWED_ADAPTERS` is not
    permissive although skforecast registers no restriction for it: a later
    skforecast may add an adapter whose license was never checked here, and
    None does not confirm that a license permits every use.
    """
    info = dataclasses.replace(
        get_model_info("autogluon/chronos-2-small"), adapter="NewAdapter"
    )

    assert info.license_restriction is None
    assert info.requires_hf_auth is False
    assert is_permissive(info) is False
    assert REVIEWED_ADAPTERS == {
        "ChronosAdapter", "TimesFM25Adapter", "TabICLAdapter", "NoriAdapter"
    }
