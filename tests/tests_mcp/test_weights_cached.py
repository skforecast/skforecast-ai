# Unit test weights_cached

from skforecast_ai.mcp._foundation import weights_cached


def test_weights_cached_needs_a_snapshot(tmp_path, monkeypatch):
    """
    Test that a repository counts as cached only when its folder of the cache
    holds a snapshot with a file in it (an interrupted download leaves an
    empty one), and that a model ID with a NUL byte is not cached rather
    than an error.
    """
    cache = tmp_path / "hf"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    snapshot = cache / "models--soda-inria--tabicl" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    (cache / "models--Synthefy--Nori" / "snapshots").mkdir(parents=True)
    empty = cache / "models--google--timesfm-2.5-200m-pytorch" / "snapshots" / "abc"
    empty.mkdir(parents=True)

    assert weights_cached("soda-inria/tabicl")
    assert not weights_cached("Synthefy/Nori")
    assert not weights_cached("google/timesfm-2.5-200m-pytorch")
    assert not weights_cached("autogluon/chronos-2-small")
    assert not weights_cached("soda-inria/tab\x00icl")
