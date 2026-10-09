# Unit test is_permissive

import dataclasses
import pytest
from skforecast.foundation import get_model_info

from skforecast_ai.mcp._foundation import (
    is_permissive,
    permissive_adapters,
    restricted_adapters,
)


@pytest.mark.parametrize(
    "model_id, expected",
    [
        ("autogluon/chronos-2-small", True),
        ("google/timesfm-2.5-200m-pytorch", True),
        ("theforecastingcompany/t0-alpha", True),
        ("google/timesfm-3.0-pytorch", False),
        ("priorlabs/tabpfn-ts", False),
    ],
    ids=["chronos-2", "timesfm 2.5", "t0", "commercial use", "provider account"],
)
def test_is_permissive_from_the_information_of_skforecast(model_id, expected):
    """
    Test that a model is permissive only when its license does not restrict
    commercial use, its weights are not gated and its provider requires no
    account.
    """
    assert is_permissive(get_model_info(model_id)) is expected


def test_is_permissive_splits_the_adapters_of_skforecast():
    """
    Test the split of the adapters of the installed skforecast: Chronos-2,
    TimesFM 2.5, TabICL, Nori and T0 run without `--allow-model`; TimesFM
    3.0, Moirai, TabPFN and TS-ICL need it. A change of skforecast that
    moves an adapter fails here, so it is seen in review.
    """
    assert [info.adapter for info in permissive_adapters()] == [
        "ChronosAdapter",
        "TimesFM25Adapter",
        "TabICLAdapter",
        "T0Adapter",
        "NoriAdapter",
    ]
    assert [info.adapter for info in restricted_adapters()] == [
        "TimesFM3Adapter",
        "MoiraiAdapter",
        "TabPFNAdapter",
        "TSICLAdapter",
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"requires_hf_auth": True},
        {"requires_provider_auth": True},
        {"commercial_use_restricted": True},
        {"commercial_use_restricted": None},
        {"requires_hf_auth": None},
        {"license": ""},
        {"license": None},
    ],
    ids=lambda changes: str(changes),
)
def test_is_permissive_false_when_a_field_applies_or_is_unknown(changes):
    """
    Test that a model is not permissive when any restricting field is true,
    or when skforecast does not give it as a bool or gives no license.
    """
    info = dataclasses.replace(get_model_info("autogluon/chronos-2-small"), **changes)

    assert is_permissive(info) is False


def test_is_permissive_false_when_the_information_lacks_the_fields():
    """
    Test that a model whose information does not have the fields of
    skforecast 0.26 (an older or a different skforecast) is blocked by
    default.
    """
    @dataclasses.dataclass(frozen=True)
    class OldInfo:
        model_id: str = "autogluon/chronos-2-small"
        adapter: str = "ChronosAdapter"
        requires_hf_auth: bool = False
        license_restriction: str | None = None

    assert is_permissive(OldInfo()) is False
