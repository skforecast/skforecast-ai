# Unit test ModelPolicy.announce

import dataclasses
from skforecast.foundation import get_model_info

from skforecast_ai.mcp import _foundation
from skforecast_ai.mcp._foundation import MODEL_DOWNLOAD_NOTICE, ModelPolicy


def _cache(tmp_path, monkeypatch, *repo_ids):
    """
    Point the Hugging Face cache to `tmp_path / 'hf'` with a snapshot of
    each repository of `repo_ids`.
    """
    cache = tmp_path / "hf"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    for repo_id in repo_ids:
        folder = cache / ("models--" + repo_id.replace("/", "--")) / "snapshots"
        (folder / "abc123").mkdir(parents=True)
        (folder / "abc123" / "config.json").write_text("{}")


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
        "The weights of 'autogluon/chronos-2-small' were not found in the "
        "local Hugging Face cache: the first run may download them from the "
        "Hugging Face Hub. License: its license is Apache-2.0 "
        "(https://huggingface.co/autogluon/chronos-2-small)."
    )
    assert notices[1].message.endswith(
        "License: its license is timesfm-non-commercial-license-v1.0 "
        "(https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE), "
        "which restricts commercial use."
    )
    assert again == []


def test_model_policy_announce_looks_up_the_repository_of_the_weights(
    tmp_path, monkeypatch
):
    """
    Test that the cache is looked up under the repository skforecast
    registers for the weights: TabICL keeps them in 'jingang/TabICL', so a
    snapshot there counts and one under its model ID does not, and the
    notice names that repository.
    """
    _cache(tmp_path, monkeypatch, "soda-inria/tabicl")
    policy = ModelPolicy()

    (notice,) = policy.announce(policy.uncached(["soda-inria/tabicl"]))

    assert notice.message.startswith(
        "The weights of 'soda-inria/tabicl' (repository 'jingang/TabICL') were "
        "not found in the local Hugging Face cache"
    )

    _cache(tmp_path, monkeypatch, "jingang/TabICL")

    assert ModelPolicy().uncached(["soda-inria/tabicl"]) == []


def test_model_policy_announce_weights_outside_the_hf_cache(tmp_path, monkeypatch):
    """
    Test that a model whose weights skforecast does not keep in the Hugging
    Face cache (TabPFN) is announced even when its repository is in that
    cache, without saying anything about that cache or HF_HUB_OFFLINE.
    """
    _cache(tmp_path, monkeypatch, "Prior-Labs/tabpfn_3_5")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    policy = ModelPolicy(("priorlabs/tabpfn",))

    uncached = policy.uncached(["priorlabs/tabpfn-ts"])
    (notice,) = policy.announce(uncached)

    assert uncached == ["priorlabs/tabpfn-ts"]
    assert notice.message.startswith(
        "The server cannot tell whether the weights of 'priorlabs/tabpfn-ts' "
        "are already downloaded: its backend keeps them in a cache of its "
        "own, so the first run may download them. License: its license is "
        "tabpfn-3-5-license-v1.0"
    )
    assert notice.message.endswith(
        "; its provider requires its own account and accepting its license, "
        "outside the Hugging Face Hub, before the weights can be used."
    )
    assert "Hugging Face cache" not in notice.message
    assert "HF_HUB_OFFLINE" not in notice.message


def test_model_policy_announce_after_the_models_ran(tmp_path, monkeypatch):
    """
    Test that the notice of a call that already ran the model (a
    comparison) says that the download may have happened, and does not add
    the sentence of HF_HUB_OFFLINE, which is about a run to come.
    """
    _cache(tmp_path, monkeypatch)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    policy = ModelPolicy()

    notices = policy.announce(["autogluon/chronos-2-small"], ran=True)

    assert notices[0].message == (
        "The weights of 'autogluon/chronos-2-small' were not found in the "
        "local Hugging Face cache: this call may have downloaded them from "
        "the Hugging Face Hub. License: its license is Apache-2.0 "
        "(https://huggingface.co/autogluon/chronos-2-small)."
    )


def test_model_policy_announce_skips_unknown_models_without_marking_them(
    tmp_path, monkeypatch
):
    """
    Test that a model ID skforecast does not serve gives no notice and is
    not recorded as announced.
    """
    _cache(tmp_path, monkeypatch)
    policy = ModelPolicy()

    assert policy.uncached(["nobody/unknown-model"]) == []
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


def test_model_policy_announce_when_skforecast_does_not_say_where(
    tmp_path, monkeypatch
):
    """
    Test that a model whose information lacks `weights_in_hf_cache` is
    announced without claiming where its weights are kept.
    """
    info = dataclasses.replace(
        get_model_info("autogluon/chronos-2-small"), weights_in_hf_cache=None
    )
    monkeypatch.setattr(_foundation, "resolve_foundation_model", lambda _: info)
    _cache(tmp_path, monkeypatch, "autogluon/chronos-2-small")
    policy = ModelPolicy()

    (notice,) = policy.announce(policy.uncached(["autogluon/chronos-2-small"]))

    assert notice.message.startswith(
        "The server cannot tell whether the weights of "
        "'autogluon/chronos-2-small' are already downloaded: skforecast does "
        "not say where they are cached, so the first run may download them."
    )
