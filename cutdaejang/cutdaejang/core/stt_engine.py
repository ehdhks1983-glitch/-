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


def _post_ai(url: str, payload: dict, key: str, timeout=None) -> dict:
    """🔁 제미나이 호출 (v1.27.1, 목록 53) — 모델이 퇴역했으면 자동으로 다른 모델로.

    회원님 22차: 404 "This model models/gemini-2.5-flash is no longer available to
    new users." 모델 이름을 박아 두면 구글이 퇴역시키는 날 통째로 멈춘다.
    """
    from . import gemini_models  # noqa: PLC0415

    return gemini_models.post_url(url, payload, key, timeout=timeout)



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
        except Exception as e:  # noqa: BLE001
            # 🔴 v1.35.1 (목록 71) — 설치는 됐는데 못 «불러오는» 경우가 있다.
            #   회원님 PC: ctranslate2.dll을 찾지 못해 FileNotFoundError(=OSError).
            #   ImportError가 아니라 예전엔 안 잡혔고, 그대로 위로 터졌다.
            raise STTError(
                "무료 음성인식(Whisper)을 불러오지 못했습니다 (" + type(e).__name__ + "). "
                "Visual C++ 재배포 패키지가 없거나 설치 파일이 깨진 경우입니다 — "
                "windows\\5_영상편집_음성인식설치.bat 를 다시 실행하거나, "
                "음성인식을 Gemini로 바꿔 주세요."
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
        return " ".join(t for _, _, t in self.transcribe_timed(audio_path, language)).strip()

    def transcribe_timed(self, audio_path: str, language: str = "ko") -> list:
        """문장(구) 단위 타임스탬프 전사 (v0.41, v0.76 확장).

        반환: [(시작초, 끝초, 텍스트, 단어들, 신뢰도), ...]
          단어들 = [(단어 시작초, 끝초, "단어"), ...] — 카라오케 자막·필러 컷용 (v0.76)
          신뢰도 = exp(avg_logprob) 0~1 — 검토 화면 "확인 필요" 표시용
        긴 발화 구간이 자막 한 줄로 오래 떠 있던 문제를 whisper 자체 세그먼트
        타임스탬프로 해결한다. VAD·no_speech 필터는 기존과 동일.
        """
        import math  # noqa: PLC0415

        model = self._get_model()
        # VAD로 비발화(음악·잡음) 구간을 먼저 걸러 환각 방지. no_speech_prob 높은 세그먼트도 제외.
        # beam_size=1(그리디): 기본값 5 대비 3~5배 빠름, 한국어 정확도 손실 미미.
        segments, _ = model.transcribe(
            str(audio_path), language=language, beam_size=1,
            word_timestamps=True,  # 🧹 단어 시각 — 필러 컷·카라오케 자막 (v0.76)
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
            no_speech_threshold=0.6, condition_on_previous_text=False,
        )
        out = []
        for s in segments:
            if getattr(s, "no_speech_prob", 0.0) >= 0.6:
                continue
            t = s.text.strip()
            if not t:
                continue
            words = []
            for w in (getattr(s, "words", None) or []):
                token = str(getattr(w, "word", "") or "").strip()
                if token:
                    words.append((float(w.start), float(w.end), token))
            conf = math.exp(min(0.0, float(getattr(s, "avg_logprob", 0.0) or 0.0)))
            out.append((float(s.start), float(s.end), t, words, round(conf, 3)))
        return out


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
        if "2.5" in self.model:  # 씽킹이 짧은 받아쓰기 출력을 통째로 삼키는 것 방지 (v0.50.2)
            payload["generationConfig"] = {"thinkingConfig": {"thinkingBudget": 0}}
        try:
            # v1.27.1 (목록 53): 모델이 퇴역했으면 자동으로 다른 모델로 (직접
            # urlopen 하던 것을 공용 입구로 — 그래야 모델 교체가 여기도 걸린다)
            data = _post_ai(url, payload, self.api_key, timeout=120.0)
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "status", "") or getattr(e, "code", "")
            body = (getattr(e, "text", "") or str(e))[:300]
            raise STTError(f"Gemini STT 오류 {code}: {body}") from e
        cands = data.get("candidates") or []
        parts = ((cands[0].get("content") or {}).get("parts") or []) if cands else []
        text = " ".join(p.get("text", "") for p in parts if p.get("text")).strip()
        if text:
            return text
        # 출력 없이 정상 종료(STOP) = 알아들을 말이 없는 구간 → 자막 없이 유지 (v0.50.2 —
        # 예전엔 오류로 던져 구간마다 경고가 쌓였다. 사용자 로그 8건)
        if cands and str(cands[0].get("finishReason", "")).upper() == "STOP":
            return ""
        # candidates 자체가 없음(안전 차단·쿼터) — 빈 자막이 캐시에 박히지 않게 오류로
        raise STTError(f"Gemini STT 빈 응답: {json.dumps(data)[:200]}")


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
    # 🎵 음악·효과음 캡션 태그 (v0.95) — BGM 구간을 "[음악]" 등으로 받아적는
    # 환각이 자막에 그대로 실렸다 (사용자 리포트: 자막에 '음악'이라는 단어).
    # _normalize가 괄호·공백을 벗기므로 "[음악]"·"(박수)"도 아래와 일치한다.
    "음악",
    "배경음악",
    "음악소리",
    "신나는음악",
    "잔잔한음악",
    "박수",
    "박수소리",
    "웃음",
    "웃음소리",
    "노래",
    "bgm",
    "♪",
    "♪♪",
}


def _normalize(text: str) -> str:
    return re.sub(r"[\s.,!?~…·\-\"'()\[\]]+", "", text).lower()


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

    def transcribe_timed(self, audio_path: str):
        """문장 단위 타임스탬프 전사 (v0.41, v0.76 확장).

        반환: [(시작μs, 끝μs, 텍스트, 단어들, 신뢰도), ...]
          단어들 = [(단어 시작μs, 끝μs, "단어"), ...] (조각 시작 기준 아님 — 오디오 절대)
        제공자가 지원하지 않으면(whisper 외) None을 반환해 호출자가 기존
        "구간=자막 한 줄" 방식으로 폴백한다. 환각 문구는 조각 단위로 제외.
        캐시는 .seg2.json — 단어 시각이 없는 옛 캐시(.seg.json)와 분리 (v0.76).
        """
        fn = getattr(self.provider, "transcribe_timed", None)
        if fn is None:
            return None
        cache = self._cache_path(audio_path).with_suffix(".seg2.json")
        if cache.exists():
            self.stats["cache_hits"] += 1
            return [tuple(x[:3]) + (list(map(tuple, x[3])) if len(x) > 3 else [],
                                    float(x[4]) if len(x) > 4 else 1.0,)
                    for x in json.loads(cache.read_text(encoding="utf-8"))]
        self.stats["calls"] += 1
        pieces = fn(str(audio_path), language=self.language)
        out = []
        for piece in pieces:
            start_s, end_s, text = piece[0], piece[1], piece[2]
            words = piece[3] if len(piece) > 3 else []
            conf = float(piece[4]) if len(piece) > 4 else 1.0
            text = (text or "").strip()
            if not text or is_hallucination(text):
                if text:
                    self.stats["hallucinations"] = self.stats.get("hallucinations", 0) + 1
                continue
            if end_s > start_s:
                w_us = [(int(a * 1e6), int(b * 1e6), t) for a, b, t in words if b > a]
                out.append((int(start_s * 1e6), int(end_s * 1e6), text, w_us, conf))
        if out:  # 빈 결과는 캐시하지 않음 (transcribe와 동일 정책)
            cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out


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
