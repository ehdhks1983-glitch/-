"""문장별 TTS 생성 + 캐싱 (기획안 §5.2, §4).

제공자 추상화: Gemini TTS(1순위) · OpenAI TTS(2순위) · Stub(오프라인 테스트용).
합성 결과는 공통 후처리(-16 LUFS 정규화 → AAC 192k m4a)를 거치고,
문장 해시(제공자|보이스|본문) 기준으로 캐싱해 재생성 비용을 없앤다.
자동 모드 실패 정책(§5.6): 문장별 재시도 2회 후 작업 실패 처리.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from ..utils import ffmpeg as ff


class TTSError(RuntimeError):
    pass


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        """text를 합성해 out_path(임의 포맷 오디오 파일)에 기록하고 경로를 반환."""
        ...


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
        body = e.read().decode("utf-8", "replace")[:500]
        raise TTSError(f"API 오류 {e.code}: {body}") from e


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

        wav_path = str(out_path) + ".wav"
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24_000)
            w.writeframes(pcm)
        os.replace(wav_path, out_path)
        return str(out_path)


class OpenAITTS:
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini-tts"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise TTSError("OPENAI_API_KEY가 설정되어 있지 않습니다")

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=json.dumps(
                {
                    "model": self.model,
                    "input": text,
                    "voice": voice or "alloy",
                    "response_format": "wav",
                }
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
            body = e.read().decode("utf-8", "replace")[:500]
            raise TTSError(f"OpenAI TTS 오류 {e.code}: {body}") from e
        return str(out_path)


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
    """Windows 내장 한국어 음성(SAPI) — API 키·인터넷 없이 무료로 실제 음성 생성.

    품질은 클라우드 TTS보다 낮지만(로봇톤), 키 없이도 '말하는 영상'이 나오게 하는
    기본 경로. 한국어 Windows 10/11에는 보통 Microsoft Heami가 설치되어 있다.
    """

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
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(ps1), str(txt), str(out_path),
                ],
                capture_output=True, timeout=120,
            )
        if proc.returncode == 3:
            raise TTSError(
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
    """오프라인 대역 — 문장 길이에 비례하는 사인파 톤 생성 (API 키 없이 파이프라인 검증용)."""

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
                "-f", "wav", str(out_path),  # 확장자 무관 컨테이너 명시
            ]
        )
        return str(out_path)


PROVIDERS = {
    "gemini": GeminiTTS,
    "openai": OpenAITTS,
    "windows": WindowsTTS,
    "stub": StubTTS,
}


class TTSEngine:
    def __init__(self, provider: TTSProvider, cache_dir):
        self.provider = provider
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, text: str, voice: str) -> str:
        raw = f"{self.provider.name}|{voice}|v1|{text}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def synth_sentence(self, text: str, voice: str = "") -> Path:
        """문장 1개 → 정규화된 m4a (캐시 적중 시 즉시 반환)."""
        out = self.cache_dir / f"{self._cache_key(text, voice)}.m4a"
        if out.exists():
            return out
        raw = self.cache_dir / (out.stem + ".raw-audio")
        self.provider.synthesize(text, voice, str(raw))
        try:
            # 공통 후처리: -16 LUFS 정규화 + 48kHz 스테레오 AAC 192k (기획안 §5.2)
            ff.run(
                [
                    ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(raw),
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k",
                    str(out),
                ]
            )
        finally:
            raw.unlink(missing_ok=True)
        return out

    def synth_all(
        self,
        sentences: List[str],
        voice: str = "",
        retries: int = 2,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        """전체 문장 합성. 문장별 재시도 후에도 실패하면 TTSError (자동 모드 정책 §5.6)."""
        paths = []
        for i, text in enumerate(sentences):
            last_err: Optional[Exception] = None
            for _ in range(retries + 1):
                try:
                    paths.append(self.synth_sentence(text, voice))
                    last_err = None
                    break
                except (TTSError, ff.FFmpegError) as e:
                    last_err = e
            if last_err is not None:
                raise TTSError(f"문장 {i + 1} TTS 실패({retries + 1}회 시도): {last_err}")
            if on_progress:
                on_progress(i + 1, len(sentences))
        return paths
