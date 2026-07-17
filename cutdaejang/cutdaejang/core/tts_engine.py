"""문장별 TTS — 429 안정화(레이트리미터·retryDelay 재시도·영구 캐시·폴백 체인) + 전처리.

패치 v0.3 (작업지시서 PATCH 1·2·6 반영):
  - 슬라이딩 윈도우 레이트리미터 (기본 8rpm — 무료 등급 한도 10의 80%)
  - 429 응답의 RetryInfo.retryDelay 준수 + 지터, 없으면 지수 백오프(4→8→16→32s)
  - 캐시 키 = SHA256(provider|model|voice|style|문장) → cache/tts/{hash}.wav 영구 보존
    (재실행 시 실패했던 문장만 API 호출)
  - 작업 단위 제공자 폴백 체인 (영상 중간에 목소리가 바뀌지 않도록 문장 단위 아님)
  - 수신 직후 전처리: 앞뒤 무음 트림(-45dB) → 10ms 페이드 → -16 LUFS → 30ms 패드
  - 보이스 스타일 프리셋(정보형/텐션형/스토리형) — Gemini 자연어 지시문
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Tuple

from .. import config
from ..utils import ffmpeg as ff
from ..utils.timefmt import US_PER_SECOND

StatusCb = Optional[Callable[[str], None]]
log = logging.getLogger("cutdaejang")


class TTSError(RuntimeError):
    pass


class TTSHTTPError(TTSError):
    """HTTP 오류 — 상태코드·파싱된 본문 유지 (재시도 판단용)."""

    def __init__(self, code: int, payload: Optional[dict], text: str):
        self.code = code
        self.payload = payload
        self.text = text
        super().__init__(f"API 오류 {code}: {text[:300]}")


class TTSNonRetryable(TTSError):
    """401/403 등 재시도해도 소용없는 오류 — 즉시 폴백 대상."""


class TTSExhausted(TTSError):
    """재시도/대기 상한 소진 — 폴백 대상."""

    def __init__(self, message: str, raw: str = ""):
        self.raw = raw  # 최종 실패 시 [자세히]로 보여줄 원본
        super().__init__(message)


# ─────────────────────────── HTTP ───────────────────────────


def _http_post_json(url: str, payload: dict, headers: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        raise TTSHTTPError(e.code, parsed, text) from e


def parse_retry_delay_s(err: TTSHTTPError) -> Optional[float]:
    """429 응답에서 서버 지정 대기시간 추출 (RetryInfo → 정규식 폴백)."""
    try:
        for detail in err.payload["error"]["details"]:
            if detail.get("@type", "").endswith("google.rpc.RetryInfo"):
                delay = detail.get("retryDelay", "")  # 예: "18.210819764s"
                m = re.match(r"([\d.]+)s", str(delay))
                if m:
                    return float(m.group(1))
    except (TypeError, KeyError):
        pass
    m = re.search(r"retry in ([\d.]+)\s*s", err.text, re.IGNORECASE)
    return float(m.group(1)) if m else None


# ─────────────────────────── 레이트리미터 ───────────────────────────


class RateLimiter:
    """슬라이딩 윈도우(60초) 레이트리미터 — 모든 API 호출 직전에 acquire."""

    def __init__(self, rpm: int, clock=time.monotonic, sleep=time.sleep):
        self.rpm = max(1, rpm)
        self._clock = clock
        self._sleep = sleep
        self._calls: deque = deque()

    def acquire(self, status_cb: StatusCb = None) -> float:
        """호출 슬롯 확보. 기다린 시간(초)을 반환."""
        waited = 0.0
        while True:
            now = self._clock()
            while self._calls and now - self._calls[0] >= 60.0:
                self._calls.popleft()
            if len(self._calls) < self.rpm:
                self._calls.append(now)
                return waited
            remain = 60.0 - (now - self._calls[0]) + 0.05
            if status_cb:
                status_cb(f"분당 한도 조절 중 — {max(1, round(remain))}초 대기")
            step = min(1.0, remain)
            self._sleep(step)
            waited += step


# ─────────────────────────── 제공자 ───────────────────────────


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, out_path: str) -> str: ...


class GeminiTTS:
    """Gemini TTS — 응답은 24kHz s16le mono PCM(base64)이며 wav로 감싼다."""

    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash-preview-tts"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise TTSError("GEMINI_API_KEY가 설정되어 있지 않습니다")

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice or "Kore"}}
                },
            },
        }
        data = _http_post_json(url, payload, {"x-goog-api-key": self.api_key})
        try:
            b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        except (KeyError, IndexError) as e:
            raise TTSError(f"Gemini TTS 응답 형식 예상 밖: {json.dumps(data)[:300]}") from e
        pcm = base64.b64decode(b64)

        import wave  # noqa: PLC0415

        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24_000)
            w.writeframes(pcm)
        return str(out_path)


class OpenAITTS:
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini-tts"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise TTSError("OPENAI_API_KEY가 설정되어 있지 않습니다")

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        try:
            return self._call(self.model, text, voice, out_path)
        except TTSHTTPError as e:
            # 모델 미지원 계정이면 tts-1로 1회 폴백 (지시서 1-4)
            if e.code in (400, 404) and self.model != "tts-1":
                return self._call("tts-1", text, voice, out_path)
            raise

    def _call(self, model: str, text: str, voice: str, out_path: str) -> str:
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=json.dumps(
                {"model": model, "input": text, "voice": voice or "nova",
                 "response_format": "wav"}
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                Path(out_path).write_bytes(resp.read())
        except urllib.error.HTTPError as e:
            text_body = e.read().decode("utf-8", "replace")
            raise TTSHTTPError(e.code, None, text_body) from e
        return str(out_path)


class ElevenLabsTTS:
    """ElevenLabs — 내 목소리 클로닝 TTS (한국어 지원, 클로닝은 유료 구독 필요).

    voice에는 클론/보이스의 voice_id를 넣는다. 응답은 mp3 → 캐시 단계에서 wav 변환.
    """

    name = "elevenlabs"

    def __init__(self, api_key: Optional[str] = None, model: str = "eleven_multilingual_v2"):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise TTSError("ELEVENLABS_API_KEY가 설정되어 있지 않습니다")

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        if not voice:
            raise TTSNonRetryable("내 목소리가 아직 등록되지 않았습니다 — [🎤 내 목소리 등록]을 먼저 해주세요")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            data=json.dumps({
                "text": text, "model_id": self.model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "xi-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                Path(out_path).write_bytes(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (401, 403):
                raise TTSNonRetryable(f"ElevenLabs 키/권한 오류 {e.code}: {body[:200]}") from e
            raise TTSHTTPError(e.code, None, body) from e
        return str(out_path)


class GPTSoVITSTTS:
    """GPT-SoVITS 로컬 API — 완전 무료·오프라인 내 목소리 (zero-shot 참조 클로닝).

    사용자가 GPT-SoVITS 통합패키지의 API 서버(api_v2.py, 기본 127.0.0.1:9880)를
    켜두면, 참조 녹음(5~10초)+그 대사만으로 내 목소리 합성. 학습은 선택(한 번만).
    """

    name = "sovits"

    def __init__(self, url: str = "", ref_audio: str = "", ref_text: str = ""):
        self.url = (url or "http://127.0.0.1:9880").rstrip("/")
        self.ref_audio = str(ref_audio or "").strip().strip('"')
        self.ref_text = (ref_text or "").strip()
        if not self.ref_audio:
            raise TTSError("내 목소리 참조 녹음이 설정되지 않았습니다 — [🎤 내 목소리 등록]에서 저장하세요")

    @property
    def cache_extra(self) -> str:
        """참조 녹음/대사가 바뀌면 목소리가 달라짐 → 캐시 키 구분자."""
        return f"{self.ref_audio}|{self.ref_text}"

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        payload = {
            "text": text, "text_lang": "ko",
            "ref_audio_path": self.ref_audio,
            "prompt_text": self.ref_text, "prompt_lang": "ko",
            "text_split_method": "cut5", "media_type": "wav",
            "streaming_mode": False,
        }
        req = urllib.request.Request(
            f"{self.url}/tts",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                Path(out_path).write_bytes(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise TTSNonRetryable(f"GPT-SoVITS 합성 실패({e.code}): {body[:250]} — "
                                  "참조 녹음 경로/대사가 맞는지 확인하세요") from e
        except urllib.error.URLError as e:
            raise TTSNonRetryable(
                "GPT-SoVITS 서버에 연결할 수 없습니다 — 통합패키지의 API 서버"
                f"(api_v2)를 먼저 실행하세요 (주소: {self.url}) / {e.reason}") from e
        if Path(out_path).stat().st_size < 1000:
            raise TTSNonRetryable("GPT-SoVITS 응답이 비어 있습니다 — 서버 콘솔의 오류를 확인하세요")
        return str(out_path)


def clone_voice(name: str, audio_path: str, api_key: str = "") -> str:
    """녹음 파일 1개로 ElevenLabs 인스턴트 보이스 클론 생성 → voice_id 반환.

    1~3분 분량의 깨끗한 낭독 녹음(mp3/wav/m4a)을 권장. 무료 등급은 클로닝 미지원.
    """
    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise TTSError("ElevenLabs API 키를 입력하세요 (elevenlabs.io에서 발급)")
    p = Path(str(audio_path).strip().strip('"'))
    if not p.is_file():
        raise TTSError(f"녹음 파일을 찾을 수 없습니다: {p}")
    if p.stat().st_size > 25 * 1024 * 1024:
        raise TTSError("녹음 파일이 너무 큽니다(25MB 초과) — 1~3분 분량이면 충분해요")
    ctype = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
             ".ogg": "audio/ogg", ".flac": "audio/flac"}.get(p.suffix.lower(), "audio/mpeg")
    boundary = f"----cutdaejang{uuid.uuid4().hex}"

    def part(headers: str, body: bytes) -> bytes:
        return f"--{boundary}\r\n{headers}\r\n\r\n".encode("utf-8") + body + b"\r\n"

    body = (
        part('Content-Disposition: form-data; name="name"', name.encode("utf-8"))
        + part(
            f'Content-Disposition: form-data; name="files"; filename="{p.name}"'
            f"\r\nContent-Type: {ctype}",
            p.read_bytes(),
        )
        + f"--{boundary}--\r\n".encode("utf-8")
    )
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices/add",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "xi-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        if e.code in (401, 403):
            raise TTSError("ElevenLabs 키가 잘못됐거나 권한이 없습니다 — 키를 확인하세요") from e
        if "subscription" in text.lower() or "upgrade" in text.lower() or e.code == 402:
            raise TTSError("이 계정 등급은 목소리 클로닝을 지원하지 않습니다 — "
                           "elevenlabs.io에서 Starter(월 $5) 이상으로 업그레이드하세요") from e
        raise TTSError(f"목소리 등록 실패({e.code}): {text[:250]}") from e
    vid = data.get("voice_id", "")
    if not vid:
        raise TTSError(f"목소리 등록 응답에 voice_id가 없습니다: {json.dumps(data)[:200]}")
    return vid


_SAPI_PS1 = r"""param($TextFile, $OutWav)
Add-Type -AssemblyName System.Speech
$text = [IO.File]::ReadAllText($TextFile, [Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$ko = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'ko*' } | Select-Object -First 1
if (-not $ko) { $s.Dispose(); exit 3 }
$s.SelectVoice($ko.VoiceInfo.Name)
$s.Rate = 0
$s.SetOutputToWaveFile($OutWav)
$s.Speak($text)
$s.Dispose()
exit 0
"""


class WindowsTTS:
    """Windows 내장 한국어 음성(SAPI) — 키·인터넷 없이 무료 (로봇톤이지만 실제 음성)."""

    name = "windows"

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        import subprocess  # noqa: PLC0415
        import sys  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        if sys.platform != "win32":
            raise TTSError("Windows 내장 음성은 Windows에서만 사용할 수 있습니다")
        with tempfile.TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / "sapi.ps1"
            txt = Path(tmp) / "text.txt"
            ps1.write_text(_SAPI_PS1, encoding="utf-8-sig")
            txt.write_text(text, encoding="utf-8")
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ps1), str(txt), str(out_path)],
                capture_output=True, timeout=120,
            )
        if proc.returncode == 3:
            raise TTSNonRetryable(
                "이 PC에 한국어 음성이 없습니다. Windows 설정 → 시간 및 언어 → 음성에서 "
                "한국어 음성을 추가하거나, Gemini API 키로 실전 모드를 사용하세요."
            )
        if proc.returncode != 0 or not Path(out_path).exists():
            raise TTSError(
                f"Windows 음성 합성 실패(rc={proc.returncode}): "
                f"{proc.stderr.decode('utf-8', 'replace')[-300:]}"
            )
        return str(out_path)


class StubTTS:
    """최종 폴백 — 문장 길이에 비례하는 사인파 톤 (파이프라인 점검용)."""

    name = "stub"

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        dur = min(10.0, max(0.8, 0.55 + 0.14 * len(text)))
        freq = 220 + (int(hashlib.sha1(text.encode()).hexdigest(), 16) % 220)
        ff.run(
            [
                ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur:.3f}",
                "-af", "volume=0.35",
                "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                "-f", "wav", str(out_path),
            ]
        )
        return str(out_path)


PROVIDERS = {"gemini": GeminiTTS, "openai": OpenAITTS, "elevenlabs": ElevenLabsTTS,
             "sovits": GPTSoVITSTTS, "windows": WindowsTTS, "stub": StubTTS}

# 보이스 스타일 프리셋 (지시서 PATCH 6) — Gemini는 자연어 지시문을 해석한다.
# ⚠ 지시문이 음성으로 읽히는지는 실키 검증 필요 — 읽히면 아래를 영어 1줄로 교체.
STYLE_INSTRUCTIONS = {
    "정보형": "차분하고 신뢰감 있는 톤으로, 약간 빠르게 또박또박 읽어줘:",
    "텐션형": "밝고 에너지 넘치는 톤으로, 리듬감 있게 읽어줘:",
    "스토리형": "낮고 몰입감 있는 톤으로, 천천히 읽어줘:",
}
# OpenAI는 지시문 미지원 → 프리셋을 보이스로 근사
OPENAI_STYLE_VOICES = {"정보형": "nova", "텐션형": "shimmer", "스토리형": "onyx"}

GEMINI_VOICES = ["Kore", "Puck", "Charon", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"]


# ─────────────────────────── 전처리 (지시서 PATCH 2) ───────────────────────────


def postprocess_clip(raw_path: str, out_wav: str, audio_cfg: dict) -> Tuple[int, int]:
    """앞뒤 무음 트림 → 10ms 에지 페이드 → -16 LUFS → 30ms 패드 → 48kHz 스테레오 wav.

    (트림 전 길이, 트림 후 길이)를 μs로 반환 — pacing 로그용.
    """
    threshold = audio_cfg.get("trim_threshold_db", -45)
    pad_s = audio_cfg.get("edge_pad_ms", 30) / 1000.0
    lufs = audio_cfg.get("lufs", -16)
    raw_us = ff.probe_duration_us(str(raw_path))

    sr = f"silenceremove=start_periods=1:start_threshold={threshold}dB"
    filters = (
        f"{sr},areverse,{sr},"
        "afade=t=in:d=0.01,areverse,afade=t=in:d=0.01,"   # 양끝 10ms 페이드 (클릭 방지)
        f"loudnorm=I={lufs}:TP=-1.5:LRA=11,"
        "aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,"
        f"adelay={audio_cfg.get('edge_pad_ms', 30)}:all=1,apad=pad_dur={pad_s}"
    )
    ff.run(
        [
            ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(raw_path),
            "-af", filters, "-c:a", "pcm_s16le", "-f", "wav", str(out_wav),
        ]
    )
    return raw_us, ff.probe_duration_us(str(out_wav))


# ─────────────────────────── 엔진 ───────────────────────────


class TTSEngine:
    def __init__(
        self,
        provider: TTSProvider,
        cache_dir,
        settings: Optional[dict] = None,
        status_cb: StatusCb = None,
        limiter: Optional[RateLimiter] = None,
        sleep=time.sleep,
    ):
        self.provider = provider
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings or config.load_settings()
        self.status_cb = status_cb
        self._sleep = sleep
        tts_cfg = self.settings["tts"]
        self.style_preset = tts_cfg.get("style_preset", "정보형")
        rate_limited = provider.name in ("gemini", "openai")
        self.limiter = limiter or (RateLimiter(tts_cfg["rpm_limit"], sleep=sleep) if rate_limited else None)
        self.stats = {"api_calls": 0, "cache_hits": 0, "trim_saved_us": 0}

    # ---------- 캐시 ----------

    def _cache_key(self, text: str, voice: str) -> str:
        model = getattr(self.provider, "model", "")
        raw = f"{self.provider.name}|{model}|{voice}|{self.style_preset}|{text}"
        # 참조 기반 제공자(SoVITS 등)는 참조가 바뀌면 다른 목소리 → 키에 반영
        extra = getattr(self.provider, "cache_extra", "")
        if extra:
            raw += f"|{extra}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def cache_path(self, text: str, voice: str) -> Path:
        return self.cache_dir / f"{self._cache_key(text, voice)}.wav"

    # ---------- 합성 ----------

    def _resolve_voice(self, voice: str) -> str:
        if voice:
            return voice
        tts_cfg = self.settings["tts"]
        if self.provider.name == "openai":
            return OPENAI_STYLE_VOICES.get(self.style_preset, tts_cfg.get("voice_openai", "nova"))
        if self.provider.name == "gemini":
            return tts_cfg.get("voice_gemini", "Kore")
        if self.provider.name == "elevenlabs":
            return tts_cfg.get("voice_elevenlabs", "")
        return ""

    def _speak_text(self, text: str) -> str:
        """Gemini에만 스타일 지시문 부착 — 지시문 + 개행 + 문장 (지시서 PATCH 6)."""
        if self.provider.name == "gemini":
            instruction = STYLE_INSTRUCTIONS.get(self.style_preset)
            if instruction:
                return f"{instruction}\n{text}"
        return text

    def _status(self, msg: str) -> None:
        if self.status_cb:
            self.status_cb(msg)

    def _wait(self, seconds: float, label: str) -> None:
        remain = seconds
        while remain > 0:
            self._status(f"{label} — {max(1, round(remain))}초 대기")
            step = min(1.0, remain)
            self._sleep(step)
            remain -= step

    def _synth_raw_with_retry(self, text: str, voice: str, raw_path: str) -> None:
        tts_cfg = self.settings["tts"]
        max_retries = tts_cfg["max_retries"]
        wait_cap = tts_cfg["retry_wait_cap_s"]
        total_wait = 0.0
        last: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            if self.limiter:
                self.limiter.acquire(status_cb=self._status)
            try:
                self.stats["api_calls"] += 1
                self.provider.synthesize(self._speak_text(text), voice, raw_path)
                return
            except TTSNonRetryable:
                raise
            except TTSHTTPError as e:
                last = e
                if e.code in (401, 403):
                    raise TTSNonRetryable(
                        f"{self.provider.name} 인증 실패({e.code}) — API 키를 확인하세요"
                    ) from e
                if e.code != 429 and e.code < 500:
                    raise  # 4xx 기타는 재시도 무의미
                if attempt >= max_retries:
                    break
                delay = parse_retry_delay_s(e) if e.code == 429 else None
                if delay is None:
                    delay = min(4 * (2**attempt), 32)  # 4→8→16→32
                delay += random.uniform(1.0, 2.0)  # 지터
                if total_wait + delay > wait_cap:
                    raise TTSExhausted(
                        f"{self.provider.name} TTS 대기 상한({wait_cap}s) 초과", raw=e.text
                    ) from e
                total_wait += delay
                label = (
                    f"{self.provider.name} 분당 한도 초과 — 자동 재시도 ({attempt + 1}/{max_retries})"
                    if e.code == 429
                    else f"{self.provider.name} 일시 오류({e.code}) — 재시도 ({attempt + 1}/{max_retries})"
                )
                self._wait(delay, label)
            except (TTSError, ff.FFmpegError) as e:
                last = e
                if attempt >= max_retries:
                    break
                self._wait(2.0, f"{self.provider.name} 오류 — 재시도 ({attempt + 1}/{max_retries})")

        raw = getattr(last, "text", "") or str(last)
        raise TTSExhausted(
            f"{self.provider.name} TTS 재시도 {max_retries}회 소진: {str(last)[:160]}", raw=raw
        )

    def synth_sentence(self, text: str, voice: str = "") -> Path:
        voice = self._resolve_voice(voice)
        out = self.cache_path(text, voice)
        if out.exists():
            self.stats["cache_hits"] += 1
            return out
        raw = out.with_suffix(".raw.wav")
        try:
            self._synth_raw_with_retry(text, voice, str(raw))
            raw_us, final_us = postprocess_clip(str(raw), str(out), self.settings["audio"])
            self.stats["trim_saved_us"] += max(0, raw_us - final_us)
        finally:
            raw.unlink(missing_ok=True)
        return out

    def synth_all(
        self,
        sentences: List[str],
        voice: str = "",
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        paths = []
        for i, text in enumerate(sentences):
            try:
                paths.append(self.synth_sentence(text, voice))
            except TTSExhausted as e:
                raise TTSExhausted(f"문장 {i + 1}: {e}", raw=e.raw) from e
            if on_progress:
                on_progress(i + 1, len(sentences))
        saved = self.stats["trim_saved_us"] / US_PER_SECOND
        self._status(
            f"TTS 완료 — API {self.stats['api_calls']}회, 캐시 {self.stats['cache_hits']}회, "
            f"무음 트림 {saved:.1f}초 단축"
        )
        return paths


# ─────────────────────────── 폴백 체인 (지시서 1-4) ───────────────────────────


def make_provider(name: str, settings: dict) -> TTSProvider:
    tts_cfg = settings["tts"]
    if name == "gemini":
        return GeminiTTS(model=tts_cfg.get("model_gemini", "gemini-2.5-flash-preview-tts"))
    if name == "openai":
        return OpenAITTS(model=tts_cfg.get("model_openai", "gpt-4o-mini-tts"))
    if name == "elevenlabs":
        return ElevenLabsTTS(model=tts_cfg.get("model_elevenlabs", "eleven_multilingual_v2"))
    if name == "sovits":
        return GPTSoVITSTTS(url=tts_cfg.get("sovits_url", ""),
                            ref_audio=tts_cfg.get("sovits_ref_audio", ""),
                            ref_text=tts_cfg.get("sovits_ref_text", ""))
    return PROVIDERS[name]()


def synth_with_fallback(
    sentences: List[str],
    chain: List[str],
    cache_root,
    settings: Optional[dict] = None,
    voice: str = "",
    status_cb: StatusCb = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    providers: Optional[dict] = None,  # 테스트 주입용
) -> Tuple[List[Path], str, Optional[str]]:
    """체인 순서대로 시도, 실패 시 '작업 전체'를 다음 제공자로 재생성.

    반환: (클립 경로들, 사용된 제공자, 폴백 사유 또는 None)
    """
    settings = settings or config.load_settings()
    import sys  # noqa: PLC0415

    full_chain = list(chain)
    final = "windows" if sys.platform == "win32" else "stub"
    if final not in full_chain:
        full_chain.append(final)
    if "stub" not in full_chain:
        full_chain.append("stub")

    reason = None
    for name in full_chain:
        try:
            provider = (providers or {}).get(name) or make_provider(name, settings)
        except TTSError as e:  # 키 없음 등 — 다음 제공자로
            reason = f"{name} 사용 불가: {e}"
            log.warning("TTS %s", reason)
            if status_cb:
                status_cb(reason)
            continue
        engine = TTSEngine(provider, Path(cache_root), settings=settings, status_cb=status_cb)
        try:
            paths = engine.synth_all(sentences, voice=voice, on_progress=on_progress)
            log.info("TTS %s로 %d문장 합성 완료", name, len(sentences))
            return paths, name, reason
        except (TTSNonRetryable, TTSExhausted) as e:
            reason = f"{name} 실패 → 다음 제공자로 폴백: {str(e)[:200]}"
            log.warning("TTS %s", reason)
            if status_cb:
                status_cb(reason)
            continue
    raise TTSError(f"모든 TTS 제공자 실패 (체인: {full_chain}) — 마지막 사유: {reason}")
