"""음성 인식(STT) — 발화 구간 오디오 → 자막 텍스트 (기획안 v1.5 육성 촬영 모드).

인터페이스: transcribe(audio_path, language) → str. 타이밍은 video_editor의 무음 감지에서
오므로 STT는 "이 구간이 무슨 말인지"만 담당한다(타임스탬프 불필요) → 제공자 교체가 쉽다.

제공자:
  - FasterWhisperSTT: 로컬(무료·오프라인). 최초 1회 모델 다운로드 필요.
  - GeminiSTT: 사용자 Gemini 키로 오디오 전사 (설치 불필요).
  - OpenAISTT: whisper-1.
  - StubSTT: 오프라인 테스트용 고정 텍스트.
결과는 (제공자|모델|오디오해시) 기준 캐싱 → 재실행 시 재전사 안 함.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Protocol

from ..utils import ffmpeg as ff


class STTError(RuntimeError):
    pass


class STTProvider(Protocol):
    name: str

    def transcribe(self, audio_path: str, language: str = "ko") -> str: ...


class FasterWhisperSTT:
    """로컬 Whisper (faster-whisper). 모델은 최초 1회 다운로드되어 캐시됨."""

    name = "whisper"
    _model = None
    _model_size = None

    def __init__(self, model_size: str = "small"):
        self.model_size = model_size

    def _get_model(self):
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415
        except ImportError as e:
            raise STTError(
                "faster-whisper가 설치되어 있지 않습니다. `pip install faster-whisper` 하거나 "
                "Gemini/OpenAI 음성인식을 사용하세요."
            ) from e
        # 클래스 레벨 캐시 (같은 모델 재사용)
        if FasterWhisperSTT._model is None or FasterWhisperSTT._model_size != self.model_size:
            import os as _os  # noqa: PLC0415

            FasterWhisperSTT._model = WhisperModel(
                self.model_size, device="cpu", compute_type="int8",
                cpu_threads=_os.cpu_count() or 4,  # CPU 코어 전부 사용 (속도↑)
            )
            FasterWhisperSTT._model_size = self.model_size
        return FasterWhisperSTT._model

    def transcribe(self, audio_path: str, language: str = "ko") -> str:
        model = self._get_model()
        # VAD로 비발화(음악·잡음) 구간을 먼저 걸러 환각 방지. no_speech_prob 높은 세그먼트도 제외.
        # beam_size=1(그리디): 기본값 5 대비 3~5배 빠름, 한국어 정확도 손실 미미.
        segments, _ = model.transcribe(
            str(audio_path), language=language, beam_size=1,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
            no_speech_threshold=0.6, condition_on_previous_text=False,
        )
        kept = [s.text.strip() for s in segments if getattr(s, "no_speech_prob", 0.0) < 0.6]
        return " ".join(t for t in kept if t).strip()


class GeminiSTT:
    """Gemini 오디오 전사 — 사용자 키로 설치 없이. wav를 inlineData로 전송."""

    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise STTError("GEMINI_API_KEY가 설정되어 있지 않습니다")

    def transcribe(self, audio_path: str, language: str = "ko") -> str:
        audio_b64 = base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "이 오디오에서 사람이 말한 내용을 한국어로 정확히 받아써 주세요. "
                                "설명·따옴표 없이 발화 텍스트만 출력하세요. 말이 없으면 빈 줄."
                            )
                        },
                        {"inlineData": {"mimeType": "audio/wav", "data": audio_b64}},
                    ]
                }
            ]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            raise STTError(f"Gemini STT 오류 {e.code}: {body}") from e
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            # 200이지만 candidates 없음(안전 차단·쿼터) — 빈 자막이 캐시에 박히지 않게 오류로
            raise STTError(f"Gemini STT 빈 응답: {json.dumps(data)[:200]}") from None  # 무음/인식 실패 → 빈 자막 (구간은 유지)


class OpenAISTT:
    """OpenAI whisper-1 전사 (multipart/form-data)."""

    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise STTError("OPENAI_API_KEY가 설정되어 있지 않습니다")

    def transcribe(self, audio_path: str, language: str = "ko") -> str:
        boundary = f"----cutdaejangSTT{uuid.uuid4().hex}"
        audio = Path(audio_path).read_bytes()
        parts = []
        for name, value in (("model", self.model), ("language", language),
                            ("response_format", "text")):
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
            )
        head = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
        )
        body = (
            "".join(parts).encode("utf-8")
            + head.encode("utf-8") + audio + f"\r\n--{boundary}--\r\n".encode("utf-8")
        )
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8").strip()
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")[:300]
            raise STTError(f"OpenAI STT 오류 {e.code}: {body_txt}") from e


class StubSTT:
    """오프라인 테스트용 — 오디오 길이에 비례한 자리표시 텍스트."""

    name = "stub"

    def transcribe(self, audio_path: str, language: str = "ko") -> str:
        dur = ff.probe_duration_us(str(audio_path)) / 1_000_000
        words = max(1, round(dur * 2))
        return " ".join(["샘플자막"] * words)


PROVIDERS = {
    "whisper": FasterWhisperSTT,
    "gemini": GeminiSTT,
    "openai": OpenAISTT,
    "stub": StubSTT,
}

# 음성인식이 무음·음악 구간에서 흔히 지어내는 환각 문구(유튜브 자막 학습 흔적).
# 정규화(공백·문장부호 제거) 후 이 목록과 일치하면 자막에서 제외한다.
_HALLUCINATION_PHRASES = {
    "시청해주셔서감사합니다",
    "시청해주셔서감사합니다다음영상에서만나요",
    "지금까지시청해주셔서감사합니다",
    "구독과좋아요부탁드립니다",
    "구독과좋아요알림설정까지부탁드립니다",
    "좋아요와구독부탁드립니다",
    "다음영상에서만나요",
    "다음시간에만나요",
    "한글자막",
    "엠비씨뉴스",
    "감사합니다시청해주셔서감사합니다",
}


def _normalize(text: str) -> str:
    return re.sub(r"[\s.,!?~…·\-\"'()\[\]]+", "", text)


def is_hallucination(text: str) -> bool:
    """무음/음악에서 지어낸 환각 문구인지 (정규화 후 denylist 대조)."""
    norm = _normalize(text)
    if not norm:
        return True
    if norm in _HALLUCINATION_PHRASES:
        return True
    # "시청해주셔서 감사합니다"류가 포함되며 짧으면 환각으로 간주
    return "시청해주셔서감사" in norm and len(norm) <= 20


class STTEngine:
    def __init__(self, provider: STTProvider, cache_dir, language: str = "ko"):
        self.provider = provider
        self.language = language
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {"calls": 0, "cache_hits": 0, "hallucinations": 0}

    def _cache_path(self, audio_path: str) -> Path:
        h = hashlib.sha256()
        h.update(f"{self.provider.name}|{getattr(self.provider, 'model', '')}|{self.language}|".encode())
        with open(audio_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return self.cache_dir / f"{h.hexdigest()}.txt"

    def transcribe(self, audio_path: str) -> str:
        cache = self._cache_path(audio_path)
        if cache.exists():
            self.stats["cache_hits"] += 1
            return cache.read_text(encoding="utf-8")
        self.stats["calls"] += 1
        text = self.provider.transcribe(str(audio_path), language=self.language)
        # 환각 문구(무음/음악에서 지어낸 말)는 빈 자막으로 처리 → 없는 자막 방지
        if is_hallucination(text):
            self.stats["hallucinations"] = self.stats.get("hallucinations", 0) + 1
            text = ""
        if text.strip():  # 빈 결과는 캐시하지 않음 — 일시 오류가 영구 빈 자막이 되지 않게
            cache.write_text(text, encoding="utf-8")
        return text


def make_provider(name: str, edit_cfg: Optional[dict] = None) -> STTProvider:
    """edit_cfg = settings['edit'] (whisper_model, model_gemini 등)."""
    edit_cfg = edit_cfg or {}
    if name == "whisper":
        return FasterWhisperSTT(model_size=edit_cfg.get("whisper_model", "small"))
    if name == "gemini":
        return GeminiSTT(model=edit_cfg.get("model_gemini", "gemini-2.5-flash"))
    if name == "openai":
        return OpenAISTT()
    return StubSTT()
