# Unit test ModelPolicy.announce

from skforecast_ai.mcp._foundation import MODEL_DOWNLOAD_NOTICE, ModelPolicy


def _cache(tmp_path, monkeypatch, *model_ids):
    """
    Point the Hugging Face cache to `tmp_path / 'hf'` with a snapshot of
    each model of `model_ids`.
    """
    cache = tmp_path / "hf"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    for model_id in model_ids:
        folder = cache / ("models--" + model_id.replace("/", "--")) / "snapshots"
        (folder / "abc123").mkdir(parents=True)


def test_model_policy_announce_once_the_models_not_cached(tmp_path, monkeypatch):
    """
    Test that `uncached` lists the models without weights in the cache, in
    order and without repetitions, that each is announced once with source
    'plan', the category of the server and its license, and that a cached
    model is never announced.
    """
    _cache(tmp_path, monkeypatch, "Synthefy/Nori")
    policy = ModelPolicy(("google/timesfm-3.0",))
    models = ["autogluon/chronos-2-small", None, "Synthefy/Nori",
              "autogluon/chronos-2-small", "google/timesfm-3.0-pytorch"]

    uncached = policy.uncached(models)
    notices = policy.announce(uncached)
    again = policy.announce(policy.uncached(models))

    assert uncached == ["autogluon/chronos-2-small", "google/timesfm-3.0-pytorch"]
    assert [notice.source for notice in notices] == ["plan", "plan"]
    assert [notice.category for notice in notices] == [MODEL_DOWNLOAD_NOTICE] * 2
    assert notices[0].message == (
        "The weights of 'autogluon/chronos-2-small' are not in the local "
        "Hugging Face cache: the first run downloads them from the Hugging "
        "Face Hub. License: skforecast registers no license restriction for it."
    )
    assert "License: its license is TimesFM Non-Commercial" in notices[1].message
    assert again == []


def test_model_policy_announce_skips_unknown_models_without_marking_them(
    tmp_path, monkeypatch
):
    """
    Test that a model ID skforecast does not serve gives no notice and is
    not recorded as announced.
    """
    _cache(tmp_path, monkeypatch)
    policy = ModelPolicy()

    assert policy.announce(["nobody/unknown-model"]) == []
    assert policy.announced == set()


def test_model_policy_announce_says_when_hf_hub_offline(tmp_path, monkeypatch):
    """
    Test that with HF_HUB_OFFLINE set the notice says the run fails until
    the weights are in the cache.
    """
    _cache(tmp_path, monkeypatch)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    policy = ModelPolicy()

    (notice,) = policy.announce(policy.uncached(["autogluon/chronos-2-small"]))

    assert notice.message.endswith(
        "HF_HUB_OFFLINE is set, so they cannot be downloaded and the run fails "
        "until they are in the cache."
    )
