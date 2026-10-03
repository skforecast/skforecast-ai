# Unit test weights_cached

from skforecast_ai.mcp._foundation import weights_cached


def test_weights_cached_needs_a_snapshot(tmp_path, monkeypatch):
    """
    Test that a model counts as cached only when its folder of the cache
    holds a snapshot, and that a model ID with a NUL byte is not cached
    rather than an error.
    """
    cache = tmp_path / "hf"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    (cache / "models--soda-inria--tabicl" / "snapshots" / "abc").mkdir(parents=True)
    (cache / "models--Synthefy--Nori" / "snapshots").mkdir(parents=True)

    assert weights_cached("soda-inria/tabicl")
    assert not weights_cached("Synthefy/Nori")
    assert not weights_cached("autogluon/chronos-2-small")
    assert not weights_cached("soda-inria/tab\x00icl")
