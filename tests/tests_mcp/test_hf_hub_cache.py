# Unit test hf_hub_cache

import os

from skforecast_ai.mcp._foundation import hf_hub_cache


def test_hf_hub_cache_resolution_order(tmp_path, monkeypatch):
    """
    Test that the cache directory is resolved as huggingface_hub does:
    HF_HUB_CACHE, then HUGGINGFACE_HUB_CACHE, then HF_HOME/hub, then
    XDG_CACHE_HOME/huggingface/hub.
    """
    for name in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    xdg = hf_hub_cache()
    monkeypatch.setenv("HF_HOME", str(tmp_path / "home"))
    home = hf_hub_cache()
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(tmp_path / "old"))
    old = hf_hub_cache()
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "new"))
    new = hf_hub_cache()

    assert xdg == os.path.join(str(tmp_path / "xdg"), "huggingface", "hub")
    assert home == os.path.join(str(tmp_path / "home"), "hub")
    assert (old, new) == (str(tmp_path / "old"), str(tmp_path / "new"))
