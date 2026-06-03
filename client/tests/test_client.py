import hashlib
import hmac
import json
import time

import pytest
import requests

from centumhi_license import cache
from centumhi_license.client import LicenseClient


class FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload).encode()

    def json(self):
        return self._payload


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTUMHI_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(time, "sleep", lambda *_: None)  # no backoff delay in tests
    return LicenseClient(
        "centum-writer", "secret123", "http://server", hwid="HW-TEST", retries=3
    )


def test_signature_matches_hmac(client):
    expected = hmac.new(b"secret123", b"K|HW-TEST|123", hashlib.sha256).hexdigest()
    assert client._sign("K", "HW-TEST", "123") == expected


def test_activate_success_signs_and_caches(client, monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["body"] = json
        return FakeResp(
            {
                "valid": True,
                "plan_type": "monthly_30",
                "expires_at": "2026-07-03T00:00:00Z",
                "days_remaining": 30,
                "status": "active",
                "max_hwid_count": 1,
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)
    result = client.verify_or_activate("  CW-M30-AAA  ")  # also tests stripping

    assert result.valid is True
    assert result.days_remaining == 30
    assert result.plan_type == "monthly_30"
    assert captured["url"].endswith("/api/verify/activate")
    assert captured["body"]["license_key"] == "CW-M30-AAA"
    assert len(captured["body"]["signature"]) == 64
    # a valid result is cached for offline grace
    assert cache.load("centum-writer", "CW-M30-AAA")["valid"] is True


def test_error_envelope_becomes_invalid(client, monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: FakeResp({"error_code": "invalid_signature", "message": "서명 검증 실패"}),
    )
    result = client.check("CW-M30-AAA")
    assert result.valid is False
    assert "서명" in result.reason


def test_offline_fallback_uses_valid_cache(client, monkeypatch):
    cache.save(
        "centum-writer",
        "CW-M30-AAA",
        {"valid": True, "plan_type": "unlimited", "status": "active"},
    )

    def boom(*a, **k):
        raise requests.ConnectionError("server down")

    monkeypatch.setattr(requests, "post", boom)
    result = client.check("CW-M30-AAA")
    assert result.valid is True
    assert result.offline is True


def test_offline_fallback_rejects_expired_cache(client, monkeypatch):
    cache.save("centum-writer", "CW-M30-OLD", {"valid": True})
    path = cache._cache_file("centum-writer", "CW-M30-OLD")
    data = json.loads(path.read_text())
    data["_cached_at"] = int(time.time()) - 100 * 86400  # well past 7-day grace
    path.write_text(json.dumps(data))

    def boom(*a, **k):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(requests, "post", boom)
    result = client.check("CW-M30-OLD")
    assert result.valid is False
    assert result.offline is True


def test_network_error_retries_then_falls_back(client, monkeypatch):
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise requests.Timeout("t")

    monkeypatch.setattr(requests, "post", boom)
    result = client.check("NO-CACHE-KEY")
    assert result.valid is False
    assert result.offline is True
    assert calls["n"] == 3  # retried `retries` times
