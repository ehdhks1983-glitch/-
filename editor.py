"""
editor.py - 애니메이션 이미지 편집 코어
GIF/WebP/APNG 프레임 단위 편집 함수
"""

from pathlib import Path
from typing import List, Tuple, Optional, Callable

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter


def _load_text_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """한글 지원 폰트 로더 (malgun → nanum → dejavu → arial → 기본)"""
    if bold:
        paths = ["C:/Windows/Fonts/malgunbd.ttf", "malgunbd.ttf",
                 "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"]
    else:
        paths = ["C:/Windows/Fonts/malgun.ttf", "malgun.ttf",
                 "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ════════════════════════════════════════
# 프레임 로딩 / 저장
# ════════════════════════════════════════

def load_frames(path: str) -> Tuple[List[Image.Image], List[int], int]:
    """
    애니메이션 이미지 로드 → (프레임 리스트, 딜레이 리스트(ms), loop)
    """
    img = Image.open(path)
    frames = []
    durations = []

    try:
        while True:
            frames.append(img.copy().convert("RGBA"))
            durations.append(img.info.get("duration", 100))
            img.seek(img.tell() + 1)
    except EOFError:
        pass

    loop = img.info.get("loop", 0)
    img.close()

    if not durations:
        durations = [100] * len(frames)

    return frames, durations, loop


def save_frames(
    frames: List[Image.Image],
    durations: List[int],
    output_path: str,
    output_format: str = "gif",
    loop: int = 0,
    quality: int = 80,
):
    """프레임 리스트 → 애니메이션 이미지 저장 (워터마크 자동 적용)"""
    if not frames:
        return

    # ── 💧 워터마크 (전역 설정 켜져 있을 때만 새 프레임으로 합성) ──
    _wm = None
    try:
        from watermark import watermark, apply_to_frame
        if watermark.active:
            _wm = [apply_to_frame(f) for f in frames]
            frames = _wm
    except Exception:
        _wm = None

    if output_format == "gif":
        converted = []
        for f in frames:
            rgb = f.convert("RGB")
            q = rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=1)
            converted.append(q)
            rgb.close()
        converted[0].save(
            output_path, save_all=True, append_images=converted[1:],
            duration=durations, loop=loop, optimize=True,
        )
        for c in converted:
            c.close()

    elif output_format == "webp":
        rgba = [f.convert("RGBA") for f in frames]
        rgba[0].save(
            output_path, save_all=True, append_images=rgba[1:],
            duration=durations, loop=loop, quality=quality, lossless=False,
        )
        for r in rgba:
            r.close()

    elif output_format == "apng":
        rgba = [f.convert("RGBA") for f in frames]
        rgba[0].save(
            output_path, save_all=True, append_images=rgba[1:],
            duration=durations, loop=loop,
        )
        for r in rgba:
            r.close()

    if _wm:
        for f in _wm:
            try:
                f.close()
            except Exception:
                pass


# ════════════════════════════════════════
# 기본 편집
# ════════════════════════════════════════

def crop_frames(
    frames: List[Image.Image],
    x: int, y: int, w: int, h: int,
) -> List[Image.Image]:
    """프레임 크롭"""
    return [f.crop((x, y, x + w, y + h)) for f in frames]


def crop_ratio(
    frames: List[Image.Image],
    ratio: str = "1:1",
) -> List[Image.Image]:
    """비율 기반 크롭 (센터)"""
    if not frames:
        return frames

    ratios = {"1:1": (1, 1), "16:9": (16, 9), "4:3": (4, 3), "3:2": (3, 2), "9:16": (9, 16)}
    rw, rh = ratios.get(ratio, (1, 1))

    fw, fh = frames[0].width, frames[0].height
    target_ratio = rw / rh
    current_ratio = fw / fh

    if current_ratio > target_ratio:
        new_w = int(fh * target_ratio)
        x = (fw - new_w) // 2
        return crop_frames(frames, x, 0, new_w, fh)
    else:
        new_h = int(fw / target_ratio)
        y = (fh - new_h) // 2
        return crop_frames(frames, 0, y, fw, new_h)


def resize_frames(
    frames: List[Image.Image],
    width: int = 0,
    height: int = 0,
    percent: int = 0,
) -> List[Image.Image]:
    """
    리사이즈. percent > 0 이면 % 기준, 아니면 px 기준.
    width만 주면 height 자동 비율 유지.
    """
    if not frames:
        return frames

    if percent > 0:
        ratio = percent / 100.0
        w = max(1, int(frames[0].width * ratio))
        h = max(1, int(frames[0].height * ratio))
    elif width > 0 and height > 0:
        w, h = width, height
    elif width > 0:
        ratio = width / frames[0].width
        w = width
        h = max(1, int(frames[0].height * ratio))
    elif height > 0:
        ratio = height / frames[0].height
        h = height
        w = max(1, int(frames[0].width * ratio))
    else:
        return frames

    return [f.resize((w, h), Image.LANCZOS) for f in frames]


def rotate_frames(
    frames: List[Image.Image],
    angle: int = 90,
    expand: bool = True,
) -> List[Image.Image]:
    """회전 (90, 180, 270 또는 자유 각도)"""
    return [f.rotate(-angle, expand=expand, resample=Image.BICUBIC) for f in frames]


def flip_frames(
    frames: List[Image.Image],
    horizontal: bool = True,
) -> List[Image.Image]:
    """좌우 또는 상하 반전"""
    if horizontal:
        return [f.transpose(Image.FLIP_LEFT_RIGHT) for f in frames]
    return [f.transpose(Image.FLIP_TOP_BOTTOM) for f in frames]


# ════════════════════════════════════════
# 속도 / 재생 편집
# ════════════════════════════════════════

def adjust_speed(
    durations: List[int],
    speed: float = 1.0,
) -> List[int]:
    """속도 조절 — 딜레이를 변경 (원본 프레임 유지)"""
    return [max(10, int(d / max(0.01, speed))) for d in durations]


def reverse_frames(
    frames: List[Image.Image],
    durations: List[int],
) -> Tuple[List[Image.Image], List[int]]:
    """역재생"""
    return list(reversed(frames)), list(reversed(durations))


def boomerang(
    frames: List[Image.Image],
    durations: List[int],
) -> Tuple[List[Image.Image], List[int]]:
    """부메랑 (정방향 → 역방향, 첫/끝 프레임 중복 제거)"""
    if len(frames) <= 2:
        return frames, durations
    rev_frames = list(reversed(frames[1:-1]))
    rev_durations = list(reversed(durations[1:-1]))
    return frames + rev_frames, durations + rev_durations


# ════════════════════════════════════════
# 색상 필터 / 효과
# ════════════════════════════════════════

def apply_grayscale(frames: List[Image.Image]) -> List[Image.Image]:
    """흑백"""
    result = []
    for f in frames:
        gray = f.convert("L").convert("RGBA")
        result.append(gray)
    return result


def apply_sepia(frames: List[Image.Image]) -> List[Image.Image]:
    """세피아"""
    result = []
    for f in frames:
        gray = f.convert("L")
        sepia = Image.merge("RGB", (
            gray.point(lambda x: min(255, int(x * 1.2))),
            gray.point(lambda x: min(255, int(x * 1.0))),
            gray.point(lambda x: min(255, int(x * 0.8))),
        ))
        result.append(sepia.convert("RGBA"))
        gray.close()
        sepia.close()
    return result


def apply_brightness(
    frames: List[Image.Image],
    factor: float = 1.0,
) -> List[Image.Image]:
    """밝기 조절 (1.0=원본, <1 어둡게, >1 밝게)"""
    return [ImageEnhance.Brightness(f).enhance(factor) for f in frames]


def apply_contrast(
    frames: List[Image.Image],
    factor: float = 1.0,
) -> List[Image.Image]:
    """대비 조절"""
    return [ImageEnhance.Contrast(f).enhance(factor) for f in frames]


def apply_blur(
    frames: List[Image.Image],
    radius: float = 2.0,
) -> List[Image.Image]:
    """블러"""
    return [f.filter(ImageFilter.GaussianBlur(radius=radius)) for f in frames]


def apply_sharpen(frames: List[Image.Image]) -> List[Image.Image]:
    """샤프닝"""
    return [f.filter(ImageFilter.SHARPEN) for f in frames]


# ════════════════════════════════════════
# 텍스트 / 워터마크
# ════════════════════════════════════════

def add_text(
    frames: List[Image.Image],
    text: str,
    position: str = "bottom",
    font_size: int = 24,
    color: str = "#FFFFFF",
    bg_color: Optional[str] = None,
    font_path: Optional[str] = None,
) -> List[Image.Image]:
    """
    모든 프레임에 텍스트 삽입.
    position: top, center, bottom, top-left, top-right, bottom-left, bottom-right
    """
    result = []

    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except (OSError, IOError):
            font = _load_text_font(font_size)
    else:
        font = _load_text_font(font_size)

    for f in frames:
        img = f.copy()
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        padding = 6

        x, y = _calc_text_position(position, img.width, img.height, tw, th, padding)

        if bg_color:
            draw.rectangle(
                [x - padding, y - padding, x + tw + padding, y + th + padding],
                fill=bg_color,
            )

        draw.text((x, y), text, fill=color, font=font)
        result.append(img)

    return result


def _calc_text_position(
    position: str, fw: int, fh: int, tw: int, th: int, padding: int,
) -> Tuple[int, int]:
    """텍스트 위치 계산"""
    margin = padding * 2
    positions = {
        "top": (fw // 2 - tw // 2, margin),
        "center": (fw // 2 - tw // 2, fh // 2 - th // 2),
        "bottom": (fw // 2 - tw // 2, fh - th - margin),
        "top-left": (margin, margin),
        "top-right": (fw - tw - margin, margin),
        "bottom-left": (margin, fh - th - margin),
        "bottom-right": (fw - tw - margin, fh - th - margin),
    }
    return positions.get(position, positions["bottom"])


def add_watermark(
    frames: List[Image.Image],
    watermark_path: str,
    position: str = "bottom-right",
    opacity: float = 0.5,
    scale: float = 0.2,
) -> List[Image.Image]:
    """이미지 워터마크 삽입"""
    try:
        wm = Image.open(watermark_path).convert("RGBA")
    except Exception:
        return frames

    result = []
    for f in frames:
        img = f.copy().convert("RGBA")

        # 워터마크 리사이즈
        wm_w = max(1, int(img.width * scale))
        wm_h = max(1, int(wm.height * (wm_w / wm.width)))
        wm_resized = wm.resize((wm_w, wm_h), Image.LANCZOS)

        # 투명도 조절
        if opacity < 1.0:
            alpha = wm_resized.split()[3]
            alpha = alpha.point(lambda a: int(a * opacity))
            wm_resized.putalpha(alpha)

        # 위치 계산
        margin = 10
        pos_map = {
            "top-left": (margin, margin),
            "top-right": (img.width - wm_w - margin, margin),
            "bottom-left": (margin, img.height - wm_h - margin),
            "bottom-right": (img.width - wm_w - margin, img.height - wm_h - margin),
            "center": (img.width // 2 - wm_w // 2, img.height // 2 - wm_h // 2),
        }
        x, y = pos_map.get(position, pos_map["bottom-right"])

        img.paste(wm_resized, (x, y), wm_resized)
        result.append(img)
        wm_resized.close()

    wm.close()
    return result


def add_frame_numbers(
    frames: List[Image.Image],
    font_size: int = 16,
    color: str = "#FFFFFF",
    bg_color: str = "#00000080",
) -> List[Image.Image]:
    """프레임 번호 표시"""
    result = []
    total = len(frames)

    font = _load_text_font(font_size)

    for i, f in enumerate(frames):
        img = f.copy()
        draw = ImageDraw.Draw(img)
        text = f"{i+1}/{total}"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 4
        draw.rectangle([pad, pad, pad + tw + pad * 2, pad + th + pad * 2], fill=bg_color)
        draw.text((pad * 2, pad * 2), text, fill=color, font=font)
        result.append(img)

    return result


# ════════════════════════════════════════
# 편집 파이프라인 (여러 효과 체이닝)
# ════════════════════════════════════════

def _swap_frames(old: List[Image.Image], new: List[Image.Image]) -> List[Image.Image]:
    """이전 프레임 리스트 닫고 새 리스트 반환 (같은 객체면 스킵)"""
    if old is not new:
        for img in old:
            try:
                img.close()
            except Exception:
                pass
    return new


def apply_edits(
    frames: List[Image.Image],
    durations: List[int],
    edits: dict,
) -> Tuple[List[Image.Image], List[int]]:
    """
    편집 옵션 딕셔너리로 일괄 적용.
    각 단계에서 이전 프레임 메모리를 해제하여 누수 방지.
    """
    f, d = frames, durations

    # 크롭
    if edits.get("crop_ratio"):
        f = _swap_frames(f, crop_ratio(f, edits["crop_ratio"]))
    elif edits.get("crop"):
        cx, cy, cw, ch = edits["crop"]
        f = _swap_frames(f, crop_frames(f, cx, cy, cw, ch))

    # 리사이즈
    if edits.get("resize_percent"):
        f = _swap_frames(f, resize_frames(f, percent=edits["resize_percent"]))
    elif edits.get("resize_width"):
        f = _swap_frames(f, resize_frames(f, width=edits["resize_width"]))

    # 회전
    if edits.get("rotate"):
        f = _swap_frames(f, rotate_frames(f, angle=edits["rotate"]))

    # 반전
    if edits.get("flip_h"):
        f = _swap_frames(f, flip_frames(f, horizontal=True))
    if edits.get("flip_v"):
        f = _swap_frames(f, flip_frames(f, horizontal=False))

    # 색상
    if edits.get("grayscale"):
        f = _swap_frames(f, apply_grayscale(f))
    elif edits.get("sepia"):
        f = _swap_frames(f, apply_sepia(f))

    if edits.get("brightness") and edits["brightness"] != 1.0:
        f = _swap_frames(f, apply_brightness(f, edits["brightness"]))
    if edits.get("contrast") and edits["contrast"] != 1.0:
        f = _swap_frames(f, apply_contrast(f, edits["contrast"]))
    if edits.get("blur"):
        f = _swap_frames(f, apply_blur(f, edits["blur"]))
    if edits.get("sharpen"):
        f = _swap_frames(f, apply_sharpen(f))

    # 텍스트
    if edits.get("text"):
        f = _swap_frames(f, add_text(f, edits["text"],
                     position=edits.get("text_position", "bottom"),
                     font_size=edits.get("text_size", 24),
                     color=edits.get("text_color", "#FFFFFF")))

    # 프레임 번호
    if edits.get("frame_numbers"):
        f = _swap_frames(f, add_frame_numbers(f))

    # 속도 (딜레이 변경 — 프레임 객체 안 바뀜)
    if edits.get("speed") and edits["speed"] != 1.0:
        d = adjust_speed(d, edits["speed"])

    # 역재생 (순서만 바뀜 — 같은 객체 재사용)
    if edits.get("reverse"):
        f, d = reverse_frames(f, d)

    # 부메랑 (기존 프레임 + 역순 복사 — 같은 객체 재사용)
    if edits.get("boomerang"):
        f, d = boomerang(f, d)

    return f, d


# ════════════════════════════════════════
# 길이 제한 / 카카오톡 이모티콘 프리셋
# ════════════════════════════════════════

def trim_to_duration(
    frames: List[Image.Image],
    durations: List[int],
    max_ms: int = 3000,
) -> Tuple[List[Image.Image], List[int]]:
    """
    누적 재생시간이 max_ms 이하가 되도록 뒤쪽 프레임을 잘라낸다 (최소 1프레임 보존).
    선택된 프레임만 반환하며, 잘려나간 프레임은 호출자가 정리한다.
    """
    if not frames:
        return frames, durations
    kept_f: List[Image.Image] = []
    kept_d: List[int] = []
    acc = 0
    for f, d in zip(frames, durations):
        if kept_f and acc + d > max_ms:
            break
        kept_f.append(f)
        kept_d.append(d)
        acc += d
    return kept_f, kept_d


def make_kakao_emoticon(
    input_path: str,
    output_path: str,
    size: int = 360,
    max_ms: int = 3000,
    quality: int = 90,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Optional[str]:
    """
    기존 GIF/WebP/APNG → 카카오톡 이모티콘 규격으로 변환.
    규격: 정사각형 size×size, 최대 max_ms(기본 3초), WebP.
    (용량 3MB 제한은 호출 측에서 optimizer로 추가 처리)
    """
    def prog(p, m):
        if on_progress:
            on_progress(p, m)

    def _close(imgs):
        for x in imgs:
            try:
                x.close()
            except Exception:
                pass

    prog(5, "프레임 로딩...")
    frames, durations, loop = load_frames(input_path)
    if not frames:
        return None

    try:
        # 1) 정사각형(1:1) 센터 크롭
        prog(25, "정사각형으로 자르는 중...")
        cropped = crop_ratio(frames, "1:1")
        if cropped is not frames:
            _close(frames)

        # 2) size×size 리사이즈
        prog(45, f"{size}×{size} 크기로 변환 중...")
        resized = [im.resize((size, size), Image.LANCZOS) for im in cropped]
        _close(cropped)

        # 3) max_ms 이내로 자르기
        prog(65, f"{max_ms / 1000:.0f}초 이내로 맞추는 중...")
        kept_f, kept_d = trim_to_duration(resized, durations, max_ms)
        kept_ids = {id(x) for x in kept_f}
        _close([x for x in resized if id(x) not in kept_ids])

        # 4) WebP 저장
        prog(85, "WebP로 저장 중...")
        save_frames(kept_f, kept_d, output_path, "webp", loop, quality=quality)
        _close(kept_f)

        prog(100, "✅ 카톡 이모티콘 완성!")
        return output_path
    except Exception:
        return None
