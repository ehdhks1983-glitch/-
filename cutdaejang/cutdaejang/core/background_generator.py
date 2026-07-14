"""배경 준비 (기획안 §5.3): Gemini 이미지 생성 or 사용자 이미지 or 로컬 폴백.

모든 경로에서 최종적으로 1080×1920(캔버스 크기) PNG를 보장한다 — 크기가 다르면
FFmpeg cover-crop으로 정규화. API 실패 시 로컬 그라데이션 폴백(자동 모드에서 배경
때문에 작업이 죽지 않도록).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional

from ..spec import Canvas
from ..utils import ffmpeg as ff
from ..utils.png import vertical_gradient_png
from .tts_engine import _http_post_json


class BackgroundError(RuntimeError):
    pass


# 주제 해시로 고를 무난한 세로형 그라데이션 팔레트 (로컬 폴백용)
_PALETTES = [
    ((16, 24, 48), (94, 33, 82)),
    ((10, 36, 46), (24, 90, 100)),
    ((30, 18, 60), (120, 60, 40)),
    ((12, 12, 16), (60, 66, 90)),
]


def generate_local(out_path: str, canvas: Canvas, seed_text: str = "") -> str:
    top, bottom = _PALETTES[sum(seed_text.encode("utf-8")) % len(_PALETTES)]
    return vertical_gradient_png(out_path, canvas.w, canvas.h, top, bottom)


def normalize_to_canvas(src_path: str, out_path: str, canvas: Canvas) -> str:
    """임의 크기 이미지 → 캔버스 크기 cover-crop PNG."""
    ff.run(
        [
            ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(src_path),
            "-vf",
            f"scale={canvas.w}:{canvas.h}:force_original_aspect_ratio=increase,"
            f"crop={canvas.w}:{canvas.h}",
            "-frames:v", "1", str(out_path),
        ]
    )
    return str(out_path)


# AI 이미지 배경은 모델 가용성이 API 버전·계정·지역마다 달라 불안정하다.
# 그래서 기본은 로컬 그라데이션(항상 동작)이고, AI 이미지는 opt-in + 실패 시 자동 폴백.
# 모델명은 설정(bg.image_model)으로 교체 가능 — 새 모델이 나와도 재빌드 없이 대응.
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image-preview"


class GeminiImage:
    """Gemini 이미지 생성 — 세로형 배경 (모델은 설정으로 교체 가능)."""

    name = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_IMAGE_MODEL,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise BackgroundError("GEMINI_API_KEY가 설정되어 있지 않습니다")

    def generate(self, prompt: str, out_path: str, canvas: Canvas) -> str:
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
                                f"{prompt}\n\n세로형(9:16) 유튜브 쇼츠 배경 이미지. "
                                "글자 없이, 하단 1/3은 자막이 올라갈 수 있게 단순하게."
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        try:
            data = _http_post_json(url, payload, {"x-goog-api-key": self.api_key})
        except Exception as e:  # HTTP/네트워크 오류 유형에 무관하게 BackgroundError로 통일
            raise BackgroundError(f"이미지 생성 API 오류: {str(e)[:200]}") from e
        try:
            parts = data["candidates"][0]["content"]["parts"]
            b64 = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
        except (KeyError, IndexError, StopIteration) as e:
            raise BackgroundError(f"이미지 응답 형식 예상 밖: {json.dumps(data)[:300]}") from e
        raw = str(out_path) + ".raw"
        Path(raw).write_bytes(base64.b64decode(b64))
        try:
            normalize_to_canvas(raw, out_path, canvas)
        finally:
            Path(raw).unlink(missing_ok=True)
        return str(out_path)


def prepare_background(
    out_path: str,
    canvas: Canvas,
    user_image: Optional[str] = None,
    prompt: str = "",
    provider: Optional[GeminiImage] = None,
    on_note: Optional[callable] = None,
) -> str:
    """우선순위: 사용자 이미지 → 제공자(Gemini) → 로컬 그라데이션 폴백.

    배경은 비필수라, 제공자에서 어떤 예외가 나도 로컬 폴백으로 넘어가 작업을 살린다.
    """
    if user_image:
        try:
            return normalize_to_canvas(user_image, out_path, canvas)
        except ff.FFmpegError:
            if on_note:
                on_note("배경 이미지를 읽지 못해 기본 배경으로 대체합니다")
    if provider is not None:
        try:
            return provider.generate(prompt, out_path, canvas)
        except Exception as e:  # 배경 실패가 작업 전체를 죽이지 않게 (§5.6 정신)
            if on_note:
                on_note(f"AI 배경 생성 실패 → 기본 배경 사용 ({str(e)[:120]})")
    return generate_local(out_path, canvas, seed_text=prompt)
