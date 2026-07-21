"""v0.65 — 🇰🇷 한국어 성우 담기: shared-voices 조회·add 담기 (네트워크 모킹)."""

import io
import json
import urllib.error

import pytest

from cutdaejang.core import tts_engine as te


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_list_shared_voices_maps_fields(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["key"] = req.headers.get("Xi-api-key")
        return _Resp({"voices": [
            {"voice_id": "v1", "public_owner_id": "o1", "name": "Anna Kim",
             "gender": "female", "age": "young", "use_case": "narration",
             "descriptive": "calm", "preview_url": "http://x/p.mp3",
             "free_users_allowed": True},
            {"voice_id": "no_owner"},  # public_owner_id 없음 → 담기 불가라 제외
        ]})

    monkeypatch.setattr(te.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
    rows = te.list_shared_voices()
    assert "shared-voices" in seen["url"] and "language=ko" in seen["url"]
    assert seen["key"] == "sk_test"
    assert rows == [{
        "voice_id": "v1", "owner_id": "o1", "name": "Anna Kim",
        "desc": "female · young · narration · calm",
        "preview_url": "http://x/p.mp3", "free_ok": True,
    }]

    monkeypatch.delenv("ELEVENLABS_API_KEY")
    with pytest.raises(te.TTSError):
        te.list_shared_voices()


def test_add_shared_voice_and_slot_limit(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp({"voice_id": "new_vid"})

    monkeypatch.setattr(te.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
    vid = te.add_shared_voice("o1", "v1", "Anna Kim")
    assert vid == "new_vid"
    assert seen["url"].endswith("/v1/voices/add/o1/v1")
    assert seen["body"] == {"new_name": "Anna Kim"}

    # 슬롯 초과는 사람이 읽을 한국어 안내로 바뀐다
    def fake_limit(req, timeout=0):
        raise urllib.error.HTTPError(
            req.full_url, 400, "bad", None,
            io.BytesIO(b'{"detail":{"status":"voice_limit_reached"}}'))

    monkeypatch.setattr(te.urllib.request, "urlopen", fake_limit)
    with pytest.raises(te.TTSError) as ei:
        te.add_shared_voice("o1", "v1", "Anna Kim")
    assert "슬롯" in str(ei.value)
