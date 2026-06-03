from centumhi_license import cache


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTUMHI_CACHE_DIR", str(tmp_path))
    assert cache.load("p", "k") is None
    cache.save("p", "k", {"valid": True, "x": 1})
    loaded = cache.load("p", "k")
    assert loaded["valid"] is True
    assert loaded["x"] == 1
    assert "_cached_at" in loaded


def test_cache_keys_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTUMHI_CACHE_DIR", str(tmp_path))
    cache.save("p", "k1", {"valid": True})
    assert cache.load("p", "k2") is None
