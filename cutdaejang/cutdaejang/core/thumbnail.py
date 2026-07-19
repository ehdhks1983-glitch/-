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


# ─────────── v0.48: 크몽식 고퀄 타이포 프리셋 ───────────
# "글씨체만"이 아니라 입체(다층 오프셋 기둥)·다중 테두리·줄별 색 교차·기울임까지.
# 배경은 대비↑+비네트로 눌러 글자가 튀게 (전문 업체 썸네일 문법).
THUMB_PRESETS = {
    "임팩트": {   # 노랑·흰 교차 + 굵은 검정 테두리 + 기울임 + 입체
        "line_colors": ["#FFE94A", "#FFFFFF"], "outline": "#141414",
        "depth": "#141414", "hl": "#FF4D4D", "extrude": 10, "rotate": -4,
        "size_frac": 0.165,
    },
    "포인트": {   # 흰/노랑/하늘 줄 교차 ("알잘딱깔센" 감성)
        "line_colors": ["#FFFFFF", "#FFE94A", "#7DC8FF"], "outline": "#0B1030",
        "depth": "#0B1030", "hl": "#FF4D4D", "extrude": 7, "rotate": 0,
        "size_frac": 0.15,
    },
    "입체3D": {   # 흰 글자 + 빨강 돌출 기둥 (3D)
        "line_colors": ["#FFFFFF"], "outline": "#202020",
        "depth": "#D7262D", "hl": "#FFD400", "extrude": 16, "rotate": -3,
        "size_frac": 0.16,
    },
    # "깔끔" = 기존 반투명 띠 스타일 (레거시 경로)
}

_LAYER_ASS = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: T,{font},48,&H00FFFFFF,&H000000FF,&H00101010,&H00000000,1,0,0,0,100,100,0,0,1,3,0,5,20,20,20,1
Style: Badge,{font},{badge_size},&H00FFFFFF,&H000000FF,{badge_box},&HB0000000,0,0,0,0,100,100,0,0,3,{badge_pad},0,9,{ml},{mr},{badge_mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events}
"""


import re as _re

_MARKUP = _re.compile(r"\[/?[가-힣A-Za-z]*\]")  # 훅 스튜디오 [색]…[/] 마크업 제거


def _esc_ass(text: str) -> str:
    text = _MARKUP.sub("", text)
    return text.replace("\\", "").replace("{", "(").replace("}", ")").strip()


def _preset_events(title: str, highlight: str, p: dict, w: int, h: int,
                   pos_x: float = 0.5, pos_y: float = 0.46) -> str:
    """제목(여러 줄)을 입체 레이어 이벤트로 — 아래 깊이 기둥 + 맨 위 컬러 글자.

    줄 안의 " | 단어"는 그 줄의 강조 단어(포인트색)로 해석한다 (훅과 동일 문법).
    """
    raw_lines = [ln for ln in title.splitlines() if ln.strip()] or ["썸네일"]
    lines, line_hls = [], []
    for ln in raw_lines:
        hl = highlight
        if "|" in ln:
            ln, hl = ln.rsplit("|", 1)
        txt = _esc_ass(ln)
        if txt:
            lines.append(txt)
            line_hls.append(_esc_ass(hl))
    if not lines:
        lines, line_hls = ["썸네일"], [""]
    size = max(56, int(h * p["size_frac"]))
    # 줄 수가 많으면 화면을 넘지 않게 자동 축소
    line_gap = int(size * 1.18)
    while len(lines) * line_gap > h * 0.72 and size > 40:
        size = int(size * 0.9)
        line_gap = int(size * 1.18)
    # 글자 블록 중심 — 마우스로 옮긴 위치 (v0.49). 화면 밖으로 못 나가게 클램프
    cx = int(w * max(0.15, min(0.85, pos_x)))
    cy = int(h * max(0.12, min(0.85, pos_y)))
    y0 = cy - line_gap * (len(lines) - 1) // 2
    bord = max(3, int(size * 0.075))
    hl = _ass_bgr(p["hl"])
    events = []
    for li, line in enumerate(lines):
        color = p["line_colors"][li % len(p["line_colors"])]
        y = y0 + li * line_gap
        base = (f"\\an5\\b1\\frz{p['rotate']}\\fs{size}\\bord{bord}"
                f"\\3c{_ass_bgr(p['outline'])}\\shad0")
        # ① 깊이 기둥 — 2px 간격 오프셋 레이어 (입체 돌출). 테두리도 깊이색으로
        #    통일해야 기둥이 단색으로 보인다 (테두리색이 덮으면 검은 기둥이 됨)
        depth = _ass_bgr(p["depth"])
        for d in range(p["extrude"], 0, -2):
            events.append(
                f"Dialogue: 0,0:00:00.00,0:00:10.00,T,,0,0,0,,"
                f"{{\\pos({cx + d},{y + d}){base}\\1c{depth}\\3c{depth}}}{line}")
        # ② 맨 위 컬러 글자 (강조 단어는 포인트색)
        top = line
        hw = (line_hls[li] or "").strip()
        if hw and hw in line:
            top = line.replace(
                hw, f"{{\\1c{hl}}}{hw}{{\\1c{_ass_bgr(color)}}}", 1)
        events.append(
            f"Dialogue: 1,0:00:00.00,0:00:10.00,T,,0,0,0,,"
            f"{{\\pos({cx},{y}){base}\\1c{_ass_bgr(color)}}}{top}")
    return "\n".join(events)


def _write_preset_ass(title: str, highlight: str, preset: str, style: Style,
                      w: int, h: int, path: Path, badge: str = "",
                      badge_color: str = "#16A34A",
                      pos_x: float = 0.5, pos_y: float = 0.46) -> str:
    p = THUMB_PRESETS[preset]
    badge_size = max(28, int(h * 0.055))
    events = _preset_events(title, highlight, p, w, h, pos_x=pos_x, pos_y=pos_y)
    if badge.strip():
        events += ("\nDialogue: 2,0:00:00.00,0:00:10.00,Badge,,0,0,0,,"
                   + hook_dialogue_text(badge.strip(), style).replace("\n", " "))
    ass = _LAYER_ASS.format(
        w=w, h=h, font=presets.font_family(style.font), events=events,
        badge_size=badge_size, badge_box=_ass_bgr(badge_color),
        badge_pad=max(8, int(badge_size * 0.35)),
        ml=int(w * 0.045), mr=int(w * 0.045), badge_mv=int(h * 0.06),
    )
    Path(path).write_text(ass, encoding="utf-8")
    return str(path)


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
    preset: str = "깔끔",
    pos_x: float = 0.5,
    pos_y: float = 0.46,
) -> str:
    """배경(영상/사진) + 제목 → 16:9 유튜브 썸네일 PNG.

    highlight 단어는 강조색, badge는 우상단 라벨("✅ 자동 발행" 등, 초록 박스).
    preset(v0.48): "임팩트"/"포인트"/"입체3D" = 크몽식 입체 타이포(중앙, 배경 눌러줌),
    "깔끔"(기본) = 기존 반투명 띠 스타일.
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

    if preset in THUMB_PRESETS:
        ass = _write_preset_ass(title, highlight, preset, style, w, h,
                                work / "thumb.ass", badge=badge, badge_color=badge_color,
                                pos_x=pos_x, pos_y=pos_y)
        # 배경을 어둡고 진하게 눌러 글자가 튀게 + 가장자리 비네트 (업체 썸네일 문법)
        grade = "eq=brightness=-0.12:contrast=1.14:saturation=1.15,vignette"
    else:
        ttl = f"{title} | {highlight}" if highlight.strip() else title
        ass = _write_thumb_ass(ttl, style, w, h, work / "thumb.ass", band=band,
                               badge=badge, badge_color=badge_color)
        grade = "eq=brightness=-0.05:saturation=1.08"
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={w}:{h},{grade},"
        f"subtitles=filename={ff.escape_filter_value(str(ass))}"
        f":fontsdir={ff.escape_filter_value(str(fonts_dir))}"
    )
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error", "-i", bg,
        "-vf", vf, "-frames:v", "1", str(out_path),
    ])
    return str(out_path)
