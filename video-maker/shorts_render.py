"""
shorts_render.py — 프레임 렌더링 (PIL)
사진을 템플릿(blur/fill/card)에 맞춰 1080×1920 프레임으로 그린다. 미리보기에도 사용.
(부록 A 분리: 분리 전 shorts_maker.py의 폰트/이미지 배치/자막 그리기/프레임 렌더부 — 동작 동일)
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from shorts_common import W, H
from shorts_models import ShortsSegment


# ════════════════════════════════════════
# 켄번스(줌/팬 모션) 필터 — 1-1
# ════════════════════════════════════════
def kenburns_vf(fps: int, duration: float, direction: str = "in",
                max_zoom: float = 1.15, zoom_step: float = 0.0008,
                prescale: int = 2) -> str:
    """정지 사진용 zoompan(켄번스) ffmpeg -vf 필터 문자열을 만든다.

    `-loop 1 -i png -t <duration>` 구조에서 fps*duration 프레임을 정확히 생성한다.
    prescale로 먼저 업스케일한 뒤 작은 zoom_step을 적용해 정수좌표 계단현상(떨림)을 완화.
    중앙 기준으로 줌인/줌아웃하며 x/y는 항상 가운데 정렬.
    """
    d = max(1, int(round(fps * float(duration))))
    pre = max(1, int(prescale))
    sw, sh = W * pre, H * pre
    mz = max(1.0, float(max_zoom))
    step = max(0.0, float(zoom_step))
    dir_ = (direction or "in").lower()
    if dir_ == "random":
        dir_ = random.choice(("in", "out"))
    if dir_ == "out":
        z = f"if(eq(on,0),{mz:.4f},max(zoom-{step:.4f},1.0))"
    else:  # in
        z = f"min(zoom+{step:.4f},{mz:.4f})"
    return (f"scale={sw}:{sh},"
            f"zoompan=z='{z}':d={d}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps}")


# ════════════════════════════════════════
# 폰트
# ════════════════════════════════════════
def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
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
# 이미지 배치 헬퍼
# ════════════════════════════════════════
def _crop_fill(img: Image.Image, tw: int, th: int) -> Image.Image:
    """비율 유지하며 tw×th를 꽉 채우도록 크롭"""
    ratio = max(tw / img.width, th / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    r = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - tw) // 2, (nh - th) // 2
    return r.crop((x, y, x + tw, y + th))


def _fit(img: Image.Image, tw: int, th: int) -> Image.Image:
    """비율 유지하며 tw×th 안에 들어가도록 축소"""
    ratio = min(tw / img.width, th / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    return img.resize((nw, nh), Image.LANCZOS)


def _draw_caption(canvas: Image.Image, text: str, position: str,
                  size: int, color: str):
    """자막을 외곽선+반투명 박스와 함께 그림"""
    if not text.strip():
        return
    base = canvas.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_font(size, bold=True)

    # 줄바꿈: 화면 폭에 맞게 자동 래핑
    max_w = W - 160
    words = text.replace("\n", " \n ").split(" ")
    lines, cur = [], ""
    for w in words:
        if w == "\n":
            lines.append(cur); cur = ""; continue
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    wrapped = "\n".join(lines) if lines else text

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=10, align="center")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = max(12, int(size * 0.35))

    x = (W - tw) // 2
    if position == "top":
        y = int(H * 0.10)
    else:  # bottom
        y = H - th - int(H * 0.14)
    text_y = y - bbox[1]

    # 반투명 박스
    draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0, 150))
    # 외곽선
    bw = max(2, size // 16)
    for dx in range(-bw, bw + 1):
        for dy in range(-bw, bw + 1):
            if dx or dy:
                draw.multiline_text((x + dx, text_y + dy), wrapped, font=font,
                                    fill=(0, 0, 0, 255), spacing=10, align="center")
    draw.multiline_text((x, text_y), wrapped, font=font, fill=color,
                        spacing=10, align="center")

    base.alpha_composite(overlay)
    canvas.paste(base.convert("RGB"), (0, 0))


def render_segment_frame(seg: ShortsSegment, caption_size: int = 56,
                         caption_color: str = "#FFFFFF", with_caption: bool = True,
                         with_watermark: bool = True) -> Image.Image:
    """세그먼트 1장을 1080×1920 프레임으로 렌더링 (미리보기에도 사용).
    with_caption=False면 자막을 안 그림(빌드 시 ASS 전문 자막으로 입히기 위함).
    with_watermark=False면 워터마크를 프레임에 박지 않음(켄번스 모드에서 줌에 잘리지
    않도록 최종 합치기 단계에서 영상에 입히기 위함 — 1-1)."""
    photo = None
    if seg.image_path and Path(seg.image_path).exists():
        try:
            photo = ImageOps.exif_transpose(Image.open(seg.image_path).convert("RGB"))
        except Exception:
            photo = None

    tpl = seg.template
    cap_pos = "bottom"

    if tpl == "card":
        canvas = Image.new("RGB", (W, H), (245, 245, 247))
        if photo:
            area_top, area_bottom = int(H * 0.30), int(H * 0.92)
            fitted = _fit(photo, W - 100, area_bottom - area_top)
            px = (W - fitted.width) // 2
            py = area_top + (area_bottom - area_top - fitted.height) // 2
            canvas.paste(fitted, (px, py))
        cap_pos = "top"
        cap_color = "#111111" if caption_color.upper() == "#FFFFFF" else caption_color
    elif tpl == "fill":
        canvas = _crop_fill(photo, W, H) if photo else Image.new("RGB", (W, H), (20, 20, 20))
        cap_color = caption_color
    else:  # blur (기본)
        if photo:
            bg = _crop_fill(photo, W, H).filter(ImageFilter.GaussianBlur(45))
            fg = _fit(photo, W, H)
            canvas = bg
            canvas.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
        else:
            canvas = Image.new("RGB", (W, H), (20, 20, 20))
        cap_color = caption_color

    if with_caption:
        _draw_caption(canvas, seg.caption, cap_pos, caption_size, cap_color)
    if with_watermark:
        try:
            from watermark import apply_to_frame
            canvas = apply_to_frame(canvas)
        except Exception:
            pass
    return canvas
