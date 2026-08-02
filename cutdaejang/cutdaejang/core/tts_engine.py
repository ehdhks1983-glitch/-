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
import urllib.parse
import urllib.request
import uuid
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Tuple

from .. import config
from . import stage_locks
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
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # 🌐 v1.25 (목록 39-6): 인터넷 끊김·DNS 실패·읽기 타임아웃은 지금까지
        # 어느 except에도 안 걸려 폴백 체인(제미나이→오픈AI→내장 음성)이 통째로
        # 무산되고 영문 원문만 떴다. 재시도 가능한 TTSError로 바꿔 흘려보낸다.
        raise TTSError(f"인터넷 연결 문제로 요청하지 못했어요: {str(e)[:160]}") from e


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


def is_daily_quota(err: TTSHTTPError) -> bool:
    """429가 '기다려도 안 풀리는' 소진인지 — 하루 한도 또는 선불 크레딧 (v0.50.2/0.51).

    사용자 로그: 하루 한도(또는 크레딧)가 끝난 날은 문장마다 120초를 꼬박 기다린
    뒤에야 다음 목소리로 넘어갔다. 분당 한도(잠깐 기다리면 풀림)와 구분해 즉시
    폴백한다. "prepayment credits are depleted"는 유료 선불 크레딧 소진 (v0.51).
    """
    try:
        for detail in err.payload["error"]["details"]:
            for v in detail.get("violations", []):
                if "perday" in str(v.get("quotaId", "")).lower():
                    return True
    except (TypeError, KeyError):
        pass
    return bool(re.search(r"per[\s_]?day|daily|prepayment credit|credits are depleted",
                          err.text[:2000], re.IGNORECASE))


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


# 🎚 고정 시드 (v1.12) — 한 작업 안의 모든 블록, 그리고 재실행까지 같은 화자 샘플을
# 뽑게 하는 기본값. 0~4294967295 사이면 값 자체는 아무거나 되지만, 이 값이 바뀌면
# 일레븐랩스 캐시가 통째로 무효가 되므로 함부로 건드리지 않는다.
ELEVEN_SEED_DEFAULT = 1_207_531


class ElevenLabsTTS:
    """ElevenLabs — 내 목소리 클로닝 TTS (한국어 지원, 클로닝은 유료 구독 필요).

    voice에는 클론/보이스의 voice_id를 넣는다. 응답은 mp3 → 캐시 단계에서 wav 변환.
    """

    name = "elevenlabs"

    def __init__(self, api_key: Optional[str] = None, model: str = "eleven_multilingual_v2",
                 stability: float = 0.75, similarity: float = 0.75, seed: int = 0):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.model = model
        # 🎙 목소리 일관성 (v0.83) — 문장마다 따로 합성하면 톤이 들쑥날쑥해지는
        # 문제: stability를 0.5→0.75로 올리고(변주 억제), 앞뒤 문장을
        # previous_text/next_text로 보내 이어읽기(문맥 조건화)한다.
        self.stability = max(0.0, min(1.0, float(stability)))
        self.similarity = max(0.0, min(1.0, float(similarity)))
        # 🎚 음높이 리셋 방지 (v1.12) — seed를 고정하면 블록이 바뀌어도 같은 화자
        # 샘플을 뽑는다(결정성은 best-effort). 0=기본 시드, 음수=시드 미사용.
        try:
            want_seed = int(seed)
        except (TypeError, ValueError):
            want_seed = 0
        self.seed: Optional[int] = (
            None if want_seed < 0
            else (ELEVEN_SEED_DEFAULT if want_seed == 0 else want_seed % 4_294_967_296))
        self.cache_extra = f"stab{self.stability:.2f}|sim{self.similarity:.2f}|ctx1"
        if self.seed is not None:     # 시드가 바뀌면 다른 소리 → 캐시 키에 반영
            self.cache_extra += f"|seed{self.seed}"
        self.wants_context = True     # 엔진이 앞뒤 문장을 넣어줌
        # 🔗 이어읽기(request stitching) — 응답 헤더 request-id를 최대 3개까지 모아
        # 다음 요청에 넘기면 블록이 넘어가도 억양·음높이가 이어진다 (2시간 내 유효).
        self._req_ids: deque = deque(maxlen=3)
        # 일레븐랩스는 한 요청에 10,000자까지 받는다 → 1~2분 영상은 블록 1개로 끝내
        # 경계 자체를 없앤다. 다른 제공자는 종전 상수 유지(= 기존 캐시 보존).
        self.continuity_max_chars = 2000
        self.continuity_max_sentences = 80
        self._prev_text = ""
        self._next_text = ""
        if not self.api_key:
            raise TTSError("ELEVENLABS_API_KEY가 설정되어 있지 않습니다")

    def _payload(self, text: str) -> dict:
        p = {
            "text": text, "model_id": self.model,
            "voice_settings": {"stability": self.stability,
                               "similarity_boost": self.similarity},
        }
        # 문맥은 과금되지 않는 조건화 입력 — 앞뒤 300자면 충분
        if self._prev_text:
            p["previous_text"] = self._prev_text[-300:]
        if self._next_text:
            p["next_text"] = self._next_text[:300]
        if self.seed is not None:
            p["seed"] = self.seed          # 블록이 바뀌어도 같은 음색·음높이로
        if self._req_ids:
            # 직전 생성들에 프로소디를 이어붙인다(최대 3개). 서버는
            # previous_request_ids가 있으면 previous_text를 무시하므로 함께 보내도
            # 안전하고, 사슬이 끊긴 구간에서는 previous_text가 그대로 동작한다.
            p["previous_request_ids"] = list(self._req_ids)
        return p

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        if not voice:
            raise TTSNonRetryable("내 목소리가 아직 등록되지 않았습니다 — [🎤 내 목소리 등록]을 먼저 해주세요")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            data=json.dumps(self._payload(text)).encode("utf-8"),
            headers={"Content-Type": "application/json", "xi-api-key": self.api_key},
            method="POST",
        )
        try:
            # 블록 하나가 최대 2000자까지 커질 수 있어 여유 있게 기다린다.
            with urllib.request.urlopen(req, timeout=300) as resp:
                Path(out_path).write_bytes(resp.read())
                # 🔗 이 생성의 request-id를 모아 다음 요청 조건화에 쓴다 (최대 3개).
                rid = str(resp.headers.get("request-id") or "").strip()
                if rid:
                    self._req_ids.append(rid)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (400, 422) and self._req_ids and "request_id" in body.lower():
                # 사슬이 만료(2시간)·무효면 끊고 문맥만으로 한 번 더 시도한다.
                # 이 가드가 없으면 4xx는 재시도 없이 곧장 다른 제공자 폴백이 되어
                # 영상 중간부터 목소리가 통째로 바뀐다 (_synth_raw_with_retry 참고).
                self._req_ids.clear()
                return self.synthesize(text, voice, out_path)
            if "paid_plan_required" in body:
                # 일레븐랩스 정책: 라이브러리 성우는 담기 무료·API 합성은 유료 (v0.65.1)
                raise TTSNonRetryable(
                    "이 성우는 무료 플랜에선 영상 제작(API)에 쓸 수 없어요 — 라이브러리에서 "
                    "담은 성우는 Starter(월 $6)부터 사용 가능해요. 무료로 만들려면 기본 성우"
                    "(Adam·Bella 같은 영어 이름)나 ⭐ AI 성우(제미나이)를 골라주세요") from e
            if e.code == 402 or "quota_exceeded" in body:
                # 키 자체의 크레딧 한도(만들 때 제한) 또는 월 크레딧 소진 (v0.65.1)
                raise TTSNonRetryable(
                    "일레븐랩스 크레딧이 막혀 있어요 — 키를 만들 때 '크레딧 한도'를 걸었다면 "
                    "그 키로는 합성이 안 돼요. elevenlabs.io의 API Keys에서 한도 없는(무제한) "
                    "새 키를 만들어 다시 저장하고, 구독 화면의 남은 크레딧도 확인해 주세요") from e
            if e.code in (401, 403):
                raise TTSNonRetryable(f"ElevenLabs 키/권한 오류 {e.code}: {body[:200]}") from e
            raise TTSHTTPError(e.code, None, body) from e
        return str(out_path)


def list_elevenlabs_voices(api_key: Optional[str] = None) -> list:
    """내 ElevenLabs 계정의 보이스 목록 (v0.46 — 기성 성우 보이스 선택용).

    프리메이드 + 라이브러리에서 담은 보이스 + 내 클론까지, 계정에 보이는 그대로.
    반환: [{"voice_id","name","category"}] (name 순).
    """
    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise TTSError("ELEVENLABS_API_KEY가 설정되어 있지 않습니다")
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise TTSError(f"ElevenLabs 보이스 목록 실패 {e.code}: "
                       f"{e.read().decode('utf-8', 'replace')[:200]}") from e
    out = [
        {"voice_id": v["voice_id"], "name": str(v.get("name") or v["voice_id"]),
         "category": str(v.get("category") or "")}
        for v in data.get("voices", []) if v.get("voice_id")
    ]
    return sorted(out, key=lambda v: (v["category"] != "cloned", v["name"].lower()))


def list_shared_voices(language: str = "ko", page_size: int = 50,
                       api_key: Optional[str] = None) -> list:
    """일레븐랩스 Voice Library(공유 보이스) 검색 — 한국어 성우 담기용 (v0.65).

    반환: [{"voice_id","owner_id","name","desc","preview_url","free_ok"}].
    """
    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise TTSError("ELEVENLABS_API_KEY가 설정되어 있지 않습니다")
    url = ("https://api.elevenlabs.io/v1/shared-voices"
           f"?page_size={int(page_size)}&language={urllib.parse.quote(language)}")
    req = urllib.request.Request(url, headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise TTSError(f"성우 라이브러리 조회 실패 {e.code}: "
                       f"{e.read().decode('utf-8', 'replace')[:200]}") from e
    out = []
    for v in data.get("voices", []):
        if not (v.get("voice_id") and v.get("public_owner_id")):
            continue
        bits = [str(v.get(k) or "").strip()
                for k in ("gender", "age", "use_case", "descriptive")]
        out.append({
            "voice_id": v["voice_id"],
            "owner_id": v["public_owner_id"],
            "name": str(v.get("name") or v["voice_id"]),
            "desc": " · ".join(b for b in bits if b),
            "preview_url": str(v.get("preview_url") or ""),
            "free_ok": bool(v.get("free_users_allowed", True)),
        })
    return out


def add_shared_voice(owner_id: str, voice_id: str, name: str,
                     api_key: Optional[str] = None) -> str:
    """라이브러리 보이스를 내 계정(내 음성)에 담기 — 담아야 API 목록에 나온다 (v0.65)."""
    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise TTSError("ELEVENLABS_API_KEY가 설정되어 있지 않습니다")
    url = (f"https://api.elevenlabs.io/v1/voices/add/"
           f"{urllib.parse.quote(owner_id)}/{urllib.parse.quote(voice_id)}")
    body = json.dumps({"new_name": (name or "성우")[:80]}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if "voice_limit" in detail or "maximum" in detail.lower():
            raise TTSError("보이스 슬롯이 가득 찼어요 — elevenlabs.io 내 음성에서 "
                           "안 쓰는 보이스를 지우거나 플랜을 올려주세요") from e
        raise TTSError(f"보이스 담기 실패 {e.code}: {detail}") from e
    return str(data.get("voice_id") or voice_id)


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
$want = '__VOICE__'
$pick = $null
if ($want -ne '') { $pick = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Name -eq $want } | Select-Object -First 1 }
if (-not $pick) { $pick = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'ko*' } | Select-Object -First 1 }
if (-not $pick) { $s.Dispose(); exit 3 }
$s.SelectVoice($pick.VoiceInfo.Name)
$s.Rate = __RATE__
$s.SetOutputToWaveFile($OutWav)
$s.Speak($text)
$s.Dispose()
exit 0
"""

_SAPI_LIST_PS1 = r"""Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object {
  $v = $_.VoiceInfo
  Write-Output ($v.Name + '|' + $v.Culture.Name + '|' + $v.Gender)
}
$s.Dispose()
"""


def build_sapi_script(rate: int, voice: str = "") -> str:
    """SAPI 합성 PS1 생성 — 보이스명은 PS 문자열 리터럴로 안전 이스케이프 (v0.59)."""
    safe = (voice or "").replace("'", "''")
    return _SAPI_PS1.replace("__RATE__", str(rate)).replace("__VOICE__", safe)


def list_windows_voices() -> list:
    """이 PC에 설치된 Windows 내장 음성 목록 (v0.59) — [{name, culture, gender}].

    Windows가 아니면 빈 목록. 한국어(ko*) 보이스를 앞으로 정렬한다.
    """
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    if sys.platform != "win32":
        return []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / "list.ps1"
            ps1.write_text(_SAPI_LIST_PS1, encoding="utf-8-sig")
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ps1)],
                capture_output=True, timeout=30,
            )
        voices = []
        for ln in proc.stdout.decode("utf-8", "replace").splitlines():
            parts = ln.strip().split("|")
            if len(parts) >= 2 and parts[0]:
                voices.append({"name": parts[0], "culture": parts[1],
                               "gender": parts[2] if len(parts) > 2 else ""})
        voices.sort(key=lambda v: (0 if v["culture"].lower().startswith("ko") else 1,
                                   v["name"]))
        return voices
    except Exception:  # noqa: BLE001 — 목록 실패는 빈 목록 (합성엔 영향 없음)
        return []


class WindowsTTS:
    """Windows 내장 한국어 음성(SAPI) — 키·인터넷 없이 무료 (로봇톤이지만 실제 음성).

    rate: SAPI 말 속도 -10(아주 느림)~10(아주 빠름), 0=보통 (v0.44 설정 가능).
    """

    name = "windows"

    def __init__(self, rate: int = 0, voice: str = ""):
        try:
            self.rate = max(-10, min(10, int(rate)))
        except (TypeError, ValueError):
            self.rate = 0
        self.voice = (voice or "").strip()  # 설치된 SAPI 보이스명 (빈 값=한국어 첫 번째)
        # 속도·보이스가 바뀌면 다른 소리 → 캐시 키에 반영 (기본값은 기존 캐시 재사용)
        parts = ([f"rate{self.rate}"] if self.rate else []) + \
                ([f"v:{self.voice}"] if self.voice else [])
        self.cache_extra = "|".join(parts)

    def synthesize(self, text: str, voice: str, out_path: str) -> str:
        import subprocess  # noqa: PLC0415
        import sys  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        if sys.platform != "win32":
            # 재시도해도 달라질 수 없는 환경 문제 → 즉시 다음 제공자/오류로
            raise TTSNonRetryable("Windows 내장 음성은 Windows에서만 사용할 수 있습니다")
        with tempfile.TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / "sapi.ps1"
            txt = Path(tmp) / "text.txt"
            ps1.write_text(build_sapi_script(self.rate, self.voice),
                           encoding="utf-8-sig")
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

# 긴 대본을 문장마다 API 호출하면 같은 보이스를 골라도 호출마다 억양·음높이가
# 조금씩 다시 샘플링된다. 실제 음성은 여러 문장을 한 호흡으로 합성한 뒤, 문장 사이
# 자연 무음에서 다시 나눠 기존 자막 타이밍 파이프라인에 그대로 넣는다.
CONTINUITY_PROVIDERS = {"gemini", "openai", "elevenlabs", "sovits"}
CONTINUITY_MAX_CHARS = 1200       # OpenAI 4096자 제한보다 충분히 작고 약 1~2분 분량
CONTINUITY_MAX_SENTENCES = 40     # 8분 롱폼도 호출 횟수를 줄여 화자·음높이·속도 변화 최소화
_SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


def continuity_blocks(sentences: List[str], max_chars: int = CONTINUITY_MAX_CHARS,
                      max_sentences: int = CONTINUITY_MAX_SENTENCES) -> List[Tuple[int, int]]:
    """긴 대본을 연속 낭독 블록 ``[(시작, 끝), ...]`` 으로 묶는다.

    구간(챕터) 경계와 무관하게 문장 순서만 보고 묶으므로, 구간이 바뀌는 곳에서도
    같은 합성 호출의 음색과 호흡이 이어질 수 있다.
    """
    if not sentences:
        return []
    max_chars = max(80, int(max_chars))
    max_sentences = max(2, int(max_sentences))
    out: List[Tuple[int, int]] = []
    start, chars = 0, 0
    for i, text in enumerate(sentences):
        add = len(str(text).strip()) + (2 if i > start else 0)
        if i > start and (chars + add > max_chars or i - start >= max_sentences):
            out.append((start, i))
            start, chars = i, 0
            add = len(str(text).strip())
        chars += add
    out.append((start, len(sentences)))
    return out


CONTEXT_CHARS = 300   # 이어읽기 문맥으로 보낼 앞뒤 글자 수 (문맥은 과금되지 않는다)


def context_tail(before: List[str], limit: int = CONTEXT_CHARS) -> str:
    """블록 앞 문장들을 뒤에서부터 limit자까지 이어 붙인다 (previous_text용)."""
    parts: List[str] = []
    total = 0
    for text in reversed([str(s).strip() for s in before]):
        if not text:
            continue
        parts.append(text)
        total += len(text) + 1
        if total >= limit:
            break
    return " ".join(reversed(parts))[-limit:]


def context_head(after: List[str], limit: int = CONTEXT_CHARS) -> str:
    """블록 뒤 문장들을 앞에서부터 limit자까지 이어 붙인다 (next_text용)."""
    parts: List[str] = []
    total = 0
    for text in [str(s).strip() for s in after]:
        if not text:
            continue
        parts.append(text)
        total += len(text) + 1
        if total >= limit:
            break
    return " ".join(parts)[:limit]


def _silence_midpoints(path: str) -> List[int]:
    """오디오 내부의 자연 무음 중앙 시각(μs). 감지 실패는 빈 목록."""
    try:
        proc = ff.run([
            ff.ffmpeg_bin(), "-hide_banner", "-v", "info", "-i", str(path),
            "-af", "silencedetect=noise=-42dB:d=0.06", "-f", "null", "-",
        ])
    except Exception:  # noqa: BLE001 — 이어읽기만 포기하고 문장별 합성으로 폴백
        return []
    text = proc.stderr.decode("utf-8", "replace")
    starts: List[float] = []
    out: List[int] = []
    for line in text.splitlines():
        ms = _SILENCE_START.search(line)
        if ms:
            starts.append(float(ms.group(1)))
        me = _SILENCE_END.search(line)
        if me and starts:
            start = starts.pop(0)
            end = float(me.group(1))
            if end > start:
                out.append(int((start + end) * 500_000))
    return out


def _pick_sentence_boundaries(duration_us: int, texts: List[str],
                              candidates: List[int]) -> List[int]:
    """예상 문장 위치와 가장 가까운 무음 N-1개를 단조 증가하도록 고른다."""
    n = len(texts)
    if n < 2:
        return []
    cands = sorted({int(c) for c in candidates
                    if 80_000 < int(c) < int(duration_us) - 80_000})
    need = n - 1
    if len(cands) < need:
        return []
    weights = [max(1, len(re.sub(r"\s+", "", str(t)))) for t in texts]
    total = sum(weights)
    acc = 0
    targets = []
    for w in weights[:-1]:
        acc += w
        targets.append(int(duration_us * acc / total))

    # 동적 계획법: 각 목표에 후보 하나를 순서대로 대응시키는 최소 거리 조합.
    inf = float("inf")
    dp = [[inf] * len(cands) for _ in range(need)]
    prev = [[-1] * len(cands) for _ in range(need)]
    for k, c in enumerate(cands):
        dp[0][k] = float((c - targets[0]) ** 2)
    for j in range(1, need):
        for k, c in enumerate(cands):
            best, best_p = inf, -1
            for p in range(k):
                if c - cands[p] < 80_000:
                    continue
                score = dp[j - 1][p] + float((c - targets[j]) ** 2)
                if score < best:
                    best, best_p = score, p
            dp[j][k], prev[j][k] = best, best_p
    k = min(range(len(cands)), key=lambda x: dp[-1][x])
    if dp[-1][k] == inf:
        return []
    picked = [cands[k]]
    for j in range(need - 1, 0, -1):
        k = prev[j][k]
        if k < 0:
            return []
        picked.append(cands[k])
    picked.reverse()
    return picked


# ─────────────────────────── 전처리 (지시서 PATCH 2) ───────────────────────────


def _speed_filter(speed) -> str:
    """말 속도 배수 → atempo 필터 문자열 (1.0이면 빈 문자열).

    atempo는 0.5~2.0만 받으므로 범위 밖은 곱해서 나눈다. 음높이는 그대로 두고
    속도만 바뀐다(피치 시프트 아님) — 목소리가 이상해지지 않는다.
    """
    try:
        s = float(speed or 1.0)
    except (TypeError, ValueError):
        return ""
    s = max(0.5, min(2.0, s))
    if abs(s - 1.0) < 0.01:
        return ""
    return f"atempo={s:.3f},"


def postprocess_clip(raw_path: str, out_wav: str, audio_cfg: dict) -> Tuple[int, int]:
    """앞뒤 무음 트림 → 10ms 에지 페이드 → -16 LUFS → 30ms 패드 → 48kHz 스테레오 wav.

    (트림 전 길이, 트림 후 길이)를 μs로 반환 — pacing 로그용.
    """
    # v0.46.1: 트림을 덜 공격적으로(-50dB 이하만), 앞뒤 여유를 50ms 이상으로 —
    # 문장 경계가 뚝뚝 끊기고 숨결·여운이 잘리던 문제 완화 (설정값이 더 부드러우면 존중)
    threshold = min(audio_cfg.get("trim_threshold_db", -45), -50)
    pad_ms = max(audio_cfg.get("edge_pad_ms", 30), 50)
    pad_s = pad_ms / 1000.0
    lufs = audio_cfg.get("lufs", -16)
    raw_us = ff.probe_duration_us(str(raw_path))
    # 🏃 말 속도 (v1.27) — 일레븐랩스·제미나이 등 제공자를 가리지 않고 여기서 한 번에.
    # 회원님 리포트: "목소리 톤 같은 게 너무 느려" — 지금까지 조절 수단이 아예 없었다.
    speed = _speed_filter(audio_cfg.get("speech_speed", 1.0))

    sr = f"silenceremove=start_periods=1:start_threshold={threshold}dB"
    filters = (
        f"{speed}{sr},areverse,{sr},"
        "afade=t=in:d=0.02,areverse,afade=t=in:d=0.02,"   # 양끝 20ms 페이드 (클릭 방지)
        f"loudnorm=I={lufs}:TP=-1.5:LRA=11,"
        "aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,"
        f"adelay={pad_ms}:all=1,apad=pad_dur={pad_s}"
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

    def _cache_key(self, text: str, voice: str, ctx: str = "") -> str:
        model = getattr(self.provider, "model", "")
        raw = f"{self.provider.name}|{model}|{voice}|{self.style_preset}|{text}"
        # 참조 기반 제공자(SoVITS 등)는 참조가 바뀌면 다른 목소리 → 키에 반영
        extra = getattr(self.provider, "cache_extra", "")
        if extra:
            raw += f"|{extra}"
        sp = self.settings["audio"].get("speech_speed", 1.0)   # 🏃 v1.27
        if abs(float(sp or 1.0) - 1.0) >= 0.01:
            raw += f"|sp:{float(sp):.2f}"
        if ctx:  # 이어읽기 문맥이 다르면 다른 소리 (v0.83)
            raw += f"|ctx:{ctx}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def cache_path(self, text: str, voice: str, ctx: str = "") -> Path:
        return self.cache_dir / f"{self._cache_key(text, voice, ctx)}.wav"

    def _forget_stitch(self) -> None:
        """캐시로 건너뛴 자리에서는 이어읽기 사슬을 끊는다 (v1.12).

        request-id 사슬은 '바로 앞에서 실제로 합성한 소리'에만 의미가 있다. 캐시로
        건너뛴 블록 뒤에 그대로 이어 붙이면 대본상 한참 앞의 억양에 조건화된다.
        사슬을 끊으면 previous_text(앞 300자) 조건화로 자동으로 되돌아간다.
        """
        ids = getattr(self.provider, "_req_ids", None)
        if ids is not None:
            ids.clear()

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

    def _speak_text(self, text: str, continuity: bool = False) -> str:
        """Gemini에만 스타일 지시문 부착 — 지시문 + 개행 + 문장 (지시서 PATCH 6)."""
        if self.provider.name == "gemini":
            instruction = STYLE_INSTRUCTIONS.get(self.style_preset)
            if instruction:
                if continuity:
                    instruction += (
                        " 전체 원고를 처음부터 끝까지 같은 화자, 같은 음높이와 말속도로 "
                        "자연스럽게 이어 읽고, 문단 사이에는 짧게만 호흡해줘. "
                        "지시문은 읽지 말고 [낭독 원고]만 말해줘:"
                    )
                    return f"{instruction}\n[낭독 원고]\n{text}"
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

    def _synth_raw_with_retry(self, text: str, voice: str, raw_path: str,
                              continuity: bool = False) -> None:
        tts_cfg = self.settings["tts"]
        max_retries = tts_cfg["max_retries"]
        wait_cap = tts_cfg["retry_wait_cap_s"]
        # ⏱ v1.32 (목록 57): 여태 wait_cap은 «재시도 사이 잠자는 시간»만 셌다.
        #   서버가 응답 없이 매달리면 요청 하나가 타임아웃(120초)까지 가는데 그건
        #   예산에 안 들어가, 문장 하나에 (5+1)×120초 = 12분이 들어가도 상한에
        #   안 걸렸다. 이제 **문장에 쓴 벽시계 시간 전체**를 센다.
        t_started = time.monotonic()
        total_wait = 0.0
        last: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            if self.limiter:
                self.limiter.acquire(status_cb=self._status)
            try:
                self.stats["api_calls"] += 1
                self.provider.synthesize(
                    self._speak_text(text, continuity=continuity), voice, raw_path)
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
                if e.code == 429 and is_daily_quota(e):
                    raise TTSExhausted(
                        f"{self.provider.name} 오늘의 무료 한도·크레딧 소진 — 즉시 다음 "
                        "목소리로 넘어갑니다 (무료 한도는 한국시간 오후 4~5시쯤 리셋, "
                        "크레딧은 ai.studio에서 충전)", raw=e.text
                    ) from e
                if attempt >= max_retries:
                    break
                delay = parse_retry_delay_s(e) if e.code == 429 else None
                if delay is None:
                    delay = min(4 * (2**attempt), 32)  # 4→8→16→32
                delay += random.uniform(1.0, 2.0)  # 지터
                if time.monotonic() - t_started + delay > wait_cap:
                    raise TTSExhausted(
                        f"{self.provider.name} TTS 대기 상한({wait_cap}s) 초과 "
                        f"— 이 문장에 {time.monotonic() - t_started:.0f}초를 썼어요",
                        raw=e.text) from e
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
                # 🌐 응답 없이 매달리다 타임아웃 난 경우가 여기로 온다 — 이것도 예산 안이다
                if time.monotonic() - t_started >= wait_cap:   # 딱 상한에서 끊는다
                    raise TTSExhausted(
                        f"{self.provider.name} 응답이 너무 느려 {wait_cap}초를 넘겼어요 "
                        "— 다음 목소리로 넘어갑니다",
                        raw=getattr(e, "text", "") or str(e)) from e
                self._wait(2.0, f"{self.provider.name} 오류 — 재시도 ({attempt + 1}/{max_retries})")

        raw = getattr(last, "text", "") or str(last)
        raise TTSExhausted(
            f"{self.provider.name} TTS 재시도 {max_retries}회 소진: {str(last)[:160]}", raw=raw
        )

    def _pronounced(self, text: str) -> str:
        if self.settings["tts"].get("auto_pronounce", True):
            from ..utils.pronounce import pronounce_ko  # noqa: PLC0415
            try:
                return pronounce_ko(text)
            except Exception:  # noqa: BLE001 — 발음 변환 문제로 합성이 죽으면 안 됨
                pass
        return text

    def synth_sentence(self, text: str, voice: str = "",
                       prev_text: str = "", next_text: str = "") -> Path:
        # 숫자·영어를 한글 발음으로 (2026년→이천이십육년, AI→에이아이) — 오독 방지 (v0.46.1).
        # 자막은 원문 그대로, TTS 입력만 바꾼다. 캐시 키도 변환 후 텍스트 기준.
        from .text_cards import strip_mark  # noqa: PLC0415

        text = text.replace("[카드]", " ")  # v1.07 캐시·테스트 하위호환
        text = strip_mark(text).strip()   # 🅰 [카드:후기] 등 장면 표식은 읽지 않음
        text = self._pronounced(text)
        voice = self._resolve_voice(voice)
        # 🎙 이어읽기 문맥 (v0.83) — 지원 제공자(일레븐랩스)만: 앞뒤 문장을 함께
        # 보내 문장 사이 톤이 이어지게 한다. 문맥이 바뀌면 소리도 달라지므로 캐시 키에 포함.
        ctx = ""
        if getattr(self.provider, "wants_context", False) and (prev_text or next_text):
            prev_text = self._pronounced(prev_text) if prev_text else ""
            next_text = self._pronounced(next_text) if next_text else ""
            ctx = f"{prev_text}\x1f{next_text}"
        out = self.cache_path(text, voice, ctx)
        if out.exists():
            self.stats["cache_hits"] += 1
            self._forget_stitch()
            return out
        raw = out.with_suffix(f".{uuid.uuid4().hex[:8]}.raw.wav")  # 동시 잡 경쟁 방지
        try:
            if getattr(self.provider, "wants_context", False):
                self.provider._prev_text = prev_text
                self.provider._next_text = next_text
            self._synth_raw_with_retry(text, voice, str(raw))
            raw_us, final_us = postprocess_clip(str(raw), str(out), self.settings["audio"])
            self.stats["trim_saved_us"] += max(0, raw_us - final_us)
        finally:
            if getattr(self.provider, "wants_context", False):
                self.provider._prev_text = ""
                self.provider._next_text = ""
            raw.unlink(missing_ok=True)
        return out

    def synth_all(
        self,
        sentences: List[str],
        voice: str = "",
        on_progress: Optional[Callable[[int, int], None]] = None,
        continuity: bool = False,
    ) -> List[Path]:
        if (continuity and len(sentences) > 1
                and self.provider.name in CONTINUITY_PROVIDERS):
            return self._synth_all_continuous(sentences, voice, on_progress)
        paths = []
        for i, text in enumerate(sentences):
            try:
                paths.append(self.synth_sentence(
                    text, voice,
                    prev_text=(sentences[i - 1] if i > 0 else ""),
                    next_text=(sentences[i + 1] if i + 1 < len(sentences) else "")))
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

    def _split_continuity_block(self, block_path: Path, texts: List[str],
                                part_paths: List[Path]) -> bool:
        duration_us = ff.probe_duration_us(str(block_path))
        cuts = _pick_sentence_boundaries(
            duration_us, texts, _silence_midpoints(str(block_path)))
        if len(cuts) != len(texts) - 1:
            return False
        bounds = [0, *cuts, duration_us]
        made: List[Path] = []
        audio_cfg = self.settings["audio"]
        threshold = min(audio_cfg.get("trim_threshold_db", -45), -50)
        pad_ms = max(audio_cfg.get("edge_pad_ms", 30), 50)
        pad_s = pad_ms / 1000.0
        sr = f"silenceremove=start_periods=1:start_threshold={threshold}dB"
        # 🏃 v1.27: 말 속도는 여기서 — 경계는 원래 속도로 찾고, 조각만 빠르게.
        speed = _speed_filter(audio_cfg.get("speech_speed", 1.0))
        try:
            for i, out in enumerate(part_paths):
                tmp = out.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp.wav")
                # 블록 안의 자연 무음을 경계로 잘랐으므로 각 조각의 앞뒤에 남은
                # 반쪽 무음은 제거한다. 그렇지 않으면 원래 무음 + retime_narration의
                # 문장 간격이 겹쳐 실제 호흡이 두 배 가까이 길어진다.
                filters = (
                    f"atrim=start={bounds[i] / 1e6:.6f}:"
                    f"end={bounds[i + 1] / 1e6:.6f},asetpts=PTS-STARTPTS,"
                    f"{speed}{sr},areverse,{sr},"
                    "afade=t=in:d=0.02,areverse,afade=t=in:d=0.02,"
                    "aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,"
                    f"adelay={pad_ms}:all=1,apad=pad_dur={pad_s}"
                )
                ff.run([
                    ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(block_path),
                    "-af", filters,
                    "-c:a", "pcm_s16le", str(tmp),
                ])
                tmp.replace(out)
                made.append(out)
        except Exception:  # noqa: BLE001
            for p in made:
                p.unlink(missing_ok=True)
            return False
        return all(p.is_file() for p in part_paths)

    def _synth_continuity_block(self, texts: List[str], voice: str,
                                prev_text: str = "", next_text: str = "") -> Optional[List[Path]]:
        """여러 문장을 한 번에 합성하고 자연 무음에서 문장별 캐시 클립으로 분리."""
        from .text_cards import strip_mark  # noqa: PLC0415

        spoken = [self._pronounced(strip_mark(t).strip()) for t in texts]
        joined = "\n\n".join(spoken)
        voice = self._resolve_voice(voice)
        prev_spoken = self._pronounced(prev_text) if prev_text else ""
        next_spoken = self._pronounced(next_text) if next_text else ""
        ctx = f"cont-v1:{prev_spoken}\x1f{next_spoken}"
        block = self.cache_path("__CONTINUITY_V1__\n" + joined, voice, ctx)
        parts = [
            self.cache_dir / f"{block.stem}.cont-{i + 1:02d}.wav"
            for i in range(len(spoken))
        ]
        if all(p.is_file() for p in parts):
            self.stats["cache_hits"] += 1
            self._forget_stitch()
            return parts

        if not block.is_file():
            raw = block.with_suffix(f".{uuid.uuid4().hex[:8]}.raw.wav")
            try:
                if getattr(self.provider, "wants_context", False):
                    self.provider._prev_text = prev_spoken
                    self.provider._next_text = next_spoken
                self._synth_raw_with_retry(
                    joined, voice, str(raw), continuity=True)
                # 🏃 v1.27: 블록은 **원래 속도로** 만든다. 여기서 빠르게 해 버리면
                # 문장 사이 자연 무음도 같이 짧아져 경계 검출이 실패하고, 이어읽기가
                # 통째로 폐기돼 문장별 재합성으로 되돌아간다(톤 튐 + 호출 3배).
                # 속도는 조각으로 자른 뒤 _split_continuity_block에서 건다.
                raw_us, final_us = postprocess_clip(
                    str(raw), str(block),
                    {**self.settings["audio"], "speech_speed": 1.0})
                self.stats["trim_saved_us"] += max(0, raw_us - final_us)
            finally:
                if getattr(self.provider, "wants_context", False):
                    self.provider._prev_text = ""
                    self.provider._next_text = ""
                raw.unlink(missing_ok=True)
        else:
            self.stats["cache_hits"] += 1
            self._forget_stitch()
        return parts if self._split_continuity_block(block, spoken, parts) else None

    def _block_context(self, sentences: List[str], start: int, end: int) -> Tuple[str, str]:
        """블록 [start, end) 앞뒤로 보낼 이어읽기 문맥 (v1.12).

        문맥을 실제로 API에 보내는 제공자(일레븐랩스)에게만 앞뒤 300자를 넉넉히 준다.
        나머지 제공자는 종전과 완전히 같은 문자열을 돌려주므로 캐시 키가 바뀌지 않는다
        (_synth_continuity_block의 ctx가 제공자 종류와 무관하게 키에 들어가기 때문).
        """
        if not getattr(self.provider, "wants_context", False):
            return ((sentences[start - 1] if start > 0 else ""),
                    (sentences[end] if end < len(sentences) else ""))
        return context_tail(sentences[:start]), context_head(sentences[end:])

    def _synth_all_continuous(
        self, sentences: List[str], voice: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        """긴 원고를 1~2분 블록으로 이어 읽되 기존 문장별 타이밍 계약은 유지."""
        paths: List[Path] = []
        done = 0
        # 제공자가 한 번에 받을 수 있는 만큼 크게 묶는다 — 블록 경계가 없으면
        # 음높이가 리셋될 자리도 없다 (일레븐랩스 2000자/80문장, 나머지는 종전값).
        blocks = continuity_blocks(
            sentences,
            max_chars=getattr(self.provider, "continuity_max_chars",
                              CONTINUITY_MAX_CHARS),
            max_sentences=getattr(self.provider, "continuity_max_sentences",
                                  CONTINUITY_MAX_SENTENCES))
        for start, end in blocks:
            texts = sentences[start:end]
            block_paths = None
            if len(texts) > 1:
                prev_ctx, next_ctx = self._block_context(sentences, start, end)
                block_paths = self._synth_continuity_block(
                    texts, voice, prev_text=prev_ctx, next_text=next_ctx)
            if block_paths is None:
                # TTS가 문장 사이에 감지 가능한 자연 무음을 만들지 않은 경우에는
                # 단어 중간을 자르지 않고 기존 문장별 방식으로 안전하게 되돌린다.
                block_paths = []
                for i, text in enumerate(texts, start):
                    prev_ctx, next_ctx = self._block_context(sentences, i, i + 1)
                    block_paths.append(self.synth_sentence(
                        text, voice, prev_text=prev_ctx, next_text=next_ctx))
            paths.extend(block_paths)
            done += len(texts)
            if on_progress:
                on_progress(done, len(sentences))
        saved = self.stats["trim_saved_us"] / US_PER_SECOND
        self._status(
            f"TTS 연속 낭독 완료 — {len(blocks)}개 호흡 블록 · "
            f"API {self.stats['api_calls']}회, 캐시 {self.stats['cache_hits']}회, "
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
        return ElevenLabsTTS(
            model=tts_cfg.get("model_elevenlabs", "eleven_multilingual_v2"),
            stability=float(tts_cfg.get("eleven_stability", 0.75)),
            similarity=float(tts_cfg.get("eleven_similarity", 0.75)),
            seed=int(tts_cfg.get("eleven_seed", 0) or 0))
    if name == "sovits":
        return GPTSoVITSTTS(url=tts_cfg.get("sovits_url", ""),
                            ref_audio=tts_cfg.get("sovits_ref_audio", ""),
                            ref_text=tts_cfg.get("sovits_ref_text", ""))
    if name == "windows":
        return WindowsTTS(rate=tts_cfg.get("windows_rate", 0),
                          voice=tts_cfg.get("windows_voice", ""))
    return PROVIDERS[name]()


@stage_locks.guarded(stage_locks.TTS)  # 🚦 동시 작업 시 TTS는 한 작업씩 (v0.93)
def synth_with_fallback(
    sentences: List[str],
    chain: List[str],
    cache_root,
    settings: Optional[dict] = None,
    voice: str = "",
    status_cb: StatusCb = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    providers: Optional[dict] = None,  # 테스트 주입용
    continuity: bool = False,
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
            paths = engine.synth_all(
                sentences, voice=voice, on_progress=on_progress,
                continuity=continuity)
            log.info("TTS %s로 %d문장 합성 완료", name, len(sentences))
            return paths, name, reason
        except (TTSNonRetryable, TTSExhausted) as e:
            reason = f"{name} 실패 → 다음 제공자로 폴백: {str(e)[:200]}"
            log.warning("TTS %s", reason)
            if status_cb:
                status_cb(reason)
            continue
    raise TTSError(f"모든 TTS 제공자 실패 (체인: {full_chain}) — 마지막 사유: {reason}")
