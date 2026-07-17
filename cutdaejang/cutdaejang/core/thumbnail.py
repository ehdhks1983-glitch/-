"""유튜브 썸네일(16:9) 자동 생성 — 대본/주제에 맞는 후킹 카피 + 임팩트 텍스트.

배경(영상 프레임 또는 사진) 위에 굵은 배경 띠 제목 + 강조색을 얹어 1280×720 PNG로.
텍스트 스타일은 영상 자막/훅과 동일 엔진(ass_writer)을 재사용한다.
AI 이미지 생성 없이도 되도록 배경은 '영상에서 뽑은 프레임'을 기본으로 한다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .. import presets
from ..spec import Style
from ..utils import ffmpeg as ff
from .render_engine import DEFAULT_FONTS_DIR
from .render_engine.ass_writer import hook_dialogue_text
from .video_editor import VIDEO_EXTS

log = logging.getLogger("cutdaejang")

_ASS = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Thumb,{font},{size},&H00FFFFFF,&H000000FF,{box},&HB0000000,0,0,0,0,100,100,0,0,{border},{pad},0,{align},{ml},{mr},{mv},1
Style: Badge,{font},{badge_size},&H00FFFFFF,&H000000FF,{badge_box},&HB0000000,0,0,0,0,100,100,0,0,3,{badge_pad},0,9,{ml},{mr},{badge_mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:10.00,Thumb,,0,0,0,,{text}
{badge_line}
"""


def _extract_frame(video: str, out_png: Path, at_frac: float = 0.4) -> str:
    """영상에서 대표 프레임 1장 추출 (검은 인트로 피하려 40% 지점)."""
    dur_us = ff.probe_duration_us(str(video))
    ss = max(0.0, (dur_us / 1e6) * at_frac)
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-ss", f"{ss:.2f}", "-i", str(video), "-frames:v", "1", str(out_png),
    ])
    return str(out_png)


def _ass_bgr(hex_rgb: str, alpha: str = "00") -> str:
    rgb = hex_rgb.lstrip("#")
    return f"&H{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}".upper()


def _write_thumb_ass(title: str, style: Style, w: int, h: int, path: Path,
                     band: bool = True, badge: str = "",
                     badge_color: str = "#16A34A") -> str:
    size = max(48, int(h * 0.15))          # 720p 기준 ≈ 108px
    pad = max(10, int(size * 0.18))
    badge_size = max(28, int(h * 0.055))
    badge_line = ""
    if badge.strip():  # 우상단 배지 (초록 박스 + 흰 글씨 — "✅ 자동 발행" 스타일)
        badge_line = (
            "Dialogue: 1,0:00:00.00,0:00:10.00,Badge,,0,0,0,,"
            + hook_dialogue_text(badge.strip(), style).replace("\n", " ")
        )
    ass = _ASS.format(
        w=w, h=h,
        font=presets.font_family(style.font),
        size=size,
        box="&H90101010" if band else "&H00101010",
        border=3 if band else 1,
        pad=pad if band else max(4, int(size * 0.06)),
        align=1,                            # 좌하단 (레퍼런스 스타일)
        ml=int(w * 0.045), mr=int(w * 0.045), mv=int(h * 0.08),
        text=hook_dialogue_text(title, style),
        badge_size=badge_size,
        badge_box=_ass_bgr(badge_color),
        badge_pad=max(8, int(badge_size * 0.35)),
        badge_mv=int(h * 0.06),
        badge_line=badge_line,
    )
    Path(path).write_text(ass, encoding="utf-8")
    return str(path)


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def make_thumbnail(
    bg_source: str,
    title: str,
    out_path: str,
    highlight: str = "",
    style: Optional[Style] = None,
    w: int = 1280,
    h: int = 720,
    band: bool = True,
    badge: str = "",
    badge_color: str = "#16A34A",
    fonts_dir: str = DEFAULT_FONTS_DIR,
    workdir: Optional[str] = None,
) -> str:
    """배경(영상/사진) + 제목 → 16:9 유튜브 썸네일 PNG.

    highlight 단어는 강조색, badge는 우상단 라벨("✅ 자동 발행" 등, 초록 박스).
    """
    style = style or Style()
    work = Path(workdir or Path(out_path).parent)
    work.mkdir(parents=True, exist_ok=True)

    src = Path(bg_source)
    if src.suffix.lower() in VIDEO_EXTS:
        bg = _extract_frame(str(src), work / "thumb_bg.png")
    elif src.is_file():
        bg = str(src)
    else:
        raise ValueError(f"배경 이미지/영상을 찾을 수 없습니다: {bg_source}")

    ttl = f"{title} | {highlight}" if highlight.strip() else title
    ass = _write_thumb_ass(ttl, style, w, h, work / "thumb.ass", band=band,
                           badge=badge, badge_color=badge_color)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={w}:{h},eq=brightness=-0.05:saturation=1.08,"
        f"subtitles=filename={ff.escape_filter_value(str(ass))}"
        f":fontsdir={ff.escape_filter_value(str(fonts_dir))}"
    )
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error", "-i", bg,
        "-vf", vf, "-frames:v", "1", str(out_path),
    ])
    return str(out_path)
