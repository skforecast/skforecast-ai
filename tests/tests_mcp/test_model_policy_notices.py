# Unit test ModelPolicy.notices

from skforecast_ai.mcp._foundation import (
    MODEL_DOWNLOAD_NOTICE,
    MODEL_LICENSE_NOTICE,
    ModelPolicy,
)
from skforecast_ai.mcp.models import ToolNotice


def test_model_policy_notices_license_of_every_foundation_model(
    tmp_path, monkeypatch
):
    """
    Test that every foundation model of a response gets one notice with the
    license skforecast registers: the announcement of its download when its
    weights are not in the cache, and a `ModelLicenseNotice` otherwise (a
    cached model, or one already announced). None, a repeated model and a
    model skforecast does not serve get none.
    """
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    policy = ModelPolicy()
    models = [
        "autogluon/chronos-2-small",
        None,
        "Synthefy/Nori",
        "autogluon/chronos-2-small",
        "unknown/model",
    ]

    first = policy.notices(models, uncached=["autogluon/chronos-2-small"])
    second = policy.notices(models, uncached=policy.uncached(models))

    assert [notice.category for notice in first] == [
        MODEL_DOWNLOAD_NOTICE,
        MODEL_LICENSE_NOTICE,
    ]
    assert "its license is Apache-2.0" in first[0].message
    assert first[1] == ToolNotice(
        source   = "plan",
        category = "ModelLicenseNotice",
        message  = (
            "Foundation model 'Synthefy/Nori'. License (by the name of the "
            "model, as skforecast registers it): its license is Apache-2.0 "
            "(https://huggingface.co/Synthefy/Nori)."
        ),
        count    = 1,
    )
    assert [(notice.category, notice.message) for notice in second] == [
        (
            "ModelLicenseNotice",
            "Foundation model 'autogluon/chronos-2-small'. License (by the "
            "name of the model, as skforecast registers it): its license is "
            "Apache-2.0 (https://huggingface.co/autogluon/chronos-2-small).",
        ),
        ("ModelDownloadNotice", second[1].message),
    ]
    assert "'Synthefy/Nori'" in second[1].message


def test_model_policy_notices_restricted_license():
    """
    Test that the license notice of a model with a restricted license says
    that it restricts commercial use.
    """
    policy = ModelPolicy(("google/timesfm-3.0",))

    notices = policy.notices(["google/timesfm-3.0-pytorch"])

    assert [notice.category for notice in notices] == ["ModelLicenseNotice"]
    assert notices[0].message == (
        "Foundation model 'google/timesfm-3.0-pytorch'. License (by the name "
        "of the model, as skforecast registers it): its license is "
        "timesfm-non-commercial-license-v1.0 "
        "(https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE), "
        "which restricts commercial use."
    )


def test_model_policy_notices_empty_without_foundation_models():
    """
    Test that a response without foundation models gets no notice.
    """
    assert ModelPolicy().notices([None, None]) == []
