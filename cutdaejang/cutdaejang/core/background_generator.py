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
# 그래서 기본은 로컬 그라데이션(항상 동작)이고, AI 이미지는 실패 시 자동 폴백.
# 모델명은 설정(bg.image_model)으로 교체 가능 — 새 모델이 나와도 재빌드 없이 대응.
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"

# 모델을 못 찾으면(404 등) 이 순서로 자동 재시도 — 프리뷰명 퇴역/개명 대응 (v0.46.1)
IMAGE_MODEL_FALLBACKS = [
    "gemini-2.5-flash-image",                    # 정식(GA) 이름
    "gemini-2.5-flash-image-preview",            # 구 프리뷰 이름
    "gemini-2.0-flash-preview-image-generation",  # 더 옛 이름 (최후)
]

_MODEL_GONE_MARKS = ("404", "NOT_FOUND", "not found", "is not supported",
                     "does not exist", "PERMISSION_DENIED")


class GeminiImage:
    """Gemini 이미지 생성 — 세로형 배경 (모델은 설정으로 교체 가능).

    설정된 모델이 없어졌으면(프리뷰 퇴역 등) 대체 모델명으로 자동 재시도하고,
    성공한 모델을 기억해 다음 장면부터는 바로 그 모델을 쓴다.
    """

    name = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_IMAGE_MODEL,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        self._working_model: Optional[str] = None  # 폴백으로 확정된 모델 (프로세스 내)
        if not self.api_key:
            raise BackgroundError("GEMINI_API_KEY가 설정되어 있지 않습니다")

    def generate(self, prompt: str, out_path: str, canvas: Canvas,
                 ref_png: Optional[str] = None) -> str:
        if self._working_model:
            candidates = [self._working_model]
        else:
            candidates = [self.model] + [m for m in IMAGE_MODEL_FALLBACKS if m != self.model]
        last: Optional[BackgroundError] = None
        for model in candidates:
            try:
                result = self._generate_with(model, prompt, out_path, canvas, ref_png=ref_png)
                if self._working_model != model:
                    self._working_model = model
                    if model != self.model:
                        import logging  # noqa: PLC0415
                        logging.getLogger("cutdaejang").warning(
                            "이미지 모델 '%s' 사용 불가 → '%s'로 자동 교체 "
                            "(설정 bg.image_model을 이 값으로 바꾸면 더 빨라요)",
                            self.model, model)
                return result
            except BackgroundError as e:
                last = e
                msg = str(e)
                if not any(k in msg for k in _MODEL_GONE_MARKS):
                    raise  # 모델 문제가 아니면(한도·네트워크 등) 다른 모델을 시도해도 소용없음
        raise last if last else BackgroundError("이미지 생성 실패")

    def _generate_with(self, model: str, prompt: str, out_path: str, canvas: Canvas,
                       ref_png: Optional[str] = None) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        parts: list = [
            {
                "text": (
                    f"{prompt}\n\n세로형(9:16) 유튜브 쇼츠 배경 이미지. "
                    "글자 없이, 하단 1/3은 자막이 올라갈 수 있게 단순하게."
                )
            }
        ]
        if ref_png and Path(ref_png).is_file():  # 캐릭터 일관성 참조 (v0.50)
            parts.append({"inlineData": {
                "mimeType": "image/png",
                "data": base64.b64encode(Path(ref_png).read_bytes()).decode(),
            }})
            parts[0]["text"] += "\n(첨부한 이미지와 같은 캐릭터·같은 그림체를 유지할 것)"
        b64 = None
        for attempt in (0, 1):
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            }
            try:
                data = _http_post_json(url, payload, {"x-goog-api-key": self.api_key})
            except Exception as e:  # HTTP/네트워크 오류 유형에 무관하게 BackgroundError로 통일
                raise BackgroundError(f"이미지 생성 API 오류: {str(e)[:200]}") from e
            try:
                out_parts = data["candidates"][0]["content"]["parts"]
                b64 = next(p["inlineData"]["data"] for p in out_parts if "inlineData" in p)
                break
            except (KeyError, IndexError, StopIteration) as e:
                # 모델이 그림 대신 말로 대답하는 경우가 가끔 있다(사용자 로그: 장면 1장) —
                # "이미지만" 지시를 붙여 한 번 더 (v0.50.2)
                replied_text = ""
                try:
                    replied_text = " ".join(
                        p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
                except (KeyError, IndexError, TypeError):
                    pass
                if attempt == 0 and replied_text.strip():
                    parts[0]["text"] += "\n(묻지 말고, 설명 없이 반드시 이미지 1장만 생성해 응답할 것)"
                    continue
                raise BackgroundError(f"이미지 응답 형식 예상 밖: {json.dumps(data)[:300]}") from e
        raw = str(out_path) + ".raw"
        Path(raw).write_bytes(base64.b64decode(b64))
        try:
            normalize_to_canvas(raw, out_path, canvas)
        finally:
            Path(raw).unlink(missing_ok=True)
        return str(out_path)


# ─────────── v0.45: 장면별 이미지 → 슬라이드 배경 영상 ───────────

# 마스코트 캐릭터 프리셋 (v0.50) — 모든 장면에 같은 캐릭터가 등장해 채널 아이덴티티.
# UI(genCharSel)와 키를 맞춘다. "직접"은 사용자가 쓴 묘사를 그대로 사용.
CHARACTER_PRESETS = {
    "해골": "유머러스한 흰 해골 캐릭터 (동그란 눈, 귀여운 만화체)",
    "고양이": "귀여운 주황 고양이 캐릭터 (큰 눈, 통통한 몸)",
    "곰돌이": "포근한 갈색 곰돌이 캐릭터 (둥근 얼굴, 순한 표정)",
    "직장인": "안경 쓴 젊은 직장인 캐릭터 (단정한 셔츠, 만화체)",
    "스틱맨": "단순한 검은 선으로 그린 스틱맨 캐릭터 (표정 풍부)",
}


# 그림체 프리셋 — UI(genBgStyle)와 키를 맞춘다. 프롬프트 앞에 붙어 전 장면 통일.
IMAGE_STYLES = {
    "일러스트": "따뜻한 플랫 벡터 일러스트 스타일, 부드러운 색감",
    "실사풍": "사실적인 고품질 사진 스타일, 자연스러운 빛",
    "3D": "귀여운 3D 렌더 스타일, 파스텔 톤, 부드러운 조명",
    "수채화": "은은한 수채화 그림 스타일, 종이 질감",
    "네온": "네온 빛 사이버 스타일, 어두운 배경에 형광 포인트",
    "미니멀": "미니멀 그래픽 스타일, 단순한 도형과 넉넉한 여백",
}


def scene_prompt_text(prompt: str, style: str = "일러스트", character: str = "") -> str:
    """장면 프롬프트 조립 — 그림체 + (있으면) 마스코트 캐릭터 + 장면 묘사 (v0.50)."""
    parts = []
    style_text = IMAGE_STYLES.get(style, "")
    if style_text:
        parts.append(style_text)
    ch = (character or "").strip()
    ch = CHARACTER_PRESETS.get(ch, ch)  # 프리셋 키면 상세 묘사로 치환
    if ch:
        parts.append(f"주인공: {ch} — 모든 장면에 같은 모습·같은 그림체로 등장")
    p = (prompt or "").strip()
    if p:
        parts.append(p if not ch else f"장면: 이 캐릭터가 {p}")
    return ". ".join(parts)


def generate_scene_images(
    prompts: list,
    provider: GeminiImage,
    out_dir,
    canvas: Canvas,
    style: str = "일러스트",
    character: str = "",
    on_note: Optional[callable] = None,
    on_progress: Optional[callable] = None,
) -> list:
    """장면 묘사 목록 → 이미지 경로 목록 (실패한 장면은 None — 호출측이 이웃으로 채움).

    스타일·캐릭터를 앞에 붙여 전 장면을 통일하고, 캐릭터 모드에서는 첫 성공
    이미지를 참조로 넘겨 다음 장면들의 캐릭터·그림체 일관성을 높인다 (v0.50).
    한 장 실패가 전체를 막지 않는다 (None으로 두고 계속).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    ref: Optional[str] = None
    for i, prompt in enumerate(prompts):
        if on_progress:
            on_progress(i, len(prompts))
        full = scene_prompt_text(prompt, style, character)
        try:
            out = provider.generate(full, str(out_dir / f"scene_{i + 1:02d}.png"),
                                    canvas, ref_png=ref)
            paths.append(out)
            if ref is None and (character or "").strip():
                ref = out  # 첫 성공작을 참조로 — 캐릭터 일관성
        except TypeError:  # 테스트 대역 등 ref_png 미지원 제공자
            try:
                paths.append(provider.generate(full, str(out_dir / f"scene_{i + 1:02d}.png"),
                                               canvas))
            except Exception as e:  # noqa: BLE001
                paths.append(None)
                if on_note:
                    on_note(f"장면 {i + 1} 이미지 실패 → 이웃 장면으로 대체 ({str(e)[:80]})")
        except Exception as e:  # noqa: BLE001 — 한 장 실패는 이웃 이미지로 대체
            paths.append(None)
            if on_note:
                on_note(f"장면 {i + 1} 이미지 실패 → 이웃 장면으로 대체 ({str(e)[:80]})")
    if on_progress:
        on_progress(len(prompts), len(prompts))
    return paths


def fill_scene_gaps(paths: list, base: Optional[str] = None) -> list:
    """None(실패 장면)을 직전 성공 이미지로, 맨 앞은 다음 성공(없으면 base)으로 채움."""
    out = list(paths)
    last = None
    for i, p in enumerate(out):
        if p:
            last = p
        elif last:
            out[i] = last
    nxt = None
    for i in range(len(out) - 1, -1, -1):
        if out[i]:
            nxt = out[i]
        elif nxt:
            out[i] = nxt
    return [p or base for p in out]


def scene_slideshow(
    images_spans: list,
    out_path: str,
    canvas: Canvas,
    motion: str = "zoom_in",
    motion_amount: float = 0.08,
    fade_s: float = 0.3,
) -> str:
    """[(이미지, 구간 μs)] → 문장 타이밍에 맞춰 넘어가는 배경 영상 (무음).

    장면마다 살짝 줌(켄번즈) + 경계 페이드로 이어 붙인다. 전체 길이 = 구간 합.
    """
    if not images_spans:
        raise BackgroundError("장면 이미지가 없습니다")
    w, h, fps = canvas.w, canvas.h, canvas.fps
    up_w, up_h = int(w * 1.5) & ~1, int(h * 1.5) & ~1
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", "-nostdin"]
    parts = []
    n = len(images_spans)
    for i, (img, dur_us) in enumerate(images_spans):
        dur_s = max(0.15, dur_us / 1e6)
        # -framerate 필수: 이미지 loop 기본은 25fps라 캔버스 fps와 어긋나 길이가 줄어든다
        args += ["-framerate", str(fps), "-loop", "1", "-t", f"{dur_s:.3f}", "-i", str(img)]
        frames = max(1, int(dur_s * fps))
        chain = (f"[{i}:v]scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
                 f"crop={up_w}:{up_h}")
        if motion in ("zoom_in", "zoom_out"):
            amt = max(0.02, min(0.2, motion_amount))
            if motion == "zoom_in":
                z = f"min(1+{amt}*on/{frames},1+{amt})"
            else:
                z = f"max(1+{amt}-{amt}*on/{frames},1)"
            chain += (f",zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                      f":d=1:s={w}x{h}:fps={fps}")
        else:
            chain += f",scale={w}:{h},fps={fps}"
        fd = min(fade_s, dur_s / 3)
        if n > 1:
            if i > 0:
                chain += f",fade=t=in:st=0:d={fd:.3f}"
            if i < n - 1:
                chain += f",fade=t=out:st={max(0.0, dur_s - fd):.3f}:d={fd:.3f}"
        parts.append(chain + f",setsar=1[v{i}]")
    fc = (";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(n))
          + f"concat=n={n}:v=1:a=0[v]")
    script = Path(out_path).with_suffix(".filter.txt")  # 장면 많으면 명령줄 한계 회피
    script.write_text(fc, encoding="utf-8")
    args += ["-filter_complex_script", str(script), "-map", "[v]",
             "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]
    ff.run(args)
    return str(out_path)


def prepare_background(
    out_path: str,
    canvas: Canvas,
    user_image: Optional[str] = None,
    prompt: str = "",
    provider: Optional[GeminiImage] = None,
    on_note: Optional[callable] = None,
) -> tuple:
    """우선순위: 사용자 이미지 → 제공자(Gemini) → 로컬 그라데이션 폴백.

    배경은 비필수라, 제공자에서 어떤 예외가 나도 로컬 폴백으로 넘어가 작업을 살린다.
    반환: (배경 경로, 출처) — 출처는 "user"/"ai"/"ai_fail:사유"/"local".
    완료 화면에서 어떤 배경이 쓰였는지 보여주기 위한 값 (v0.40).
    """
    if user_image:
        try:
            return normalize_to_canvas(user_image, out_path, canvas), "user"
        except ff.FFmpegError:
            if on_note:
                on_note("배경 이미지를 읽지 못해 기본 배경으로 대체합니다")
    ai_fail = ""
    if provider is not None:
        try:
            return provider.generate(prompt, out_path, canvas), "ai"
        except Exception as e:  # 배경 실패가 작업 전체를 죽이지 않게 (§5.6 정신)
            ai_fail = str(e)[:120]
            if on_note:
                on_note(f"AI 배경 생성 실패 → 기본 배경 사용 ({ai_fail})")
    path = generate_local(out_path, canvas, seed_text=prompt)
    return path, (f"ai_fail:{ai_fail}" if ai_fail else "local")
