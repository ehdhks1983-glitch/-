"""
tts_engine.py — 나래이션 음성 엔진
ElevenLabs(자연스러운 음성, API 키 필요) → 실패/미설정 시 시스템 음성으로 폴백.
설정은 data/tts.json 에 저장(로컬, 배포 안 됨).
"""

import json
from pathlib import Path
from typing import Optional, List

from config import DATA_DIR

TTS_FILE = DATA_DIR / "tts.json"

DEFAULTS = {
    "use_elevenlabs": False,
    "api_key": "",
    "voice_id": "",
    "model": "eleven_multilingual_v2",
    "stability": 50,       # %
    "similarity": 75,      # %
}


class TTSSettings:
    def __init__(self):
        self._d = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            if TTS_FILE.exists():
                self._d.update(json.loads(TTS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass

    def save(self):
        try:
            TTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TTS_FILE.write_text(json.dumps(self._d, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        except Exception:
            pass

    def get(self, k, default=None):
        v = self._d.get(k)
        return v if v is not None else (DEFAULTS.get(k) if default is None else default)

    def set(self, k, v):
        self._d[k] = v

    @property
    def use_elevenlabs(self) -> bool:
        return bool(self._d.get("use_elevenlabs")
                    and (self._d.get("api_key") or "").strip()
                    and (self._d.get("voice_id") or "").strip())


tts_settings = TTSSettings()


def elevenlabs_tts(text: str, out_mp3: str) -> Optional[str]:
    """ElevenLabs로 음성 생성 → mp3. 실패 시 None."""
    import urllib.request
    key = (tts_settings.get("api_key") or "").strip()
    voice = (tts_settings.get("voice_id") or "").strip()
    if not key or not voice or not (text or "").strip():
        return None
    try:
        stab = max(0, min(100, int(tts_settings.get("stability")))) / 100.0
        sim = max(0, min(100, int(tts_settings.get("similarity")))) / 100.0
        body = json.dumps({
            "text": text,
            "model_id": tts_settings.get("model") or "eleven_multilingual_v2",
            "voice_settings": {"stability": stab, "similarity_boost": sim},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            data=body, method="POST",
            headers={"xi-api-key": key, "Content-Type": "application/json",
                     "Accept": "audio/mpeg"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if not data:
            return None
        Path(out_mp3).parent.mkdir(parents=True, exist_ok=True)
        Path(out_mp3).write_bytes(data)
        return out_mp3 if Path(out_mp3).exists() and Path(out_mp3).stat().st_size > 0 else None
    except Exception:
        return None


def test_elevenlabs(api_key: str, voice_id: str, out_mp3: str,
                    model: str = "eleven_multilingual_v2") -> Optional[str]:
    """설정 창의 '테스트' 버튼용 — 임시 키/보이스로 샘플 생성."""
    prev = (tts_settings.get("api_key"), tts_settings.get("voice_id"), tts_settings.get("model"))
    tts_settings.set("api_key", api_key)
    tts_settings.set("voice_id", voice_id)
    tts_settings.set("model", model)
    try:
        return elevenlabs_tts("안녕하세요. 나래이션 음성 테스트입니다.", out_mp3)
    finally:
        tts_settings.set("api_key", prev[0])
        tts_settings.set("voice_id", prev[1])
        tts_settings.set("model", prev[2])


def list_voices(api_key: str) -> List[dict]:
    """계정의 보이스 목록 (선택). 실패 시 빈 리스트."""
    import urllib.request
    if not (api_key or "").strip():
        return []
    try:
        req = urllib.request.Request("https://api.elevenlabs.io/v1/voices",
                                     headers={"xi-api-key": api_key.strip()})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [{"name": v.get("name", ""), "voice_id": v.get("voice_id", "")}
                for v in data.get("voices", [])]
    except Exception:
        return []
